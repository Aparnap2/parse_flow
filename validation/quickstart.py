#!/usr/bin/env python3
"""
DocuFlow v1 E2E Quickstart Script
Proves the system works end-to-end in under 50 lines
"""

import hashlib
import requests
import time
import sys

API_BASE = "http://localhost:8787"
TEST_FILE = "test_pdf.pdf"

def main():
    # 1. Create project
    resp = requests.post(f"{API_BASE}/v1/projects", json={"name": "Quickstart"})
    project_id = resp.json()["id"]
    print(f"✅ Project: {project_id}")
    
    # 2. Create API key
    resp = requests.post(f"{API_BASE}/v1/api-keys", json={"project_id": project_id, "name": "quickstart"})
    api_key = resp.json()["key"]
    print(f"✅ API Key: {api_key[:10]}...")
    
    # 3. Create document
    with open(TEST_FILE, "rb") as f:
        content = f.read()
        sha256 = hashlib.sha256(content).hexdigest()
    
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(f"{API_BASE}/v1/documents",
                        json={"project_id": project_id, "source_name": "quickstart.pdf",
                              "content_type": "application/pdf", "sha256": sha256},
                        headers=headers)
    doc_data = resp.json()
    doc_id = doc_data["document_id"]
    print(f"✅ Document: {doc_id}")
    
    # 4. Upload document
    upload_url = resp.json()["upload_url"]
    requests.put(upload_url, data=content, headers={"Content-Type": "application/pdf"})
    print("✅ Uploaded")
    
    # 5. Complete document
    requests.post(f"{API_BASE}/v1/documents/{doc_id}/complete", headers=headers)
    print("✅ Processing started")
    
    # 6. Poll until ready
    while True:
        resp = requests.get(f"{API_BASE}/v1/documents/{doc_id}", headers=headers)
        status = resp.json()["status"]
        if status == "READY":
            chunks = resp.json()["chunk_count"]
            print(f"✅ Ready with {chunks} chunks")
            break
        elif status == "FAILED":
            print("❌ Processing failed")
            sys.exit(1)
        time.sleep(2)
        print(".", end="", flush=True)
    
    # 7. Query document
    resp = requests.post(f"{API_BASE}/v1/query", 
                        json={"query": "What does this document contain?", 
                              "document_id": doc_id, "mode": "answer"}, 
                        headers=headers)
    answer = resp.json()["answer"]
    print(f"\n✅ Answer: {answer[:100]}...")

if __name__ == "__main__":
    main()