# === Standard Library ===
import json
import logging
import time
from datetime import timezone

import requests

# === Agno ===
from agno.agent import Agent
from agno.knowledge.pdf_url import PDFUrlKnowledgeBase
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.slack import SlackTools
from agno.vectordb.pgvector import PgVector
from django.conf import settings

# === Django ===
from django.db.models import Q
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

# === DRF Spectacular ===
from drf_spectacular.utils import extend_schema

# === Django REST Framework ===
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    permission_classes,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from slack_sdk import WebClient

from apps.reggie.utils.gcs_utils import ingest_gcs_prefix, ingest_single_file
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
    FileTag,
    KnowledgeBase,
    KnowledgeBasePdfURL,
    ModelProvider,
    Project,
    StorageBucket,
    Tag,
)
from .serializers import (
    AgentExpectedOutputSerializer,
    AgentInstructionSerializer,
    AgentSerializer,
    BulkFileUploadSerializer,
    ChatSessionSerializer,
    FileSerializer,
    FileTagSerializer,
    KnowledgeBasePdfURLSerializer,
    KnowledgeBaseSerializer,
    ModelProviderSerializer,
    ProjectSerializer,
    StorageBucketSerializer,
    StreamAgentRequestSerializer,
    TagSerializer,
)

logger = logging.getLogger(__name__)


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


@extend_schema(tags=["Agents"])
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


