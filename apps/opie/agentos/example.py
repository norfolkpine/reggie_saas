"""
AgentOS Integration Example

This file demonstrates how to use the AgentOS integration with Django.
It provides examples of common operations and usage patterns.
"""

import logging
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from .service import AgentOSService
from .config import get_agent_os_for_user, get_agent_os_app_for_user

User = get_user_model()
logger = logging.getLogger(__name__)


def example_basic_usage():
    """
    Example of basic AgentOS usage.
    """
    # Get a user (in practice, this would be from request.user)
    user = User.objects.first()
    
    if not user:
        print("No users found. Please create a user first.")
        return
    
    print(f"Using AgentOS with user: {user.email}")
    
    # Create AgentOS service
    service = AgentOSService(user)
    
    # Get available agents
    agents = service.get_available_agents()
    print(f"Available agents: {len(agents)}")
    
    for agent in agents:
        print(f"  - {agent['name']} (ID: {agent['id']})")
    
    # Get AgentOS info
    info = service.get_agent_os_info()
    print(f"AgentOS Info: {info}")
    
    # Create a session (if agents are available)
    if agents:
        agent_id = agents[0]['id']
        session_id = service.create_session(agent_id, "Example Session")
        print(f"Created session: {session_id}")
        
        # Send a message
        result = service.send_message(
            agent_id=agent_id,
            session_id=session_id,
            message="Hello, how can you help me?"
        )
        print(f"Message result: {result}")


def example_agent_creation():
    """
    Example of creating agents programmatically.
    """
    from ..models import Agent as DjangoAgent
    
    # Get a user
    user = User.objects.first()
    
    if not user:
        print("No users found. Please create a user first.")
        return
    
    # Get a Django agent
    django_agent = DjangoAgent.objects.first()
    
    if not django_agent:
        print("No Django agents found. Please create an agent first.")
        return
    
    print(f"Creating AgentOS agent from Django agent: {django_agent.name}")
    
    # Create AgentOS instance
    agent_os = get_agent_os_for_user(user)
    
    # The agent should already be available through the service
    service = AgentOSService(user)
    agents = service.get_available_agents()
    
    print(f"AgentOS agents available: {len(agents)}")


def example_fastapi_app():
    """
    Example of getting the FastAPI app.
    """
    user = User.objects.first()
    
    if not user:
        print("No users found. Please create a user first.")
        return
    
    # Get the FastAPI app
    app = get_agent_os_app_for_user(user)
    
    print(f"FastAPI app created: {app}")
    print("You can now run this with uvicorn or integrate it into your Django app.")


def example_custom_agent():
    """
    Example of creating a custom agent.
    """
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat
    
    # Create a simple custom agent
    custom_agent = Agent(
        name="Custom Example Agent",
        model=OpenAIChat(id="gpt-4"),
        instructions=["You are a helpful assistant."],
        markdown=True
    )
    
    print(f"Created custom agent: {custom_agent.name}")
    
    # In practice, you would add this to your AgentOS instance
    # agent_os.agents.append(custom_agent)


class ExampleCommand(BaseCommand):
    """
    Django management command to run examples.
    """
    help = 'Run AgentOS integration examples'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--example',
            type=str,
            choices=['basic', 'agent_creation', 'fastapi', 'custom'],
            default='basic',
            help='Which example to run'
        )
    
    def handle(self, *args, **options):
        example = options['example']
        
        try:
            if example == 'basic':
                example_basic_usage()
            elif example == 'agent_creation':
                example_agent_creation()
            elif example == 'fastapi':
                example_fastapi_app()
            elif example == 'custom':
                example_custom_agent()
            
            self.stdout.write(
                self.style.SUCCESS(f'Example "{example}" completed successfully!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Example "{example}" failed: {e}')
            )


if __name__ == "__main__":
    # Run examples directly (for testing)
    print("Running AgentOS integration examples...")
    
    try:
        example_basic_usage()
        print("Basic usage example completed!")
    except Exception as e:
        print(f"Basic usage example failed: {e}")
    
    try:
        example_agent_creation()
        print("Agent creation example completed!")
    except Exception as e:
        print(f"Agent creation example failed: {e}")
    
    try:
        example_fastapi_app()
        print("FastAPI app example completed!")
    except Exception as e:
        print(f"FastAPI app example failed: {e}")
