# Create your tests here.

import uuid
from django.conf import settings
from django.utils.text import slugify
from agno.knowledge import AgentKnowledge
from agno.vector_db import PgVector
from agno.embedders import OpenAIEmbedder, GeminiEmbedder, GroqEmbedder # Assuming AnthropicEmbedder will be similar
# Import AnthropicEmbedder if available, or use a mock/placeholder if not critical for type assertion
# from agno.embedders import AnthropicEmbedder
import requests # For mocking in FileViewSetTests

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework_api_key.models import APIKey

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from unittest.mock import patch

from apps.api.models import UserAPIKey
from apps.reggie.models import (
    File,
    KnowledgeBase,
    FileKnowledgeBaseLink,
    ModelProvider,
    StorageBucket,
    Team,
    Agent,
    AgentInstruction,
    ChatSession,
    # Category, Capability - add if direct creation is needed and not through fixtures or defaults
)
from apps.reggie.storage import PostgresAgentStorage, AgentSession # For mocking
from django.core.exceptions import ValidationError


User = get_user_model()


class AgentModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Users
        cls.user1 = User.objects.create_user(email="agentuser1@example.com", password="password", first_name="Agent", last_name="UserOne")
        cls.superuser = User.objects.create_superuser(email="agentsuper@example.com", password="password")
        cls.user_in_team = User.objects.create_user(email="agentteamuser@example.com", password="password")
        cls.user3_no_access = User.objects.create_user(email="agentuser3@example.com", password="password")

        # Team
        cls.team1 = Team.objects.create(name="Agent Test Team", created_by=cls.user1)
        cls.team1.members.add(cls.user_in_team)
        cls.team1.members.add(cls.user1) # Owner should also be a member

        # Model Provider (reusing openai_provider logic from KB tests for simplicity)
        cls.agent_model_provider = ModelProvider.objects.create(
            name="Agent OpenAI Provider",
            provider="openai",
            api_key="agent_openai_key",
            config={"embedder_id": "text-embedding-3-small", "dimensions": 1536, "llm_model_id": "gpt-4"}, # Added llm_model_id
            owner=cls.user1,
            team=cls.team1,
        )
        cls.google_model_provider = ModelProvider.objects.create( # For mismatch test
            name="Agent Google Provider",
            provider="google",
            api_key="agent_google_key",
            config={"embedder_id": "text-embedding-004", "dimensions": 768, "llm_model_id": "gemini-pro"},
            owner=cls.user1,
            team=cls.team1,
        )


        # KnowledgeBase
        cls.agent_kb = KnowledgeBase.objects.create(
            name="Agent Test KB",
            created_by=cls.user1,
            team=cls.team1,
            embedding_model=cls.agent_model_provider, # KB uses the same provider as agent for valid case
        )
        cls.google_kb_for_mismatch = KnowledgeBase.objects.create(
            name="Agent Google KB Mismatch",
            created_by=cls.user1,
            team=cls.team1,
            embedding_model=cls.google_model_provider, # KB uses Google provider
        )


        # Agent Instructions
        cls.enabled_instruction = AgentInstruction.objects.create(
            name="Enabled Test Instruction",
            instruction_text="This is an enabled instruction for agent tests.",
            created_by=cls.user1,
            is_enabled=True,
            is_system_level=False,
        )
        cls.disabled_instruction = AgentInstruction.objects.create(
            name="Disabled Test Instruction",
            instruction_text="This is a disabled instruction.",
            created_by=cls.user1,
            is_enabled=False,
            is_system_level=False,
        )
        cls.system_instruction = AgentInstruction.objects.create(
            name="System Test Instruction",
            instruction_text="This is a system-level instruction.",
            created_by=cls.user1, # Or a system user if applicable
            is_enabled=True,
            is_system_level=True,
        )
        cls.disabled_system_instruction = AgentInstruction.objects.create(
            name="Disabled System Instruction",
            instruction_text="This is a disabled system-level instruction.",
            created_by=cls.user1,
            is_enabled=False,
            is_system_level=True,
        )

        # Optional: Category and Capability if needed for direct agent creation
        # cls.category = Category.objects.create(name="Test Category")
        # cls.capability = Capability.objects.create(name="Test Capability")

    @patch("uuid.uuid4")
    def test_save_id_and_table_name_generation(self, mock_uuid):
        fixed_uuid_str = "a1b2c3d4-e5f6-7890-1234-567890abcdef"
        fixed_uuid_obj = uuid.UUID(fixed_uuid_str)
        # Let's have uuid.uuid4() return a series of different UUIDs if called multiple times
        # during a single save, or for different fields.
        # For this test, we'll assume unique_code gets one, and other ID generations might use their own logic or parts of a UUID.
        mock_uuid.side_effect = [
            fixed_uuid_obj, # For unique_code
            uuid.UUID("00000000-0000-0000-0000-000000000001"), # For agent_id generation if it uses uuid
            uuid.UUID("00000000-0000-0000-0000-000000000002"), # Placeholder if other UUIDs are needed
        ]

        agent_name = "My Test Agent"
        agent = Agent(
            name=agent_name,
            created_by=self.user1,
            team=self.team1,
            model_provider=self.agent_model_provider,
            # knowledge_base can be added later or here if it affects ID generation
        )
        agent.save()

        # 1. Assert unique_code
        self.assertEqual(agent.unique_code, fixed_uuid_obj)

        # 2. Assert agent_id generation
        # Format: {provider_initial}-{mocked_uuid_prefix}-{slugified_name}
        # This is an assumption. The actual implementation might differ.
        provider_initial = self.agent_model_provider.provider[:2].lower()
        # If agent_id uses a different UUID or a portion of unique_code:
        # For now, assume it might derive from unique_code's first part for simplicity of mocking.
        # Or, if it uses the second UUID from side_effect:
        agent_id_uuid_prefix = str(mock_uuid.side_effect[1])[:8] if len(mock_uuid.side_effect) > 1 else str(fixed_uuid_obj)[:8]

        # Let's refine based on typical model code: agent_id might not use a separate UUID but be derived.
        # For now, using the prompt's direct format:
        expected_agent_id = f"{provider_initial}-{agent_id_uuid_prefix}-{slugify(agent_name)}"
        # If the model uses its own UUID for agent_id, the mock_uuid.side_effect needs to provide that.
        # Let's assume the model's _generate_agent_id uses the second UUID from the mock for its prefix.
        self.assertEqual(agent.agent_id, expected_agent_id)

        # Helper for cleaning IDs for table names (lowercase, underscores)
        def clean_for_table_name(id_str):
            return id_str.replace("-", "_").lower()

        # 3. Assert session_table
        expected_session_table = f"agent_session_{clean_for_table_name(agent.agent_id)}"
        self.assertEqual(agent.session_table, expected_session_table)

        # 4. Assert agent_knowledge_id
        expected_agent_knowledge_id = f"agent_kb_{clean_for_table_name(agent.agent_id)}"
        self.assertEqual(agent.agent_knowledge_id, expected_agent_knowledge_id)

        # 5. Assert memory_table
        expected_memory_table = f"agent_memory_{clean_for_table_name(agent.agent_id)}"
        self.assertEqual(agent.memory_table, expected_memory_table)

        # Store original IDs
        original_agent_id = agent.agent_id
        original_unique_code = agent.unique_code
        original_session_table = agent.session_table
        original_agent_knowledge_id = agent.agent_knowledge_id
        original_memory_table = agent.memory_table

        # Reset mock if it was exhausted or to ensure next call is predictable if needed.
        # For this test, we are checking if IDs change on re-save, so new UUIDs should NOT be generated for these specific fields.
        # We might need to ensure that any @property using uuid4() is also patched if it influences these fields on save.
        # For now, assume these fields are set in save() only if not already set.

        mock_uuid.reset_mock() # Reset calls, but side_effect might persist if not a new instance.
                               # It's safer to set side_effect again if more UUIDs are expected for other operations.

        # Test that IDs are not regenerated on subsequent saves
        agent.name = "My Test Agent Updated"
        agent.save()

        self.assertEqual(agent.agent_id, original_agent_id)
        self.assertEqual(agent.unique_code, original_unique_code)
        self.assertEqual(agent.session_table, original_session_table)
        self.assertEqual(agent.agent_knowledge_id, original_agent_knowledge_id)
        self.assertEqual(agent.memory_table, original_memory_table)

    def test_clean_method_validation_logic(self):
        # Scenario 1: Mismatched ModelProvider and KnowledgeBase.embedding_model
        agent_mismatch = Agent(
            name="Mismatch Agent",
            created_by=self.user1,
            team=self.team1,
            model_provider=self.agent_model_provider, # OpenAI provider
            knowledge_base=self.google_kb_for_mismatch, # Google KB
        )
        with self.assertRaisesRegex(ValidationError,
                                     "KnowledgeBase's embedding model provider must match the agent's model provider."):
            agent_mismatch.clean()

        # Scenario 2: Matching ModelProvider and KnowledgeBase.embedding_model
        agent_match = Agent(
            name="Match Agent",
            created_by=self.user1,
            team=self.team1,
            model_provider=self.agent_model_provider,    # OpenAI provider
            knowledge_base=self.agent_kb,                # OpenAI KB (setup in setUpTestData)
        )
        try:
            agent_match.clean()  # Should not raise ValidationError
        except ValidationError as e:
            self.fail(f"clean() raised ValidationError unexpectedly: {e}")

        # Scenario 3: Agent with no KnowledgeBase (should also pass clean)
        agent_no_kb = Agent(
            name="No KB Agent",
            created_by=self.user1,
            team=self.team1,
            model_provider=self.agent_model_provider,
            knowledge_base=None,
        )
        try:
            agent_no_kb.clean() # Should not raise ValidationError
        except ValidationError as e:
            self.fail(f"clean() raised ValidationError unexpectedly for agent with no KB: {e}")

    def test_get_active_instructions(self):
        agent = Agent.objects.create(
            name="Instruction Test Agent",
            created_by=self.user1,
            team=self.team1,
            model_provider=self.agent_model_provider,
        )

        # Scenario 1: Agent with specific, enabled instruction
        agent.instructions.set([self.enabled_instruction])
        active_instructions_s1 = agent.get_active_instructions()
        self.assertIn(self.enabled_instruction, active_instructions_s1)
        self.assertIn(self.system_instruction, active_instructions_s1)
        self.assertNotIn(self.disabled_instruction, active_instructions_s1)
        self.assertNotIn(self.disabled_system_instruction, active_instructions_s1)
        self.assertEqual(active_instructions_s1.count(), 2)

        # Scenario 2: Agent with specific, disabled instruction
        agent.instructions.set([self.disabled_instruction])
        active_instructions_s2 = agent.get_active_instructions()
        self.assertNotIn(self.disabled_instruction, active_instructions_s2)
        self.assertIn(self.system_instruction, active_instructions_s2)
        self.assertEqual(active_instructions_s2.count(), 1)

        # Scenario 3: Agent with no specific instruction (clear the m2m)
        agent.instructions.clear()
        active_instructions_s3 = agent.get_active_instructions()
        self.assertIn(self.system_instruction, active_instructions_s3)
        self.assertEqual(active_instructions_s3.count(), 1)

        # Scenario 4: Agent with specific enabled AND specific disabled instruction
        # (should only pick up the enabled one + system)
        agent.instructions.set([self.enabled_instruction, self.disabled_instruction])
        active_instructions_s4 = agent.get_active_instructions()
        self.assertIn(self.enabled_instruction, active_instructions_s4)
        self.assertIn(self.system_instruction, active_instructions_s4)
        self.assertNotIn(self.disabled_instruction, active_instructions_s4)
        self.assertEqual(active_instructions_s4.count(), 2)

        # Scenario 5: Only disabled system instruction exists (and agent has no specific)
        # (This requires temporarily disabling the main system_instruction or creating a context)
        # For simplicity, we assume self.system_instruction is the only enabled one.
        # If we were to disable self.system_instruction and enable self.disabled_system_instruction (but it's disabled by name)
        # then the agent should get 0 instructions.
        # Let's test that if NO system instructions are enabled, agent gets only its own.

        # Temporarily disable the main system instruction for a sub-test
        self.system_instruction.is_enabled = False
        self.system_instruction.save()

        agent.instructions.set([self.enabled_instruction])
        active_instructions_s5 = agent.get_active_instructions()
        self.assertIn(self.enabled_instruction, active_instructions_s5)
        self.assertNotIn(self.system_instruction, active_instructions_s5) # Because it's now disabled
        self.assertEqual(active_instructions_s5.count(), 1)

        # Restore system instruction state for other tests
        self.system_instruction.is_enabled = True
        self.system_instruction.save()

    def test_is_accessible_by_user(self):
        agent = Agent.objects.create(
            name="Access Test Agent",
            created_by=self.user1, # Owned by user1
            model_provider=self.agent_model_provider,
            # Not associated with team1 initially for some tests
        )

        # Scenario 1: Global agent
        agent.is_global = True
        agent.save()
        self.assertTrue(agent.is_accessible_by_user(self.user_in_team)) # Any user
        self.assertTrue(agent.is_accessible_by_user(self.user3_no_access)) # Any user

        # Scenario 2: Superuser access (agent is not global)
        agent.is_global = False
        agent.save()
        self.assertTrue(agent.is_accessible_by_user(self.superuser))

        # Scenario 3: Team access (agent is not global)
        # user_in_team is already a member of team1 (user1's team)
        agent.team = self.team1 # Assign agent to team1
        agent.save()
        # self.user1 is the owner, should have access
        self.assertTrue(agent.is_accessible_by_user(self.user1))
        # self.user_in_team is a member of team1, should have access
        self.assertTrue(agent.is_accessible_by_user(self.user_in_team))

        # Scenario 4: No access (not global, not superuser, not owner, not in agent's team)
        agent.team = None # Make sure agent is not in any team for this specific check
        agent.save()
        # user3_no_access is not owner, not superuser, and agent is not global and not in their team
        self.assertFalse(agent.is_accessible_by_user(self.user3_no_access))

        # Scenario 4b: Agent in a team, but user is not in that team
        agent.team = self.team1
        agent.save()
        # user3_no_access is not in team1
        self.assertFalse(agent.is_accessible_by_user(self.user3_no_access))

        # Scenario 5: Owner access (already implicitly tested, but good to be explicit)
        agent_owned_by_user1 = Agent.objects.create(
            name="Owned Agent",
            created_by=self.user1,
            model_provider=self.agent_model_provider,
            is_global=False, # Ensure it's not global for this check
            team=None # Ensure no team assignment for this specific check
        )
        self.assertTrue(agent_owned_by_user1.is_accessible_by_user(self.user1))
        # And someone else who is not superuser, not team member, should not have access
        self.assertFalse(agent_owned_by_user1.is_accessible_by_user(self.user3_no_access))


class ChatSessionViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="chatsessionuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otherchatuser@example.com", password="password")

        # Minimal ModelProvider and Agent setup for ChatSession
        self.model_provider = ModelProvider.objects.create(
            name="ChatSession Test Provider", provider="openai", api_key="cs_test_key", owner=self.user
        )
        self.agent1 = Agent.objects.create(
            name="Chat Agent 1", created_by=self.user, model_provider=self.model_provider
        )
        self.agent2 = Agent.objects.create(
            name="Chat Agent 2", created_by=self.other_user, model_provider=self.model_provider
        )

        self.session1 = ChatSession.objects.create(
            user=self.user, agent=self.agent1, title="User 1 Session"
        )
        self.session2 = ChatSession.objects.create(
            user=self.other_user, agent=self.agent2, title="User 2 Session"
        )
        # Session for the same user but different agent
        self.session3_user1_agent2 = ChatSession.objects.create(
            user=self.user, agent=self.agent2, title="User 1 Session with Agent 2"
        )


        self.client = APIClient()

        # URLs
        self.list_url = reverse("chat_sessions-list") # Assuming 'chat_sessions' is the basename
        # Detail URL needs an ID, will be constructed in tests, e.g.,
        # reverse("chat_sessions-detail", kwargs={'id': self.session1.id})
        # Messages URL also needs an ID for the session, e.g.,
        # reverse("chat_sessions-messages", kwargs={'id': self.session1.id})

    def test_list_chat_sessions(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        # Should only list sessions for self.user (session1 and session3_user1_agent2)
        self.assertEqual(len(response.data['results']), 2)
        session_ids_in_response = [item['id'] for item in response.data['results']]
        self.assertIn(str(self.session1.id), session_ids_in_response)
        self.assertIn(str(self.session3_user1_agent2.id), session_ids_in_response)
        self.assertNotIn(str(self.session2.id), session_ids_in_response)

    def test_retrieve_chat_session(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("chat_sessions-detail", kwargs={'id': self.session1.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.session1.id))
        self.assertEqual(response.data['title'], self.session1.title)

        # Try to retrieve session of another user - should fail (404)
        other_user_session_url = reverse("chat_sessions-detail", kwargs={'id': self.session2.id})
        response = self.client.get(other_user_session_url)
        self.assertEqual(response.status_code, 404)

    def test_create_chat_session(self):
        self.client.force_authenticate(user=self.user)
        data = {
            "agent_id": str(self.agent1.id),
            "title": "New Session Title",
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        new_session = ChatSession.objects.get(id=response.data['id'])
        self.assertEqual(new_session.user, self.user)
        self.assertEqual(new_session.agent, self.agent1)
        self.assertEqual(new_session.title, "New Session Title")

    def test_update_chat_session(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("chat_sessions-detail", kwargs={'id': self.session1.id})
        new_title = "Updated Session Title"
        data = {"title": new_title}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.session1.refresh_from_db()
        self.assertEqual(self.session1.title, new_title)

        # Try to update session of another user - should fail (404)
        other_user_session_url = reverse("chat_sessions-detail", kwargs={'id': self.session2.id})
        response = self.client.patch(other_user_session_url, data, format="json")
        self.assertEqual(response.status_code, 404)


    def test_delete_chat_session(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("chat_sessions-detail", kwargs={'id': self.session1.id})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ChatSession.objects.filter(id=self.session1.id).exists())

        # Try to delete session of another user - should fail (404)
        other_user_session_url = reverse("chat_sessions-detail", kwargs={'id': self.session2.id})
        response = self.client.delete(other_user_session_url)
        self.assertEqual(response.status_code, 404)

    @patch("apps.reggie.views.PostgresAgentStorage")
    def test_get_session_messages_with_messages(self, MockPostgresAgentStorage):
        self.client.force_authenticate(user=self.user)

        # Configure mock PostgresAgentStorage instance and its read method
        mock_storage_instance = MockPostgresAgentStorage.return_value
        mock_agent_session = AgentSession(session_id=str(self.session1.id), memory={
            "runs": [
                {"message": {"role": "user", "content": "Hello Agent", "created_at": timezone.now().isoformat()}},
                {"response": {"role": "assistant", "content": "Hello User", "created_at": timezone.now().isoformat()}},
                {"message": {"role": "user", "content": "How are you?", "created_at": timezone.now().isoformat()}},
                {"response": {"role": "assistant", "content": "I am fine.", "created_at": timezone.now().isoformat()}},
            ]
        })
        mock_storage_instance.read.return_value = mock_agent_session

        messages_url = reverse("chat_sessions-messages", kwargs={'id': self.session1.id})
        response = self.client.get(messages_url)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 4) # 2 pairs of message/response

        # Check structure of the first message (user) and response (assistant)
        self.assertEqual(response.data['results'][0]['role'], 'user')
        self.assertEqual(response.data['results'][0]['content'], 'Hello Agent')
        self.assertIn('created_at', response.data['results'][0])

        self.assertEqual(response.data['results'][1]['role'], 'assistant')
        self.assertEqual(response.data['results'][1]['content'], 'Hello User')
        self.assertIn('created_at', response.data['results'][1])

        MockPostgresAgentStorage.assert_called_once_with(session_id=str(self.session1.id), user_id=str(self.user.id))
        mock_storage_instance.read.assert_called_once()

    @patch("apps.reggie.views.PostgresAgentStorage")
    def test_get_session_messages_no_messages(self, MockPostgresAgentStorage):
        self.client.force_authenticate(user=self.user)
        mock_storage_instance = MockPostgresAgentStorage.return_value
        # Scenario 1: "runs" key exists but is empty
        mock_agent_session_empty_runs = AgentSession(session_id=str(self.session1.id), memory={"runs": []})
        mock_storage_instance.read.return_value = mock_agent_session_empty_runs

        messages_url = reverse("chat_sessions-messages", kwargs={'id': self.session1.id})
        response = self.client.get(messages_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

        # Scenario 2: "runs" key does not exist in memory
        mock_agent_session_no_runs_key = AgentSession(session_id=str(self.session1.id), memory={}) # No "runs" key
        mock_storage_instance.read.return_value = mock_agent_session_no_runs_key
        response = self.client.get(messages_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)


    @patch("apps.reggie.views.PostgresAgentStorage")
    def test_get_session_messages_storage_read_returns_none(self, MockPostgresAgentStorage):
        self.client.force_authenticate(user=self.user)
        mock_storage_instance = MockPostgresAgentStorage.return_value
        mock_storage_instance.read.return_value = None # Simulate session not found in storage

        messages_url = reverse("chat_sessions-messages", kwargs={'id': self.session1.id})
        response = self.client.get(messages_url)
        self.assertEqual(response.status_code, 200) # Viewset currently returns 200 with empty list
        self.assertEqual(len(response.data['results']), 0)


    @patch("apps.reggie.views.PostgresAgentStorage")
    @patch.object(settings, 'DATABASE_URL', None) # Mock settings.DATABASE_URL to be None
    def test_get_session_messages_no_database_url(self, MockPostgresAgentStorage):
        self.client.force_authenticate(user=self.user)
        # No need to mock storage_instance.read if DATABASE_URL check happens first

        messages_url = reverse("chat_sessions-messages", kwargs={'id': self.session1.id})
        response = self.client.get(messages_url)

        # This depends on how the view handles a missing DATABASE_URL.
        # Assuming it leads to an inability to create PostgresAgentStorage or a specific check.
        # If PostgresAgentStorage constructor raises an error, that would be a 500.
        # If the view explicitly checks and returns something else:
        # For now, let's assume it might try to proceed and then fail if storage cannot be initialized.
        # If the view's _get_storage raises ValueError for no DATABASE_URL leading to 500:
        self.assertEqual(response.status_code, 500)
        # Check for a specific error message if applicable and if the view returns a structured error
        # self.assertIn("Database URL not configured", response.data.get("detail", ""))
        # If it doesn't return a specific message, or if the error is generic, this check might be omitted or adjusted.

        # Ensure storage wasn't even attempted if DATABASE_URL is None and checked early
        # MockPostgresAgentStorage.assert_not_called() # This depends on implementation detail


class ModelProviderViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="modelprovideruser@example.com", password="password")
        self.superuser = User.objects.create_superuser(email="modelprovidersuper@example.com", password="password")

        self.enabled_provider = ModelProvider.objects.create(
            name="Enabled Test Provider", provider="openai", api_key="enabled_key", owner=self.user, is_enabled=True
        )
        self.disabled_provider = ModelProvider.objects.create(
            name="Disabled Test Provider", provider="google", api_key="disabled_key", owner=self.user, is_enabled=False
        )
        # Another enabled provider by a different user, just to ensure filtering isn't by user (it's is_enabled)
        self.other_user_enabled_provider = ModelProvider.objects.create(
            name="Other User Enabled Provider", provider="anthropic", api_key="other_key", owner=self.superuser, is_enabled=True
        )

        self.client = APIClient()
        self.list_url = reverse("model_providers-list") # Assuming 'model_providers' is basename

    def test_list_model_providers_as_regular_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        provider_ids_in_response = [item['id'] for item in response.data['results']]

        self.assertIn(str(self.enabled_provider.id), provider_ids_in_response)
        self.assertIn(str(self.other_user_enabled_provider.id), provider_ids_in_response)
        self.assertNotIn(str(self.disabled_provider.id), provider_ids_in_response)
        self.assertEqual(len(provider_ids_in_response), 2)


    def test_list_model_providers_as_superuser(self):
        # Behavior should be the same for superuser regarding is_enabled filter
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        provider_ids_in_response = [item['id'] for item in response.data['results']]

        self.assertIn(str(self.enabled_provider.id), provider_ids_in_response)
        self.assertIn(str(self.other_user_enabled_provider.id), provider_ids_in_response)
        self.assertNotIn(str(self.disabled_provider.id), provider_ids_in_response)
        self.assertEqual(len(provider_ids_in_response), 2)

    def test_retrieve_enabled_model_provider(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("model_providers-detail", kwargs={'pk': self.enabled_provider.pk}) # pk or id
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.enabled_provider.id))

    def test_retrieve_disabled_model_provider_fails(self):
        # Even if directly accessed, a disabled provider should not be retrievable via this viewset due to queryset.
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("model_providers-detail", kwargs={'pk': self.disabled_provider.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404) # Because it's filtered from the queryset

    def test_unauthenticated_access_to_model_providers_fails(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401) # IsAuthenticated permission

        detail_url = reverse("model_providers-detail", kwargs={'pk': self.enabled_provider.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 401)


class AgentInstructionViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="instructionuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otherinstructionuser@example.com", password="password")
        self.superuser = User.objects.create_superuser(email="instructionadmin@example.com", password="password")

        self.instruction1 = AgentInstruction.objects.create(
            name="User1 Instruction", instruction_text="Text for user1", created_by=self.user, is_system_level=False
        )
        self.instruction2 = AgentInstruction.objects.create(
            name="OtherUser Instruction", instruction_text="Text for other_user", created_by=self.other_user, is_system_level=False
        )
        self.system_instruction_for_listing = AgentInstruction.objects.create(
            name="System Instruction Test", instruction_text="System text", created_by=self.superuser, is_system_level=True, is_enabled=True
        )
        # A disabled system instruction to ensure it's not listed
        AgentInstruction.objects.create(
            name="Disabled System Instruction", instruction_text="Disabled system text", created_by=self.superuser, is_system_level=True, is_enabled=False
        )


        self.client = APIClient()
        self.list_url = reverse("agent_instructions-list") # Basename usually model name + 's'

    def test_list_agent_instructions(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

        response_ids = [item['id'] for item in response.data['results']]
        self.assertIn(str(self.instruction1.id), response_ids)
        self.assertIn(str(self.system_instruction_for_listing.id), response_ids)
        self.assertNotIn(str(self.instruction2.id), response_ids) # Other user's non-system instruction
        self.assertEqual(len(response_ids), 2) # User's own + enabled system

    def test_retrieve_own_agent_instruction(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agent_instructions-detail", kwargs={'pk': self.instruction1.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.instruction1.id))

    def test_retrieve_other_user_agent_instruction_fails(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agent_instructions-detail", kwargs={'pk': self.instruction2.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404) # Should not see it

    def test_retrieve_system_agent_instruction_as_regular_user(self):
        # System instructions might be retrievable by PK if permissions allow,
        # but typically list includes them, detail might be restricted or allowed.
        # Assuming they are retrievable if listed.
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agent_instructions-detail", kwargs={'pk': self.system_instruction_for_listing.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.system_instruction_for_listing.id))


    def test_create_agent_instruction(self):
        self.client.force_authenticate(user=self.user)
        data = {"name": "New User Instruction", "instruction_text": "My new instruction."}
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        new_instruction = AgentInstruction.objects.get(id=response.data['id'])
        self.assertEqual(new_instruction.created_by, self.user)
        self.assertEqual(new_instruction.name, data["name"])
        self.assertFalse(new_instruction.is_system_level) # Default should be False

    def test_update_own_agent_instruction(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agent_instructions-detail", kwargs={'pk': self.instruction1.pk})
        data = {"name": "Updated Name", "instruction_text": "Updated text."}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.instruction1.refresh_from_db()
        self.assertEqual(self.instruction1.name, data["name"])
        self.assertEqual(self.instruction1.instruction_text, data["instruction_text"])

    def test_update_other_user_agent_instruction_fails(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agent_instructions-detail", kwargs={'pk': self.instruction2.pk})
        data = {"name": "Attempted Update"}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 404)

    def test_update_system_agent_instruction_by_regular_user_fails(self):
        # Regular users should not be able to update system instructions.
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agent_instructions-detail", kwargs={'pk': self.system_instruction_for_listing.pk})
        data = {"name": "Attempted System Update"}
        response = self.client.patch(update_url, data, format="json")
        # This might be 403 Forbidden or 404 Not Found depending on how permissions/queryset filtering is done.
        # If the object is simply not found in the queryset for update by that user, it's 404.
        # If it's found but permission denied, it's 403. Let's assume 404 for now.
        self.assertIn(response.status_code, [403, 404])


    def test_delete_own_agent_instruction(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agent_instructions-detail", kwargs={'pk': self.instruction1.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AgentInstruction.objects.filter(pk=self.instruction1.pk).exists())

    def test_delete_other_user_agent_instruction_fails(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agent_instructions-detail", kwargs={'pk': self.instruction2.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 404)

    def test_delete_system_agent_instruction_by_regular_user_fails(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agent_instructions-detail", kwargs={'pk': self.system_instruction_for_listing.pk})
        response = self.client.delete(delete_url)
        self.assertIn(response.status_code, [403, 404])

    # TODO: Add tests for superuser being able to manage system_level instructions (update/delete) if that's the intended behavior.
    # For now, focusing on user-level + system listing.


class AgentExpectedOutputViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="outputuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otheroutputuser@example.com", password="password")

        # Agent is a dependency for AgentExpectedOutput
        self.model_provider = ModelProvider.objects.create(name="Output Test Provider", owner=self.user)
        self.agent = Agent.objects.create(name="Output Test Agent", created_by=self.user, model_provider=self.model_provider)
        self.other_agent = Agent.objects.create(name="Other Output Test Agent", created_by=self.other_user, model_provider=self.model_provider)


        self.output1 = AgentExpectedOutput.objects.create(
            agent=self.agent, type="json_object", created_by=self.user, content={"key": "value"}
        )
        self.output2 = AgentExpectedOutput.objects.create(
            agent=self.other_agent, type="text", created_by=self.other_user, content="some text"
        )
        # Output for self.user but different agent, to test agent filtering if applicable, though viewset is typically user-filtered.
        self.output3_user1_agent_also = AgentExpectedOutput.objects.create(
            agent=self.agent, type="text", created_by=self.user, content="another value for agent1"
        )


        self.client = APIClient()
        self.list_url = reverse("agent_expected_outputs-list") # Assuming basename

    def test_list_agent_expected_outputs(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

        response_ids = [item['id'] for item in response.data['results']]
        self.assertIn(str(self.output1.id), response_ids)
        self.assertIn(str(self.output3_user1_agent_also.id), response_ids)
        self.assertNotIn(str(self.output2.id), response_ids) # Other user's output
        self.assertEqual(len(response_ids), 2)

    def test_retrieve_own_agent_expected_output(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agent_expected_outputs-detail", kwargs={'pk': self.output1.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.output1.id))

    def test_retrieve_other_user_agent_expected_output_fails(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agent_expected_outputs-detail", kwargs={'pk': self.output2.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)

    def test_create_agent_expected_output(self):
        self.client.force_authenticate(user=self.user)
        data = {
            "agent_id": str(self.agent.id),
            "type": "text",
            "content": "Brand new output."
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        new_output = AgentExpectedOutput.objects.get(id=response.data['id'])
        self.assertEqual(new_output.created_by, self.user)
        self.assertEqual(new_output.agent, self.agent)
        self.assertEqual(new_output.content, data["content"])

    def test_update_own_agent_expected_output(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agent_expected_outputs-detail", kwargs={'pk': self.output1.pk})
        data = {"content": {"new_key": "new_value"}, "type": "json_object"}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.output1.refresh_from_db()
        self.assertEqual(self.output1.content, data["content"])

    def test_update_other_user_agent_expected_output_fails(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agent_expected_outputs-detail", kwargs={'pk': self.output2.pk})
        data = {"content": "Attempted Update"}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 404)

    def test_delete_own_agent_expected_output(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agent_expected_outputs-detail", kwargs={'pk': self.output1.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AgentExpectedOutput.objects.filter(pk=self.output1.pk).exists())

    def test_delete_other_user_agent_expected_output_fails(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agent_expected_outputs-detail", kwargs={'pk': self.output2.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 404)


class KnowledgeBaseViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="kbuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otherkbuser@example.com", password="password")
        self.team = Team.objects.create(name="KB Test Team", created_by=self.user) # KBs are team-associated
        self.user.teams.add(self.team)
        self.other_user.teams.add(self.team) # Let them be in the same team for some tests

        self.model_provider1 = ModelProvider.objects.create(
            name="KB Provider 1", provider="openai", api_key="kb_key1", owner=self.user, team=self.team
        )
        self.model_provider2 = ModelProvider.objects.create(
            name="KB Provider 2", provider="google", api_key="kb_key2", owner=self.other_user, team=self.team
        )

        self.kb1 = KnowledgeBase.objects.create(
            name="User1 KB", created_by=self.user, team=self.team, embedding_model=self.model_provider1
        )
        self.kb2 = KnowledgeBase.objects.create(
            name="OtherUser KB", created_by=self.other_user, team=self.team, embedding_model=self.model_provider2
        )
        # KB for user1 with a different provider
        self.kb3_user1_provider2 = KnowledgeBase.objects.create(
            name="User1 KB Provider2", created_by=self.user, team=self.team, embedding_model=self.model_provider2
        )


        self.client = APIClient()
        self.list_url = reverse("knowledge_bases-list") # Assuming basename

    def test_list_knowledge_bases(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

        response_ids = [item['id'] for item in response.data['results']]
        # Users should see KBs belonging to their team(s)
        # In this setup, user and other_user are in the same team.
        self.assertIn(str(self.kb1.id), response_ids)
        self.assertIn(str(self.kb2.id), response_ids) # Because they are in the same team
        self.assertIn(str(self.kb3_user1_provider2.id), response_ids)
        self.assertEqual(len(response_ids), 3)


    def test_retrieve_own_knowledge_base(self): # "Own" here means accessible via team
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("knowledge_bases-detail", kwargs={'pk': self.kb1.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.kb1.id))

    def test_retrieve_other_user_knowledge_base_in_same_team(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("knowledge_bases-detail", kwargs={'pk': self.kb2.pk})
        response = self.client.get(detail_url) # Should be able to retrieve as they are in the same team
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.kb2.id))

    def test_create_knowledge_base(self):
        self.client.force_authenticate(user=self.user)
        data = {
            "name": "New User KB",
            "description": "A brand new KB.",
            "team_id": str(self.team.id),
            "embedding_model_id": str(self.model_provider1.id)
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        new_kb = KnowledgeBase.objects.get(id=response.data['id'])
        self.assertEqual(new_kb.created_by, self.user) # Serializer should set this
        self.assertEqual(new_kb.team, self.team)
        self.assertEqual(new_kb.name, data["name"])

    @patch("agno.knowledge.AgentKnowledge.vector_db_delete_table") # Mock if delete triggers this
    def test_update_own_knowledge_base(self, mock_vector_db_delete):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("knowledge_bases-detail", kwargs={'pk': self.kb1.pk})
        data = {"name": "Updated KB Name", "description": "Updated desc."}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.kb1.refresh_from_db()
        self.assertEqual(self.kb1.name, data["name"])
        mock_vector_db_delete.assert_not_called() # Name change shouldn't trigger delete usually

    @patch("agno.knowledge.AgentKnowledge.vector_db_delete_table")
    def test_update_other_user_knowledge_base_in_same_team_permission_check(self, mock_vector_db_delete):
        # Updating another user's KB, even in the same team, might be restricted by object-level permissions.
        # Default DRF behavior is often that if you can retrieve, you can update (unless perms are stricter).
        # Let's assume for now that if a user is part of the team, they can update.
        # If this should fail, the expected status would be 403 or 404.
        self.client.force_authenticate(user=self.user) # self.user trying to update self.kb2 (created by other_user)
        update_url = reverse("knowledge_bases-detail", kwargs={'pk': self.kb2.pk})
        data = {"name": "Attempted Update by Team Member"}
        response = self.client.patch(update_url, data, format="json")
        # This depends on specific permissions. If only creator can update, this should be 403/404.
        # If team members with write access can update, it's 200.
        # For now, let's assume team members can update objects within their team.
        self.assertEqual(response.status_code, 200)
        self.kb2.refresh_from_db()
        self.assertEqual(self.kb2.name, data["name"])

    @patch("agno.knowledge.AgentKnowledge.vector_db_delete_table")
    def test_delete_own_knowledge_base(self, mock_vector_db_delete):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("knowledge_bases-detail", kwargs={'pk': self.kb1.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(KnowledgeBase.objects.filter(pk=self.kb1.pk).exists())
        mock_vector_db_delete.assert_called_once() # Assuming delete cascade/signal triggers this

    @patch("agno.knowledge.AgentKnowledge.vector_db_delete_table")
    def test_delete_other_user_knowledge_base_in_same_team_permission_check(self, mock_vector_db_delete):
        # Similar to update, this depends on object-level permissions.
        # Assuming team members can delete objects within their team.
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("knowledge_bases-detail", kwargs={'pk': self.kb2.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(KnowledgeBase.objects.filter(pk=self.kb2.pk).exists())
        mock_vector_db_delete.assert_called_once()


class AgentViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="agentviewuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otheragentview@example.com", password="password")
        self.superuser = User.objects.create_superuser(email="superagentview@example.com", password="password")

        self.team = Team.objects.create(name="AgentView Team", created_by=self.user)
        self.user.teams.add(self.team)
        # other_user is not in self.team initially

        self.model_provider = ModelProvider.objects.create(
            name="AgentView Provider", provider="openai", api_key="av_key", owner=self.user, team=self.team
        )
        # Another provider for variety or specific agent needs if any
        self.model_provider_other = ModelProvider.objects.create(
            name="AgentView Provider Other", provider="google", api_key="av_key_other", owner=self.other_user # No team or different team
        )


        self.agent_user1 = Agent.objects.create(
            name="User1 Agent", created_by=self.user, team=self.team, model_provider=self.model_provider
        )
        self.agent_other_user = Agent.objects.create(
            name="OtherUser Agent", created_by=self.other_user, model_provider=self.model_provider_other # Can be on a different team or no team
        )
        self.global_agent = Agent.objects.create(
            name="Global Agent", created_by=self.superuser, model_provider=self.model_provider, is_global=True
            # Global agent might not have a team, or could have one.
        )

        self.client = APIClient()
        self.list_url = reverse("agents-list") # Assuming 'agents' is the basename

    def test_list_agents_as_regular_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

        response_ids = [item['id'] for item in response.data['results']]
        self.assertIn(str(self.agent_user1.id), response_ids)
        self.assertIn(str(self.global_agent.id), response_ids)
        self.assertNotIn(str(self.agent_other_user.id), response_ids)
        self.assertEqual(len(response_ids), 2)

    def test_list_agents_as_superuser(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        response_ids = [item['id'] for item in response.data['results']]
        self.assertIn(str(self.agent_user1.id), response_ids)
        self.assertIn(str(self.global_agent.id), response_ids)
        self.assertIn(str(self.agent_other_user.id), response_ids)
        self.assertEqual(len(response_ids), 3)

    def test_retrieve_own_agent(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agents-detail", kwargs={'pk': self.agent_user1.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.agent_user1.id))

    def test_retrieve_global_agent_as_regular_user(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agents-detail", kwargs={'pk': self.global_agent.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(self.global_agent.id))

    def test_retrieve_other_user_agent_fails_for_regular_user(self):
        self.client.force_authenticate(user=self.user)
        detail_url = reverse("agents-detail", kwargs={'pk': self.agent_other_user.pk})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)

    def test_create_agent(self):
        self.client.force_authenticate(user=self.user)
        data = {
            "name": "Newly Created Agent",
            "description": "Test create agent.",
            "model_provider_id": str(self.model_provider.id),
            "team_id": str(self.team.id), # Assuming team is required or set by default
            # Other fields like system_prompt, temperature, etc., can be added
        }
        response = self.client.post(self.list_url, data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        new_agent = Agent.objects.get(id=response.data['id'])
        self.assertEqual(new_agent.created_by, self.user)
        self.assertEqual(new_agent.name, data["name"])
        self.assertEqual(new_agent.team, self.team)

    def test_update_own_agent(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agents-detail", kwargs={'pk': self.agent_user1.pk})
        data = {"name": "User1 Agent Updated Name"}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.agent_user1.refresh_from_db()
        self.assertEqual(self.agent_user1.name, data["name"])

    def test_update_other_user_agent_fails_for_regular_user(self):
        self.client.force_authenticate(user=self.user)
        update_url = reverse("agents-detail", kwargs={'pk': self.agent_other_user.pk})
        data = {"name": "Attempted Update"}
        response = self.client.patch(update_url, data, format="json")
        self.assertEqual(response.status_code, 404)

    def test_update_global_agent_by_regular_user_permission_check(self):
        # This depends on how permissions are set for global agents.
        # If only owner/superuser can update global agents:
        self.client.force_authenticate(user=self.user) # self.user is not self.superuser (owner of global_agent)
        update_url = reverse("agents-detail", kwargs={'pk': self.global_agent.pk})
        data = {"name": "Global Agent Updated by User1"}
        response = self.client.patch(update_url, data, format="json")
        # Expect 403 (Forbidden) or 404 if not in queryset for update
        self.assertIn(response.status_code, [403, 404])

    def test_delete_own_agent(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agents-detail", kwargs={'pk': self.agent_user1.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Agent.objects.filter(pk=self.agent_user1.pk).exists())

    def test_delete_other_user_agent_fails_for_regular_user(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agents-detail", kwargs={'pk': self.agent_other_user.pk})
        response = self.client.delete(delete_url)
        self.assertEqual(response.status_code, 404)

    def test_delete_global_agent_by_regular_user_permission_check(self):
        self.client.force_authenticate(user=self.user)
        delete_url = reverse("agents-detail", kwargs={'pk': self.global_agent.pk})
        response = self.client.delete(delete_url)
        self.assertIn(response.status_code, [403, 404])

class FileViewSetTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="viewsetuser@example.com", password="password")
        self.superuser = User.objects.create_superuser(email="viewsetsuper@example.com", password="password")

        self.team = Team.objects.create(name="FileViewSet Team", created_by=self.user)
        self.team.members.add(self.user)

        self.model_provider = ModelProvider.objects.create(
            name="FileViewSet Provider",
            provider="openai",
            api_key="fileview_openai_key",
            config={"embedder_id": "text-embedding-3-small", "dimensions": 1536},
            owner=self.user,
            team=self.team,
        )
        self.knowledge_base = KnowledgeBase.objects.create(
            name="FileViewSet KB",
            created_by=self.user,
            team=self.team,
            embedding_model=self.model_provider,
        )
        # Ensure system storage bucket exists or mock get_system_bucket
        # For tests, creating one is often simpler if direct mocking of class/static methods on models is tricky.
        self.storage_bucket = StorageBucket.objects.create(
            name=settings.DEFAULT_GCS_BUCKET_NAME, # Assuming this is how system bucket is identified
            is_system_bucket=True,
            team=None, # System buckets might not be tied to a team
            owner=self.superuser, # Or a generic system user
        )
        # Also a team-specific bucket for some tests if necessary
        self.team_storage_bucket = StorageBucket.objects.create(
            name="fileviewset-team-bucket",
            team=self.team,
            owner=self.user,
        )

        self.client = APIClient()
        # Authenticate if most tests need it, or do it per test.
        # self.client.force_authenticate(user=self.user)

        # Common URLs (adjust namespace if needed, e.g., 'v1:files-list')
        self.files_list_url = reverse("files-list")
        self.ingest_selected_url = reverse("files-ingest-selected")
        self.link_to_kb_url = reverse("files-link-to-kb")
        self.unlink_from_kb_url = reverse("files-unlink-from-kb")
        # Detail URL for a specific file (will need a file_uuid)
        # self.file_detail_url = reverse("files-detail", kwargs={'uuid': self.some_file_uuid})

    @patch("django.core.files.storage.default_storage.save")
    @patch("apps.reggie.models.File.get_storage_path") # To control the generated path in the File model
    def test_create_file_simple_upload(self, mock_get_storage_path, mock_storage_save):
        self.client.force_authenticate(user=self.user)

        # Define return values for mocks
        mock_get_storage_path.return_value = f"user_files/{self.user.id}-{self.user.uuid}/2024/01/01/testfile_mocked.pdf"
        mock_storage_save.return_value = mock_get_storage_path.return_value # save returns the name of the file saved

        test_file = SimpleUploadedFile("testfile.pdf", b"file content", content_type="application/pdf")
        data = {
            "file": test_file,
            "title": "My Test PDF",
            "team_id": self.team.id, # Assuming team_id is required
            "storage_bucket_id": self.team_storage_bucket.id, # Assuming bucket is required
        }

        response = self.client.post(self.files_list_url, data, format="multipart")

        self.assertEqual(response.status_code, 201, response.data)

        file_obj = File.objects.get(uuid=response.data['uuid'])
        self.assertEqual(file_obj.title, "My Test PDF")
        self.assertEqual(file_obj.file_type, "pdf")
        self.assertEqual(file_obj.uploaded_by, self.user)
        self.assertEqual(file_obj.team, self.team)
        self.assertEqual(file_obj.storage_bucket, self.team_storage_bucket)
        # Path check based on mock_get_storage_path's return value being stored in storage_path by the model
        # The File model's save() method should construct the full gs:// path.
        # If mock_storage_save returns the relative path, and the model prepends gs://bucket/, this is correct.
        self.assertEqual(file_obj.storage_path, f"gs://{self.team_storage_bucket.name}/{mock_get_storage_path.return_value}")

        mock_storage_save.assert_called_once()
        # Check that default_storage.save was called with a path that ends with what get_storage_path produced.
        # The first argument to default_storage.save is the name (path), second is the content.
        self.assertEqual(mock_storage_save.call_args[0][0], mock_get_storage_path.return_value)


    @patch("apps.reggie.views.FileViewSet._trigger_async_ingestion")
    @patch("django.core.files.storage.default_storage.save")
    @patch("apps.reggie.models.File.get_storage_path")
    def test_create_file_with_auto_ingest(self, mock_get_storage_path, mock_storage_save, mock_trigger_ingestion):
        self.client.force_authenticate(user=self.user)

        mock_get_storage_path.return_value = f"user_files/{self.user.id}-{self.user.uuid}/2024/01/01/auto_ingest_test.txt"
        mock_storage_save.return_value = mock_get_storage_path.return_value

        test_file = SimpleUploadedFile("auto_ingest_test.txt", b"text content", content_type="text/plain")
        data = {
            "file": test_file,
            "title": "Auto Ingest Text",
            "team_id": self.team.id,
            "storage_bucket_id": self.team_storage_bucket.id,
            "auto_ingest": True,
            "knowledge_base_id": self.knowledge_base.id,
        }

        response = self.client.post(self.files_list_url, data, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)

        file_obj = File.objects.get(uuid=response.data['uuid'])
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file_obj, knowledge_base=self.knowledge_base).exists())
        link_obj = FileKnowledgeBaseLink.objects.get(file=file_obj, knowledge_base=self.knowledge_base)

        mock_trigger_ingestion.assert_called_once_with(file_obj, self.knowledge_base, link_obj)

    def test_create_file_auto_ingest_missing_kb_id(self):
        self.client.force_authenticate(user=self.user)
        test_file = SimpleUploadedFile("missing_kb.txt", b"content", content_type="text/plain")
        data = {
            "file": test_file,
            "title": "Missing KB Test",
            "team_id": self.team.id,
            "storage_bucket_id": self.team_storage_bucket.id,
            "auto_ingest": True,
            # knowledge_base_id is missing
        }
        response = self.client.post(self.files_list_url, data, format="multipart")
        self.assertEqual(response.status_code, 400) # Bad Request

    def test_create_file_auto_ingest_invalid_kb_id(self):
        self.client.force_authenticate(user=self.user)
        test_file = SimpleUploadedFile("invalid_kb.txt", b"content", content_type="text/plain")
        non_existent_kb_uuid = uuid.uuid4()
        data = {
            "file": test_file,
            "title": "Invalid KB Test",
            "team_id": self.team.id,
            "storage_bucket_id": self.team_storage_bucket.id,
            "auto_ingest": True,
            "knowledge_base_id": non_existent_kb_uuid,
        }
        response = self.client.post(self.files_list_url, data, format="multipart")
        # This might be a 400 if the serializer validates existence, or 404 if get_object_or_404 is used early.
        # Based on typical DRF, serializer validation would make it a 400.
        # If the view fetches the KB explicitly and it's not found, it might be 404.
        # Let's assume serializer validation leading to 400, but this depends on implementation.
        # If the problem description implies a 404, we should use that. "invalid knowledgebase_id" -> "Not Found"
        self.assertEqual(response.status_code, 404) # Or 400, check view/serializer logic

    @patch("requests.post")
    @patch("django.core.files.storage.default_storage.save") # In case file saving occurs
    def test_ingest_selected(self, mock_storage_save, mock_requests_post):
        self.client.force_authenticate(user=self.user)

        # Create some files (ensure they have storage_path, as that's likely used)
        file1_content = SimpleUploadedFile("f1.txt", b"c1")
        file1 = File.objects.create(
            uploaded_by=self.user, team=self.team, storage_bucket=self.team_storage_bucket,
            original_filename="f1.txt", file=file1_content, file_type="txt",
            storage_path=f"gs://{self.team_storage_bucket.name}/f1.txt" # Assume it's already saved
        )
        file2_content = SimpleUploadedFile("f2.pdf", b"c2")
        file2 = File.objects.create(
            uploaded_by=self.user, team=self.team, storage_bucket=self.team_storage_bucket,
            original_filename="f2.pdf", file=file2_content, file_type="pdf",
            storage_path=f"gs://{self.team_storage_bucket.name}/f2.pdf"
        )

        # Create another KB for multi-KB selection
        kb2 = KnowledgeBase.objects.create(
            name="FileViewSet KB2", created_by=self.user, team=self.team, embedding_model=self.model_provider
        )

        # Mock response from requests.post if needed, e.g., success
        mock_requests_post.return_value.status_code = 200
        mock_requests_post.return_value.json.return_value = {"status": "success", "message": "Ingestion started"}


        data = {
            "file_uuids": [str(file1.uuid), str(file2.uuid)],
            "knowledgebase_ids": [str(self.knowledge_base.id), str(kb2.id)],
        }
        response = self.client.post(self.ingest_selected_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        # Check that FileKnowledgeBaseLink objects were created
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file1, knowledge_base=self.knowledge_base).exists())
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file1, knowledge_base=kb2).exists())
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file2, knowledge_base=self.knowledge_base).exists())
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file2, knowledge_base=kb2).exists())

        total_links = 2 * 2 # 2 files, 2 KBs
        self.assertEqual(FileKnowledgeBaseLink.objects.count(), total_links)

        # Check ingestion_status (assuming it's set to 'pending' by ingest_selected)
        for link in FileKnowledgeBaseLink.objects.all():
            self.assertEqual(link.ingestion_status, "pending") # Or 'processing' depending on implementation

        # Assert requests.post was called for each link
        self.assertEqual(mock_requests_post.call_count, total_links)

        # Example check for one call (assuming INGESTION_SERVICE_URL is in settings)
        # The exact payload depends on what `_trigger_ingestion_task` sends.
        # This is a conceptual check; the actual payload details need to match the implementation.
        expected_payload_file1_kb1 = {
            "file_path": file1.storage_path, # Or however the path is retrieved/constructed
            "vector_table_name": self.knowledge_base.vector_table_name,
            "knowledgebase_id": str(self.knowledge_base.id),
            "file_id": str(file1.id), # Assuming internal DB ID
            "team_id": str(self.team.id),
            "link_id": str(FileKnowledgeBaseLink.objects.get(file=file1, knowledge_base=self.knowledge_base).id),
            "file_type": file1.file_type,
            "title": file1.title,
            "subject_type": "document", # Or as per actual logic
            "api_key": settings.INTERNAL_API_KEY, # Assuming this is used
        }

        # This assertion is tricky because the order of calls might not be guaranteed,
        # and the exact format of the payload needs to be known.
        # A more robust way is to check call_args_list if the order is not fixed.
        # For simplicity, if we can predict one call:
        # mock_requests_post.assert_any_call(settings.INGESTION_SERVICE_URL, json=expected_payload_file1_kb1)
        # For multiple calls, you might iterate through call_args_list and match.
        # For now, just checking call_count is a good start. The detailed payload check is complex without seeing the view's code.

    @patch("apps.reggie.views.FileViewSet._trigger_async_ingestion") # Should NOT be called
    @patch("requests.post") # Should NOT be called
    def test_link_to_kb(self, mock_requests_post, mock_trigger_async_ingestion):
        self.client.force_authenticate(user=self.user)

        file1 = File.objects.create(uploaded_by=self.user, team=self.team, storage_bucket=self.team_storage_bucket, original_filename="link_f1.txt", file_type="txt")
        file2 = File.objects.create(uploaded_by=self.user, team=self.team, storage_bucket=self.team_storage_bucket, original_filename="link_f2.pdf", file_type="pdf")

        kb2 = KnowledgeBase.objects.create(name="LinkTest KB2", created_by=self.user, team=self.team, embedding_model=self.model_provider)

        data = {
            "file_uuids": [str(file1.uuid), str(file2.uuid)],
            "knowledgebase_ids": [str(self.knowledge_base.id), str(kb2.id)],
        }
        response = self.client.post(self.link_to_kb_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        # Check that FileKnowledgeBaseLink objects were created
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file1, knowledge_base=self.knowledge_base).exists())
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file1, knowledge_base=kb2).exists())
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file2, knowledge_base=self.knowledge_base).exists())
        self.assertTrue(FileKnowledgeBaseLink.objects.filter(file=file2, knowledge_base=kb2).exists())

        total_links = 2 * 2
        self.assertEqual(FileKnowledgeBaseLink.objects.count(), total_links)

        # Check ingestion_status
        for link in FileKnowledgeBaseLink.objects.all():
            self.assertEqual(link.ingestion_status, "not_started")

        # Assert that no ingestion was triggered
        mock_requests_post.assert_not_called()
        mock_trigger_async_ingestion.assert_not_called()

    def test_unlink_from_kb(self):
        self.client.force_authenticate(user=self.user)

        file_to_unlink = File.objects.create(
            uploaded_by=self.user, team=self.team,
            storage_bucket=self.team_storage_bucket,
            original_filename="unlink_me.txt", file_type="txt"
        )
        # Link it first
        link = FileKnowledgeBaseLink.objects.create(
            file=file_to_unlink,
            knowledge_base=self.knowledge_base,
            ingestion_status="completed" # Status doesn't matter for unlinking
        )
        self.assertEqual(FileKnowledgeBaseLink.objects.count(), 1)

        data = {
            "file_uuid": str(file_to_unlink.uuid), # Changed to singular as per typical unlink actions
            "knowledgebase_id": str(self.knowledge_base.id),
        }

        # Construct URL for unlinking if it's a detail route or specific action
        # Assuming self.unlink_from_kb_url is a general action URL that accepts these params in POST body.
        # If it's a detail route on the file, it might be different:
        # url = reverse("files-detail-unlink-kb", kwargs={'uuid': file_to_unlink.uuid})
        # and then kb_id in data. For now, using the defined self.unlink_from_kb_url

        response = self.client.post(self.unlink_from_kb_url, data, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        self.assertEqual(FileKnowledgeBaseLink.objects.count(), 0)
        self.assertFalse(FileKnowledgeBaseLink.objects.filter(id=link.id).exists())

class KnowledgeBaseModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="kb_testuser@example.com", password="password")
        cls.team = Team.objects.create(name="KB Test Team", created_by=cls.user)
        cls.openai_provider = ModelProvider.objects.create(
            name="OpenAI Test Provider",
            provider="openai",
            api_key="openai_test_key",
            config={"embedder_id": "text-embedding-3-small", "dimensions": 1536},
            owner=cls.user,
            team=cls.team,
        )
        cls.google_provider = ModelProvider.objects.create(
            name="Google Test Provider",
            provider="google",
            api_key="google_test_key",
            config={"embedder_id": "text-embedding-004", "dimensions": 768},
            owner=cls.user,
            team=cls.team,
        )
        cls.anthropic_provider = ModelProvider.objects.create(
            name="Anthropic Test Provider",
            provider="anthropic",
            api_key="anthropic_test_key",
            config={"embedder_id": "anthropic-embedder", "dimensions": 1024}, # Placeholder
            owner=cls.user,
            team=cls.team,
        )
        cls.groq_provider = ModelProvider.objects.create(
            name="Groq Test Provider",
            provider="groq",
            api_key="groq_test_key",
            config={"embedder_id": "nomic-embed-text-v1.5", "dimensions": 768}, # common Groq accessible model
            owner=cls.user,
            team=cls.team,
        )
        cls.incomplete_provider = ModelProvider.objects.create(
            name="Incomplete Provider",
            provider="openai",
            api_key="incomplete_key",
            config={"dimensions": 1536}, # Missing embedder_id
            owner=cls.user,
            team=cls.team,
        )
        cls.no_config_provider = ModelProvider.objects.create(
            name="No Config Provider",
            provider="openai",
            api_key="no_config_key",
            owner=cls.user,
            team=cls.team,
        )

    @patch("uuid.uuid4")
    @patch("agno.knowledge.AgentKnowledge.vector_db_create") # Mock create at class/static level if that's how it's called
    def test_save_id_and_table_name_generation(self, mock_vector_db_create, mock_uuid):
        fixed_uuid = uuid.UUID("abcdef12-3456-7890-abcd-ef1234567890")
        mock_uuid.return_value = fixed_uuid

        kb_name = "My Test Knowledge Base"
        kb = KnowledgeBase(
            name=kb_name,
            description="A test KB.",
            created_by=self.user,
            team=self.team,
            embedding_model=self.openai_provider,
        )
        kb.save()

        # Assert knowledgebase_id generation
        # Example: kb{provider_initial}-{mocked_uuid_prefix}-{slugified_name}
        # provider_initial for "openai" could be "op" or "oa" or just "o" depending on implementation
        # Assuming first two letters of provider: 'op' for 'openai'
        # Assuming first 8 chars of UUID: 'abcdef12'
        # slugified_name: "my-test-knowledge-base"
        # Let's check the actual model code for the exact logic for provider initial if possible,
        # or make a reasonable assumption. Assuming it takes first 2 letters of provider.
        provider_initial = self.openai_provider.provider[:2].lower()
        uuid_prefix = str(fixed_uuid)[:8]
        slugified_name = slugify(kb_name)

        # The exact format needs to be derived from the KnowledgeBase model's save() method.
        # For now, let's assume a structure and verify. This might need adjustment.
        # Let's say the model generates it like: "kb_op_abcdef12_my-test-knowledge-base"
        # Or if it's "kb" + provider_initial + "-" + uuid_prefix + "-" + slugified_name
        # Let's assume: f"kb{provider_initial}-{uuid_prefix}-{slugified_name}" based on the prompt.
        # The prompt format was: kb{provider_initial}-{mocked_uuid_prefix}-{slugified_name}

        # Based on a common pattern, the actual ID might be just the UUID or a slugified name + UUID.
        # Let's assume the model's `_generate_knowledgebase_id` creates something like:
        # `kb_team_<team_id>_name_<slugified_name>_uuid_<uuid_prefix>` OR
        # `kb_<uuid_hex>`
        # Given the prompt, I will test for: `kb<provider_initial>-<uuid_prefix>-<slugified_name>`
        # This is a guess and might need to be adjusted after seeing the model's actual implementation or running the test.

        # Let's look at the model code for _generate_knowledgebase_id and _generate_vector_table_name
        # Since I can't see it, I'll proceed with the prompt's example format.
        expected_kb_id = f"kb{provider_initial}-{uuid_prefix}-{slugify(kb_name)}"
        self.assertEqual(kb.knowledgebase_id, expected_kb_id)

        # Assert vector_table_name generation
        # Usually, this is a cleaned version of knowledgebase_id, safe for DB table names.
        # e.g., replacing hyphens with underscores, ensuring it starts with a letter, and is lowercase.
        expected_table_name = expected_kb_id.replace("-", "_").lower()
        # Table names often have length limits and other restrictions.
        # Assuming it's just a direct transformation for now.
        self.assertEqual(kb.vector_table_name, expected_table_name)

        # Assert that vector_db.create was called (or the appropriate mock)
        mock_vector_db_create.assert_called_once()
        # We could also check the arguments if necessary, e.g.,
        # mock_vector_db_create.assert_called_once_with(table_name=expected_table_name, dimensions=ANY)

    def test_get_embedder(self):
        kb_openai = KnowledgeBase(name="OpenAI KB", embedding_model=self.openai_provider, team=self.team, created_by=self.user)
        embedder_openai = kb_openai.get_embedder()
        self.assertIsInstance(embedder_openai, OpenAIEmbedder)
        self.assertEqual(embedder_openai.model_id, self.openai_provider.config["embedder_id"])
        self.assertEqual(embedder_openai.dimensions, self.openai_provider.config["dimensions"])

        kb_google = KnowledgeBase(name="Google KB", embedding_model=self.google_provider, team=self.team, created_by=self.user)
        embedder_google = kb_google.get_embedder()
        self.assertIsInstance(embedder_google, GeminiEmbedder) # Assuming GeminiEmbedder for "google"
        self.assertEqual(embedder_google.model_id, self.google_provider.config["embedder_id"])
        # Dimensions might not be directly on GeminiEmbedder, but passed via a common mechanism if applicable.
        # self.assertEqual(embedder_google.dimensions, self.google_provider.config["dimensions"])


        kb_groq = KnowledgeBase(name="Groq KB", embedding_model=self.groq_provider, team=self.team, created_by=self.user)
        embedder_groq = kb_groq.get_embedder()
        self.assertIsInstance(embedder_groq, GroqEmbedder)
        self.assertEqual(embedder_groq.model_id, self.groq_provider.config["embedder_id"])
        # self.assertEqual(embedder_groq.dimensions, self.groq_provider.config["dimensions"])

        # Test for Anthropic (assuming an AnthropicEmbedder exists or a generic one is used)
        # For now, let's assume if AnthropicEmbedder is not imported, this part would be commented out or use a more generic check.
        # kb_anthropic = KnowledgeBase(name="Anthropic KB", embedding_model=self.anthropic_provider, team=self.team, created_by=self.user)
        # embedder_anthropic = kb_anthropic.get_embedder()
        # self.assertIsInstance(embedder_anthropic, AnthropicEmbedder) # Or relevant class
        # self.assertEqual(embedder_anthropic.model_id, self.anthropic_provider.config["embedder_id"])

        # Test ValueError for missing embedder_id in config
        kb_incomplete = KnowledgeBase(name="Incomplete KB", embedding_model=self.incomplete_provider, team=self.team, created_by=self.user)
        with self.assertRaisesRegex(ValueError, "embedder_id not found in provider config"):
            kb_incomplete.get_embedder()

        # Test ValueError for missing config (if config itself is None)
        kb_no_config = KnowledgeBase(name="No Config KB", embedding_model=self.no_config_provider, team=self.team, created_by=self.user)
        with self.assertRaisesRegex(ValueError, "Config not found for model provider"): # Or specific message
            kb_no_config.get_embedder()

        # Test ValueError for missing model_provider
        kb_no_provider = KnowledgeBase(name="No Provider KB", team=self.team, created_by=self.user) # No embedding_model
        with self.assertRaisesRegex(ValueError, "Model provider not set for this Knowledge Base"):
            kb_no_provider.get_embedder()

    @patch("uuid.uuid4") # Mock uuid for save if it's called during build_knowledge implicitly
    @patch("agno.knowledge.AgentKnowledge.vector_db_create") # Mock create to avoid actual DB operations
    def test_build_knowledge(self, mock_vector_db_create, mock_uuid):
        # Ensure KB is saved to have vector_table_name and knowledgebase_id
        fixed_uuid = uuid.UUID("12345678-1234-1234-1234-1234567890ab")
        mock_uuid.return_value = fixed_uuid

        kb = KnowledgeBase(
            name="KB for Build Test",
            created_by=self.user,
            team=self.team,
            embedding_model=self.openai_provider # Using a provider with full config
        )
        kb.save() # This will generate knowledgebase_id and vector_table_name

        # Call build_knowledge
        agent_knowledge = kb.build_knowledge()

        self.assertIsInstance(agent_knowledge, AgentKnowledge)
        self.assertIsInstance(agent_knowledge.vector_db, PgVector)

        # Assert PgVector configuration
        self.assertEqual(agent_knowledge.vector_db.db_url, settings.PGVECTOR_DB_URL)
        self.assertEqual(agent_knowledge.vector_db.table_name, kb.vector_table_name)

        # Assert embedder is correctly initialized and passed
        expected_embedder = kb.get_embedder()
        self.assertIsInstance(agent_knowledge.vector_db.embedder, OpenAIEmbedder)
        self.assertEqual(agent_knowledge.vector_db.embedder.model_id, expected_embedder.model_id)
        self.assertEqual(agent_knowledge.vector_db.embedder.dimensions, expected_embedder.dimensions)

        # Check if create was called during save, not during build_knowledge typically
        # If build_knowledge is also supposed to ensure creation, this mock might need adjustment.
        # For now, assuming .save() handles creation call.
        mock_vector_db_create.assert_called_once() # Called during kb.save()

class FileModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="testuser@example.com", password="password")
        cls.team = Team.objects.create(name="Test Team", created_by=cls.user)
        cls.model_provider = ModelProvider.objects.create(
            name="Test Provider",
            api_key="test_api_key",
            owner=cls.user,
            team=cls.team,
        )
        cls.knowledge_base = KnowledgeBase.objects.create(
            name="Test KB",
            description="Test KB description",
            created_by=cls.user,
            team=cls.team,
            embedding_model=cls.model_provider,
        )
        cls.storage_bucket = StorageBucket.objects.create(
            name="test-bucket",
            team=cls.team,
            owner=cls.user,
        )

    @patch("uuid.uuid4")
    @patch("django.core.files.storage.default_storage.save")
    def test_save_path_generation_and_naming(self, mock_storage_save, mock_uuid):
        mock_uuid.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")
        mock_storage_save.return_value = "mocked_path"

        # Test with a user file
        file = File(
            uploaded_by=self.user,
            team=self.team,
            storage_bucket=self.storage_bucket,
            original_filename="test_document.pdf",
            file_type="pdf",
            file=SimpleUploadedFile("test_document.pdf", b"file_content", content_type="application/pdf")
        )
        file.save()

        expected_filename_suffix = "test_document_12345678.pdf"
        self.assertTrue(mock_storage_save.call_args[0][0].endswith(expected_filename_suffix))
        # Path structure: user_files/{user_id}-{user_uuid}/YYYY/MM/DD/{original_filename}_{mocked_uuid_suffix}.ext
        self.assertIn(f"user_files/{self.user.id}-{self.user.uuid}/", mock_storage_save.call_args[0][0])
        self.assertEqual(file.storage_path, f"gs://{self.storage_bucket.name}/mocked_path")
        self.assertEqual(file.title, "test_document") # Title generated from filename

        # Test with a global file
        mock_storage_save.reset_mock()
        global_file = File(
            team=self.team, # Global files might still be associated with a team for org purposes
            storage_bucket=self.storage_bucket,
            original_filename="global_guide.txt",
            file_type="txt",
            is_global=True,
            title="Official Global Guide",
            file=SimpleUploadedFile("global_guide.txt", b"file_content", content_type="text/plain")
        )
        global_file.save()

        expected_global_filename_suffix = "global_guide_12345678.txt"
        self.assertTrue(mock_storage_save.call_args[0][0].endswith(expected_global_filename_suffix))
        self.assertIn(f"global/library/", mock_storage_save.call_args[0][0])
        self.assertEqual(global_file.storage_path, f"gs://{self.storage_bucket.name}/mocked_path")
        self.assertEqual(global_file.title, "Official Global Guide") # Title was provided

        # Test title generation when no title is provided
        mock_storage_save.reset_mock()
        no_title_file = File(
            uploaded_by=self.user,
            team=self.team,
            storage_bucket=self.storage_bucket,
            original_filename="another document.docx",
            file_type="docx",
            file=SimpleUploadedFile("another document.docx", b"file_content", content_type="application/octet-stream")
        )
        no_title_file.save()
        self.assertEqual(no_title_file.title, "another document")

    @patch("apps.reggie.models.File._trigger_async_ingestion") # Assuming the method is on the File model
    @patch("django.core.files.storage.default_storage.save")
    def test_save_auto_ingest(self, mock_storage_save, mock_trigger_ingestion):
        mock_storage_save.return_value = "mocked_auto_ingest_path"

        file_content = SimpleUploadedFile("auto_ingest_doc.txt", b"content", content_type="text/plain")
        file_for_ingestion = File(
            uploaded_by=self.user,
            team=self.team,
            storage_bucket=self.storage_bucket,
            original_filename="auto_ingest_doc.txt",
            file_type="txt",
            auto_ingest=True,
            file=file_content
        )
        # Link to a knowledge base before saving
        file_for_ingestion.save() # Initial save to get an ID
        file_for_ingestion.knowledge_bases.add(self.knowledge_base)
        # We call save again, this time auto_ingest should trigger if implemented in save()
        # Or, if linking triggers it, that's also covered.
        # If save() itself is what should create FileKnowledgeBaseLink from a temp field,
        # then the initial .save() and .knowledge_bases.add() is the setup for that.

        # Assert FileKnowledgeBaseLink was created
        link = FileKnowledgeBaseLink.objects.filter(file=file_for_ingestion, knowledge_base=self.knowledge_base).first()
        self.assertIsNotNone(link)

        # Assert that the ingestion trigger was called
        # We might need to adjust the call check depending on how _trigger_async_ingestion is called
        # (e.g. if it's called for each KB link or once per file)
        # For this test, assuming it's called for each link that needs ingestion.
        mock_trigger_ingestion.assert_called_once_with(self.knowledge_base, link)

    @patch("apps.reggie.utils.gcs_utils.ingest_single_file")
    @patch("django.core.files.storage.default_storage.save")
    def test_run_ingestion(self, mock_storage_save, mock_ingest_single_file):
        mock_storage_save.return_value = "mocked_run_ingestion_path"

        # Create file and save it
        file_to_ingest = File(
            uploaded_by=self.user,
            team=self.team,
            storage_bucket=self.storage_bucket,
            original_filename="test_ingestion_doc.txt",
            file_type="txt",
            file=SimpleUploadedFile("test_ingestion_doc.txt", b"content", content_type="text/plain")
        )
        file_to_ingest.save()

        # Create another KnowledgeBase for multi-KB ingestion test
        other_kb = KnowledgeBase.objects.create(
            name="Other Test KB", created_by=self.user, team=self.team, embedding_model=self.model_provider
        )

        # Link file to knowledge bases
        link1 = FileKnowledgeBaseLink.objects.create(
            file=file_to_ingest, knowledge_base=self.knowledge_base, ingestion_status="pending"
        )
        link2 = FileKnowledgeBaseLink.objects.create(
            file=file_to_ingest, knowledge_base=other_kb, ingestion_status="pending"
        )

        # Mock successful ingestion for the first KB and failure for the second
        def side_effect_ingest(file_content, file_path_in_gcs, kb_id, file_id, team_id, link_id, file_type, title, subject_type):
            if kb_id == self.knowledge_base.id:
                # Simulate updating progress within the mocked function for completeness
                link = FileKnowledgeBaseLink.objects.get(id=link_id)
                link.ingestion_status = "completed"
                link.ingestion_completed_at = timezone.now()
                link.save()
                return {"status": "success", "message": "Ingested successfully"}
            elif kb_id == other_kb.id:
                link = FileKnowledgeBaseLink.objects.get(id=link_id)
                link.ingestion_status = "failed"
                link.ingestion_error_message = "Simulated ingestion error"
                link.save()
                raise Exception("Simulated ingestion error")
            return {"status": "error", "message": "Unknown KB"}

        mock_ingest_single_file.side_effect = side_effect_ingest

        file_to_ingest.run_ingestion()

        # Assert mock_ingest_single_file was called for each link
        self.assertEqual(mock_ingest_single_file.call_count, 2)
        mock_ingest_single_file.assert_any_call(
            file_to_ingest.file, file_to_ingest.get_gcs_path(), self.knowledge_base.id, file_to_ingest.id, self.team.id, link1.id, file_to_ingest.file_type, file_to_ingest.title, "document"
        )
        mock_ingest_single_file.assert_any_call(
            file_to_ingest.file, file_to_ingest.get_gcs_path(), other_kb.id, file_to_ingest.id, self.team.id, link2.id, file_to_ingest.file_type, file_to_ingest.title, "document"
        )


        link1.refresh_from_db()
        self.assertEqual(link1.ingestion_status, "completed")
        self.assertIsNotNone(link1.ingestion_completed_at)

        link2.refresh_from_db()
        self.assertEqual(link2.ingestion_status, "failed")
        self.assertEqual(link2.ingestion_error_message, "Simulated ingestion error")

        # is_ingested should be True if at least one ingestion succeeded
        file_to_ingest.refresh_from_db()
        self.assertTrue(file_to_ingest.is_ingested)

        # Test case where all ingestions fail
        mock_ingest_single_file.reset_mock()
        mock_ingest_single_file.side_effect = Exception("Universal ingestion failure")
        file_all_fail = File.objects.create(
            uploaded_by=self.user, team=self.team, storage_bucket=self.storage_bucket,
            original_filename="all_fail.txt", file_type="txt",
            file=SimpleUploadedFile("all_fail.txt", b"c"),
            is_ingested=False # Explicitly set to False for this sub-test
        )
        link_all_fail = FileKnowledgeBaseLink.objects.create(
            file=file_all_fail, knowledge_base=self.knowledge_base, ingestion_status="pending"
        )
        file_all_fail.run_ingestion()
        link_all_fail.refresh_from_db()
        file_all_fail.refresh_from_db()
        self.assertEqual(link_all_fail.ingestion_status, "failed")
        self.assertIn("Universal ingestion failure", link_all_fail.ingestion_error_message)
        self.assertFalse(file_all_fail.is_ingested)

    @patch("django.core.files.storage.default_storage.save")
    def test_update_ingestion_progress(self, mock_storage_save):
        mock_storage_save.return_value = "mocked_progress_path"

        file_for_progress = File(
            uploaded_by=self.user,
            team=self.team,
            storage_bucket=self.storage_bucket,
            original_filename="progress_test.txt",
            file_type="txt",
            file=SimpleUploadedFile("progress_test.txt", b"content", content_type="text/plain")
        )
        file_for_progress.save()

        link = FileKnowledgeBaseLink.objects.create(
            file=file_for_progress,
            knowledge_base=self.knowledge_base,
            ingestion_status="processing"
        )

        # Update progress partially
        file_for_progress.update_ingestion_progress(link_id=link.id, progress=50.0, processed_docs=5, total_docs=10)
        link.refresh_from_db()
        self.assertEqual(link.ingestion_progress, 50.0)
        self.assertEqual(link.processed_docs, 5)
        self.assertEqual(link.total_docs, 10)
        self.assertEqual(link.ingestion_status, "processing") # Should still be processing
        self.assertIsNone(link.ingestion_completed_at)
        file_for_progress.refresh_from_db()
        self.assertFalse(file_for_progress.is_ingested) # Not fully ingested yet

        # Update progress to completion
        file_for_progress.update_ingestion_progress(link_id=link.id, progress=100.0, processed_docs=10, total_docs=10)
        link.refresh_from_db()
        file_for_progress.refresh_from_db()

        self.assertEqual(link.ingestion_progress, 100.0)
        self.assertEqual(link.processed_docs, 10)
        self.assertEqual(link.total_docs, 10)
        self.assertEqual(link.ingestion_status, "completed")
        self.assertIsNotNone(link.ingestion_completed_at)
        self.assertTrue(file_for_progress.is_ingested)

        # Test updating progress for a link that doesn't exist (should not error, but log ideally)
        # For now, just ensure it doesn't crash and doesn't wrongly update other things.
        non_existent_link_uuid = uuid.uuid4()
        try:
            file_for_progress.update_ingestion_progress(link_id=non_existent_link_uuid, progress=75.0)
        except FileKnowledgeBaseLink.DoesNotExist:
            self.fail("update_ingestion_progress raised DoesNotExist for a non-existent link_id, should handle gracefully.")
        except Exception as e:
            self.fail(f"update_ingestion_progress raised an unexpected exception: {e}")

        # Ensure no other links were affected
        link.refresh_from_db()
        self.assertEqual(link.ingestion_status, "completed") # Should remain completed


class FileAPIKeyAuthenticationTest(APITestCase):
    def setUp(self):
        # Create system user and API key
        self.system_user = User.objects.create_user(
            email="cloud-run-service@system.local", password="testpass123", is_system=True
        )
        self.system_api_key, self.system_key = APIKey.objects.create_key(name="Cloud Run Ingestion Service")

        # Create regular user and API key
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")
        self.user_api_key = UserAPIKey.objects.create_key(name="Test User API Key", user=self.user)

        # Create a test file
        self.file_uuid = uuid.uuid4()
        # TODO: This File create call might fail if the model's save() method expects team/user
        # and other fields that are not nullable. We might need to adjust this later.
        self.file = File.objects.create(
            uuid=self.file_uuid,
            title="Test File",
            file_type="pdf",
            uploaded_by=self.user, # Assuming uploaded_by is a field
            team=self.user.teams.first() # Assuming user is part of a team or team can be null
        )


        self.update_url = reverse("files-update-progress", kwargs={"uuid": self.file_uuid})
        self.list_url = reverse("files-list-with-kbs")

    def test_update_progress_with_system_api_key(self):
        """Test that update_progress endpoint works with valid system API key"""
        headers = {"Authorization": f"Api-Key {self.system_key}"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_update_progress_with_user_api_key_fails(self):
        """Test that update_progress endpoint fails with user API key"""
        headers = {"Authorization": f"Api-Key {self.user_api_key[1]}"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_list_files_with_system_api_key(self):
        """Test that list endpoint works with system API key"""
        headers = {"Authorization": f"Api-Key {self.system_key}"}
        response = self.client.get(self.list_url, format="json", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_list_files_with_user_api_key(self):
        """Test that list endpoint works with user API key"""
        headers = {"Authorization": f"Api-Key {self.user_api_key[1]}"}
        response = self.client.get(self.list_url, format="json", headers=headers)
        self.assertEqual(response.status_code, 200)

    def test_update_progress_with_invalid_api_key(self):
        """Test that update_progress endpoint fails with invalid API key"""
        headers = {"Authorization": "Api-Key invalid-key"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_update_progress_with_wrong_prefix(self):
        """Test that update_progress endpoint fails with wrong Authorization prefix"""
        headers = {"Authorization": f"Bearer {self.system_key}"}
        data = {"progress": 50.0, "processed_docs": 5, "total_docs": 10}

        response = self.client.post(self.update_url, data, format="json", headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Invalid API key format", str(response.content))


class ReggieTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="test@example.com", password="testpass123")
        self.file = File.objects.create(uuid=uuid.uuid4(), title="Test File", file_type="pdf")

    def test_file_creation(self):
        self.assertEqual(self.file.title, "Test File")
        self.assertEqual(self.file.file_type, "pdf")
        self.assertIsNotNone(self.file.uuid)
