import contextlib
import logging
import time
import os

from agno.agent import Agent
from agno.workflow import Condition, Loop, Parallel, Router, Step, Steps, Workflow
from agno.workflow.types import StepInput, StepOutput, WorkflowExecutionInput
from agno.db.postgres.postgres import PostgresDb
from apps.opie.models import Agent as DjangoAgent
from apps.opie.models import Workflow as DjangoWorkflow
from apps.opie.models import Tool as DjangoTool

from django.conf import settings
from django.core.cache import cache

from apps.opie.agents.agent_builder import AgentBuilder

logger = logging.getLogger(__name__)


# Tool identifier to tool class mapping
TOOL_CLASS_MAPPING = {
    'file_reader': 'apps.opie.agents.tools.filereader.FileReaderTools',
    'google_search': 'agno.tools.googlesearch.GoogleSearchTools',
    'website_scraper': 'apps.opie.agents.tools.selenium_tools.WebsitePageScraperTools',
    'coingecko': 'apps.opie.agents.tools.coingecko.CoinGeckoTools',
    'blockscout': 'apps.opie.agents.tools.blockscout.BlockscoutTools',
    'jules_api': 'apps.opie.agents.tools.jules_api.JulesApiTools',
    'reasoning': 'agno.tools.reasoning.ReasoningTools',
    'file_generation': 'apps.opie.agents.tools.file_generation.FileGenerationTools',
    'jira': 'apps.opie.agents.tools.jira.JiraTools',
    'gmail': 'apps.opie.agents.tools.gmail.GmailTools',
    'google_calendar': 'apps.opie.agents.tools.calendar.GoogleCalendarTools',
    'sharepoint': 'apps.opie.agents.tools.sharepoint.SharePointTools',
    'monday': 'apps.opie.agents.tools.monday.MondayTools',
    'confluence': 'apps.opie.agents.tools.confluence.ConfluenceTools',
}


