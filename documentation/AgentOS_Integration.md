# AgentOS Integration with Django

This document describes the integration of AgentOS with the Django-based Reggie SaaS application.

## Overview

AgentOS is integrated into the existing Django application under `apps/opie/` to provide enhanced agent management, API endpoints, and web interfaces. The integration bridges the existing agent infrastructure with AgentOS capabilities while maintaining compatibility with the current system.

## Architecture

### Components

1. **AgentOS Configuration** (`apps/opie/agentos/config.py`)
   - Manages AgentOS instance creation and configuration
   - Bridges Django agents with AgentOS agents
   - Handles knowledge base integration

2. **AgentOS Service** (`apps/opie/agentos/service.py`)
   - High-level service for AgentOS operations
   - Manages agent interactions and session handling
   - Provides API response formatting

3. **AgentOS Views** (`apps/opie/agentos/views.py`)
   - Django views for web interface and API endpoints
   - Handles authentication and request processing
   - Provides both web UI and REST API access

4. **Management Commands**
   - `agentos_start`: Start AgentOS server
   - `agentos_test`: Test AgentOS functionality
   - `agentos_sync`: Sync Django agents with AgentOS

## Installation

### Prerequisites

- Python 3.9+
- Django application with existing agent infrastructure
- AgentOS (agno) package installed

### Dependencies

The following packages are required:

```bash
pip install agno fastapi["standard"] uvicorn
```

### Configuration

Add the following settings to your Django settings:

```python
# AgentOS Settings
AGENTOS_ENABLED = True
AGENTOS_DEFAULT_HOST = "127.0.0.1"
AGENTOS_DEFAULT_PORT = 7777
AGENTOS_CACHE_TTL = 1800  # 30 minutes
AGENTOS_INCLUDE_VAULT_AGENTS = True
AGENTOS_AUTO_RELOAD = DEBUG
```

## Usage

### Starting AgentOS Server

To start the AgentOS server:

```bash
# Start with default settings
python manage.py agentos_start

# Start with custom host and port
python manage.py agentos_start --host 0.0.0.0 --port 8080

# Start for specific user
python manage.py agentos_start --user-id 1

# Start with auto-reload for development
python manage.py agentos_start --reload
```

### Testing AgentOS

To test AgentOS functionality:

```bash
# Test with default user
python manage.py agentos_test

# Test with specific user
python manage.py agentos_test --user-id 1

# Test specific agent
python manage.py agentos_test --agent-id "agent-123"
```

### Syncing Agents

To sync Django agents with AgentOS:

```bash
# Sync all agents for all users
python manage.py agentos_sync

# Sync for specific user
python manage.py agentos_sync --user-id 1

# Sync specific agent
python manage.py agentos_sync --agent-id "agent-123"

# Dry run to see what would be synced
python manage.py agentos_sync --dry-run
```

## API Endpoints

### Web Interface

- `/agentos/` - Main dashboard
- `/agentos/agents/` - Agent list
- `/agentos/chat/<agent_id>/` - Interactive chat
- `/agentos/session/<session_id>/` - Session management

### REST API

- `GET /api/v1/agentos/` - AgentOS info
- `GET /api/v1/agentos/agents/` - Available agents
- `POST /api/v1/agentos/send-message/` - Send message to agent
- `POST /api/v1/agentos/create-session/` - Create new session
- `GET /api/v1/agentos/sessions/` - User sessions
- `GET /api/v1/agentos/info/` - AgentOS instance info

### Example API Usage

#### Get Available Agents

```bash
curl -X GET "http://localhost:8000/api/v1/agentos/agents/" \
  -H "Authorization: Bearer <token>"
```

#### Send Message to Agent

```bash
curl -X POST "http://localhost:8000/api/v1/agentos/send-message/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "agent_id": "agent-123",
    "message": "Hello, how can you help me?",
    "session_id": "session-456"
  }'
```

#### Create New Session

```bash
curl -X POST "http://localhost:8000/api/v1/agentos/create-session/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "agent_id": "agent-123",
    "title": "New Chat Session"
  }'
```

## Integration with Existing Agents

The integration maintains compatibility with existing Django agents by:

1. **Preserving Existing Functionality**: All existing agent functionality remains unchanged
2. **Bridging Infrastructure**: AgentOS agents are created from Django Agent models
3. **Unified API**: Both Django and AgentOS agents are accessible through the same API
4. **Session Management**: Chat sessions are managed through Django's existing system