@extend_schema(tags=["Agent Templates"])
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_global_templates(request):
    """
    Returns global instruction templates and expected output templates.
    """
    instructions = AgentInstruction.objects.filter(is_enabled=True, is_global=True)
    outputs = AgentExpectedOutput.objects.filter(is_enabled=True, is_global=True)

    return Response(
        {
            "instructions": AgentInstructionSerializer(instructions, many=True).data,
            "expected_outputs": AgentExpectedOutputSerializer(outputs, many=True).data,
        }
    )


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
    serializer_class = FileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        document = serializer.save(uploaded_by=self.request.user)

        try:
            file_path = document.file.name
            vector_table_name = (
                document.team.default_knowledge_base.vector_table_name if document.team else "pdf_documents"
            )

            ingest_single_file(file_path, vector_table_name)
            logger.info(f"✅ Single document {document.id} ingestion triggered successfully.")
        except Exception as e:
            logger.exception(f"❌ Ingestion trigger failed for document {document.id}: {e}")

    @extend_schema(
        operation_id="Bulk Upload Files",
        summary="Upload multiple documents",
        description="Allows users to bulk upload multiple documents in a single request.",
        request=BulkFileUploadSerializer,
        responses={201: {"description": "Bulk upload successful"}},
    )
    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):
        """
        Custom action to handle bulk document uploads.
        Handles both database storage and cloud storage upload.
        Only ingests files if auto_ingest is True.
        """
        serializer = BulkFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Save documents to database and cloud storage
            documents = serializer.save(uploaded_by=request.user)
            
            # Process each document
            for document in documents:
                # The file is automatically uploaded to cloud storage via Django's storage backend
                # which is configured to use GCS in settings.py
                
                # Set GCS path if not already set
                if not document.gcs_path:
                    document.gcs_path = document.file.name
                    document.save(update_fields=['gcs_path'])
                
                # Only ingest if auto_ingest is True and document has a knowledge base
                if document.auto_ingest and document.knowledge_base:
                    try:
                        # Update status to processing
                        document.ingestion_status = 'processing'
                        document.ingestion_started_at = timezone.now()
                        document.save(update_fields=['ingestion_status', 'ingestion_started_at'])
                        
                        # Call Cloud Run ingestion service
                        ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
                        response = requests.post(
                            ingestion_url,
                            json={
                                "file_path": document.gcs_path,
                                "vector_table_name": document.knowledge_base.vector_table_name,
                                "file_id": document.id  # Pass file ID for progress tracking
                            },
                            timeout=300  # 5 minute timeout
                        )
                        response.raise_for_status()
                        
                    except Exception as e:
                        document.ingestion_status = 'failed'
                        document.ingestion_error = str(e)
                        document.save(update_fields=['ingestion_status', 'ingestion_error'])
                        logger.error(f"❌ Failed to auto-ingest document {document.id} via Cloud Run: {e}")
            
            return Response(
                {"message": f"{len(documents)} documents uploaded successfully."},
                status=status.HTTP_201_CREATED,
            )
            
        except Exception as e:
            logger.exception("❌ Bulk upload failed")
            return Response(
                {"error": f"Failed to upload documents: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"], url_path="update-progress")
    def update_progress(self, request, pk=None):
        """
        Update the ingestion progress of a file.
        Called by Cloud Run service during ingestion.
        """
        try:
            document = self.get_object()
            progress_data = request.data
            
            document.ingestion_progress = progress_data.get('progress', 0.0)
            document.processed_docs = progress_data.get('processed_docs', 0)
            document.total_docs = progress_data.get('total_docs', 0)
            
            # If progress is 100%, mark as completed
            if document.ingestion_progress >= 100:
                document.ingestion_status = 'completed'
                document.is_ingested = True
                document.ingestion_completed_at = timezone.now()
            
            document.save(update_fields=[
                'ingestion_progress',
                'processed_docs',
                'total_docs',
                'ingestion_status',
                'is_ingested',
                'ingestion_completed_at'
            ])
            
            return Response({"message": "Progress updated successfully"})
            
        except Exception as e:
            logger.exception(f"❌ Failed to update progress for file {pk}: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=["post"], url_path="ingest-selected")
    def ingest_selected(self, request):
        """
        Manually ingest selected files.
        Expects a list of file IDs in the request.
        """
        file_ids = request.data.get('file_ids', [])
        if not file_ids:
            return Response(
                {"error": "No file IDs provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            files = File.objects.filter(
                id__in=file_ids,
                uploaded_by=request.user,
                is_ingested=False  # Only process uningested files
            )

            results = {
                "success": [],
                "failed": []
            }

            for file in files:
                if not file.knowledge_base:
                    results["failed"].append({
                        "id": file.id,
                        "error": "No knowledge base associated with file"
                    })
                    continue

                try:
                    # Update status to processing
                    file.ingestion_status = 'processing'
                    file.ingestion_started_at = timezone.now()
                    file.save(update_fields=['ingestion_status', 'ingestion_started_at'])
                    
                    # Call Cloud Run ingestion service
                    ingestion_url = f"{settings.LLAMAINDEX_INGESTION_URL}/ingest-file"
                    response = requests.post(
                        ingestion_url,
                        json={
                            "file_path": file.gcs_path,
                            "vector_table_name": file.knowledge_base.vector_table_name
                        },
                        timeout=300  # 5 minute timeout
                    )
                    response.raise_for_status()
                    
                    # Update status to completed
                    file.ingestion_status = 'completed'
                    file.is_ingested = True
                    file.ingestion_completed_at = timezone.now()
                    file.save(update_fields=[
                        'ingestion_status', 
                        'is_ingested', 
                        'ingestion_completed_at'
                    ])
                    
                    results["success"].append({
                        "id": file.id,
                        "message": "Ingestion completed successfully"
                    })
                    logger.info(f"✅ Document {file.id} manually ingested successfully via Cloud Run.")
                except Exception as e:
                    file.ingestion_status = 'failed'
                    file.ingestion_error = str(e)
                    file.save(update_fields=['ingestion_status', 'ingestion_error'])
                    
                    results["failed"].append({
                        "id": file.id,
                        "error": str(e)
                    })
                    logger.error(f"❌ Failed to manually ingest document {file.id} via Cloud Run: {e}")

            return Response({
                "message": f"Processed {len(files)} files",
                "results": results
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception("❌ Manual ingestion failed")
            return Response(
                {"error": f"Failed to process files: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["post"], url_path="reingest")
    def reingest(self, request, pk=None):
        """
        Manually trigger re-ingestion of a single file via Cloud Run.
        Useful for admin/debugging purposes.
        """
        try:
            document = self.get_object()

            file_path = document.file.name
            vector_table_name = (
                document.team.default_knowledge_base.vector_table_name if document.team else "pdf_documents"
            )

            ingest_single_file(file_path, vector_table_name)
            return Response({"message": f"✅ Ingestion triggered for file {document.id}"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"❌ Reingestion failed for file {pk}: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
    def get_session_messages(self, request, pk=None):
        try:
            session = ChatSession.objects.get(pk=pk, user=request.user)
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
