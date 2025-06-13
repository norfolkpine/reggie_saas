from django.urls import reverse
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from unittest.mock import patch, MagicMock

# LlamaIndex imports for type checking/mocking (adjust paths based on actual LlamaIndex version)
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
from llama_index.core.indices.vector_store import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever

from apps.users.models import CustomUser
from apps.teams.models import Team
from apps.reggie.models import KnowledgeBase, ModelProvider, Agent as DjangoAgent
from apps.reggie.agents.agent_builder import AgentBuilder

# User = get_user_model() # Use this if you prefer flexibility

class KnowledgeBaseAccessTests(APITestCase):
    def setUp(self):
        self.owner_user = CustomUser.objects.create_user(username='kb_owner', email='kb_owner@test.com', password='password123', display_name='KB Owner')
        self.team_member_user = CustomUser.objects.create_user(username='kb_team_member', email='kb_team_member@test.com', password='password123', display_name='KB Team Member')
        self.other_user = CustomUser.objects.create_user(username='kb_other', email='kb_other@test.com', password='password123', display_name='KB Other User')
        self.another_owner = CustomUser.objects.create_user(username='kb_another_owner', email='kb_another_owner@test.com', password='password123', display_name='KB Another Owner')
        self.superuser = CustomUser.objects.create_superuser(username='kb_superuser', email='kb_superuser@test.com', password='password123')

        self.team_a = Team.objects.create(name='KB Access Team A', owner=self.owner_user)
        self.team_a.members.add(self.team_member_user)

        self.model_provider = ModelProvider.objects.create(provider="test_provider", model_name="test_model", embedder_id="test_embedder")

        self.kb_owned = KnowledgeBase.objects.create(
            name="Owned KB",
            owner=self.owner_user,
            model_provider=self.model_provider
        )
        self.kb_team = KnowledgeBase.objects.create(
            name="Team A KB",
            team=self.team_a,
            owner=self.owner_user, # A KB can have an owner and also be assigned to a team
            model_provider=self.model_provider
        )
        self.kb_global = KnowledgeBase.objects.create(
            name="Global KB",
            is_global=True,
            owner=self.owner_user, # Global KBs can still have an owner
            model_provider=self.model_provider
        )
        self.kb_other_owner = KnowledgeBase.objects.create(
            name="Other Owner's KB",
            owner=self.another_owner,
            model_provider=self.model_provider
        )

        # Agents for AgentBuilder tests
        self.agent_with_kb_owned = DjangoAgent.objects.create(
            name="Agent With Owned KB",
            user=self.owner_user, # Agent owned by owner_user
            knowledge_base=self.kb_owned,
            agent_id="agent_kb_owned_test",
            model=self.model_provider
        )
        self.agent_with_kb_other = DjangoAgent.objects.create(
            name="Agent With Other KB",
            user=self.owner_user, # Agent also owned by owner_user
            knowledge_base=self.kb_other_owner, # But KB is owned by another_owner
            agent_id="agent_kb_other_test",
            model=self.model_provider
        )
        self.agent_with_global_kb = DjangoAgent.objects.create(
            name="Agent With Global KB",
            user=self.other_user, # Agent owned by other_user
            knowledge_base=self.kb_global,
            agent_id="agent_kb_global_test",
            model=self.model_provider
        )
        self.agent_with_team_kb = DjangoAgent.objects.create(
            name="Agent With Team KB",
            user=self.team_member_user, # Agent owned by team_member_user
            knowledge_base=self.kb_team,
            agent_id="agent_kb_team_test",
            model=self.model_provider
        )

        self.client = APIClient()
        self.kb_list_url = reverse('knowledgebase-list') # Check your router for actual name

        # Setup for LlamaIndex filtering tests
        self.kb_for_filtering_test = KnowledgeBase.objects.create(
            name="LlamaIndex Filtering Test KB",
            owner=self.owner_user,
            model_provider=self.model_provider,
            knowledge_type="llamaindex"  # Crucial for this test
        )
        self.agent_for_filtering = DjangoAgent.objects.create(
            name="Agent for LlamaIndex Filtering",
            user=self.owner_user,
            knowledge_base=self.kb_for_filtering_test,
            agent_id="agent_filter_test_llamaindex",
            model=self.model_provider
        )


    # --- KnowledgeBaseViewSet: get_queryset Tests ---
    def test_list_kbs_for_owner_user(self):
        self.client.force_authenticate(user=self.owner_user)
        response = self.client.get(self.kb_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kb_names = [item['name'] for item in response.data.get('results', response.data)] # Handle pagination
        self.assertIn(self.kb_owned.name, kb_names)
        self.assertIn(self.kb_global.name, kb_names)
        self.assertIn(self.kb_team.name, kb_names) # owner_user also created kb_team
        self.assertNotIn(self.kb_other_owner.name, kb_names)

    def test_retrieve_owned_kb_for_owner_user(self):
        self.client.force_authenticate(user=self.owner_user)
        url = reverse('knowledgebase-detail', kwargs={'pk': self.kb_owned.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.kb_owned.name)

    def test_list_kbs_for_team_member(self):
        self.client.force_authenticate(user=self.team_member_user)
        response = self.client.get(self.kb_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kb_names = [item['name'] for item in response.data.get('results', response.data)]
        self.assertIn(self.kb_team.name, kb_names)
        self.assertIn(self.kb_global.name, kb_names)
        self.assertNotIn(self.kb_owned.name, kb_names)
        self.assertNotIn(self.kb_other_owner.name, kb_names)

    def test_retrieve_team_kb_for_team_member(self):
        self.client.force_authenticate(user=self.team_member_user)
        url = reverse('knowledgebase-detail', kwargs={'pk': self.kb_team.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.kb_team.name)

    def test_list_kbs_for_other_user(self):
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(self.kb_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kb_names = [item['name'] for item in response.data.get('results', response.data)]
        self.assertIn(self.kb_global.name, kb_names)
        self.assertNotIn(self.kb_owned.name, kb_names)
        self.assertNotIn(self.kb_team.name, kb_names)
        self.assertNotIn(self.kb_other_owner.name, kb_names)


    def test_retrieve_global_kb_for_other_user(self):
        self.client.force_authenticate(user=self.other_user)
        url = reverse('knowledgebase-detail', kwargs={'pk': self.kb_global.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], self.kb_global.name)

    def test_other_user_cannot_retrieve_owned_kb(self):
        self.client.force_authenticate(user=self.other_user)
        url = reverse('knowledgebase-detail', kwargs={'pk': self.kb_owned.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


    def test_list_kbs_for_superuser(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.kb_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kb_names = [item['name'] for item in response.data.get('results', response.data)]
        self.assertIn(self.kb_owned.name, kb_names)
        self.assertIn(self.kb_team.name, kb_names)
        self.assertIn(self.kb_global.name, kb_names)
        self.assertIn(self.kb_other_owner.name, kb_names)

    # --- KnowledgeBaseViewSet: perform_create Tests ---
    def test_create_kb_sets_owner_to_request_user(self):
        self.client.force_authenticate(user=self.owner_user)
        data = {
            "name": "New KB by Owner",
            "model_provider": self.model_provider.pk,
            # No owner, team, is_global specified - owner should be auto-set
        }
        response = self.client.post(self.kb_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_kb = KnowledgeBase.objects.get(pk=response.data['id'])
        self.assertEqual(created_kb.owner, self.owner_user)

    # --- AgentBuilder KB Access Control Tests ---
    def test_agent_builder_authorized_kb_succeeds(self):
        try:
            builder = AgentBuilder(
                agent_id=self.agent_with_kb_owned.agent_id,
                user=self.owner_user, # owner_user owns agent_with_kb_owned and kb_owned
                session_id='test_session_auth_kb'
            )
            agent_instance = builder.build() # Should not raise PermissionDenied for KB
            self.assertIsNotNone(agent_instance)
        except PermissionDenied as e:
            self.fail(f"AgentBuilder raised PermissionDenied unexpectedly: {e}")
        except Exception as e:
            self.fail(f"AgentBuilder raised an unexpected exception: {e}")


    def test_agent_builder_unauthorized_kb_fails(self):
        # self.agent_with_kb_other is owned by self.owner_user
        # but its self.kb_other_owner is owned by self.another_owner
        with self.assertRaises(PermissionDenied) as context:
            builder = AgentBuilder(
                agent_id=self.agent_with_kb_other.agent_id,
                user=self.owner_user, # owner_user tries to use agent linked to unauthorized KB
                session_id='test_session_unauth_kb'
            )
            # The KB access check is in build(), called after successful agent authorization.
            # Agent auth itself should pass here.
            builder.build()

        self.assertIn(f"User {self.owner_user.username} does not have access to KnowledgeBase '{self.kb_other_owner.name}'", str(context.exception))

    def test_agent_builder_global_kb_succeeds_for_other_user(self):
        # self.agent_with_global_kb is owned by self.other_user and uses kb_global
        try:
            builder = AgentBuilder(
                agent_id=self.agent_with_global_kb.agent_id,
                user=self.other_user, # User is other_user, who doesn't own kb_global but it's global
                session_id='test_session_global_kb'
            )
            agent_instance = builder.build()
            self.assertIsNotNone(agent_instance)
        except PermissionDenied as e:
            self.fail(f"AgentBuilder raised PermissionDenied unexpectedly for global KB: {e}")

    def test_agent_builder_team_kb_succeeds_for_team_member(self):
        # self.agent_with_team_kb is owned by self.team_member_user and uses kb_team (team_a)
        # self.team_member_user is in team_a
        try:
            builder = AgentBuilder(
                agent_id=self.agent_with_team_kb.agent_id,
                user=self.team_member_user,
                session_id='test_session_team_kb_member'
            )
            agent_instance = builder.build()
            self.assertIsNotNone(agent_instance)
        except PermissionDenied as e:
            self.fail(f"AgentBuilder raised PermissionDenied unexpectedly for team KB by team member: {e}")

    def test_agent_builder_team_kb_fails_for_non_team_member(self):
        # self.agent_with_team_kb uses kb_team (team_a)
        # self.owner_user is NOT in team_a for this test setup.
        # However, self.owner_user owns self.agent_with_team_kb for this specific test case
        # to isolate the KB check.

        agent_using_team_kb_but_owned_by_owner = DjangoAgent.objects.create(
            name="Agent For Team KB Test (Owner)",
            user=self.owner_user, # owner_user owns this agent
            knowledge_base=self.kb_team, # agent uses kb_team (Team A)
            agent_id="agent_teamkb_owner_test",
            model=self.model_provider
        )
        # Ensure owner_user is not part of team_a for this test to be valid
        self.team_a.members.remove(self.owner_user)

        with self.assertRaises(PermissionDenied) as context:
            builder = AgentBuilder(
                agent_id=agent_using_team_kb_but_owned_by_owner.agent_id,
                user=self.owner_user, # owner_user is not in team_a
                session_id='test_session_team_kb_non_member'
            )
            builder.build()
        self.assertIn(f"User {self.owner_user.username} does not have access to KnowledgeBase '{self.kb_team.name}'", str(context.exception))


    # --- AgentBuilder LlamaIndex Metadata Filtering Tests ---
    @patch('apps.reggie.agents.helpers.agent_helpers.PGVectorStore') # Mock the DB connection part
    @patch('apps.reggie.agents.helpers.agent_helpers.VectorStoreIndex.from_vector_store') # Mock the index creation
    @patch('apps.reggie.agents.helpers.agent_helpers.VectorIndexRetriever') # Target the constructor of the retriever
    def test_agent_builder_applies_project_id_filter_to_llamaindex(
            self, mock_vector_index_retriever_cls,
            mock_from_vector_store, mock_pg_vector_store_cls):

        # Setup mock instances and return values
        mock_pg_vector_store_instance = MagicMock()
        mock_pg_vector_store_cls.return_value = mock_pg_vector_store_instance

        mock_index_instance = MagicMock(spec=VectorStoreIndex)
        mock_from_vector_store.return_value = mock_index_instance

        mock_retriever_instance = MagicMock(spec=VectorIndexRetriever)
        mock_vector_index_retriever_cls.return_value = mock_retriever_instance

        test_project_id = "project_123_uuid_for_filter"

        builder = AgentBuilder(
            agent_id=self.agent_for_filtering.agent_id,
            user=self.owner_user,
            session_id='test_filter_session',
            project_id=test_project_id
        )
        try:
            agent_built = builder.build()
        except Exception as e:
            # This might happen if other parts of Agent or AgentKnowledge are not fully mocked
            # or if there's an issue in the build process not related to mocking.
            self.fail(f"AgentBuilder.build() raised an unexpected exception: {e}")

        # Assert that VectorIndexRetriever was instantiated (called)
        mock_vector_index_retriever_cls.assert_called_once()

        # Get the keyword arguments passed to the VectorIndexRetriever constructor
        _, called_kwargs = mock_vector_index_retriever_cls.call_args

        self.assertIn('filters', called_kwargs)
        filters_arg = called_kwargs['filters']
        self.assertIsInstance(filters_arg, MetadataFilters)
        self.assertEqual(len(filters_arg.filters), 1)
        filter_condition = filters_arg.filters[0]
        self.assertIsInstance(filter_condition, ExactMatchFilter)
        self.assertEqual(filter_condition.key, "project_id")
        self.assertEqual(filter_condition.value, test_project_id)

    @patch('apps.reggie.agents.helpers.agent_helpers.PGVectorStore')
    @patch('apps.reggie.agents.helpers.agent_helpers.VectorStoreIndex.from_vector_store')
    @patch('apps.reggie.agents.helpers.agent_helpers.VectorIndexRetriever')
    def test_agent_builder_no_project_id_no_filter_for_llamaindex(
            self, mock_vector_index_retriever_cls,
            mock_from_vector_store, mock_pg_vector_store_cls):

        mock_pg_vector_store_instance = MagicMock()
        mock_pg_vector_store_cls.return_value = mock_pg_vector_store_instance

        mock_index_instance = MagicMock(spec=VectorStoreIndex)
        mock_from_vector_store.return_value = mock_index_instance

        mock_retriever_instance = MagicMock(spec=VectorIndexRetriever)
        mock_vector_index_retriever_cls.return_value = mock_retriever_instance

        builder = AgentBuilder(
            agent_id=self.agent_for_filtering.agent_id,
            user=self.owner_user,
            session_id='test_no_filter_session',
            project_id=None # Explicitly None
        )
        try:
            agent_built = builder.build()
        except Exception as e:
            self.fail(f"AgentBuilder.build() raised an unexpected exception (no filter test): {e}")

        mock_vector_index_retriever_cls.assert_called_once()
        _, called_kwargs = mock_vector_index_retriever_cls.call_args

        # When project_id is None, 'filters' should not be in retriever_kwargs for VectorIndexRetriever
        # as per the logic in build_knowledge_base helper.
        self.assertNotIn('filters', called_kwargs, "Filters should not be applied when project_id is None.")

```
