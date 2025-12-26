"""
Sarah AI Processing Engine with Direct Value Extraction

This module implements an optimized document processing system for Sarah AI
that directly parses the structured output from OCR models.
"""

import json
import requests
import tempfile
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import base64
import asyncio
import aiohttp
from pathlib import Path
import logging

from pydantic import BaseModel, Field

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Pydantic models for data validation
class FieldDefinition(BaseModel):
    """Represents a single field in a blueprint schema"""
    name: str = Field(..., description="Name of the field")
    field_type: str = Field(..., description="Type of the field (text, currency, number, date)")
    instruction: str = Field(..., description="Instruction for extraction")
    required: bool = Field(default=True, description="Whether this field is required")

class BlueprintSchema(BaseModel):
    """Represents a complete extraction blueprint"""
    id: str
    user_id: str
    name: str
    fields: List[FieldDefinition]
    target_sheet_id: Optional[str] = None
    created_at: Optional[str] = None

class ProcessingResult(BaseModel):
    """Represents the result of document processing"""
    extracted_data: Dict[str, str]
    confidence: float
    raw_text: str
    raw_ocr: str
    processing_timestamp: str
    schema_used: List[Dict[str, str]]

class SarahAIProcessor:
    """
    Optimized AI Processing Engine for Sarah AI
    Directly parses structured output from OCR models
    """
    
    def __init__(self, ollama_endpoint: str = "http://localhost:11434"):
        self.ollama_endpoint = ollama_endpoint
        self.deepseek_model = "deepseek-ocr:3b"
        self.docling_model = "ibm/granite-docling:latest"
    
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
            logger.info(f"Calling Ollama with model: {model}")
            start_time = datetime.now()
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    logger.info(f"Ollama call completed in {duration:.2f}s")
                    return result.get("response", "")
                else:
                    logger.error(f"Ollama call failed with status {response.status}")
                    return f"Error: HTTP {response.status}"
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return f"Error: {str(e)}"
    
    async def process_document_with_schema(self, document_path: str, schema: List[Dict[str, str]]) -> ProcessingResult:
        """
        Process a document according to a user-defined schema
        """
        logger.info(f"Processing document: {document_path}")
        logger.info(f"Using schema: {schema}")
        
        async with aiohttp.ClientSession() as session:
            # Step 1: Extract text content from document using Docling
            logger.info("Step 1: Extracting text with Granite Docling...")
            text_content = await self._extract_text_with_docling(session, document_path)
            logger.info("Text extracted with Docling")
            
            # Step 2: Use DeepSeek OCR for high-accuracy extraction
            logger.info("Step 2: Extracting with DeepSeek OCR...")
            ocr_content = await self._extract_with_deepseek_ocr(session, document_path)
            logger.info("OCR performed with DeepSeek")
            
            # Step 3: Parse the structured output and extract values based on schema
            logger.info("Step 3: Parsing structured output and extracting values...")
            extracted_data = self._extract_values_from_structured_output(
                text_content,
                ocr_content,
                schema
            )
            
            # Step 4: Calculate confidence score
            confidence = self._calculate_confidence(extracted_data, schema)
            
            # Step 5: Format results
            result = ProcessingResult(
                extracted_data=extracted_data,
                confidence=confidence,
                raw_text=text_content,
                raw_ocr=ocr_content,
                processing_timestamp=datetime.utcnow().isoformat(),
                schema_used=schema
            )
            
            logger.info(f"Processing complete. Confidence: {confidence}")
            return result
    
    async def _extract_text_with_docling(self, session, document_path: str) -> str:
        """
        Extract text from document using Granite Docling via Ollama
        """
        logger.info("Using Granite Docling for document conversion...")
        
        # Create a prompt for Docling to extract document content
        prompt = "Convert this document to markdown format preserving structure, tables, and text content. Focus on accuracy and layout preservation. Respond only with the markdown content."
        
        # Call Ollama with the docling model
        result = await self._call_ollama(session, self.docling_model, prompt, document_path)
        return result
    
    async def _extract_with_deepseek_ocr(self, session, document_path: str) -> str:
        """
        Extract text from document using DeepSeek OCR via Ollama
        """
        logger.info("Using DeepSeek OCR for high-accuracy extraction...")
        
        # Create a prompt for DeepSeek OCR to extract document content
        prompt = "<image>\n<|grounding|>Convert the document to markdown. Pay special attention to tables, figures, and financial details. Preserve layout and structure for accurate analysis. Respond only with the extracted content."
        
        # Call Ollama with the deepseek model
        result = await self._call_ollama(session, self.deepseek_model, prompt, document_path)
        return result
    
    def _extract_values_from_structured_output(
        self,
        text_content: str,
        ocr_content: str,
        schema: List[Dict[str, str]]
    ) -> Dict[str, str]:
        """
        Directly extract values from the structured output of OCR models
        based on the provided schema
        """
        logger.info("Extracting values from structured output...")
        extracted = {}
        
        # Combine content for extraction
        combined_content = text_content + "\n\n" + ocr_content
        
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')
            
            logger.info(f"Extracting field: {field_name} (type: {field_type})")
            
            # Extract based on field type and keywords
            if field_type == 'currency':
                extracted[field_name] = self._extract_currency_value(combined_content, field_name, instruction)
            elif field_type == 'date':
                extracted[field_name] = self._extract_date_value(combined_content, field_name, instruction)
            elif field_type == 'number':
                extracted[field_name] = self._extract_number_value(combined_content, field_name, instruction)
            else:  # text
                extracted[field_name] = self._extract_text_value(combined_content, field_name, instruction)
            
            logger.info(f"Field {field_name} extracted: '{extracted[field_name]}'")
        
        return extracted
    
    def _extract_currency_value(self, content: str, field_name: str, instruction: str) -> str:
        """
        Extract currency values from the content
        """
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
        """
        Extract date values from the content
        """
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
        """
        Extract number values from the content
        """
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
        """
        Extract text values from the content
        """
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
    
    def _calculate_confidence(self, extracted_data: Dict[str, Any], schema: List[Dict[str, str]]) -> float:
        """
        Calculate confidence score based on extraction completeness
        """
        if not schema:
            return 0.0
        
        # Count how many fields were successfully extracted (not containing "No ... found")
        successful_extractions = sum(
            1 for value in extracted_data.values() 
            if value and not value.startswith("No ") and len(value) > 0
        )
        
        # Calculate confidence as percentage of successful extractions
        confidence = successful_extractions / len(schema)
        
        # Apply additional confidence factors based on data quality
        for field_name, value in extracted_data.items():
            if value and not value.startswith("No ") and len(value) > 0:
                # Add small confidence boost for successfully extracted fields
                confidence += 0.02  # Smaller boost to avoid exceeding 1.0
        
        # Ensure confidence is between 0 and 1
        return min(1.0, max(0.0, confidence))


