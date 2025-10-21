"""
Management command to start AgentOS server.
"""

import logging
import uvicorn
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.opie.agentos.config import get_agent_os_app_for_user

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Start AgentOS server'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host',
            type=str,
            default='127.0.0.1',
            help='Host to bind to (default: 127.0.0.1)'
        )
        parser.add_argument(
            '--port',
            type=int,
            default=7777,
            help='Port to bind to (default: 7777)'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to run AgentOS for (if not provided, uses first superuser)'
        )
        parser.add_argument(
            '--reload',
            action='store_true',
            help='Enable auto-reload for development'
        )

    def handle(self, *args, **options):
        host = options['host']
        port = options['port']
        user_id = options['user_id']
        reload = options['reload']

        try:
            # Get user
            if user_id:
                user = User.objects.get(id=user_id)
            else:
                user = User.objects.filter(is_superuser=True).first()
                if not user:
                    raise CommandError('No superuser found. Please provide --user-id or create a superuser.')

            self.stdout.write(f'Starting AgentOS for user: {user.email}')

            # Get AgentOS app
            app = get_agent_os_app_for_user(user)

            # Start server
            uvicorn.run(
                app,
                host=host,
                port=port,
                reload=reload,
                log_level='info'
            )

        except User.DoesNotExist:
            raise CommandError(f'User with ID {user_id} not found')
        except Exception as e:
            raise CommandError(f'Failed to start AgentOS: {e}')

