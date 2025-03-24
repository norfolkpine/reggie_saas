from rest_framework import viewsets, generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from agno.agent import Agent
from agno.tools.slack import SlackTools
from .models import Agent as DjangoAgent  

from .models import (
    Agent, AgentInstruction, AgentExpectedOutput, StorageBucket, KnowledgeBase, Tag, Project, Document, DocumentTag
)
from .serializers import (
    AgentSerializer, AgentInstructionSerializer, AgentExpectedOutputSerializer, StorageBucketSerializer, KnowledgeBaseSerializer, 
    TagSerializer, ProjectSerializer, DocumentSerializer, DocumentTagSerializer, BulkDocumentUploadSerializer
)

from slack_sdk.errors import SlackApiError
from .agents.slack_client import client  # Import from slack_client.py

@extend_schema(tags=["Agents"])
class AgentViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows managing agents.
    """
    queryset = Agent.objects.all()
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
