from rest_framework import serializers
from .models import Agent, AgentInstruction

class AgentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)  # Show username instead of ID

    class Meta:
        model = Agent
        fields = ['id', 'user', 'name', 'description', 'search_knowledge', 'is_global', 'team', 'subscriptions', 'created_at']
        read_only_fields = ['user', 'created_at']

class AgentInstructionSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)  # Show username instead of ID
    agent_name = serializers.CharField(source='agent.name', read_only=True)  # Show agent name instead of ID

    class Meta:
        model = AgentInstruction
        fields = ['id', 'user', 'agent', 'agent_name', 'instruction', 'category', 'is_enabled', 'is_global', 'created_at']
        read_only_fields = ['user', 'agent_name', 'created_at']
