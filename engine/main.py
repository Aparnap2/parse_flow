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
R2_BUCKET = "parseflow-storage"  # Updated for ParseFlow
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://<account>.r2.cloudflarestorage.com")

def get_s3_client():
    """Create S3 client lazily to avoid import-time errors"""
    return boto3.client(
        's3',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        endpoint_url=R2_ENDPOINT
    )

# ParseFlow-specific prompts for different modes
GENERAL_PROMPT = textwrap.dedent("""\
    Convert the document to markdown format preserving structure, tables, and text content.
    Focus on accuracy and layout preservation.""")

FINANCIAL_PROMPT = textwrap.dedent("""\
    Extract financial data and convert document to markdown.
    Pay special attention to tables, figures, and financial details.
    Preserve layout and structure for accurate financial analysis.""")

@app.post("/process")
async def process_job(request: Request):
    if request.headers.get("x-secret") != ENGINE_SECRET:
        raise HTTPException(401, "Unauthorized")

    data = await request.json()
    r2_key = data.get("r2_key")
    job_id = data.get("job_id")
    mode = data.get("mode", "general")  # 'general' or 'financial'

    # Use S3 client to fetch the document from R2
    s3_client = get_s3_client()
    response = s3_client.get_object(Bucket=R2_BUCKET, Key=r2_key)
    pdf_content = response['Body'].read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_content)
        temp_pdf_path = f.name

    try:
        converter = DocumentConverter()
        doc_result = converter.convert(temp_pdf_path)

        # For general mode, use Docling primarily
        if mode == "general":
            markdown_content = doc_result.document.export_to_markdown()

            # For financial mode, consider using additional processing
            # (This would integrate with DeepSeek-OCR in a full implementation)
            if mode == "financial":
                # In a full implementation, this would call the DeepSeek-OCR processor
                # For now, we'll just return the Docling result with a trust score
                trust_score = 0.85  # Placeholder for actual confidence calculation
            else:
                trust_score = 0.95  # Higher confidence for general mode with Docling

        else:
            # Default to general processing if mode is not recognized
            markdown_content = doc_result.document.export_to_markdown()
            trust_score = 0.95

        # Generate visual proof
        proof_key = f"proof/{job_id}.html"
        proof_content = f"<html><body><h1>Visual Proof for Job {job_id}</h1><p>Generated from {r2_key}</p></body></html>"

        get_s3_client().put_object(
            Bucket=R2_BUCKET,
            Key=proof_key,
            Body=proof_content,
            ContentType="text/html"
        )

        R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "https://pub-<hash>.r2.dev")
        proof_url = f"{R2_PUBLIC_URL}/{proof_key}"

        # Prepare result structure according to ParseFlow schema
        result = {
            "job_id": job_id,
            "status": "completed",
            "mode": mode,
            "trust_score": trust_score,
            "markdown": markdown_content,
            "output_key": f"results/{job_id}.json",  # Path where result will be stored
            "visual_proof_url": proof_url,
            "metrics": {
                "pages_processed": len(doc_result.document.pages) if hasattr(doc_result.document, 'pages') else 0,
                "tables_extracted": len(doc_result.document.tables) if hasattr(doc_result.document, 'tables') else 0,
                "figures_extracted": len(doc_result.document.figures) if hasattr(doc_result.document, 'figures') else 0
            }
        }

        # In a real implementation, this result would be stored in R2 and
        # a callback would be sent to the Cloudflare worker
        return result

    finally:
        if os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)