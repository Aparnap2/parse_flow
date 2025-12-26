"""
Sarah AI Processing Engine with Real DeepSeek OCR and Granite Docling Integration
Optimized version with better prompts and efficiency
"""

import json
import requests
import tempfile
import os
from typing import Dict, Any, List
from datetime import datetime
import re
import base64
import asyncio
import aiohttp
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SarahAIProcessor:
    """
    AI Processing Engine for Sarah AI
    Uses DeepSeek OCR and Granite Docling for document processing
    with schema-based extraction
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
                "num_predict": 512,  # Limit response length
                "stop": ["\n\n", "If you cannot find the value", "respond with"]  # Stop tokens
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
                    response_text = result.get("response", "")
                    
                    # Clean up the response to remove repetitive text
                    if "If you cannot find the value, respond with" in response_text:
                        # Take only the first part before the repetitive text
                        response_text = response_text.split("If you cannot find the value, respond with")[0].strip()
                    
                    return response_text
                else:
                    logger.error(f"Ollama call failed with status {response.status}")
                    return f"Error: HTTP {response.status}"
        except Exception as e:
            logger.error(f"Error calling Ollama: {e}")
            return f"Error: {str(e)}"
    
    async def process_document_with_schema(self, document_path: str, schema: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process a document according to a user-defined schema using real models
        """
        logger.info(f"Processing document: {document_path}")
        logger.info(f"Using schema: {schema}")
        
        # Create an aiohttp session for async requests
        async with aiohttp.ClientSession() as session:
            # Step 1: Extract text content from document using Docling
            logger.info("Step 1: Extracting text with Granite Docling...")
            text_content = await self._extract_text_with_docling(session, document_path)
            logger.info("Text extracted with Docling")
            
            # Step 2: Use DeepSeek OCR for high-accuracy extraction
            logger.info("Step 2: Extracting with DeepSeek OCR...")
            ocr_content = await self._extract_with_deepseek_ocr(session, document_path)
            logger.info("OCR performed with DeepSeek")
            
            # Step 3: Combine information and extract according to schema
            logger.info("Step 3: Extracting data according to schema...")
            extracted_data = await self._extract_according_to_schema(
                session,
                text_content, 
                ocr_content, 
                schema
            )
            
            # Step 4: Calculate confidence score
            confidence = self._calculate_confidence(extracted_data, schema)
            
            # Step 5: Format results
            result = {
                "extracted_data": extracted_data,
                "confidence": confidence,
                "raw_text": text_content,
                "raw_ocr": ocr_content,
                "processing_timestamp": datetime.utcnow().isoformat(),
                "schema_used": schema
            }
            
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
    
    async def _extract_according_to_schema(
        self, 
        session,
        text_content: str, 
        ocr_content: str, 
        schema: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Extract data according to the provided schema using AI
        """
        logger.info("Extracting data according to schema using AI...")
        extracted = {}
        
        # Combine content for extraction
        combined_content = text_content + "\n\n" + ocr_content
        
        # Process each field in the schema
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')
            
            logger.info(f"Extracting field: {field_name} (type: {field_type})")
            
            # Create a specific prompt for this field with better instructions
            extraction_prompt = f"""
            From the following document content, extract only the value for '{field_name}'.
            The field type is '{field_type}' and the instruction is: {instruction}
            
            Document content:
            {combined_content}
            
            Respond ONLY with the extracted value, nothing else.
            If you cannot find the value, respond with "NOT_FOUND".
            Do not explain your reasoning or repeat the instructions.
            """
            
            # Use DeepSeek model to extract the specific field
            result = await self._call_ollama(session, self.deepseek_model, extraction_prompt)
            
            # Clean up the result
            result_clean = result.strip()
            
            if result_clean == "NOT_FOUND" or "not found" in result_clean.lower():
                extracted[field_name] = f"No {field_type} found for: {instruction}"
                logger.info(f"Field {field_name} not found")
            else:
                # Clean the result further to remove any additional text
                cleaned_result = self._clean_extraction_result(result_clean, field_type)
                extracted[field_name] = cleaned_result
                logger.info(f"Field {field_name} extracted: {cleaned_result}")
        
        return extracted
    
    def _clean_extraction_result(self, result: str, field_type: str) -> str:
        """
        Clean the extraction result based on field type
        """
        # Remove any leading/trailing whitespace and quotes
        cleaned = result.strip().strip('"').strip("'")
        
        # Apply field-type-specific cleaning
        if field_type == 'currency':
            # Extract currency pattern
            currency_match = re.search(r'\$?[\d,]+\.?\d{0,2}', cleaned)
            if currency_match:
                return currency_match.group(0)
        elif field_type == 'date':
            # Extract date pattern
            date_patterns = [
                r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # MM/DD/YYYY
                r'\b\d{4}-\d{2}-\d{2}\b',        # YYYY-MM-DD
                r'\b\d{1,2}-\d{1,2}-\d{2,4}\b'  # MM-DD-YYYY
            ]
            for pattern in date_patterns:
                match = re.search(pattern, cleaned)
                if match:
                    return match.group(0)
        elif field_type == 'number':
            # Extract number pattern
            number_match = re.search(r'\b\d+\.?\d*\b', cleaned)
            if number_match:
                return number_match.group(0)
        
        return cleaned
    
    def _calculate_confidence(self, extracted_data: Dict[str, Any], schema: List[Dict[str, str]]) -> float:
        """
        Calculate confidence score based on extraction completeness
        """
        if not schema:
            return 0.0
        
        # Count how many fields were successfully extracted
        successful_extractions = sum(
            1 for value in extracted_data.values() 
            if value and not value.startswith("No ") and "NOT_FOUND" not in value
        )
        
        # Calculate confidence as percentage of successful extractions
        confidence = successful_extractions / len(schema)
        
        # Apply additional confidence factors based on data quality
        for field_name, value in extracted_data.items():
            if value and not value.startswith("No ") and "NOT_FOUND" not in value:
                # Add small confidence boost for successfully extracted fields
                confidence += 0.05
        
        # Ensure confidence is between 0 and 1
        return min(1.0, max(0.0, confidence))


async def test_with_real_models():
    """
    Test the processing engine with actual Ollama models
    """
    logger.info("=== Sarah AI Processing Engine with Real Models ===\n")
    
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
        logger.info(f"Extracted Data: {result['extracted_data']}")
        logger.info(f"Confidence: {result['confidence']:.2f}")
        logger.info(f"Raw Text (first 100 chars): {result['raw_text'][:100]}...")
        logger.info(f"Raw OCR (first 100 chars): {result['raw_ocr'][:100]}...")
        
        # Check if review is needed based on confidence
        requires_review = result['confidence'] < 0.8
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