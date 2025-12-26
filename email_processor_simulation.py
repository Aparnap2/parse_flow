"""
Sarah AI Email Processing Worker

This module simulates the email processing functionality for Sarah AI,
handling incoming emails with document attachments and processing them
according to user-defined blueprints.
"""

import json
import tempfile
import os
from datetime import datetime
from typing import Dict, Any, Optional
import re

class EmailProcessor:
    """Simulates the email processing functionality for Sarah AI"""
    
    def __init__(self):
        self.users_db = {}
        self.blueprints_db = {}
        self.jobs_db = {}
        self.rate_limiter = {}
    
    def add_user(self, user_id: str, email: str, inbox_alias: str):
        """Add a user to the system"""
        self.users_db[user_id] = {
            "id": user_id,
            "email": email,
            "inbox_alias": inbox_alias,
            "created_at": datetime.utcnow().isoformat()
        }
    
    def add_blueprint(self, user_id: str, blueprint_data: Dict[str, Any]):
        """Add a blueprint for a user"""
        blueprint_id = f"bp_{len(self.blueprints_db) + 1}"
        blueprint = {
            "id": blueprint_id,
            "user_id": user_id,
            "name": blueprint_data["name"],
            "schema": blueprint_data["schema"],
            "created_at": datetime.utcnow().isoformat()
        }
        self.blueprints_db[blueprint_id] = blueprint
        
        # Link to user
        user = self.users_db.get(user_id)
        if user:
            if "blueprint_ids" not in user:
                user["blueprint_ids"] = []
            user["blueprint_ids"].append(blueprint_id)
        
        return blueprint
    
    def simulate_email_received(self, sender: str, recipient: str, subject: str, attachments: list):
        """Simulate receiving an email with attachments"""
        print(f"Received email from {sender} to {recipient} with {len(attachments)} attachment(s)")
        
        # Rate limiting check
        if not self._check_rate_limit(sender):
            print(f"Rate limit exceeded for {sender}, dropping email")
            self._send_rate_limit_email(sender)
            return {"status": "dropped", "reason": "rate_limit"}
        
        # Find user by inbox alias
        user = self._find_user_by_inbox_alias(recipient)
        if not user:
            print(f"No user found for inbox alias: {recipient}")
            return {"status": "error", "reason": "no_user_found"}
        
        print(f"Identified user: {user['id']}")
        
        # Find user's blueprint
        blueprint = self._find_blueprint_for_user(user['id'])
        if not blueprint:
            print(f"No blueprint found for user: {user['id']}")
            self._send_no_blueprint_email(sender)
            return {"status": "error", "reason": "no_blueprint"}
        
        print(f"Using blueprint: {blueprint['id']} - {blueprint['name']}")
        
        # Process each PDF attachment
        results = []
        for attachment in attachments:
            if attachment.get('content_type') == 'application/pdf':
                result = self._process_pdf_attachment(
                    user['id'], 
                    blueprint, 
                    attachment,
                    sender,
                    subject
                )
                results.append(result)
        
        return {
            "status": "processed",
            "user_id": user['id'],
            "blueprint_id": blueprint['id'],
            "results": results
        }
    
    def _check_rate_limit(self, sender: str) -> bool:
        """Check if the sender is within rate limits"""
        # For simulation, we'll allow 5 emails per hour per sender
        current_time = datetime.utcnow().timestamp()
        if sender not in self.rate_limiter:
            self.rate_limiter[sender] = []
        
        # Clean up old entries (older than 1 hour)
        one_hour_ago = current_time - 3600
        self.rate_limiter[sender] = [
            timestamp for timestamp in self.rate_limiter[sender] 
            if timestamp > one_hour_ago
        ]
        
        # Check if under limit
        if len(self.rate_limiter[sender]) >= 5:
            return False
        
        # Add current timestamp
        self.rate_limiter[sender].append(current_time)
        return True
    
    def _find_user_by_inbox_alias(self, inbox_alias: str):
        """Find a user by their inbox alias"""
        for user in self.users_db.values():
            if user.get('inbox_alias') == inbox_alias:
                return user
        return None
    
    def _find_blueprint_for_user(self, user_id: str):
        """Find a blueprint for a user"""
        user = self.users_db.get(user_id)
        if not user or 'blueprint_ids' not in user:
            return None
        
        # Return the first blueprint (in a real system, you might have logic to select the right one)
        for bp_id in user.get('blueprint_ids', []):
            if bp_id in self.blueprints_db:
                return self.blueprints_db[bp_id]
        
        return None
    
    def _process_pdf_attachment(self, user_id: str, blueprint: Dict[str, Any], 
                              attachment: Dict[str, Any], sender: str, subject: str):
        """Process a single PDF attachment"""
        print(f"Processing PDF attachment: {attachment.get('filename', 'unknown')}")
        
        # Create a job record
        job_id = f"job_{len(self.jobs_db) + 1}"
        job = {
            "id": job_id,
            "user_id": user_id,
            "blueprint_id": blueprint['id'],
            "status": "queued",
            "r2_key": f"uploads/{user_id}/{attachment.get('filename', 'unnamed.pdf')}",
            "sender": sender,
            "subject": subject,
            "created_at": datetime.utcnow().isoformat()
        }
        self.jobs_db[job_id] = job
        
        print(f"Created job: {job_id}")
        
        # In a real system, this would queue the job for processing
        # For simulation, we'll process it immediately
        processing_result = self._simulate_document_processing(blueprint['schema'])
        
        # Update job with results
        job.update({
            "status": "completed" if processing_result.get("success") else "failed",
            "result_json": json.dumps(processing_result.get("data", {})),
            "confidence": processing_result.get("confidence", 0.0),
            "completed_at": datetime.utcnow().isoformat()
        })
        
        return {
            "job_id": job_id,
            "status": job["status"],
            "confidence": job["confidence"],
            "extracted_data": processing_result.get("data", {})
        }
    
    def _simulate_document_processing(self, schema: list):
        """Simulate processing a document according to the provided schema"""
        # Generate mock data based on the schema
        extracted_data = {}
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            
            # Generate appropriate mock data based on field type
            if field_type == 'currency':
                extracted_data[field_name] = "$1,234.56"
            elif field_type == 'number':
                extracted_data[field_name] = "1234"
            elif field_type == 'date':
                extracted_data[field_name] = "2025-12-26"
            else:  # text
                extracted_data[field_name] = f"Sample {field_name} value"
        
        # Calculate confidence (mock calculation)
        confidence = 0.92  # High confidence for demo purposes
        
        return {
            "success": True,
            "data": extracted_data,
            "confidence": confidence
        }
    
    def _send_rate_limit_email(self, recipient: str):
        """Simulate sending a rate limit exceeded email"""
        print(f"Sending rate limit exceeded notification to {recipient}")
    
    def _send_no_blueprint_email(self, recipient: str):
        """Simulate sending a no blueprint found email"""
        print(f"Sending no blueprint notification to {recipient}")


