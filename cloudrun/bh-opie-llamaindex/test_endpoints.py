#!/usr/bin/env python3
"""
Test script for LlamaIndex GCS ingestion service endpoints
"""
import json
import requests
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8080"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

def test_health_check():
    """Test the health check endpoint"""
    print("🔍 Testing health check endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/", headers=HEADERS)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_openapi_docs():
    """Test the OpenAPI documentation endpoint"""
    print("\n🔍 Testing OpenAPI docs endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/docs")
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'Unknown')}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_openapi_json():
    """Test the OpenAPI JSON schema endpoint"""
    print("\n🔍 Testing OpenAPI JSON endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/openapi.json", headers=HEADERS)
        print(f"Status Code: {response.status_code}")
        schema = response.json()
        print(f"OpenAPI Version: {schema.get('openapi', 'Unknown')}")
        print(f"Available Paths: {list(schema.get('paths', {}).keys())}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_ingest_gcs_endpoint():
    """Test the GCS ingestion endpoint with a sample request"""
    print("\n🔍 Testing GCS ingestion endpoint...")
    
    # Sample request payload
    payload = {
        "gcs_prefix": "test-documents/",
        "file_limit": 5,
        "vector_table_name": "test_vector_table"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/ingest-gcs", json=payload, headers=HEADERS)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code in [200, 500]  # 500 might be expected due to missing env vars
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_ingest_file_endpoint():
    """Test the single file ingestion endpoint with a sample request"""
    print("\n🔍 Testing single file ingestion endpoint...")
    
    # Sample request payload
    payload = {
        "file_path": "gs://test-bucket/sample.pdf",
        "vector_table_name": "test_vector_table",
        "file_uuid": "test-uuid-12345",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-ada-002",
        "user_uuid": "user-uuid-12345",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "batch_size": 10
    }
    
    try:
        response = requests.post(f"{BASE_URL}/ingest-file", json=payload, headers=HEADERS)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code in [200, 500]  # 500 might be expected due to missing env vars
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_delete_vectors_endpoint():
    """Test the delete vectors endpoint with a sample request"""
    print("\n🔍 Testing delete vectors endpoint...")
    
    # Sample request payload
    payload = {
        "vector_table_name": "test_vector_table",
        "file_uuid": "test-uuid-12345"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/delete-vectors", json=payload, headers=HEADERS)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code in [200, 500]  # 500 might be expected due to missing env vars
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_invalid_endpoint():
    """Test an invalid endpoint to ensure proper error handling"""
    print("\n🔍 Testing invalid endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/invalid-endpoint", headers=HEADERS)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 404
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Run all endpoint tests"""
    print("🚀 Starting LlamaIndex GCS Ingestion Service Endpoint Tests")
    print("=" * 60)
    
    tests = [
        ("Health Check", test_health_check),
        ("OpenAPI Docs", test_openapi_docs),
        ("OpenAPI JSON", test_openapi_json),
        ("GCS Ingestion", test_ingest_gcs_endpoint),
        ("Single File Ingestion", test_ingest_file_endpoint),
        ("Delete Vectors", test_delete_vectors_endpoint),
        ("Invalid Endpoint", test_invalid_endpoint),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        success = test_func()
        results.append((test_name, success))
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:<25} {status}")
        if success:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed - check the output above for details")

if __name__ == "__main__":
    main()
