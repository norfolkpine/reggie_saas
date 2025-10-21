"""
Management command to sync Django agents with AgentOS.
"""

import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.opie.models import Agent as DjangoAgent
from apps.opie.agentos.config import agent_os_config

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync Django agents with AgentOS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to sync agents for (if not provided, syncs for all users)'
        )
        parser.add_argument(
            '--agent-id',
            type=str,
            help='Specific agent ID to sync (if not provided, syncs all agents)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually doing it'
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        agent_id = options['agent_id']
        dry_run = options['dry_run']

        try:
            if user_id:
                users = [User.objects.get(id=user_id)]
            else:
                users = User.objects.filter(is_active=True)

            if agent_id:
                agents = [DjangoAgent.objects.get(agent_id=agent_id)]
            else:
                agents = DjangoAgent.objects.filter(is_enabled=True)

            self.stdout.write(f'Found {len(users)} users and {len(agents)} agents to sync')

            for user in users:
                self.stdout.write(f'Processing user: {user.email}')
                
                if dry_run:
                    self.stdout.write(f'  Would sync {len(agents)} agents for {user.email}')
                    continue

                try:
                    # Initialize AgentOS for user
                    agent_os = agent_os_config.initialize_agent_os(user, include_vault_agents=True)
                    self.stdout.write(f'  AgentOS initialized for {user.email}')
                    
                    # Get available agents
                    available_agents = agent_os_config.get_available_agents(user)
                    self.stdout.write(f'  {len(available_agents)} agents available for {user.email}')
                    
                except Exception as e:
                    self.stdout.write(f'  Error processing user {user.email}: {e}')
                    continue

            if dry_run:
                self.stdout.write(self.style.WARNING('Dry run completed - no changes made'))
            else:
                self.stdout.write(self.style.SUCCESS('AgentOS sync completed successfully!'))

        except User.DoesNotExist:
            raise CommandError(f'User with ID {user_id} not found')
        except DjangoAgent.DoesNotExist:
            raise CommandError(f'Agent with ID {agent_id} not found')
        except Exception as e:
            raise CommandError(f'AgentOS sync failed: {e}')