def simulate_email_processing():
    """Simulate the email processing workflow"""
    print("=== Sarah AI Email Processing Simulation ===\n")
    
    processor = EmailProcessor()
    
    # Add a sample user
    user_id = "user_12345"
    processor.add_user(
        user_id=user_id,
        email="test@example.com",
        inbox_alias="user_12345@sarah.ai"
    )
    print(f"Added user: {user_id}")
    
    # Add a sample blueprint for the user
    blueprint_data = {
        "name": "Xero Import",
        "schema": [
            {"name": "Vendor", "type": "text", "instruction": "Extract vendor name"},
            {"name": "Total", "type": "currency", "instruction": "Extract total amount"},
            {"name": "Invoice Date", "type": "date", "instruction": "Extract invoice date"}
        ]
    }
    blueprint = processor.add_blueprint(user_id, blueprint_data)
    print(f"Added blueprint: {blueprint['id']}\n")
    
    # Simulate receiving an email
    email_result = processor.simulate_email_received(
        sender="vendor@home-depot.com",
        recipient="user_12345@sarah.ai",
        subject="Invoice #12345",
        attachments=[
            {
                "filename": "invoice_12345.pdf",
                "content_type": "application/pdf",
                "size": 123456
            }
        ]
    )
    
    print(f"\nEmail processing result: {email_result}")
    
    # Simulate rate limiting
    print(f"\n--- Testing Rate Limiting ---")
    for i in range(6):
        rate_limit_result = processor.simulate_email_received(
            sender="frequent@sender.com",
            recipient="user_12345@sarah.ai",
            subject=f"Test email {i}",
            attachments=[
                {
                    "filename": f"doc_{i}.pdf",
                    "content_type": "application/pdf",
                    "size": 50000
                }
            ]
        )
        print(f"Email {i+1} result: {rate_limit_result['status']}")
    
    # Show jobs database
    print(f"\n--- Jobs Database ---")
    for job_id, job in processor.jobs_db.items():
        print(f"Job {job_id}: {job['status']} - Confidence: {job.get('confidence', 'N/A')}")


if __name__ == "__main__":
    simulate_email_processing()