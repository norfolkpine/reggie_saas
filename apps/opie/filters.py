"""
Custom filters for the file manager interface.
Handles multi-model filtering for Files and Collections.

Usage Examples:
# Search for files and folders containing "report"
GET /opie/api/v1/files/?file_manager=true&search=report

# Show only folders, sorted by date
GET /opie/api/v1/files/?file_manager=true&type=folder&sort=date&sort_order=desc

# Show only ingested files, sorted by size
GET /opie/api/v1/files/?file_manager=true&type=files&status=ingested&sort=size

# Show processing files, sorted by name
GET /opie/api/v1/files/?file_manager=true&status=processing&sort=name
"""
from django.db.models import Q


class FileManagerFilter:
    """
    Custom filter class for file manager mode that handles filtering
    across both Files and Collections models.
    """
    
    def __init__(self, request):
        self.request = request
        self.params = request.query_params
    
    def apply_filters(self, files_queryset, folders_queryset):
        """
        Apply all filters to both querysets.
        
        Args:
            files_queryset: QuerySet of File objects
            folders_queryset: QuerySet of Collection objects
            
        Returns:
            tuple: (filtered_files_queryset, filtered_folders_queryset)
        """
        files_queryset, folders_queryset = self._apply_search_filter(files_queryset, folders_queryset)
        files_queryset, folders_queryset = self._apply_type_filter(files_queryset, folders_queryset)
        files_queryset = self._apply_status_filter(files_queryset)
        return files_queryset, folders_queryset
    
    def _apply_search_filter(self, files_queryset, folders_queryset):
        """Apply search filter to both files and folders."""
        search = self.params.get("search", "").strip()
        if search:
            files_queryset = files_queryset.filter(title__icontains=search)
            folders_queryset = folders_queryset.filter(name__icontains=search)
        return files_queryset, folders_queryset
    
    def _apply_type_filter(self, files_queryset, folders_queryset):
        """Apply type filter to show only files or only folders."""
        type_filter = self.params.get("type", "").strip().lower()
        if type_filter == "folder":
            # Only show folders, hide files
            files_queryset = files_queryset.none()
        elif type_filter == "files":
            # Only show files, hide folders
            folders_queryset = folders_queryset.none()
        return files_queryset, folders_queryset
    
    def _apply_status_filter(self, files_queryset):
        """Apply status filter to files only (folders don't have ingestion status)."""
        status_filter = self.params.get("status", "").strip().lower()
        if not status_filter:
            return files_queryset
        
        status_mapping = {
            "ingested": {"is_ingested": True},
            "not_ingested": {"is_ingested": False},
            "processing": {"fileknowledgebaselink__ingestion_status": "processing"},
            "failed": {"fileknowledgebaselink__ingestion_status": "failed"},
        }
        
        if status_filter in status_mapping:
            filter_kwargs = status_mapping[status_filter]
            if "fileknowledgebaselink" in filter_kwargs:
                # Handle related field filtering with distinct to avoid duplicates
                files_queryset = files_queryset.filter(**filter_kwargs).distinct()
            else:
                files_queryset = files_queryset.filter(**filter_kwargs)
        
        return files_queryset


class FileManagerSorter:
    """
    Custom sorter class for file manager mode that handles sorting
    across both Files and Collections models.
    """
    
    def __init__(self, request):
        self.request = request
        self.params = request.query_params
    
    def apply_sorting(self, folders_data, files_data):
        """
        Apply sorting to serialized data for both folders and files.
        
        Args:
            folders_data: List of serialized Collection data
            files_data: List of serialized File data
            
        Returns:
            tuple: (sorted_folders_data, sorted_files_data)
        """
        sort_by = self.params.get("sort", "name").strip().lower()
        sort_order = self.params.get("sort_order", "asc").strip().lower()
        reverse = sort_order == "desc"
        
        if sort_by == "date":
            folders_data.sort(key=lambda x: x.get("created_at", ""), reverse=reverse)
            files_data.sort(key=lambda x: x.get("created_at", ""), reverse=reverse)
        elif sort_by == "size":
            # Sort files by size, folders by name (folders don't have size)
            folders_data.sort(key=lambda x: x.get("name", ""), reverse=reverse)
            files_data.sort(key=lambda x: x.get("file_size", 0), reverse=reverse)
        elif sort_by == "status":
            # Sort files by ingestion status, folders by name
            folders_data.sort(key=lambda x: x.get("name", ""), reverse=reverse)
            files_data.sort(key=lambda x: x.get("is_ingested", False), reverse=reverse)
        elif sort_by == "type":
            # Sort files by file type, folders by name
            folders_data.sort(key=lambda x: x.get("name", ""), reverse=reverse)
            files_data.sort(key=lambda x: x.get("file_type", ""), reverse=reverse)
        else:  # Default: sort by name
            folders_data.sort(key=lambda x: x.get("name", ""), reverse=reverse)
            files_data.sort(key=lambda x: x.get("title", ""), reverse=reverse)
        
        return folders_data, files_data
