"""
Apify Actor for Sarah AI - Invoice Processing

This actor processes invoices using DeepSeek OCR and Granite Docling models
with schema-based extraction and validation capabilities.
Uses Ollama models for local processing instead of OpenAI.
"""

import os
from typing import TypedDict, List, Dict, Any
from apify import Actor
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
import tempfile
import requests
import base64
import asyncio
import aiohttp
import re
from datetime import datetime
from openai import OpenAI  # For Ollama compatibility
import json

# Initialize client using environment variables (can be set to Ollama or OpenAI)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")  # Default to Ollama
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")  # Default to Ollama dummy key
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "ministral-3:3b")  # Default to local model

client = OpenAI(
    base_url=OPENAI_BASE_URL,
    api_key=OPENAI_API_KEY
)

# Document processing models (using ONNX for efficiency)
DOCLING_MODEL = os.getenv("DOCLING_MODEL", "ibm/granite-docling:latest")

# 1. Define the Strict Output Schema (Pydantic)
class InvoiceLineItem(BaseModel):
    description: str
    amount: float
    category: str = Field(description="One of: Meals, Travel, Office, Software")

class InvoiceData(BaseModel):
    vendor: str
    total_amount: float
    tax_amount: float
    line_items: List[InvoiceLineItem]
    validation_status: str = Field(description="'valid' or 'needs_review'")
    extracted_fields: Dict[str, Any] = Field(description="Additional extracted fields based on user schema")

# 2. Define the Graph State
class AgentState(TypedDict):
    pdf_url: str
    user_schema: Dict[str, Any]
    extracted_text: str
    structured_data: dict
    validation_status: str
    attempts: int
    confidence: float

