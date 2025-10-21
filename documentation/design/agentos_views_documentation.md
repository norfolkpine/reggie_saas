# AgentOS Views Documentation

This document provides comprehensive documentation for the AgentOS-related Django views used in the Reggie SaaS application.

## Overview

The AgentOS views provide both web interface and API endpoints for interacting with the Agno (AgentOS) library. These views handle user authentication, session management, agent interactions, and metrics display.

## View Architecture

### Web Interface Views

#### 1. AgentOSDashboardView
**Purpose**: Main dashboard for AgentOS functionality
**Template**: `agentos/dashboard.html`
**Authentication**: LoginRequiredMixin

```python
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
```

**Context Data**:
- `agentos_info`: AgentOS instance information
- `available_agents`: List of available agents
- `user_agents`: Django agents accessible to user (global, team, subscription-based)
- `error`: Error message if loading fails

**Features**:
- Displays AgentOS instance status
- Shows available agents
- Lists user's accessible Django agents
- Error handling for AgentOS initialization

#### 2. AgentOSAgentListView
**Purpose**: List and manage available agents
**Template**: `agentos/agents.html`
**Authentication**: LoginRequiredMixin

```python
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
```

**Context Data**:
- `agents`: Available AgentOS agents
- `django_agents`: Django agents accessible to user
- `error`: Error message if loading fails

**Features**:
- Lists all available agents
- Shows Django agents with proper permissions
- Handles agent access control

#### 3. AgentOSSessionView
**Purpose**: Manage chat sessions
**Template**: `agentos/session.html`
**Authentication**: LoginRequiredMixin

```python
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
```

**URL Parameters**:
- `session_id`: Session identifier

**Context Data**:
- `session`: Session object
- `agent`: Agent object for the session
- `agentos_info`: AgentOS instance information
- `error`: Error message if session not found

**Features**:
- Displays session details
- Shows associated agent
- Handles session not found errors

#### 4. AgentOSChatView
**Purpose**: Interactive chat interface
**Template**: `agentos/chat.html`
**Authentication**: LoginRequiredMixin

```python
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
```

**URL Parameters**:
- `agent_id`: Agent identifier

**Context Data**:
- `agent`: Agent object
- `agentos_info`: AgentOS instance information
- `error`: Error message if agent not found

**Features**:
- Interactive chat interface
- Real-time messaging
- Agent-specific chat

### API Endpoints

#### 1. agentos_api
**Purpose**: Main API endpoint for AgentOS functionality
**Methods**: GET, POST
**Authentication**: login_required

**GET Parameters**:
- `action`: API action (info, agents)

**POST Data**:
- `action`: API action
- `agent_id`: Agent identifier
- `session_id`: Session identifier
- `message`: Message content
- `context`: Additional context

**Responses**:
- JSON responses with success/error status
- Agent information
- Session data
- Message results

#### 2. agentos_agents_api
**Purpose**: Get available agents
**Method**: GET
**Authentication**: login_required

**Response**:
```json
{
  "agents": [
    {
      "id": "agent_123",
      "name": "Assistant",
      "description": "Helpful assistant",
      "model": "gpt-4",
      "tools": ["search", "calculator"],
      "capabilities": ["chat", "analysis"]
    }
  ]
}
```

#### 3. agentos_send_message
**Purpose**: Send message to agent
**Method**: POST
**Authentication**: login_required, csrf_exempt

**Request Data**:
```json
{
  "agent_id": "agent_123",
  "session_id": "session_456",
  "message": "Hello, how can you help?",
  "context": {}
}
```

**Response**:
```json
{
  "success": true,
  "response": "I can help you with...",
  "session_id": "session_456",
  "agent_id": "agent_123",
  "timestamp": "2024-01-01T12:00:00Z"
}
```

#### 4. agentos_create_session
**Purpose**: Create new chat session
**Method**: POST
**Authentication**: login_required, csrf_exempt

**Request Data**:
```json
{
  "agent_id": "agent_123",
  "title": "New Chat Session"
}
```

**Response**:
```json
{
  "success": true,
  "session_id": "session_456"
}
```

#### 5. agentos_sessions_api
**Purpose**: Get user's chat sessions
**Method**: GET
**Authentication**: login_required

