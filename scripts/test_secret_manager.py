#!/usr/bin/env python3
"""
Secret Manager Test Script

This script tests Secret Manager authentication and access for the Django application.
It simulates the same authentication method used in bh_opie/settings.py.

Usage:
    python scripts/test_secret_manager.py [--secret-id SECRET_ID] [--version VERSION]

Examples:
    python scripts/test_secret_manager.py
    python scripts/test_secret_manager.py --secret-id bh-opie-backend --version latest
    python scripts/test_secret_manager.py --secret-id bh-opie-backend --version enabled
"""

import argparse
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from google.auth import default
from google.cloud import secretmanager
from google.auth.exceptions import DefaultCredentialsError


def test_secret_manager_access(secret_id="bh-opie-backend", version="latest", project_id="bh-opie"):
    """
    Test Secret Manager access using the same method as Django settings.py
    
    Args:
        secret_id (str): The secret ID to test
        version (str): The version to access (latest, enabled, or specific version number)
        project_id (str): The GCP project ID
    
    Returns:
        bool: True if successful, False otherwise
    """
    
    print(f"Testing Secret Manager access...")
    print(f"Secret: {secret_id}")
    print(f"Version: {version}")
    print(f"Project: {project_id}")
    print("-" * 50)
    
    try:
        # Use Application Default Credentials (ADC) which should work with VM service account
        try:
            # Get default credentials (VM service account)
            credentials, detected_project = default()
            print(f"✅ Using credentials: {credentials.service_account_email if hasattr(credentials, 'service_account_email') else 'default'}")
            print(f"✅ Detected project: {detected_project}")
            
            # Create client with explicit credentials
            client = secretmanager.SecretManagerServiceClient(credentials=credentials)
            secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
            print(f"✅ Secret name: {secret_name}")
            
            response = client.access_secret_version(request={"name": secret_name})
            payload = response.payload.data.decode("UTF-8")
            
            print("✅ Successfully loaded secrets from Secret Manager")
            print(f"✅ Secret version: {response.name}")
            print(f"✅ Secret content length: {len(payload)} characters")
            
            # Check if it contains expected content
            if "DJANGO_CONFIGURATION" in payload:
                print("✅ Secret contains Django configuration")
            else:
                print("⚠️ Secret doesn't contain expected Django configuration")
            
            # Show first few lines of content (for debugging)
            lines = payload.split('\n')[:5]
            print("✅ First 5 lines of secret content:")
            for i, line in enumerate(lines, 1):
                if line.strip():
                    print(f"   {i}: {line[:80]}{'...' if len(line) > 80 else ''}")
                
            return True
            
        except DefaultCredentialsError as e_adc:
            print(f"⚠️ ADC error, trying without explicit credentials: {e_adc}")
            # Fallback to default client creation
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
            response = client.access_secret_version(request={"name": secret_name})
            payload = response.payload.data.decode("UTF-8")
            
            print("✅ Successfully loaded secrets from Secret Manager (fallback)")
            print(f"✅ Secret version: {response.name}")
            return True
            
    except Exception as e_secret_load:
        print(f"❌ Error loading secrets from Secret Manager: {e_secret_load}")
        return False


def list_secret_versions(secret_id="bh-opie-backend", project_id="bh-opie"):
    """List available versions for a secret"""
    try:
        credentials, _ = default()
        client = secretmanager.SecretManagerServiceClient(credentials=credentials)
        
        parent = f"projects/{project_id}/secrets/{secret_id}"
        versions = client.list_secret_versions(request={"parent": parent})
        
        print(f"Available versions for {secret_id}:")
        print("-" * 50)
        
        for version in versions:
            state = version.state.name
            create_time = version.create_time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Version: {version.name.split('/')[-1]}")
            print(f"  State: {state}")
            print(f"  Created: {create_time}")
            try:
                if hasattr(version, 'aliases') and version.aliases:
                    aliases = [alias.name.split('/')[-1] for alias in version.aliases]
                    print(f"  Aliases: {', '.join(aliases)}")
            except AttributeError:
                pass  # Aliases field not available in this version
            print()
            
    except Exception as e:
        print(f"❌ Error listing versions: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test Secret Manager access")
    parser.add_argument("--secret-id", default="bh-opie-backend", help="Secret ID to test")
    parser.add_argument("--version", default="latest", help="Version to access (latest, enabled, or version number)")
    parser.add_argument("--project-id", default="bh-opie", help="GCP project ID")
    parser.add_argument("--list-versions", action="store_true", help="List available versions")
    
    args = parser.parse_args()
    
    if args.list_versions:
        list_secret_versions(args.secret_id, args.project_id)
        return
    
    success = test_secret_manager_access(args.secret_id, args.version, args.project_id)
    
    if success:
        print("\n🎉 Secret Manager test completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Secret Manager test failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
