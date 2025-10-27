# AgentOS Services Documentation

This document provides comprehensive documentation for the AgentOS-related service classes used in the Reggie SaaS application.

## Overview

The AgentOS services provide the business logic layer for interacting with the Agno (AgentOS) library. These services handle agent management, session management, message processing, and metrics tracking.

## Service Architecture

### Core Services

#### 1. AgentOSService
**Purpose**: Main service for AgentOS operations
**Location**: `apps/opie/agentos/service.py`

**Key Methods**:
- `get_available_agents()`: Get list of available agents
- `get_agent_by_id(agent_id)`: Get specific agent by ID
- `create_session(agent_id, title)`: Create new chat session
- `get_session(session_id)`: Get session by ID
- `send_message(agent_id, session_id, message, context)`: Send message to agent
- `get_agent_os_info()`: Get AgentOS instance information

**Features**:
- User-specific AgentOS initialization
- Agent discovery and management
- Session lifecycle management
- Message handling and routing
- Error handling and logging

#### 2. AgentOSMetricsService
**Purpose**: Metrics tracking and analytics
**Location**: `apps/opie/agentos/metrics_service.py`

**Key Methods**:
- `create_session()`: Track session creation
- `record_message()`: Track message metrics
- `record_usage()`: Track usage statistics
- `record_performance()`: Track performance metrics
- `record_error()`: Track errors and issues
- `get_user_metrics()`: Get user-specific metrics
- `get_agent_metrics()`: Get agent-specific metrics
- `get_system_metrics()`: Get system-wide metrics

**Features**:
- Session tracking
- Message analytics
- Usage statistics
- Performance monitoring
- Error tracking
- Cost tracking
- Token usage monitoring

## Service Classes

### AgentOSService Class

#### Initialization
```python
def __init__(self, user):
    self.user = user
    self.agent_os = None
    self._initialize_agent_os()
```

#### Core Methods

##### get_available_agents()
**Purpose**: Get list of available agents for the user
**Returns**: List[Dict[str, Any]]

**Response Format**:
```python
[
    {
        'id': 'agent_123',
        'name': 'Assistant',
        'description': 'Helpful assistant',
        'model': 'gpt-4',
        'tools': ['search', 'calculator'],
        'capabilities': ['chat', 'analysis']
    }
]
```

##### get_agent_by_id(agent_id)
**Purpose**: Get specific agent by ID
**Parameters**: `agent_id` (str)
**Returns**: Agent object or None

##### create_session(agent_id, title)
**Purpose**: Create new chat session
**Parameters**: 
- `agent_id` (str): Agent identifier
- `title` (str): Session title (default: "New Chat")
**Returns**: Session ID or None

##### get_session(session_id)
**Purpose**: Get session by ID
**Parameters**: `session_id` (str)
**Returns**: Session object or None

##### send_message(agent_id, session_id, message, context)
**Purpose**: Send message to agent
**Parameters**:
- `agent_id` (str): Agent identifier
- `session_id` (str): Session identifier
- `message` (str): Message content
- `context` (Dict, optional): Additional context
**Returns**: Response dictionary

**Response Format**:
```python
{
    'success': True,
    'response': 'Agent response',
    'session_id': 'session_456',
    'agent_id': 'agent_123',
    'timestamp': '2024-01-01T12:00:00Z'
}
```

##### get_agent_os_info()
**Purpose**: Get AgentOS instance information
**Returns**: Dictionary with instance details

**Response Format**:
```python
{
    'id': 'agentos_user_123',
    'description': 'AgentOS instance for user@example.com',
    'agents_count': 5,
    'available_agents': [...]
}
```

### AgentOSMetricsService Class

#### Initialization
```python
def __init__(self, user=None):
    self.user = user
    self.cache_ttl = 300  # 5 minutes
```

#### Core Methods

##### create_session(agent_id, agent_name, session_id, title)
**Purpose**: Track session creation
**Parameters**:
- `agent_id` (str): Agent identifier
- `agent_name` (str): Human-readable agent name
- `session_id` (str): Session identifier
- `title` (str): Session title
**Returns**: AgentOSSession object

##### record_message(session, message_id, role, content, **kwargs)
**Purpose**: Track message metrics
**Parameters**:
- `session`: Session object
- `message_id` (str): Message identifier
- `role` (str): Message role (user/assistant/system)
- `content` (str): Message content
- `**kwargs`: Additional metrics (tokens, cost, response_time, etc.)
**Returns**: AgentOSMessage object

##### record_usage(user, agent_id, date, **metrics)
**Purpose**: Track usage statistics
**Parameters**:
- `user`: User object
- `agent_id` (str): Agent identifier
- `date` (date): Usage date
- `**metrics`: Usage metrics (sessions, messages, tokens, cost, etc.)
**Returns**: AgentOSUsage object

