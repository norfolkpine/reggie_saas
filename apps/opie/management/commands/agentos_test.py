"""
Management command to test AgentOS functionality.
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.opie.agentos.service import AgentOSService
from apps.opie.models import Agent as DjangoAgent

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test AgentOS functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to test with (if not provided, uses first superuser)'
        )
        parser.add_argument(
            '--agent-id',
            type=str,
            help='Specific agent ID to test (if not provided, tests all available agents)'
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        agent_id = options['agent_id']

        try:
            # Get user
            if user_id:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.filter(is_superuser=True).first()
                if not user:
                    raise CommandError('No superuser found. Please provide --user-id or create a superuser.')

            self.stdout.write(f'Testing AgentOS for user: {user.email}')

            # Create service
            service = AgentOSService(user)

            # Test AgentOS info
            self.stdout.write('Testing AgentOS info...')
            info = service.get_agent_os_info()
            self.stdout.write(f'AgentOS Info: {info}')

            # Test available agents
            self.stdout.write('Testing available agents...')
            agents = service.get_available_agents()
            self.stdout.write(f'Found {len(agents)} agents:')
            for agent in agents:
                self.stdout.write(f'  - {agent["name"]} (ID: {agent["id"]})')

            # Test specific agent if provided
            if agent_id:
                self.stdout.write(f'Testing specific agent: {agent_id}')
                agent = service.get_agent_by_id(agent_id)
                if agent:
                    self.stdout.write(f'Agent found: {agent.name}')
                else:
                    self.stdout.write(f'Agent {agent_id} not found')

            # Test session creation
            if agents:
                test_agent_id = agents[0]['id']
                self.stdout.write(f'Testing session creation with agent: {test_agent_id}')
                session_id = service.create_session(test_agent_id, 'Test Session')
                if session_id:
                    self.stdout.write(f'Session created: {session_id}')
                else:
                    self.stdout.write('Failed to create session')

            self.stdout.write(self.style.SUCCESS('AgentOS test completed successfully!'))

        except User.DoesNotExist:
            raise CommandError(f'User with ID {user_id} not found')
        except Exception as e:
            raise CommandError(f'AgentOS test failed: {e}')

