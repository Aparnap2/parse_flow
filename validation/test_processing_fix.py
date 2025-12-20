#!/usr/bin/env python3
"""
Test script to verify document processing fix
"""

import requests
import json
import time
import hashlib
import io

API_BASE_URL = "http://localhost:8787"

def test_document_processing():
    """Test complete document processing flow"""
    print("🧪 Testing Document Processing Fix")
    print("=" * 50)
    
    # Step 1: Create project
    print("1. Creating project...")
    response = requests.post(f"{API_BASE_URL}/v1/projects", json={"name": "Test Project"})
    if response.status_code != 200:
        print(f"❌ Failed to create project: {response.status_code}")
        return False, None
    
    response_data = response.json()
    project_data = response_data.get("data", {})
    project_id = project_data.get("id")
    print(f"✅ Project created: {project_id}")
    
    # Step 2: Create API key
    print("2. Creating API key...")
    response = requests.post(f"{API_BASE_URL}/v1/api-keys", json={
        "project_id": project_id,
        "name": "Test Key"
    })
    if response.status_code != 200:
        print(f"❌ Failed to create API key: {response.status_code}")
        return False, None
    
    response_data = response.json()
    api_key_data = response_data.get("data", {})
    api_key = api_key_data.get("key")
    print(f"✅ API key created: {api_key[:10]}...")
    
    # Step 3: Create document
    print("3. Creating document...")
    test_content = b"Test document content for processing"
    file_hash = hashlib.sha256(test_content).hexdigest()
    
    response = requests.post(f"{API_BASE_URL}/v1/documents", 
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "project_id": project_id,
            "source_name": "test_document.pdf",
            "content_type": "application/pdf",
            "sha256": file_hash
        }
    )
    if response.status_code != 200:
        print(f"❌ Failed to create document: {response.status_code}")
        print(f"Response: {response.text}")
        return False, None
    
    response_data = response.json()
    doc_data = response_data.get("data", {})
    document_id = doc_data.get("id")
    print(f"✅ Document created: {document_id}")
    
    # Step 4: Upload document (simulate)
    print("4. Simulating document upload...")
    files = {'file': ('test_document.pdf', io.BytesIO(test_content), 'application/pdf')}
    response = requests.put(f"{API_BASE_URL}/v1/documents/{document_id}/upload",
        headers={"Authorization": f"Bearer {api_key}"},
        files=files
    )
    if response.status_code != 200:
        print(f"❌ Failed to upload document: {response.status_code}")
        return False, None
    print("✅ Document uploaded")
    
    # Step 5: Complete document (trigger processing)
    print("5. Completing document (triggering processing)...")
    response = requests.post(f"{API_BASE_URL}/v1/documents/{document_id}/complete",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    if response.status_code != 200:
        print(f"❌ Failed to complete document: {response.status_code}")
        print(f"Response: {response.text}")
        return False, None
    
    response_data = response.json()
    complete_data = response_data.get("data", {})
    print(f"✅ Document completion triggered: {complete_data}")
    
    # Step 6: Check document status
    print("6. Checking document status...")
    max_attempts = 10
    for attempt in range(max_attempts):
        response = requests.get(f"{API_BASE_URL}/v1/documents/{document_id}",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        if response.status_code != 200:
            print(f"❌ Failed to get document status: {response.status_code}")
            return False, None
        
        response_data = response.json()
        doc_data = response_data.get("data", {})
        status = doc_data.get("status")
        print(f"   Attempt {attempt + 1}: Status = {status}")
        
        if status == "READY":
            chunk_count = doc_data.get("chunk_count", 0)
            print(f"✅ Document processing completed successfully!")
            print(f"   Chunks created: {chunk_count}")
            return True, api_key
        elif status == "FAILED":
            error = doc_data.get("error", "Unknown error")
            print(f"❌ Document processing failed: {error}")
            return False, None
        elif status in ["CREATED", "UPLOADED", "PROCESSING"]:
            time.sleep(1)  # Wait and check again
            continue
        else:
            print(f"❌ Unexpected status: {status}")
            return False, None
    
    print(f"❌ Document still in {status} state after {max_attempts} attempts")
    return False, None

def test_query_functionality(api_key):
    """Test query functionality after processing"""
    print("\n🔍 Testing Query Functionality")
    print("=" * 50)
    
    # Test query endpoint
    response = requests.post("http://localhost:8787/v1/query",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": "document processing", "mode": "chunks", "top_k": 5}
    )
    print(f"Query endpoint status: {response.status_code}")
    if response.status_code == 200:
        print(f"Query response: {response.json()}")
    return True

if __name__ == "__main__":
    print("Starting DocuFlow Processing Fix Test...\n")
    
    # Test document processing
    success, api_key = test_document_processing()
    
    if success:
        print("\n🎉 All tests passed! Document processing is working correctly.")
        # Test query functionality
        test_query_functionality(api_key)
    else:
        print("\n❌ Tests failed. Check the logs above for details.")