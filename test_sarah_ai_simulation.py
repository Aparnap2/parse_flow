"""
Sarah AI Simulation Test File

This file simulates the Sarah AI functionality without modifying the existing ParseFlow implementation.
It demonstrates the key features of Sarah AI as specified in the PRD.
"""

import json
import tempfile
import os
from typing import Dict, List, Any
import re

class SarahAISimulator:
    """
    A simulator for Sarah AI functionality based on the PRD specifications
    """
    
    def __init__(self):
        self.users = []
        self.blueprints = []
        self.jobs = []
    
    def create_user(self, email: str, google_id: str = None) -> Dict[str, Any]:
        """Create a new user with an inbox alias"""
        user_id = f"user_{len(self.users) + 1}"
        inbox_alias = f"{user_id}@sarah.ai"
        
        user = {
            "id": user_id,
            "email": email,
            "google_id": google_id,
            "inbox_alias": inbox_alias
        }
        
        self.users.append(user)
        return user
    
    def create_blueprint(self, user_id: str, name: str, schema: List[Dict[str, str]]) -> Dict[str, Any]:
        """Create a new extraction blueprint"""
        blueprint_id = f"bp_{len(self.blueprints) + 1}"
        
        blueprint = {
            "id": blueprint_id,
            "user_id": user_id,
            "name": name,
            "schema_json": json.dumps(schema)
        }
        
        self.blueprints.append(blueprint)
        return blueprint
    
    def process_email(self, sender: str, recipient: str, attachment_path: str) -> Dict[str, Any]:
        """Simulate processing an email with an attachment"""
        # Find user based on inbox alias
        user = next((u for u in self.users if u["inbox_alias"] == recipient), None)
        if not user:
            return {"error": f"No user found for inbox alias: {recipient}"}
        
        # Find user's blueprint
        user_blueprint = next((bp for bp in self.blueprints if bp["user_id"] == user["id"]), None)
        if not user_blueprint:
            return {"error": f"No blueprint found for user: {user['id']}"}
        
        # Create a job
        job_id = f"job_{len(self.jobs) + 1}"
        job = {
            "id": job_id,
            "user_id": user["id"],
            "status": "queued",
            "r2_key": f"uploads/{user['id']}/{os.path.basename(attachment_path)}",
            "result_json": None,
            "confidence": None,
            "created_at": "2025-12-26T10:00:00Z"
        }
        
        self.jobs.append(job)
        
        # Simulate processing
        result = self._simulate_document_processing(attachment_path, user_blueprint)
        
        # Update job status
        job.update({
            "status": "completed" if result.get("success") else "failed",
            "result_json": json.dumps(result.get("data", {})),
            "confidence": result.get("confidence", 0.0),
            "completed_at": "2025-12-26T10:05:00Z"
        })
        
        return {
            "job_id": job_id,
            "status": job["status"],
            "result": result.get("data", {}),
            "confidence": result.get("confidence", 0.0)
        }
    
    def _simulate_document_processing(self, file_path: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate processing a document according to the user's schema"""
        # Load the schema
        schema = json.loads(blueprint["schema_json"])
        
        # For simulation purposes, we'll create mock data based on the schema
        extracted_data = {}
        for field in schema:
            field_name = field["name"]
            field_type = field.get("type", "text")
            
            # Generate mock data based on field type
            if field_type == "currency":
                extracted_data[field_name] = "$1,234.56"
            elif field_type == "number":
                extracted_data[field_name] = "1234"
            elif field_type == "date":
                extracted_data[field_name] = "2025-12-26"
            else:  # text
                extracted_data[field_name] = f"Sample {field_name} value"
        
        # Calculate confidence (mock calculation)
        confidence = 0.95  # High confidence for demo purposes
        
        return {
            "success": True,
            "data": extracted_data,
            "confidence": confidence
        }
    
    def get_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all jobs for a user"""
        return [job for job in self.jobs if job["user_id"] == user_id]


def test_sarah_ai_simulation():
    """Test the Sarah AI simulation"""
    print("=== Sarah AI Simulation Test ===\n")
    
    # Initialize simulator
    simulator = SarahAISimulator()
    
    # 1. Create a user
    print("1. Creating a user...")
    user = simulator.create_user("test@example.com", "google123")
    print(f"   Created user: {user['id']} with inbox alias: {user['inbox_alias']}\n")
    
    # 2. Create a blueprint
    print("2. Creating a blueprint...")
    schema = [
        {"name": "Vendor", "type": "text", "instruction": "Extract vendor name from invoice"},
        {"name": "Total", "type": "currency", "instruction": "Extract total amount"},
        {"name": "Invoice Date", "type": "date", "instruction": "Extract invoice date"},
        {"name": "Invoice Number", "type": "text", "instruction": "Extract invoice number"}
    ]
    
    blueprint = simulator.create_blueprint(user["id"], "Xero Import", schema)
    print(f"   Created blueprint: {blueprint['id']} named '{blueprint['name']}'\n")
    
    # 3. Simulate receiving an email with an attachment
    print("3. Processing an email with an attachment...")
    
    # Create a temporary file to simulate an attachment
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as temp_file:
        temp_file.write("Sample invoice document")
        temp_file_path = temp_file.name
    
    try:
        result = simulator.process_email(
            "vendor@example.com",
            user["inbox_alias"],
            temp_file_path
        )
        
        print(f"   Processing result: {result}\n")
        
        # 4. Check the job status
        print("4. Checking job status...")
        user_jobs = simulator.get_user_jobs(user["id"])
        if user_jobs:
            latest_job = user_jobs[0]
            print(f"   Job ID: {latest_job['id']}")
            print(f"   Status: {latest_job['status']}")
            print(f"   Confidence: {latest_job['confidence']}")
            print(f"   Result: {latest_job['result_json']}")
        
    finally:
        # Clean up the temporary file
        os.unlink(temp_file_path)
    
    print("\n=== Simulation Complete ===")


def demonstrate_sarah_ai_features():
    """Demonstrate key features of Sarah AI as specified in the PRD"""
    print("\n=== Sarah AI Feature Demonstration ===\n")
    
    print("Feature A: The Blueprint Builder")
    print("- Users can define custom columns and instructions")
    print("- Supports different field types (text, currency, number, date)")
    print("- Allows custom math formulas\n")
    
    print("Feature B: The Email Ingest")
    print("- Each user gets a unique inbox alias (e.g., user123@sarah.ai)")
    print("- System identifies user via 'From' address")
    print("- Processes PDF attachments automatically\n")
    
    print("Feature C: The AI Processor")
    print("- Extracts data according to user-defined schemas")
    print("- Handles different document formats")
    print("- Calculates confidence scores\n")
    
    print("Feature D: The HITL Dashboard")
    print("- Users can review low-confidence data")
    print("- Visual reports of extracted data")
    print("- Approve/reject functionality\n")


if __name__ == "__main__":
    test_sarah_ai_simulation()
    demonstrate_sarah_ai_features()