async def test_with_real_models():
    """
    Test the processing engine with actual Ollama models
    """
    logger.info("=== Sarah AI Optimized Processing Engine with Real Models ===\n")
    
    # Create a processor instance
    processor = SarahAIProcessor()
    
    # Use the test image we created
    document_path = 'test_invoice.png'
    
    if not os.path.exists(document_path):
        logger.error(f"Test document not found: {document_path}")
        return
    
    try:
        # Define a schema for extraction
        schema = [
            {"name": "Vendor", "type": "text", "instruction": "vendor or supplier name"},
            {"name": "Invoice Date", "type": "date", "instruction": "invoice date in YYYY-MM-DD format"},
            {"name": "Total", "type": "currency", "instruction": "total amount including tax"}
        ]
        
        logger.info("Starting document processing...")
        start_time = datetime.now()
        
        # Process the document
        result = await processor.process_document_with_schema(document_path, schema)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"\nProcessing completed in {duration:.2f} seconds")
        logger.info(f"Extracted Data: {result.extracted_data}")
        logger.info(f"Confidence: {result.confidence:.2f}")
        logger.info(f"Raw Text (first 100 chars): {result.raw_text[:100]}...")
        logger.info(f"Raw OCR (first 100 chars): {result.raw_ocr[:100]}...")
        
        # Check if review is needed based on confidence
        requires_review = result.confidence < 0.8
        logger.info(f"\nRequires Review: {requires_review}")
        
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()


def check_ollama_connection():
    """
    Check if Ollama is running and models are available
    """
    logger.info("=== Checking Ollama Connection ===")
    
    try:
        response = requests.get("http://localhost:11434/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        
        logger.info("Available models:")
        for model in models:
            logger.info(f"  - {model['name']}")
        
        # Check for required models
        required_models = ["deepseek-ocr:3b", "ibm/granite-docling:latest"]
        available_models = [model['name'] for model in models]
        
        logger.info(f"\nRequired models check:")
        for req_model in required_models:
            status = "✓ Available" if req_model in available_models else "✗ Missing"
            logger.info(f"  {req_model}: {status}")
        
        return len([m for m in required_models if m in available_models]) == len(required_models)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error connecting to Ollama: {e}")
        return False


if __name__ == "__main__":
    # Check if Ollama is available
    ollama_available = check_ollama_connection()
    
    if ollama_available:
        logger.info("\nOllama is available with required models. Starting test...")
        asyncio.run(test_with_real_models())
    else:
        logger.error("\nOllama is not available or required models are missing.")
        logger.error("Please ensure Ollama is running and required models are pulled:")
        logger.error("  ollama pull deepseek-ocr:3b")
        logger.error("  ollama pull ibm/granite-docling:latest")