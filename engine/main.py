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
import re

app = FastAPI()
ENGINE_SECRET = os.getenv("ENGINE_SECRET")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = "sarah-ai-storage"  # Updated for Sarah AI
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "https://<account>.r2.cloudflarestorage.com")

def get_s3_client():
    """Create S3 client lazily to avoid import-time errors"""
    return boto3.client(
        's3',
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        endpoint_url=R2_ENDPOINT
    )

@app.post("/process")
async def process_job(request: Request):
    if request.headers.get("x-secret") != ENGINE_SECRET:
        raise HTTPException(401, "Unauthorized")

    data = await request.json()
    r2_key = data.get("r2_key")
    job_id = data.get("job_id")
    schema_json = data.get("schema_json")  # User-defined extraction schema

    if not schema_json:
        raise HTTPException(400, "schema_json is required")

    # Parse the schema
    try:
        schema = json.loads(schema_json)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid schema_json format")

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

        # Extract text content from the document
        markdown_content = doc_result.document.export_to_markdown()

        # Apply the user-defined schema to extract specific fields
        extracted_data = extract_with_schema(markdown_content, schema)

        # Calculate confidence based on how many required fields were found
        required_fields = [field for field in schema if 'required' in field and field['required']]
        found_fields = [field for field in required_fields if field['name'] in extracted_data]
        confidence = len(found_fields) / len(required_fields) if required_fields else 0.9

        # Apply custom math formulas if specified in schema
        for field in schema:
            if 'formula' in field:
                # Simple formula processing - in a real implementation, this would be more sophisticated
                extracted_data[field['name']] = apply_formula(extracted_data, field['formula'])

        # Prepare result structure according to Sarah AI schema
        result = {
            "job_id": job_id,
            "status": "completed",
            "confidence": confidence,
            "result": extracted_data,
            "raw_markdown": markdown_content,
            "metrics": {
                "pages_processed": len(doc_result.document.pages) if hasattr(doc_result.document, 'pages') else 0,
                "tables_extracted": len(doc_result.document.tables) if hasattr(doc_result.document, 'tables') else 0,
                "fields_extracted": len(extracted_data)
            }
        }

        return result

    finally:
        if os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)


def extract_with_schema(text, schema):
    """
    Extract data from text according to the user-defined schema
    """
    extracted = {}

    for field in schema:
        field_name = field['name']
        field_type = field.get('type', 'text')
        instruction = field.get('instruction', '')

        # Use the instruction to guide the extraction
        if field_type == 'currency':
            # Extract currency values
            pattern = r'\$?[\d,]+\.?\d*'
            matches = re.findall(pattern, text)
            if matches:
                # Take the first match that looks like a currency value
                extracted[field_name] = matches[0].replace(',', '')
        elif field_type == 'number':
            # Extract numeric values
            pattern = r'\b\d+\.?\d*\b'
            matches = re.findall(pattern, text)
            if matches:
                extracted[field_name] = matches[0]
        elif field_type == 'date':
            # Extract date values
            date_patterns = [
                r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # MM/DD/YYYY or MM/DD/YY
                r'\b\d{4}-\d{2}-\d{2}\b',         # YYYY-MM-DD
                r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',  # MM-DD-YYYY or MM-DD-YY
            ]
            for pattern in date_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    extracted[field_name] = matches[0]
                    break
        elif field_type == 'text':
            # Extract text based on the instruction
            # This is a simplified approach - in a real implementation, you'd use an LLM to extract based on the instruction
            extracted[field_name] = extract_text_by_instruction(text, instruction)

    return extracted


def extract_text_by_instruction(text, instruction):
    """
    Extract text based on the instruction
    """
    # This is a simplified implementation - in a real system, you would use an LLM to extract based on the instruction
    # For now, we'll just look for the instruction text in the document and return the following text
    import re

    # Look for the instruction in the text
    pattern = re.compile(re.escape(instruction) + r'\s*[:\-\—]\s*([^\n\r.]+)', re.IGNORECASE)
    match = pattern.search(text)

    if match:
        return match.group(1).strip()

    # If not found, return the first sentence that contains the instruction keywords
    words = instruction.lower().split()
    lines = text.split('\n')

    for line in lines:
        line_lower = line.lower()
        if all(word in line_lower for word in words):
            return line.strip()

    return f"No data found for instruction: {instruction}"


def apply_formula(data, formula):
    """
    Apply a mathematical formula to the extracted data
    """
    # This is a simplified implementation - in a real system, you'd use a safe evaluation method
    # For now, we'll just do some basic string replacements
    try:
        # Replace field names in the formula with their values
        processed_formula = formula
        for key, value in data.items():
            processed_formula = processed_formula.replace(key, str(value))

        # Evaluate the formula (in a real system, use a safe eval)
        # For now, just return the formula as is
        return processed_formula
    except:
        return f"Formula error: {formula}"