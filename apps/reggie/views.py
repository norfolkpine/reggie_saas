from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from .models import Agent, AgentInstruction
from .serializers import AgentSerializer, AgentInstructionSerializer

class AgentViewSet(viewsets.ModelViewSet):
    """
    API endpoint to create, update, and retrieve AI Agents.
    """
    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Users can see:
        - Agents they own
        - Agents shared with their team
        - Global agents
        """
        user = self.request.user
        return Agent.objects.filter(Q(user=user) | Q(team__members=user) | Q(is_global=True)).distinct()

    def perform_create(self, serializer):
        """
        Assigns the logged-in user as the owner when creating an agent.
        """
        serializer.save(user=self.request.user)

class AgentInstructionViewSet(viewsets.ModelViewSet):
    """
    API endpoint to create, update, and retrieve AI Agent Instructions.
    """
    serializer_class = AgentInstructionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Users can see:
        - Instructions for their agents
        - Global instructions
        - Instructions for team-shared agents
        """
        user = self.request.user
        return AgentInstruction.objects.filter(Q(user=user) | Q(agent__team__members=user) | Q(is_global=True)).distinct()

    def perform_create(self, serializer):
        """
        Assigns the logged-in user when creating an instruction.
        """
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def toggle_enabled(self, request, pk=None):
        """
        API endpoint to enable/disable an instruction.
        """
        instruction = self.get_object()
        instruction.is_enabled = not instruction.is_enabled
        instruction.save()
        return Response({"status": "success", "is_enabled": instruction.is_enabled})
