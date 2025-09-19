"""
Example usage of signed URL utilities for AI agents.
This demonstrates how AI agents can generate proper file URLs.
"""

from .signed_url_utils import get_file_url, generate_signed_url, get_file_content_type


def example_ai_agent_file_access():
    """
    Example of how an AI agent can generate file URLs for different use cases.
    """
    
    # Example file paths (these would come from your file models)
    file_paths = [
        "bh-reggie-test-media/user_files/user_uuid=641b01fe-870e-4dee-88fd-5bdc4541bbf9/year=2025/month=08/day=28/C2025C00235_27e0d171.pdf",
        "media/vault/project_456/contract.docx", 
        "media/global/templates/standard_form.pdf"
    ]
    
    print("=== AI Agent File URL Generation Examples ===\n")
    
    for file_path in file_paths:
        print(f"File: {file_path}")
        
        # 1. Get direct URL (for public files or when signed URLs aren't needed)
        direct_url = get_file_url(file_path, signed=False)
        print(f"  Direct URL: {direct_url}")
        
        # 2. Get signed URL (for private files that need time-limited access)
        signed_url = get_file_url(file_path, signed=True, expiration_hours=2)
        print(f"  Signed URL (2h): {signed_url}")
        
        # 3. Get content type for the file
        content_type = get_file_content_type(file_path)
        print(f"  Content Type: {content_type}")
        
        print()


def example_ai_agent_with_file_models():
    """
    Example of how an AI agent would work with actual file models.
    """
    from django.core.files.storage import default_storage
    
    # Simulate file model instances
    class MockFile:
        def __init__(self, file_path, title, file_size):
            self.file = MockFileField(file_path)
            self.title = title
            self.file_size = file_size
    
    class MockFileField:
        def __init__(self, name):
            self.name = name
    
    # Example files
    files = [
        MockFile("media/user_files/123/report.pdf", "Q4 Report", 1024000),
        MockFile("media/vault/project_456/contract.docx", "Service Contract", 512000),
    ]
    
    print("=== AI Agent with File Models ===\n")
    
    for file in files:
        print(f"File: {file.title}")
        print(f"  Path: {file.file.name}")
        print(f"  Size: {file.file_size} bytes")
        
        # Generate appropriate URL based on file type/context
        if "vault" in file.file.name:
            # Vault files might need signed URLs for security
            url = get_file_url(file.file.name, signed=True, expiration_hours=1)
            print(f"  URL (signed, 1h): {url}")
        else:
            # Regular files might use direct URLs
            url = get_file_url(file.file.name, signed=False)
            print(f"  URL (direct): {url}")
        
        print()


if __name__ == "__main__":
    # Run examples
    example_ai_agent_file_access()
    example_ai_agent_with_file_models()
