# === Standard Library ===
import json
import logging
import re
import time

# from datetime import timezone
import requests

# === Agno ===
from agno.agent import Agent
from agno.knowledge.pdf_url import PDFUrlKnowledgeBase
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.slack import SlackTools
from agno.vectordb.pgvector import PgVector
from asgiref.sync import sync_to_async
from django.conf import settings

# === Django ===
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

# === DRF Spectacular ===
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

# === Django REST Framework ===
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from slack_sdk import WebClient

from apps.reggie.agents.helpers.agent_helpers import get_schema
from apps.reggie.utils.gcs_utils import ingest_single_file
from apps.reggie.utils.token_usage import create_token_usage_record
from apps.slack_integration.models import SlackWorkspace

# === External SDKs ===
from .agents.agent_builder import AgentBuilder  # Adjust path if needed

# === Local ===
from .models import Agent as DjangoAgent  # avoid conflict with agno.Agent
from .models import (
    AgentExpectedOutput,
    AgentInstruction,
    Category,
    ChatSession,
    Collection,
    EphemeralFile,
    File,
    FileKnowledgeBaseLink,
    FileTag,
    KnowledgeBase,
    KnowledgeBasePdfURL,
    ModelProvider,
    Project,
    StorageBucket,
    ProjectInstruction,
    Tag,
    UserFeedback,
    VaultFile,
    TokenUsage,
    UserTokenSummary,
    TeamTokenSummary,
)
from .permissions import HasValidSystemAPIKey
from .serializers import (
    AgentExpectedOutputSerializer,
    AgentInstructionSerializer,
    AgentInstructionsResponseSerializer,
    AgentSerializer,
    CategorySerializer,
    ChatSessionSerializer,
    CollectionDetailSerializer,
    CollectionSerializer,
    FileIngestSerializer,
    FileKnowledgeBaseLinkSerializer,
    FileSerializer,
    FileTagSerializer,
    GlobalTemplatesResponseSerializer,
    KnowledgeBasePdfURLSerializer,
    KnowledgeBaseSerializer,
    ModelProviderSerializer,
    ProjectInstructionSerializer,
    ProjectSerializer,
    StorageBucketSerializer,
    StreamAgentRequestSerializer,
    TagSerializer,
    UploadFileResponseSerializer,
    UploadFileSerializer,
    UserFeedbackSerializer,
    VaultFileSerializer,
    TokenUsageSerializer,
    UserTokenSummarySerializer
)
from .tasks import dispatch_ingestion_jobs_from_batch
from .filters import FileManagerFilter, FileManagerSorter


class AsyncStreamingHttpResponse(StreamingHttpResponse):
    """Async version of StreamingHttpResponse for ASGI."""

    async def __aiter__(self):
        for part in self.streaming_content:
            yield part


class AsyncIteratorWrapper:
    """Wrapper to convert a sync iterator to an async iterator."""

    def __init__(self, sync_iterator):
        self.sync_iterator = sync_iterator

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            # Run the iterator's next method in a thread pool
            item = await sync_to_async(next)(self.sync_iterator)
            return item
        except StopIteration:
            raise StopAsyncIteration from None


logger = logging.getLogger(__name__)


class UserFeedbackViewSet(viewsets.ModelViewSet):
    """
    API endpoint for submitting and viewing user feedback on chat sessions.
    """

    queryset = UserFeedback.objects.all().order_by("-created_at")
    serializer_class = UserFeedbackSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema(tags=["Health"])
@api_view(["GET"])
def health_check(request):
    """
    Simple health check endpoint to verify the API is running.
    """
    return Response({"status": "healthy"}, status=status.HTTP_200_OK)


@extend_schema(tags=["Agents"])
class AgentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing agents.
    Returns:
    - All agents if superuser
    - User's agents + global agents for regular users
    """

    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return DjangoAgent.objects.all()
        return DjangoAgent.objects.filter(Q(user=user) | Q(is_global=True))

    # --- Caching Helpers ---
    CACHE_TTL = 300  # seconds

    def _agent_list_cache_key(self, request):
        return f"agents:list:{request.user.id}"

    def _agent_detail_cache_key(self, pk):
        return f"agent:{pk}"

    def list(self, request, *args, **kwargs):
        # Only cache unfiltered first-page requests
        if request.query_params:
            return super().list(request, *args, **kwargs)

        cache_key = self._agent_list_cache_key(request)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, self.CACHE_TTL)
        return response

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get(self.lookup_field or "pk")
        cache_key = self._agent_detail_cache_key(pk)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        response = super().retrieve(request, *args, **kwargs)
        cache.set(cache_key, response.data, self.CACHE_TTL)
        return response

    # Invalidate cache on write operations
    def _invalidate_cache(self, instance=None):
        cache.delete(self._agent_list_cache_key(self.request))
        if instance:
            cache.delete(self._agent_detail_cache_key(instance.pk))

    def perform_create(self, serializer):
        instance = serializer.save()
        self._invalidate_cache(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._invalidate_cache(instance)

    def perform_destroy(self, instance):
        self._invalidate_cache(instance)
        super().perform_destroy(instance)


@extend_schema(
    tags=["Agents"], responses={200: AgentInstructionsResponseSerializer, 404: AgentInstructionsResponseSerializer}
)
@api_view(["GET"])
def get_agent_instructions(request, agent_id):
    """Fetch the instruction assigned directly to the agent (if enabled)."""
    try:
        agent = DjangoAgent.objects.get(id=agent_id)
    except DjangoAgent.DoesNotExist:
        return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

    if agent.instructions and agent.instructions.is_enabled:
        serializer = AgentInstructionSerializer(agent.instructions)
        return Response(serializer.data, status=status.HTTP_200_OK)

    return Response({"error": "No enabled instruction assigned to this agent."}, status=404)


@extend_schema(
    methods=["GET"],
    tags=["Agents"],
    responses=AgentExpectedOutputSerializer,  # or your correct serializer
)
def get_agent_expected_output(request, agent_id):
    """Fetch the specific expected output assigned to the agent."""
    try:
        agent = DjangoAgent.objects.get(id=agent_id)
    except DjangoAgent.DoesNotExist:
        return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

    if agent.expected_output and agent.expected_output.is_enabled:
        serializer = AgentExpectedOutputSerializer(agent.expected_output)
        return Response(serializer.data, status=status.HTTP_200_OK)

    return Response({"error": "No enabled expected output assigned to this agent."}, status=404)


@extend_schema(tags=["Agent Templates"], responses={200: GlobalTemplatesResponseSerializer})
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_global_templates(request):
    """
    Returns global instruction templates and expected output templates.
    """
    instructions = AgentInstruction.objects.filter(is_enabled=True, is_global=True)
    outputs = AgentExpectedOutput.objects.filter(is_enabled=True, is_global=True)

    response_data = {
        "instructions": AgentInstructionSerializer(instructions, many=True).data,
        "expected_outputs": AgentExpectedOutputSerializer(outputs, many=True).data,
    }
    return Response(response_data)


@extend_schema(tags=["Agent Instructions"])
class AgentInstructionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing agent instructions.
    """

    serializer_class = AgentInstructionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return AgentInstruction.objects.all()
        return AgentInstruction.objects.filter(Q(is_global=True) | Q(user=user))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # maybe add update for viewing instructions in team


@extend_schema(tags=["Agent Expected Output"])
class AgentExpectedOutputViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing agent expected outputs.
    """

    queryset = AgentExpectedOutput.objects.all()
    serializer_class = AgentExpectedOutputSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema(tags=["Storage Buckets"])
class StorageBucketViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing storage buckets.
    """

    queryset = StorageBucket.objects.all()
    serializer_class = StorageBucketSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema(tags=["Knowledge Bases"])