##### record_performance(agent_id, date, **metrics)
**Purpose**: Track performance metrics
**Parameters**:
- `agent_id` (str): Agent identifier
- `date` (date): Performance date
- `**metrics`: Performance metrics (sessions, success_rate, response_time, etc.)
**Returns**: AgentOSPerformance object

##### record_error(user, agent_id, error_type, error_message, **kwargs)
**Purpose**: Track errors and issues
**Parameters**:
- `user`: User object
- `agent_id` (str): Agent identifier
- `error_type` (str): Error type
- `error_message` (str): Error message
- `**kwargs`: Additional error details (session, context, stack_trace, etc.)
**Returns**: AgentOSError object

##### get_user_metrics(user, days=30)
**Purpose**: Get user-specific metrics
**Parameters**:
- `user`: User object
- `days` (int): Number of days to look back
**Returns**: Dictionary with user metrics

##### get_agent_metrics(agent_id, days=30)
**Purpose**: Get agent-specific metrics
**Parameters**:
- `agent_id` (str): Agent identifier
- `days` (int): Number of days to look back
**Returns**: Dictionary with agent metrics

##### get_system_metrics(days=30)
**Purpose**: Get system-wide metrics
**Parameters**:
- `days` (int): Number of days to look back
**Returns**: Dictionary with system metrics

## API View Classes

### AgentOSAPIView
**Purpose**: Django view for AgentOS API endpoints
**Methods**: GET, POST
**Authentication**: User authentication required

**GET Actions**:
- `info`: Get AgentOS instance information
- `agents`: Get available agents

**POST Actions**:
- `send_message`: Send message to agent
- `create_session`: Create new session

### AgentOSWebhookView
**Purpose**: Webhook endpoint for external integrations
**Methods**: POST
**Authentication**: None (webhook)

**Features**:
- External integration support
- Webhook data processing
- Error handling

## Configuration Services

### AgentOSConfig Class
**Purpose**: AgentOS configuration and setup
**Location**: `apps/opie/agentos/config.py`

**Key Methods**:
- `get_llm_model(model_provider)`: Get LLM model from provider
- `create_agent_from_django(django_agent, user, session_id)`: Create AgentOS agent from Django agent
- `create_vault_agent(project_id, user, session_id, **kwargs)`: Create vault agent
- `get_available_agents(user)`: Get available agents for user
- `create_knowledge_base(name, description)`: Create knowledge base
- `initialize_agent_os(user, include_vault_agents)`: Initialize AgentOS instance
- `get_agent_os_app(user, include_vault_agents)`: Get FastAPI app

## Service Integration

### Django Integration
- User authentication and authorization
- Team-based permissions
- Subscription-based access control
- Database persistence
- Caching layer

### Agno Integration
- Agent creation and management
- Session lifecycle
- Message processing
- Knowledge base integration
- Tool integration

### External Integrations
- Webhook support
- API endpoints
- Metrics collection
- Error tracking
- Performance monitoring

## Error Handling

### Service-Level Errors
- AgentOS initialization failures
- Agent not found errors
- Session creation failures
- Message processing errors
- Metrics recording errors

### Error Recovery
- Graceful degradation
- Fallback mechanisms
- User-friendly error messages
- Logging and monitoring

## Performance Considerations

### Caching
- Service instance caching
- User permissions caching
- Agent list caching
- Metrics caching

### Database Optimization
- Efficient queries
- Proper indexing
- Connection pooling
- Query optimization

### Memory Management
- Service instance lifecycle
- Cache management
- Resource cleanup
- Memory monitoring

## Security Considerations

### Authentication
- User-based access control
- Session ownership validation
- Permission checking
- API key management

### Data Protection
- Input validation
- SQL injection prevention
- XSS protection
- CSRF protection

### Privacy
- Data encryption
- Access logging
- Audit trails
- Compliance features

## Future Enhancements

### Planned Features
- **Real-time Updates**: WebSocket integration
- **Advanced Analytics**: Machine learning insights
- **Multi-tenant Support**: Enhanced isolation
- **API Rate Limiting**: Abuse prevention
- **Advanced Caching**: Redis integration

### Performance Improvements
- **Async Processing**: Background tasks
- **Database Sharding**: Scalability
- **CDN Integration**: Asset delivery
- **Load Balancing**: High availability

### Security Enhancements
- **OAuth Integration**: Third-party auth
- **API Versioning**: Backward compatibility
- **Audit Logging**: Security monitoring
- **Compliance Tools**: GDPR/CCPA support



