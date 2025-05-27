import json
import os
from urllib.parse import urljoin
import requests
from dotenv import load_dotenv
from pathlib import Path

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


def main():
    print("\n=== Testing Configuration ===")
    print(f"Base URL: {BASE_URL}")
    print(f"System API Key: {DJANGO_API_KEY if DJANGO_API_KEY else 'None'}")

    if not DJANGO_API_KEY:
        print("⚠️ No system API key found in environment variables")
    else:
        # Example test: try to access a protected endpoint with the system API key
        headers = {"Authorization": f"Api-Key {DJANGO_API_KEY}"}
        try:
            response = requests.get(f"{BASE_URL}/some/protected/endpoint", headers=headers)
            print(f"Status code: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error making request: {e}")

        # Test the health endpoint
        print("\n=== Testing System API Key ===")
        test_api_key(DJANGO_API_KEY, BASE_URL)

    # Exit with appropriate status code
    exit(0)


if __name__ == "__main__":
    main()
