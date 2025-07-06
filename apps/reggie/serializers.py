import os

from rest_framework import serializers

from apps.reggie.models import Collection
from apps.teams.models import Team

from .models import (
    Agent,
    AgentExpectedOutput,
    AgentInstruction,
    Category,
    ChatSession,
    CustomUser,
    File,
    FileKnowledgeBaseLink,
    FileTag,
    KnowledgeBase,
    KnowledgeBasePdfURL,
    KnowledgeBasePermission,
    ModelProvider,
    Project,
    StorageBucket,
    Tag,
    UserFeedback,
    VaultFile,
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


class KnowledgeBaseShareSerializer(serializers.Serializer):
    teams = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(),
        ),
        allow_empty=False,
        help_text="List of objects with 'team_id' and 'role' (viewer/editor/owner).",
    )

    def validate(self, data):
        allowed_roles = {"viewer", "editor", "owner"}
        for entry in data["teams"]:
            if "team_id" not in entry or "role" not in entry:
                raise serializers.ValidationError("Each team entry must have 'team_id' and 'role'.")
            if entry["role"] not in allowed_roles:
                raise serializers.ValidationError(f"Invalid role: {entry['role']}. Must be one of {allowed_roles}.")
        return data


class UserFeedbackSerializer(serializers.ModelSerializer):
    session = serializers.PrimaryKeyRelatedField(queryset=ChatSession.objects.all())

    class Meta:
        model = UserFeedback
        fields = [
            "id",
            "user",
            "session",
            "chat_id",
            "feedback_type",  # Choices: good, bad
            "feedback_text",
            "created_at",
        ]
        read_only_fields = ["id", "user", "created_at"]


class AgentInstructionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentInstruction
        fields = "__all__"


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description"]


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

    knowledge_base = serializers.CharField()
    # Instruction: same logic (1 assigned instruction or new)
    instructions = AgentInstructionSerializer(read_only=True)
    instructions_id = serializers.PrimaryKeyRelatedField(
        queryset=AgentInstruction.objects.all(), source="instructions", write_only=True, required=False
    )
    custom_instruction = serializers.CharField(write_only=True, required=False)
    # Alias for default_reasoning
    reasoning = serializers.BooleanField(
        source="default_reasoning",
        required=False,
    )

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["knowledge_base"] = instance.knowledge_base.knowledgebase_id if instance.knowledge_base else None
        return ret

    def validate_knowledge_base(self, value):
        try:
            kb = KnowledgeBase.objects.get(knowledgebase_id=value)
            return kb
        except KnowledgeBase.DoesNotExist:
            raise serializers.ValidationError("KnowledgeBase with this ID does not exist.")

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
            "reasoning",
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

        knowledge_base = validated_data.get("knowledge_base", None)
        if isinstance(knowledge_base, str):
            validated_data["knowledge_base"] = self.validate_knowledge_base(knowledge_base)

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

        knowledge_base = validated_data.get("knowledge_base", None)
        if isinstance(knowledge_base, str):
            validated_data["knowledge_base"] = self.validate_knowledge_base(knowledge_base)

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


class PermissionInputSerializer(serializers.Serializer):
    team_id = serializers.IntegerField(help_text="ID of the team")
    role = serializers.ChoiceField(choices=["viewer", "editor", "owner"], help_text="Role for the team")


