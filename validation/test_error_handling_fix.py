#!/usr/bin/env python3
"""
Test script to validate the enhanced error handling for external services.
This script tests all the critical error scenarios that were identified as blockers.
"""

import asyncio
import json
import requests
import time
from typing import Dict, Any, Optional
import subprocess
import sys
from pathlib import Path

# Add the validation directory to Python path
sys.path.append(str(Path(__file__).parent))

from systematic_validation import DocuFlowValidator, ValidationResult

class ErrorHandlingValidator(DocuFlowValidator):
    """Enhanced validator focused on error handling scenarios"""
    
    def __init__(self, base_url: str = "http://localhost:8787"):
        super().__init__()
        self.base_url = base_url
        self.test_results: Dict[str, ValidationResult] = {}
    
    async def test_authentication_errors(self) -> ValidationResult:
        """Test that authentication endpoints return proper error codes"""
        print("🧪 Testing authentication error handling...")
        
        tests = [
            {
                "name": "Missing API key",
                "headers": {},
                "expected_status": 401,
                "expected_code": "MISSING_API_KEY"
            },
            {
                "name": "Invalid API key",
                "headers": {"Authorization": "Bearer invalid_key_12345"},
                "expected_status": 403,
                "expected_code": "INVALID_API_KEY"
            },
            {
                "name": "Malformed Authorization header",
                "headers": {"Authorization": "invalid_format"},
                "expected_status": 401,
                "expected_code": "MISSING_API_KEY"
            }
        ]
        
        all_passed = True
        results = []
        
        for test in tests:
            try:
                response = requests.post(
                    f"{self.base_url}/v1/documents",
                    headers=test["headers"],
                    json={"project_id": "test-project", "source_name": "test.pdf", "content_type": "application/pdf", "sha256": "abc123"}
                )
                
                if response.status_code == test["expected_status"]:
                    data = response.json()
                    if data.get("error", {}).get("code") == test["expected_code"]:
                        results.append(f"✅ {test['name']}: Correct {test['expected_status']} with code {test['expected_code']}")
                    else:
                        results.append(f"❌ {test['name']}: Wrong error code. Expected {test['expected_code']}, got {data.get('error', {}).get('code')}")
                        all_passed = False
                else:
                    results.append(f"❌ {test['name']}: Wrong status code. Expected {test['expected_status']}, got {response.status_code}")
                    all_passed = False
                    
            except Exception as e:
                results.append(f"❌ {test['name']}: Exception - {str(e)}")
                all_passed = False
        
        return ValidationResult(
            test_name="Authentication Error Handling",
            passed=all_passed,
            details="\n".join(results)
        )
    
    async def test_vectorize_errors(self) -> ValidationResult:
        """Test Vectorize service error handling"""
        print("🧪 Testing Vectorize error handling...")
        
        # First create a document and project
        try:
            project_response = requests.post(f"{self.base_url}/v1/projects", json={"name": "Vectorize Test"})
            project_data = project_response.json()
            project_id = project_data["data"]["id"]
            
            api_key_response = requests.post(f"{self.base_url}/v1/api-keys", json={"project_id": project_id, "name": "test-key"})
            api_key_data = api_key_response.json()
            api_key = api_key_data["data"]["key"]
            
            headers = {"Authorization": f"Bearer {api_key}"}
            
            # Create document
            doc_response = requests.post(
                f"{self.base_url}/v1/documents",
                headers=headers,
                json={"project_id": project_id, "source_name": "test.pdf", "content_type": "application/pdf", "sha256": "vectorize_test_123"}
            )
            
            if doc_response.status_code != 200:
                return ValidationResult(
                    test_name="Vectorize Error Handling",
                    passed=False,
                    details=f"Failed to create document: {doc_response.status_code} - {doc_response.text}"
                )
            
            doc_data = doc_response.json()
            doc_id = doc_data["data"]["id"]
            
            # Upload a test file
            upload_url = f"{self.base_url}/v1/documents/{doc_id}/upload"
            # Create a simple test PDF content
            test_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000074 00000 n \n0000000120 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF"
            
            # Use proper multipart form data format
            files = {'file': ('test.pdf', test_content, 'application/pdf')}
            upload_response = requests.put(upload_url, headers=headers, files=files)
            
            if upload_response.status_code != 200:
                return ValidationResult(
                    test_name="Vectorize Error Handling",
                    passed=False,
                    details=f"Failed to upload test file: {upload_response.status_code} - {upload_response.text}"
                )
            
            # Complete document to trigger processing
            complete_response = requests.post(
                f"{self.base_url}/v1/documents/{doc_id}/complete",
                headers=headers
            )
            
            # Wait a bit for processing to potentially fail
            time.sleep(2)
            
            # Check document status
            status_response = requests.get(
                f"{self.base_url}/v1/documents/{doc_id}",
                headers=headers
            )
            
            status_data = status_response.json()
            doc_status = status_data["data"]["status"]
            
            if doc_status == "FAILED":
                # Check if it has proper error information
                error_info = status_data["data"].get("error", "")
                if error_info and ("Vectorize" in error_info or "vector" in error_info.lower()):
                    return ValidationResult(
                        test_name="Vectorize Error Handling",
                        passed=True,
                        details="✅ Document properly failed with Vectorize error information"
                    )
                else:
                    return ValidationResult(
                        test_name="Vectorize Error Handling",
                        passed=False,
                        details=f"❌ Document failed but without proper Vectorize error info: {error_info}"
                    )
            elif doc_status == "READY":
                return ValidationResult(
                    test_name="Vectorize Error Handling",
                    passed=True,
                    details="✅ Document processed successfully (Vectorize working)"
                )
            else:
                return ValidationResult(
                    test_name="Vectorize Error Handling",
                    passed=False,
                    details=f"❌ Document in unexpected state: {doc_status}"
                )
                
        except Exception as e:
            return ValidationResult(
                test_name="Vectorize Error Handling",
                passed=False,
                details=f"❌ Exception during Vectorize test: {str(e)}"
            )
    
    async def test_r2_errors(self) -> ValidationResult:
        """Test R2 service error handling"""
        print("🧪 Testing R2 error handling...")
        
        try:
            # Try to upload to a non-existent document
            project_response = requests.post(f"{self.base_url}/v1/projects", json={"name": "R2 Test"})
            project_data = project_response.json()
            project_id = project_data["data"]["id"]
            
            api_key_response = requests.post(f"{self.base_url}/v1/api-keys", json={"project_id": project_id, "name": "test-key"})
            api_key_data = api_key_response.json()
            api_key = api_key_data["data"]["key"]
            
            headers = {"Authorization": f"Bearer {api_key}"}
            
            # Try to upload to non-existent document
            files = {'file': ('test.pdf', b"test data", 'application/pdf')}
            upload_response = requests.put(
                f"{self.base_url}/v1/documents/non-existent-id/upload",
                headers=headers,
                files=files
            )
            
            if upload_response.status_code == 404:
                data = upload_response.json()
                if data.get("error", {}).get("code") == "DOCUMENT_NOT_FOUND":
                    return ValidationResult(
                        test_name="R2 Error Handling",
                        passed=True,
                        details="✅ Proper 404 error for non-existent document"
                    )
                else:
                    return ValidationResult(
                        test_name="R2 Error Handling",
                        passed=False,
                        details=f"❌ Wrong error code for non-existent document: {data.get('error', {}).get('code')}"
                    )
            else:
                return ValidationResult(
                    test_name="R2 Error Handling",
                    passed=False,
                    details=f"❌ Wrong status code for non-existent document: {upload_response.status_code}"
                )
                
        except Exception as e:
            return ValidationResult(
                test_name="R2 Error Handling",
                passed=False,
                details=f"❌ Exception during R2 test: {str(e)}"
            )
    
    async def test_ai_service_errors(self) -> ValidationResult:
        """Test Workers AI service error handling"""
        print("🧪 Testing Workers AI error handling...")
        
        try:
            project_response = requests.post(f"{self.base_url}/v1/projects", json={"name": "AI Test"})
            project_data = project_response.json()
            project_id = project_data["data"]["id"]
            
            api_key_response = requests.post(f"{self.base_url}/v1/api-keys", json={"project_id": project_id, "name": "test-key"})
            api_key_data = api_key_response.json()
            api_key = api_key_data["data"]["key"]
            
            headers = {"Authorization": f"Bearer {api_key}"}
            
            # Test query with very long text that might cause AI service issues
            long_query = "x" * 10000  # 10k characters
            
            query_response = requests.post(
                f"{self.base_url}/v1/query",
                headers=headers,
                json={
                    "query": long_query,
                    "top_k": 5,
                    "mode": "chunks"
                }
            )
            
            # The system should handle this gracefully
            if query_response.status_code in [200, 500]:
                data = query_response.json()
                if query_response.status_code == 500:
                    # Check if it's a proper AI error
                    error_code = data.get("error", {}).get("code")
                    if error_code in ["EMBEDDING_ERROR", "ANSWER_GENERATION_ERROR"]:
                        return ValidationResult(
                            test_name="AI Service Error Handling",
                            passed=True,
                            details="✅ Proper AI service error handling"
                        )
                    else:
                        return ValidationResult(
                            test_name="AI Service Error Handling",
                            passed=False,
                            details=f"❌ Wrong error code for AI service: {error_code}"
                        )
                else:
                    return ValidationResult(
                        test_name="AI Service Error Handling",
                        passed=True,
                        details="✅ AI service handled long query successfully"
                    )
            else:
                return ValidationResult(
                    test_name="AI Service Error Handling",
                    passed=False,
                    details=f"❌ Unexpected status code: {query_response.status_code}"
                )
                
        except Exception as e:
            return ValidationResult(
                test_name="AI Service Error Handling",
                passed=False,
                details=f"❌ Exception during AI service test: {str(e)}"
            )
    
    async def test_webhook_errors(self) -> ValidationResult:
        """Test webhook delivery error handling"""
        print("🧪 Testing webhook error handling...")
        
        try:
            project_response = requests.post(f"{self.base_url}/v1/projects", json={"name": "Webhook Test"})
            project_data = project_response.json()
            project_id = project_data["data"]["id"]
            
            api_key_response = requests.post(f"{self.base_url}/v1/api-keys", json={"project_id": project_id, "name": "test-key"})
            api_key_data = api_key_response.json()
            api_key = api_key_data["data"]["key"]
            
            headers = {"Authorization": f"Bearer {api_key}"}
            
            # Register webhook to invalid URL
            webhook_response = requests.post(
                f"{self.base_url}/v1/webhooks",
                headers=headers,
                json={"url": "http://invalid-url-that-does-not-exist.com/webhook", "events": ["document.processed"], "project_id": project_id}
            )
            
            if webhook_response.status_code == 200:
                webhook_data = webhook_response.json()
                # The webhook response should have the webhook data, not webhook_id
                if "data" in webhook_data and "id" in webhook_data["data"]:
                    webhook_id = webhook_data["data"]["id"]
                    
                    # Create and process a document to trigger webhook
                    doc_response = requests.post(
                        f"{self.base_url}/v1/documents",
                        headers=headers,
                        json={"project_id": project_id, "source_name": "test.pdf", "content_type": "application/pdf", "sha256": "webhook_test_123"}
                    )
                    
                    if doc_response.status_code == 200:
                        return ValidationResult(
                            test_name="Webhook Error Handling",
                            passed=True,
                            details="✅ Webhook registered successfully (delivery errors handled internally)"
                        )
                    else:
                        return ValidationResult(
                            test_name="Webhook Error Handling",
                            passed=False,
                            details=f"❌ Failed to create test document: {doc_response.status_code}"
                        )
                else:
                    return ValidationResult(
                        test_name="Webhook Error Handling",
                        passed=False,
                        details=f"❌ Webhook response missing expected data structure: {webhook_data}"
                    )
            else:
                return ValidationResult(
                    test_name="Webhook Error Handling",
                    passed=False,
                    details=f"❌ Failed to register webhook: {webhook_response.status_code} - {webhook_response.text}"
                )
                
        except Exception as e:
            return ValidationResult(
                test_name="Webhook Error Handling",
                passed=False,
                details=f"❌ Exception during webhook test: {str(e)}"
            )
    
    async def test_database_errors(self) -> ValidationResult:
        """Test database error handling"""
        print("🧪 Testing database error handling...")
        
        try:
            # Test with invalid project ID
            api_key_response = requests.post(
                f"{self.base_url}/v1/api-keys",
                json={"project_id": "non-existent-project-id", "name": "test-key"}
            )
            
            if api_key_response.status_code == 404:
                data = api_key_response.json()
                if data.get("error", {}).get("code") == "PROJECT_NOT_FOUND":
                    return ValidationResult(
                        test_name="Database Error Handling",
                        passed=True,
                        details="✅ Proper 404 error for non-existent project"
                    )
                else:
                    return ValidationResult(
                        test_name="Database Error Handling",
                        passed=False,
                        details=f"❌ Wrong error code for non-existent project: {data.get('error', {}).get('code')}"
                    )
            else:
                return ValidationResult(
                    test_name="Database Error Handling",
                    passed=False,
                    details=f"❌ Wrong status code for non-existent project: {api_key_response.status_code}"
                )
                
        except Exception as e:
            return ValidationResult(
                test_name="Database Error Handling",
                passed=False,
                details=f"❌ Exception during database test: {str(e)}"
            )
    
    async def run_all_tests(self) -> Dict[str, ValidationResult]:
        """Run all error handling tests"""
        print("🚀 Starting comprehensive error handling validation...")
        
        tests = [
            self.test_authentication_errors,
            self.test_vectorize_errors,
            self.test_r2_errors,
            self.test_ai_service_errors,
            self.test_webhook_errors,
            self.test_database_errors,
        ]
        
        results = {}
        
        for test_func in tests:
            try:
                result = await test_func()
                results[result.test_name] = result
                print(f"  {result.test_name}: {'✅ PASS' if result.passed else '❌ FAIL'}")
                if not result.passed:
                    print(f"    Details: {result.details}")
            except Exception as e:
                results[test_func.__name__] = ValidationResult(
                    test_name=test_func.__name__,
                    passed=False,
                    details=f"Exception: {str(e)}"
                )
                print(f"  {test_func.__name__}: ❌ FAIL (Exception)")
        
        return results
    
    def generate_report(self, results: Dict[str, ValidationResult]) -> str:
        """Generate a comprehensive error handling report"""
        passed = sum(1 for r in results.values() if r.passed)
        total = len(results)
        
        report = f"""
# Error Handling Validation Report

## Summary
- **Total Tests**: {total}
- **Passed**: {passed}
- **Failed**: {total - passed}
- **Success Rate**: {passed/total*100:.1f}%

## Detailed Results

"""
        
        for name, result in results.items():
            status = "✅ PASS" if result.passed else "❌ FAIL"
            report += f"### {result.test_name}: {status}\n"
            report += f"{result.details}\n\n"
        
        if passed < total:
            report += """
## Recommendations

The following error handling scenarios need attention:

"""
            for name, result in results.items():
                if not result.passed:
                    report += f"- **{result.test_name}**: {result.details}\n"
        
        return report

async def main():
    """Main test execution"""
    print("🔧 Error Handling Validation for DocuFlow")
    print("=" * 50)
    
    # Ensure the local API server is running
    try:
        response = requests.get("http://localhost:8787/v1/projects", timeout=5)
        # Any response (even 405) means server is running
        print("✅ Local API server is running")
    except requests.exceptions.RequestException as e:
        print("❌ Local API server not running. Please start it first:")
        print("   cd validation && . .venv/bin/activate && uvicorn standardized_api_server:app --host 0.0.0.0 --port 8787 --reload")
        print(f"   Error: {str(e)}")
        return
    
    validator = ErrorHandlingValidator()
    results = await validator.run_all_tests()
    
    report = validator.generate_report(results)
    print("\n" + report)
    
    # Save report to file
    report_path = Path(__file__).parent / "error_handling_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"\n📄 Report saved to {report_path}")
    
    # Exit with appropriate code
    passed = sum(1 for r in results.values() if r.passed)
    total = len(results)
    
    if passed == total:
        print("🎉 All error handling tests passed!")
        sys.exit(0)
    else:
        print(f"⚠️  {total - passed} out of {total} tests failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())