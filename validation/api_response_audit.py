#!/usr/bin/env python3
"""
Audit API response formats to identify inconsistencies
"""

import requests
import json

API_BASE_URL = "http://localhost:8787"

def audit_api_responses():
    """Audit all API endpoints for response format consistency"""
    print("🔍 Auditing API Response Formats")
    print("=" * 60)
    
    # Create a project and API key for testing
    print("1. Creating test project...")
    response = requests.post(f"{API_BASE_URL}/v1/projects", json={"name": "Audit Project"})
    response_data = response.json()
    project_data = response_data.get("data", {})
    project_id = project_data.get("id")
    print(f"   Project ID: {project_id}")
    
    print("2. Creating API key...")
    response = requests.post(f"{API_BASE_URL}/v1/api-keys", json={
        "project_id": project_id,
        "name": "Audit Key"
    })
    response_data = response.json()
    api_key_data = response_data.get("data", {})
    api_key = api_key_data.get("key")
    print(f"   API Key: {api_key[:10]}...")
    
    endpoints = [
        {
            "name": "Create Project",
            "method": "POST",
            "url": "/v1/projects",
            "data": {"name": "Test Project"},
            "auth": False
        },
        {
            "name": "Create API Key", 
            "method": "POST",
            "url": "/v1/api-keys",
            "data": {"project_id": project_id, "name": "Test Key"},
            "auth": False
        },
        {
            "name": "Create Document",
            "method": "POST", 
            "url": "/v1/documents",
            "data": {
                "project_id": project_id,
                "source_name": "test.pdf",
                "content_type": "application/pdf",
                "sha256": "abc123"
            },
            "auth": True
        },
        {
            "name": "Get Document",
            "method": "GET",
            "url": f"/v1/documents/test-doc-id",
            "data": None,
            "auth": True
        },
        {
            "name": "Query Documents",
            "method": "POST",
            "url": "/v1/query",
            "data": {"query": "test query", "mode": "chunks", "top_k": 5},
            "auth": True
        },
        {
            "name": "Create Webhook",
            "method": "POST",
            "url": "/v1/webhooks",
            "data": {
                "project_id": project_id,
                "url": "https://example.com/webhook",
                "events": ["document.ready"]
            },
            "auth": True
        }
    ]
    
    results = []
    
    for endpoint in endpoints:
        print(f"\n3. Testing: {endpoint['name']}")
        headers = {}
        if endpoint['auth']:
            headers['Authorization'] = f'Bearer {api_key}'
        
        try:
            if endpoint['method'] == 'POST':
                response = requests.post(f"{API_BASE_URL}{endpoint['url']}", 
                                       json=endpoint['data'], headers=headers)
            elif endpoint['method'] == 'GET':
                response = requests.get(f"{API_BASE_URL}{endpoint['url']}", headers=headers)
            
            print(f"   Status: {response.status_code}")
            
            try:
                response_data = response.json()
                print(f"   Response keys: {list(response_data.keys())}")
                results.append({
                    "endpoint": endpoint['name'],
                    "status": response.status_code,
                    "response_keys": list(response_data.keys()),
                    "sample_response": response_data
                })
            except:
                print(f"   Non-JSON response: {response.text[:100]}")
                results.append({
                    "endpoint": endpoint['name'],
                    "status": response.status_code,
                    "response_keys": [],
                    "sample_response": response.text
                })
                
        except Exception as e:
            print(f"   Error: {e}")
            results.append({
                "endpoint": endpoint['name'],
                "status": "ERROR",
                "response_keys": [],
                "sample_response": str(e)
            })
    
    # Analysis
    print(f"\n📊 Response Format Analysis")
    print("=" * 60)
    
    # Check for common patterns
    all_keys = set()
    key_frequency = {}
    
    for result in results:
        for key in result['response_keys']:
            all_keys.add(key)
            key_frequency[key] = key_frequency.get(key, 0) + 1
    
    print(f"All unique response keys found: {sorted(all_keys)}")
    print(f"\nKey frequency across endpoints:")
    for key, freq in sorted(key_frequency.items(), key=lambda x: x[1], reverse=True):
        print(f"  {key}: {freq} endpoints")
    
    # Identify inconsistencies
    print(f"\n⚠️  Potential Issues Found:")
    
    # Check for inconsistent success indicators
    success_indicators = ['ok', 'success', 'status']
    success_patterns = {}
    for result in results:
        for indicator in success_indicators:
            if indicator in result['response_keys']:
                if indicator not in success_patterns:
                    success_patterns[indicator] = []
                success_patterns[indicator].append(result['endpoint'])
    
    if len(success_patterns) > 1:
        print("  ❌ Multiple success indicator patterns:")
        for indicator, endpoints in success_patterns.items():
            print(f"    - {indicator}: {endpoints}")
    
    # Check for inconsistent ID field names
    id_fields = ['id', 'document_id', 'project_id', 'webhook_id']
    id_patterns = {}
    for result in results:
        for field in id_fields:
            if field in result['response_keys']:
                if field not in id_patterns:
                    id_patterns[field] = []
                id_patterns[field].append(result['endpoint'])
    
    if len(id_patterns) > 3:  # Allow for different types of IDs
        print("  ❌ Inconsistent ID field naming:")
        for field, endpoints in id_patterns.items():
            print(f"    - {field}: {endpoints}")
    
    # Check for missing standard fields
    standard_fields = ['created_at', 'updated_at']
    for field in standard_fields:
        missing_endpoints = [r['endpoint'] for r in results if field not in r['response_keys'] and r['status'] == 200]
        if missing_endpoints:
            print(f"  ❌ Missing {field} in: {missing_endpoints}")
    
    return results

if __name__ == "__main__":
    audit_api_responses()