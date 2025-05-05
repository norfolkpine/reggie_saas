import os
from urllib.parse import urljoin

import requests


def test_api_key(api_key, base_url="http://localhost:8000"):
    """
    Test an API key against the health endpoint
    """
    headers = {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json", "Accept": "application/json"}

    # Test the health endpoint
    health_url = urljoin(base_url, "api/v1/health/")
    try:
        response = requests.get(health_url, headers=headers)
        print(f"\nTesting API key against {health_url}")
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("✅ API key is valid and working")
        elif response.status_code == 403:
            print("❌ API key is invalid or unauthorized")
        else:
            print(f"⚠️ Unexpected status code: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Error making request: {str(e)}")


def main():
    # Get API keys from environment variables
    system_api_key = os.getenv("DJANGO_API_KEY")
    user_api_key = os.getenv("USER_API_KEY")
    base_url = os.getenv("DJANGO_API_URL", "http://localhost:8000")

    if system_api_key:
        print("\n=== Testing System API Key ===")
        test_api_key(system_api_key, base_url)
    else:
        print("⚠️ No system API key found in environment variables")

    if user_api_key:
        print("\n=== Testing User API Key ===")
        test_api_key(user_api_key, base_url)
    else:
        print("⚠️ No user API key found in environment variables")


if __name__ == "__main__":
    main()
