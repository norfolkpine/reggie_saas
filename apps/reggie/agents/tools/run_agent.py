import logging
from pydantic import BaseModel, Field
from agno.tools import Toolkit
from agno.utils.log import logger
from ..agent_builder import AgentBuilder


class RunAgentToolInput(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent to run.")
    input: str = Field(..., description="The input prompt or query for the agent.")


class RunAgentTool(Toolkit):
    """A tool to run another agent by its ID."""

    def __init__(self, user, session_id: str):
        self.user = user
        self.session_id = session_id
        super().__init__(name="run_agent_tools")
        
        # Register the method as an Agno tool
        self.register(self.run_agent_by_id)

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