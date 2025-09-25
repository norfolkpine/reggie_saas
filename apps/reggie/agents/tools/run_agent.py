import logging
from pydantic import BaseModel, Field
from agno.tools.base import BaseTool
from ..agent_builder import AgentBuilder

logger = logging.getLogger(__name__)


class RunAgentToolInput(BaseModel):
    agent_id: str = Field(..., description="The ID of the agent to run.")
    input: str = Field(..., description="The input prompt or query for the agent.")


class RunAgentTool(BaseTool):
    """A tool to run another agent by its ID."""

    name: str = "run_agent_by_id"
    description: str = "Executes another AI agent with a specific ID and returns its response. Use this to delegate tasks to specialized agents as part of a workflow."
    args_schema = RunAgentToolInput

    def __init__(self, user, session_id: str):
        super().__init__()
        self.user = user
        self.session_id = session_id

    def _run(self, agent_id: str, input: str) -> str:
        """Runs the specified agent and returns its output."""
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