class KnowledgeBasePermissionSerializer(serializers.ModelSerializer):
    team_id = serializers.IntegerField(source="team.id")
    team_name = serializers.CharField(source="team.name")
    role = serializers.CharField()

    class Meta:
        model = KnowledgeBasePermission
        fields = ["id", "team_id", "team_name", "role"]


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        view = self.context.get("view")
        # Remove 'permissions_detail' only for list (GET) requests
        if request and view and request.method == "GET" and getattr(view, "action", None) == "list":
            self.fields.pop("permissions_detail", None)

    is_file_linked = serializers.SerializerMethodField()
    # Accept input for permissions as a write-only field, output as read-only (detailed)
    permissions = serializers.SerializerMethodField(read_only=True)
    permissions_input = PermissionInputSerializer(many=True, write_only=True, required=False)
    role = serializers.SerializerMethodField(help_text="The role of the authenticated user for this knowledge base.")

    def get_permissions(self, obj):
        from .models import KnowledgeBasePermission

        perms = KnowledgeBasePermission.objects.filter(knowledge_base=obj).select_related("team")
        return KnowledgeBasePermissionSerializer(perms, many=True).data

    class Meta:
        model = KnowledgeBase
        fields = [
            "id",
            "knowledgebase_id",
            "name",
            "description",
            "model_provider",
            "chunk_size",
            "chunk_overlap",
            "vector_table_name",
            "created_at",
            "updated_at",
            "is_file_linked",
            "permissions",
            "permissions_input",
            "role",
        ]

    def create(self, validated_data):
        permissions = validated_data.pop("permissions_input", None)
        kb = super().create(validated_data)
        if permissions:
            from apps.teams.models import Team

            from .models import KnowledgeBasePermission

            for entry in permissions:
                team_id = entry["team_id"]
                role = entry["role"]
                try:
                    team = Team.objects.get(pk=team_id)
                    KnowledgeBasePermission.objects.create(
                        knowledge_base=kb,
                        team=team,
                        role=role,
                        created_by=self.context["request"].user if "request" in self.context else None,
                    )
                except Team.DoesNotExist:
                    pass
            kb.save()
        return kb

    def update(self, instance, validated_data):
        permissions = validated_data.pop("permissions_input", None)
        kb = super().update(instance, validated_data)
        print("permissions", permissions)
        print("kb", validated_data)
        if permissions is not None:
            from apps.teams.models import Team

            from .models import KnowledgeBasePermission

            KnowledgeBasePermission.objects.filter(knowledge_base=kb).delete()
            for entry in permissions:
                team_id = entry["team_id"]
                role = entry["role"]
                try:
                    team = Team.objects.get(pk=team_id)
                    KnowledgeBasePermission.objects.create(
                        knowledge_base=kb,
                        team=team,
                        role=role,
                        created_by=self.context["request"].user if "request" in self.context else None,
                    )
                except Team.DoesNotExist:
                    pass
            kb.save()
        return kb

    def get_role(self, obj):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None
        user = request.user
        # If the user is the owner, always owner
        if obj.uploaded_by == user:
            return "owner"
        # Otherwise, check KnowledgeBasePermission for user's teams
        user_teams = getattr(user, "teams", None)
        if user_teams is not None:
            from .models import KnowledgeBasePermission

            perms = KnowledgeBasePermission.objects.filter(knowledge_base=obj, team__in=user.teams.all())
            if perms.exists():
                # Return the highest role if multiple
                role_priority = {"owner": 3, "editor": 2, "viewer": 1}
                highest = sorted(perms, key=lambda x: role_priority.get(x.role, 0), reverse=True)[0]
                return highest.role
        return None

    def get_is_file_linked(self, obj):
        """Check if a specific file is linked to this knowledge base."""
        request = self.context.get("request")
        if not request:
            return None

        file_id = request.query_params.get("file_id")
        if not file_id:
            return None

        try:
            # Debug logging
            print(f"Checking link for file_id: {file_id} and kb_id: {obj.id}")

            # Check if there's any link between the file and knowledge base
            link_exists = FileKnowledgeBaseLink.objects.filter(file__uuid=file_id, knowledge_base=obj).exists()

            print(f"Link exists: {link_exists}")
            return link_exists

        except Exception as e:
            print(f"Error checking link: {str(e)}")
            return False


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


class VaultFileSerializer(serializers.ModelSerializer):
    filename = serializers.SerializerMethodField()
    original_filename = serializers.CharField(read_only=True)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), required=False, allow_null=True)
    uploaded_by = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all())
    team = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), required=False, allow_null=True)
    shared_with_users = serializers.PrimaryKeyRelatedField(queryset=CustomUser.objects.all(), many=True, required=False)
    shared_with_teams = serializers.PrimaryKeyRelatedField(queryset=Team.objects.all(), many=True, required=False)
    size = serializers.IntegerField(read_only=True)
    type = serializers.CharField(read_only=True)
    inherited_users = serializers.SerializerMethodField()
    inherited_teams = serializers.SerializerMethodField()

    class Meta:
        model = VaultFile
        fields = [
            "file",
            "filename",
            "original_filename",
            "id",
            "file",
            "project",
            "uploaded_by",
            "team",
            "shared_with_users",
            "shared_with_teams",
            "size",
            "type",
            "inherited_users",
            "inherited_teams",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "inherited_users", "inherited_teams", "size", "type"]

    def get_filename(self, obj):
        return os.path.basename(obj.file.name) if obj.file else None

    def get_inherited_users(self, obj):
        if obj.project:
            # Owner, members, and users from project.team and shared_with_teams
            users = set()
            users.add(obj.project.owner)
            users.update(obj.project.members.all())
            if obj.project.team:
                users.update(obj.project.team.members.all())
            for team in obj.project.shared_with_teams.all():
                users.update(team.members.all())
            return [user.pk for user in users]
        return []

    def get_inherited_teams(self, obj):
        if obj.project:
            teams = set()
            if obj.project.team:
                teams.add(obj.project.team)
            teams.update(obj.project.shared_with_teams.all())
            return [team.pk for team in teams]
        return []

    def validate(self, data):
        # Prevent removing inherited permissions
        project = data.get("project") or getattr(self.instance, "project", None)
        if project:
            inherited_user_ids = set([project.owner.pk])
            inherited_user_ids.update(project.members.values_list("pk", flat=True))
            if project.team:
                inherited_user_ids.update(project.team.members.values_list("pk", flat=True))
            for team in project.shared_with_teams.all():
                inherited_user_ids.update(team.members.values_list("pk", flat=True))
            shared_with_users = data.get("shared_with_users")
            if shared_with_users is not None and len(shared_with_users) > 0:
                if not set(shared_with_users).issuperset(inherited_user_ids):
                    raise serializers.ValidationError("Cannot remove inherited project user permissions from file.")
        return data


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ["id", "name"]


