"""
Django management command for AgentOS metrics operations.
"""

import logging
from datetime import date, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.opie.agentos.metrics_service import get_metrics_service
from apps.opie.models import AgentOSSession, AgentOSUsage, AgentOSPerformance

User = get_user_model()
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Manage AgentOS metrics and statistics'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            choices=['update', 'cleanup', 'export', 'stats'],
            help='Action to perform'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to process (default: 30)'
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Specific user ID to process'
        )
        parser.add_argument(
            '--agent-id',
            type=str,
            help='Specific agent ID to process'
        )
        parser.add_argument(
            '--format',
            choices=['json', 'csv'],
            default='json',
            help='Export format (default: json)'
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path for export'
        )
        parser.add_argument(
            '--cleanup-days',
            type=int,
            default=90,
            help='Days of old data to clean up (default: 90)'
        )
    
    def handle(self, *args, **options):
        action = options['action']
        days = options['days']
        user_id = options.get('user_id')
        agent_id = options.get('agent_id')
        
        try:
            if action == 'update':
                self.update_metrics(days, user_id, agent_id)
            elif action == 'cleanup':
                self.cleanup_metrics(options['cleanup_days'])
            elif action == 'export':
                self.export_metrics(days, user_id, agent_id, options['format'], options.get('output'))
            elif action == 'stats':
                self.show_stats(days, user_id, agent_id)
        except Exception as e:
            raise CommandError(f'Failed to execute {action}: {e}')
    
    def update_metrics(self, days, user_id=None, agent_id=None):
        """Update metrics for specified period."""
        self.stdout.write('Updating AgentOS metrics...')
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Get users to process
        if user_id:
            users = User.objects.filter(id=user_id)
        else:
            users = User.objects.filter(
                agentos_sessions__created_at__date__range=[start_date, end_date]
            ).distinct()
        
        if not users.exists():
            self.stdout.write(self.style.WARNING('No users found with AgentOS activity'))
            return
        
        metrics_service = get_metrics_service()
        updated_count = 0
        
        for user in users:
            try:
                user_service = get_metrics_service(user)
                
                # Get user's agents
                user_agents = AgentOSSession.objects.filter(
                    user=user,
                    created_at__date__range=[start_date, end_date]
                ).values_list('agent_id', flat=True).distinct()
                
                if agent_id and agent_id not in user_agents:
                    continue
                
                agents_to_process = [agent_id] if agent_id else user_agents
                
                for agent in agents_to_process:
                    # Update daily usage
                    for i in range(days):
                        current_date = end_date - timedelta(days=i)
                        user_service.update_daily_usage(agent, current_date)
                    
                    # Update daily performance
                    for i in range(days):
                        current_date = end_date - timedelta(days=i)
                        user_service.update_daily_performance(agent, current_date)
                    
                    updated_count += 1
                
                self.stdout.write(f'Updated metrics for user {user.id} ({user.email})')
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Failed to update metrics for user {user.id}: {e}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated metrics for {updated_count} agent-user combinations')
        )
    
    def cleanup_metrics(self, cleanup_days):
        """Clean up old metrics data."""
        self.stdout.write(f'Cleaning up metrics older than {cleanup_days} days...')
        
        metrics_service = get_metrics_service()
        result = metrics_service.cleanup_old_metrics(cleanup_days)
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Cleaned up {result["sessions_deleted"]} old sessions and '
                f'{result["errors_deleted"]} old errors'
            )
        )
    
    def export_metrics(self, days, user_id, agent_id, format_type, output_file):
        """Export metrics data."""
        self.stdout.write('Exporting AgentOS metrics...')
        
        if user_id:
            user = User.objects.get(id=user_id)
            metrics_service = get_metrics_service(user)
            data = metrics_service.get_user_metrics(days=days)
        else:
            metrics_service = get_metrics_service()
            data = metrics_service.get_system_metrics(days=days)
        
        if format_type == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write headers
            if user_id:
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Total Sessions', data.get('total_sessions', 0)])
                writer.writerow(['Total Messages', data.get('total_messages', 0)])
                writer.writerow(['Total Tokens', data.get('total_tokens', 0)])
                writer.writerow(['Total Cost', data.get('total_cost', 0)])
                writer.writerow(['Total Errors', data.get('total_errors', 0)])
            else:
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Total Users', data.get('total_users', 0)])
                writer.writerow(['Total Sessions', data.get('total_sessions', 0)])
                writer.writerow(['Total Messages', data.get('total_messages', 0)])
                writer.writerow(['Total Tokens', data.get('total_tokens', 0)])
                writer.writerow(['Total Cost', data.get('total_cost', 0)])
                writer.writerow(['Total Errors', data.get('total_errors', 0)])
                writer.writerow(['Error Rate', f"{data.get('error_rate', 0):.2f}%"])
            
            csv_content = output.getvalue()
            output.close()
            
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(csv_content)
                self.stdout.write(f'Exported to {output_file}')
            else:
                self.stdout.write(csv_content)
        else:
            import json
            json_content = json.dumps(data, indent=2, default=str)
            
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(json_content)
                self.stdout.write(f'Exported to {output_file}')
            else:
                self.stdout.write(json_content)
    
    def show_stats(self, days, user_id, agent_id):
        """Show statistics summary."""
        self.stdout.write('AgentOS Metrics Statistics')
        self.stdout.write('=' * 50)
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Overall stats
        total_sessions = AgentOSSession.objects.filter(
            created_at__date__range=[start_date, end_date]
        ).count()
        
        total_messages = sum(
            session.message_count for session in AgentOSSession.objects.filter(
                created_at__date__range=[start_date, end_date]
            )
        )
        
        total_tokens = sum(
            session.total_tokens for session in AgentOSSession.objects.filter(
                created_at__date__range=[start_date, end_date]
            )
        )
        
        total_cost = sum(
            float(session.total_cost) for session in AgentOSSession.objects.filter(
                created_at__date__range=[start_date, end_date]
            )
        )
        
        self.stdout.write(f'Period: {start_date} to {end_date} ({days} days)')
        self.stdout.write(f'Total Sessions: {total_sessions}')
        self.stdout.write(f'Total Messages: {total_messages}')
        self.stdout.write(f'Total Tokens: {total_tokens:,}')
        self.stdout.write(f'Total Cost: ${total_cost:.2f}')
        
        # User stats
        if user_id:
            user = User.objects.get(id=user_id)
            user_sessions = AgentOSSession.objects.filter(
                user=user,
                created_at__date__range=[start_date, end_date]
            )
            
            self.stdout.write(f'\nUser: {user.email} (ID: {user.id})')
            self.stdout.write(f'User Sessions: {user_sessions.count()}')
            self.stdout.write(f'User Messages: {sum(s.message_count for s in user_sessions)}')
            self.stdout.write(f'User Tokens: {sum(s.total_tokens for s in user_sessions):,}')
            self.stdout.write(f'User Cost: ${sum(float(s.total_cost) for s in user_sessions):.2f}')
        
        # Agent stats
        if agent_id:
            agent_sessions = AgentOSSession.objects.filter(
                agent_id=agent_id,
                created_at__date__range=[start_date, end_date]
            )
            
            self.stdout.write(f'\nAgent: {agent_id}')
            self.stdout.write(f'Agent Sessions: {agent_sessions.count()}')
            self.stdout.write(f'Agent Messages: {sum(s.message_count for s in agent_sessions)}')
            self.stdout.write(f'Agent Tokens: {sum(s.total_tokens for s in agent_sessions):,}')
            self.stdout.write(f'Agent Cost: ${sum(float(s.total_cost) for s in agent_sessions):.2f}')
        
        # Top agents
        from django.db.models import Count, Sum
        top_agents = AgentOSSession.objects.filter(
            created_at__date__range=[start_date, end_date]
        ).values('agent_id', 'agent_name').annotate(
            session_count=Count('id'),
            total_messages=Sum('message_count'),
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('total_cost')
        ).order_by('-session_count')[:5]
        
        if top_agents:
            self.stdout.write('\nTop 5 Agents by Sessions:')
            for agent in top_agents:
                self.stdout.write(
                    f"  {agent['agent_name']} ({agent['agent_id']}): "
                    f"{agent['session_count']} sessions, "
                    f"{agent['total_messages']} messages, "
                    f"{agent['total_tokens']:,} tokens, "
                    f"${float(agent['total_cost']):.2f}"
                )
        
        self.stdout.write('\nStatistics completed successfully!')
