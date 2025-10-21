"""
AgentOS Service for Django Integration

This service provides a high-level interface for AgentOS operations within Django.
It handles agent management, session management, and API interactions.
"""

import logging
import json
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View

from .config import get_agent_os_for_user, get_agent_os_app_for_user
from ..models import Agent as DjangoAgent, ChatSession

User = get_user_model()
logger = logging.getLogger(__name__)


class AgentOSService:
    """
    Service class for managing AgentOS operations within Django.
    Provides methods for agent interaction, session management, and API responses.
    """
    
    def __init__(self, user):
        self.user = user
        self.agent_os = None
        self._initialize_agent_os()
    
    def _initialize_agent_os(self):
        """Initialize AgentOS for the user."""
        try:
            self.agent_os = get_agent_os_for_user(self.user, include_vault_agents=True)
        except Exception as e:
            logger.error(f"Failed to initialize AgentOS for user {self.user.id}: {e}")
            raise
    
    def get_available_agents(self) -> List[Dict[str, Any]]:
        """
        Get list of available agents for the user.
        Returns agent information in a format suitable for API responses.
        """
        try:
            agents = []
            if self.agent_os and hasattr(self.agent_os, 'agents'):
                for i, agent in enumerate(self.agent_os.agents):
                    # Use the agent's existing ID if it has one, otherwise generate one
                    agent_id = getattr(agent, 'id', None)
                    if not agent_id:
                        # Generate ID from name if no ID exists
                        agent_id = agent.name.lower().replace(' ', '-') if hasattr(agent, 'name') else f'agent_{i}'
                    
                    agent_info = {
                        'id': agent_id,
                        'name': getattr(agent, 'name', 'Unknown Agent'),
                        'description': getattr(agent, 'description', ''),
                        'model': getattr(agent.model, 'id', 'unknown') if hasattr(agent, 'model') else 'unknown',
                        'tools': [getattr(tool, 'name', str(type(tool).__name__)) for tool in getattr(agent, 'tools', [])],
                        'capabilities': getattr(agent, 'capabilities', [])
                    }
                    agents.append(agent_info)
            return agents
        except Exception as e:
            logger.error(f"Failed to get available agents: {e}")
            return []
    
    def get_agent_by_id(self, agent_id: str) -> Optional[Any]:
        """
        Get a specific agent by ID.
        """
        try:
            if self.agent_os and hasattr(self.agent_os, 'agents'):
                for i, agent in enumerate(self.agent_os.agents):
                    # Use the same ID logic as in get_available_agents
                    agent_id_attr = getattr(agent, 'id', None)
                    if not agent_id_attr:
                        # Generate ID from name if no ID exists
                        agent_id_attr = agent.name.lower().replace(' ', '-') if hasattr(agent, 'name') else f'agent_{i}'
                    
                    if agent_id_attr == agent_id:
                        return agent
            return None
        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}")
            return None
    
    def create_session(self, agent_id: str, title: str = "New Chat") -> Optional[str]:
        """
        Create a new chat session for an agent.
        Returns the session ID.
        """
        try:
            # First check if it's an AgentOS agent
            agentos_agent = self.get_agent_by_id(agent_id)
            if agentos_agent:
                # For AgentOS agents, we'll create a session without a Django agent
                # In a real implementation, you might want to create a special session type
                session_id = f"agentos_{agent_id}_{self.user.id}_{title.lower().replace(' ', '_')}"
                return session_id
            
            # Try to get the Django agent
            try:
                django_agent = DjangoAgent.objects.get(agent_id=agent_id)
                
                # Create a new chat session
                session = ChatSession.objects.create(
                    user=self.user,
                    agent=django_agent,
                    title=title
                )
                
                return str(session.id)
            except DjangoAgent.DoesNotExist:
                logger.error(f"Django agent {agent_id} not found")
                return None
            
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return None
    
    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """
        Get a chat session by ID.
        """
        try:
            return ChatSession.objects.get(id=session_id, user=self.user)
        except ChatSession.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    def send_message(self, agent_id: str, session_id: str, message: str, 
                    context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Send a message to an agent and get a response.
        """
        try:
            # Get the agent
            agent = self.get_agent_by_id(agent_id)
            if not agent:
                return {
                    'success': False,
                    'error': f'Agent {agent_id} not found',
                    'response': None
                }
            
            # Get or create session
            session = self.get_session(session_id)
            if not session:
                # Create a new session
                session_id = self.create_session(agent_id)
                if not session_id:
                    return {
                        'success': False,
                        'error': 'Failed to create session',
                        'response': None
                    }
                session = self.get_session(session_id)
            
            # Send message to agent
            # This would need to be adapted based on your agent's message handling
            # For now, we'll return a placeholder response
            response = {
                'success': True,
                'response': f"Agent {agent.name} received: {message}",
                'session_id': session_id,
                'agent_id': agent_id,
                'timestamp': session.updated_at.isoformat()
            }
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': None
            }
    
    def get_agent_os_info(self) -> Dict[str, Any]:
        """
        Get information about the AgentOS instance.
        """
        try:
            if not self.agent_os:
                return {'error': 'AgentOS not initialized'}
            
            return {
                'id': f"agentos_user_{self.user.id}",
                'description': getattr(self.agent_os, 'description', ''),
                'agents_count': len(getattr(self.agent_os, 'agents', [])),
                'available_agents': self.get_available_agents()
            }
        except Exception as e:
            logger.error(f"Failed to get AgentOS info: {e}")
            return {'error': str(e)}


class AgentOSAPIView(View):
    """
    Django view for AgentOS API endpoints.
    Provides REST API access to AgentOS functionality.
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Override dispatch to handle authentication and CSRF."""
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, *args, **kwargs):
        """Handle GET requests."""
        try:
            service = AgentOSService(request.user)
            
            # Get the action from URL parameters
            action = request.GET.get('action', 'info')
            
            if action == 'info':
                return JsonResponse(service.get_agent_os_info())
            elif action == 'agents':
                return JsonResponse({'agents': service.get_available_agents()})
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
                
        except Exception as e:
            logger.error(f"AgentOS API GET error: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def post(self, request, *args, **kwargs):
        """Handle POST requests."""
        try:
            service = AgentOSService(request.user)
            data = json.loads(request.body)
            
            action = data.get('action')
            
            if action == 'send_message':
                agent_id = data.get('agent_id')
                session_id = data.get('session_id')
                message = data.get('message')
                context = data.get('context')
                
                if not all([agent_id, message]):
                    return JsonResponse({'error': 'Missing required fields'}, status=400)
                
                result = service.send_message(agent_id, session_id, message, context)
                return JsonResponse(result)
                
            elif action == 'create_session':
                agent_id = data.get('agent_id')
                title = data.get('title', 'New Chat')
                
                if not agent_id:
                    return JsonResponse({'error': 'Missing agent_id'}, status=400)
                
                session_id = service.create_session(agent_id, title)
                if session_id:
                    return JsonResponse({'success': True, 'session_id': session_id})
                else:
                    return JsonResponse({'error': 'Failed to create session'}, status=500)
                    
            else:
                return JsonResponse({'error': 'Invalid action'}, status=400)
                
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"AgentOS API POST error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class AgentOSWebhookView(View):
    """
    Webhook view for external AgentOS integrations.
    """
    
    def post(self, request, *args, **kwargs):
        """Handle webhook POST requests."""
        try:
            data = json.loads(request.body)
            # Process webhook data here
            return JsonResponse({'status': 'success'})
        except Exception as e:
            logger.error(f"AgentOS webhook error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


def get_agent_os_service_for_user(user) -> AgentOSService:
    """
    Get or create an AgentOS service for a user.
    """
    cache_key = f"agentos_service_{user.id}"
    cached_service = cache.get(cache_key)
    
    if cached_service:
        return cached_service
    
    try:
        service = AgentOSService(user)
        # Cache for 30 minutes
        cache.set(cache_key, service, timeout=1800)
        return service
    except Exception as e:
        logger.error(f"Failed to create AgentOS service for user {user.id}: {e}")
        raise
