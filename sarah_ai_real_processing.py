"""
Sarah AI Processing Engine with Real DeepSeek OCR and Granite Docling Integration

This module implements the AI processing engine for Sarah AI using
real DeepSeek OCR and Granite Docling models via Ollama.
"""

import json
import requests
import tempfile
import os
from typing import Dict, Any, List
from datetime import datetime
import re
import base64
from pathlib import Path

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
    
    def _call_ollama(self, model: str, prompt: str, image_path: str = None) -> str:
        """
        Call Ollama API with the specified model
        """
        url = f"{self.ollama_endpoint}/api/generate"
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        # Add image if provided
        if image_path:
            encoded_image = self._encode_image(image_path)
            payload["images"] = [encoded_image]
        
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama: {e}")
            return f"Error: {str(e)}"
    
    def process_document_with_schema(self, document_path: str, schema: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process a document according to a user-defined schema using real models
        """
        print(f"Processing document: {document_path}")
        print(f"Using schema: {schema}")
        
        # Step 1: Extract text content from document using Docling
        text_content = self._extract_text_with_docling(document_path)
        print("Text extracted with Docling")
        
        # Step 2: Use DeepSeek OCR for high-accuracy extraction
        ocr_content = self._extract_with_deepseek_ocr(document_path)
        print("OCR performed with DeepSeek")
        
        # Step 3: Combine information and extract according to schema
        extracted_data = self._extract_according_to_schema(
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
        
        print(f"Processing complete. Confidence: {confidence}")
        return result
    
    def _extract_text_with_docling(self, document_path: str) -> str:
        """
        Extract text from document using Granite Docling via Ollama
        """
        print("Using Granite Docling for document conversion...")
        
        # Create a prompt for Docling to extract document content
        prompt = "Convert this document to markdown format preserving structure, tables, and text content. Focus on accuracy and layout preservation."
        
        # Call Ollama with the docling model
        result = self._call_ollama(self.docling_model, prompt, document_path)
        return result
    
    def _extract_with_deepseek_ocr(self, document_path: str) -> str:
        """
        Extract text from document using DeepSeek OCR via Ollama
        """
        print("Using DeepSeek OCR for high-accuracy extraction...")
        
        # Create a prompt for DeepSeek OCR to extract document content
        prompt = "<image>\n<|grounding|>Convert the document to markdown. Pay special attention to tables, figures, and financial details. Preserve layout and structure for accurate analysis."
        
        # Call Ollama with the deepseek model
        result = self._call_ollama(self.deepseek_model, prompt, document_path)
        return result
    
    def _extract_according_to_schema(
        self,
        text_content: str,
        ocr_content: str,
        schema: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Extract data according to the provided schema using AI
        """
        print("Extracting data according to schema using AI...")
        extracted = {}

        # Combine content for extraction
        combined_content = text_content + "\n\n" + ocr_content

        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')

            # Create a specific prompt for this field
            extraction_prompt = f"""
            From the following document content, extract only the value for '{field_name}'.
            The field type is '{field_type}' and the instruction is: {instruction}

            Document content:
            {combined_content}

            Respond with only the extracted value, nothing else.
            If you cannot find the value, respond with "NOT_FOUND".
            """

            # Use DeepSeek model to extract the specific field
            result = self._call_ollama(self.deepseek_model, extraction_prompt)

            # Clean up the result
            result_clean = result.strip()

            if result_clean == "NOT_FOUND" or "not found" in result_clean.lower():
                extracted[field_name] = f"No {field_type} found for: {instruction}"
            else:
                # Clean the result further to remove any additional text
                extracted[field_name] = self._clean_extraction_result(result_clean, field_type)

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
            import re
            currency_match = re.search(r'\$?[\d,]+\.?\d{0,2}', cleaned)
            if currency_match:
                return currency_match.group(0)
        elif field_type == 'date':
            # Extract date pattern
            import re
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
            import re
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


def test_with_real_models():
    """
    Test the processing engine with actual Ollama models
    """
    print("=== Sarah AI Processing Engine with Real Models ===\n")
    
    # Create a processor instance
    processor = SarahAIProcessor()
    
    # Create a mock document (in reality, this would be a PDF file)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
        temp_file.write("""
        INVOICE
        Invoice #: 12345
        Date: 12/20/2025
        Vendor: Home Depot
        Items:
        - Lumber: $800.00
        - Nails: $15.99
        Tax: $65.28
        Total: $881.27
        """)
        document_path = temp_file.name
    
    try:
        # Define a schema for extraction
        schema = [
            {"name": "Vendor", "type": "text", "instruction": "vendor or supplier name"},
            {"name": "Invoice Number", "type": "text", "instruction": "invoice reference number"},
            {"name": "Invoice Date", "type": "date", "instruction": "invoice date in YYYY-MM-DD format"},
            {"name": "Total", "type": "currency", "instruction": "total amount including tax"},
            {"name": "Tax", "type": "currency", "instruction": "tax amount"}
        ]
        
        # Process the document
        result = processor.process_document_with_schema(document_path, schema)
        
        print(f"\nProcessing Result:")
        print(f"Extracted Data: {result['extracted_data']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Raw Text: {result['raw_text'][:100]}...")
        print(f"Raw OCR: {result['raw_ocr'][:100]}...")
        
        # Check if review is needed based on confidence
        requires_review = result['confidence'] < 0.8
        print(f"\nRequires Review: {requires_review}")
        
    except Exception as e:
        print(f"Error during processing: {e}")
    finally:
        # Clean up the temporary file
        os.unlink(document_path)
    
    print("\n=== Test Complete ===")


def check_ollama_connection():
    """
    Check if Ollama is running and models are available
    """
    print("=== Checking Ollama Connection ===")
    
    try:
        response = requests.get("http://localhost:11434/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        
        print("Available models:")
        for model in models:
            print(f"  - {model['name']}")
        
        # Check for required models
        required_models = ["deepseek-ocr:3b", "ibm/granite-docling:latest"]
        available_models = [model['name'] for model in models]
        
        print(f"\nRequired models check:")
        for req_model in required_models:
            status = "✓ Available" if req_model in available_models else "✗ Missing"
            print(f"  {req_model}: {status}")
        
        return len([m for m in required_models if m in available_models]) == len(required_models)
        
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        return False


if __name__ == "__main__":
    # Check if Ollama is available
    ollama_available = check_ollama_connection()
    
    if ollama_available:
        print("\nOllama is available with required models. Starting test...")
        test_with_real_models()
    else:
        print("\nOllama is not available or required models are missing.")
        print("Please ensure Ollama is running and required models are pulled:")
        print("  ollama pull deepseek-ocr:3b")
        print("  ollama pull ibm/granite-docling:latest")