"""
AgentOS Views for Django Integration

This module provides Django views for AgentOS functionality,
including API endpoints, web interfaces, and management views.
"""

import logging
import json
from typing import Dict, Any
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.core.paginator import Paginator
from django.db.models import Q

from .service import AgentOSService, AgentOSAPIView, AgentOSWebhookView
from ..models import Agent as DjangoAgent, ChatSession
from .config import get_agent_os_app_for_user

logger = logging.getLogger(__name__)


class AgentOSDashboardView(LoginRequiredMixin, TemplateView):
    """
    Main dashboard view for AgentOS functionality.
    """
    template_name = 'agentos/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            service = AgentOSService(self.request.user)
            context.update({
                'agentos_info': service.get_agent_os_info(),
                'available_agents': service.get_available_agents(),
                'user_agents': DjangoAgent.objects.filter(
                    Q(is_global=True) | 
                    Q(team__members__user=self.request.user) |
                    Q(subscriptions__customer__user=self.request.user, subscriptions__status="active")
                ).distinct()[:10]
            })
        except Exception as e:
            logger.error(f"Error loading AgentOS dashboard: {e}")
            context['error'] = str(e)
        
        return context


class AgentOSAgentListView(LoginRequiredMixin, TemplateView):
    """
    View for listing and managing agents.
    """
    template_name = 'agentos/agents.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            service = AgentOSService(self.request.user)
            context.update({
                'agents': service.get_available_agents(),
                'django_agents': DjangoAgent.objects.filter(
                    Q(is_global=True) | 
                    Q(team__members__user=self.request.user) |
                    Q(subscriptions__customer__user=self.request.user, subscriptions__status="active")
                ).distinct()
            })
        except Exception as e:
            logger.error(f"Error loading agents: {e}")
            context['error'] = str(e)
        
        return context


class AgentOSSessionView(LoginRequiredMixin, TemplateView):
    """
    View for managing chat sessions.
    """
    template_name = 'agentos/session.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            service = AgentOSService(self.request.user)
            session_id = self.kwargs.get('session_id')
            
            if session_id:
                session = service.get_session(session_id)
                if session:
                    context.update({
                        'session': session,
                        'agent': service.get_agent_by_id(session.agent.agent_id),
                        'agentos_info': service.get_agent_os_info()
                    })
                else:
                    context['error'] = 'Session not found'
            else:
                context['error'] = 'No session ID provided'
                
        except Exception as e:
            logger.error(f"Error loading session: {e}")
            context['error'] = str(e)
        
        return context


class AgentOSChatView(LoginRequiredMixin, TemplateView):
    """
    Interactive chat interface for AgentOS.
    """
    template_name = 'agentos/chat.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            service = AgentOSService(self.request.user)
            agent_id = self.kwargs.get('agent_id')
            
            if agent_id:
                agent = service.get_agent_by_id(agent_id)
                if agent:
                    context.update({
                        'agent': agent,
                        'agentos_info': service.get_agent_os_info()
                    })
                else:
                    context['error'] = 'Agent not found'
            else:
                context['error'] = 'No agent ID provided'
                
        except Exception as e:
            logger.error(f"Error loading chat: {e}")
            context['error'] = str(e)
        
        return context


@login_required
def agentos_api(request):
    """
    Main API endpoint for AgentOS functionality.
    """
    if request.method == 'GET':
        return AgentOSAPIView.as_view()(request)
    elif request.method == 'POST':
        return AgentOSAPIView.as_view()(request)
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
def agentos_webhook(request):
    """
    Webhook endpoint for external integrations.
    """
    if request.method == 'POST':
        return AgentOSWebhookView.as_view()(request)
    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)


@login_required
@require_http_methods(["GET"])
def agentos_agents_api(request):
    """
    API endpoint for getting available agents.
    """
    try:
        service = AgentOSService(request.user)
        agents = service.get_available_agents()
        return JsonResponse({'agents': agents})
    except Exception as e:
        logger.error(f"Error getting agents: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def agentos_send_message(request):
    """
    API endpoint for sending messages to agents.
    """
    try:
        data = json.loads(request.body)
        service = AgentOSService(request.user)
        
        agent_id = data.get('agent_id')
        session_id = data.get('session_id')
        message = data.get('message')
        context = data.get('context')
        
        if not all([agent_id, message]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        result = service.send_message(agent_id, session_id, message, context)
        return JsonResponse(result)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def agentos_create_session(request):
    """
    API endpoint for creating new chat sessions.
    """
    try:
        data = json.loads(request.body)
        service = AgentOSService(request.user)
        
        agent_id = data.get('agent_id')
        title = data.get('title', 'New Chat')
        
        if not agent_id:
            return JsonResponse({'error': 'Missing agent_id'}, status=400)
        
        session_id = service.create_session(agent_id, title)
        if session_id:
            return JsonResponse({'success': True, 'session_id': session_id})
        else:
            return JsonResponse({'error': 'Failed to create session'}, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_sessions_api(request):
    """
    API endpoint for getting user's chat sessions.
    """
    try:
        sessions = ChatSession.objects.filter(user=request.user).order_by('-updated_at')
        
        # Pagination
        page = request.GET.get('page', 1)
        paginator = Paginator(sessions, 20)
        sessions_page = paginator.get_page(page)
        
        sessions_data = []
        for session in sessions_page:
            sessions_data.append({
                'id': str(session.id),
                'title': session.title,
                'agent_name': session.agent.name,
                'agent_id': session.agent.agent_id,
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat()
            })
        
        return JsonResponse({
            'sessions': sessions_data,
            'page': sessions_page.number,
            'total_pages': paginator.num_pages,
            'total_sessions': paginator.count
        })
        
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_info_api(request):
    """
    API endpoint for getting AgentOS instance information.
    """
    try:
        service = AgentOSService(request.user)
        info = service.get_agent_os_info()
        return JsonResponse(info)
    except Exception as e:
        logger.error(f"Error getting AgentOS info: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def agentos_fastapi_app(request):
    """
    Serve the FastAPI app for AgentOS.
    This is a placeholder - in production, you'd want to use a proper ASGI server.
    """
    try:
        # This is a simplified approach - in production, you'd want to use
        # a proper ASGI server or proxy to the FastAPI app
        app = get_agent_os_app_for_user(request.user)
        
        # For now, return information about the app
        return JsonResponse({
            'message': 'AgentOS FastAPI app is available',
            'app_id': getattr(app, 'id', 'unknown'),
            'note': 'In production, this would serve the actual FastAPI app'
        })
        
    except Exception as e:
        logger.error(f"Error getting FastAPI app: {e}")
        return JsonResponse({'error': str(e)}, status=500)
