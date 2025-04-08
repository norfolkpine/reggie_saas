from rest_framework import serializers

from apps.teams.models import Team

from .models import (
    Agent,
    AgentExpectedOutput,
    AgentInstruction,
    ChatSession,
    Document,
    DocumentTag,
    KnowledgeBase,
    Project,
    StorageBucket,
    Tag,
)

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
        fields = "__all__"


class AgentExpectedOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentExpectedOutput
        fields = "__all__"


class AgentSerializer(serializers.ModelSerializer):
    # Return full details of related expected output
    expected_output = AgentExpectedOutputSerializer(read_only=True)
    expected_output_id = serializers.PrimaryKeyRelatedField(
        queryset=AgentExpectedOutput.objects.all(), source="expected_output", write_only=True, required=False
    )
    expected_output_data = AgentExpectedOutputSerializer(write_only=True, required=False)

    # Instruction: same logic (1 assigned instruction or new)
    instructions = AgentInstructionSerializer(read_only=True)
    instructions_id = serializers.PrimaryKeyRelatedField(
        queryset=AgentInstruction.objects.all(), source="instructions", write_only=True, required=False
    )
    custom_instruction = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Agent
        fields = [
            "id",
            "name",
            "description",
            "category",
            "model",
            "instructions",
            "instructions_id",
            "custom_instruction",
            "expected_output",
            "expected_output_id",
            "expected_output_data",
            "knowledge_base",
            "search_knowledge",
            "cite_knowledge",
            "add_datetime_to_instructions",
            "show_tool_calls",
            "markdown_enabled",
            "debug_mode",
            "num_history_responses",
            "is_global",
            "team",
            "subscriptions",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        user = self.context["request"].user

        # Handle expected output creation
        expected_output_data = validated_data.pop("expected_output_data", None)
        expected_output_id = validated_data.pop("expected_output", None)

        if expected_output_data:
            expected_output = AgentExpectedOutput.objects.create(user=user, **expected_output_data)
        else:
            expected_output = expected_output_id

        # Handle instruction creation
        custom_instruction = validated_data.pop("custom_instruction", None)
        instructions_id = validated_data.pop("instructions", None)

        if custom_instruction:
            instruction = AgentInstruction.objects.create(
                user=user,
                instruction=custom_instruction,
                is_global=False,
                is_enabled=True,
                is_system=False,
                title="Custom",
            )
        else:
            instruction = instructions_id

        return Agent.objects.create(
            user=user, expected_output=expected_output, instructions=instruction, **validated_data
        )

    def update(self, instance, validated_data):
        user = self.context["request"].user

        expected_output_data = validated_data.pop("expected_output_data", None)
        expected_output_id = validated_data.pop("expected_output", None)
        custom_instruction = validated_data.pop("custom_instruction", None)
        instructions_id = validated_data.pop("instructions", None)

        if expected_output_data:
            instance.expected_output = AgentExpectedOutput.objects.create(user=user, **expected_output_data)
        elif expected_output_id:
            instance.expected_output = expected_output_id

        if custom_instruction:
            instance.instructions = AgentInstruction.objects.create(
                user=user,
                instruction=custom_instruction,
                is_global=False,
                is_enabled=True,
                is_system=False,
                title="Custom",
            )
        elif instructions_id:
            instance.instructions = instructions_id

        return super().update(instance, validated_data)


class StorageBucketSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorageBucket
        fields = "__all__"


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBase
        fields = "__all__"


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = "__all__"


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"


class DocumentTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentTag
        fields = "__all__"


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = "__all__"


class BulkDocumentUploadSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=False))
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), required=False)

    def create(self, validated_data):
        user = self.context["request"].user
        team = validated_data.get("team", None)
        title = validated_data.get("title", None)
        description = validated_data.get("description", "")

        documents = []
        for file in validated_data["files"]:
            document = Document.objects.create(
                file=file, uploaded_by=user, team=team, title=title or file.name, description=description
            )
            documents.append(document)
        return documents


class StreamAgentRequestSerializer(serializers.Serializer):
    agent_id = serializers.CharField(help_text="ID of the agent to use")
    message = serializers.CharField(help_text="Message to send to the agent")
    session_id = serializers.CharField(help_text="Unique session identifier for chat history")


class ChatSessionSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source="id", read_only=True)
    agent_id = serializers.CharField(write_only=True)
    agent_code = serializers.CharField(source="agent.agent_id", read_only=True)
    title = serializers.CharField(min_length=3, required=False)

    class Meta:
        model = ChatSession
        fields = ["session_id", "title", "agent_id", "agent_code", "created_at", "updated_at"]
        read_only_fields = ["session_id", "created_at", "updated_at", "agent_code"]

    def create(self, validated_data):
        user = self.context["request"].user
        agent_id_str = validated_data.pop("agent_id")

        try:
            agent = Agent.objects.get(agent_id=agent_id_str)
        except Agent.DoesNotExist:
            raise serializers.ValidationError({"agent_id": "Agent with this agent_id does not exist."})

        return ChatSession.objects.create(user=user, agent=agent, **validated_data)