### Agent Creation Flow

1. Django Agent model is queried
2. AgentBuilder creates the agent using existing infrastructure
3. Agent is wrapped for AgentOS compatibility
4. Agent is added to AgentOS instance

### Knowledge Base Integration

AgentOS knowledge bases are created using the existing PgVector infrastructure:

- Vector databases use the same PostgreSQL connection
- Embedding models are shared between systems
- Knowledge base permissions are respected

## Web Interface

### Dashboard

The main dashboard (`/agentos/`) provides:

- Overview of available agents
- Quick access to chat interfaces
- Session management
- AgentOS instance information

### Chat Interface

The chat interface (`/agentos/chat/<agent_id>/`) provides:

- Real-time messaging with agents
- Session history
- File upload capabilities
- Tool usage visualization

### Agent Management

The agent list (`/agentos/agents/`) provides:

- List of available agents
- Agent capabilities and tools
- Performance metrics
- Configuration options

## Caching

AgentOS uses Django's caching framework for:

- Agent instances (30-minute TTL)
- Knowledge base status
- User permissions
- Session data

Cache keys follow the pattern: `agentos_<type>_<identifier>`

## Security

### Authentication

- All endpoints require Django authentication
- User permissions are respected
- Agent access is controlled by existing RBAC

### CSRF Protection

- Web endpoints are CSRF protected
- API endpoints use token-based authentication
- Webhook endpoints are CSRF exempt

### Data Privacy

- User data is isolated per user
- Agent sessions are user-specific
- Knowledge base access follows existing permissions

## Monitoring and Logging

### Logging

AgentOS operations are logged using Django's logging framework:

```python
import logging
logger = logging.getLogger(__name__)
```

### Error Handling

- Graceful degradation when AgentOS is unavailable
- Detailed error messages for debugging
- Fallback to existing agent functionality

## Troubleshooting

### Common Issues

1. **AgentOS Not Starting**
   - Check if agno package is installed
   - Verify database connection
   - Check user permissions

2. **Agents Not Available**
   - Run sync command: `python manage.py agentos_sync`
   - Check agent permissions
   - Verify model provider configuration

3. **Knowledge Base Issues**
   - Check PgVector configuration
   - Verify embedding model settings
   - Check vector table permissions

### Debug Mode

Enable debug mode for detailed logging:

```python
# In settings.py
AGENTOS_DEBUG = True
```

## Development

### Adding New Agent Types

1. Create agent in Django models
2. Update AgentOS configuration
3. Add agent-specific tools if needed
4. Test with management commands

### Customizing AgentOS

1. Extend `AgentOSConfig` class
2. Override agent creation methods
3. Add custom knowledge base types
4. Implement custom tools

## Production Deployment

### Requirements

- ASGI server (e.g., Uvicorn, Gunicorn with Uvicorn workers)
- Redis for caching (recommended)
- PostgreSQL with PgVector extension

### Configuration

```python
# Production settings
AGENTOS_ENABLED = True
AGENTOS_DEFAULT_HOST = "0.0.0.0"
AGENTOS_DEFAULT_PORT = 7777
AGENTOS_CACHE_TTL = 3600  # 1 hour
AGENTOS_AUTO_RELOAD = False
```

### Scaling

- Use multiple AgentOS instances behind a load balancer
- Implement session affinity for chat sessions
- Use Redis for shared caching
- Consider agent instance pooling

## Examples

### Basic Agent Interaction

```python
from apps.opie.agentos.service import AgentOSService

# Create service for user
service = AgentOSService(user)

# Get available agents
agents = service.get_available_agents()

# Send message to agent
result = service.send_message(
    agent_id="agent-123",
    session_id="session-456",
    message="Hello, how can you help me?"
)
```

### Custom Agent Creation

```python
from apps.opie.agentos.config import agent_os_config

# Create custom agent
agent = agent_os_config.create_agent_from_django(django_agent, user, session_id)

# Add to AgentOS instance
agent_os = agent_os_config.initialize_agent_os(user)
agent_os.agents.append(agent)
```

## Support

For issues and questions:

1. Check the troubleshooting section
2. Review Django and AgentOS logs
3. Test with management commands
4. Contact the development team

## Changelog

### Version 1.0.0
- Initial AgentOS integration
- Django views and API endpoints
- Management commands
- Web interface
- Documentation
