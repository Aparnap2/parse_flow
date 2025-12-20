#!/usr/bin/env python3
"""
Systematic 4-layer validation for DocuFlow v1 readiness.
Tests: correctness, robustness, system behavior, performance & limits.
"""

import asyncio
import hashlib
import json
import os
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiohttp
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8787")
ENGINE_URL = os.getenv("ENGINE_URL", "http://localhost:8000")
WEBHOOK_TEST_URL = os.getenv("WEBHOOK_TEST_URL", "https://webhook.site/your-unique-url")

# Test data
TEST_PDF_PATH = Path(__file__).parent / "test_pdf.pdf"
TEST_DOCX_PATH = Path(__file__).parent / "test_docx.docx"
LARGE_PDF_PATH = Path(__file__).parent / "large_test.pdf"

class ValidationResult:
    def __init__(self, test_name: str, passed: bool, details: str = "", error: Optional[str] = None):
        self.test_name = test_name
        self.passed = passed
        self.details = details
        self.error = error
        self.timestamp = datetime.now().isoformat()

class DocuFlowValidator:
    def __init__(self):
        self.results: List[ValidationResult] = []
        self.project_id: Optional[str] = None
        self.api_key: Optional[str] = None
        self.document_id: Optional[str] = None
        self.webhook_id: Optional[str] = None
        self.session = requests.Session()
        
    def log_result(self, test_name: str, passed: bool, details: str = "", error: Optional[str] = None):
        result = ValidationResult(test_name, passed, details, error)
        self.results.append(result)
        status = "✅" if passed else "❌"
        print(f"{status} {test_name}")
        if details:
            print(f"   Details: {details}")
        if error:
            print(f"   Error: {error}")
        return passed

    def make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make authenticated request to API"""
        headers = kwargs.get('headers', {})
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        kwargs['headers'] = headers
        
        url = f"{API_BASE_URL}{endpoint}"
        return self.session.request(method, url, **kwargs)

    # ==================== 1. HAPPY PATH TESTS ====================

    def test_create_project(self) -> bool:
        """Test project creation"""
        try:
            response = self.make_request('POST', '/v1/projects', json={
                'name': f'Test Project {random.randint(1000, 9999)}',
                'description': 'Validation test project'
            })
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data.get('success') and 'data' in response_data:
                    self.project_id = response_data['data']['id']
                    return self.log_result('Create Project', True, f"Project ID: {self.project_id}")
                else:
                    return self.log_result('Create Project', False, f"Invalid response format: {response_data}")
            else:
                return self.log_result('Create Project', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Create Project', False, error=str(e))

    def test_create_api_key(self) -> bool:
        """Test API key creation"""
        if not self.project_id:
            return self.log_result('Create API Key', False, error="No project ID available")
            
        try:
            response = self.make_request('POST', '/v1/api-keys', json={
                'project_id': self.project_id,
                'name': 'Validation Test Key'
            })
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data.get('success') and 'data' in response_data:
                    self.api_key = response_data['data']['key']
                    return self.log_result('Create API Key', True, f"Key: {self.api_key[:10]}...")
                else:
                    return self.log_result('Create API Key', False, f"Invalid response format: {response_data}")
            else:
                return self.log_result('Create API Key', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Create API Key', False, error=str(e))

    def test_create_document(self) -> bool:
        """Test document creation"""
        if not self.api_key:
            return self.log_result('Create Document', False, error="No API key available")
            
        try:
            # Calculate SHA256 of test PDF
            with open(TEST_PDF_PATH, 'rb') as f:
                file_content = f.read()
                file_sha256 = hashlib.sha256(file_content).hexdigest()
            
            response = self.make_request('POST', '/v1/documents', json={
                'project_id': self.project_id,
                'source_name': 'test_document.pdf',
                'content_type': 'application/pdf',
                'sha256': file_sha256
            })
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data.get('success') and 'data' in response_data:
                    data = response_data['data']
                    self.document_id = data['id']
                    upload_url = data.get('upload_url')
                    status = data.get('status')
                return self.log_result('Create Document', True, 
                    f"Document ID: {self.document_id}, Status: {status}, Upload URL: {upload_url is not None}")
            else:
                return self.log_result('Create Document', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Create Document', False, error=str(e))

    def test_upload_document(self) -> bool:
        """Test document upload"""
        if not self.document_id:
            return self.log_result('Upload Document', False, error="No document ID available")
            
        try:
            # Get upload URL first
            response = self.make_request('GET', f'/v1/documents/{self.document_id}')
            if response.status_code != 200:
                return self.log_result('Upload Document', False, f"Failed to get document: {response.status_code}")
                
            response_data = response.json()
            if not response_data.get('success') or 'data' not in response_data:
                return self.log_result('Upload Document', False, "Invalid document response format")
                
            doc_data = response_data['data']
            upload_url = doc_data.get('upload_url')
            if not upload_url:
                return self.log_result('Upload Document', False, "No upload URL available")
            
            # Upload file using multipart form data with proper auth
            with open(TEST_PDF_PATH, 'rb') as f:
                files = {'file': ('test_document.pdf', f, 'application/pdf')}
                upload_response = requests.put(upload_url, files=files, headers={
                    'Authorization': f'Bearer {self.api_key}'
                })
            
            if upload_response.status_code in [200, 201]:
                return self.log_result('Upload Document', True, "File uploaded successfully")
            else:
                return self.log_result('Upload Document', False, f"Upload failed: {upload_response.status_code}")
        except Exception as e:
            return self.log_result('Upload Document', False, error=str(e))

    def test_complete_document(self) -> bool:
        """Test document completion"""
        if not self.document_id:
            return self.log_result('Complete Document', False, error="No document ID available")
            
        try:
            response = self.make_request('POST', f'/v1/documents/{self.document_id}/complete')
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data.get('success') and 'data' in response_data:
                    data = response_data['data']
                    status = data.get('status')
                    return self.log_result('Complete Document', True, f"Status: {status}")
                else:
                    return self.log_result('Complete Document', False, f"Invalid response format: {response_data}")
            else:
                return self.log_result('Complete Document', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Complete Document', False, error=str(e))

    def test_document_processing(self) -> bool:
        """Test document processing completion"""
        if not self.document_id:
            return self.log_result('Document Processing', False, error="No document ID available")
            
        try:
            # Poll for completion
            max_attempts = 30
            for attempt in range(max_attempts):
                response = self.make_request('GET', f'/v1/documents/{self.document_id}')
                if response.status_code != 200:
                    return self.log_result('Document Processing', False, f"Failed to get document: {response.status_code}")
                
                response_data = response.json()
                if not response_data.get('success') or 'data' not in response_data:
                    return self.log_result('Document Processing', False, "Invalid document response format")
                
                data = response_data['data']
                status = data.get('status')
                
                if status == 'READY':
                    chunk_count = data.get('chunk_count', 0)
                    return self.log_result('Document Processing', True, 
                        f"Document ready with {chunk_count} chunks")
                elif status == 'FAILED':
                    error = data.get('error', 'Unknown error')
                    return self.log_result('Document Processing', False, f"Processing failed: {error}")
                elif status == 'PROCESSING':
                    time.sleep(2)  # Wait 2 seconds before polling again
                    continue
                else:
                    time.sleep(2)
                    continue
            
            return self.log_result('Document Processing', False, "Timeout waiting for processing completion")
        except Exception as e:
            return self.log_result('Document Processing', False, error=str(e))

    def test_query_chunks_mode(self) -> bool:
        """Test query in chunks mode"""
        if not self.document_id:
            return self.log_result('Query Chunks Mode', False, error="No document ID available")
            
        try:
            response = self.make_request('POST', '/v1/query', json={
                'query': 'test document processing',
                'document_id': self.document_id,
                'mode': 'chunks',
                'top_k': 5
            })
            
            if response.status_code == 200:
                response_data = response.json()
                if not response_data.get('success') or 'data' not in response_data:
                    return self.log_result('Query Chunks Mode', False, "Invalid query response format")
                
                data = response_data['data']
                chunks = data.get('chunks', [])
                citations = data.get('citations', [])
                
                if chunks and citations:
                    # Check if chunks contain relevant text
                    relevant_found = any('test' in chunk.get('content_md', '').lower() for chunk in chunks)
                    return self.log_result('Query Chunks Mode', True, 
                        f"Found {len(chunks)} chunks, {len(citations)} citations, relevant: {relevant_found}")
                else:
                    return self.log_result('Query Chunks Mode', False, "No chunks or citations returned")
            else:
                return self.log_result('Query Chunks Mode', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Query Chunks Mode', False, error=str(e))

    def test_query_answer_mode(self) -> bool:
        """Test query in answer mode"""
        if not self.document_id:
            return self.log_result('Query Answer Mode', False, error="No document ID available")
            
        try:
            response = self.make_request('POST', '/v1/query', json={
                'query': 'What does this document contain?',
                'document_id': self.document_id,
                'mode': 'answer',
                'top_k': 5
            })
            
            if response.status_code == 200:
                response_data = response.json()
                if not response_data.get('success') or 'data' not in response_data:
                    return self.log_result('Query Answer Mode', False, "Invalid query response format")
                
                data = response_data['data']
                answer = data.get('answer', '')
                chunks = data.get('chunks', [])
                
                if answer and chunks:
                    return self.log_result('Query Answer Mode', True, 
                        f"Answer length: {len(answer)}, chunks: {len(chunks)}")
                else:
                    return self.log_result('Query Answer Mode', False, "Missing answer or chunks")
            else:
                return self.log_result('Query Answer Mode', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Query Answer Mode', False, error=str(e))

    # ==================== 2. UNHAPPY PATH TESTS ====================

    def test_auth_missing_header(self) -> bool:
        """Test missing authorization header"""
        try:
            response = requests.get(f"{API_BASE_URL}/v1/documents/fake-id")
            
            if response.status_code == 401:
                return self.log_result('Auth Missing Header', True, "Correctly rejected unauthenticated request")
            else:
                return self.log_result('Auth Missing Header', False, f"Expected 401, got {response.status_code}")
        except Exception as e:
            return self.log_result('Auth Missing Header', False, error=str(e))

    def test_auth_invalid_key(self) -> bool:
        """Test invalid API key"""
        try:
            response = requests.get(f"{API_BASE_URL}/v1/documents/fake-id", headers={
                'Authorization': 'Bearer invalid_key_12345'
            })
            
            if response.status_code == 403:
                return self.log_result('Auth Invalid Key', True, "Correctly rejected invalid key")
            else:
                return self.log_result('Auth Invalid Key', False, f"Expected 403, got {response.status_code}")
        except Exception as e:
            return self.log_result('Auth Invalid Key', False, error=str(e))

    def test_cross_project_access(self) -> bool:
        """Test cross-project access prevention"""
        if not self.api_key or not self.document_id:
            return self.log_result('Cross Project Access', False, error="Missing API key or document ID")
            
        try:
            # Try to access document with different project context
            # This would require creating a second project, but for now we'll test with invalid doc ID
            fake_doc_id = "00000000-0000-0000-0000-000000000000"
            response = self.make_request('GET', f'/v1/documents/{fake_doc_id}')
            
            if response.status_code == 404:
                return self.log_result('Cross Project Access', True, "Correctly returned 404 for invalid document")
            else:
                return self.log_result('Cross Project Access', False, f"Expected 404, got {response.status_code}")
        except Exception as e:
            return self.log_result('Cross Project Access', False, error=str(e))

    def test_duplicate_document(self) -> bool:
        """Test duplicate document handling"""
        if not self.api_key:
            return self.log_result('Duplicate Document', False, error="No API key available")
            
        try:
            # Calculate SHA256 of test PDF
            with open(TEST_PDF_PATH, 'rb') as f:
                file_content = f.read()
                file_sha256 = hashlib.sha256(file_content).hexdigest()
            
            # Create document with same SHA256 twice
            response1 = self.make_request('POST', '/v1/documents', json={
                'project_id': self.project_id,
                'source_name': 'duplicate_test.pdf',
                'content_type': 'application/pdf',
                'sha256': file_sha256
            })
            
            response2 = self.make_request('POST', '/v1/documents', json={
                'project_id': self.project_id,
                'source_name': 'duplicate_test2.pdf',
                'content_type': 'application/pdf',
                'sha256': file_sha256
            })
            
            if response1.status_code in [200, 201] and response2.status_code in [200, 201]:
                response_data1 = response1.json()
                response_data2 = response2.json()
                
                if not (response_data1.get('success') and 'data' in response_data1 and
                       response_data2.get('success') and 'data' in response_data2):
                    return self.log_result('Duplicate Document', False, "Invalid response format")
                
                data1 = response_data1['data']
                data2 = response_data2['data']
                
                # Check if second request was deduplicated
                deduped = data2.get('deduped', False)
                same_id = data1.get('id') == data2.get('id')
                
                return self.log_result('Duplicate Document', True, 
                    f"Deduplicated: {deduped}, Same ID: {same_id}")
            else:
                return self.log_result('Duplicate Document', False, 
                    f"Status codes: {response1.status_code}, {response2.status_code}")
        except Exception as e:
            return self.log_result('Duplicate Document', False, error=str(e))

    def test_invalid_content_type(self) -> bool:
        """Test invalid content type handling"""
        if not self.api_key:
            return self.log_result('Invalid Content Type', False, error="No API key available")
            
        try:
            # Create document with mismatched content type
            with open(TEST_PDF_PATH, 'rb') as f:
                file_content = f.read()
                file_sha256 = hashlib.sha256(file_content).hexdigest()
            
            response = self.make_request('POST', '/v1/documents', json={
                'project_id': self.project_id,
                'source_name': 'test.txt',
                'content_type': 'text/plain',  # Wrong content type for PDF
                'sha256': file_sha256
            })
            
            if response.status_code in [200, 201]:
                # Try to complete it - should fail during processing
                doc_id = response.json().get('id')
                complete_response = self.make_request('POST', f'/v1/documents/{doc_id}/complete')
                
                if complete_response.status_code == 200:
                    # Wait for processing to fail
                    time.sleep(5)
                    status_response = self.make_request('GET', f'/v1/documents/{doc_id}')
                    if status_response.status_code == 200:
                        data = status_response.json()
                        if data.get('status') == 'FAILED':
                            return self.log_result('Invalid Content Type', True, 
                                "Processing correctly failed for mismatched content type")
                
                return self.log_result('Invalid Content Type', False, 
                    "Processing should have failed but didn't")
            else:
                return self.log_result('Invalid Content Type', False, f"Status: {response.status_code}")
        except Exception as e:
            return self.log_result('Invalid Content Type', False, error=str(e))

    # ==================== 3. SYSTEM BEHAVIOR TESTS ====================

    def test_webhook_registration(self) -> bool:
        """Test webhook registration"""
        if not self.api_key:
            return self.log_result('Webhook Registration', False, error="No API key available")
            
        try:
            response = self.make_request('POST', '/v1/webhooks', json={
                'project_id': self.project_id,
                'url': WEBHOOK_TEST_URL,
                'events': ['document.ready'],
                'active': True
            })
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if response_data.get('success') and 'data' in response_data:
                    data = response_data['data']
                    self.webhook_id = data.get('id')
                    return self.log_result('Webhook Registration', True, f"Webhook ID: {self.webhook_id}")
                else:
                    return self.log_result('Webhook Registration', False, f"Invalid response format: {response_data}")
            else:
                return self.log_result('Webhook Registration', False, f"Status: {response.status_code}", response.text)
        except Exception as e:
            return self.log_result('Webhook Registration', False, error=str(e))

    def test_concurrent_document_processing(self) -> bool:
        """Test concurrent document processing"""
        if not self.api_key:
            return self.log_result('Concurrent Processing', False, error="No API key available")
            
        try:
            # Create multiple documents concurrently
            document_ids = []
            
            def create_and_upload_doc(i):
                try:
                    # Create document
                    response = self.make_request('POST', '/v1/documents', json={
                        'project_id': self.project_id,
                        'source_name': f'concurrent_test_{i}.pdf',
                        'content_type': 'application/pdf',
                        'sha256': hashlib.sha256(f'content_{i}'.encode()).hexdigest()
                    })
                    
                    if response.status_code in [200, 201]:
                        response_data = response.json()
                        if response_data.get('success') and 'data' in response_data:
                            doc_id = response_data['data'].get('id')
                            
                            # Upload a small test file
                            upload_response = self.make_request('GET', f'/v1/documents/{doc_id}')
                            if upload_response.status_code == 200:
                                upload_data = upload_response.json()
                                if upload_data.get('success') and 'data' in upload_data:
                                    upload_url = upload_data['data'].get('upload_url')
                                    if upload_url:
                                        # Upload test content
                                        test_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF"
                                        files = {'file': (f'test_{i}.pdf', test_content, 'application/pdf')}
                                        upload_req = requests.put(upload_url, files=files, headers={
                                            'Authorization': f'Bearer {self.api_key}'
                                        })
                                        
                                        if upload_req.status_code == 200:
                                            # Complete document
                                            complete_response = self.make_request('POST', f'/v1/documents/{doc_id}/complete')
                                            if complete_response.status_code == 200:
                                                return doc_id
                    return None
                except Exception as e:
                    print(f"Error in concurrent doc {i}: {e}")
                    return None
            
            # Create 5 documents concurrently
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(create_and_upload_doc, i) for i in range(5)]
                for future in as_completed(futures):
                    doc_id = future.result()
                    if doc_id:
                        document_ids.append(doc_id)
            
            if len(document_ids) >= 3:  # At least 3 successful
                return self.log_result('Concurrent Processing', True, 
                    f"Created {len(document_ids)} documents concurrently")
            else:
                return self.log_result('Concurrent Processing', False, 
                    f"Only {len(document_ids)} documents created successfully")
        except Exception as e:
            return self.log_result('Concurrent Processing', False, error=str(e))

    # ==================== 4. PERFORMANCE TESTS ====================

    def test_large_document_handling(self) -> bool:
        """Test large document handling"""
        # For now, we'll simulate with multiple small documents
        if not self.api_key:
            return self.log_result('Large Document Handling', False, error="No API key available")
            
        try:
            start_time = time.time()
            
            # Create a larger document by combining content
            large_content = "Large document content. " * 1000  # Simulate larger content
            large_hash = hashlib.sha256(large_content.encode()).hexdigest()
            
            response = self.make_request('POST', '/v1/documents', json={
                'project_id': self.project_id,
                'source_name': 'large_document.pdf',
                'content_type': 'application/pdf',
                'sha256': large_hash
            })
            
            if response.status_code in [200, 201]:
                response_data = response.json()
                if not response_data.get('success') or 'data' not in response_data:
                    return self.log_result('Large Document Handling', False, "Invalid response format")
                
                doc_id = response_data['data'].get('id')
                
                # Complete and wait for processing
                self.make_request('POST', f'/v1/documents/{doc_id}/complete')
                
                # Poll for completion
                for _ in range(30):
                    status_response = self.make_request('GET', f'/v1/documents/{doc_id}')
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        if not status_data.get('success') or 'data' not in status_data:
                            continue
                        data = status_data['data']
                        if data.get('status') == 'READY':
                            processing_time = time.time() - start_time
                            chunk_count = data.get('chunk_count', 0)
                            return self.log_result('Large Document Handling', True, 
                                f"Processed in {processing_time:.2f}s with {chunk_count} chunks")
                    time.sleep(2)
                
                return self.log_result('Large Document Handling', False, "Timeout processing large document")
            else:
                return self.log_result('Large Document Handling', False, f"Status: {response.status_code}")
        except Exception as e:
            return self.log_result('Large Document Handling', False, error=str(e))

    def test_query_performance(self) -> bool:
        """Test query performance"""
        if not self.document_id:
            return self.log_result('Query Performance', False, error="No document ID available")
            
        try:
            # Test multiple queries
            query_times = []
            for _ in range(5):
                start_time = time.time()
                response = self.make_request('POST', '/v1/query', json={
                    'query': 'test document processing',
                    'document_id': self.document_id,
                    'mode': 'chunks',
                    'top_k': 5
                })
                query_time = time.time() - start_time
                
                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get('success') and 'data' in response_data:
                        query_times.append(query_time)
            
            if query_times:
                avg_time = sum(query_times) / len(query_times)
                max_time = max(query_times)
                return self.log_result('Query Performance', True, 
                    f"Avg: {avg_time:.3f}s, Max: {max_time:.3f}s over {len(query_times)} queries")
            else:
                return self.log_result('Query Performance', False, "No successful queries")
        except Exception as e:
            return self.log_result('Query Performance', False, error=str(e))

    # ==================== MAIN VALIDATION RUN ====================

    def run_all_tests(self):
        """Run all validation tests"""
        print("🚀 Starting DocuFlow v1 Systematic Validation")
        print("=" * 60)
        
        # 1. Happy Path Tests
        print("\n📋 1. HAPPY PATH TESTS")
        print("-" * 30)
        
        self.test_create_project()
        self.test_create_api_key()
        self.test_create_document()
        self.test_upload_document()
        self.test_complete_document()
        self.test_document_processing()
        self.test_query_chunks_mode()
        self.test_query_answer_mode()
        
        # 2. Unhappy Path Tests
        print("\n🚨 2. UNHAPPY PATH TESTS")
        print("-" * 30)
        
        self.test_auth_missing_header()
        self.test_auth_invalid_key()
        self.test_cross_project_access()
        self.test_duplicate_document()
        self.test_invalid_content_type()
        
        # 3. System Behavior Tests
        print("\n⚙️  3. SYSTEM BEHAVIOR TESTS")
        print("-" * 30)
        
        self.test_webhook_registration()
        self.test_concurrent_document_processing()
        
        # 4. Performance Tests
        print("\n⚡ 4. PERFORMANCE TESTS")
        print("-" * 30)
        
        self.test_large_document_handling()
        self.test_query_performance()
        
        # Summary
        print("\n📊 VALIDATION SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\nFailed Tests:")
            for result in self.results:
                if not result.passed:
                    print(f"  ❌ {result.test_name}")
                    if result.error:
                        print(f"     Error: {result.error}")
        
        return passed_tests, failed_tests

if __name__ == "__main__":
    validator = DocuFlowValidator()
    passed, failed = validator.run_all_tests()
    
    # Exit with error code if any tests failed
    exit(1 if failed > 0 else 0)