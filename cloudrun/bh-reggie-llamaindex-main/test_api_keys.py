import requests
import os
import json
from urllib.parse import urljoin

def mask_sensitive_value(key, value):
    """Mask sensitive values like API keys"""
    sensitive_keys = ['API_KEY', 'PASSWORD', 'SECRET']
    if any(s in key for s in sensitive_keys):
        return f"{value[:6]}...{value[-4:]}" if value else None
    return value

def load_env_from_file(env_file='.env'):
    """Load environment variables from file"""
    if not os.path.exists(env_file):
        print(f"⚠️ Environment file {env_file} not found")
        return
        
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value
                except ValueError:
                    print(f"⚠️ Skipping malformed line: {line}")

def test_api_key(api_key, base_url="http://localhost:8000"):
    """
    Test an API key against the health endpoint
    """
    headers = {
        'Authorization': f'Api-Key {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    
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
        except:
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
    # Load environment variables from file
    load_env_from_file()
    
    # Get API keys from environment variables
    system_api_key = os.environ.get("DJANGO_API_KEY")
    user_api_key = os.environ.get("USER_API_KEY")
    base_url = os.environ.get("DJANGO_API_URL", "http://localhost:8000")
    
    print("\n=== Testing Configuration ===")
    print(f"Base URL: {base_url}")
    print(f"System API Key: {mask_sensitive_value('DJANGO_API_KEY', system_api_key)}")
    print(f"User API Key: {mask_sensitive_value('USER_API_KEY', user_api_key)}")
    
    success = False
    if system_api_key:
        print("\n=== Testing System API Key ===")
        success = test_api_key(system_api_key, base_url)
    else:
        print("⚠️ No system API key found in environment variables")
        
    if user_api_key:
        print("\n=== Testing User API Key ===")
        success = test_api_key(user_api_key, base_url) or success
    else:
        print("⚠️ No user API key found in environment variables")
        
    # Exit with appropriate status code
    exit(0 if success else 1)
        
if __name__ == "__main__":
    main() 