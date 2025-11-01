#!/usr/bin/env python
"""
Script to check and read a document file from GCS bucket.
The file content is base64 encoded, so this script decodes it.
"""

import base64
import json
import os
import sys

from django.conf import settings
from google.cloud import storage
from google.oauth2 import service_account

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bh_opie.settings")
import django

django.setup()

from apps.opie.utils.gcs_utils import get_storage_client
from apps.docs.utils import base64_yjs_to_text, base64_yjs_to_xml


def get_client_with_fallback():
    """Get GCS client, falling back to service account file if Django settings aren't configured."""
    try:
        return get_storage_client()
    except (AttributeError, Exception):
        # Fallback: use service account file directly
        creds_path = ".gcp/creds/bh-opie/storage.json"
        if os.path.exists(creds_path):
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            return storage.Client(credentials=credentials, project="bh-opie")
        else:
            raise Exception(f"Could not find credentials file at {creds_path}")


def check_and_read_file(file_key: str, bucket_name: str = None):
    """
    Check if file exists and read its content with base64 decoding.
    
    Args:
        file_key: The GCS object key (path) to the file
        bucket_name: Optional bucket name, defaults to GCS_DOCS_BUCKET_NAME
    """
    if bucket_name is None:
        try:
            bucket_name = settings.GCS_DOCS_BUCKET_NAME
        except AttributeError:
            bucket_name = "bh-opie-docs"

    print(f"Checking file: {file_key}")
    print(f"Bucket: {bucket_name}")
    print("-" * 80)

    try:
        client = get_client_with_fallback()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_key)

        # Check if file exists
        if not blob.exists():
            print(f"❌ File NOT found: {file_key}")
            return None

        print(f"✅ File exists!")
        print(f"Size: {blob.size} bytes")
        print(f"Content Type: {blob.content_type}")
        print(f"Time Created: {blob.time_created}")
        print("-" * 80)

        # Download and read the content
        print("Reading file content...")
        content_bytes = blob.download_as_bytes()
        print(f"Downloaded {len(content_bytes)} bytes")

        # Try to decode as UTF-8 first (in case it's stored as base64 string)
        try:
            content_str = content_bytes.decode("utf-8")
            print(f"Decoded to UTF-8 string: {len(content_str)} characters")
            
            # Check if content looks like base64
            import re
            is_base64_like = re.match(r'^[A-Za-z0-9+/]*={0,2}$', content_str)
            
            # Try to decode base64 from string (with and without validation)
            if is_base64_like:
                try:
                    decoded_bytes = base64.b64decode(content_str, validate=True)
                    # Try to decode as UTF-8
                    try:
                        decoded_str = decoded_bytes.decode("utf-8")
                        print(f"✅ Base64 decoded and UTF-8 decoded: {len(decoded_str)} characters")
                    except UnicodeDecodeError:
                        # Decoded bytes are binary (likely Y.js format)
                        print(f"✅ Base64 decoded: {len(decoded_bytes)} bytes")
                        print(f"⚠️  Decoded content is binary (not UTF-8 text) - likely Y.js document format")
                        
                        # Try to extract text from Y.js format
                        try:
                            print("-" * 80)
                            print("Extracting text from Y.js document...")
                            extracted_text = base64_yjs_to_text(content_str)
                            print(f"✅ Extracted text: {len(extracted_text)} characters")
                            print("-" * 80)
                            print("Text content:")
                            print(extracted_text)
                            
                            # Also show XML structure if needed
                            xml_structure = base64_yjs_to_xml(content_str)
                            print("-" * 80)
                            print(f"XML structure ({len(xml_structure)} characters):")
                            print(xml_structure[:1000])
                            if len(xml_structure) > 1000:
                                print(f"\n... (truncated, {len(xml_structure) - 1000} more characters)")
                            
                            return extracted_text
                        except Exception as e:
                            print(f"⚠️  Could not extract text from Y.js: {e}")
                            print(f"Binary content (hex, first 100 bytes): {decoded_bytes[:100].hex()}")
                            print(f"Binary content (repr, first 200 bytes): {repr(decoded_bytes[:200])}")
                            # Convert binary to string representation for display
                            decoded_str = base64.b64encode(decoded_bytes).decode("utf-8")
                            print(f"Re-encoded as base64 for display: {len(decoded_str)} characters")
                except Exception as e1:
                    # Try without validation (in case padding is off)
                    try:
                        decoded_bytes = base64.b64decode(content_str, validate=False)
                        try:
                            decoded_str = decoded_bytes.decode("utf-8")
                            print(f"✅ Base64 decoded (unvalidated) and UTF-8 decoded: {len(decoded_str)} characters")
                        except UnicodeDecodeError:
                            print(f"✅ Base64 decoded (unvalidated): {len(decoded_bytes)} bytes")
                            print(f"⚠️  Decoded content is binary (not UTF-8 text)")
                            
                            # Try to extract text from Y.js format
                            try:
                                print("-" * 80)
                                print("Extracting text from Y.js document...")
                                extracted_text = base64_yjs_to_text(content_str)
                                print(f"✅ Extracted text: {len(extracted_text)} characters")
                                print("-" * 80)
                                print("Text content:")
                                print(extracted_text)
                                return extracted_text
                            except Exception as e:
                                print(f"⚠️  Could not extract text from Y.js: {e}")
                                decoded_str = base64.b64encode(decoded_bytes).decode("utf-8")
                    except Exception as e2:
                        # Not valid base64
                        print(f"⚠️  Base64 decode failed: {e1}, then {e2}")
                        print(f"Content appears to be binary/Y.js format (starts with: {content_str[:50]})")
                        print(f"Content length: {len(content_str)} characters")
                        decoded_str = content_str
            else:
                # Doesn't look like base64
                print("⚠️  Content doesn't match base64 pattern")
                print(f"Content appears to be binary/Y.js format (starts with: {content_str[:50]})")
                decoded_str = content_str
        except UnicodeDecodeError:
            # Content is binary - try base64 decode directly
            print("Content appears to be binary, attempting base64 decode...")
            try:
                decoded_bytes = base64.b64decode(content_bytes, validate=True)
                decoded_str = decoded_bytes.decode("utf-8")
                print(f"Base64 decoded from bytes: {len(decoded_str)} characters")
            except (base64.binascii.Error, UnicodeDecodeError) as e:
                print(f"❌ Could not decode: {e}")
                print("Raw bytes (hex, first 100 bytes):")
                print(content_bytes[:100].hex())
                return content_bytes
        
        print("-" * 80)
        print("Decoded content:")
        print(decoded_str[:500])  # Print first 500 chars
        if len(decoded_str) > 500:
            print(f"\n... (truncated, {len(decoded_str) - 500} more characters)")
        
        # Try to parse as JSON
        try:
            json_content = json.loads(decoded_str)
            print("-" * 80)
            print("✅ Content is valid JSON")
            if isinstance(json_content, dict):
                print(f"JSON keys: {list(json_content.keys())}")
            else:
                print(f"JSON type: {type(json_content).__name__}")
        except json.JSONDecodeError:
            print("-" * 80)
            print("⚠️  Content is not valid JSON (might be binary or other format)")

        return decoded_str

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_document_file.py <file_key> [bucket_name]")
        print("\nExample:")
        print(
            "python scripts/check_document_file.py "
            "'user=47adba46-1bec-4bb1-a664-27fb0b81c14b/year=2025/month=10/day=27/4d61aecb-0293-43a2-a54a-e67c6fd395cd/file'"
        )
        sys.exit(1)

    file_key = sys.argv[1]
    bucket_name = sys.argv[2] if len(sys.argv) > 2 else None

    check_and_read_file(file_key, bucket_name)

