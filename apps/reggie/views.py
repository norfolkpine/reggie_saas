# === Standard Library ===
import json
import requests

# === Django ===
from django.conf import settings
from django.http import (
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt

# === Django REST Framework ===
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import (
    action,
    api_view,
    permission_classes,
)
from rest_framework.response import Response

# === DRF Spectacular ===
from drf_spectacular.utils import extend_schema

# === External SDKs ===
from slack_sdk.errors import SlackApiError

# === Agno ===
from agno.agent import Agent
from agno.tools.slack import SlackTools

# === Local ===
from .models import (
    Agent as DjangoAgent,  # avoid conflict with agno.Agent
    AgentInstruction,
    AgentExpectedOutput,
    StorageBucket,
    KnowledgeBase,
    Tag,
    Project,
    Document,
    DocumentTag,
    SlackWorkspace,
)
from .serializers import (
    AgentSerializer,
    AgentInstructionSerializer,
    AgentExpectedOutputSerializer,
    StorageBucketSerializer,
    KnowledgeBaseSerializer,
    TagSerializer,
    ProjectSerializer,
    DocumentSerializer,
    DocumentTagSerializer,
    BulkDocumentUploadSerializer,
)
from .agents.agent_builder import AgentBuilder  # Adjust path if needed

@extend_schema(tags=["Agents"])
class AgentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing agents.
    """
    queryset = DjangoAgent.objects.all()
    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated]

@api_view(["GET"])
def get_agent_instructions(request, agent_id):
    """Fetch active instructions for a specific agent."""
    try:
        agent = Agent.objects.get(id=agent_id)
        instructions = agent.get_active_instructions()
        serializer = AgentInstructionSerializer(instructions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Agent.DoesNotExist:
        return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

@api_view(["GET"])
def get_agent_expected_output(request, agent_id):
    """Fetch active expected output for a specific agent. There should only be one active expected output, maybe enforce get first"""
    try:
        agent = Agent.objects.get(id=agent_id)
        expected_output = agent.get_active_outputs()
        serializer = AgentExpectedOutputSerializer(expected_output, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Agent.DoesNotExist:
        return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)


@extend_schema(tags=["Agent Instructions"])
class AgentInstructionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing agent instructions.
    """
    queryset = AgentInstruction.objects.all()
    serializer_class = AgentInstructionSerializer
    permission_classes = [permissions.IsAuthenticated]

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


@extend_schema(tags=["Documents"])
class DocumentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing documents.
    """
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)

    @extend_schema(
        operation_id="Bulk Upload Documents",
        summary="Upload multiple documents",
        description="Allows users to bulk upload multiple documents in a single request.",
        request=BulkDocumentUploadSerializer,
        responses={201: {"description": "Bulk upload successful"}},
    )
    @action(detail=False, methods=["post"], url_path="bulk-upload")
    def bulk_upload(self, request):
        """
        Custom action to handle bulk document uploads.
        """
        serializer = BulkDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documents = serializer.save()
        return Response(
            {"message": f"{len(documents)} documents uploaded successfully."},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Document Tags"])
class DocumentTagViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing document tags.
    """
    queryset = DocumentTag.objects.all()
    serializer_class = DocumentTagSerializer
    permission_classes = [permissions.IsAuthenticated]

# Slackbot webhook
@csrf_exempt
def slack_events(request):
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
                client.chat_postMessage(
                    channel=event["channel"],
                    text=f"Hello! You mentioned me: {event['text']}"
                )

        return JsonResponse({"message": "Event received"})

# Initialize Agent tools (only once)
slack_tools = SlackTools()

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
    scopes = [
        "app_mentions:read",
        "channels:read",
        "chat:write",
        "im:read",
        "users:read"
    ]
    scope_str = ",".join(scopes)
    install_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}&scope={scope_str}&redirect_uri={redirect_uri}"
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
    response = requests.post("https://slack.com/api/oauth.v2.access", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }).json()

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
            "bot_user_id": response.get("bot_user_id")
        }
    )

    return HttpResponse("🎉 Slack successfully connected to your workspace!")

from .agents.agent_builder import AgentBuilder

# Sample view or function
def init_agent(user, agent_name, session_id):
    builder = AgentBuilder(agent_name=agent_name, user=user, session_id=session_id)
    agent = builder.build()
    return agent


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def stream_agent_response(request):
    agent_name = request.data.get("agent_name")
    message = request.data.get("message")
    session_id = request.data.get("session_id")

    if not all([agent_name, message, session_id]):
        return Response({"error": "Missing required parameters."}, status=400)

    def event_stream():
        builder = AgentBuilder(agent_name=agent_name, user=request.user, session_id=session_id)
        agent = builder.build()

        try:
            for chunk in agent.run_stream(message):
                yield f"data: {json.dumps({'token': chunk.message.content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
