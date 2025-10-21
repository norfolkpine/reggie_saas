"""
AgentOS Metrics Service

This service handles tracking and management of AgentOS metrics,
including usage statistics, performance monitoring, and error tracking.
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache

from ..models import (
    AgentOSSession,
    AgentOSMessage,
    AgentOSUsage,
    AgentOSPerformance,
    AgentOSError,
    TokenUsage
)

User = get_user_model()
logger = logging.getLogger(__name__)


class AgentOSMetricsService:
    """
    Service for tracking and managing AgentOS metrics.
    Provides methods for recording usage, performance, and errors.
    """
    
    def __init__(self, user=None):
        self.user = user
        self.cache_ttl = 300  # 5 minutes
    
    def create_session(self, agent_id: str, agent_name: str, session_id: str, 
                      title: str = "AgentOS Chat") -> AgentOSSession:
        """
        Create a new AgentOS session and track it.
        """
        try:
            session = AgentOSSession.objects.create(
                user=self.user,
                agent_id=agent_id,
                agent_name=agent_name,
                session_id=session_id,
                title=title
            )
            logger.info(f"Created AgentOS session {session_id} for user {self.user.id}")
            return session
        except Exception as e:
            logger.error(f"Failed to create AgentOS session: {e}")
            raise
    
    def record_message(self, session: AgentOSSession, message_id: str, role: str,
                      content: str, tokens_used: int = 0, cost: float = 0.0,
                      response_time_ms: int = 0, model_used: str = "",
                      tools_used: List[str] = None, metadata: Dict = None) -> AgentOSMessage:
        """
        Record a message in an AgentOS session.
        """
        try:
            message = AgentOSMessage.objects.create(
                session=session,
                message_id=message_id,
                role=role,
                content=content,
                tokens_used=tokens_used,
                cost=cost,
                response_time_ms=response_time_ms,
                model_used=model_used,
                tools_used=tools_used or [],
                metadata=metadata or {}
            )
            
            # Update session statistics
            session.message_count += 1
            session.total_tokens += tokens_used
            session.total_cost += cost
            session.save(update_fields=['message_count', 'total_tokens', 'total_cost', 'last_activity'])
            
            logger.debug(f"Recorded message {message_id} for session {session.session_id}")
            return message
        except Exception as e:
            logger.error(f"Failed to record message: {e}")
            raise
    
    def record_error(self, agent_id: str, error_type: str, error_message: str,
                    error_code: str = "", stack_trace: str = "", context: Dict = None,
                    session: AgentOSSession = None) -> AgentOSError:
        """
        Record an error that occurred in AgentOS.
        """
        try:
            error = AgentOSError.objects.create(
                user=self.user,
                session=session,
                agent_id=agent_id,
                error_type=error_type,
                error_message=error_message,
                error_code=error_code,
                stack_trace=stack_trace,
                context=context or {}
            )
            logger.warning(f"Recorded AgentOS error: {error_type} - {error_message}")
            return error
        except Exception as e:
            logger.error(f"Failed to record error: {e}")
            raise
    
    def update_daily_usage(self, agent_id: str, date_obj: date = None) -> AgentOSUsage:
        """
        Update daily usage statistics for a user and agent.
        """
        if date_obj is None:
            date_obj = date.today()
        
        try:
            usage, created = AgentOSUsage.objects.get_or_create(
                user=self.user,
                agent_id=agent_id,
                date=date_obj,
                defaults={
                    'session_count': 0,
                    'message_count': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'avg_response_time_ms': 0,
                    'unique_tools_used': 0
                }
            )
            
            # Calculate updated statistics
            sessions = AgentOSSession.objects.filter(
                user=self.user,
                agent_id=agent_id,
                created_at__date=date_obj
            )
            
            messages = AgentOSMessage.objects.filter(
                session__user=self.user,
                session__agent_id=agent_id,
                created_at__date=date_obj
            )
            
            usage.session_count = sessions.count()
            usage.message_count = messages.count()
            usage.total_tokens = sum(msg.tokens_used for msg in messages)
            usage.total_cost = sum(float(msg.cost) for msg in messages)
            
            if messages.exists():
                usage.avg_response_time_ms = sum(msg.response_time_ms for msg in messages) // messages.count()
                all_tools = set()
                for msg in messages:
                    all_tools.update(msg.tools_used or [])
                usage.unique_tools_used = len(all_tools)
            
            usage.save()
            return usage
        except Exception as e:
            logger.error(f"Failed to update daily usage: {e}")
            raise
    
    def update_daily_performance(self, agent_id: str, date_obj: date = None) -> AgentOSPerformance:
        """
        Update daily performance statistics for an agent.
        """
        if date_obj is None:
            date_obj = date.today()
        
        try:
            performance, created = AgentOSPerformance.objects.get_or_create(
                agent_id=agent_id,
                date=date_obj,
                defaults={
                    'total_sessions': 0,
                    'successful_sessions': 0,
                    'failed_sessions': 0,
                    'avg_response_time_ms': 0,
                    'avg_tokens_per_session': 0,
                    'avg_cost_per_session': 0.0,
                    'user_satisfaction_score': 0.0,
                    'error_rate': 0.0
                }
            )
            
            # Calculate performance metrics
            sessions = AgentOSSession.objects.filter(
                agent_id=agent_id,
                created_at__date=date_obj
            )
            
            messages = AgentOSMessage.objects.filter(
                session__agent_id=agent_id,
                created_at__date=date_obj
            )
            
            errors = AgentOSError.objects.filter(
                agent_id=agent_id,
                created_at__date=date_obj
            )
            
            performance.total_sessions = sessions.count()
            performance.successful_sessions = sessions.filter(is_active=True).count()
            performance.failed_sessions = sessions.filter(is_active=False).count()
            
            if messages.exists():
                performance.avg_response_time_ms = sum(msg.response_time_ms for msg in messages) // messages.count()
                performance.avg_tokens_per_session = sum(msg.tokens_used for msg in messages) // max(sessions.count(), 1)
                performance.avg_cost_per_session = sum(float(msg.cost) for msg in messages) / max(sessions.count(), 1)
            
            if performance.total_sessions > 0:
                performance.error_rate = (errors.count() / performance.total_sessions) * 100
            
            performance.save()
            return performance
        except Exception as e:
            logger.error(f"Failed to update daily performance: {e}")
            raise
    
    def get_user_metrics(self, user=None, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive metrics for a user.
        """
        if user is None:
            user = self.user
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        try:
            # Get usage data
            usage_data = AgentOSUsage.objects.filter(
                user=user,
                date__range=[start_date, end_date]
            ).order_by('-date')
            
            # Get session data
            sessions = AgentOSSession.objects.filter(
                user=user,
                created_at__date__range=[start_date, end_date]
            ).order_by('-last_activity')
            
            # Get error data
            errors = AgentOSError.objects.filter(
                user=user,
                created_at__date__range=[start_date, end_date]
            ).order_by('-created_at')
            
            # Calculate totals
            total_sessions = sessions.count()
            total_messages = sum(session.message_count for session in sessions)
            total_tokens = sum(usage.total_tokens for usage in usage_data)
            total_cost = sum(float(usage.total_cost) for usage in usage_data)
            total_errors = errors.count()
            
            # Get agent breakdown
            agent_breakdown = {}
            for session in sessions:
                agent_id = session.agent_id
                if agent_id not in agent_breakdown:
                    agent_breakdown[agent_id] = {
                        'name': session.agent_name,
                        'sessions': 0,
                        'messages': 0,
                        'tokens': 0,
                        'cost': 0.0
                    }
                agent_breakdown[agent_id]['sessions'] += 1
                agent_breakdown[agent_id]['messages'] += session.message_count
                agent_breakdown[agent_id]['tokens'] += session.total_tokens
                agent_breakdown[agent_id]['cost'] += float(session.total_cost)
            
            return {
                'user': user,
                'period_days': days,
                'start_date': start_date,
                'end_date': end_date,
                'total_sessions': total_sessions,
                'total_messages': total_messages,
                'total_tokens': total_tokens,
                'total_cost': total_cost,
                'total_errors': total_errors,
                'agent_breakdown': agent_breakdown,
                'usage_data': list(usage_data.values()),
                'recent_sessions': list(sessions[:10].values()),
                'recent_errors': list(errors[:10].values())
            }
        except Exception as e:
            logger.error(f"Failed to get user metrics: {e}")
            return {}
    
    def get_agent_metrics(self, agent_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get comprehensive metrics for a specific agent.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        try:
            # Get performance data
            performance_data = AgentOSPerformance.objects.filter(
                agent_id=agent_id,
                date__range=[start_date, end_date]
            ).order_by('-date')
            
            # Get session data
            sessions = AgentOSSession.objects.filter(
                agent_id=agent_id,
                created_at__date__range=[start_date, end_date]
            ).order_by('-last_activity')
            
            # Get error data
            errors = AgentOSError.objects.filter(
                agent_id=agent_id,
                created_at__date__range=[start_date, end_date]
            ).order_by('-created_at')
            
            # Calculate totals
            total_sessions = sessions.count()
            total_messages = sum(session.message_count for session in sessions)
            total_tokens = sum(session.total_tokens for session in sessions)
            total_cost = sum(float(session.total_cost) for session in sessions)
            total_errors = errors.count()
            
            # Calculate averages
            avg_response_time = 0
            if sessions.exists():
                all_messages = AgentOSMessage.objects.filter(
                    session__agent_id=agent_id,
                    created_at__date__range=[start_date, end_date]
                )
                if all_messages.exists():
                    avg_response_time = sum(msg.response_time_ms for msg in all_messages) // all_messages.count()
            
            success_rate = 0
            if total_sessions > 0:
                successful_sessions = sessions.filter(is_active=True).count()
                success_rate = (successful_sessions / total_sessions) * 100
            
            return {
                'agent_id': agent_id,
                'period_days': days,
                'start_date': start_date,
                'end_date': end_date,
                'total_sessions': total_sessions,
                'total_messages': total_messages,
                'total_tokens': total_tokens,
                'total_cost': total_cost,
                'total_errors': total_errors,
                'avg_response_time_ms': avg_response_time,
                'success_rate': success_rate,
                'performance_data': list(performance_data.values()),
                'recent_sessions': list(sessions[:10].values()),
                'recent_errors': list(errors[:10].values())
            }
        except Exception as e:
            logger.error(f"Failed to get agent metrics: {e}")
            return {}
    
    def get_system_metrics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get system-wide metrics for all AgentOS usage.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        try:
            # Get all usage data
            usage_data = AgentOSUsage.objects.filter(
                date__range=[start_date, end_date]
            )
            
            # Get all sessions
            sessions = AgentOSSession.objects.filter(
                created_at__date__range=[start_date, end_date]
            )
            
            # Get all errors
            errors = AgentOSError.objects.filter(
                created_at__date__range=[start_date, end_date]
            )
            
            # Calculate totals
            total_users = User.objects.filter(
                agentos_sessions__created_at__date__range=[start_date, end_date]
            ).distinct().count()
            
            total_sessions = sessions.count()
            total_messages = sum(session.message_count for session in sessions)
            total_tokens = sum(session.total_tokens for session in sessions)
            total_cost = sum(float(session.total_cost) for session in sessions)
            total_errors = errors.count()
            
            # Get top agents by usage
            agent_usage = {}
            for session in sessions:
                agent_id = session.agent_id
                if agent_id not in agent_usage:
                    agent_usage[agent_id] = {
                        'name': session.agent_name,
                        'sessions': 0,
                        'messages': 0,
                        'tokens': 0,
                        'cost': 0.0
                    }
                agent_usage[agent_id]['sessions'] += 1
                agent_usage[agent_id]['messages'] += session.message_count
                agent_usage[agent_id]['tokens'] += session.total_tokens
                agent_usage[agent_id]['cost'] += float(session.total_cost)
            
            # Sort by sessions
            top_agents = sorted(agent_usage.items(), key=lambda x: x[1]['sessions'], reverse=True)[:10]
            
            return {
                'period_days': days,
                'start_date': start_date,
                'end_date': end_date,
                'total_users': total_users,
                'total_sessions': total_sessions,
                'total_messages': total_messages,
                'total_tokens': total_tokens,
                'total_cost': total_cost,
                'total_errors': total_errors,
                'top_agents': top_agents,
                'error_rate': (total_errors / max(total_sessions, 1)) * 100
            }
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {}
    
    def cleanup_old_metrics(self, days: int = 90):
        """
        Clean up old metrics data to prevent database bloat.
        """
        cutoff_date = date.today() - timedelta(days=days)
        
        try:
            # Clean up old sessions
            old_sessions = AgentOSSession.objects.filter(
                last_activity__date__lt=cutoff_date,
                is_active=False
            )
            session_count = old_sessions.count()
            old_sessions.delete()
            
            # Clean up old errors that are resolved
            old_errors = AgentOSError.objects.filter(
                created_at__date__lt=cutoff_date,
                is_resolved=True
            )
            error_count = old_errors.count()
            old_errors.delete()
            
            logger.info(f"Cleaned up {session_count} old sessions and {error_count} old errors")
            return {'sessions_deleted': session_count, 'errors_deleted': error_count}
        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")
            raise


def get_metrics_service(user=None) -> AgentOSMetricsService:
    """
    Get or create an AgentOS metrics service for a user.
    """
    return AgentOSMetricsService(user)