class FileSerializer(serializers.ModelSerializer):
    filesize = serializers.IntegerField(read_only=True)
    collection = CollectionSerializer(read_only=True)

    class Meta:
        model = File
        fields = [
            "uuid",
            "title",
            "description",
            "file",
            "file_type",
            "storage_bucket",
            "storage_path",
            "original_path",
            "uploaded_by",
            "team",
            "source",
            "visibility",
            "is_global",
            "created_at",
            "updated_at",
            "collection",
            "filesize",
        ]
        read_only_fields = [
            "uuid",
            "storage_path",
            "original_path",
            "uploaded_by",
            "created_at",
            "updated_at",
            "collection",
            "filesize",
        ]


class UploadFileSerializer(serializers.Serializer):
    files = serializers.ListField(child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=False))
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    team = serializers.IntegerField(required=False, allow_null=True)
    is_global = serializers.BooleanField(default=False, required=False)
    is_ephemeral = serializers.BooleanField(required=False, default=False)
    session_id = serializers.CharField(required=False, allow_blank=True)
    storage_bucket = serializers.PrimaryKeyRelatedField(
        queryset=StorageBucket.objects.all(),
        required=False,
        allow_null=True,
        help_text="Optional storage bucket. If not provided, system default will be used.",
    )
    filesize = serializers.IntegerField(read_only=True)
    collection = CollectionSerializer(read_only=True)

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
        if value and not self.context["request"].user.is_superuser:
            raise serializers.ValidationError("Only superadmins can upload files to the global directory.")
        return value

    def create(self, validated_data):
        from .models import Collection, EphemeralFile

        user = self.context["request"].user
        team = validated_data.get("team", None)
        title = validated_data.get("title", None)
        description = validated_data.get("description", "")
        is_global = validated_data.get("is_global", False)
        is_ephemeral = validated_data.get("is_ephemeral", False)
        session_id = validated_data.get("session_id", "")
        storage_bucket = validated_data.get("storage_bucket", None)

        documents = []

        for file in validated_data["files"]:
            if is_ephemeral:
                # Create EphemeralFile
                ephemeral_file = EphemeralFile.objects.create(
                    uploaded_by=user,
                    session_id=session_id,
                    file=file,
                    name=file.name,
                    mime_type=file.content_type or "application/octet-stream",
                )
                documents.append(ephemeral_file)
            else:
                # Compute title as per frontend logic
                computed_title = f"{title}-{file.name}" if title else file.name
                # Only assign a collection if title is provided
                if title:
                    collection, _ = Collection.objects.get_or_create(name=title)
                else:
                    collection = None
                document = File.objects.create(
                    file=file,
                    uploaded_by=user,
                    team=team,
                    title=computed_title,
                    description=description,
                    is_global=is_global,
                    storage_bucket=storage_bucket,  # Will use system default if None
                    visibility=File.PUBLIC if is_global else File.PRIVATE,
                    collection=collection,
                )
                documents.append(document)

        return documents


