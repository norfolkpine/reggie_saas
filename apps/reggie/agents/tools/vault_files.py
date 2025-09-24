from typing import List, Dict, Optional, Any
from agno.tools import Toolkit
from agno.utils.log import logger
from django.apps import apps
from django.contrib.auth import get_user_model

User = get_user_model()


class VaultFilesTools(Toolkit):
    def __init__(
        self,
        project_id: str,
        user,
        folder_id: Optional[str] = None,
        file_ids: Optional[list] = None,
    ):
        self.project_id = project_id
        self.user = user
        self.folder_id = folder_id
        self.file_ids = file_ids or []

        super().__init__(name="vault_files_tools")

        # Register methods as Agno tools
        self.register(self.get_vault_files)
        self.register(self.get_vault_file_content)
        self.register(self.get_vault_file_by_id)
        self.register(self.search_vault_files)
        self.register(self.get_folder_contents)
        self.register(self.get_root_folder_contents)

        print("===============================================================")
        print(self.project_id)
        print(self.user)
        print(self.folder_id)
        print(self.file_ids)
        print("===============================================================")

    def _get_vault_file_model(self):
        """Get the VaultFile model."""
        return apps.get_model('reggie', 'VaultFile')

    def _get_project_model(self):
        """Get the Project model."""
        return apps.get_model('reggie', 'Project')

    def get_vault_files(
        self, 
        project_uuid: Optional[str] = None, 
        parent_id: Optional[int] = None,
        limit: int = 50,
        user_id: Optional[int] = None
    ) -> str:
        """
        Get a list of vault files accessible to the current user.
        
        Args:
            project_uuid: Optional project UUID to filter files by project
            parent_id: Optional parent folder ID to filter files by folder
            limit: Maximum number of files to return (default: 50)
            user_id: User ID to filter files for (if not provided, returns all accessible files)
        
        Returns:
            Formatted string containing the list of vault files
        """
        try:
            print("vault file getting")

            VaultFile = self._get_vault_file_model()
            Project = self._get_project_model()
            
            # Start with base queryset
            queryset = VaultFile.objects.all()
            
            # Apply filters
            if project_uuid:
                try:
                    project = Project.objects.get(uuid=project_uuid)
                    queryset = queryset.filter(project=project)
                except Project.DoesNotExist:
                    return f"Project with UUID {project_uuid} not found."
            
            if parent_id is not None:
                queryset = queryset.filter(parent_id=parent_id)
            
            if user_id:
                # Filter by user access - this would need to be implemented based on your permission model
                # For now, we'll get files uploaded by the user or shared with them
                from django.db import models
                queryset = queryset.filter(
                    models.Q(uploaded_by_id=user_id) |
                    models.Q(shared_with_users__id=user_id) |
                    models.Q(project__owner_id=user_id) |
                    models.Q(project__members__id=user_id) |
                    models.Q(project__team__members__id=user_id) |
                    models.Q(project__shared_with_teams__members__id=user_id)
                ).distinct()
            
            # Apply limit and order
            files = queryset.order_by('-created_at')[:limit]
            
            if not files:
                return "No vault files found."
            
            result = f"Found {len(files)} vault file(s):\n\n"
            for file in files:
                file_type = "📁" if file.is_folder else "📄"
                filename = file.original_filename or (file.file.name.split('/')[-1] if file.file else 'Unknown')
                result += f"{file_type} {filename}\n"
                result += f"   ID: {file.id}\n"
                result += f"   Size: {file.size or 'Unknown'} bytes\n"
                result += f"   Type: {file.type or 'Unknown'}\n"
                result += f"   Uploaded: {file.created_at.strftime('%Y-%m-%d %H:%M') if file.created_at else 'Unknown'}\n"
                if file.project:
                    result += f"   Project: {file.project.name} ({file.project.uuid})\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            error_msg = f"Error fetching vault files: {e}"
            logger.error(error_msg)
            return error_msg

    def get_vault_file_by_id(self, file_id: int) -> str:
        """
        Get details of a specific vault file by ID.
        
        Args:
            file_id: The ID of the vault file to retrieve
        
        Returns:
            Formatted string containing the file details
        """
        try:
            VaultFile = self._get_vault_file_model()
            
            try:
                file_obj = VaultFile.objects.get(id=file_id)
            except VaultFile.DoesNotExist:
                return f"Vault file with ID {file_id} not found."
            
            # Format the response
            result = f"Vault File Details:\n\n"
            result += f"ID: {file_obj.id}\n"
            filename = file_obj.original_filename or (file_obj.file.name.split('/')[-1] if file_obj.file else 'Unknown')
            result += f"Filename: {filename}\n"
            result += f"Size: {file_obj.size or 'Unknown'} bytes\n"
            result += f"Type: {file_obj.type or 'Unknown'}\n"
            result += f"Is Folder: {file_obj.is_folder}\n"
            result += f"Uploaded By: {file_obj.uploaded_by.username if file_obj.uploaded_by else 'Unknown'}\n"
            result += f"Created: {file_obj.created_at.strftime('%Y-%m-%d %H:%M') if file_obj.created_at else 'Unknown'}\n"
            result += f"Updated: {file_obj.updated_at.strftime('%Y-%m-%d %H:%M') if file_obj.updated_at else 'Unknown'}\n"
            
            if file_obj.project:
                result += f"Project: {file_obj.project.name} ({file_obj.project.uuid})\n"
            if file_obj.team:
                result += f"Team: {file_obj.team.name}\n"
            
            return result
            
        except Exception as e:
            error_msg = f"Error fetching vault file {file_id}: {e}"
            logger.error(error_msg)
            return error_msg

    def get_vault_file_content(
        self, 
        file_id: int, 
        max_chars: int = 20000
    ) -> str:
        """
        Get the content of a vault file by ID.
        This will read the file content directly from storage.
        
        Args:
            file_id: The ID of the vault file to read
            max_chars: Maximum number of characters to return (default: 20000)
        
        Returns:
            String containing the file content
        """
        try:
            VaultFile = self._get_vault_file_model()
            
            try:
                file_obj = VaultFile.objects.get(id=file_id)
            except VaultFile.DoesNotExist:
                return f"Vault file with ID {file_id} not found."
            
            # Check if it's a folder
            if file_obj.is_folder:
                return f"File {file_id} is a folder and cannot be read as content."
            
            # Check if file exists
            if not file_obj.file:
                return f"File {file_id} has no file content."
            
            # Read file content
            try:
                with file_obj.file.open('rb') as f:
                    content = f.read()
            except Exception as e:
                return f"Error reading file {file_id}: {e}"
            
            # Try to decode as text
            try:
                text_content = content.decode('utf-8')
            except UnicodeDecodeError:
                # If it's not text, return a message
                return f"File {file_id} is a binary file and cannot be displayed as text. Size: {len(content)} bytes"
            
            # Truncate if too long
            if len(text_content) > max_chars:
                text_content = text_content[:max_chars] + "\n... [truncated]"
            
            return f"Content of vault file {file_id}:\n\n{text_content}"
            
        except Exception as e:
            error_msg = f"Error reading vault file {file_id}: {e}"
            logger.error(error_msg)
            return error_msg

    def search_vault_files(
        self, 
        query: str, 
        project_uuid: Optional[str] = None,
        limit: int = 20,
        user_id: Optional[int] = None
    ) -> str:
        """
        Search vault files by filename or content.
        
        Args:
            query: Search query string
            project_uuid: Optional project UUID to limit search to specific project
            limit: Maximum number of results to return (default: 20)
            user_id: User ID to filter files for (if not provided, searches all accessible files)
        
        Returns:
            Formatted string containing matching vault files
        """
        try:
            VaultFile = self._get_vault_file_model()
            Project = self._get_project_model()
            
            # Start with base queryset
            queryset = VaultFile.objects.all()
            
            # Apply project filter
            if project_uuid:
                try:
                    project = Project.objects.get(uuid=project_uuid)
                    queryset = queryset.filter(project=project)
                except Project.DoesNotExist:
                    return f"Project with UUID {project_uuid} not found."
            
            # Apply user filter
            if user_id:
                from django.db import models
                queryset = queryset.filter(
                    models.Q(uploaded_by_id=user_id) |
                    models.Q(shared_with_users__id=user_id) |
                    models.Q(project__owner_id=user_id) |
                    models.Q(project__members__id=user_id) |
                    models.Q(project__team__members__id=user_id) |
                    models.Q(project__shared_with_teams__members__id=user_id)
                ).distinct()
            
            # Search by filename (case-insensitive)
            from django.db import models
            queryset = queryset.filter(
                models.Q(original_filename__icontains=query) |
                models.Q(file__icontains=query)
            )
            
            # Apply limit and order
            files = queryset.order_by('-created_at')[:limit]
            
            if not files:
                return f"No vault files found matching query: '{query}'"
            
            result = f"Found {len(files)} vault file(s) matching '{query}':\n\n"
            for file in files:
                file_type = "📁" if file.is_folder else "📄"
                filename = file.original_filename or (file.file.name.split('/')[-1] if file.file else 'Unknown')
                result += f"{file_type} {filename}\n"
                result += f"   ID: {file.id}\n"
                result += f"   Size: {file.size or 'Unknown'} bytes\n"
                result += f"   Type: {file.type or 'Unknown'}\n"
                if file.project:
                    result += f"   Project: {file.project.name} ({file.project.uuid})\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            error_msg = f"Error searching vault files: {e}"
            logger.error(error_msg)
            return error_msg

    def get_folder_contents(
        self, 
        folder_id: int,
        user_id: Optional[int] = None,
        include_subfolders: bool = False
    ) -> str:
        """
        Get the contents of a specific folder (files and subfolders).
        
        Args:
            folder_id: The ID of the folder to get contents for
            user_id: User ID to filter files for (if not provided, returns all accessible files)
            include_subfolders: Whether to include files from subfolders (default: False)
        
        Returns:
            Formatted string containing folder contents
        """

        print("folder_id", folder_id)

        try:
            VaultFile = self._get_vault_file_model()
            
            # First verify the folder exists and is actually a folder
            try:
                folder = VaultFile.objects.get(id=folder_id)
            except VaultFile.DoesNotExist:
                return f"Folder with ID {folder_id} not found."
            
            if not folder.is_folder:
                return f"Item with ID {folder_id} is not a folder (it's a file)."
            
            # Get files and folders in this folder
            queryset = VaultFile.objects.filter(parent_id=folder_id)
            
            # Apply user filter if provided
            if user_id:
                from django.db import models
                queryset = queryset.filter(
                    models.Q(uploaded_by_id=user_id) |
                    models.Q(shared_with_users__id=user_id) |
                    models.Q(project__owner_id=user_id) |
                    models.Q(project__members__id=user_id) |
                    models.Q(project__team__members__id=user_id) |
                    models.Q(project__shared_with_teams__members__id=user_id)
                ).distinct()
            
            # Order by folders first, then files, then by name
            items = queryset.order_by('-is_folder', 'original_filename', 'file')
            
            if not items:
                return f"Folder '{folder.original_filename or 'Root'}' is empty."
            
            # Separate folders and files
            folders = [item for item in items if item.is_folder]
            files = [item for item in items if not item.is_folder]
            
            result = f"Contents of folder '{folder.original_filename or 'Root'}':\n\n"
            
            # Show folders first
            if folders:
                result += "📁 Folders:\n"
                for folder_item in folders:
                    result += f"   📁 {folder_item.original_filename or 'Unnamed Folder'}\n"
                    result += f"      ID: {folder_item.id}\n"
                    result += f"      Created: {folder_item.created_at.strftime('%Y-%m-%d %H:%M') if folder_item.created_at else 'Unknown'}\n"
                    if folder_item.project:
                        result += f"      Project: {folder_item.project.name}\n"
                    result += "\n"
            
            # Show files
            if files:
                result += "📄 Files:\n"
                for file_item in files:
                    filename = file_item.original_filename or (file_item.file.name.split('/')[-1] if file_item.file else 'Unknown')
                    result += f"   📄 {filename}\n"
                    result += f"      ID: {file_item.id}\n"
                    result += f"      Size: {file_item.size or 'Unknown'} bytes\n"
                    result += f"      Type: {file_item.type or 'Unknown'}\n"
                    result += f"      Created: {file_item.created_at.strftime('%Y-%m-%d %H:%M') if file_item.created_at else 'Unknown'}\n"
                    if file_item.project:
                        result += f"      Project: {file_item.project.name}\n"
                    result += "\n"
            
            # Show summary
            total_items = len(items)
            folder_count = len(folders)
            file_count = len(files)
            result += f"Summary: {total_items} items total ({folder_count} folders, {file_count} files)\n"
            
            # If include_subfolders is True, also show contents of subfolders
            if include_subfolders and folders:
                result += "\n" + "="*50 + "\n"
                result += "SUBFOLDER CONTENTS:\n"
                result += "="*50 + "\n"
                
                for folder_item in folders:
                    subfolder_contents = self.get_folder_contents(folder_item.id, user_id, include_subfolders=False)
                    # Remove the header line and add indentation
                    lines = subfolder_contents.split('\n')
                    indented_lines = ['   ' + line for line in lines[1:]]  # Skip first line (header)
                    result += f"\nSubfolder '{folder_item.original_filename or 'Unnamed'}':\n"
                    result += '\n'.join(indented_lines) + "\n"
            
            return result
            
        except Exception as e:
            error_msg = f"Error getting folder contents for folder {folder_id}: {e}"
            logger.error(error_msg)
            return error_msg

    def get_root_folder_contents(
        self, 
        project_uuid: Optional[str] = None,
        user_id: Optional[int] = None,
        include_subfolders: bool = False
    ) -> str:
        """
        Get the contents of the root folder (files and folders with parent_id=0).
        
        Args:
            project_uuid: Optional project UUID to filter files by project
            user_id: User ID to filter files for (if not provided, returns all accessible files)
            include_subfolders: Whether to include files from subfolders (default: False)
        
        Returns:
            Formatted string containing root folder contents
        """
        try:
            VaultFile = self._get_vault_file_model()
            Project = self._get_project_model()
            
            # Start with root level items (parent_id=0)
            queryset = VaultFile.objects.filter(parent_id=0)
            
            # Apply project filter
            if project_uuid:
                try:
                    project = Project.objects.get(uuid=project_uuid)
                    queryset = queryset.filter(project=project)
                except Project.DoesNotExist:
                    return f"Project with UUID {project_uuid} not found."
            
            # Apply user filter if provided
            if user_id:
                from django.db import models
                queryset = queryset.filter(
                    models.Q(uploaded_by_id=user_id) |
                    models.Q(shared_with_users__id=user_id) |
                    models.Q(project__owner_id=user_id) |
                    models.Q(project__members__id=user_id) |
                    models.Q(project__team__members__id=user_id) |
                    models.Q(project__shared_with_teams__members__id=user_id)
                ).distinct()
            
            # Order by folders first, then files, then by name
            items = queryset.order_by('-is_folder', 'original_filename', 'file')
            
            if not items:
                project_name = f" in project '{project.name}'" if project_uuid else ""
                return f"Root folder{project_name} is empty."
            
            # Separate folders and files
            folders = [item for item in items if item.is_folder]
            files = [item for item in items if not item.is_folder]
            
            project_name = f" in project '{project.name}'" if project_uuid else ""
            result = f"Root folder contents{project_name}:\n\n"
            
            # Show folders first
            if folders:
                result += "📁 Folders:\n"
                for folder_item in folders:
                    result += f"   📁 {folder_item.original_filename or 'Unnamed Folder'}\n"
                    result += f"      ID: {folder_item.id}\n"
                    result += f"      Created: {folder_item.created_at.strftime('%Y-%m-%d %H:%M') if folder_item.created_at else 'Unknown'}\n"
                    if folder_item.project:
                        result += f"      Project: {folder_item.project.name}\n"
                    result += "\n"
            
            # Show files
            if files:
                result += "📄 Files:\n"
                for file_item in files:
                    filename = file_item.original_filename or (file_item.file.name.split('/')[-1] if file_item.file else 'Unknown')
                    result += f"   📄 {filename}\n"
                    result += f"      ID: {file_item.id}\n"
                    result += f"      Size: {file_item.size or 'Unknown'} bytes\n"
                    result += f"      Type: {file_item.type or 'Unknown'}\n"
                    result += f"      Created: {file_item.created_at.strftime('%Y-%m-%d %H:%M') if file_item.created_at else 'Unknown'}\n"
                    if file_item.project:
                        result += f"      Project: {file_item.project.name}\n"
                    result += "\n"
            
            # Show summary
            total_items = len(items)
            folder_count = len(folders)
            file_count = len(files)
            result += f"Summary: {total_items} items total ({folder_count} folders, {file_count} files)\n"
            
            # If include_subfolders is True, also show contents of subfolders
            if include_subfolders and folders:
                result += "\n" + "="*50 + "\n"
                result += "SUBFOLDER CONTENTS:\n"
                result += "="*50 + "\n"
                
                for folder_item in folders:
                    subfolder_contents = self.get_folder_contents(folder_item.id, user_id, include_subfolders=False)
                    # Remove the header line and add indentation
                    lines = subfolder_contents.split('\n')
                    indented_lines = ['   ' + line for line in lines[1:]]  # Skip first line (header)
                    result += f"\nSubfolder '{folder_item.original_filename or 'Unnamed'}':\n"
                    result += '\n'.join(indented_lines) + "\n"
            
            return result
            
        except Exception as e:
            error_msg = f"Error getting root folder contents: {e}"
            logger.error(error_msg)
            return error_msg
