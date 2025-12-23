from fastapi import FastAPI, Request, HTTPException
from docling.document_converter import DocumentConverter
import langextract as lx
from langextract.data import ExampleData, Extraction
import textwrap
import requests
import json
import tempfile
import os
import boto3

app = FastAPI()
ENGINE_SECRET = os.getenv("ENGINE_SECRET")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = "structurize-inbox"
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://<account>.r2.cloudflarestorage.com")

def get_s3_client():
    """Create S3 client lazily to avoid import-time errors"""
    return boto3.client(
        's3',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        endpoint_url=R2_ENDPOINT
    )

INVOICE_PROMPT = textwrap.dedent("""\
    Extract exactly these fields from the invoice:
    - Vendor Name (company name at top)
    - Invoice Date (usually near top)
    - Total Amount (final total, includes tax)
    - Invoice Number (INV-xxx format)
    
    Point to exact text locations. Do not guess.""")

@app.post("/process")
async def process_job(request: Request):
    if request.headers.get("x-secret") != ENGINE_SECRET:
        raise HTTPException(401, "Unauthorized")

    data = await request.json()
    r2_key = data.get("r2_key")
    job_id = data.get("job_id")

    # Use S3 client to fetch the document from R2
    s3_client = get_s3_client()
    response = s3_client.get_object(Bucket=R2_BUCKET, Key=r2_key)
    pdf_content = response['Body'].read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_content)
        temp_pdf_path = f.name

    try:
        # Get model configuration from environment variables
        model_id = os.getenv("LANGEXTRACT_MODEL_ID", "gemini-2.5-flash")
        extraction_passes = int(os.getenv("LANGEXTRACT_PASSES", "2"))
        max_workers = int(os.getenv("LANGEXTRACT_MAX_WORKERS", "4"))

        lang_result = lx.extract(
            text_or_documents=temp_pdf_path,
            prompt_description=INVOICE_PROMPT,
            model_id=model_id,
            extraction_passes=extraction_passes,
            max_workers=max_workers
        )
        
        html_viz = lx.visualize([lang_result])
        viz_key = f"proof/{data.get('job_id')}.html"
        
        get_s3_client().put_object(
            Bucket=R2_BUCKET,
            Key=viz_key,
            Body=html_viz.data,
            ContentType="text/html"
        )
        
        R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-<hash>.r2.dev")
        proof_url = f"{R2_PUBLIC_URL}/{viz_key}"
        
        converter = DocumentConverter()
        doc_result = converter.convert(temp_pdf_path)
        
        line_items = []
        if doc_result.document.tables:
            table = doc_result.document.tables[0]
            line_items = table.to_dict('records')
        
        header_data = {
            "vendor": _find_extraction(lang_result, "Vendor Name"),
            "date": _find_extraction(lang_result, "Invoice Date"),
            "total": _find_extraction(lang_result, "Total Amount"),
            "invoice_number": _find_extraction(lang_result, "Invoice Number")
        }

        structured_data = {
            "header": header_data,
            # Add flat keys for compatibility with sync worker and audit function
            "vendor": header_data["vendor"]["value"] if header_data["vendor"] else None,
            "date": header_data["date"]["value"] if header_data["date"] else None,
            "total": header_data["total"]["value"] if header_data["total"] else None,
            "invoice_number": header_data["invoice_number"]["value"] if header_data["invoice_number"] else None,
            "line_items": line_items,
            "visual_proof_url": proof_url,
            "markdown": doc_result.document.export_to_markdown()
        }
        
        return structured_data
        
    finally:
        if os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)

def _find_extraction(result, field_name):
    for doc in result.documents:
        for extraction in doc.extractions:
            if field_name in extraction.extraction_class:
                return {
                    "value": extraction.extraction_text.strip(),
                    "confidence": getattr(extraction, 'score', 1.0),
                    "span": getattr(extraction, 'span', None)
                }
    return None