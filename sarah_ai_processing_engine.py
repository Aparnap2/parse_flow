"""
Sarah AI Processing Engine with DeepSeek OCR and Granite Docling

This module implements the AI processing engine for Sarah AI using
DeepSeek OCR for high-accuracy OCR and Granite Docling for document
conversion, with schema-based extraction.
"""

import json
import requests
import tempfile
import os
from typing import Dict, Any, List
from datetime import datetime
import re

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
    
    def process_document_with_schema(self, document_path: str, schema: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Process a document according to a user-defined schema
        """
        print(f"Processing document: {document_path}")
        print(f"Using schema: {schema}")
        
        # Step 1: Extract text content from document using Docling
        text_content = self._extract_text_with_docling(document_path)
        print("Text extracted with Docling")
        
        # Step 2: Use DeepSeek OCR for high-accuracy extraction if needed
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
        Extract text from document using Granite Docling
        """
        # In a real implementation, we would use the granite-docling model
        # For simulation, we'll return a mock response
        print("Using Granite Docling for document conversion...")
        
        # Mock implementation - in real usage, you would call the docling API
        with open(document_path, 'r') as f:
            content = f.read()
        
        # Return mock text content
        return f"Mock text content from Docling for {document_path}"
    
    def _extract_with_deepseek_ocr(self, document_path: str) -> str:
        """
        Extract text from document using DeepSeek OCR via Ollama
        """
        print("Using DeepSeek OCR for high-accuracy extraction...")
        
        # In a real implementation, we would call the Ollama API
        # For simulation, we'll return a mock response
        return f"Mock OCR content from DeepSeek for {document_path}"
    
    def _extract_according_to_schema(
        self, 
        text_content: str, 
        ocr_content: str, 
        schema: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Extract data according to the provided schema
        """
        print("Extracting data according to schema...")
        extracted = {}
        
        # Combine content for extraction
        combined_content = text_content + " " + ocr_content
        
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')
            
            # Extract based on field type and instruction
            if field_type == 'currency':
                extracted[field_name] = self._extract_currency(combined_content, instruction)
            elif field_type == 'number':
                extracted[field_name] = self._extract_number(combined_content, instruction)
            elif field_type == 'date':
                extracted[field_name] = self._extract_date(combined_content, instruction)
            else:  # text
                extracted[field_name] = self._extract_text(combined_content, instruction)
        
        return extracted
    
    def _extract_currency(self, text: str, instruction: str) -> str:
        """
        Extract currency values from text
        """
        # Look for currency patterns: $XXX,XXX.XX or XXX,XXX.XX
        currency_pattern = r'\$?[\d,]+\.?\d{0,2}'
        matches = re.findall(currency_pattern, text)
        return matches[0] if matches else f"No currency found for: {instruction}"
    
    def _extract_number(self, text: str, instruction: str) -> str:
        """
        Extract numeric values from text
        """
        number_pattern = r'\b\d+\.?\d*\b'
        matches = re.findall(number_pattern, text)
        return matches[0] if matches else f"No number found for: {instruction}"
    
    def _extract_date(self, text: str, instruction: str) -> str:
        """
        Extract date values from text
        """
        date_patterns = [
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # MM/DD/YYYY
            r'\b\d{4}-\d{2}-\d{2}\b',        # YYYY-MM-DD
            r'\b\d{1,2}-\d{1,2}-\d{2,4}\b'  # MM-DD-YYYY
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        
        return f"No date found for: {instruction}"
    
    def _extract_text(self, text: str, instruction: str) -> str:
        """
        Extract text based on the instruction
        """
        # Look for the instruction keywords in the text
        keywords = instruction.lower().split()
        lines = text.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            if all(keyword in line_lower for keyword in keywords):
                # Return the part of the line after the instruction keywords
                return line.strip()
        
        # If not found directly, try to find the instruction text followed by the value
        instruction_pattern = re.compile(re.escape(instruction) + r'\s*[:\-\—]\s*([^\n\r.]+)', re.IGNORECASE)
        match = instruction_pattern.search(text)
        if match:
            return match.group(1).strip()
        
        return f"No text found for: {instruction}"
    
    def _calculate_confidence(self, extracted_data: Dict[str, Any], schema: List[Dict[str, str]]) -> float:
        """
        Calculate confidence score based on extraction completeness
        """
        if not schema:
            return 0.0
        
        # Count how many fields were successfully extracted
        successful_extractions = sum(
            1 for value in extracted_data.values() 
            if value and not value.startswith("No ")
        )
        
        # Calculate confidence as percentage of successful extractions
        confidence = successful_extractions / len(schema)
        
        # Apply additional confidence factors based on data quality
        for field_name, value in extracted_data.items():
            if value and not value.startswith("No "):
                # Add small confidence boost for successfully extracted fields
                confidence += 0.05
        
        # Ensure confidence is between 0 and 1
        return min(1.0, max(0.0, confidence))


def simulate_processing():
    """
    Simulate the document processing workflow
    """
    print("=== Sarah AI Processing Engine Simulation ===\n")
    
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
            {"name": "Vendor", "type": "text", "instruction": "vendor name"},
            {"name": "Invoice Number", "type": "text", "instruction": "invoice number"},
            {"name": "Invoice Date", "type": "date", "instruction": "invoice date"},
            {"name": "Total", "type": "currency", "instruction": "total amount"},
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
        
    finally:
        # Clean up the temporary file
        os.unlink(document_path)
    
    print("\n=== Simulation Complete ===")


def demonstrate_model_capabilities():
    """
    Demonstrate the capabilities of the different models
    """
    print("\n=== Model Capabilities ===\n")
    
    print("DeepSeek OCR:")
    print("- High-accuracy OCR for document processing")
    print("- Specialized for layout-aware extraction")
    print("- Handles complex document structures")
    print("- Supports multiple languages")
    
    print("\nGranite Docling:")
    print("- Document conversion and structure analysis")
    print("- Extracts tables, figures, and text")
    print("- Preserves document layout")
    print("- Converts to multiple output formats")
    
    print("\nCombined Approach:")
    print("- Use Docling for structure and layout")
    print("- Use DeepSeek OCR for high-accuracy text extraction")
    print("- Apply user-defined schema for custom extraction")
    print("- Calculate confidence scores for quality assurance")


if __name__ == "__main__":
    simulate_processing()
    demonstrate_model_capabilities()