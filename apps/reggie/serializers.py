from rest_framework import serializers

from apps.teams.models import Team

from .models import (
    Agent,
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
    FileKnowledgeBaseLink,
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
            "agent_id",
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
        read_only_fields = ["id", "agent_id", "created_at"]

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


class FileTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileTag
        fields = "__all__"


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = [
            'uuid',
            'title',
            'description',
            'file',
            'file_type',
            'storage_bucket',
            'storage_path',
            'original_path',
            'uploaded_by',
            'team',
            'source',
            'visibility',
            'is_global',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['uuid', 'storage_path', 'original_path', 'uploaded_by', 'created_at', 'updated_at']


class UploadFileSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=False))
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    team = serializers.IntegerField(required=False, allow_null=True)
    is_global = serializers.BooleanField(default=False, required=False)
    storage_bucket = serializers.PrimaryKeyRelatedField(
        queryset=StorageBucket.objects.all(),
        required=False,
        allow_null=True,
        help_text="Optional storage bucket. If not provided, system default will be used."
    )

    def validate_team(self, value):
        """
        Validate team ID and convert invalid values to None.
        """
        if value in [0, "0", None, ""]:
            return None
            
        try:
            return Team.objects.get(id=value)
        except Team.DoesNotExist:
            return None

    def validate_is_global(self, value):
        """
        Validate that only superusers can set is_global to True.
        """
        if value and not self.context['request'].user.is_superuser:
            raise serializers.ValidationError(
                "Only superadmins can upload files to the global directory."
            )
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        team = validated_data.get("team", None)
        title = validated_data.get("title", None)
        description = validated_data.get("description", "")
        is_global = validated_data.get("is_global", False)
        storage_bucket = validated_data.get("storage_bucket", None)

        documents = []
        for file in validated_data["files"]:
            document = File.objects.create(
                file=file,
                uploaded_by=user,
                team=team,
                title=title or file.name,  # Use filename as title if not provided
                description=description,
                is_global=is_global,
                storage_bucket=storage_bucket,  # Will use system default if None
                visibility=File.PUBLIC if is_global else File.PRIVATE
            )
            documents.append(document)

        return documents


class UploadFileResponseSerializer(serializers.Serializer):
    """Response serializer for file uploads."""
    message = serializers.CharField(
        help_text="Success message with number of files uploaded"
    )
    documents = FileSerializer(
        many=True, 
        help_text="List of successfully uploaded and processed documents"
    )
    failed_uploads = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="List of files that failed to upload with error messages"
    )

    class Meta:
        swagger_schema_fields = {
            "title": "File Upload Response",
            "description": "Response format for file uploads including success/failure details",
            "examples": [
                {
                    "summary": "Successful upload",
                    "value": {
                        "message": "3 documents uploaded successfully.",
                        "documents": [
                            {
                                "id": 1,
                                "title": "document1.pdf",
                                "file_type": "pdf",
                                "ingestion_status": "processing",
                                "ingestion_progress": 0.0
                            }
                        ],
                        "failed_uploads": []
                    }
                },
                {
                    "summary": "Partial failure",
                    "value": {
                        "message": "2 documents uploaded, 1 failed",
                        "documents": [
                            {
                                "id": 1,
                                "title": "document1.pdf",
                                "file_type": "pdf",
                                "ingestion_status": "processing",
                                "ingestion_progress": 0.0
                            }
                        ],
                        "failed_uploads": [
                            {
                                "name": "large.pdf",
                                "error": "File size exceeds limit"
                            }
                        ]
                    }
                }
            ]
        }


class StreamAgentRequestSerializer(serializers.Serializer):
    agent_id = serializers.CharField(help_text="ID of the agent to use")
    message = serializers.CharField(help_text="Message to send to the agent")
    session_id = serializers.CharField(help_text="Unique session identifier for chat history")


class ChatSessionSerializer(serializers.ModelSerializer):
    session_id = serializers.UUIDField(source="id", read_only=True)
    agent_id = serializers.CharField(write_only=True)
    # agent_code = serializers.CharField(source="agent.agent_id", read_only=True)
    title = serializers.CharField(min_length=3, required=False)

    class Meta:
        model = ChatSession
        fields = ["session_id", "title", "agent_id", "created_at", "updated_at"]
        read_only_fields = ["session_id", "created_at", "updated_at"]

    def create(self, validated_data):
        user = self.context["request"].user
        agent_id_str = validated_data.pop("agent_id")

        try:
            agent = Agent.objects.get(agent_id=agent_id_str)
        except Agent.DoesNotExist:
            raise serializers.ValidationError({"agent_id": "Agent with this agent_id does not exist."})

        return ChatSession.objects.create(user=user, agent=agent, **validated_data)


class ModelProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelProvider
        fields = ["id", "provider", "model_name", "is_enabled"]


# serializers.py


class KnowledgeBasePdfURLSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBasePdfURL
        fields = ["id", "kb", "url", "is_enabled", "added_at"]
        read_only_fields = ["id", "added_at"]


class GlobalTemplatesResponseSerializer(serializers.Serializer):
    instructions = AgentInstructionSerializer(many=True)
    expected_outputs = AgentExpectedOutputSerializer(many=True)


class AgentInstructionsResponseSerializer(serializers.Serializer):
    error = serializers.CharField(required=False)
    instruction = serializers.CharField(required=False)


class FileIngestSerializer(serializers.Serializer):
    file_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of file IDs to ingest"
    )
    knowledgebase_id = serializers.CharField(
        help_text="Knowledge base ID to ingest the files into (e.g. 'kbo-8df45f-llamaindex-t')"
    )

    def validate_file_ids(self, value):
        """
        Validate that all files exist and are accessible by the user.
        Also checks file types and status.
        """
        user = self.context['request'].user
        files = []
        invalid_ids = []
        invalid_types = []
        already_ingesting = []
        
        for file_id in value:
            try:
                file = File.objects.get(id=file_id)
                # Check file access
                if not (file.is_global or file.uploaded_by == user or 
                       (file.team and user in file.team.members.all())):
                    invalid_ids.append(file_id)
                    continue
                
                # Check file type
                if file.file_type not in ['pdf', 'docx', 'txt', 'csv', 'json']:
                    invalid_types.append(file_id)
                    continue
                
                # Check if already being ingested
                if file.knowledge_base_links.filter(
                    ingestion_status__in=['processing', 'pending']
                ).exists():
                    already_ingesting.append(file_id)
                    continue
                
                files.append(file)
            except File.DoesNotExist:
                invalid_ids.append(file_id)
        
        errors = []
        if invalid_ids:
            errors.append(f"Files with IDs {invalid_ids} do not exist or are not accessible.")
        if invalid_types:
            errors.append(f"Files with IDs {invalid_types} have unsupported file types.")
        if already_ingesting:
            errors.append(f"Files with IDs {already_ingesting} are already being ingested.")
        
        if errors:
            raise serializers.ValidationError(" ".join(errors))
        
        return files

    def validate_knowledgebase_id(self, value):
        """
        Validate that the knowledge base exists and is accessible.
        """
        user = self.context['request'].user
        try:
            kb = KnowledgeBase.objects.get(knowledgebase_id=value)
            # Add any additional access checks here if needed
            # For example, team-based access control
            return kb
        except KnowledgeBase.DoesNotExist:
            raise serializers.ValidationError(
                f"Knowledge base with ID '{value}' does not exist."
            )

    def create(self, validated_data):
        """
        Create or update FileKnowledgeBaseLink entries for each file.
        """
        files = validated_data['file_ids']  # Already validated and converted to File objects
        knowledge_base = validated_data['knowledgebase_id']  # Already validated and converted to KB object
        
        links = []
        for file in files:
            # Create or get the link
            link, created = FileKnowledgeBaseLink.objects.get_or_create(
                file=file,
                knowledge_base=knowledge_base,
                defaults={
                    'ingestion_status': 'pending',
                    'ingestion_progress': 0.0,
                    'processed_docs': 0,
                    'total_docs': 0
                }
            )
            
            if not created and link.ingestion_status in ['failed', 'completed', 'not_started']:
                # Reset status for re-ingestion
                link.ingestion_status = 'pending'
                link.ingestion_error = None
                link.ingestion_progress = 0.0
                link.processed_docs = 0
                link.total_docs = 0
                link.ingestion_started_at = None
                link.ingestion_completed_at = None
                link.save(update_fields=[
                    'ingestion_status',
                    'ingestion_error',
                    'ingestion_progress',
                    'processed_docs',
                    'total_docs',
                    'ingestion_started_at',
                    'ingestion_completed_at'
                ])
            
            links.append(link)
        
        return links


class FileIngestResponseSerializer(serializers.Serializer):
    """Response serializer for file ingestion."""
    message = serializers.CharField(help_text="Status message")
    links = serializers.ListField(
        child=serializers.DictField(),
        help_text="List of created/updated file-KB links with their status"
    )

    class Meta:
        swagger_schema_fields = {
            "title": "File Ingestion Response",
            "description": "Response format for file ingestion requests",
            "example": {
                "message": "Started ingestion of 2 files",
                "links": [
                    {
                        "file_id": 1,
                        "file_name": "document1.pdf",
                        "knowledge_base_id": "kbo-8df45f-llamaindex-t",
                        "status": "pending",
                        "progress": 0.0,
                        "processed_docs": 0,
                        "total_docs": 0
                    }
                ]
            }
        }
