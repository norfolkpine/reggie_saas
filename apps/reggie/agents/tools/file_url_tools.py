"""
Agent tools for generating file URLs and signed URLs.
These tools allow AI agents to generate proper URLs for files stored in the system.
"""

from agno.tools import Toolkit
from agno.utils.log import logger


class FileURLTools(Toolkit):
    """
    Tools for generating file URLs and signed URLs for AI agents.
    
    These tools allow agents to:
    - Generate direct URLs for files
    - Generate signed URLs with expiration times
    - Get file content types
    - Validate file access
    """
    
    def __init__(self):
        super().__init__(name="file_url_tools")
        self.register(self.get_file_url)
        self.register(self.generate_signed_url)
        self.register(self.get_file_content_type)
        self.register(self.validate_file_access)
    
    def get_file_url(
        self, 
        file_path: str, 
        signed: bool = False, 
        expiration_hours: int = 1
    ) -> str:
        """
        Get a file URL, optionally signed for cloud storage.
        
        This is the main function for AI agents to use when they need to generate
        URLs for files referenced in their responses.
        
        Args:
            file_path: Path to the file in storage (e.g., 'media/user_files/123/document.pdf')
            signed: Whether to generate a signed URL (for cloud storage)
            expiration_hours: Hours until signed URL expires (if signed=True)
            
        Returns:
            File URL (signed or direct)
            
        Example:
            # For public files
            url = get_file_url("media/user_files/document.pdf", signed=False)
            
            # For private files with time-limited access
            url = get_file_url("media/vault/contract.pdf", signed=True, expiration_hours=2)
        """
        try:
            from apps.reggie.utils.signed_url_utils import get_file_url as _get_file_url
            return _get_file_url(file_path, signed=signed, expiration_hours=expiration_hours)
        except Exception as e:
            logger.error(f"Failed to get file URL for {file_path}: {str(e)}")
            return f"Error generating URL for {file_path}: {str(e)}"
    
    def generate_signed_url(
        self, 
        file_path: str, 
        expiration_hours: int = 1, 
        method: str = "GET", 
        content_type: str = None
    ) -> str:
        """
        Generate a signed URL for accessing a file stored in cloud storage.
        
        This function generates time-limited signed URLs for secure file access.
        Useful when agents need to provide temporary access to private files.
        
        Args:
            file_path: Path to the file in storage
            expiration_hours: Number of hours until the URL expires (default: 1)
            method: HTTP method allowed (default: 'GET')
            content_type: Optional content type for the file
            
        Returns:
            Signed URL string or error message if generation fails
            
        Example:
            signed_url = generate_signed_url("media/vault/private_document.pdf", expiration_hours=6)
        """
        try:
            from apps.reggie.utils.signed_url_utils import generate_signed_url as _generate_signed_url
            result = _generate_signed_url(file_path, expiration_hours, method, content_type)
            if result:
                return result
            else:
                return f"Failed to generate signed URL for {file_path}"
        except Exception as e:
            logger.error(f"Failed to generate signed URL for {file_path}: {str(e)}")
            return f"Error generating signed URL for {file_path}: {str(e)}"
    
    def get_file_content_type(self, file_path: str) -> str:
        """
        Get content type for a file based on its extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            MIME type string
            
        Example:
            content_type = get_file_content_type("document.pdf")  # Returns "application/pdf"
        """
        try:
            from apps.reggie.utils.signed_url_utils import get_file_content_type as _get_file_content_type
            return _get_file_content_type(file_path)
        except Exception as e:
            logger.error(f"Failed to get content type for {file_path}: {str(e)}")
            return "application/octet-stream"
    
    def validate_file_access(self, file_path: str, user_id: str = None) -> str:
        """
        Validate that a user has access to a file.
        
        This is a basic implementation that checks if the file path is in allowed directories.
        Should be enhanced based on your access control needs.
        
        Args:
            file_path: Path to the file
            user_id: Optional user ID for access validation
            
        Returns:
            "true" if user has access, "false" otherwise
            
        Example:
            has_access = validate_file_access("media/user_files/document.pdf", "user123")
        """
        try:
            from apps.reggie.utils.signed_url_utils import validate_file_access as _validate_file_access
            
            # Create a mock user object if user_id is provided
            user = None
            if user_id:
                try:
                    from apps.users.models import CustomUser
                    user = CustomUser.objects.get(id=user_id)
                except Exception:
                    pass
            
            result = _validate_file_access(file_path, user)
            return "true" if result else "false"
        except Exception as e:
            logger.error(f"Failed to validate file access for {file_path}: {str(e)}")
            return "false"
