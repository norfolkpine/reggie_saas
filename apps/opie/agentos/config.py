"""
AgentOS Configuration for Django Integration

This module provides configuration and setup for AgentOS within the Django application.
It bridges the existing agent infrastructure with AgentOS capabilities.
"""

import logging
from typing import List, Optional, Dict, Any
from django.conf import settings
from django.core.cache import cache

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.os import AgentOS
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector

from ..models import Agent as DjangoAgent, ModelProvider
from django.db import models
from ..agents.agent_builder import AgentBuilder
from ..agents.vault_agent import VaultAgentBuilder

logger = logging.getLogger(__name__)


class AgentOSConfig:
    """
    Configuration class for AgentOS integration with Django.
    Manages agent creation, knowledge bases, and AgentOS instance setup.
    """
    
    def __init__(self):
        self.agent_os = None
        self.agents = []
        self.knowledge_bases = {}
        
    def get_llm_model(self, model_provider: ModelProvider) -> Any:
        """Get LLM model from ModelProvider."""
        if model_provider.provider == "openai":
            return OpenAIChat(id=model_provider.model_name)
        # Add other providers as needed
        return OpenAIChat(id=model_provider.model_name)
    
    def create_agent_from_django(self, django_agent: DjangoAgent, user, session_id: str) -> Agent:
        """
        Create an AgentOS Agent from a Django Agent model.
        This bridges the existing AgentBuilder with AgentOS.
        """
        try:
            # Use existing AgentBuilder to create the agent
            agent_builder = AgentBuilder(
                agent_id=django_agent.agent_id,
                user=user,
                session_id=session_id
            )
            
            # Build the agent using existing infrastructure
            agent = agent_builder.build()
            
            # Convert to AgentOS format if needed
            return agent
            
        except Exception as e:
            logger.error(f"Failed to create agent from Django model {django_agent.agent_id}: {e}")
            raise
    
    def create_vault_agent(self, project_id: str, user, session_id: str, 
                          folder_id: Optional[str] = None, 
                          file_ids: Optional[List[str]] = None,
                          model_name: Optional[str] = None) -> Agent:
        """
        Create a vault agent using existing VaultAgentBuilder.
        """
        try:
            vault_builder = VaultAgentBuilder(
                project_id=project_id,
                user=user,
                session_id=session_id,
                agent_id=f"vault_{project_id}",
                folder_id=folder_id,
                file_ids=file_ids
            )
            
            return vault_builder.build(model_name=model_name)
            
        except Exception as e:
            logger.error(f"Failed to create vault agent for project {project_id}: {e}")
            raise
    
    def get_available_agents(self, user) -> List[Agent]:
        """
        Get all available agents for a user based on their permissions.
        """
        agents = []
        
        try:
            # Get Django agents accessible by user
            # First get global agents
            django_agents = DjangoAgent.objects.filter(is_global=True)
            
            # Add team-based agents
            from apps.teams.models import Membership
            user_teams = Membership.objects.filter(user=user).values_list('team', flat=True)
            team_agents = DjangoAgent.objects.filter(team__in=user_teams)
            django_agents = django_agents.union(team_agents)
            
            # Add subscription-based agents
            subscription_agents = DjangoAgent.objects.filter(
                subscriptions__customer__user=user, 
                subscriptions__status="active"
            )
            django_agents = django_agents.union(subscription_agents)
            
            for django_agent in django_agents:
                try:
                    # Create a temporary session ID for agent creation
                    temp_session_id = f"agentos_{django_agent.agent_id}_{user.id}"
                    agent = self.create_agent_from_django(django_agent, user, temp_session_id)
                    agents.append(agent)
                except Exception as e:
                    logger.warning(f"Failed to create agent {django_agent.name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error getting available agents: {e}")
            
        return agents
    
    def create_knowledge_base(self, name: str, description: str = "") -> Knowledge:
        """
        Create a knowledge base using existing infrastructure.
        """
        try:
            # Use existing knowledge base creation logic
            from .models import KnowledgeBase
            
            # This would need to be adapted based on your existing knowledge base setup
            # For now, return a basic knowledge base
            return Knowledge(
                vector_db=PgVector(
                    db_url=settings.DATABASE_URL,
                    table_name=f"agentos_kb_{name.lower().replace(' ', '_')}",
                    embedder=OpenAIChat(id="text-embedding-ada-002")
                ),
                num_documents=5
            )
            
        except Exception as e:
            logger.error(f"Failed to create knowledge base {name}: {e}")
            raise
    
    def initialize_agent_os(self, user, include_vault_agents: bool = True) -> AgentOS:
        """
        Initialize AgentOS with available agents and knowledge bases.
        """
        try:
            # Get available agents
            agents = self.get_available_agents(user)
            
            # Add vault agents if requested
            if include_vault_agents:
                # This would need to be adapted based on your project structure
                # For now, we'll skip vault agents in the initial setup
                pass
            
            # If no agents are available, create a simple default agent
            if not agents:
                from agno.agent import Agent
                from agno.models.openai import OpenAIChat
                
                default_agent = Agent(
                    name="Default Assistant",
                    model=OpenAIChat(id="gpt-4"),
                    instructions=["You are a helpful AI assistant."],
                    markdown=True
                )
                agents = [default_agent]
            
            # Create AgentOS instance
            self.agent_os = AgentOS(
                description=f"AgentOS instance for {user.email}",
                agents=agents
            )
            
            return self.agent_os
            
        except Exception as e:
            logger.error(f"Failed to initialize AgentOS: {e}")
            raise
    
    def get_agent_os_app(self, user, include_vault_agents: bool = True):
        """
        Get the FastAPI app for AgentOS.
        """
        try:
            if not self.agent_os:
                self.initialize_agent_os(user, include_vault_agents)
            
            return self.agent_os.get_app()
            
        except Exception as e:
            logger.error(f"Failed to get AgentOS app: {e}")
            raise


# Global instance
agent_os_config = AgentOSConfig()


def get_agent_os_for_user(user, include_vault_agents: bool = True) -> AgentOS:
    """
    Get or create an AgentOS instance for a specific user.
    Uses caching to avoid recreating instances.
    """
    cache_key = f"agentos_user_{user.id}_{include_vault_agents}"
    cached_agent_os = cache.get(cache_key)
    
    if cached_agent_os:
        return cached_agent_os
    
    try:
        agent_os = agent_os_config.initialize_agent_os(user, include_vault_agents)
        # Cache for 30 minutes
        cache.set(cache_key, agent_os, timeout=1800)
        return agent_os
    except Exception as e:
        logger.error(f"Failed to get AgentOS for user {user.id}: {e}")
        raise


def get_agent_os_app_for_user(user, include_vault_agents: bool = True):
    """
    Get the FastAPI app for AgentOS for a specific user.
    """
    try:
        agent_os = get_agent_os_for_user(user, include_vault_agents)
        return agent_os.get_app()
    except Exception as e:
        logger.error(f"Failed to get AgentOS app for user {user.id}: {e}")
        raise
