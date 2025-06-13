from django.urls import reverse
from django.conf import settings as django_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from unittest.mock import patch, MagicMock

from apps.users.models import CustomUser
from apps.reggie.models import Agent as DjangoAgent, ModelProvider, KnowledgeBase

class StreamAgentResponseAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username='api_test_user', email='api_user@test.com', password='password123')

        # AgentBuilder requires a ModelProvider for the agent
        cls.model_provider = ModelProvider.objects.create(
            provider="test_api_provider",
            model_name="test_api_model",
            embedder_id="test_api_embedder"
        )

        # AgentBuilder also requires the agent to have a knowledge_base for some internal logging, even if we mock the build.
        # Creating a minimal KB.
        cls.kb = KnowledgeBase.objects.create(
            name="API Test KB",
            owner=cls.user,
            model_provider=cls.model_provider,
            knowledge_type="llamaindex" # or any valid type
        )

        cls.agent = DjangoAgent.objects.create(
            name="API Test Agent",
            user=cls.user,
            agent_id="api_test_agent_001", # Ensure this is unique or handle appropriately
            model=cls.model_provider,
            knowledge_base=cls.kb
        )

        # Attempt to determine the URL name. If 'stream-agent-response' is not registered,
        # this will fail. This is a common source of errors in tests if names don't match.
        try:
            cls.stream_url = reverse('stream-agent-response')
        except Exception as e:
            # Fallback or print a warning if the URL name is guessed.
            # For this exercise, we'll assume 'stream-agent-response' is correct or defined elsewhere.
            print(f"Warning: Could not reverse 'stream-agent-response'. Using hardcoded path. Error: {e}")
            cls.stream_url = '/api/reggie/stream-agent-response/' # Adjust if your URL is different

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('apps.reggie.views.AgentBuilder') # Target AgentBuilder where it's used (in views.py)
    def test_stream_agent_api_with_project_id(self, mock_agent_builder_cls):
        # Configure the mock AgentBuilder instance and its build().run() methods
        mock_builder_instance = MagicMock()
        mock_agent_instance = MagicMock()

        def mock_stream_generator(*args, **kwargs):
            yield MagicMock(content="dummy chunk", citations=None, tools=None)
            # yield from () # Alternative for empty generator

        mock_agent_instance.run.return_value = mock_stream_generator()
        mock_builder_instance.build.return_value = mock_agent_instance
        mock_agent_builder_cls.return_value = mock_builder_instance

        test_project_id = "project_uuid_for_api_test"
        payload = {
            "agent_id": self.agent.agent_id,
            "message": "Hello Agent",
            "session_id": "apisession_with_project",
            "project_id": test_project_id
        }

        response = self.client.post(self.stream_url, payload, format='json')

        # Check if the view processed the request successfully before checking mock calls
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=f"API call failed: {response.content}")

        mock_agent_builder_cls.assert_called_once()
        args, kwargs = mock_agent_builder_cls.call_args

        self.assertEqual(kwargs.get('agent_id'), self.agent.agent_id)
        self.assertEqual(kwargs.get('user'), self.user)
        self.assertEqual(kwargs.get('session_id'), "apisession_with_project")
        self.assertEqual(kwargs.get('project_id'), test_project_id)

    @patch('apps.reggie.views.AgentBuilder')
    def test_stream_agent_api_without_project_id(self, mock_agent_builder_cls):
        mock_builder_instance = MagicMock()
        mock_agent_instance = MagicMock()

        def mock_stream_generator(*args, **kwargs):
            yield MagicMock(content="dummy chunk", citations=None, tools=None)
            # yield from ()

        mock_agent_instance.run.return_value = mock_stream_generator()
        mock_builder_instance.build.return_value = mock_agent_instance
        mock_agent_builder_cls.return_value = mock_builder_instance

        payload = {
            "agent_id": self.agent.agent_id,
            "message": "Hello Agent Again",
            "session_id": "apisession_no_project"
            # project_id is omitted
        }

        response = self.client.post(self.stream_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=f"API call failed: {response.content}")

        mock_agent_builder_cls.assert_called_once()
        args, kwargs = mock_agent_builder_cls.call_args

        self.assertEqual(kwargs.get('agent_id'), self.agent.agent_id)
        self.assertEqual(kwargs.get('user'), self.user)
        self.assertEqual(kwargs.get('session_id'), "apisession_no_project")
        # project_id should be None or not present if the default in AgentBuilder.__init__ is None
        self.assertIsNone(kwargs.get('project_id'), "project_id should be None when not provided in payload")
```