class UploadFileResponseSerializer(serializers.Serializer):
    """Response serializer for file uploads."""

    message = serializers.CharField(help_text="Success message with number of files uploaded")
    documents = FileSerializer(many=True, help_text="List of successfully uploaded and processed documents")
    failed_uploads = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text="List of files that failed to upload with error messages",
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
                                "ingestion_progress": 0.0,
                            }
                        ],
                        "failed_uploads": [],
                    },
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
                                "ingestion_progress": 0.0,
                            }
                        ],
                        "failed_uploads": [{"name": "large.pdf", "error": "File size exceeds limit"}],
                    },
                },
            ],
        }


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
        fields = [
            "session_id",
            "title",
            "agent_id",  # for POST/PUT
            "agent_code",  # for GET (read-only, agent's code)
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["session_id", "agent_code", "created_at", "updated_at"]

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
    file_ids = serializers.ListField(child=serializers.UUIDField(), help_text="List of file UUIDs to ingest")
    knowledgebase_ids = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of knowledge base IDs to ingest the files into (e.g. ['kbo-8df45f-llamaindex-t', 'kbo-another-kb'])",
    )

    def validate_file_ids(self, value):
        """
        Validate that all files exist and are accessible by the user.
        Also checks file types and status.
        Skip validation if the request is a remove_kb or unlink_kb operation.
        """

        user = self.context["request"].user
        files = []
        invalid_ids = []
        invalid_types = []
        already_ingesting = []

        for file_uuid in value:
            try:
                file = File.objects.get(uuid=file_uuid)
                # Check file access
                if not (file.is_global or file.uploaded_by == user or (file.team and user in file.team.members.all())):
                    invalid_ids.append(file_uuid)
                    continue

                # Check file type
                if file.file_type not in ["pdf", "docx", "txt", "csv", "json"]:
                    invalid_types.append(file_uuid)
                    continue

                # Check if already being ingested
                if file.knowledge_base_links.filter(ingestion_status__in=["processing", "pending"]).exists():
                    already_ingesting.append(file_uuid)
                    continue

                files.append(file)
            except File.DoesNotExist:
                invalid_ids.append(file_uuid)

        errors = []
        if invalid_ids:
            errors.append(f"Files with UUIDs {invalid_ids} do not exist or are not accessible.")
        if invalid_types:
            errors.append(f"Files with UUIDs {invalid_types} have unsupported file types.")
        if already_ingesting:
            errors.append(f"Files with UUIDs {already_ingesting} are already being ingested.")

        if errors:
            raise serializers.ValidationError(" ".join(errors))

        return files

    def validate_knowledgebase_ids(self, value):
        """
        Validate that all knowledge bases exist and are accessible.
        """
        kbs = []
        invalid_ids = []

        for kb_id in value:
            try:
                kb = KnowledgeBase.objects.get(knowledgebase_id=kb_id)
                # Add any additional access checks here if needed
                # For example, team-based access control
                kbs.append(kb)
            except KnowledgeBase.DoesNotExist:
                invalid_ids.append(kb_id)

        if invalid_ids:
            raise serializers.ValidationError(f"Knowledge bases with IDs {invalid_ids} do not exist.")

        return kbs

    def create(self, validated_data):
        """
        Create or update FileKnowledgeBaseLink entries for each file and knowledge base combination.
        """
        files = validated_data["file_ids"]  # Already validated and converted to File objects
        knowledge_bases = validated_data["knowledgebase_ids"]  # Already validated and converted to KB objects

        links = []
        for file in files:
            for knowledge_base in knowledge_bases:
                # Create or get the link
                link, created = FileKnowledgeBaseLink.objects.get_or_create(
                    file=file,
                    knowledge_base=knowledge_base,
                    defaults={
                        "ingestion_status": "pending",
                        "ingestion_progress": 0.0,
                        "processed_docs": 0,
                        "total_docs": 0,
                        "chunk_size": knowledge_base.chunk_size,
                        "chunk_overlap": knowledge_base.chunk_overlap,
                    },
                )

                if not created and link.ingestion_status in ["failed", "completed", "not_started"]:
                    # Reset status for re-ingestion
                    link.ingestion_status = "pending"
                    link.ingestion_error = None
                    link.ingestion_progress = 0.0
                    link.processed_docs = 0
                    link.total_docs = 0
                    link.ingestion_started_at = None
                    link.ingestion_completed_at = None
                    link.save(
                        update_fields=[
                            "ingestion_status",
                            "ingestion_error",
                            "ingestion_progress",
                            "processed_docs",
                            "total_docs",
                            "ingestion_started_at",
                            "ingestion_completed_at",
                        ]
                    )

                links.append(link)

        return links


class FileIngestResponseSerializer(serializers.Serializer):
    """Response serializer for file ingestion."""

    message = serializers.CharField(help_text="Status message")
    links = serializers.ListField(
        child=serializers.DictField(), help_text="List of created/updated file-KB links with their status"
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
                        "total_docs": 0,
                    }
                ],
            },
        }


