"""
Sarah AI Processing Engine Simulation

This file simulates the Sarah AI processing engine without modifying the existing ParseFlow engine
"""

import json
import re
from typing import Dict, Any, List

class SarahAIProcessor:
    """
    A simulator for the Sarah AI processing engine that uses user-defined schemas
    """
    
    def __init__(self):
        self.processing_history = []
    
    def process_document_with_schema(self, document_text: str, schema_json: str) -> Dict[str, Any]:
        """
        Process a document according to a user-defined schema
        """
        try:
            schema = json.loads(schema_json)
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Invalid schema JSON"
            }
        
        # Apply the schema to extract data from the document
        extracted_data = self._extract_with_schema(document_text, schema)
        
        # Calculate confidence based on how many fields were successfully extracted
        total_fields = len(schema)
        extracted_fields = len([k for k, v in extracted_data.items() if v])
        confidence = extracted_fields / total_fields if total_fields > 0 else 0
        
        result = {
            "success": True,
            "data": extracted_data,
            "confidence": confidence,
            "schema_used": schema
        }
        
        self.processing_history.append(result)
        return result
    
    def _extract_with_schema(self, text: str, schema: List[Dict[str, str]]) -> Dict[str, str]:
        """
        Extract data from text according to the provided schema
        """
        extracted = {}
        
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')
            
            # Extract based on field type and instruction
            if field_type == 'currency':
                extracted[field_name] = self._extract_currency(text, instruction)
            elif field_type == 'number':
                extracted[field_name] = self._extract_number(text, instruction)
            elif field_type == 'date':
                extracted[field_name] = self._extract_date(text, instruction)
            else:  # text
                extracted[field_name] = self._extract_text(text, instruction)
        
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


def test_sarah_ai_processor():
    """
    Test the Sarah AI processor with sample data
    """
    print("=== Sarah AI Processing Engine Simulation ===\n")
    
    processor = SarahAIProcessor()
    
    # Sample document text
    sample_document = """
    INVOICE
    Invoice #: 12345
    Date: 12/20/2025
    Vendor: Home Depot
    Items:
    - Lumber: $800.00
    - Nails: $15.99
    Tax: $65.28
    Total: $881.27
    """
    
    # Sample schema
    schema = [
        {"name": "Vendor", "type": "text", "instruction": "vendor name"},
        {"name": "Invoice Number", "type": "text", "instruction": "invoice number"},
        {"name": "Invoice Date", "type": "date", "instruction": "invoice date"},
        {"name": "Total", "type": "currency", "instruction": "total amount"},
        {"name": "Tax", "type": "currency", "instruction": "tax amount"}
    ]
    
    print("1. Processing document with schema...")
    print(f"   Document: {sample_document[:100]}...")
    print(f"   Schema: {schema}\n")
    
    result = processor.process_document_with_schema(
        sample_document,
        json.dumps(schema)
    )
    
    print("2. Processing result:")
    print(f"   Success: {result['success']}")
    print(f"   Confidence: {result['confidence']:.2f}")
    print(f"   Extracted data: {result['data']}\n")
    
    # Test with a different schema
    print("3. Testing with a different schema...")
    different_schema = [
        {"name": "Customer", "type": "text", "instruction": "customer name"},
        {"name": "Amount", "type": "currency", "instruction": "amount"}
    ]
    
    result2 = processor.process_document_with_schema(
        sample_document,
        json.dumps(different_schema)
    )
    
    print("4. Second processing result:")
    print(f"   Success: {result2['success']}")
    print(f"   Confidence: {result2['confidence']:.2f}")
    print(f"   Extracted data: {result2['data']}\n")
    
    print("5. Processing history:")
    for i, record in enumerate(processor.processing_history, 1):
        print(f"   Record {i}: Confidence {record['confidence']:.2f}, Fields: {len(record['data'])}")
    
    print("\n=== Simulation Complete ===")


def demonstrate_schema_flexibility():
    """
    Demonstrate how the schema-based extraction provides flexibility
    """
    print("\n=== Schema Flexibility Demonstration ===\n")
    
    print("Sarah AI allows users to define custom extraction schemas:")
    print("- Users specify which fields to extract")
    print("- Different field types (text, currency, number, date)")
    print("- Custom instructions for each field")
    print("- Flexible processing based on user requirements\n")
    
    print("Example schemas:")
    print("1. Financial Document Schema:")
    finance_schema = [
        {"name": "Vendor", "type": "text", "instruction": "company name"},
        {"name": "Invoice Total", "type": "currency", "instruction": "final amount"},
        {"name": "Due Date", "type": "date", "instruction": "payment due date"}
    ]
    print(f"   {finance_schema}\n")
    
    print("2. Purchase Order Schema:")
    po_schema = [
        {"name": "PO Number", "type": "text", "instruction": "purchase order number"},
        {"name": "Order Date", "type": "date", "instruction": "date order was placed"},
        {"name": "Total Amount", "type": "currency", "instruction": "order total"}
    ]
    print(f"   {po_schema}\n")
    
    print("3. Receipt Schema:")
    receipt_schema = [
        {"name": "Merchant", "type": "text", "instruction": "store name"},
        {"name": "Transaction Date", "type": "date", "instruction": "date of purchase"},
        {"name": "Total Paid", "type": "currency", "instruction": "amount paid"}
    ]
    print(f"   {receipt_schema}\n")
    
    print("This flexibility allows Sarah AI to process various document types")
    print("according to each user's specific requirements.")


if __name__ == "__main__":
    test_sarah_ai_processor()
    demonstrate_schema_flexibility()