class WorkflowBuilder:
    def __init__(
        self,
        agent_ids: list[str],
        tool_ids: list[int],
        user,
        session_id: str,
        workflow_id: str = None
    ):
        """
        Initialize WorkflowBuilder with agent IDs and tool IDs.

        Args:
            agent_ids: List of agent IDs (agent_id strings)
            tool_ids: List of tool IDs (Tool model primary keys)
            user: Django user instance
            session_id: Session ID for the workflow
            workflow_id: Optional workflow ID to load workflow metadata
        """
        self.agent_ids = agent_ids
        self.tool_ids = tool_ids
        self.user = user
        self.session_id = session_id
        self.workflow_id = workflow_id
        self.django_workflow = self._get_django_workflow() if workflow_id else None

    def _get_django_workflow(self) -> DjangoWorkflow:
        """Retrieve the Django workflow by workflow_id"""
        return DjangoWorkflow.objects.get(id=self.workflow_id)

    def _load_tool_class(self, tool_identifier: str, tool_config: dict = None):
        """Dynamically load and instantiate a tool class"""
        import importlib

        if tool_identifier not in TOOL_CLASS_MAPPING:
            logger.warning(f"Tool identifier '{tool_identifier}' not found in mapping")
            return None

        tool_path = TOOL_CLASS_MAPPING[tool_identifier]
        module_path, class_name = tool_path.rsplit('.', 1)

        try:
            module = importlib.import_module(module_path)
            tool_class = getattr(module, class_name)

            # Instantiate tool with config if provided
            if tool_config:
                return tool_class(**tool_config)
            else:
                # Some tools need specific initialization
                if tool_identifier == 'file_generation':
                    return tool_class(
                        output_directory=settings.MEDIA_ROOT,
                        user_uuid=str(self.user.id) if self.user else None
                    )
                elif tool_identifier == 'reasoning':
                    return tool_class(add_instructions=True)
                else:
                    return tool_class()

        except Exception as e:
            logger.error(f"Error loading tool '{tool_identifier}': {e}")
            return None

    def _build_tools_from_definition(self) -> list:
        """Build tool instances from tool IDs"""
        tools = []

        for tool_id in self.tool_ids:
            try:
                # Get the Django tool
                django_tool = DjangoTool.objects.get(id=tool_id)

                if not django_tool.is_enabled:
                    logger.warning(f"Tool '{django_tool.name}' is disabled, skipping")
                    continue

                # Load the tool class
                tool_instance = self._load_tool_class(
                    django_tool.tool_identifier,
                    tool_config=django_tool.required_fields
                )

                if tool_instance:
                    tools.append(tool_instance)
                    logger.debug(f"Successfully loaded tool: {django_tool.name}")

            except DjangoTool.DoesNotExist:
                logger.error(f"Tool with ID {tool_id} not found")
            except Exception as e:
                logger.error(f"Error loading tool {tool_id}: {e}")

        return tools

    def _build_agents_from_definition(self) -> list[Agent]:
        """Build Agno agents from agent IDs"""
        agents = []

        for agent_id in self.agent_ids:
            try:
                # Get the Django agent
                django_agent = DjangoAgent.objects.get(agent_id=agent_id)

                # Build the Agno agent using AgentBuilder
                agent_builder = AgentBuilder(
                    agent_id=agent_id,
                    user=self.user,
                    session_id=self.session_id
                )
                agent = agent_builder.build()
                agents.append(agent)

                logger.debug(f"Successfully built agent: {agent.name}")
            except DjangoAgent.DoesNotExist:
                logger.error(f"Agent with agent_id {agent_id} not found")
            except Exception as e:
                logger.error(f"Error building agent {agent_id}: {e}")

        return agents

    def _create_workflow_execution_function(self, agents: list[Agent], tools: list, execution_mode: str = "sequential"):
        """Create the workflow execution function dynamically"""
        async def workflow_execution(execution_input: WorkflowExecutionInput) -> str:
            """Execute the workflow with the configured agents"""
            message: str = execution_input.input
            results = []

            workflow_name = self.django_workflow.name if self.django_workflow else "Agent Workflow"
            logger.info(f"🚀 Starting workflow: {workflow_name}")
            logger.info(f"📝 Input message: {message}")
            logger.info(f"🔧 Available tools: {[type(t).__name__ for t in tools]}")

            if execution_mode == "sequential":
                # Execute agents one after another
                for i, agent in enumerate(agents, 1):
                    logger.info(f"🔄 Executing agent {i}/{len(agents)}: {agent.name}")

                    # Use previous result as input if available
                    agent_input = message if i == 1 else results[-1]

                    result = await agent.arun(agent_input)
                    results.append(result.content)

                    logger.info(f"✅ Agent {agent.name} completed")

            elif execution_mode == "parallel":
                # Execute agents in parallel
                import asyncio
                logger.info(f"⚡ Executing {len(agents)} agents in parallel")

                tasks = [agent.arun(message) for agent in agents]
                parallel_results = await asyncio.gather(*tasks)
                results = [r.content for r in parallel_results]

                logger.info(f"✅ All agents completed")

            # Combine results
            final_result = "\n\n".join([
                f"## {agents[i].name} Result:\n{result}"
                for i, result in enumerate(results)
            ])

            logger.info(f"🎉 Workflow {workflow_name} completed successfully")

            return final_result

        return workflow_execution

    def build(self, execution_mode: str = "sequential", workflow_name: str = None, workflow_description: str = None) -> Workflow:
        """
        Build the Agno workflow from agent IDs and tool IDs.

        Args:
            execution_mode: "sequential" or "parallel" execution mode
            workflow_name: Optional workflow name (defaults to workflow model name or "Agent Workflow")
            workflow_description: Optional workflow description

        Returns:
            Configured Agno Workflow instance
        """
        t0 = time.time()
        logger.info(
            f"[WorkflowBuilder] Starting build: "
            f"agents={len(self.agent_ids)}, tools={len(self.tool_ids)}, "
            f"user_id={self.user.id}, session_id={self.session_id}"
        )

        # Build agents from agent IDs
        agents = self._build_agents_from_definition()

        if not agents:
            raise ValueError(f"No agents could be built from agent_ids: {self.agent_ids}")

        logger.info(f"[WorkflowBuilder] Built {len(agents)} agents")

        # Build tools from tool IDs
        tools = self._build_tools_from_definition()
        logger.info(f"[WorkflowBuilder] Loaded {len(tools)} tools")

        # Create workflow execution function
        execution_function = self._create_workflow_execution_function(agents, tools, execution_mode)

        # Get or create PostgresDb instance
        from apps.opie.agents.agent_builder import CACHED_DB, get_db_url

        if CACHED_DB is None:
            db = PostgresDb(db_url=get_db_url())
        else:
            db = CACHED_DB

        # Determine workflow name and description
        if workflow_name is None:
            workflow_name = self.django_workflow.name if self.django_workflow else "Agent Workflow"

        if workflow_description is None:
            workflow_description = self.django_workflow.description if self.django_workflow else f"Workflow with {len(agents)} agents"

        # Build the Agno workflow
        workflow = Workflow(
            name=workflow_name,
            description=workflow_description,
            db=db,
            steps=execution_function,
            session_state={},  # Initialize empty workflow session state
        )

        logger.info(f"[WorkflowBuilder] Build completed in {time.time() - t0:.2f}s")
        return workflow