# === Standard Library ===
import json
import os
import re

import requests

# === Agno ===
from agno.agent import Agent

# === Django ===
from django.conf import settings
from django.db.models import Q
from django.http import (
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
from rest_framework.response import Response
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient

# from agno.tools.slack import SlackTools
from apps.reggie.agents.tools.custom_slack import SlackTools
from apps.utils.slack import slack_verified

# === External SDKs ===
from .agents.agent_builder import AgentBuilder  # Adjust path if needed

# === Local ===
from .models import (
    Agent as DjangoAgent,  # avoid conflict with agno.Agent
)
from .models import (
    AgentExpectedOutput,
    AgentInstruction,
    Document,
    DocumentTag,
    KnowledgeBase,
    Project,
    SlackWorkspace,
    StorageBucket,
    Tag,
)
from .serializers import (
    AgentExpectedOutputSerializer,
    AgentInstructionSerializer,
    AgentSerializer,
    BulkDocumentUploadSerializer,
    DocumentSerializer,
    DocumentTagSerializer,
    KnowledgeBaseSerializer,
    ProjectSerializer,
    StorageBucketSerializer,
    StreamAgentRequestSerializer,
    TagSerializer,
)


def get_slack_tools():
    return SlackTools(token=os.getenv("SLACK_TOKEN"))


# Initialize Agent tools (only once)
slack_tools = get_slack_tools()

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


@api_view(["GET"])
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
web_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
auth_info = web_client.auth_test()
BOT_USER_ID = auth_info["user_id"]

def extract_channel_and_ts(url: str) -> tuple:
    pattern = r'https://([a-zA-Z0-9\-]+)\.slack\.com/archives/([A-Za-z0-9]+)/p([0-9]+)'
    
    match = re.match(pattern, url)
    
    if match:
        channel = match.group(2) 
        ts = match.group(3)  
        
        ts_standard = f"{ts[:10]}.{ts[10:]}"
        
        return channel, ts_standard
    else:
        raise ValueError("Invalid Slack message URL format")
    
@csrf_exempt
def slack_events(request):
    """Handle incoming Slack events like mentions."""
    if request.method == "POST":
        data = json.loads(request.body)

        # Slack verification challenge
    if "challenge" in data:
        return HttpResponse(data.get("challenge"), content_type="text/plain", status=200)


    text = data.get("text", "").strip()
    event = data.get("event", {})
    user = event.get("user")
    bot_id = event.get("bot_id")
    if bot_id or user == BOT_USER_ID:
        print("🤖 Ignoring bot message.")
        return JsonResponse(data={},status=200)

    event_type = event.get("type")
    channel = event.get("channel")
    channel_type = event.get("channel_type")
    text = event.get("text", "").strip()
    thread_ts = event.get("thread_ts") or event.get("ts")  # thread_ts or message timestamp
    message_ts = event.get("ts")

    # React to acknowledge
    try:
        web_client.reactions_add(
            name="eyes",
            channel=channel,
            timestamp=event["ts"]
        )
    except Exception as e:
        print(f"⚠️ Failed to react to message: {e}")
        return JsonResponse(data={},status=200)

        
    agent = Agent(
        tools=[slack_tools], 
        show_tool_calls=True,
        debug_mode=True,
        instructions= [
            "If translating, return only the translated text. Use slack_tools.",
            """
                If replying as reggie on slack, use slack_tools. 
                ALWAYS refer to context from received input before doing anything (contains sender as from_user, channel, thread_ts as the timestamp to reply to if needed and message itself); 
                    all further instructions will be based on this context.
                ALWAYS try to validate the decision to reply on a thread or reply on channel by validating with is_thread_valid, then use tools accordingly;
                    if it's a thread, do get_thread_history and if it's a single message, do get_channel_history. 
                FINALLY, always send_message back (either reply to thread or as a mesage on the channel). ALWAYS.
            """,
            "Format using currency symbols",
        ],
    )

    try:
        if event_type == "app_mention":
            if "<@U08JZ8L8TPA>" in text:
                text = text.replace("<@U08JZ8L8TPA>", "").strip()
            
            data = {
                "type": "slack",
                "from_user": user,
                "channel": channel,
                "thread_ts": thread_ts,
                "message": text,
            }
            response = agent.run(message=str(data), markdown=True).to_dict().get("content", "")

        elif event_type == "message" and channel_type == "im":
            print(f"📩 DM from <@{user}>: {text}")
            response = agent.run(text)
            web_client.chat_postMessage(
                channel=channel,
                text=response.content.strip(),
                thread_ts=thread_ts
            )

        else:
            print("ℹ️ Event type not supported.")

    except Exception as e:
        print(f"❌ Error in event handler: {e}")
        web_client.chat_postMessage(
            channel=channel,
            text="⚠️ Sorry, something went wrong while processing your request."
        )

    return JsonResponse({"message": "Event received"}, status=200)



@csrf_exempt
@slack_verified
def agent_request(request, agent_id):
    """Handles Slack interactions for a specific agent via URL path."""
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
        
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
        
    if payload.get("type") == "url_verification":
        return HttpResponse(payload.get("challenge"), content_type="text/plain", status=200)

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
    response = agent.run(prompt, markdown=True).to_dict().get("content", "")
    if not response:
        return JsonResponse({"error": "No response from agent"}, status=500)


    return JsonResponse({"agent_id": agent_obj.id, "response": response})


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
def init_agent(user, agent_name, session_id):
    builder = AgentBuilder(agent_name=agent_name, user=user, session_id=session_id)
    agent = builder.build()
    return agent


@csrf_exempt
@extend_schema(
    request=StreamAgentRequestSerializer,
    responses={200: {"type": "string", "description": "Server-Sent Events stream"}},
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
        builder = AgentBuilder(agent_id=agent_id, user=request.user, session_id=session_id)
        agent = builder.build()

        buffer = ""
        try:
            for chunk in agent.run(message, stream=True):
                if chunk.content:
                    buffer += chunk.content

                    # Send buffered content if it passes a threshold
                    if len(buffer) > 30:
                        yield f"data: {json.dumps({'token': buffer, 'markdown': True})}\n\n"
                        buffer = ""

                # Optionally stream citations if available
                if chunk.citations:
                    yield f"data: {json.dumps({'citations': chunk.citations})}\n\n"

            # Flush any remaining buffer
            if buffer:
                yield f"data: {json.dumps({'token': buffer, 'markdown': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Signal end of stream
        yield "data: [DONE]\n\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")