**Query Parameters**:
- `page`: Page number for pagination

**Response**:
```json
{
  "sessions": [
    {
      "id": "session_456",
      "title": "Chat Session",
      "agent_name": "Assistant",
      "agent_id": "agent_123",
      "created_at": "2024-01-01T12:00:00Z",
      "updated_at": "2024-01-01T12:30:00Z"
    }
  ],
  "page": 1,
  "total_pages": 5,
  "total_sessions": 50
}
```

#### 6. agentos_info_api
**Purpose**: Get AgentOS instance information
**Method**: GET
**Authentication**: login_required

**Response**:
```json
{
  "id": "agentos_user_123",
  "description": "AgentOS instance for user@example.com",
  "agents_count": 5,
  "available_agents": [...]
}
```

#### 7. agentos_fastapi_app
**Purpose**: Serve FastAPI app for AgentOS
**Method**: GET
**Authentication**: login_required

**Response**:
```json
{
  "message": "AgentOS FastAPI app is available",
  "app_id": "agentos_app_123",
  "note": "In production, this would serve the actual FastAPI app"
}
```

#### 8. agentos_webhook
**Purpose**: Webhook endpoint for external integrations
**Method**: POST
**Authentication**: None (webhook)

**Request Data**:
```json
{
  "event": "message_received",
  "data": {...}
}
```

**Response**:
```json
{
  "status": "success"
}
```

## URL Patterns

### Web Interface URLs
```
/agentos/                          # Dashboard
/agentos/agents/                   # Agent list
/agentos/chat/<agent_id>/          # Chat with agent
/agentos/session/<session_id>/     # Session view
/agentos/webhook/                  # Webhook endpoint
```

### API URLs
```
/api/v1/agentos/                   # Main API
/api/v1/agentos/agents/            # Agents API
/api/v1/agentos/send-message/      # Send message
/api/v1/agentos/create-session/    # Create session
/api/v1/agentos/sessions/          # Sessions API
/api/v1/agentos/info/              # Info API
/api/v1/agentos/fastapi/           # FastAPI app
```

## Error Handling

### Common Error Responses
```json
{
  "success": false,
  "error": "Error message",
  "response": null
}
```

### Error Types
- **Authentication Error**: User not logged in
- **Agent Not Found**: Invalid agent ID
- **Session Not Found**: Invalid session ID
- **Missing Fields**: Required fields not provided
- **Invalid JSON**: Malformed request data
- **AgentOS Error**: AgentOS initialization or operation failed

## Security Considerations

### Authentication
- All views require user authentication
- User-specific data access only
- Session ownership validation

### CSRF Protection
- Web views: CSRF tokens required
- API endpoints: csrf_exempt for external integrations
- Webhook endpoints: No CSRF protection (external)

### Data Validation
- Input sanitization
- JSON validation
- Field length limits
- SQL injection prevention

## Performance Considerations

### Caching
- AgentOS service instances cached
- User permissions cached
- Agent lists cached

### Database Queries
- Optimized queries with select_related
- Pagination for large datasets
- Indexed fields for fast lookups

### Error Handling
- Graceful degradation
- User-friendly error messages
- Logging for debugging

## Integration Points

### Django Integration
- User authentication system
- Team-based permissions
- Subscription-based access
- Django admin integration

### Agno Integration
- AgentOS service layer
- Session management
- Message handling
- Error tracking

### Frontend Integration
- AJAX API calls
- Real-time updates
- WebSocket support (future)
- Progressive enhancement

## Future Enhancements

### Planned Features
- **Real-time Chat**: WebSocket integration
- **File Uploads**: Document sharing in chat
- **Voice Messages**: Audio message support
- **Screen Sharing**: Collaborative sessions
- **Multi-language**: Internationalization

### Performance Improvements
- **Caching**: Redis caching layer
- **CDN**: Static asset delivery
- **Database**: Query optimization
- **API**: Rate limiting and throttling

### Security Enhancements
- **Rate Limiting**: API abuse prevention
- **Audit Logging**: Security event tracking
- **Encryption**: End-to-end message encryption
- **Compliance**: GDPR/CCPA compliance features
