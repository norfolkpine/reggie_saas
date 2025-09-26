import logging
from pydantic import BaseModel, Field
from agno.tools import Toolkit
from agno.utils.log import logger


class RunAgentToolInput(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent to run.")
    input: str = Field(..., description="The input prompt or query for the agent.")


class RunAgentTool(Toolkit):
    """A tool to run another agent by its ID."""

    def __init__(self, user, session_id: str):
        self.user = user
        self.session_id = session_id
        super().__init__(name="run_agent_tools")
        
        # Register the methods as Agno tools
        self.register(self.run_agent_by_id)
        self.register(self.list_available_agents)
        self.register(self.find_agents_by_capability)
        self.register(self.find_agents_by_name)
        self.register(self.get_agent_details)

    def run_agent_by_id(self, agent_id: str, input: str) -> str:
        """
        Executes another AI agent with a specific ID and returns its response. 
        Use this to delegate tasks to specialized agents as part of a workflow.
        
        Args:
            agent_id: The ID of the agent to run
            input: The input prompt or query for the agent
        
        Returns:
            String containing the agent's response
        """
        logger.info(f"Running agent '{agent_id}' for user '{self.user.id}' with input: '{input}'")
        try:
            # Import here to avoid circular import
            from ..agent_builder import AgentBuilder
            
            # Each sub-agent run should have its own session_id to avoid memory contamination.
            # We can derive a new session_id from the current one.
            sub_session_id = f"{self.session_id}_{agent_id}"

            builder = AgentBuilder(agent_id=agent_id, user=self.user, session_id=sub_session_id)
            agent = builder.build()
            response = agent.run(input)

            # The response from an agent run is an AgentResponse object.
            # We should return the `output` attribute.
            if hasattr(response, "output"):
                return response.output
            return str(response)

        except Exception as e:
            logger.error(f"Error running agent '{agent_id}': {e}", exc_info=True)
            return f"Error: Could not run agent with ID '{agent_id}'. Reason: {e}"

    def list_available_agents(self, limit: int = 20) -> str:
        """
        List all available agents that the current user can access.
        
        Args:
            limit: Maximum number of agents to return (default: 20)
        
        Returns:
            Formatted string containing the list of available agents
        """
        try:
            from apps.reggie.models import Agent as DjangoAgent
            from django.db.models import Q
            
            # Get agents accessible to the user (user's agents + global agents)
            agents = DjangoAgent.objects.filter(
                Q(user=self.user) | Q(is_global=True)
            ).select_related('category', 'model', 'instructions', 'expected_output')[:limit]
            
            if not agents:
                return "No agents available."
            
            result = f"Available Agents ({len(agents)}):\n\n"
            for agent in agents:
                result += f"🔹 {agent.name}\n"
                result += f"   ID: {agent.agent_id}\n"
                result += f"   Description: {agent.description or 'No description'}\n"
                if agent.category:
                    result += f"   Category: {agent.category.name}\n"
                if agent.model:
                    result += f"   Model: {agent.model.name}\n"
                if agent.capabilities.exists():
                    capabilities = [cap.name for cap in agent.capabilities.all()]
                    result += f"   Capabilities: {', '.join(capabilities)}\n"
                result += f"   Global: {'Yes' if agent.is_global else 'No'}\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error listing agents: {e}", exc_info=True)
            return f"Error: Could not list agents. Reason: {e}"

    def find_agents_by_capability(self, capability: str, limit: int = 10) -> str:
        """
        Find agents that have a specific capability.
        
        Args:
            capability: The capability to search for (e.g., 'compliance', 'analysis', 'document_processing')
            limit: Maximum number of agents to return (default: 10)
        
        Returns:
            Formatted string containing matching agents
        """
        try:
            from apps.reggie.models import Agent as DjangoAgent, Capability
            from django.db.models import Q
            
            # Search for capability by name (case-insensitive)
            capabilities = Capability.objects.filter(name__icontains=capability)
            
            if not capabilities.exists():
                return f"No capabilities found matching '{capability}'."
            
            # Get agents that have any of the matching capabilities
            agents = DjangoAgent.objects.filter(
                Q(user=self.user) | Q(is_global=True),
                capabilities__in=capabilities
            ).select_related('category', 'model').distinct()[:limit]
            
            if not agents:
                return f"No agents found with capability '{capability}'."
            
            result = f"Agents with capability '{capability}' ({len(agents)}):\n\n"
            for agent in agents:
                result += f"🔹 {agent.name}\n"
                result += f"   ID: {agent.agent_id}\n"
                result += f"   Description: {agent.description or 'No description'}\n"
                if agent.category:
                    result += f"   Category: {agent.category.name}\n"
                # Show all capabilities for this agent
                agent_capabilities = [cap.name for cap in agent.capabilities.all()]
                result += f"   Capabilities: {', '.join(agent_capabilities)}\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error finding agents by capability: {e}", exc_info=True)
            return f"Error: Could not find agents by capability. Reason: {e}"

    def find_agents_by_name(self, name: str, limit: int = 10) -> str:
        """
        Find agents by name (case-insensitive partial match).
        
        Args:
            name: The name or partial name to search for
            limit: Maximum number of agents to return (default: 10)
        
        Returns:
            Formatted string containing matching agents
        """
        try:
            from apps.reggie.models import Agent as DjangoAgent
            from django.db.models import Q
            
            # Search for agents by name (case-insensitive partial match)
            agents = DjangoAgent.objects.filter(
                Q(user=self.user) | Q(is_global=True),
                name__icontains=name
            ).select_related('category', 'model', 'instructions', 'expected_output')[:limit]
            
            if not agents:
                return f"No agents found with name containing '{name}'."
            
            result = f"Agents with name containing '{name}' ({len(agents)}):\n\n"
            for agent in agents:
                result += f"🔹 {agent.name}\n"
                result += f"   ID: {agent.agent_id}\n"
                result += f"   Description: {agent.description or 'No description'}\n"
                if agent.category:
                    result += f"   Category: {agent.category.name}\n"
                if agent.model:
                    result += f"   Model: {agent.model.name}\n"
                if agent.capabilities.exists():
                    capabilities = [cap.name for cap in agent.capabilities.all()]
                    result += f"   Capabilities: {', '.join(capabilities)}\n"
                result += f"   Global: {'Yes' if agent.is_global else 'No'}\n"
                result += "\n"
            
            return result
            
        except Exception as e:
            logger.error(f"Error finding agents by name: {e}", exc_info=True)
            return f"Error: Could not find agents by name. Reason: {e}"

    def get_agent_details(self, agent_id: str) -> str:
        """
        Get detailed information about a specific agent.
        
        Args:
            agent_id: The ID of the agent to get details for
        
        Returns:
            Formatted string containing detailed agent information
        """
        try:
            from apps.reggie.models import Agent as DjangoAgent
            from django.db.models import Q
            
            try:
                agent = DjangoAgent.objects.filter(
                    Q(user=self.user) | Q(is_global=True),
                    agent_id=agent_id
                ).select_related('category', 'model', 'instructions', 'expected_output').first()
                
                if not agent:
                    return f"Agent with ID '{agent_id}' not found or not accessible."
                
                result = f"Agent Details: {agent.name}\n"
                result += "=" * 50 + "\n\n"
                result += f"ID: {agent.agent_id}\n"
                result += f"Description: {agent.description or 'No description'}\n"
                result += f"Created: {agent.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"Updated: {agent.updated_at.strftime('%Y-%m-%d %H:%M')}\n"
                result += f"Global: {'Yes' if agent.is_global else 'No'}\n"
                
                if agent.category:
                    result += f"Category: {agent.category.name}\n"
                
                if agent.model:
                    result += f"Model: {agent.model.name}\n"
                
                if agent.instructions:
                    result += f"Instructions: {agent.instructions.name}\n"
                
                if agent.expected_output:
                    result += f"Expected Output: {agent.expected_output.name}\n"
                
                if agent.capabilities.exists():
                    capabilities = [cap.name for cap in agent.capabilities.all()]
                    result += f"Capabilities: {', '.join(capabilities)}\n"
                
                # Configuration details
                result += f"\nConfiguration:\n"
                result += f"  Search Knowledge: {agent.search_knowledge}\n"
                result += f"  Cite Knowledge: {agent.cite_knowledge}\n"
                result += f"  Read Chat History: {agent.read_chat_history}\n"
                result += f"  Show Tool Calls: {agent.show_tool_calls}\n"
                result += f"  Markdown Enabled: {agent.markdown_enabled}\n"
                result += f"  Default Reasoning: {agent.default_reasoning}\n"
                result += f"  Debug Mode: {agent.debug_mode}\n"
                
                return result
                
            except DjangoAgent.DoesNotExist:
                return f"Agent with ID '{agent_id}' not found."
            
        except Exception as e:
            logger.error(f"Error getting agent details: {e}", exc_info=True)
            return f"Error: Could not get agent details. Reason: {e}"