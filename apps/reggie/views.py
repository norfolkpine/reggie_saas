# === Standard Library ===
import json
import logging
import time

import requests

# === Agno ===
from agno.agent import Agent
from agno.knowledge.pdf_url import PDFUrlKnowledgeBase
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.slack import SlackTools
from agno.vectordb.pgvector import PgVector
from django.conf import settings

# === Django ===
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

# === DRF Spectacular ===
from drf_spectacular.utils import OpenApiParameter, extend_schema

# === Django REST Framework ===
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    permission_classes,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from slack_sdk import WebClient

from apps.reggie.utils.gcs_utils import ingest_single_file
from apps.slack_integration.models import (
    SlackWorkspace,
)

# === External SDKs ===
from .agents.agent_builder import AgentBuilder  # Adjust path if needed

# === Local ===
from .models import (
    Agent as DjangoAgent,  # avoid conflict with agno.Agent
)
from .models import (
    AgentExpectedOutput,
    AgentInstruction,
    ChatSession,
    File,
    FileKnowledgeBaseLink,
    FileTag,
    KnowledgeBase,
    KnowledgeBasePdfURL,
    ModelProvider,
    Project,
    StorageBucket,
    Tag,
)
from .permissions import HasSystemOrUserAPIKey, HasValidSystemAPIKey
from .serializers import (
    AgentExpectedOutputSerializer,
    AgentInstructionSerializer,
    AgentInstructionsResponseSerializer,
    AgentSerializer,
    ChatSessionSerializer,
    FileIngestSerializer,
    FileSerializer,
    FileTagSerializer,
    GlobalTemplatesResponseSerializer,
    KnowledgeBasePdfURLSerializer,
    KnowledgeBaseSerializer,
    ModelProviderSerializer,
    ProjectSerializer,
    StorageBucketSerializer,
    StreamAgentRequestSerializer,
    TagSerializer,
    UploadFileResponseSerializer,
    UploadFileSerializer,
)

logger = logging.getLogger(__name__)


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
    """
    API endpoint that allows managing knowledge bases.
    """

    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [permissions.IsAuthenticated]

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
            200: FileSerializer(many=True),
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
                serializer = FileSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = FileSerializer(queryset, many=True)
            return Response(serializer.data)

        except KnowledgeBase.DoesNotExist:
            return Response({"error": "Knowledge base not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Tags"])
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