# 3. Define the Nodes (The "Intern Skills")
class OCRProcessor:
    def __init__(self, ollama_endpoint: str = "http://localhost:11434"):
        self.ollama_endpoint = ollama_endpoint
        # Using only Docling for document processing (more efficient than OCR)
        self.docling_model = os.getenv("DOCLING_MODEL", "ibm/granite-docling:latest")
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64 for API requests"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    async def _call_ollama(self, session, model: str, prompt: str, image_path: str = None) -> str:
        """
        Async call to Ollama API with the specified model
        """
        url = f"{self.ollama_endpoint}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Lower temperature for more consistent results
                "num_predict": 1024,  # Limit response length
            }
        }
        
        # Add image if provided
        if image_path:
            encoded_image = self._encode_image(image_path)
            payload["images"] = [encoded_image]
        
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "")
                else:
                    print(f"Ollama call failed with status {response.status}")
                    return f"Error: HTTP {response.status}"
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            return f"Error: {str(e)}"
    
    async def download_pdf(self, pdf_url: str) -> str:
        """Download PDF from URL and save to temporary file"""
        async with aiohttp.ClientSession() as session:
            async with session.get(pdf_url) as response:
                if response.status == 200:
                    content = await response.read()
                    # Create a temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                        tmp_file.write(content)
                        return tmp_file.name
                else:
                    raise Exception(f"Failed to download PDF: {response.status}")
    
    async def extract_text_with_docling(self, session, pdf_path: str) -> str:
        """Extract text from PDF using Granite Docling"""
        prompt = "Convert this document to markdown format preserving structure, tables, and text content. Focus on accuracy and layout preservation. Respond only with the markdown content."
        result = await self._call_ollama(session, self.docling_model, prompt, pdf_path)
        return result
    
    def extract_according_to_schema(self, text_content: str, ocr_content: str, schema: List[Dict[str, str]]) -> Dict[str, Any]:
        """Extract data according to the provided schema"""
        extracted = {}
        
        # Combine content for extraction
        combined_content = text_content + "\n\n" + ocr_content
        
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')
            
            # Extract based on field type and keywords
            if field_type == 'currency':
                extracted[field_name] = self._extract_currency_value(combined_content, field_name, instruction)
            elif field_type == 'date':
                extracted[field_name] = self._extract_date_value(combined_content, field_name, instruction)
            elif field_type == 'number':
                extracted[field_name] = self._extract_number_value(combined_content, field_name, instruction)
            else:  # text
                extracted[field_name] = self._extract_text_value(combined_content, field_name, instruction)
        
        return extracted
    
    def _extract_currency_value(self, content: str, field_name: str, instruction: str) -> str:
        """Extract currency values from the content"""
        # Look for currency keywords near the field name
        keywords = [field_name.lower(), instruction.lower(), 'total', 'amount', 'cost', 'price']
        
        # Look for currency patterns
        currency_pattern = r'\$?[\d,]+\.?\d{2}'
        
        # Find relevant lines in the content
        lines = content.split('\n')
        for line in lines:
            line_lower = line.lower()
            
            # Check if any keyword is in the line
            if any(keyword in line_lower for keyword in keywords):
                # Extract currency from this line
                matches = re.findall(currency_pattern, line)
                if matches:
                    return matches[0].replace(',', '')  # Remove commas
        
        # If not found with keywords, search globally for currency
        global_matches = re.findall(currency_pattern, content)
        if global_matches:
            return global_matches[0].replace(',', '')
        
        return f"No currency found for: {field_name}"
    
    def _extract_date_value(self, content: str, field_name: str, instruction: str) -> str:
        """Extract date values from the content"""
        # Look for date keywords near the field name
        keywords = [field_name.lower(), instruction.lower(), 'date', 'invoice date', 'bill date', 'issued']
        
        # Look for date patterns
        date_patterns = [
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # MM/DD/YYYY
            r'\b\d{4}-\d{2}-\d{2}\b',        # YYYY-MM-DD
            r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',  # MM-DD-YYYY
            r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b', # MM.DD.YYYY
        ]
        
        # Find relevant lines in the content
        lines = content.split('\n')
        for line in lines:
            line_lower = line.lower()
            
            # Check if any keyword is in the line
            if any(keyword in line_lower for keyword in keywords):
                # Extract date from this line using patterns
                for pattern in date_patterns:
                    match = re.search(pattern, line)
                    if match:
                        return match.group(0)
        
        # If not found with keywords, search globally for dates
        for pattern in date_patterns:
            matches = re.findall(pattern, content)
            if matches:
                return matches[0]
        
        return f"No date found for: {field_name}"
    
    def _extract_number_value(self, content: str, field_name: str, instruction: str) -> str:
        """Extract number values from the content"""
        # Look for number keywords near the field name
        keywords = [field_name.lower(), instruction.lower(), 'number', 'count', 'qty', 'quantity']
        
        # Look for number patterns
        number_pattern = r'\b\d+\.?\d*\b'
        
        # Find relevant lines in the content
        lines = content.split('\n')
        for line in lines:
            line_lower = line.lower()
            
            # Check if any keyword is in the line
            if any(keyword in line_lower for keyword in keywords):
                # Extract number from this line
                matches = re.findall(number_pattern, line)
                if matches:
                    return matches[0]
        
        # If not found with keywords, search globally for numbers
        global_matches = re.findall(number_pattern, content)
        if global_matches:
            return global_matches[0]
        
        return f"No number found for: {field_name}"
    
    def _extract_text_value(self, content: str, field_name: str, instruction: str) -> str:
        """Extract text values from the content"""
        # Look for text keywords near the field name
        keywords = [field_name.lower(), instruction.lower()]
        
        # Find relevant lines in the content
        lines = content.split('\n')
        for line in lines:
            line_lower = line.lower()
            
            # Check if any keyword is in the line
            if any(keyword in line_lower for keyword in keywords):
                # Extract the text part after the keyword
                for keyword in keywords:
                    if keyword in line_lower:
                        # Find the position of the keyword and extract text after it
                        pos = line_lower.find(keyword)
                        if pos != -1:
                            # Extract text after the keyword
                            after_keyword = line[pos + len(keyword):].strip()
                            # Remove common separators
                            after_keyword = re.sub(r'^[:\-—]\s*', '', after_keyword)
                            return after_keyword.strip()
        
        # If not found with keywords, search for the instruction in the content
        instruction_lower = instruction.lower()
        for line in lines:
            if instruction_lower in line.lower():
                # Extract text after the instruction
                pos = line.lower().find(instruction_lower)
                if pos != -1:
                    after_instruction = line[pos + len(instruction_lower):].strip()
                    after_instruction = re.sub(r'^[:\-—]\s*', '', after_instruction)
                    return after_instruction.strip()
        
        # Last resort: return the first occurrence of any text related to the field
        for line in lines:
            if field_name.lower() in line.lower():
                return line.strip()
        
        return f"No text found for: {field_name}"

def parse_pdf_node(state: AgentState) -> Dict[str, Any]:
    """Downloads and processes the PDF using Docling"""
    import asyncio

    async def process_pdf():
        processor = OCRProcessor()

        # Download the PDF
        pdf_path = await processor.download_pdf(state['pdf_url'])

        try:
            async with aiohttp.ClientSession() as session:
                # Extract text with Docling (efficient ONNX-based processing)
                text_content = await processor.extract_text_with_docling(session, pdf_path)

                # Extract according to user schema using only Docling output
                user_schema = state.get('user_schema', [])
                extracted_fields = processor.extract_according_to_schema(
                    text_content,
                    text_content,  # Using same content for both params since we only have one source now
                    user_schema
                )

                # Calculate a simple confidence based on how many fields were found
                found_fields = sum(1 for v in extracted_fields.values() if not v.startswith("No "))
                total_fields = len(extracted_fields)
                confidence = found_fields / total_fields if total_fields > 0 else 0.0

                return {
                    "extracted_text": text_content,  # Just the Docling output
                    "structured_data": {
                        "extracted_fields": extracted_fields,
                        "raw_text": text_content
                    },
                    "confidence": confidence
                }
        finally:
            # Clean up the temporary file
            import os
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

    # Run the async function
    import nest_asyncio
    nest_asyncio.apply()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(process_pdf())
    loop.close()

    return result

def extract_data_node(state: AgentState) -> Dict[str, Any]:
    """Uses LLM to map Text -> Pydantic Schema"""
    # Extract key fields from the structured data
    structured_data = state['structured_data']
    extracted_fields = structured_data.get('extracted_fields', {})
    
    # Try to map to InvoiceData schema
    vendor = extracted_fields.get('Vendor', 'Unknown Vendor')
    total_str = extracted_fields.get('Total', '0.0')
    tax_str = extracted_fields.get('Tax', '0.0')
    
    # Convert to numbers, handling potential errors
    try:
        total_amount = float(re.sub(r'[^\d.-]', '', str(total_str)))
    except (ValueError, TypeError):
        total_amount = 0.0
    
    try:
        tax_amount = float(re.sub(r'[^\d.-]', '', str(tax_str)))
    except (ValueError, TypeError):
        tax_amount = 0.0
    
    # Create line items from other extracted fields
    line_items = []
    for field_name, value in extracted_fields.items():
        if field_name not in ['Vendor', 'Total', 'Tax']:
            try:
                amount = float(re.sub(r'[^\d.-]', '', str(value)))
                line_items.append({
                    "description": field_name,
                    "amount": amount,
                    "category": "Miscellaneous"
                })
            except (ValueError, TypeError):
                # If it's not a number, just add it as a description
                line_items.append({
                    "description": f"{field_name}: {value}",
                    "amount": 0.0,
                    "category": "Miscellaneous"
                })
    
    # Create the InvoiceData object
    invoice_data = InvoiceData(
        vendor=vendor,
        total_amount=total_amount,
        tax_amount=tax_amount,
        line_items=line_items,
        validation_status="valid",  # Default to valid
        extracted_fields=extracted_fields
    )
    
    return {"structured_data": invoice_data.model_dump()}

def validate_math_node(state: AgentState) -> Dict[str, Any]:
    """Checks Total == Subtotal + Tax"""
    data = state['structured_data']
    extracted_fields = data.get('extracted_fields', {})
    
    # Get the total amount from extracted fields
    total_str = extracted_fields.get('Total', '0.0')
    tax_str = extracted_fields.get('Tax', '0.0')
    
    try:
        total_amount = float(re.sub(r'[^\d.-]', '', str(total_str)))
        tax_amount = float(re.sub(r'[^\d.-]', '', str(tax_str)))
    except (ValueError, TypeError):
        return {"validation_status": "needs_review", "attempts": state.get('attempts', 0) + 1}
    
    # Calculate expected total from line items
    line_items = data.get('line_items', [])
    subtotal = sum(item['amount'] for item in line_items if item['description'] != 'Tax')
    calculated_total = subtotal + tax_amount
    
    # Self-Correction Logic
    if abs(total_amount - calculated_total) > 0.01:
        # If math is wrong, mark for review
        return {"validation_status": "needs_review", "attempts": state.get('attempts', 0) + 1}

    return {"validation_status": "valid"}

# 4. Build the Graph
def create_workflow():
    workflow = StateGraph(AgentState)
    workflow.add_node("parse", parse_pdf_node)
    workflow.add_node("extract", extract_data_node)
    workflow.add_node("validate", validate_math_node)

    workflow.set_entry_point("parse")
    workflow.add_edge("parse", "extract")
    workflow.add_edge("extract", "validate")
    workflow.add_edge("validate", END) # In real world, add conditional edge back to 'extract' if invalid

    return workflow.compile()

app = create_workflow()

# 5. The Apify Entry Point
async def main():
    async with Actor:
        # Get Input from Apify
        actor_input = await Actor.get_input() or {}
        pdf_url = actor_input.get('pdf_url')
        user_schema = actor_input.get('schema', [])

        if not pdf_url:
            await Actor.fail("Missing pdf_url")
            return

        # Run the LangGraph Agent
        inputs = {
            "pdf_url": pdf_url, 
            "attempts": 0,
            "user_schema": user_schema
        }
        result_state = await app.ainvoke(inputs)

        # Add confidence to the result
        result_data = result_state['structured_data']
        result_data['confidence'] = result_state.get('confidence', 0.0)
        result_data['validation_status'] = result_state.get('validation_status', 'unknown')

        # Push Result
        await Actor.push_data(result_data)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())