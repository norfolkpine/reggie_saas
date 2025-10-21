"""
AgentOS Metrics Views

Django views for displaying and managing AgentOS metrics,
including dashboards, API endpoints, and reports.
"""

import json
import logging
from datetime import date, timedelta
from typing import Dict, Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView, ListView
from django.views.decorators.csrf import csrf_exempt

from ..models import (
    AgentOSSession,
    AgentOSMessage,
    AgentOSUsage,
    AgentOSPerformance,
    AgentOSError
)
from .metrics_service import get_metrics_service

logger = logging.getLogger(__name__)


class AgentOSMetricsDashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard for AgentOS metrics.
    """
    template_name = 'agentos/metrics_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get metrics for the last 30 days
        metrics_service = get_metrics_service(user)
        user_metrics = metrics_service.get_user_metrics(days=30)
        
        context.update({
            'user_metrics': user_metrics,
            'page_title': 'AgentOS Metrics Dashboard',
            'current_user': user,
        })
        return context


class AgentOSMetricsListView(LoginRequiredMixin, ListView):
    """
    List view for AgentOS sessions and metrics.
    """
    model = AgentOSSession
    template_name = 'opie/agentos_metrics_list.html'
    context_object_name = 'sessions'
    paginate_by = 20
    
    def get_queryset(self):
        return AgentOSSession.objects.filter(
            user=self.request.user
        ).order_by('-last_activity')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get summary metrics
        metrics_service = get_metrics_service(user)
        user_metrics = metrics_service.get_user_metrics(days=7)
        
        context.update({
            'user_metrics': user_metrics,
            'page_title': 'AgentOS Sessions',
        })
        return context


class AgentOSMetricsDetailView(LoginRequiredMixin, TemplateView):
    """
    Detail view for a specific AgentOS session.
    """
    template_name = 'opie/agentos_metrics_detail.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session_id = kwargs.get('session_id')
        user = self.request.user
        
        session = get_object_or_404(
            AgentOSSession,
            session_id=session_id,
            user=user
        )
        
        # Get messages for this session
        messages = AgentOSMessage.objects.filter(
            session=session
        ).order_by('created_at')
        
        # Get errors for this session
        errors = AgentOSError.objects.filter(
            session=session
        ).order_by('-created_at')
        
        context.update({
            'session': session,
            'messages': messages,
            'errors': errors,
            'page_title': f'Session: {session.title}',
        })
        return context


# API Views for Metrics

@login_required
@require_http_methods(["GET"])
def agentos_metrics_api(request):
    """
    API endpoint for getting user metrics.
    """
    try:
        days = int(request.GET.get('days', 30))
        user = request.user
        
        metrics_service = get_metrics_service(user)
        user_metrics = metrics_service.get_user_metrics(days=days)
        
        return JsonResponse({
            'success': True,
            'data': user_metrics
        })
    except Exception as e:
        logger.error(f"Failed to get user metrics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_agent_metrics_api(request, agent_id):
    """
    API endpoint for getting agent-specific metrics.
    """
    try:
        days = int(request.GET.get('days', 30))
        user = request.user
        
        metrics_service = get_metrics_service(user)
        agent_metrics = metrics_service.get_agent_metrics(agent_id=agent_id, days=days)
        
        return JsonResponse({
            'success': True,
            'data': agent_metrics
        })
    except Exception as e:
        logger.error(f"Failed to get agent metrics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_system_metrics_api(request):
    """
    API endpoint for getting system-wide metrics (admin only).
    """
    if not request.user.is_staff:
        return JsonResponse({
            'success': False,
            'error': 'Permission denied'
        }, status=403)
    
    try:
        days = int(request.GET.get('days', 30))
        
        metrics_service = get_metrics_service()
        system_metrics = metrics_service.get_system_metrics(days=days)
        
        return JsonResponse({
            'success': True,
            'data': system_metrics
        })
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_sessions_api(request):
    """
    API endpoint for getting user sessions.
    """
    try:
        user = request.user
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        agent_id = request.GET.get('agent_id')
        
        queryset = AgentOSSession.objects.filter(user=user)
        
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        
        queryset = queryset.order_by('-last_activity')
        
        paginator = Paginator(queryset, per_page)
        sessions_page = paginator.get_page(page)
        
        sessions_data = []
        for session in sessions_page:
            sessions_data.append({
                'id': session.id,
                'session_id': session.session_id,
                'agent_id': session.agent_id,
                'agent_name': session.agent_name,
                'title': session.title,
                'is_active': session.is_active,
                'message_count': session.message_count,
                'total_tokens': session.total_tokens,
                'total_cost': float(session.total_cost),
                'created_at': session.created_at.isoformat(),
                'last_activity': session.last_activity.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'sessions': sessions_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total_pages': paginator.num_pages,
                    'total_count': paginator.count,
                    'has_next': sessions_page.has_next(),
                    'has_previous': sessions_page.has_previous(),
                }
            }
        })
    except Exception as e:
        logger.error(f"Failed to get sessions: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_session_messages_api(request, session_id):
    """
    API endpoint for getting messages for a specific session.
    """
    try:
        user = request.user
        session = get_object_or_404(
            AgentOSSession,
            session_id=session_id,
            user=user
        )
        
        messages = AgentOSMessage.objects.filter(
            session=session
        ).order_by('created_at')
        
        messages_data = []
        for message in messages:
            messages_data.append({
                'id': message.id,
                'message_id': message.message_id,
                'role': message.role,
                'content': message.content,
                'tokens_used': message.tokens_used,
                'cost': float(message.cost),
                'response_time_ms': message.response_time_ms,
                'model_used': message.model_used,
                'tools_used': message.tools_used,
                'metadata': message.metadata,
                'created_at': message.created_at.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'session': {
                    'id': session.id,
                    'session_id': session.session_id,
                    'agent_id': session.agent_id,
                    'agent_name': session.agent_name,
                    'title': session.title,
                },
                'messages': messages_data
            }
        })
    except Exception as e:
        logger.error(f"Failed to get session messages: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_errors_api(request):
    """
    API endpoint for getting user errors.
    """
    try:
        user = request.user
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        agent_id = request.GET.get('agent_id')
        is_resolved = request.GET.get('is_resolved')
        
        queryset = AgentOSError.objects.filter(user=user)
        
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        
        if is_resolved is not None:
            queryset = queryset.filter(is_resolved=is_resolved.lower() == 'true')
        
        queryset = queryset.order_by('-created_at')
        
        paginator = Paginator(queryset, per_page)
        errors_page = paginator.get_page(page)
        
        errors_data = []
        for error in errors_page:
            errors_data.append({
                'id': error.id,
                'agent_id': error.agent_id,
                'error_type': error.error_type,
                'error_message': error.error_message,
                'error_code': error.error_code,
                'is_resolved': error.is_resolved,
                'context': error.context,
                'created_at': error.created_at.isoformat(),
                'resolved_at': error.resolved_at.isoformat() if error.resolved_at else None,
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'errors': errors_data,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total_pages': paginator.num_pages,
                    'total_count': paginator.count,
                    'has_next': errors_page.has_next(),
                    'has_previous': errors_page.has_previous(),
                }
            }
        })
    except Exception as e:
        logger.error(f"Failed to get errors: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def agentos_resolve_error_api(request, error_id):
    """
    API endpoint for resolving an error.
    """
    try:
        user = request.user
        error = get_object_or_404(
            AgentOSError,
            id=error_id,
            user=user
        )
        
        error.is_resolved = True
        error.resolved_at = timezone.now()
        error.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Error resolved successfully'
        })
    except Exception as e:
        logger.error(f"Failed to resolve error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_export_metrics_api(request):
    """
    API endpoint for exporting metrics data.
    """
    try:
        user = request.user
        days = int(request.GET.get('days', 30))
        format_type = request.GET.get('format', 'json')
        
        metrics_service = get_metrics_service(user)
        user_metrics = metrics_service.get_user_metrics(days=days)
        
        if format_type == 'csv':
            # Generate CSV export
            import csv
            from django.http import HttpResponse
            
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="agentos_metrics_{user.id}_{date.today()}.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Total Sessions', user_metrics.get('total_sessions', 0)])
            writer.writerow(['Total Messages', user_metrics.get('total_messages', 0)])
            writer.writerow(['Total Tokens', user_metrics.get('total_tokens', 0)])
            writer.writerow(['Total Cost', user_metrics.get('total_cost', 0)])
            writer.writerow(['Total Errors', user_metrics.get('total_errors', 0)])
            
            return response
        else:
            # Return JSON
            return JsonResponse({
                'success': True,
                'data': user_metrics
            })
    except Exception as e:
        logger.error(f"Failed to export metrics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
