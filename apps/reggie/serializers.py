from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import (
    Agent, AgentInstruction, AgentExpectedOutput, StorageBucket, KnowledgeBase, Tag, Project, Document, DocumentTag
)
from apps.teams.models import Team

# class AgentSerializer(serializers.ModelSerializer):
#     instructions = serializers.SerializerMethodField()

#     class Meta:
#         model = Agent
#         fields = '__all__'  # Ensure it includes `instructions`

#     @extend_schema_field(serializers.ListField(child=serializers.CharField()))
#     def get_instructions(self, obj):
#         """Fetch active instructions for the agent."""
#         return AgentInstructionSerializer(obj.get_active_instructions(), many=True).data

class AgentInstructionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentInstruction
        fields = '__all__'

class AgentExpectedOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentExpectedOutput
        fields = '__all__'


class AgentSerializer(serializers.ModelSerializer):
    instructions = serializers.SerializerMethodField()
    expected_output = AgentExpectedOutputSerializer(read_only=True)  # Return full details
    expected_output_id = serializers.PrimaryKeyRelatedField(
        queryset=AgentExpectedOutput.objects.all(),
        source="expected_output",
        write_only=True,
        required=False
    )
    expected_output_data = AgentExpectedOutputSerializer(write_only=True, required=False)  # Allows creating a new expected output

    class Meta:
        model = Agent
        fields = '__all__'  # Includes instructions, expected_output, and creation fields

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_instructions(self, obj):
        """Fetch active instructions for the agent."""
        return AgentInstructionSerializer(obj.get_active_instructions(), many=True).data

    def create(self, validated_data):
        """Allow creating an agent with either an existing expected output or a new one."""
        expected_output_data = validated_data.pop("expected_output_data", None)
        expected_output_id = validated_data.pop("expected_output", None)  # Comes from `expected_output_id`

        if expected_output_data:
            expected_output = AgentExpectedOutput.objects.create(**expected_output_data)
        elif expected_output_id:
            expected_output = expected_output_id
        else:
            expected_output = None

        agent = Agent.objects.create(expected_output=expected_output, **validated_data)
        return agent

    def update(self, instance, validated_data):
        """Allow updating an agent with either an existing expected output or creating a new one."""
        expected_output_data = validated_data.pop("expected_output_data", None)
        expected_output_id = validated_data.pop("expected_output", None)

        if expected_output_data:
            expected_output = AgentExpectedOutput.objects.create(**expected_output_data)
            instance.expected_output = expected_output
        elif expected_output_id:
            instance.expected_output = expected_output_id

        return super().update(instance, validated_data)


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