@extend_schema(tags=["Files"])
class FileViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing files.
    """

    queryset = File.objects.all()
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action == "update_progress":
            # System-to-system communication (Cloud Run)
            permission_classes = [HasValidSystemAPIKey]
        elif self.action in ["list_files", "list_with_kbs"]:
            # Allow either system or user API key access for listing files
            permission_classes = [HasSystemOrUserAPIKey]
        else:
            # Regular user authentication for other operations
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        """
        Filter files based on user access:
        - All files if request is from Cloud Run ingestion service
        - User's own files
        - Team files (if user is in team)
        - Global files
        """
        # Check if request is from Cloud Run ingestion service
        request_source = self.request.headers.get("X-Request-Source")
        if request_source == "cloud-run-ingestion":
            logger.info("🔄 Request from Cloud Run ingestion service - bypassing filters")
            return File.objects.all()

        user = self.request.user
        if user.is_superuser:
            return File.objects.all()

        return File.objects.filter(Q(uploaded_by=user) | Q(team__in=user.teams.all()) | Q(is_global=True))

    def get_serializer_class(self):
        if self.action == "create":
            return UploadFileSerializer
        elif self.action == "ingest_selected":
            return FileIngestSerializer
        elif self.action == "list_files":
            return FileSerializer
        return FileSerializer

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
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        try:
            # Check auto_ingest and knowledgebase_id first
            auto_ingest = request.data.get("auto_ingest", False)
            kb_id = request.data.get("knowledgebase_id", "").strip() if auto_ingest else None

            if auto_ingest and not kb_id:
                return Response(
                    {"error": "knowledgebase_id is required when auto_ingest is True"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get knowledge base if auto_ingest is True
            kb = None
            if auto_ingest:
                try:
                    kb = KnowledgeBase.objects.get(knowledgebase_id=kb_id)
                except KnowledgeBase.DoesNotExist:
                    return Response(
                        {"error": f"Knowledge base with ID '{kb_id}' does not exist."},
                        status=status.HTTP_404_NOT_FOUND
                    )

            # Save documents to database and cloud storage
            documents = serializer.save()
            logger.info(f"✅ Successfully saved {len(documents)} documents to database")

            failed_uploads = []
            successful_uploads = []

            for document in documents:
                try:
                    if auto_ingest and kb:
                        logger.info(f"🔄 Setting up auto-ingestion for document {document.title} into KB {kb_id}")

                        # Create link in pending state
                        link = FileKnowledgeBaseLink.objects.create(
                            file=document,
                            knowledge_base=kb,
                            ingestion_status="pending",
                            chunk_size=kb.chunk_size,
                            chunk_overlap=kb.chunk_overlap,
                            embedding_model=kb.model_provider.embedder_id if kb.model_provider else None,
                        )

                        # Set auto_ingest flag and add knowledge base to the document
                        document.auto_ingest = True
                        document.save()
                        document.knowledge_bases.add(kb)

                        # Trigger ingestion
                        try:
                            self._trigger_async_ingestion(document, kb, link)
                            successful_uploads.append({
                                "file": document.title,
                                "status": "Uploaded and ingestion started",
                                "ingestion_status": "processing",
                                "link_id": link.id
                            })
                        except Exception as e:
                            logger.error(f"❌ Failed to start ingestion for document {document.title}: {e}")
                            link.ingestion_status = "failed"
                            link.ingestion_error = str(e)
                            link.save(update_fields=["ingestion_status", "ingestion_error"])
                            successful_uploads.append({
                                "file": document.title,
                                "status": "Uploaded but ingestion failed",
                                "ingestion_status": "failed",
                                "link_id": link.id,
                                "error": str(e)
                            })
                    else:
                        successful_uploads.append({
                            "file": document.title,
                            "status": "Uploaded successfully",
                            "ingestion_status": "not_requested"
                        })

                except Exception as e:
                    logger.error(f"❌ Failed to process document {document.title}: {e}")
                    failed_uploads.append({"file": document.title, "error": str(e)})

            response_data = {
                "message": f"{len(documents)} documents processed.",
                "successful_uploads": successful_uploads,
                "failed_uploads": failed_uploads,
            }

            if failed_uploads:
                return Response(response_data, status=status.HTTP_207_MULTI_STATUS)
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.exception("❌ Upload failed")
            return Response(
                {"message": "Failed to process documents", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _trigger_async_ingestion(self, document, kb, link):
        """Helper method to trigger async ingestion"""
        try:
            # Update link status to processing
            link.ingestion_status = "processing"
            link.ingestion_started_at = timezone.now()
            link.save(update_fields=["ingestion_status", "ingestion_started_at"])

            # Call Cloud Run ingestion service asynchronously
            ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
            
            # Ensure we have the correct file path format
            storage_path = document.storage_path
            if storage_path.startswith("gs://"):
                # Already in correct format
                gcs_path = storage_path
            else:
                # Add gs:// prefix and bucket name if needed
                gcs_path = f"gs://{settings.GCS_BUCKET_NAME}/{storage_path}"
            
            # Prepare payload with all necessary information
            payload = {
                "file_path": gcs_path,
                "vector_table_name": kb.vector_table_name,
                "file_uuid": str(document.uuid),
                "link_id": link.id,
                "embedding_model": kb.model_provider.embedder_id if kb.model_provider else None,
                "chunk_size": kb.chunk_size,
                "chunk_overlap": kb.chunk_overlap,
            }
            logger.info(f"📤 Sending async ingestion request with payload: {payload}")

            # Make the request in a separate thread
            import threading
            threading.Thread(
                target=self._make_async_request,
                args=(ingestion_url, payload, link),
                daemon=True
            ).start()

            logger.info(f"✅ Successfully queued ingestion for document {document.uuid}")

        except Exception as e:
            logger.error(f"❌ Failed to trigger async ingestion for document {document.uuid}: {e}")
            link.ingestion_status = "failed"
            link.ingestion_error = str(e)
            link.save(update_fields=["ingestion_status", "ingestion_error"])
            raise  # Re-raise to handle in the caller

    def _make_async_request(self, url, payload, link):
        """Helper method to make async request"""
        try:
            logger.info(f"🔄 Making request to Cloud Run service at {url}")
            
            if not settings.LLAMAINDEX_INGESTION_URL:
                raise ValueError("LLAMAINDEX_INGESTION_URL is not configured")

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Request-Source": "cloud-run-ingestion",
            }
            
            # Add system API key if available
            if hasattr(settings, 'SYSTEM_API_KEY') and settings.SYSTEM_API_KEY:
                headers['Authorization'] = f'Bearer {settings.SYSTEM_API_KEY}'
            
            logger.info(f"📤 Sending request with payload: {payload}")
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            # Log the full response for debugging
            logger.info(f"📥 Response status: {response.status_code}")
            logger.info(f"📥 Response headers: {response.headers}")
            try:
                response_json = response.json()
                logger.info(f"📥 Response body: {response_json}")
            except:
                logger.info(f"📥 Response text: {response.text}")
            
            if response.status_code >= 400:
                error_msg = f"Ingestion request failed with status {response.status_code}: {response.text}"
                logger.error(f"❌ {error_msg}")
                link.ingestion_status = "failed"
                link.ingestion_error = error_msg
                link.save(update_fields=["ingestion_status", "ingestion_error"])
                return
                
            response.raise_for_status()
            logger.info(f"✅ Successfully sent ingestion request for link {link.id}")
            
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ Configuration error: {error_msg}")
            link.ingestion_status = "failed"
            link.ingestion_error = f"Configuration error: {error_msg}"
            link.save(update_fields=["ingestion_status", "ingestion_error"])
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            link.ingestion_status = "failed"
            link.ingestion_error = error_msg
            link.save(update_fields=["ingestion_status", "ingestion_error"])
        except Exception as e:
            logger.error(f"❌ Async ingestion request failed for link {link.id}: {e}")
            link.ingestion_status = "failed"
            link.ingestion_error = str(e)
            link.save(update_fields=["ingestion_status", "ingestion_error"])

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
                description="Number of results per page (default: 10)",
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

        try:
            links = serializer.save()

            # Start ingestion for each link
            for link in links:
                try:
                    logger.info(
                        f"🔄 Queuing ingestion for file {link.file.uuid} into KB {link.knowledge_base.knowledgebase_id}"
                    )

                    # Update status to pending
                    link.ingestion_status = "pending"
                    link.save(update_fields=["ingestion_status"])

                    # Call Cloud Run ingestion service
                    ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
                    payload = {
                        "file_path": link.file.storage_path,
                        "vector_table_name": link.knowledge_base.vector_table_name,
                        "file_uuid": str(link.file.uuid),
                        "link_id": link.id,
                        "embedding_model": link.knowledge_base.model_provider.embedder_id,
                        "chunk_size": link.knowledge_base.chunk_size,
                        "chunk_overlap": link.knowledge_base.chunk_overlap,
                    }
                    logger.info(f"📤 Sending ingestion request with payload: {payload}")

                    # Use requests for synchronous call
                    response = requests.post(ingestion_url, json=payload, timeout=None)
                    response.raise_for_status()
                    logger.info(f"✅ Successfully queued ingestion for file {link.file.uuid}")

                except Exception as e:
                    logger.exception(f"❌ Failed to queue ingestion for file {link.file.uuid}")
                    link.ingestion_status = "failed"
                    link.ingestion_error = str(e)
                    link.save(update_fields=["ingestion_status", "ingestion_error"])

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

                    # Call Cloud Run ingestion service
                    ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
                    response = requests.post(
                        ingestion_url,
                        json={
                            "file_path": file.gcs_path,
                            "vector_table_name": link.knowledge_base.vector_table_name,
                            "file_uuid": str(file.uuid),
                            "link_id": link.id,
                        },
                        timeout=300,
                    )
                    response.raise_for_status()

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
                    app.handle
                except Exception as e:
                    print(f"Error sending message: {e}")
        return JsonResponse({"message": "Event received"})


def get_slack_tools():
    return SlackTools(token=settings.SLACK_BOT_TOKEN)


# Initialize Agent tools (only once)
slack_tools = get_slack_tools()


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
        agent = Agent(tools=[slack_tools], show_tool_calls=True)

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

    def event_stream():
        total_start = time.time()

        build_start = time.time()
        builder = AgentBuilder(agent_id=agent_id, user=request.user, session_id=session_id)
        agent = builder.build()
        build_time = time.time() - build_start
        yield f"data: {json.dumps({'debug': f'Agent build time: {build_time:.2f}s'})}\n\n"

        buffer = ""
        chunk_count = 0
        debug_mode = getattr(agent, "debug_mode", False)

        tools_sent = False  # ✅ Add this flag

        try:
            run_start = time.time()
            for chunk in agent.run(message, stream=True):
                chunk_count += 1

                if chunk.content:
                    buffer += chunk.content
                    if len(buffer) > 100:
                        yield f"data: {json.dumps({'token': buffer, 'markdown': True})}\n\n"
                        buffer = ""

                if chunk.citations:
                    yield f"data: {json.dumps({'citations': chunk.citations})}\n\n"

                if chunk.tools:
                    try:
                        serialized_tools = [str(tool) for tool in chunk.tools]
                        if not tools_sent:
                            yield f"data: {json.dumps({'tools': serialized_tools})}\n\n"
                            tools_sent = True  # set AFTER successfully yielding
                    except Exception as e:
                        logger.warning(f"[Agent:{agent.name}] Failed to serialize tools: {e}")

                if debug_mode:
                    raw_payload = chunk.dict() if hasattr(chunk, "dict") else str(chunk)
                    logger.debug(f"[Agent:{agent.name}] Raw chunk: {raw_payload}")
                    if chunk_count % 10 == 0:
                        logger.debug(f"[Agent:{agent.name}] {chunk_count} chunks processed")

            run_time = time.time() - run_start
            yield f"data: {json.dumps({'debug': f'agent.run total time: {run_time:.2f}s'})}\n\n"

            if buffer:
                yield f"data: {json.dumps({'token': buffer, 'markdown': True})}\n\n"

        except Exception as e:
            logger.exception(f"[Agent:{agent_id}] Error during streaming response")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        total_time = time.time() - total_start
        yield f"data: {json.dumps({'debug': f'Total stream time: {total_time:.2f}s'})}\n\n"
        yield "data: [DONE]\n\n"

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
    def get_session_messages(self, request, uuid=None):
        try:
            session = ChatSession.objects.get(uuid=uuid, user=request.user)
        except ChatSession.DoesNotExist:
            return Response({"error": "Session not found."}, status=404)

        db_url = getattr(settings, "DATABASE_URL", None)
        if not db_url:
            return Response({"error": "DATABASE_URL is not configured."}, status=500)

        storage = PostgresAgentStorage(table_name="reggie_storage_sessions", db_url=db_url)
        messages = storage.get_messages_for_session(session_id=str(session.id))

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
            kb = KnowledgeBase.objects.get(id=kb_id)
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
        ingest_single_file.delay(str(file_obj.uuid), kb.id)

        return Response({"message": "File ingestion started", "link_id": link.id})

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
