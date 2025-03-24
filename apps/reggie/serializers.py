from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import (
    Agent, AgentInstruction, AgentOutput, StorageBucket, KnowledgeBase, Tag, Project, Document, DocumentTag
)
from apps.teams.models import Team

class AgentSerializer(serializers.ModelSerializer):
    instructions = serializers.SerializerMethodField()

    class Meta:
        model = Agent
        fields = '__all__'  # Ensure it includes `instructions`

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_instructions(self, obj):
        """Fetch active instructions for the agent."""
        return AgentInstructionSerializer(obj.get_active_instructions(), many=True).data



class AgentInstructionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentInstruction
        fields = '__all__'

class AgentOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentOutput
        fields = '__all__'

class StorageBucketSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorageBucket
        fields = '__all__'


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBase
        fields = '__all__'


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = '__all__'


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = '__all__'


class DocumentTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentTag
        fields = '__all__'


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'


class BulkDocumentUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=False)
    )
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), required=False)

    def create(self, validated_data):
        user = self.context['request'].user
        team = validated_data.get('team', None)
        title = validated_data.get('title', None)
        description = validated_data.get('description', "")

        documents = []
        for file in validated_data['files']:
            document = Document.objects.create(
                file=file,
                uploaded_by=user,
                team=team,
                title=title or file.name,
                description=description
            )
            documents.append(document)
        return documents