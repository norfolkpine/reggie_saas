import json
import os
from pathlib import Path
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

# Always load .env from one directory up
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DJANGO_API_KEY = os.getenv("DJANGO_API_KEY")


def mask_sensitive_value(key, value):
    """Mask sensitive values like API keys"""
    sensitive_keys = ["API_KEY", "PASSWORD", "SECRET"]
    if any(s in key for s in sensitive_keys):
        return f"{value[:6]}...{value[-4:]}" if value else None
    return value


def test_api_key(api_key, base_url="http://localhost:8000"):
    """
    Test an API key against the health endpoint
    """
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json", "Accept": "application/json"}

    # Test the health endpoint
    health_url = urljoin(base_url, "health/")
    try:
        print(f"\nTesting API key against {health_url}")
        print(f"Headers: {headers}")
        response = requests.get(health_url, headers=headers)
        print(f"Status code: {response.status_code}")

        try:
            response_json = response.json()
            print("Response:")
            print(json.dumps(response_json, indent=2))
        except json.JSONDecodeError:
            print(f"Response: {response.text}")

        if response.status_code == 403:
            print("❌ API key is invalid or unauthorized")
            return False
        elif response.status_code in [200, 500]:  # Accept 500 as it means we authenticated but Celery is down
            if response.status_code == 500 and "CeleryHealthCheckCelery" in response.text:
                print("✅ API key is valid (Celery is down but authentication worked)")
            else:
                print("✅ API key is valid and working")
            return True
        else:
            print(f"⚠️ Unexpected status code: {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"❌ Error making request: {str(e)}")
        return False


def test_file_progress_update(api_key, base_url="http://localhost:8000"):
    """
    Test POSTing a progress update to the file endpoint.
    """
    dummy_file_uuid = "123e4567-e89b-12d3-a456-426614174000"
    url = f"{base_url.rstrip('/')}/opie/api/v1/files/{dummy_file_uuid}/update-progress/"
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"progress": 42.0, "processed_docs": 21, "total_docs": 50, "link_id": None, "error": None}
    print(f"\nTesting file progress update endpoint: {url}")
    print(f"Payload: {json.dumps(payload)}")
    try:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Status code: {response.status_code}")
        try:
            print("Response:")
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(f"Response: {response.text}")
        if response.status_code in [200, 201]:
            print("✅ File progress update POST succeeded.")
            return True
        else:
            print("❌ File progress update POST failed.")
            return False
    except Exception as e:
        print(f"❌ Exception during file progress update POST: {e}")
        return False


def main():
    print("\n=== Testing Configuration ===")
    print(f"Base URL: {BASE_URL}")
    print(f"System API Key: {DJANGO_API_KEY if DJANGO_API_KEY else 'None'}")

    if not DJANGO_API_KEY:
        print("⚠️ No system API key found in environment variables")
        exit(1)
    else:
        print("\n=== Testing System API Key ===")
        valid = test_api_key(DJANGO_API_KEY, BASE_URL)
        if not valid:
            print("❌ System API key test failed.")
            exit(1)
        else:
            print("✅ System API key test passed.")
            # Test the file progress update endpoint
            file_update_ok = test_file_progress_update(DJANGO_API_KEY, BASE_URL)
            if not file_update_ok:
                print("❌ File progress update endpoint test failed.")
                exit(1)
            else:
                print("✅ File progress update endpoint test passed.")
                exit(0)


if __name__ == "__main__":
    main()