class DocumentListingSerializer(serializers.ModelSerializer):
    """
    Serializer for listing documents in a knowledge base with their processing status and metadata.
    A document represents a processed file in the context of a knowledge base.
    """

    document_id = serializers.SerializerMethodField()
    file_id = serializers.UUIDField(source="file.uuid")
    title = serializers.CharField(source="file.title")
    description = serializers.CharField(source="file.description", allow_null=True)
    file_type = serializers.CharField(source="file.file_type")
    file_size = serializers.IntegerField(source="file.file_size")
    page_count = serializers.IntegerField(source="file.page_count")
    total_chunks = serializers.IntegerField(source="processed_docs")
    chunk_size = serializers.IntegerField()
    chunk_overlap = serializers.IntegerField()
    status = serializers.CharField(source="ingestion_status")
    progress = serializers.FloatField(source="ingestion_progress")
    error = serializers.CharField(source="ingestion_error", allow_null=True)
    created_at = serializers.DateTimeField(source="file.created_at")
    updated_at = serializers.DateTimeField()

    class Meta:
        model = FileKnowledgeBaseLink
        fields = [
            "document_id",
            "file_id",
            "title",
            "description",
            "file_type",
            "file_size",
            "page_count",
            "total_chunks",
            "chunk_size",
            "chunk_overlap",
            "status",
            "progress",
            "error",
            "created_at",
            "updated_at",
        ]

    def get_document_id(self, obj):
        """Generate a unique document ID combining file and KB IDs"""
        return f"doc-{obj.file.uuid}-{obj.knowledge_base.knowledgebase_id}"


class KnowledgeBaseInfoSerializer(serializers.ModelSerializer):
    """Simplified KB info for file listings"""

    kb_id = serializers.CharField(source="knowledgebase_id")
    kb_name = serializers.CharField(source="name")

    class Meta:
        model = KnowledgeBase
        fields = ["kb_id", "kb_name"]


class FileListWithKBSerializer(serializers.ModelSerializer):
    collection = CollectionSerializer(read_only=True)
    """Enhanced file serializer that includes knowledge base information"""

    id = serializers.UUIDField(source="uuid")
    name = serializers.CharField(source="title")
    type = serializers.CharField(source="file_type")
    size = serializers.IntegerField(source="file_size")
    location = serializers.CharField(source="storage_path")
    filesize = serializers.IntegerField(read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(source="uploaded_by", read_only=True)
    create_date = serializers.DateTimeField(source="created_at")
    update_date = serializers.DateTimeField(source="updated_at")
    create_time = serializers.SerializerMethodField()
    update_time = serializers.SerializerMethodField()
    kbs_info = serializers.SerializerMethodField()
    source_type = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = [
            "id",
            "name",
            "type",
            "size",
            "location",
            "collection",
            "filesize",
            "created_by",
            "create_date",
            "update_date",
            "create_time",
            "update_time",
            "kbs_info",
            "source_type",
        ]


class FileKnowledgeBaseLinkSerializer(serializers.ModelSerializer):
    """Serializer for listing files in a knowledge base with their processing status."""

    file_id = serializers.UUIDField(source="file.uuid")
    title = serializers.CharField(source="file.title")
    description = serializers.CharField(source="file.description", allow_null=True)
    file_type = serializers.CharField(source="file.file_type")
    filesize = serializers.IntegerField(source="file.filesize")
    size = serializers.IntegerField(source="file.filesize")
    page_count = serializers.IntegerField(source="file.page_count")
    collection = CollectionSerializer(source="file.collection", read_only=True)
    created_at = serializers.DateTimeField(source="file.created_at")
    updated_at = serializers.DateTimeField(source="file.updated_at")
    status = serializers.CharField(source="ingestion_status")
    progress = serializers.FloatField(source="ingestion_progress")
    error = serializers.CharField(source="ingestion_error", allow_null=True)
    processed_docs = serializers.IntegerField()
    total_docs = serializers.IntegerField()
    chunk_size = serializers.IntegerField()
    chunk_overlap = serializers.IntegerField()

    class Meta:
        model = FileKnowledgeBaseLink
        fields = [
            "file_id",
            "title",
            "description",
            "file_type",
            "filesize",
            "size",
            "page_count",
            "created_at",
            "updated_at",
            "status",
            "progress",
            "error",
            "processed_docs",
            "total_docs",
            "chunk_size",
            "chunk_overlap",
            "collection",
        ]
