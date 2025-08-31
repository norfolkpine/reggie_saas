import json
import logging
import mimetypes
import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.app_integrations.models import ConnectedApp, SupportedApp
from apps.reggie.models import Collection, File as ReggieFile
from apps.teams.models import Team
from apps.users.models import CustomUser

logger = logging.getLogger(__name__)

# Google Drive MIME types
GOOGLE_DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SUPPORTED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/json": "json",
    "application/vnd.google-apps.document": "gdoc",
    "application/vnd.google-apps.spreadsheet": "gsheet",
    "application/vnd.google-apps.presentation": "gslides",
}

class GoogleDriveSync:
    """Google Drive sync service that mirrors folder structure and files into collections"""
    
    def __init__(self, user: CustomUser, team: Optional[Team] = None):
        self.user = user
        self.team = team
        self.access_token = None
        self.sync_stats = {
            "collections_created": 0,
            "files_downloaded": 0,
            "files_skipped": 0,
            "errors": [],
            "start_time": timezone.now(),
        }
        
    def authenticate(self) -> bool:
        """Get valid Google Drive access token"""
        try:
            google_drive_app = SupportedApp.objects.get(key="google_drive")
            creds = ConnectedApp.objects.get(user=self.user, app_id=google_drive_app.id)
            self.access_token = creds.get_valid_token()
            return True
        except Exception as e:
            self.sync_stats["errors"].append(f"Authentication failed: {str(e)}")
            return False
    
    def get_google_drive_files(self, folder_id: Optional[str] = None, page_token: Optional[str] = None) -> Dict:
        """Fetch files and folders from Google Drive"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {
            "pageSize": 1000,
            "fields": "nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, size, parents, webViewLink)",
            "spaces": "drive",
        }
        
        if folder_id:
            params["q"] = f"'{folder_id}' in parents"
        else:
            params["q"] = "trashed=false"
            
        if page_token:
            params["pageToken"] = page_token
            
        try:
            response = requests.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.sync_stats["errors"].append(f"Failed to fetch Google Drive files: {str(e)}")
            return {"files": [], "nextPageToken": None}
    
    def download_file(self, file_id: str, filename: str) -> Optional[ContentFile]:
        """Download a file from Google Drive"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            response = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                headers=headers,
                stream=True,
                timeout=60,
            )
            response.raise_for_status()
            
            # Read content into memory
            content = response.content
            return ContentFile(content, name=filename)
            
        except requests.RequestException as e:
            self.sync_stats["errors"].append(f"Failed to download {filename}: {str(e)}")
            return None
    
    def get_or_create_collection(self, name: str, parent: Optional[Collection] = None, 
                                collection_type: str = "folder") -> Collection:
        """Get or create a collection, maintaining hierarchy"""
        collection, created = Collection.objects.get_or_create(
            name=name,
            parent=parent,
            defaults={
                "description": f"Synced from Google Drive: {name}",
                "collection_type": collection_type,
                "created_at": timezone.now(),
            }
        )
        
        if created:
            self.sync_stats["collections_created"] += 1
            logger.info(f"Created collection: {name}")
            
        return collection
    
    def get_file_type_from_mime(self, mime_type: str) -> str:
        """Map Google Drive MIME type to file type"""
        return SUPPORTED_MIME_TYPES.get(mime_type, "other")
    
    def should_sync_file(self, mime_type: str, size: Optional[int] = None) -> bool:
        """Determine if a file should be synced"""
        # Skip Google Apps files that can't be downloaded as regular files
        if mime_type.startswith("application/vnd.google-apps."):
            return False
            
        # Skip unsupported file types
        if mime_type not in SUPPORTED_MIME_TYPES:
            return False
            
        # Skip very large files (optional size limit)
        if size and size > 100 * 1024 * 1024:  # 100MB limit
            return False
            
        return True
    
    def sync_file(self, file_data: Dict, collection: Optional[Collection] = None) -> bool:
        """Sync a single file from Google Drive"""
        file_id = file_data["id"]
        name = file_data["name"]
        mime_type = file_data["mimeType"]
        size = file_data.get("size")
        
        # Check if file should be synced
        if not self.should_sync_file(mime_type, size):
            self.sync_stats["files_skipped"] += 1
            logger.info(f"Skipping file: {name} (type: {mime_type})")
            return False
        
        # Check if file already exists (by name and collection)
        existing_file = ReggieFile.objects.filter(
            title=name,
            collection=collection,
            uploaded_by=self.user
        ).first()
        
        if existing_file:
            logger.info(f"File already exists: {name}")
            return True
        
        # Download file from Google Drive
        content_file = self.download_file(file_id, name)
        if not content_file:
            return False
        
        try:
            # Create file record
            file_obj = ReggieFile.objects.create(
                title=name,
                description=f"Synced from Google Drive: {name}",
                file=content_file,
                file_type=self.get_file_type_from_mime(mime_type),
                uploaded_by=self.user,
                team=self.team,
                collection=collection,
                collection_order=0,
                filesize=len(content_file),
            )
            
            self.sync_stats["files_downloaded"] += 1
            logger.info(f"Successfully synced file: {name}")
            return True
            
        except Exception as e:
            self.sync_stats["errors"].append(f"Failed to create file {name}: {str(e)}")
            return False
    
    def sync_folder_structure(self, folder_id: Optional[str] = None, 
                             parent_collection: Optional[Collection] = None,
                             depth: int = 0, max_depth: int = 10) -> None:
        """Recursively sync folder structure from Google Drive"""
        if depth > max_depth:
            logger.warning(f"Max depth reached: {max_depth}")
            return
        
        # Get files and folders from Google Drive
        drive_data = self.get_google_drive_files(folder_id)
        files = drive_data.get("files", [])
        
        # Separate folders and files
        folders = [f for f in files if f["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME_TYPE]
        regular_files = [f for f in files if f["mimeType"] != GOOGLE_DRIVE_FOLDER_MIME_TYPE]
        
        # Process folders first (to maintain hierarchy)
        for folder_data in folders:
            folder_name = folder_data["name"]
            folder_id = folder_data["id"]
            
            # Create or get collection for this folder
            collection = self.get_or_create_collection(
                name=folder_name,
                parent=parent_collection,
                collection_type="folder"
            )
            
            # Recursively sync subfolder
            self.sync_folder_structure(
                folder_id=folder_id,
                parent_collection=collection,
                depth=depth + 1,
                max_depth=max_depth
            )
        
        # Process files in current folder
        for file_data in regular_files:
            self.sync_file(file_data, parent_collection)
    
    def sync_all(self, root_folder_id: Optional[str] = None, max_depth: int = 10) -> Dict:
        """Main sync method - syncs entire Google Drive or specific folder"""
        if not self.authenticate():
            return self.sync_stats
        
        logger.info(f"Starting Google Drive sync for user: {self.user.email}")
        
        try:
            # Start sync from root or specified folder
            self.sync_folder_structure(
                folder_id=root_folder_id,
                parent_collection=None,
                depth=0,
                max_depth=max_depth
            )
            
            self.sync_stats["end_time"] = timezone.now()
            duration = self.sync_stats["end_time"] - self.sync_stats["start_time"]
            self.sync_stats["duration_seconds"] = duration.total_seconds()
            
            logger.info(f"Google Drive sync completed. Stats: {self.sync_stats}")
            
        except Exception as e:
            self.sync_stats["errors"].append(f"Sync failed: {str(e)}")
            logger.error(f"Google Drive sync failed: {str(e)}")
        
        return self.sync_stats


# API Views
@extend_schema(
    tags=["Google Drive Sync"],
    summary="Start Google Drive sync",
    description="Sync files and folders from Google Drive into the hierarchical collections system",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "root_folder_id": {
                    "type": "string",
                    "description": "Optional: Google Drive folder ID to start sync from. If not provided, syncs entire drive."
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum folder depth to sync (default: 10)",
                    "default": 10
                },
                "team_id": {
                    "type": "integer",
                    "description": "Optional: Team ID to associate synced files with"
                }
            }
        }
    },
    responses={
        200: {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "sync_stats": {
                    "type": "object",
                    "properties": {
                        "collections_created": {"type": "integer"},
                        "files_downloaded": {"type": "integer"},
                        "files_skipped": {"type": "integer"},
                        "errors": {"type": "array", "items": {"type": "string"}},
                        "duration_seconds": {"type": "number"}
                    }
                }
            }
        },
        400: {"type": "object", "properties": {"error": {"type": "string"}}},
        401: {"type": "object", "properties": {"error": {"type": "string"}}}
    }
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_google_drive_sync(request):
    """Start Google Drive sync process"""
    try:
        root_folder_id = request.data.get("root_folder_id")
        max_depth = int(request.data.get("max_depth", 10))
        team_id = request.data.get("team_id")
        
        # Validate max_depth
        if max_depth < 1 or max_depth > 20:
            return Response(
                {"error": "max_depth must be between 1 and 20"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get team if specified
        team = None
        if team_id:
            try:
                team = Team.objects.get(id=team_id)
                # Check if user has access to this team
                if not team.members.filter(id=request.user.id).exists():
                    return Response(
                        {"error": "You don't have access to this team"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            except Team.DoesNotExist:
                return Response(
                    {"error": "Team not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Start sync process
        sync_service = GoogleDriveSync(user=request.user, team=team)
        sync_stats = sync_service.sync_all(
            root_folder_id=root_folder_id,
            max_depth=max_depth
        )
        
        return Response({
            "message": "Google Drive sync completed successfully",
            "sync_stats": sync_stats
        })
        
    except Exception as e:
        logger.error(f"Google Drive sync failed: {str(e)}")
        return Response(
            {"error": f"Sync failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=["Google Drive Sync"],
    summary="Get Google Drive folder structure",
    description="Preview the folder structure that would be synced without actually downloading files",
    parameters=[
        {
            "name": "folder_id",
            "in": "query",
            "description": "Google Drive folder ID to explore",
            "required": False,
            "schema": {"type": "string"}
        },
        {
            "name": "max_depth",
            "in": "query",
            "description": "Maximum depth to explore",
            "required": False,
            "schema": {"type": "integer", "default": 5}
        }
    ],
    responses={
        200: {
            "type": "object",
            "properties": {
                "folder_structure": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "children": {"type": "array"}
                    }
                },
                "file_count": {"type": "integer"},
                "folder_count": {"type": "integer"}
            }
        },
        401: {"type": "object", "properties": {"error": {"type": "string"}}}
    }
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def preview_google_drive_structure(request):
    """Preview Google Drive folder structure without syncing"""
    try:
        folder_id = request.query_params.get("folder_id")
        max_depth = int(request.query_params.get("max_depth", 5))
        
        # Validate max_depth
        if max_depth < 1 or max_depth > 10:
            return Response(
                {"error": "max_depth must be between 1 and 10"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Authenticate
        sync_service = GoogleDriveSync(user=request.user)
        if not sync_service.authenticate():
            return Response(
                {"error": "Google Drive not connected"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Get folder structure
        def explore_folder(folder_id: Optional[str], depth: int = 0) -> Dict:
            if depth > max_depth:
                return {"name": "...", "type": "truncated"}
            
            drive_data = sync_service.get_google_drive_files(folder_id)
            files = drive_data.get("files", [])
            
            folders = [f for f in files if f["mimeType"] == GOOGLE_DRIVE_FOLDER_MIME_TYPE]
            regular_files = [f for f in files if f["mimeType"] != GOOGLE_DRIVE_FOLDER_MIME_TYPE]
            
            children = []
            
            # Add folders
            for folder in folders:
                children.append(explore_folder(folder["id"], depth + 1))
            
            # Add files (just names, not full details)
            for file in regular_files:
                children.append({
                    "name": file["name"],
                    "type": "file",
                    "mime_type": file["mimeType"],
                    "size": file.get("size")
                })
            
            return {
                "name": "Root" if folder_id is None else "Folder",
                "type": "folder",
                "children": children
            }
        
        structure = explore_folder(folder_id)
        
        # Count files and folders
        def count_items(item: Dict) -> Tuple[int, int]:
            file_count = 0
            folder_count = 0
            
            if item["type"] == "file":
                file_count = 1
            elif item["type"] == "folder":
                folder_count = 1
                for child in item.get("children", []):
                    f_count, fol_count = count_items(child)
                    file_count += f_count
                    folder_count += fol_count
            
            return file_count, folder_count
        
        file_count, folder_count = count_items(structure)
        
        return Response({
            "folder_structure": structure,
            "file_count": file_count,
            "folder_count": folder_count
        })
        
    except Exception as e:
        logger.error(f"Failed to preview Google Drive structure: {str(e)}")
        return Response(
            {"error": f"Preview failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@extend_schema(
    tags=["Google Drive Sync"],
    summary="Get sync status and history",
    description="Get information about previous sync operations and current status",
    responses={
        200: {
            "type": "object",
            "properties": {
                "last_sync": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string", "format": "date-time"},
                        "status": {"type": "string"},
                        "stats": {"type": "object"}
                    }
                },
                "connected_status": {"type": "boolean"},
                "total_synced_files": {"type": "integer"},
                "total_synced_collections": {"type": "integer"}
            }
        }
    }
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_sync_status(request):
    """Get Google Drive sync status and statistics"""
    try:
        # Check connection status
        try:
            google_drive_app = SupportedApp.objects.get(key="google_drive")
            connected_app = ConnectedApp.objects.get(user=request.user, app_id=google_drive_app.id)
            connected_status = True
            last_sync_time = connected_app.updated_at
        except (SupportedApp.DoesNotExist, ConnectedApp.DoesNotExist):
            connected_status = False
            last_sync_time = None
        
        # Count synced files and collections
        synced_files = ReggieFile.objects.filter(
            uploaded_by=request.user,
            description__icontains="Synced from Google Drive"
        ).count()
        
        synced_collections = Collection.objects.filter(
            description__icontains="Synced from Google Drive"
        ).count()
        
        return Response({
            "connected_status": connected_status,
            "last_sync": {
                "timestamp": last_sync_time,
                "status": "connected" if connected_status else "disconnected"
            },
            "total_synced_files": synced_files,
            "total_synced_collections": synced_collections
        })
        
    except Exception as e:
        logger.error(f"Failed to get sync status: {str(e)}")
        return Response(
            {"error": f"Failed to get status: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