class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    """
    API endpoint that allows managing knowledge bases.
    """

    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=["post"], url_path="share-to-teams")
    def share_to_teams(self, request, pk=None):
        """
        Share this knowledge base with other teams by adding team IDs.
        Only the owner (uploaded_by) or a superuser can share.
        """
        kb = self.get_object()
        user = request.user
        if not (user.is_superuser or kb.uploaded_by == user):
            return Response({"error": "You do not have permission to share this knowledge base."}, status=403)

        from .serializers import KnowledgeBaseShareSerializer

        serializer = KnowledgeBaseShareSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        teams_data = serializer.validated_data["teams"]
        # Remove all current permissions before adding new ones
        from .models import KnowledgeBasePermission

        KnowledgeBasePermission.objects.filter(knowledge_base=kb).delete()
        from apps.teams.models import Team

        added_teams = []
        errors = []
        team_ids = [entry["team_id"] for entry in teams_data]
        team_objs = Team.objects.filter(pk__in=team_ids)
        team_map = {team.pk: team for team in team_objs}
        for entry in teams_data:
            team_id = entry["team_id"]
            role = entry["role"]
            team = team_map.get(team_id)
            if team:
                KnowledgeBasePermission.objects.create(knowledge_base=kb, team=team, role=role, created_by=user)
                added_teams.append({"team_id": team_id, "role": role})
            else:
                errors.append(f"Team {team_id} does not exist.")
        kb.save()
        return Response({"message": "Knowledge base shared.", "added_teams": added_teams, "errors": errors})

    def get_queryset(self):
        user = self.request.user
        print(user)
        print(user.teams)
        print(user.is_superuser)
        if user.is_superuser:
            return KnowledgeBase.objects.all()
        user_teams = getattr(user, "teams", None)
        if user_teams is not None:
            return KnowledgeBase.objects.filter(
                models.Q(uploaded_by=user) | models.Q(permission_links__team__in=user.teams.all())
            ).distinct()
        return KnowledgeBase.objects.filter(uploaded_by=user)

    def perform_create(self, serializer):
        # Only use serializer's permissions logic; do not handle legacy 'teams' field
        serializer.save(uploaded_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="file_id",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Optional file UUID to check if it's linked to each knowledge base",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page",
                required=False,
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Total number of items"},
                    "next": {"type": "string", "description": "URL for next page", "nullable": True},
                    "previous": {"type": "string", "description": "URL for previous page", "nullable": True},
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "knowledgebase_id": {"type": "string"},
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "model_provider": {"type": "integer"},
                                "chunk_size": {"type": "integer"},
                                "chunk_overlap": {"type": "integer"},
                                "vector_table_name": {"type": "string"},
                                "created_at": {"type": "string", "format": "date-time"},
                                "updated_at": {"type": "string", "format": "date-time"},
                                "is_file_linked": {"type": "boolean", "nullable": True},
                            },
                        },
                    },
                },
            }
        },
    )
    @extend_schema(
        summary="List files",
        description="List files with optional filename filtering (search) and dynamic pagination size (pageitem).",
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter files by filename (case-insensitive, partial match)",
                required=False,
            ),
            OpenApiParameter(
                name="pageitem",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page (pagination size)",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination",
                required=False,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """List all knowledge bases with optional file linking status."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        summary="List files in knowledge base",
        description=(
            "List all files that have been ingested or are being ingested into this knowledge base.\n\n"
            "Features:\n"
            "- Detailed file metadata\n"
            "- Processing status and progress\n"
            "- Chunking information\n"
            "- Error details if ingestion failed\n\n"
            "The results are paginated and can be filtered by status and search query."
        ),
        parameters=[
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by ingestion status (not_started, processing, completed, failed)",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search files by title or description",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page",
                required=False,
            ),
        ],
        responses={
            200: FileKnowledgeBaseLinkSerializer(many=True),
            404: {"description": "Knowledge base not found"},
        },
    )
    @action(detail=True, methods=["get"], url_path="files")
    def list_files(self, request, pk=None):
        """List all files in the knowledge base with their processing status."""
        try:
            knowledge_base = self.get_object()

            # Get query parameters
            status_filter = request.query_params.get("status")
            search_query = request.query_params.get("search")

            # Start with all links for this knowledge base
            queryset = FileKnowledgeBaseLink.objects.filter(knowledge_base=knowledge_base).select_related("file")

            # Apply status filter if provided
            if status_filter:
                queryset = queryset.filter(ingestion_status=status_filter)

            # Apply search filter if provided
            if search_query:
                queryset = queryset.filter(
                    Q(file__title__icontains=search_query) | Q(file__description__icontains=search_query)
                )

            # Order by most recently updated
            queryset = queryset.order_by("-updated_at")

            # Paginate results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = FileKnowledgeBaseLinkSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = FileKnowledgeBaseLinkSerializer(queryset, many=True)
            return Response(serializer.data)

        except KnowledgeBase.DoesNotExist:
            return Response({"error": "Knowledge base not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Tags"])
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows listing agent categories.
    """

    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class TagViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing tags.
    """

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema(tags=["Projects"])
class ProjectViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing projects.
    """

    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Project.objects.all()
        # user_teams = getattr(user, "teams", None)
        qs = Project.objects.filter(
            models.Q(owner=user)
            | models.Q(members=user)
            | models.Q(team__in=user.teams.all())
            | models.Q(shared_with_teams__in=user.teams.all())
        )
        return qs.distinct()

    # --- Caching Helpers ---
    CACHE_TTL = 300  # seconds

    def _project_list_cache_key(self, request):
        return f"projects:list:{request.user.id}"

    def _project_detail_cache_key(self, uuid):
        return f"project:{uuid}"

    def list(self, request, *args, **kwargs):
        if request.query_params:
            return super().list(request, *args, **kwargs)
        cache_key = self._project_list_cache_key(request)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, self.CACHE_TTL)
        return response

    def retrieve(self, request, *args, **kwargs):
        uuid = kwargs.get(self.lookup_field or "uuid")
        cache_key = self._project_detail_cache_key(uuid)
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().retrieve(request, *args, **kwargs)
        cache.set(cache_key, response.data, self.CACHE_TTL)
        return response

    def _invalidate_cache(self, instance=None):
        cache.delete(self._project_list_cache_key(self.request))
        if instance:
            cache.delete(self._project_detail_cache_key(instance.uuid))

    def perform_create(self, serializer):
        instance = serializer.save()
        self._invalidate_cache(instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._invalidate_cache(instance)

    def perform_destroy(self, instance):
        self._invalidate_cache(instance)
        super().perform_destroy(instance)


@extend_schema(tags=["Files"])
class VaultFileViewSet(viewsets.ModelViewSet):
    queryset = VaultFile.objects.all()
    serializer_class = VaultFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Hybrid: access if user is owner, in file/project members, or in file/project teams
        qs = VaultFile.objects.all()
        return qs.filter(
            models.Q(uploaded_by=user)
            | models.Q(shared_with_users=user)
            | models.Q(shared_with_teams__in=user.teams.all())
            | models.Q(project__owner=user)
            | models.Q(project__members=user)
            | models.Q(project__team__members=user)
            | models.Q(project__shared_with_teams__in=user.teams.all())
        ).distinct()

    from drf_spectacular.utils import extend_schema

    @extend_schema(
        request={"multipart/form-data": VaultFileSerializer},
        summary="Upload a vault file",
        description="Upload a file to the vault. Requires multipart/form-data.",
    )
    def create(self, request, *args, **kwargs):
        # Handle project_uuid field - convert to project instance
        # Create a mutable copy safely without deep copying file objects
        data = {}
        for key, value in request.data.items():
            data[key] = value
        project_uuid = data.get('project_uuid')
        if project_uuid:
            try:
                project = Project.objects.get(uuid=project_uuid)
                data['project'] = project.id
                # Remove project_uuid as it's not a valid field
                data.pop('project_uuid', None)
            except Project.DoesNotExist:
                logger.error(f"Project with UUID {project_uuid} does not exist")
                return Response({"error": f"Project with UUID {project_uuid} does not exist"}, status=400)

        # Handle uploaded_by - ensure it's set to current user if not provided or invalid
        if not data.get('uploaded_by') or str(data.get('uploaded_by')) != str(request.user.id):
            data['uploaded_by'] = request.user.id

        serializer = self.get_serializer(data=data)
        logger.info(f"VaultFile upload request: {data}")
        if not serializer.is_valid():
            logger.error(f"VaultFile upload failed: {serializer.errors}")
            return Response(serializer.errors, status=400)

        # Extract file info
        file_obj = request.FILES.get("file")
        if file_obj:
            serializer.validated_data["size"] = file_obj.size
            serializer.validated_data["type"] = getattr(file_obj, "content_type", None) or file_obj.name.split(".")[-1]
            serializer.validated_data["original_filename"] = file_obj.name

        self.perform_create(serializer)
        
        # Auto-embed file for AI insights (only for actual files, not folders)
        vault_file = serializer.instance
        if not vault_file.is_folder and vault_file.file and vault_file.project:
            try:
                # Use improved embedding approach similar to knowledge base
                self._queue_vault_embedding(vault_file)
            except Exception as e:
                logger.warning(f"Failed to queue vault embedding for file {vault_file.id}: {e}")
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=201, headers=headers)

    def destroy(self, request, *args, **kwargs):
        """Custom delete method that handles recursive folder deletion."""
        vault_file = self.get_object()
        
        # Check if it's a folder and has children
        if vault_file.is_folder:
            children_count = VaultFile.objects.filter(parent_id=vault_file.id).count()
            if children_count > 0:
                # Check if force deletion is requested
                force_delete = request.query_params.get('force', '').lower() == 'true'
                if not force_delete:
                    return Response({
                        "error": "Folder contains items",
                        "children_count": children_count,
                        "message": f"This folder contains {children_count} item(s). Add ?force=true to delete all contents."
                    }, status=400)
                
                # Recursively delete all children
                self._delete_folder_recursively(vault_file.id)
        
        # Delete the file/folder itself
        vault_file.delete()
        logger.info(f"Deleted vault file/folder: {vault_file.id} (is_folder: {vault_file.is_folder})")
        
        return Response(status=204)
    
    def _delete_folder_recursively(self, folder_id):
        """Recursively delete all files and subfolders in a folder."""
        children = VaultFile.objects.filter(parent_id=folder_id)
        
        for child in children:
            if child.is_folder:
                # Recursively delete subfolders
                self._delete_folder_recursively(child.id)
            
            # Delete the child (file or empty folder)
            child.delete()
            logger.info(f"Recursively deleted vault item: {child.id} (is_folder: {child.is_folder})")

    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, pk=None):
        """Share this vault file with users or teams."""
        vault_file = self.get_object()
        users = request.data.get("users", [])
        teams = request.data.get("teams", [])
        if users:
            vault_file.shared_with_users.add(*users)
        if teams:
            vault_file.shared_with_teams.add(*teams)
        vault_file.save()
        return Response({"status": "shared"})

    @action(detail=False, methods=["get"], url_path="by-project")
    def by_project(self, request):
        """
        Get all vault files by project UUID and parent_id. 
        Usage: /vault-files/by-project/?project_uuid=<uuid>&parent_id=<id>
        """
        project_uuid = request.query_params.get("project_uuid")
        parent_id = request.query_params.get("parent_id", "0")  # Default to root level (0)
        search = request.query_params.get("search", "")
        
        if not project_uuid:
            return Response({"error": "project_uuid is required as query param"}, status=400)

        try:
            # Convert parent_id to integer
            try:
                parent_id = int(parent_id)
            except (ValueError, TypeError):
                parent_id = 0

            # Filter by project UUID and parent_id
            files = self.get_queryset().filter(
                project__uuid=project_uuid,
                parent_id=parent_id
            )
            
            # Apply search filter if provided
            if search:
                files = files.filter(
                    Q(original_filename__icontains=search) |
                    Q(file__icontains=search)
                )
            
            # Order by folders first, then by name
            files = files.order_by('-is_folder', 'original_filename')

            # Apply pagination if enabled
            page = self.paginate_queryset(files)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            # Return all results if pagination is disabled
            serializer = self.get_serializer(files, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error filtering vault files by project UUID {project_uuid} and parent_id {parent_id}: {e}")
            return Response({"error": "Failed to retrieve vault files"}, status=500)

    @action(detail=False, methods=["post"], url_path="move")
    def move(self, request):
        """
        Move vault files/folders to a different parent folder.
        Handles drag and drop operations in the file manager.
        """
        file_ids = request.data.get("file_ids", [])
        target_folder_id = request.data.get("target_folder_id", 0)
        
        if not file_ids:
            return Response({"error": "file_ids is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Convert target_folder_id to integer
            try:
                target_folder_id = int(target_folder_id)
            except (ValueError, TypeError):
                target_folder_id = 0
            
            # Get files to move
            files_to_move = VaultFile.objects.filter(
                id__in=file_ids
            ).filter(
                # Ensure user has access to these files
                models.Q(uploaded_by=request.user) |
                models.Q(shared_with_users=request.user) |
                models.Q(shared_with_teams__in=request.user.teams.all()) |
                models.Q(project__owner=request.user) |
                models.Q(project__members=request.user) |
                models.Q(project__team__members=request.user)
            ).distinct()
            
            if not files_to_move.exists():
                return Response({"error": "No files found or you don't have permission to move them"}, status=status.HTTP_404_NOT_FOUND)
            
            # If target is not root (0), verify it exists and is a folder
            if target_folder_id > 0:
                try:
                    target_folder = VaultFile.objects.get(
                        id=target_folder_id,
                        is_folder=True
                    )
                    
                    # Ensure user has access to target folder
                    has_access = VaultFile.objects.filter(
                        id=target_folder_id
                    ).filter(
                        models.Q(uploaded_by=request.user) |
                        models.Q(shared_with_users=request.user) |
                        models.Q(shared_with_teams__in=request.user.teams.all()) |
                        models.Q(project__owner=request.user) |
                        models.Q(project__members=request.user) |
                        models.Q(project__team__members=request.user)
                    ).exists()
                    
                    if not has_access:
                        return Response({"error": "You don't have permission to move files to this folder"}, status=status.HTTP_403_FORBIDDEN)
                    
                    # Prevent moving a folder into itself or its children
                    for file_to_move in files_to_move:
                        if file_to_move.is_folder:
                            if file_to_move.id == target_folder_id:
                                return Response({"error": "Cannot move a folder into itself"}, status=status.HTTP_400_BAD_REQUEST)
                            
                            # Check if target is a child of this folder
                            if self._is_child_folder(target_folder_id, file_to_move.id):
                                return Response({"error": "Cannot move a folder into its own child folder"}, status=status.HTTP_400_BAD_REQUEST)
                    
                except VaultFile.DoesNotExist:
                    return Response({"error": "Target folder not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Move the files
            moved_count = 0
            for file_to_move in files_to_move:
                file_to_move.parent_id = target_folder_id
                file_to_move.save()
                moved_count += 1
                logger.info(f"Moved vault file {file_to_move.id} to folder {target_folder_id}")
            
            return Response({
                "success": True,
                "moved_count": moved_count,
                "message": f"Successfully moved {moved_count} item(s)"
            })
            
        except Exception as e:
            logger.error(f"Error moving vault files: {e}")
            return Response({"error": "Failed to move files"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _is_child_folder(self, potential_child_id, parent_id):
        """
        Recursively check if a folder is a child of another folder.
        """
        # Start from the potential child and traverse up the parent chain
        current_id = potential_child_id
        visited = set()  # Prevent infinite loops
        
        while current_id and current_id != 0:
            if current_id in visited:
                # Circular reference detected
                return False
            
            if current_id == parent_id:
                return True
            
            visited.add(current_id)
            
            try:
                current_folder = VaultFile.objects.get(id=current_id)
                current_id = current_folder.parent_id
            except VaultFile.DoesNotExist:
                break
        
        return False

    @action(detail=False, methods=["post"], url_path="ai-insights")
    def ai_insights(self, request):
        """Generate AI insights for vault files based on a question"""
        from .serializers import AiInsightsRequestSerializer
        from .utils.gcs_utils import post_to_cloud_run
        from .models import AiConversation, Project
        import time
        
        request_serializer = AiInsightsRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = request_serializer.validated_data
        
        try:
            project = Project.objects.get(uuid=validated_data['project_uuid'])
            if not (project.owner == request.user or 
                    request.user in project.members.all() or 
                    (project.team and request.user in project.team.members.all())):
                return Response(
                    {"error": "You don't have access to this project"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Convert UUID to string for JSON serialization
            payload = validated_data.copy()
            payload['project_uuid'] = str(payload['project_uuid'])
            
            start_time = time.time()
            ai_response = post_to_cloud_run("/ai-insights", payload, timeout=60)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            AiConversation.objects.create(
                user=request.user,
                project=project,
                folder_id=validated_data.get('parent_id', 0),
                question=validated_data['question'],
                response=ai_response.get('response', ''),
                context_files=validated_data.get('file_ids', []),
                tokens_used=ai_response.get('tokens_used', 0),
                response_time_ms=response_time_ms
            )
            
            ai_response['response_time_ms'] = response_time_ms
            return Response(ai_response, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in AI insights: {e}")
            return Response({"error": "AI service unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(detail=False, methods=["post"], url_path="ai-chat") 
    def ai_chat(self, request):
        """Handle AI chat conversations about vault files"""
        from .serializers import AiChatRequestSerializer
        from .utils.gcs_utils import post_to_cloud_run
        from .models import AiConversation, Project
        import time
        
        request_serializer = AiChatRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = request_serializer.validated_data
        
        try:
            try:
                project = Project.objects.get(uuid=validated_data['project_uuid'])
            except Project.DoesNotExist:
                return Response(
                    {"error": "Project not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            if not (project.owner == request.user or 
                    request.user in project.members.all() or 
                    (project.team and request.user in project.team.members.all())):
                return Response(
                    {"error": "You don't have access to this project"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get conversation history
            recent_conversations = AiConversation.objects.filter(
                user=request.user,
                project=project,
                folder_id=validated_data.get('parent_id', 0)
            ).order_by('-created_at')[:5]
            
            conversation_history = [
                {"question": conv.question, "response": conv.response}
                for conv in reversed(recent_conversations)
            ]
            
            payload = validated_data.copy()
            payload['conversation_history'] = conversation_history
            # Convert UUID to string for JSON serialization
            payload['project_uuid'] = str(payload['project_uuid'])
            
            logger.info(f"Sending AI chat request to Cloud Run. Payload: {payload}")
            start_time = time.time() 
            ai_response = post_to_cloud_run("/ai-chat", payload, timeout=60)
            response_time_ms = int((time.time() - start_time) * 1000)
            
            AiConversation.objects.create(
                user=request.user,
                project=project,
                folder_id=validated_data.get('parent_id', 0),
                question=validated_data['message'],
                response=ai_response.get('response', ''),
                context_files=validated_data.get('file_ids', []),
                tokens_used=ai_response.get('tokens_used', 0),
                response_time_ms=response_time_ms
            )
            
            ai_response['response_time_ms'] = response_time_ms
            return Response(ai_response, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            logger.error(f"Error in AI chat: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response({"error": "AI service unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(detail=False, methods=["post"], url_path="vault-agent-chat")
    def vault_agent_chat(self, request):
        """
        Handle vault AI chat using the Reggie agent with vault vector embeddings.
        This endpoint uses the existing agent system but with vault-specific knowledge base.
        """
        from .serializers import AiChatRequestSerializer
        from .models import Project, Agent as DjangoAgent, ModelProvider
        from agno.vectordb.pgvector import PgVector
        from agno.embedder.openai import OpenAIEmbedder
        from agno.knowledge import AgentKnowledge
        from agno.agent import Agent as AgnoAgent
        from agno.memory import AgentMemory
        from agno.memory.db.postgres import PgMemoryDb
        from agno.storage.agent.postgres import PostgresAgentStorage
        from apps.reggie.agents.helpers.agent_helpers import (
            get_db_url,
            get_schema,
            get_llm_model,
            get_instructions_tuple,
            get_expected_output,
            MultiMetadataAgentKnowledge,
        )
        import asyncio
        
        request_serializer = AiChatRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        validated_data = request_serializer.validated_data
        
        try:
            # Get project
            project = Project.objects.get(uuid=validated_data['project_uuid'])
            
            # Check permissions
            if not (project.owner == request.user or 
                    request.user in project.members.all() or 
                    (project.team and request.user in project.team.members.all())):
                return Response(
                    {"error": "You don't have access to this project"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get or create a default Reggie agent for vault
            try:
                vault_agent = DjangoAgent.objects.get(name="Vault Assistant")
            except DjangoAgent.DoesNotExist:
                # Create a default vault agent
                vault_agent = DjangoAgent.objects.create(
                    user=request.user,
                    name="Vault Assistant",
                    description="AI assistant for vault file analysis",
                    is_global=True,
                    search_knowledge=True,
                    cite_knowledge=True,
                    markdown_enabled=True,
                    add_history_to_messages=True
                )

            # Ensure the vault agent has a valid model
            if not vault_agent.model or not getattr(vault_agent.model, "is_enabled", False):
                default_model = ModelProvider.objects.filter(is_enabled=True).first()
                if not default_model:
                    return Response(
                        {"error": "No enabled model provider configured"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                vault_agent.model = default_model
                vault_agent.save(update_fields=["model"])
            
            # Create custom vector DB and knowledge for vault with project filtering
            embedder = OpenAIEmbedder(id="text-embedding-3-small", dimensions=1536)
            # Use enhanced PgVector class with search_with_filter capability
            from apps.reggie.agents.helpers.agent_helpers import MultiMetadataFilteredPgVector
            vault_vector_db = MultiMetadataFilteredPgVector(
                db_url=get_db_url(),
                table_name="data_vault_vector_table",  # Use the actual table where embeddings are stored
                schema=get_schema(),
                embedder=embedder,
            )

            # Optimized document retrieval for token efficiency
            knowledge = MultiMetadataAgentKnowledge(
                vector_db=vault_vector_db,
                num_documents=2,  # Reduced from 3 to minimize token usage
                filter_dict={"project_uuid": str(project.uuid)},
            )

            # Log for debugging
            logger.info(f"Vault search configured for project_uuid: {str(project.uuid)} using table: data_vault_vector_table")

            # Build memory and storage compatible with Agno Agent
            memory = AgentMemory(
                db=PgMemoryDb(table_name=settings.AGENT_MEMORY_TABLE, db_url=get_db_url(), schema=get_schema()),
                create_user_memories=True,
                create_session_summary=True,
            )
            storage = PostgresAgentStorage(
                table_name=vault_agent.session_table,
                db_url=get_db_url(),
                schema=get_schema(),
            )

            # Prepare model, instructions, expected output
            model = get_llm_model(vault_agent.model)
            user_instruction, other_instructions = get_instructions_tuple(vault_agent, request.user)

            # Add vault-specific instructions for better document handling
            vault_instructions = [
                "You are analyzing documents from the user's vault for project " + str(project.uuid) + ".",
                "When asked for summaries, search the knowledge base thoroughly and provide comprehensive summaries based on all relevant documents found.",
                "Always search for documents before saying no information is available.",
                "Use multiple search queries if needed to find all relevant content."
            ]

            instructions = ([user_instruction] if user_instruction else []) + vault_instructions + other_instructions
            expected_output = get_expected_output(vault_agent)

            # Assemble the agent
            agent = AgnoAgent(
                agent_id=str(vault_agent.agent_id),
                name=vault_agent.name,
                session_id=f"vault_{project.uuid}_{request.user.id}",
                user_id=str(request.user.id),
                model=model,
                storage=storage,
                memory=memory,
                knowledge=knowledge,
                description=vault_agent.description,
                instructions=instructions,
                expected_output=expected_output,
                search_knowledge=True,
                read_chat_history=vault_agent.read_chat_history,
                tools=[],
                markdown=vault_agent.markdown_enabled,
                show_tool_calls=vault_agent.show_tool_calls,
                add_history_to_messages=vault_agent.add_history_to_messages,
                add_datetime_to_instructions=vault_agent.add_datetime_to_instructions,
                debug_mode=vault_agent.debug_mode,
                read_tool_call_history=vault_agent.read_tool_call_history,
                num_history_responses=vault_agent.num_history_responses,
                add_references=True,
            )
            
            # Stream the response
            def generate_stream():
                try:
                    # Run async agent without streaming first to avoid async generator issues
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    # Get response without streaming to avoid async generator complexity
                    response = loop.run_until_complete(
                        agent.arun(validated_data['message'], stream=False)
                    )

                    # Handle single response - extract just the content
                    if response:
                        # Extract content from RunResponse object
                        content = response.content if hasattr(response, 'content') else str(response)
                        yield f"data: {json.dumps({'content': content})}\n\n"

                    yield f"data: {json.dumps({'finished': True})}\n\n"

                except Exception as e:
                    logger.error(f"Error in vault agent chat: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                finally:
                    loop.close()
            
            return StreamingHttpResponse(
                generate_stream(),
                content_type='text/event-stream'
            )
            
        except Project.DoesNotExist:
            return Response(
                {"error": "Project not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in vault agent chat: {e}")
            return Response(
                {"error": "AI service unavailable"}, 
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
    
    @action(detail=False, methods=["post"], url_path="ai-chat-stream")
    def ai_chat_stream(self, request):
        """Handle AI chat conversations with streaming responses"""
        from .serializers import AiChatRequestSerializer
        from .utils.gcs_utils import post_to_cloud_run
        from .models import AiConversation, Project
        import time
        import json
        import requests
        from django.http import StreamingHttpResponse
        
        request_serializer = AiChatRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = request_serializer.validated_data
        
        try:
            try:
                project = Project.objects.get(uuid=validated_data['project_uuid'])
            except Project.DoesNotExist:
                return Response(
                    {"error": "Project not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check permissions
            if not (project.owner == request.user or 
                    request.user in project.members.all() or 
                    (project.team and request.user in project.team.members.all())):
                return Response(
                    {"error": "You don't have access to this project"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get conversation history
            recent_conversations = AiConversation.objects.filter(
                user=request.user,
                project=project,
                folder_id=validated_data.get('parent_id', 0)
            ).order_by('-created_at')[:5]
            
            conversation_history = [
                {"question": conv.question, "response": conv.response}
                for conv in reversed(recent_conversations)
            ]
            
            payload = validated_data.copy()
            payload['conversation_history'] = conversation_history
            payload['project_uuid'] = str(payload['project_uuid'])
            
            logger.info(f"Sending streaming AI chat request to Cloud Run")
            
            def generate_stream():
                ai_response_content = ""
                conversation_id = None
                sources = []
                response_time_ms = 0
                tokens_used = 0
                
                try:
                    cloud_run_url = getattr(settings, 'LLAMAINDEX_INGESTION_URL', 'http://localhost:8080')
                    start_time = time.time()
                    
                    with requests.post(
                        f"{cloud_run_url}/ai-chat-stream",
                        json=payload,
                        stream=True,
                        timeout=120
                    ) as response:
                        response.raise_for_status()
                        
                        # Forward the streaming response
                        print("fouind response", response)
                        for line in response.iter_lines():
                            if line:
                                decoded_line = line.decode('utf-8')
                                yield f"{decoded_line}\n"
                                
                                # Parse response data for conversation history
                                if decoded_line.startswith('data: '):
                                    try:
                                        data_json = decoded_line[6:]  # Remove 'data: '
                                        if data_json != '[DONE]':
                                            data = json.loads(data_json)
                                            if data.get('type') == 'conversation_id':
                                                conversation_id = data.get('data')
                                            elif data.get('type') == 'sources':
                                                sources = data.get('data', [])
                                            elif data.get('type') == 'content':
                                                ai_response_content += data.get('data', '')
                                            elif data.get('type') == 'completion':
                                                response_time_ms = data.get('data', {}).get('response_time_ms', 0)
                                                tokens_used = data.get('data', {}).get('tokens_used', 0)
                                    except json.JSONDecodeError:
                                        pass
                                
                                # Check for completion
                                if 'data: [DONE]' in decoded_line:
                                    break
                    
                    # Save conversation to database
                    if ai_response_content:
                        AiConversation.objects.create(
                            user=request.user,
                            project=project,
                            folder_id=validated_data.get('parent_id', 0),
                            question=validated_data['message'],
                            response=ai_response_content,
                            context_files=validated_data.get('file_ids', []),
                            tokens_used=tokens_used,
                            response_time_ms=response_time_ms
                        )
                        
                except requests.RequestException as e:
                    logger.error(f"❌ AI Chat streaming service error: {e}")
                    error_data = {
                        "type": "error",
                        "data": {
                            "error": "AI service unavailable",
                            "message": "Unable to process your request at the moment."
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                    yield "data: [DONE]\n\n"
            
            return StreamingHttpResponse(
                generate_stream(),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                }
            )
            
        except Exception as e:
            import traceback
            logger.error(f"Error in streaming AI chat: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response({"error": "AI service unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    @action(detail=False, methods=["get"], url_path="chat-history")
    def get_chat_history(self, request):
        """Get chat history for a project and folder"""
        from .models import AiConversation, Project
        
        project_uuid = request.query_params.get('project_uuid')
        parent_id = int(request.query_params.get('parent_id', 0))
        limit = int(request.query_params.get('limit', 50))
        
        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            try:
                project = Project.objects.get(uuid=project_uuid)
            except Project.DoesNotExist:
                return Response(
                    {"error": "Project not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Check permissions
            if not (project.owner == request.user or 
                    request.user in project.members.all() or 
                    (project.team and request.user in project.team.members.all())):
                return Response(
                    {"error": "You don't have access to this project"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Get conversation history
            conversations = AiConversation.objects.filter(
                user=request.user,
                project=project,
                folder_id=parent_id
            ).order_by('-created_at')[:limit]
            
            chat_history = []
            for conv in reversed(conversations):  # Reverse to show chronological order
                chat_history.extend([
                    {
                        "role": "user",
                        "content": conv.question,
                        "timestamp": conv.created_at.isoformat(),
                        "conversation_id": f"conv_{project.uuid}_{conv.folder_id}_{int(conv.created_at.timestamp())}"
                    },
                    {
                        "role": "assistant", 
                        "content": conv.response,
                        "timestamp": conv.created_at.isoformat(),
                        "conversation_id": f"conv_{project.uuid}_{conv.folder_id}_{int(conv.created_at.timestamp())}",
                        "sources": [],  # You can expand this to include actual sources if stored
                        "tokens_used": conv.tokens_used,
                        "response_time_ms": conv.response_time_ms
                    }
                ])
            
            return Response({
                "chat_history": chat_history,
                "total_conversations": len(conversations),
                "project_uuid": str(project.uuid),
                "parent_id": parent_id
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            import traceback
            logger.error(f"Error getting chat history: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return Response({"error": "Failed to get chat history"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _queue_vault_embedding(self, vault_file):
        """
        Queue vault file for embedding using unified LlamaIndex service
        """
        from .tasks import embed_vault_file_task
        from django.utils import timezone

        # Set embedding status to pending
        vault_file.embedding_status = "pending"
        vault_file.save(update_fields=["embedding_status"])

        logger.info(f"🔄 Queueing vault file {vault_file.id} ({vault_file.original_filename}) for embedding via unified LlamaIndex service")

        try:
            # Use the updated task that calls our new vault utils
            embed_vault_file_task.delay(vault_file.id)
            logger.info(f"✅ Successfully queued vault embedding task for file {vault_file.id}")

        except Exception as e:
            logger.error(f"Failed to queue vault embedding for file {vault_file.id}: {e}")
            vault_file.embedding_status = "failed"
            vault_file.embedding_error = f"Failed to queue embedding task: {str(e)}"
            vault_file.save(update_fields=["embedding_status", "embedding_error"])
            logger.error(f"❌ Failed to queue embedding task for vault file {vault_file.id}: {e}")
            raise

    @action(detail=False, methods=["get"], url_path="folder-summary")
    def folder_summary(self, request):
        """Generate AI summary for a folder's contents"""
        from .utils.gcs_utils import post_to_cloud_run
        
        project_uuid = request.query_params.get('project_uuid')
        parent_id = int(request.query_params.get('parent_id', 0))
        
        if not project_uuid:
            return Response({"error": "project_uuid parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            project = Project.objects.get(uuid=project_uuid)
            if not (project.owner == request.user or 
                    request.user in project.members.all() or 
                    (project.team and request.user in project.team.members.all())):
                return Response({"error": "You don't have access to this project"}, status=status.HTTP_403_FORBIDDEN)
            
            payload = {"project_uuid": project_uuid, "parent_id": parent_id}
            summary_response = post_to_cloud_run("/folder-summary", payload, timeout=45)
            
            return Response(summary_response, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in folder summary: {e}")
            return Response({"error": "AI service unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@extend_schema_view(
    list=extend_schema(
        summary="List files or file manager",
        description=(
            "List files accessible to the user. Use file_manager=true for combined files and collections view.\n\n"
            "Standard mode:\n"
            "- Returns paginated list of files\n"
            "- Supports scope filtering (mine, global, team, all)\n\n"
            "File manager mode (file_manager=true):\n"
            "- Returns combined files and collections\n"
            "- Hierarchical navigation with collection_uuid\n"
            "- Includes current collection details and breadcrumb path\n"
            "- Sorted alphabetically by name/title\n"
            "- Perfect for building file manager frontend"
        ),
        parameters=[
            OpenApiParameter(
                name="file_manager",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Set to true for file manager mode (combined files + collections)",
                required=False,
            ),
            OpenApiParameter(
                name="collection_uuid",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Optional: Get contents of specific collection (file manager mode only)",
                required=False,
            ),
            OpenApiParameter(
                name="scope",
                type=str,
                location=OpenApiParameter.QUERY,
                description="File scope: mine, global, team, all (standard mode only)",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page",
                required=False,
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Total number of items"},
                    "next": {"type": "string", "description": "URL for next page", "nullable": True},
                    "previous": {"type": "string", "description": "URL for previous page", "nullable": True},
                    "current_collection": {
                        "type": "object",
                        "description": "Current collection details (null for root level)",
                        "properties": {
                            "uuid": {
                                "type": "string",
                                "format": "uuid",
                                "nullable": True,
                                "description": "Collection UUID",
                            },
                            "name": {"type": "string", "description": "Collection name"},
                            "description": {
                                "type": "string",
                                "nullable": True,
                                "description": "Collection description",
                            },
                            "collection_type": {
                                "type": "string",
                                "description": "Collection type (folder, regulation, act, etc.)",
                            },
                            "created_at": {
                                "type": "string",
                                "format": "date-time",
                                "nullable": True,
                                "description": "Creation timestamp",
                            },
                        },
                    },
                    "breadcrumb_path": {
                        "type": "array",
                        "description": "Breadcrumb navigation path from root to current collection",
                        "items": {
                            "type": "object",
                            "properties": {
                                "uuid": {
                                    "type": "string",
                                    "format": "uuid",
                                    "nullable": True,
                                    "description": "Collection UUID (null for root)",
                                },
                                "name": {"type": "string", "description": "Collection name"},
                            },
                        },
                    },
                    "results": {
                        "type": "array",
                        "description": "Array of files and/or collections",
                        "items": {"type": "object", "description": "File or collection item"},
                    },
                },
            }
        },
        tags=["Files"],
    )
)
class FileViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing files.
    """

    queryset = File.objects.all()
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    @action(detail=False, methods=["post"], url_path="bulk-delete-and-unlink")
    def bulk_delete_and_unlink(self, request):
        """
        Bulk delete files and unlink them from all knowledge bases.
        Accepts the same input as unlink_from_kb: {"file_ids": [...], "knowledgebase_ids": [...]}
        """
        serializer = FileIngestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        files = serializer.validated_data["file_ids"]
        # knowledge_bases = serializer.validated_data["knowledgebase_ids"]  # Not used for delete, but validated

        results = {"deleted": [], "errors": []}
        for file in files:
            try:
                # Unlink from all KBs
                links_deleted = FileKnowledgeBaseLink.objects.filter(file=file).delete()
                file.delete()
                results["deleted"].append(
                    {
                        "file_uuid": str(file.uuid),
                        "file_name": getattr(file, "title", None),
                        "links_deleted": links_deleted[0],
                    }
                )
            except Exception as e:
                results["errors"].append({"file_uuid": str(getattr(file, "uuid", None)), "error": str(e)})
        return Response({"message": f"Processed {len(files)} files.", "results": results})

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action == "update_progress":
            # System-to-system communication (Cloud Run)
            permission_classes = [HasValidSystemAPIKey]
        elif self.action in ["list_files", "list_with_kbs"]:
            # Use regular user authentication for file listing (JWT/session)
            permission_classes = [permissions.IsAuthenticated]
        else:
            # Regular user authentication for other operations
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """
        Filter files based on user access and optional scope:
        - scope=mine: Only files uploaded by the user
        - scope=global: Only global files
        - scope=team: Only files for user's teams
        - scope=user: Only files for a specific user (user_id required)
        - scope=all or not specified: All accessible files (own, team, global)
        """
        request_source = self.request.headers.get("X-Request-Source")
        if request_source == "cloud-run-ingestion":
            logger.info("🔄 Request from Cloud Run ingestion service - bypassing filters")
            return File.objects.all()

        user = self.request.user
        scope = self.request.query_params.get("scope", "all")
        user_teams = getattr(user, "teams", None)

        if user.is_superuser:
            if scope == "mine":
                return File.objects.filter(uploaded_by=user)
            elif scope == "global":
                return File.objects.filter(is_global=True)
            elif scope == "team" and user_teams is not None:
                return File.objects.filter(team__in=user.teams.all())
            elif scope == "user":
                user_id = self.request.query_params.get("user_id")
                if user_id:
                    return File.objects.filter(uploaded_by__id=user_id)
            # Default: all files
            return File.objects.all()

        if scope == "mine":
            return File.objects.filter(uploaded_by=user)
        elif scope == "global":
            return File.objects.filter(is_global=True)
        elif scope == "team" and user_teams is not None:
            return File.objects.filter(team__in=user.teams.all())
        else:  # "all" or unknown
            qs = File.objects.filter(uploaded_by=user)
            if user_teams is not None:
                qs = qs | File.objects.filter(team__in=user.teams.all())
            qs = qs | File.objects.filter(is_global=True)
            return qs.distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return UploadFileSerializer
        elif self.action == "ingest_selected":
            return FileIngestSerializer
        elif self.action == "list_files":
            return FileSerializer
        return FileSerializer

    def list(self, request, *args, **kwargs):
        """Custom list method that handles file_manager mode"""
        # Check if file_manager mode is requested
        if request.query_params.get("file_manager") == "true":
            # Redirect to collections logic for file manager mode
            collection_uuid = request.query_params.get("collection_uuid")

            if collection_uuid:
                # Get specific collection contents
                try:
                    from .models import Collection

                    instance = Collection.objects.get(uuid=collection_uuid)

                    # Get folders and files
                    folders = instance.children.all()
                    files = instance.files.all()

                    # Apply filters using custom filter helper
                    filter_handler = FileManagerFilter(request)
                    files, folders = filter_handler.apply_filters(files, folders)

                    # Combine folders and files for pagination
                    from itertools import chain

                    folders_data = list(CollectionSerializer(folders, many=True).data)
                    files_data = list(FileSerializer(files, many=True).data)

                    # Apply sorting using custom sorter helper
                    sorter_handler = FileManagerSorter(request)
                    folders_data, files_data = sorter_handler.apply_sorting(folders_data, files_data)

                    # Combine and maintain sort order
                    combined_items = list(chain(folders_data, files_data))

                    # Manually implement pagination for the combined list
                    # Get page_size from query params, fallback to paginator default
                    page_size = request.query_params.get("page_size")
                    if page_size:
                        try:
                            page_size = int(page_size)
                        except (TypeError, ValueError):
                            page_size = self.paginator.get_page_size(request) if self.paginator else 10
                    else:
                        page_size = self.paginator.get_page_size(request) if self.paginator else 10

                    page_number = request.query_params.get("page", 1)

                    try:
                        page_number = int(page_number)
                    except (TypeError, ValueError):
                        page_number = 1

                    # Calculate slice indices
                    start_index = (page_number - 1) * page_size
                    end_index = start_index + page_size

                    # Get paginated slice of the combined items
                    paginated_items = combined_items[start_index:end_index]

                    # Separate folders and files from paginated results
                    paginated_folders = [item for item in paginated_items if "collection_type" in item]
                    paginated_files = [item for item in paginated_items if "file_type" in item]

                    # Create pagination info
                    has_next = end_index < len(combined_items)
                    has_previous = page_number > 1

                    # Build pagination URLs
                    base_url = request.build_absolute_uri(request.path)
                    query_params = request.GET.copy()

                    next_url = None
                    previous_url = None

                    if has_next:
                        query_params["page"] = page_number + 1
                        next_url = f"{base_url}?{query_params.urlencode()}"

                    if has_previous:
                        query_params["page"] = page_number - 1
                        previous_url = f"{base_url}?{query_params.urlencode()}"

                    {
                        "uuid": instance.uuid,
                        "id": instance.id,
                        "name": instance.name,
                        "description": instance.description,
                        "collection_type": instance.collection_type,
                        "children": paginated_folders,
                        "files": paginated_files,
                        "full_path": instance.get_full_path(),
                    }

                    # Return a flat list of items for the frontend to handle
                    return Response(
                        {
                            "count": len(combined_items),
                            "next": next_url,
                            "previous": previous_url,
                            "current_collection": {
                                "uuid": str(instance.uuid),
                                "name": instance.name,
                                "description": instance.description,
                                "collection_type": instance.collection_type,
                                "created_at": instance.created_at.isoformat() if instance.created_at else None,
                            },
                            "breadcrumb_path": [
                                {"uuid": str(ancestor.uuid), "name": ancestor.name}
                                for ancestor in instance.get_ancestors()
                            ]
                            + [{"uuid": str(instance.uuid), "name": instance.name}],
                            "results": paginated_items,  # Return the paginated slice
                        }
                    )

                    # If pagination is disabled, return all results
                    from .serializers import CollectionDetailSerializer

                    serializer = CollectionDetailSerializer(instance, context={"request": request})
                    return Response(serializer.data)

                except Collection.DoesNotExist:
                    return Response({"error": "Collection not found"}, status=status.HTTP_404_NOT_FOUND)
            else:
                # Get root contents (folders + files)
                from .models import Collection

                root_collections = Collection.objects.filter(parent__isnull=True)
                root_files = File.objects.filter(collection__isnull=True)

                if not request.user.is_superuser:
                    root_files = root_files.filter(
                        Q(uploaded_by=request.user) | Q(team__members=request.user) | Q(is_global=True)
                    )

                # Apply filters using custom filter helper
                filter_handler = FileManagerFilter(request)
                root_files, root_collections = filter_handler.apply_filters(root_files, root_collections)

                # Combine folders and files for pagination
                from itertools import chain

                # Create a combined queryset-like structure
                folders_data = list(CollectionSerializer(root_collections, many=True).data)
                files_data = list(FileSerializer(root_files, many=True).data)

                # Apply sorting using custom sorter helper
                sorter_handler = FileManagerSorter(request)
                folders_data, files_data = sorter_handler.apply_sorting(folders_data, files_data)

                # Combine and maintain sort order
                combined_items = list(chain(folders_data, files_data))

                # Manually implement pagination for the combined list
                # Get page_size from query params, fallback to paginator default
                page_size = request.query_params.get("page_size")
                if page_size:
                    try:
                        page_size = int(page_size)
                    except (TypeError, ValueError):
                        page_size = self.paginator.get_page_size(request) if self.paginator else 10
                else:
                    page_size = self.paginator.get_page_size(request) if self.paginator else 10

                page_number = request.query_params.get("page", 1)

                try:
                    page_number = int(page_number)
                except (TypeError, ValueError):
                    page_number = 1

                # Calculate slice indices
                start_index = (page_number - 1) * page_size
                end_index = start_index + page_size

                # Get paginated slice of the combined items
                paginated_items = combined_items[start_index:end_index]

                # Separate folders and files from paginated results
                paginated_folders = [item for item in paginated_items if "collection_type" in item]
                paginated_files = [item for item in paginated_items if "file_type" in item]

                # Create pagination info
                has_next = end_index < len(combined_items)
                has_previous = page_number > 1

                # Build pagination URLs
                base_url = request.build_absolute_uri(request.path)
                query_params = request.GET.copy()

                next_url = None
                previous_url = None

                if has_next:
                    query_params["page"] = page_number + 1
                    next_url = f"{base_url}?{query_params.urlencode()}"

                if has_previous:
                    query_params["page"] = page_number - 1
                    previous_url = f"{base_url}?{query_params.urlencode()}"

                # Return a flat list of items for the frontend to handle
                return Response(
                    {
                        "count": len(combined_items),
                        "next": next_url,
                        "previous": previous_url,
                        "current_collection": {
                            "uuid": None,
                            "name": "Root",
                            "description": "Root directory",
                            "collection_type": "folder",
                            "created_at": None,
                        },
                        "breadcrumb_path": [{"uuid": None, "name": "Root"}],
                        "results": paginated_items,  # Return the paginated slice
                    }
                )

        # Default behavior for regular file listing
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Upload files",
        description=(
            "Upload one or more files to the system.\n\n"
            "Features:\n"
            "- Single or multiple file upload\n"
            "- Optional auto-ingestion into knowledge base\n"
            "- Team and visibility settings\n"
            "- Global library uploads (superadmins only)\n\n"
            "Supported file types: PDF, DOCX, TXT, CSV, JSON"
        ),
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string", "format": "binary"},
                        "description": "One or more files to upload",
                    },
                    "title": {"type": "string", "description": "Optional title for the files (defaults to filename)"},
                    "description": {"type": "string", "description": "Optional description for the files"},
                    "team": {"type": "integer", "description": "Optional team ID"},
                    "auto_ingest": {"type": "boolean", "description": "Whether to automatically ingest the files"},
                    "is_global": {"type": "boolean", "description": "Upload to global library (superadmins only)"},
                    "knowledgebase_id": {"type": "string", "description": "Required if auto_ingest is True"},
                    "is_ephemeral": {"type": "boolean", "description": "Whether the file is ephemeral"},
                },
                "required": ["files"],
            }
        },
        responses={
            201: UploadFileResponseSerializer,
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            500: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
    )
    def create(self, request, *args, **kwargs):
        """
        Upload one or more documents.
        Handles both database storage and cloud storage upload.
        Only queues files for ingestion if auto_ingest is True.
        """
        try:
            serializer = self.get_serializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)

            # Check auto_ingest and knowledgebase_id first
            auto_ingest = request.data.get("auto_ingest", False)
            kb_id = request.data.get("knowledgebase_id", "").strip() if auto_ingest else None

            if auto_ingest and not kb_id:
                return Response(
                    {"error": "knowledgebase_id is required when auto_ingest is True"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get knowledge base if auto_ingest is True
            kb = None
            if auto_ingest:
                try:
                    kb = KnowledgeBase.objects.get(knowledgebase_id=kb_id)
                except KnowledgeBase.DoesNotExist:
                    return Response(
                        {"error": f"Knowledge base with ID '{kb_id}' does not exist."}, status=status.HTTP_404_NOT_FOUND
                    )

            # Save documents to database and cloud storage
            documents = serializer.save()
            logger.info(f"✅ Successfully saved {len(documents)} documents to database")

            failed_uploads = []
            successful_uploads = []
            batch_file_info_list = []

            # --- Build documents array for frontend ---
            documents_array = []
            for document in documents:
                # EphemeralFile: has .uuid, .name, .mime_type, .file.url
                if isinstance(document, EphemeralFile):
                    documents_array.append(
                        {
                            "uuid": str(document.uuid),
                            "title": document.name,
                            "file_type": document.mime_type,
                            "file": document.file.url if hasattr(document.file, "url") else None,
                        }
                    )
                else:
                    # Regular File: use FileSerializer
                    doc_data = FileSerializer(document, context={"request": request}).data
                    documents_array.append(
                        {
                            "uuid": doc_data["uuid"],
                            "title": doc_data["title"],
                            "file_type": doc_data["file_type"],
                            "file": doc_data["file"],
                        }
                    )

            for document in documents:
                try:
                    if auto_ingest and kb and not isinstance(document, EphemeralFile):
                        logger.info(f"🔄 Setting up auto-ingestion for document {document.title} into KB {kb_id}")

                        # Create link in pending state
                        link = FileKnowledgeBaseLink.objects.create(
                            file=document,
                            knowledge_base=kb,
                            ingestion_status="pending",  # Changed to pending
                            chunk_size=kb.chunk_size,
                            chunk_overlap=kb.chunk_overlap,
                            embedding_model=kb.model_provider.embedder_id if kb.model_provider else None,
                        )

                        # Set auto_ingest flag and add knowledge base to the document
                        document.auto_ingest = True
                        # document.save() # Save will be done by serializer or later if needed
                        document.knowledge_bases.add(kb)
                        # Ensure document changes are saved if not handled by serializer.save() already
                        document.save(update_fields=["auto_ingest"])

                        storage_path = document.storage_path
                        gcs_path = (
                            storage_path
                            if storage_path.startswith("gs://")
                            else f"gs://{settings.GCS_BUCKET_NAME}/{storage_path}"
                        )

                        # Get effective chunking settings
                        effective_chunk_size = kb.chunk_size
                        effective_chunk_overlap = kb.chunk_overlap
                        chunking_strategy = "token"  # Default fallback
                        document_type = "general"  # Default fallback
                        
                        if kb.chunking_strategy:
                            effective_chunk_size = kb.chunking_strategy.get_effective_chunk_size(kb.chunk_size)
                            effective_chunk_overlap = kb.chunking_strategy.get_effective_chunk_overlap(kb.chunk_overlap)
                            chunking_strategy = kb.chunking_strategy.strategy_type
                            document_type = kb.chunking_strategy.document_type

                        file_info = {
                            "file_uuid": str(document.uuid),
                            "gcs_path": gcs_path,
                            # "knowledgebase_id": kb.knowledgebase_id,
                            "vector_table_name": kb.vector_table_name,
                            "link_id": link.id,
                            "embedding_provider": kb.model_provider.provider if kb.model_provider else None,
                            "embedding_model": kb.model_provider.embedder_id if kb.model_provider else None,
                            "chunk_size": effective_chunk_size,
                            "chunk_overlap": effective_chunk_overlap,
                            "chunking_strategy": chunking_strategy,
                            "document_type": document_type,
                            "original_filename": document.title,  # For logging
                            "user_uuid": request.user.uuid,
                            "team_id": request.data.get("team_id", None),
                            "knowledgebase_id": kb.knowledgebase_id,
                        }
                        batch_file_info_list.append(file_info)

                        successful_uploads.append(
                            {
                                "file": document.title,
                                "status": "Queued for ingestion",  # Changed status message
                                "ingestion_status": "pending",
                                "link_id": link.id,
                            }
                        )
                    else:
                        successful_uploads.append(
                            {
                                "file": getattr(document, "title", getattr(document, "name", "")),
                                "status": "Uploaded successfully",
                                "ingestion_status": "not_requested",
                            }
                        )

                except Exception as e:
                    logger.error(
                        f"❌ Failed to process document {getattr(document, 'title', getattr(document, 'name', ''))} for auto-ingestion setup: {e}"
                    )
                    # If link was created, mark it as failed
                    if "link" in locals() and link and link.id:
                        link.ingestion_status = "failed"
                        link.ingestion_error = f"Pre-queueing error: {str(e)}"
                        link.save(update_fields=["ingestion_status", "ingestion_error"])
                    failed_uploads.append(
                        {
                            "file": getattr(document, "title", getattr(document, "name", "")),
                            "error": f"Error during ingestion setup: {str(e)}",
                        }
                    )

            if batch_file_info_list:
                try:
                    dispatch_ingestion_jobs_from_batch.delay(batch_file_info_list)
                    logger.info(f"🚀 Dispatched {len(batch_file_info_list)} files for ingestion via Celery task.")
                except Exception as e:
                    logger.error(f"❌ Failed to dispatch Celery task for batch ingestion: {e}")
                    # Potentially mark all these links as failed or handle retry
                    for item in successful_uploads:  # Iterate over items intended for queue
                        if item["ingestion_status"] == "pending":  # Check if it was meant for queue
                            try:
                                link_to_fail = FileKnowledgeBaseLink.objects.get(id=item["link_id"])
                                link_to_fail.ingestion_status = "failed"
                                link_to_fail.ingestion_error = f"Celery dispatch error: {str(e)}"
                                link_to_fail.save(update_fields=["ingestion_status", "ingestion_error"])
                                item["status"] = "Uploaded but ingestion dispatch failed"
                                item["ingestion_status"] = "failed"
                                item["error"] = str(e)
                            except FileKnowledgeBaseLink.DoesNotExist:
                                logger.error(
                                    f"Could not find link {item['link_id']} to mark as failed after Celery dispatch error."
                                )
                            except Exception as inner_e:
                                logger.error(f"Error marking link {item.get('link_id')} as failed: {inner_e}")

            # Get collection information if files were uploaded to a collection
            collection_data = None
            if documents and hasattr(documents[0], "collection") and documents[0].collection:
                collection_data = CollectionSerializer(documents[0].collection, context={"request": request}).data

            response_data = {
                "message": f"{len(documents)} documents processed.",
                "documents": documents_array,
                "collection": collection_data,
                "successful_uploads": successful_uploads,
                "failed_uploads": failed_uploads,
            }

            if failed_uploads:
                # Determine appropriate status based on whether all failed or some succeeded
                # For simplicity, if any failed during processing, using 207.
                # If all failed before any processing (e.g. initial validation), could be 400.
                return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("❌ Upload failed")
            return Response(
                {"message": "Failed to process documents", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # _trigger_async_ingestion and _make_async_request are removed as per requirements.

    @extend_schema(
        summary="List files",
        description=(
            "List all accessible files with their associated knowledge bases.\n\n"
            "Features:\n"
            "- File metadata\n"
            "- Associated knowledge bases\n"
            "- Creation and update timestamps\n\n"
            "The results are paginated and can be filtered by type and keywords."
        ),
        parameters=[
            OpenApiParameter(
                name="type",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by file type (pdf, docx, txt, etc.)",
                required=False,
            ),
            OpenApiParameter(
                name="keywords",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search files by name or description",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page",
                required=False,
            ),
        ],
        responses={200: FileSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="list")
    def list_files(self, request):
        """List all accessible files with their knowledge base associations."""
        try:
            # Get query parameters
            file_type = request.query_params.get("type")
            keywords = request.query_params.get("keywords")

            # Start with base queryset
            queryset = self.get_queryset().prefetch_related("knowledge_base_links__knowledge_base")

            # Apply file type filter if provided
            if file_type:
                queryset = queryset.filter(file_type=file_type)

            # Apply search filter if provided
            if keywords:
                queryset = queryset.filter(Q(title__icontains=keywords) | Q(description__icontains=keywords))

            # Order by most recently updated
            queryset = queryset.order_by("-updated_at")

            # Paginate results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = FileSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = FileSerializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="update-progress")
    def update_progress(self, request, uuid=None):
        """
        Update ingestion progress for a file.
        Called by the Cloud Run ingestion service.
        Requires API key authentication.
        """
        try:
            logger.info(f"📊 Received progress update for file {uuid}")
            auth_header = request.headers.get("Authorization", "")
            logger.info(f"🔑 Auth header: {auth_header[:15]}...")
            logger.info(
                f"👤 Request user: {request.user.email if not isinstance(request.user, AnonymousUser) else 'AnonymousUser'}"
            )

            file = self.get_object()
            progress = request.data.get("progress", 0)
            processed_docs = request.data.get("processed_docs", 0)
            total_docs = request.data.get("total_docs", 0)
            link_id = request.data.get("link_id")

            logger.info(f"📈 Updating progress: {progress:.1f}% ({processed_docs}/{total_docs} documents)")

            # If link_id is provided, update that specific link
            if link_id:
                try:
                    link = FileKnowledgeBaseLink.objects.get(id=link_id, file=file)
                    link.ingestion_progress = progress
                    link.processed_docs = processed_docs
                    link.total_docs = total_docs

                    if progress >= 100:
                        link.ingestion_status = "completed"
                        link.ingestion_completed_at = timezone.now()
                        # Update file's ingested status
                        file.is_ingested = True
                        file.save(update_fields=["is_ingested"])

                    link.save(
                        update_fields=[
                            "ingestion_progress",
                            "processed_docs",
                            "total_docs",
                            "ingestion_status",
                            "ingestion_completed_at",
                        ]
                    )
                    logger.info(f"✅ Updated progress for link {link_id}")
                except FileKnowledgeBaseLink.DoesNotExist:
                    logger.error(f"❌ Link {link_id} not found for file {uuid}")
                    return Response(
                        {"error": f"Link {link_id} not found for file {uuid}"}, status=status.HTTP_404_NOT_FOUND
                    )
            else:
                # Fall back to updating the active link if no link_id provided
                active_link = file.knowledge_base_links.filter(ingestion_status="processing").first()
                if active_link:
                    active_link.ingestion_progress = progress
                    active_link.processed_docs = processed_docs
                    active_link.total_docs = total_docs

                    if progress >= 100:
                        active_link.ingestion_status = "completed"
                        active_link.ingestion_completed_at = timezone.now()
                        # Update file's ingested status
                        file.is_ingested = True
                        file.save(update_fields=["is_ingested"])

                    active_link.save(
                        update_fields=[
                            "ingestion_progress",
                            "processed_docs",
                            "total_docs",
                            "ingestion_status",
                            "ingestion_completed_at",
                        ]
                    )
                    logger.info("✅ Updated progress for active link")
                else:
                    logger.warning(f"⚠️ No active ingestion link found for file {uuid}")

            return Response(
                {
                    "message": "Progress updated successfully",
                    "progress": progress,
                    "processed_docs": processed_docs,
                    "total_docs": total_docs,
                    "is_ingested": file.is_ingested,
                    "link_id": link_id if link_id else None,
                }
            )

        except File.DoesNotExist:
            logger.error(f"❌ File not found: {uuid}")
            return Response({"error": f"File with UUID {uuid} not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception(f"❌ Failed to update ingestion progress for file {uuid}")
            return Response(
                {"error": f"Failed to update progress: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], url_path="ingest-selected")
    def ingest_selected(self, request):
        """
        Manually ingest selected files into multiple knowledge bases.
        """
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        print(request.data)
        try:
            links = serializer.save()

            # Start ingestion for each link
            file_info_list = []
            for link in links:
                try:
                    logger.info(
                        f"🔄 Queuing ingestion for file {link.file.uuid} into KB {link.knowledge_base.knowledgebase_id}"
                    )

                    # Update status to pending
                    link.ingestion_status = "pending"
                    link.save(update_fields=["ingestion_status"])
                    print("link", link)
                    print("model_provider", getattr(link.knowledge_base.model_provider, "embedder_id", None))
                    # Build file_info dict for Celery task
                    file_info = {
                        "gcs_path": link.file.storage_path,
                        "vector_table_name": link.knowledge_base.vector_table_name,
                        "file_uuid": str(link.file.uuid),
                        "link_id": link.id,
                        "embedding_provider": getattr(link.knowledge_base.model_provider, "provider", None),
                        "embedding_model": getattr(link.knowledge_base.model_provider, "embedder_id", None),
                        "chunk_size": link.knowledge_base.chunk_size,
                        "chunk_overlap": link.knowledge_base.chunk_overlap,
                        "original_filename": getattr(link.file, "title", None),
                        "user_uuid": request.user.uuid,
                        "team_id": request.data.get("team_id", None),
                        "knowledgebase_id": link.knowledge_base.knowledgebase_id,
                    }
                    logger.info(f"📤 Adding to batch ingestion: {file_info}")
                    file_info_list.append(file_info)

                except Exception as e:
                    logger.exception(f"❌ Failed to queue ingestion for file {link.file.uuid}")
                    link.ingestion_status = "failed"
                    link.ingestion_error = str(e)
                    link.save(update_fields=["ingestion_status", "ingestion_error"])

            # Dispatch batch ingestion job
            if file_info_list:
                print("file_info_list ", file_info_list)
                dispatch_ingestion_jobs_from_batch.delay(file_info_list)

            return Response(
                {
                    "message": f"Queued ingestion of {len(links)} file-knowledge base combinations",
                    "links": [
                        {
                            "file_uuid": str(link.file.uuid),
                            "file_name": link.file.title,
                            "knowledge_base_id": link.knowledge_base.knowledgebase_id,
                            "status": link.ingestion_status,
                            "progress": link.ingestion_progress,
                            "processed_docs": link.processed_docs,
                            "total_docs": link.total_docs,
                            "storage_path": link.file.storage_path,
                            "vector_table": link.knowledge_base.vector_table_name,
                            "user_uuid": request.user.uuid,
                            "team_id": request.data.get("team_id", None),
                            "knowledgebase_id": link.knowledge_base.knowledgebase_id,
                        }
                        for link in links
                    ],
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("❌ Manual ingestion failed")
            return Response(
                {"error": f"Failed to process files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"], url_path="reingest")
    def reingest(self, request, uuid=None):
        """
        Manually trigger re-ingestion of a file into all its linked knowledge bases.
        """
        try:
            file = self.get_object()
            results = {"success": [], "failed": []}

            file_info_list = []
            for link in file.knowledge_base_links.all():
                try:
                    # Reset status
                    link.ingestion_status = "processing"
                    link.ingestion_error = None
                    link.ingestion_progress = 0.0
                    link.processed_docs = 0
                    link.total_docs = 0
                    link.ingestion_started_at = timezone.now()
                    link.ingestion_completed_at = None
                    link.save()

                    # Build file_info dict for Celery task
                    file_info = {
                        "gcs_path": getattr(file, "gcs_path", None) or getattr(file, "storage_path", None),
                        "vector_table_name": link.knowledge_base.vector_table_name,
                        "file_uuid": str(file.uuid),
                        "link_id": link.id,
                        "embedding_provider": getattr(link.knowledge_base.model_provider, "provider", None),
                        "embedding_model": getattr(link.knowledge_base.model_provider, "embedder_id", None),
                        "chunk_size": link.knowledge_base.chunk_size,
                        "chunk_overlap": link.knowledge_base.chunk_overlap,
                        "original_filename": getattr(file, "title", None),
                        "user_uuid": request.user.uuid,
                        "team_id": request.data.get("team_id", None),
                        "knowledgebase_id": link.knowledge_base.knowledgebase_id,
                    }
                    logger.info(f"📤 Adding to reingest batch: {file_info}")
                    file_info_list.append(file_info)
                    results["success"].append(
                        {
                            "knowledge_base_id": link.knowledge_base.knowledgebase_id,
                            "message": "Reingestion started successfully",
                        }
                    )
                except Exception as e:
                    link.ingestion_status = "failed"
                    link.ingestion_error = str(e)
                    link.save(update_fields=["ingestion_status", "ingestion_error"])
                    results["failed"].append(
                        {"knowledge_base_id": link.knowledge_base.knowledgebase_id, "error": str(e)}
                    )
                    logger.error(
                        f"❌ Failed to reingest file {file.id} into KB {link.knowledge_base.knowledgebase_id}: {e}"
                    )

            return Response(
                {
                    "message": f"Processed reingestion for {len(file.knowledge_base_links.all())} knowledge bases",
                    "results": results,
                }
            )

        except Exception as e:
            logger.exception(f"❌ Reingestion failed for file {uuid}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="List files with knowledge base information",
        description=(
            "List all files with their associated knowledge bases.\n\n"
            "Features:\n"
            "- File metadata\n"
            "- Associated knowledge bases\n"
            "- Creation and update timestamps\n\n"
            "The results are paginated and can be filtered by type and search query."
        ),
        parameters=[
            OpenApiParameter(
                name="type",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by file type (pdf, docx, txt, etc.)",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search files by name",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page",
                required=False,
            ),
        ],
        responses={200: FileSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="list-with-kbs")
    def list_with_kbs(self, request):
        """List all files with their knowledge base associations."""
        try:
            # Get query parameters
            file_type = request.query_params.get("type")
            search_query = request.query_params.get("search")

            # Start with base queryset
            queryset = self.get_queryset().prefetch_related("knowledge_base_links__knowledge_base")

            # Apply file type filter if provided
            if file_type:
                queryset = queryset.filter(file_type=file_type)

            # Apply search filter if provided
            if search_query:
                queryset = queryset.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))

            # Order by most recently updated
            queryset = queryset.order_by("-updated_at")

            # Paginate results
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = FileSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            # If pagination is disabled
            serializer = FileSerializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"], url_path="link-to-kb")
    def link_to_kb(self, request):
        """
        Link files to knowledge bases without ingestion.
        Simply creates the links in the database.
        """
        serializer = FileIngestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            files = serializer.validated_data["file_ids"]
            knowledge_bases = serializer.validated_data["knowledgebase_ids"]

            results = {"links_created": [], "existing_links": [], "errors": []}

            for file in files:
                for kb in knowledge_bases:
                    try:
                        # Create or get the link
                        link, created = FileKnowledgeBaseLink.objects.get_or_create(
                            file=file,
                            knowledge_base=kb,
                            defaults={
                                "ingestion_status": "not_started",
                                "ingestion_progress": 0.0,
                            },
                        )

                        if created:
                            results["links_created"].append(
                                {
                                    "file_uuid": str(file.uuid),
                                    "file_name": file.title,
                                    "kb_id": kb.knowledgebase_id,
                                    "kb_name": kb.name,
                                }
                            )
                        else:
                            results["existing_links"].append(
                                {
                                    "file_uuid": str(file.uuid),
                                    "file_name": file.title,
                                    "kb_id": kb.knowledgebase_id,
                                    "kb_name": kb.name,
                                }
                            )

                    except Exception as e:
                        results["errors"].append(
                            {
                                "file_uuid": str(file.uuid),
                                "file_name": file.title,
                                "kb_id": kb.knowledgebase_id,
                                "error": str(e),
                            }
                        )

            return Response(results, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("❌ File-KB linking failed")
            return Response({"error": f"Failed to link files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="Unlink files from knowledge bases",
        description=(
            "Remove files from knowledge bases by deleting their FileKnowledgeBaseLink entries.\n\n"
            "Features:\n"
            "- Remove multiple files from multiple knowledge bases in one request\n"
            "- Detailed success and error reporting\n"
            "- Idempotent operation (safe to retry)\n\n"
            "The files themselves are not deleted, only their association with the knowledge bases."
        ),
        request=FileIngestSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Summary message"},
                    "results": {
                        "type": "object",
                        "properties": {
                            "unlinked": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "file_uuid": {"type": "string", "format": "uuid"},
                                        "file_name": {"type": "string"},
                                        "kb_id": {"type": "string"},
                                        "kb_name": {"type": "string"},
                                    },
                                },
                            },
                            "errors": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "file_uuid": {"type": "string", "format": "uuid"},
                                        "file_name": {"type": "string"},
                                        "kb_id": {"type": "string"},
                                        "error": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "example": {
                    "message": "Unlinked 2 file-knowledge base combinations",
                    "results": {
                        "unlinked": [
                            {
                                "file_uuid": "123e4567-e89b-12d3-a456-426614174000",
                                "file_name": "document1.pdf",
                                "kb_id": "kb-123",
                                "kb_name": "My Knowledge Base",
                            }
                        ],
                        "errors": [
                            {
                                "file_uuid": "123e4567-e89b-12d3-a456-426614174001",
                                "file_name": "document2.pdf",
                                "kb_id": "kb-456",
                                "error": "Link does not exist",
                            }
                        ],
                    },
                },
            },
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            500: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        tags=["Files"],
    )
    @action(detail=False, methods=["post"], url_path="unlink-from-kb")
    def unlink_from_kb(self, request):
        """
        Unlink files from knowledge bases.
        This will remove the FileKnowledgeBaseLink entries but keep the files.
        """
        serializer = FileIngestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            files = serializer.validated_data["file_ids"]
            knowledge_bases = serializer.validated_data["knowledgebase_ids"]

            results = {"unlinked": [], "errors": []}

            for file in files:
                for kb in knowledge_bases:
                    try:
                        # Find and delete the link
                        link = FileKnowledgeBaseLink.objects.get(file=file, knowledge_base=kb)
                        link.delete()

                        results["unlinked"].append(
                            {
                                "file_uuid": str(file.uuid),
                                "file_name": file.title,
                                "kb_id": kb.knowledgebase_id,
                                "kb_name": kb.name,
                            }
                        )
                    except FileKnowledgeBaseLink.DoesNotExist:
                        results["errors"].append(
                            {
                                "file_uuid": str(file.uuid),
                                "file_name": file.title,
                                "kb_id": kb.knowledgebase_id,
                                "error": "Link does not exist",
                            }
                        )
                    except Exception as e:
                        results["errors"].append(
                            {
                                "file_uuid": str(file.uuid),
                                "file_name": file.title,
                                "kb_id": kb.knowledgebase_id,
                                "error": str(e),
                            }
                        )

            return Response(
                {
                    "message": f"Unlinked {len(results['unlinked'])} file-knowledge base combinations",
                    "results": results,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("❌ File-KB unlinking failed")
            return Response(
                {"error": f"Failed to unlink files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @extend_schema(
        summary="Move files between collections",
        description="Move one or more files to a different collection",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "file_ids": {
                        "type": "array",
                        "items": {"type": "string", "format": "uuid"},
                        "description": "List of file UUIDs to move",
                    },
                    "target_collection_id": {
                        "type": "integer",
                        "description": "ID of the target collection (null to move to root level)",
                    },
                },
                "required": ["file_ids"],
            }
        },
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            404: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        tags=["Files"],
    )
    @action(detail=False, methods=["post"], url_path="move-to-collection")
    def move_to_collection(self, request):
        """Move files to a different collection"""
        file_ids = request.data.get("file_ids", [])
        target_collection_uuid = request.data.get("target_collection_uuid")
        target_collection_id = request.data.get("target_collection_id")  # Keep for backward compatibility

        if not file_ids:
            return Response({"error": "file_ids is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get target collection if specified
            target_collection = None
            if target_collection_uuid is not None:
                try:
                    target_collection = Collection.objects.get(uuid=target_collection_uuid)
                except Collection.DoesNotExist:
                    return Response({"error": "Target collection not found"}, status=status.HTTP_404_NOT_FOUND)
            elif target_collection_id is not None:
                try:
                    target_collection = Collection.objects.get(id=target_collection_id)
                except Collection.DoesNotExist:
                    return Response({"error": "Target collection not found"}, status=status.HTTP_404_NOT_FOUND)

            # Get files and check permissions
            files = File.objects.filter(uuid__in=file_ids)
            moved_count = 0

            for file in files:
                # Check if user has access to the file
                if (
                    file.uploaded_by == request.user
                    or (file.team and file.team.members.filter(id=request.user.id).exists())
                    or request.user.is_superuser
                ):
                    file.collection = target_collection
                    file.save(update_fields=["collection"])
                    moved_count += 1

            if moved_count == 0:
                return Response(
                    {"error": "No files were moved. Check your permissions."}, status=status.HTTP_400_BAD_REQUEST
                )

            return Response(
                {
                    "message": f'Moved {moved_count} files to collection "{target_collection.name if target_collection else "root level"}"',
                    "moved_count": moved_count,
                }
            )

        except Exception as e:
            return Response({"error": f"Failed to move files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(tags=["File Tags"])
class FileTagViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing file tags.
    """

    queryset = FileTag.objects.all()
    serializer_class = FileTagSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema(tags=["Global Instruction Templates"])
class GlobalInstructionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgentInstructionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AgentInstruction.objects.filter(is_enabled=True, is_global=True)


@extend_schema(tags=["Global Expected Output Templates"])
class GlobalExpectedOutputViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgentExpectedOutputSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return AgentExpectedOutput.objects.filter(is_enabled=True, is_global=True)


### SLACK ###
# Slackbot webhook
client = WebClient(token=settings.SLACK_BOT_TOKEN)


@csrf_exempt
def slack_events(request: HttpRequest):
    """Handle incoming Slack events like mentions."""
    if request.method == "POST":
        data = json.loads(request.body)

        # Slack verification challenge
        if "challenge" in data:
            return JsonResponse({"challenge": data["challenge"]})

        # Check if bot was mentioned
        if "event" in data:
            event = data["event"]
            if event.get("type") == "app_mention":
                try:
                    from apps.slack_integration.bot.factory import build_bolt_app

                    app = build_bolt_app()
                    # TODO: Implement proper Slack event handling
                    # app.handle(event)  # This would be the proper implementation
                except Exception as e:
                    print(f"Error sending message: {e}")
        return JsonResponse({"message": "Event received"})


def get_slack_tools():
    try:
        if not settings.SLACK_BOT_TOKEN:
            return None
        return SlackTools(token=settings.SLACK_BOT_TOKEN)
    except (AttributeError, ValueError):
        # Handle cases where SLACK_BOT_TOKEN is not set or invalid
        return None


# Lazy initialization - only create when actually needed
_slack_tools = None


def get_slack_tools_lazy():
    global _slack_tools
    if _slack_tools is None:
        _slack_tools = get_slack_tools()
    return _slack_tools


@csrf_exempt
def agent_request(request, agent_id):
    """Handles Slack interactions for a specific agent via URL path."""
    if request.method == "POST":
        data = json.loads(request.body)
        prompt = data.get("prompt", "")

        if not prompt:
            return JsonResponse({"error": "Prompt is required"}, status=400)

        # Fetch the agent from the database
        try:
            agent_obj = DjangoAgent.objects.get(id=agent_id)
        except DjangoAgent.DoesNotExist:
            return JsonResponse({"error": "Agent not found"}, status=404)

        # Initialize Agno Agent with SlackTools
        slack_tools = get_slack_tools_lazy()
        tools = [slack_tools] if slack_tools else []
        agent = Agent(tools=tools, show_tool_calls=True)

        # Process the request
        response = agent.print_response(prompt, markdown=True)

        return JsonResponse({"agent": agent_obj.name, "response": response})

    return JsonResponse({"error": "Invalid request"}, status=400)


# Slack OAUTH
def slack_oauth_start(request):
    client_id = settings.SLACK_CLIENT_ID
    redirect_uri = "https://yourdomain.com/slack/oauth/callback/"  # must match Slack config
    scopes = ["app_mentions:read", "channels:read", "chat:write", "im:read", "users:read"]
    scope_str = ",".join(scopes)
    install_url = (
        f"https://slack.com/oauth/v2/authorize?client_id={client_id}&scope={scope_str}&redirect_uri={redirect_uri}"
    )
    return redirect(install_url)


def slack_oauth_callback(request):
    code = request.GET.get("code")
    if not code:
        return HttpResponse("Missing code", status=400)

    redirect_uri = "https://yourdomain.com/slack/oauth/callback/"
    client_id = settings.SLACK_CLIENT_ID
    client_secret = settings.SLACK_CLIENT_SECRET

    # Exchange code for token
    response = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
    ).json()

    if not response.get("ok"):
        return HttpResponse(f"Slack OAuth failed: {response.get('error')}", status=400)

    # Get current tenant context
    current_team = request.user.team  # Or however you associate the tenant

    # Save or update Slack workspace
    SlackWorkspace.objects.update_or_create(
        slack_team_id=response["team"]["id"],
        defaults={
            "team": current_team,
            "slack_team_name": response["team"]["name"],
            "access_token": response["access_token"],
            "bot_user_id": response.get("bot_user_id"),
        },
    )

    return HttpResponse("🎉 Slack successfully connected to your workspace!")


# Sample view or function
def init_agent(user, agent_id, session_id):
    builder = AgentBuilder(agent_id=agent_id, user=user, session_id=session_id)
    agent = builder.build()
    return agent


@csrf_exempt
@extend_schema(
    request=StreamAgentRequestSerializer,
    responses={200: {"type": "string", "description": "Server-Sent Events stream"}},
    tags=["Reggie AI"],
)
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def stream_agent_response(request):
    agent_id = request.data.get("agent_id")
    message = request.data.get("message")
    session_id = request.data.get("session_id")

    if not all([agent_id, message, session_id]):
        return Response({"error": "Missing required parameters."}, status=400)

    # Define the synchronous event stream generator
    def event_stream():
        print("[DEBUG] Starting event_stream")
        total_start = time.time()

        build_start = time.time()
        print("[DEBUG] Before AgentBuilder")
        builder = AgentBuilder(agent_id=agent_id, user=request.user, session_id=session_id)
        print("[DEBUG] Before agent.build()")
        agent = builder.build()
        print("[DEBUG] After agent.build()")
        build_time = time.time() - build_start
        print(f"[DEBUG] Agent build time: {build_time:.2f}s")
        yield f"data: {json.dumps({'debug': f'Agent build time: {build_time:.2f}s'})}\n\n"

        chunk_count = 0
        debug_mode = getattr(agent, "debug_mode", False)

        try:
            run_start = time.time()
            print("[DEBUG] Starting agent.run loop")
            # 🔥 Load files
            from apps.reggie.models import EphemeralFile

            agno_files = []
            for ef in EphemeralFile.objects.filter(session_id=session_id):
                agno_file = ef.to_agno_file()
                print("📦 View: File passed to agent.run", vars(agno_file))
                agno_files.append(agno_file)

            for chunk in agent.run(message, stream=True, files=agno_files):  # now passes agno_files
                chunk_count += 1
                try:
                    event_data = (
                        chunk.to_dict()
                        if hasattr(chunk, "to_dict")
                        else (chunk.dict() if hasattr(chunk, "dict") else str(chunk))
                    )
                    print(f"[DEBUG] Yielding event #{chunk_count}:", event_data)
                    yield f"data: {json.dumps(event_data)}\n\n"
                except Exception as e:
                    logger.exception(f"[Agent:{agent_id}] Failed to serialize chunk")
                    print(f"[DEBUG] Error serializing chunk #{chunk_count}: {e}")
                    yield f"data: {json.dumps({'error': f'Failed to serialize chunk: {str(e)}'})}\n\n"
                if debug_mode and chunk_count % 10 == 0:
                    logger.debug(f"[Agent:{agent.name}] {chunk_count} chunks processed")

            run_time = time.time() - run_start
            print(f"[DEBUG] agent.run total time: {run_time:.2f}s")
            yield f"data: {json.dumps({'debug': f'agent.run total time: {run_time:.2f}s'})}\n\n"
        except Exception as e:
            logger.exception(f"[Agent:{agent_id}] Error during streaming response")
            print(f"[DEBUG] Exception in event_stream: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Get metrics at the end of the session
            metrics = agent.get_session_metrics().to_dict()
            if metrics:
                model_provider = builder.django_agent.model
                create_token_usage_record(
                    user=request.user,
                    session_id=session_id,
                    agent_name=agent.name,
                    model_provider=model_provider.provider,
                    model_name=model_provider.model_name,
                    input_tokens=metrics.get("input_tokens", 0),
                    output_tokens=metrics.get("output_tokens", 0),
                    total_tokens=metrics.get("total_tokens", 0),
                )

        total_time = time.time() - total_start
        print(f"[DEBUG] Total stream time: {total_time:.2f}s")
        yield f"data: {json.dumps({'debug': f'Total stream time: {total_time:.2f}s'})}\n\n"
        print("[DEBUG] Yielding [DONE]")
        yield "data: [DONE]\n\n"

    # Return the standard StreamingHttpResponse for DRF to handle correctly
    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


@extend_schema(tags=["Reggie AI"])
class ChatSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save()  # user is handled in the serializer

    @action(detail=True, methods=["get"], url_path="messages")
    def get_session_messages(self, request, pk=None):
        try:
            session = ChatSession.objects.get(id=pk, user=request.user)
        except ChatSession.DoesNotExist:
            return Response({"error": "Session not found."}, status=404)

        db_url = getattr(settings, "DATABASE_URL", None)
        if not db_url:
            return Response({"error": "DATABASE_URL is not configured."}, status=500)

        table_name = getattr(settings, "AGENT_STORAGE_TABLE", "reggie_storage_sessions")
        schema = get_schema()
        storage = PostgresAgentStorage(table_name=table_name, db_url=db_url, schema=schema)
        agentSession = storage.read(session_id=str(session.id))
        runs = agentSession.memory.get("runs") if hasattr(agentSession, "memory") else None
        messages = []

        def strip_references(text):
            if not isinstance(text, str):
                return text
            # Remove references section and everything after the reference pattern
            # First remove the <references> tags and their content
            text = re.sub(r"<references>.*?</references>", "", text, flags=re.DOTALL)
            # Then remove everything after the reference pattern
            text = re.sub(
                r"\n\nUse the following references from the knowledge base if it helps:.*", "", text, flags=re.DOTALL
            )
            return text.strip()

        if runs and isinstance(runs, list):
            for run in runs:
                user_msg = run.get("message")
                response = run.get("response", {})
                if response.get("session_id") == str(session.id):
                    if user_msg:
                        # If the message was generated by a tool (file upload), only show the user's input or a placeholder
                        if user_msg.get("content_for_history") or user_msg.get("_original_user_message"):
                            content = user_msg.get("content_for_history") or user_msg.get("_original_user_message")
                        elif user_msg.get("tool") or user_msg.get("tool_call"):
                            # If a tool was used, show a placeholder
                            content = user_msg.get("user_input") or "[File uploaded]"
                        else:
                            content = (
                                strip_references(user_msg.get("content"))
                                if user_msg.get("role") == "user"
                                else user_msg.get("content")
                            )
                        msg_obj = {
                            "role": user_msg.get("role"),
                            "content": content,
                            "id": user_msg.get("created_at"),
                            "timestamp": user_msg.get("created_at"),
                        }
                        messages.append(msg_obj)
                    if response.get("model"):
                        resp_obj = {
                            "role": "assistant",
                            "content": response.get("content"),
                            "id": response.get("created_at"),
                            "timestamp": response.get("created_at"),
                        }
                        messages.append(resp_obj)

        paginator = PageNumberPagination()
        paginator.page_size = 20
        result_page = paginator.paginate_queryset(messages, request)
        return paginator.get_paginated_response(result_page)


@extend_schema(tags=["Agent Model Providers"])
class ModelProviderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Returns a list of enabled model providers.
    """

    queryset = ModelProvider.objects.filter(is_enabled=True).order_by("id")  # .order_by("provider", "model_name")
    serializer_class = ModelProviderSerializer
    permission_classes = [permissions.IsAuthenticated]


# views.py


def embed_pdf_urls(kb):
    urls = list(kb.pdf_urls.filter(is_enabled=True).values_list("url", flat=True))
    if not urls:
        return

    pdf_kb = PDFUrlKnowledgeBase(
        urls=urls,
        vector_db=PgVector(
            table_name=kb.vector_table_name,
            db_url=settings.DATABASE_URL,
        ),
    )
    pdf_kb.embed_documents()


class KnowledgeBasePdfURLViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeBasePdfURLSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return KnowledgeBasePdfURL.objects.filter(uploaded_by=self.request.user)

    def perform_create(self, serializer):
        instance = serializer.save(uploaded_by=self.request.user)
        try:
            embed_pdf_urls(instance.kb)
        except Exception as e:
            print(f"❌ PDF embedding failed: {e}")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def handle_file_ingestion(request):
    """
    Endpoint to ingest a single file into a knowledge base.
    """
    try:
        # Get file and knowledge base info from request
        file_uuid = request.data.get("file_uuid")
        kb_id = request.data.get("kb_id")

        # Validate inputs
        if not file_uuid or not kb_id:
            return Response({"error": "Both file_uuid and kb_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Get the file and knowledge base
        try:
            file_obj = File.objects.get(uuid=file_uuid)
            kb = KnowledgeBase.objects.get(knowledgebase_id=kb_id)
        except (File.DoesNotExist, KnowledgeBase.DoesNotExist):
            return Response({"error": "File or knowledge base not found"}, status=status.HTTP_404_NOT_FOUND)

        # Create the link
        link, created = FileKnowledgeBaseLink.objects.get_or_create(
            file=file_obj,
            knowledge_base=kb,
            defaults={
                "ingestion_status": "processing",
                "ingestion_progress": 0.0,
                "processed_docs": 0,
                "total_docs": 0,
            },
        )

        if not created:
            # Reset status for re-ingestion
            link.ingestion_status = "processing"
            link.ingestion_error = None
            link.ingestion_progress = 0.0
            link.processed_docs = 0
            link.total_docs = 0
            link.save()

        # Start ingestion process
        ingest_single_file.delay(str(file_obj.uuid), kb.knowledgebase_id)

        return Response({"message": "File ingestion started", "link_id": link.id})

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(tags=["Collections"])
class CollectionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing hierarchical collections (folders).
    """

    queryset = Collection.objects.all()
    serializer_class = CollectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    pagination_class = PageNumberPagination

    def get_queryset(self):
        """Filter collections based on user access"""
        user = self.request.user

        if user.is_superuser:
            return Collection.objects.all()

        # For regular users, show collections they have access to
        # This includes collections with their files or team files
        user_collections = Collection.objects.filter(
            models.Q(files__uploaded_by=user) | models.Q(files__team__members=user)
        ).distinct()

        return user_collections

    @extend_schema(
        summary="List collections",
        description="Get a hierarchical list of collections accessible to the user. If no collection_uuid provided, returns root contents (folders + files). If collection_uuid provided, returns collection contents. ALL results are paginated for performance.",
        parameters=[
            OpenApiParameter(
                name="collection_uuid",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Optional: Get contents of specific collection. If not provided, returns root contents.",
                required=False,
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Page number for pagination (default: 1)",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Number of results per page (default: 50, max: 1000)",
                required=False,
            ),
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Total number of items (folders + files)"},
                    "next": {"type": "string", "description": "URL for next page", "nullable": True},
                    "previous": {"type": "string", "description": "URL for previous page", "nullable": True},
                    "results": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string", "nullable": True},
                            "id": {"type": "integer", "nullable": True},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "collection_type": {"type": "string"},
                            "children": {"type": "array", "description": "Paginated sub-folders"},
                            "files": {"type": "array", "description": "Paginated files"},
                            "full_path": {"type": "string"},
                        },
                    },
                },
            }
        },
    )
    def list(self, request, *args, **kwargs):
        """List collections or get collection contents"""
        collection_uuid = request.query_params.get("collection_uuid")

        if collection_uuid:
            # Get specific collection contents
            try:
                instance = Collection.objects.get(uuid=collection_uuid)

                # Get folders and files
                folders = instance.children.all()
                files = instance.files.all()

                # Combine folders and files for pagination
                from itertools import chain

                folders_data = list(CollectionSerializer(folders, many=True).data)
                files_data = list(FileSerializer(files, many=True).data)

                # Combine and sort by name
                combined_items = sorted(
                    chain(folders_data, files_data), key=lambda x: x.get("name", x.get("title", ""))
                )

                # Manually implement pagination for the combined list
                if self.paginator:
                    page_size = self.paginator.get_page_size(request)
                    page_number = request.query_params.get("page", 1)

                    try:
                        page_number = int(page_number)
                    except (TypeError, ValueError):
                        page_number = 1

                    # Calculate slice indices
                    start_index = (page_number - 1) * page_size
                    end_index = start_index + page_size

                    # Get paginated slice of the combined items
                    paginated_items = combined_items[start_index:end_index]

                    # Separate folders and files from paginated results
                    paginated_folders = [item for item in paginated_items if "collection_type" in item]
                    paginated_files = [item for item in paginated_items if "file_type" in item]

                    # Create pagination info
                    has_next = end_index < len(combined_items)
                    has_previous = page_number > 1

                    # Build pagination URLs
                    base_url = request.build_absolute_uri(request.path)
                    query_params = request.GET.copy()

                    next_url = None
                    previous_url = None

                    if has_next:
                        query_params["page"] = page_number + 1
                        next_url = f"{base_url}?{query_params.urlencode()}"

                    if has_previous:
                        query_params["page"] = page_number - 1
                        previous_url = f"{base_url}?{query_params.urlencode()}"

                    {
                        "uuid": instance.uuid,
                        "id": instance.id,
                        "name": instance.name,
                        "description": instance.description,
                        "collection_type": instance.collection_type,
                        "children": paginated_folders,
                        "files": paginated_files,
                        "full_path": instance.get_full_path(),
                    }

                    # Return a flat list of items for the frontend to handle
                    return Response(
                        {
                            "count": len(combined_items),
                            "next": next_url,
                            "previous": previous_url,
                            "current_collection": {
                                "uuid": str(instance.uuid),
                                "name": instance.name,
                                "description": instance.description,
                                "collection_type": instance.collection_type,
                                "created_at": instance.created_at.isoformat() if instance.created_at else None,
                            },
                            "breadcrumb_path": [
                                {"uuid": str(ancestor.uuid), "name": ancestor.name}
                                for ancestor in instance.get_ancestors()
                            ]
                            + [{"uuid": str(instance.uuid), "name": instance.name}],
                            "results": paginated_items,  # Return the paginated slice
                        }
                    )

                # If pagination is disabled, return all results
                serializer = CollectionDetailSerializer(instance, context={"request": request})
                return Response(serializer.data)

            except Collection.DoesNotExist:
                return Response({"error": "Collection not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            # Get root contents (folders + files)
            root_collections = self.get_queryset().filter(parent__isnull=True)
            root_files = File.objects.filter(collection__isnull=True)

            if not request.user.is_superuser:
                root_files = root_files.filter(
                    Q(uploaded_by=request.user) | Q(team__members=request.user) | Q(is_global=True)
                )

            # Combine folders and files for pagination
            from itertools import chain

            # Create a combined queryset-like structure
            folders_data = list(CollectionSerializer(root_collections, many=True).data)
            files_data = list(FileSerializer(root_files, many=True).data)

            # Combine and sort by name
            combined_items = sorted(chain(folders_data, files_data), key=lambda x: x.get("name", x.get("title", "")))

            # Manually implement pagination for the combined list
            if self.paginator:
                page_size = self.paginator.get_page_size(request)
                page_number = request.query_params.get("page", 1)

                try:
                    page_number = int(page_number)
                except (TypeError, ValueError):
                    page_number = 1

                # Calculate slice indices
                start_index = (page_number - 1) * page_size
                end_index = start_index + page_size

                # Get paginated slice of the combined items
                paginated_items = combined_items[start_index:end_index]

                # Separate folders and files from paginated results
                paginated_folders = [item for item in paginated_items if "collection_type" in item]
                paginated_files = [item for item in paginated_items if "file_type" in item]

                # Create pagination info
                has_next = end_index < len(combined_items)
                has_previous = page_number > 1

                # Build pagination URLs
                base_url = request.build_absolute_uri(request.path)
                query_params = request.GET.copy()

                next_url = None
                previous_url = None

                if has_next:
                    query_params["page"] = page_number + 1
                    next_url = f"{base_url}?{query_params.urlencode()}"

                if has_previous:
                    query_params["page"] = page_number - 1
                    previous_url = f"{base_url}?{query_params.urlencode()}"

                root_data = {
                    "uuid": None,
                    "id": None,
                    "name": "Root",
                    "description": "Root directory",
                    "collection_type": "folder",
                    "children": paginated_folders,
                    "files": paginated_files,
                    "full_path": "Root",
                }

                return Response(
                    {
                        "count": len(combined_items),
                        "next": next_url,
                        "previous": previous_url,
                        "current_collection": {
                            "uuid": None,
                            "name": "Root",
                            "description": "Root directory",
                            "collection_type": "folder",
                            "created_at": None,
                        },
                        "breadcrumb_path": [{"uuid": None, "name": "Root"}],
                        "results": paginated_items,  # Return the paginated slice
                    }
                )

            # If pagination is disabled, return all results
            root_data = {
                "uuid": None,
                "id": None,
                "name": "Root",
                "description": "Root directory",
                "collection_type": "folder",
                "children": folders_data,
                "files": files_data,
                "full_path": "Root",
            }

            return Response(root_data)

    @extend_schema(
        summary="Get collection details",
        description="Get detailed information about a collection including files and subcollections",
        responses={200: CollectionDetailSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        """Get collection details with files and subcollections"""
        instance = self.get_object()
        serializer = CollectionDetailSerializer(instance, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="add-files")
    def add_files(self, request, pk=None):
        """Add existing files to a collection"""
        collection = self.get_object()
        file_ids = request.data.get("file_ids", [])

        if not file_ids:
            return Response({"error": "file_ids is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            files = File.objects.filter(id__in=file_ids)
            added_count = 0

            for file in files:
                # Check if user has access to the file
                if (
                    file.uploaded_by == request.user
                    or (file.team and file.team.members.filter(id=request.user.id).exists())
                    or request.user.is_superuser
                ):
                    file.collection = collection
                    file.save()
                    added_count += 1

            return Response(
                {"message": f'Added {added_count} files to collection "{collection.name}"', "added_count": added_count}
            )

        except Exception as e:
            return Response({"error": f"Failed to add files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=["post"], url_path="reorder-files")
    def reorder_files(self, request, pk=None):
        """Reorder files within a collection"""
        collection = self.get_object()
        file_orders = request.data.get("file_orders", [])

        if not file_orders:
            return Response({"error": "file_orders is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            for item in file_orders:
                file_id = item.get("file_id")
                order = item.get("order", 0)

                if file_id is not None:
                    file = File.objects.get(id=file_id, collection=collection)
                    file.collection_order = order
                    file.save(update_fields=["collection_order"])

            return Response({"message": "Files reordered successfully"})

        except File.DoesNotExist:
            return Response(
                {"error": "One or more files not found in this collection"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to reorder files: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"], url_path="move-to")
    def move_to(self, request, pk=None):
        """Move this collection to a different parent collection"""
        collection = self.get_object()
        new_parent_id = request.data.get("new_parent_id")

        if new_parent_id is None:
            # Move to root level
            collection.parent = None
        else:
            try:
                new_parent = Collection.objects.get(id=new_parent_id)
                # Prevent circular references
                if new_parent == collection or new_parent in collection.get_descendants():
                    return Response(
                        {"error": "Cannot move collection to itself or its descendants"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                collection.parent = new_parent
            except Collection.DoesNotExist:
                return Response({"error": "Parent collection not found"}, status=status.HTTP_404_NOT_FOUND)

        collection.save()
        return Response(
            {
                "message": f'Collection "{collection.name}" moved successfully',
                "new_parent": collection.parent.name if collection.parent else None,
            }
        )

    @extend_schema(
        summary="Create folder/collection",
        description="Create a new folder or collection, optionally within a parent collection",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the folder/collection"},
                    "parent_uuid": {
                        "type": "string",
                        "description": "Optional: UUID of parent collection. If not provided, creates at root level.",
                    },
                    "description": {"type": "string", "description": "Optional description of the folder/collection"},
                    "collection_type": {
                        "type": "string",
                        "enum": ["folder", "regulation", "act", "guideline", "manual"],
                        "description": "Type of collection (default: folder)",
                    },
                },
                "required": ["name"],
            }
        },
        responses={
            201: CollectionSerializer,
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            404: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        tags=["Collections"],
    )
    @action(detail=False, methods=["post"], url_path="create-folder")
    def create_folder(self, request):
        """Create a new folder/collection"""
        name = request.data.get("name")
        parent_uuid = request.data.get("parent_uuid")
        description = request.data.get("description", "")
        collection_type = request.data.get("collection_type", "folder")

        if not name:
            return Response({"error": "name is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parent = None
            if parent_uuid:
                try:
                    parent = Collection.objects.get(uuid=parent_uuid)
                except Collection.DoesNotExist:
                    return Response(
                        {"error": f"Parent collection with UUID {parent_uuid} not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            collection = Collection.objects.create(
                name=name, parent=parent, description=description, collection_type=collection_type
            )

            serializer = CollectionSerializer(collection)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Failed to create collection: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request):
        """Get the complete collection tree structure"""
        root_collections = self.get_queryset().filter(parent__isnull=True)
        serializer = CollectionSerializer(root_collections, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Delete collection",
        description="Delete a collection and optionally handle its contents",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "handle_contents": {
                        "type": "string",
                        "enum": ["delete_all", "move_to_parent", "move_to_root"],
                        "description": "How to handle files and subcollections in the deleted collection",
                    },
                    "target_collection_id": {
                        "type": "integer",
                        "description": "Required if handle_contents is 'move_to_parent' or 'move_to_root'",
                    },
                },
                "required": ["handle_contents"],
            }
        },
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}},
            400: {"type": "object", "properties": {"error": {"type": "string"}}},
            404: {"type": "object", "properties": {"error": {"type": "string"}}},
        },
        tags=["Collections"],
    )
    @action(detail=True, methods=["delete"], url_path="delete")
    def delete_collection(self, request, pk=None):
        """Delete a collection with options for handling its contents"""
        collection = self.get_object()
        handle_contents = request.data.get("handle_contents", "delete_all")
        target_collection_id = request.data.get("target_collection_id")

        try:
            if handle_contents == "delete_all":
                # Delete everything in the collection
                deleted_count = collection.files.count()
                collection.files.all().delete()

                # Delete all subcollections recursively
                subcollections = collection.get_descendants()
                subcollections_count = len(subcollections)
                for subcollection in subcollections:
                    subcollection.files.all().delete()
                    subcollection.delete()

                # Delete the collection itself
                collection.delete()

                return Response(
                    {
                        "message": f'Collection "{collection.name}" and all contents deleted successfully',
                        "deleted_files": deleted_count,
                        "deleted_subcollections": subcollections_count,
                    }
                )

            elif handle_contents == "move_to_parent":
                # Move contents to parent collection
                if not collection.parent:
                    return Response(
                        {"error": "Cannot move to parent: collection is at root level"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Move files to parent
                moved_files = collection.files.count()
                collection.files.update(collection=collection.parent)

                # Move subcollections to parent
                moved_subcollections = collection.children.count()
                collection.children.update(parent=collection.parent)

                # Delete the empty collection
                collection.delete()

                return Response(
                    {
                        "message": f'Collection "{collection.name}" deleted, contents moved to parent',
                        "moved_files": moved_files,
                        "moved_subcollections": moved_subcollections,
                    }
                )

            elif handle_contents == "move_to_root":
                # Move contents to root level
                if not target_collection_id:
                    return Response(
                        {"error": "target_collection_id is required for move_to_root"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    target_collection = Collection.objects.get(id=target_collection_id)
                except Collection.DoesNotExist:
                    return Response({"error": "Target collection not found"}, status=status.HTTP_404_NOT_FOUND)

                # Move files to target collection
                moved_files = collection.files.count()
                collection.files.update(collection=target_collection)

                # Move subcollections to target collection
                moved_subcollections = collection.children.count()
                collection.children.update(parent=target_collection)

                # Delete the empty collection
                collection.delete()

                return Response(
                    {
                        "message": f'Collection "{collection.name}" deleted, contents moved to "{target_collection.name}"',
                        "moved_files": moved_files,
                        "moved_subcollections": moved_subcollections,
                    }
                )

            else:
                return Response({"error": "Invalid handle_contents value"}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response(
                {"error": f"Failed to delete collection: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

@extend_schema(tags=["Token Usage"])
class TokenUsageViewSet(viewsets.ReadOnlyModelViewSet):
    
    serializer_class = TokenUsageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    
    def get_queryset(self):
        """Filter token usage based on user permissions and query parameters"""
        queryset = TokenUsage.objects.select_related("user", "team").all()
        
        # Filter by team if user is not staff
        if not self.request.user.is_staff:
            user_teams = self.request.user.teams.all()
            queryset = queryset.filter(team__in=user_teams)
        
        # Apply filters
        user_id = self.request.query_params.get("user_id")
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        team_id = self.request.query_params.get("team_id")
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        
        operation_type = self.request.query_params.get("operation_type")
        if operation_type:
            queryset = queryset.filter(operation_type=operation_type)
        
        provider = self.request.query_params.get("provider")
        if provider:
            queryset = queryset.filter(provider=provider)
        
        model = self.request.query_params.get("model")
        if model:
            queryset = queryset.filter(model=model)
        
        # Date range filtering
        date_from = self.request.query_params.get("date_from")
        if date_from:
            try:
                from django.utils.dateparse import parse_datetime
                date_from = parse_datetime(date_from)
                if date_from:
                    queryset = queryset.filter(created_at__gte=date_from)
            except (ValueError, TypeError):
                pass
        
        date_to = self.request.query_params.get("date_to")
        if date_to:
            try:
                from django.utils.dateparse import parse_datetime
                date_to = parse_datetime(date_to)
                if date_to:
                    queryset = queryset.filter(created_at__lte=date_to)
            except (ValueError, TypeError):
                pass
        
        return queryset.order_by("-created_at")
    
    @extend_schema(
        summary="Get token usage summary",
        description="Get aggregated token usage statistics",
        parameters=[
            OpenApiParameter(
                name="group_by",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Group by field (user, team, operation_type, provider, model)",
                enum=["user", "team", "operation_type", "provider", "model"]
            ),
            OpenApiParameter(
                name="date_from",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Start date (ISO format)"
            ),
            OpenApiParameter(
                name="date_to",
                type=str,
                location=OpenApiParameter.QUERY,
                description="End date (ISO format)"
            ),
        ]
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get aggregated token usage statistics"""
        from django.db.models import Sum, Count, Avg
        from django.db.models.functions import TruncDate
        
        queryset = self.get_queryset()
        
        # Date range filtering
        date_from = request.query_params.get("date_from")
        if date_from:
            try:
                from django.utils.dateparse import parse_datetime
                date_from = parse_datetime(date_from)
                if date_from:
                    queryset = queryset.filter(created_at__gte=date_from)
            except (ValueError, TypeError):
                pass
        
        date_to = request.query_params.get("date_to")
        if date_to:
            try:
                from django.utils.dateparse import parse_datetime
                date_to = parse_datetime(date_to)
                if date_to:
                    queryset = queryset.filter(created_at__lte=date_to)
            except (ValueError, TypeError):
                pass
        
        group_by = request.query_params.get("group_by", "operation_type")
        
        # Validate group_by field
        valid_group_fields = ["user", "team", "operation_type", "provider", "model"]
        if group_by not in valid_group_fields:
            return Response(
                {"error": f"Invalid group_by field. Must be one of: {valid_group_fields}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Aggregate data
        if group_by == "user":
            summary = queryset.values("user__email", "user__id").annotate(
                total_tokens=Sum("total_tokens"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                total_cost=Sum("cost_usd"),
                request_count=Count("id"),
                avg_tokens_per_request=Avg("total_tokens")
            ).order_by("-total_tokens")
        elif group_by == "team":
            summary = queryset.values("team__name", "team__id").annotate(
                total_tokens=Sum("total_tokens"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                total_cost=Sum("cost_usd"),
                request_count=Count("id"),
                avg_tokens_per_request=Avg("total_tokens")
            ).order_by("-total_tokens")
        else:
            summary = queryset.values(group_by).annotate(
                total_tokens=Sum("total_tokens"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                total_cost=Sum("cost_usd"),
                request_count=Count("id"),
                avg_tokens_per_request=Avg("total_tokens")
            ).order_by("-total_tokens")
        
        return Response({
            "group_by": group_by,
            "summary": list(summary),
            "total_records": queryset.count(),
            "date_range": {
                "from": date_from,
                "to": date_to
            }
        })
    @action(detail=False, methods=["get"], url_path="usersummary")
    def user_token_summary(self, request):
        try:
            search = request.query_params.get("search") 

            queryset = UserTokenSummary.objects.select_related("user")

            if search:
                queryset = queryset.filter(
                    Q(user__email__icontains=search) |
                    Q(user__first_name__icontains=search) |
                    Q(user__last_name__icontains=search)
                )

            queryset = queryset.order_by("-updated_at")

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = UserTokenSummarySerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = UserTokenSummarySerializer(queryset, many=True)
            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
            
    @action(detail=False, methods=["get"], url_path="user")
    def user_token_by_user(self, request):
        """Get token usage records for a specific user"""
        from django.db.models import Avg, Count, Sum
        from django.utils.dateparse import parse_datetime

        user = self.request.user
        user_id = self.request.user.id

        if not user_id:
            return Response(
                {"error": "user_id parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            queryset = self.get_queryset().filter(user_id=user_id)

            date_from = request.query_params.get("date_from")
            if date_from:
                date_from = parse_datetime(date_from)
                if date_from:
                    queryset = queryset.filter(created_at__gte=date_from)

            date_to = request.query_params.get("date_to")
            if date_to:
                date_to = parse_datetime(date_to)
                if date_to:
                    queryset = queryset.filter(created_at__lte=date_to)

            stats = queryset.aggregate(
                total_tokens=Sum("total_tokens"),
                total_cost=Sum("cost"),
                request_count=Count("id"),
            )
            queryset = queryset.order_by("-created_at")

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                response_data = serializer.data
                paginated_response = self.get_paginated_response(response_data)
                return paginated_response

            serializer = self.get_serializer(queryset, many=True)
            return Response({
                "stats": stats,
                "records": serializer.data
            })

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["get"], url_path="currentuser")
    def user_token_summary(self, request):
        try:
            user = self.request.user
            user_id = self.request.user.id

            if not user_id:
                return Response(
                    {"error": "user_id parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            queryset = UserTokenSummary.objects.get(user_id=user_id)

            serializer = UserTokenSummarySerializer(queryset)
            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )