# ==========================
# apps/reggie/models.py
# ==========================

from django.db import models
from apps.users.models import CustomUser
from apps.teams.models import Team
from apps.utils.models import BaseModel


class InstructionCategory(models.TextChoices):
    SCOPE = "Scope & Knowledge Boundaries", "Scope & Knowledge Boundaries"
    RETRIEVAL = "Information Retrieval & Accuracy", "Information Retrieval & Accuracy"
    RESPONSE_FORMATTING = "Response Handling & Formatting", "Response Handling & Formatting"
    COMPLIANCE = "Compliance-Specific Instructions", "Compliance-Specific Instructions"
    PERSONALITY = "Personality", "Personality"
    PROCESS = "Process", "Process"
    IMPROVEMENT = "Improvement", "Improvement"


class Agent(BaseModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='owned_agents')
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, null=True, blank=True, related_name='agents')
    knowledge_base = models.ForeignKey('KnowledgeBase', on_delete=models.SET_NULL, null=True, blank=True)
    is_global = models.BooleanField(default=False)
    show_tool_calls = models.BooleanField(default=True)
    markdown_enabled = models.BooleanField(default=True)
    search_knowledge = models.BooleanField(default=True)
    add_datetime_to_instructions = models.BooleanField(default=True)
    subscriptions = models.ManyToManyField('djstripe.Subscription', related_name='agents', blank=True)

    def get_agno_agent(self, session_id=None):
        from apps.reggie.agno_assist.agent import initialize_knowledge_base, get_agent_storage
        from agno.agent import Agent as AgnoAgent
        from agno.models.openai import OpenAIChat
        from agno.tools.python import PythonTools

        knowledge = initialize_knowledge_base(load_knowledge=False)
        combined_instructions = "\n".join([
            i.instruction for i in self.instructions.filter(is_enabled=True)
        ])

        return AgnoAgent(
            name=self.name,
            session_id=session_id,
            model=OpenAIChat(id="gpt-4o"),
            description=self.description,
            instructions=combined_instructions,
            knowledge=knowledge,
            tools=[PythonTools()],
            storage=get_agent_storage(),
            add_history_to_messages=True,
            num_history_responses=3,
            show_tool_calls=self.show_tool_calls,
            read_chat_history=True,
            markdown=self.markdown_enabled,
        )


class AgentInstruction(BaseModel):
    agent = models.ForeignKey('Agent', on_delete=models.CASCADE, related_name='instructions', null=True, blank=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='agent_instructions')
    instruction = models.TextField()
    category = models.CharField(max_length=100, choices=InstructionCategory.choices, default=InstructionCategory.PROCESS)
    is_enabled = models.BooleanField(default=True)
    is_global = models.BooleanField(default=False)


class KnowledgeBase(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    path = models.CharField(max_length=500, blank=True, null=True)
    vector_table_name = models.CharField(max_length=255, unique=True)


# ==========================
# apps/reggie/agno_assist/agent.py
# ==========================

from pathlib import Path
from textwrap import dedent
from typing import Optional
from agno.agent import Agent
from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge.url import UrlKnowledge
from agno.models.openai import OpenAIChat
from agno.storage.agent.sqlite import SqliteAgentStorage
from agno.tools.python import PythonTools
from agno.vectordb.lancedb import LanceDb, SearchType

cwd = Path(__file__).parent
tmp_dir = cwd.joinpath("tmp")
tmp_dir.mkdir(parents=True, exist_ok=True)

def initialize_knowledge_base(load_knowledge: bool = False):
    agent_knowledge = UrlKnowledge(
        urls=["https://docs.agno.com/llms-full.txt"],
        vector_db=LanceDb(
            uri=str(tmp_dir.joinpath("lancedb")),
            table_name="agno_assist_knowledge",
            search_type=SearchType.hybrid,
            embedder=OpenAIEmbedder(id="text-embedding-3-small"),
        ),
    )
    if load_knowledge:
        agent_knowledge.load()
    return agent_knowledge

def get_agent_storage():
    return SqliteAgentStorage(
        table_name="agno_assist_sessions", db_file=str(tmp_dir.joinpath("agents.db"))
    )

# ==========================
# apps/reggie/views.py
# ==========================

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from apps.reggie.models import Agent


class DynamicAgentChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        question = request.data.get("question")
        session_id = request.data.get("session_id")
        agent_id = request.data.get("agent_id")

        if not question or not agent_id:
            return Response({"error": "Question and agent_id are required."}, status=400)

        agent_instance = Agent.objects.filter(id=agent_id).first()

        if not agent_instance:
            return Response({"error": "Agent not found."}, status=404)

        # Load dynamic Agno Agent
        agno_agent = agent_instance.get_agno_agent(session_id=session_id)
        response = agno_agent.run(question)

        return Response({
            "response": response,
            "session_id": agno_agent.session_id
        }, status=200)

# ==========================
# apps/reggie/urls.py
# ==========================

from django.urls import path
from apps.reggie.views import DynamicAgentChatView

urlpatterns = [
    path('dynamic-chat/', DynamicAgentChatView.as_view(), name='dynamic-chat'),
]

# ==========================
# apps/reggie/admin.py
# ==========================

from django.contrib import admin
from apps.reggie.models import Agent, AgentInstruction, KnowledgeBase

@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'team', 'is_global', 'created_at')
    list_filter = ('is_global', 'team')
    search_fields = ('name',)

@admin.register(AgentInstruction)
class AgentInstructionAdmin(admin.ModelAdmin):
    list_display = ('instruction', 'agent', 'user', 'is_enabled', 'is_global', 'created_at')
    list_filter = ('is_enabled', 'is_global', 'category')

@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'vector_table_name', 'created_at')
