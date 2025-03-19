# DEV
from typing import List
from apps.models import Agent, AgentInstruction

def get_instructions(django_agent: Agent) -> List[str]:
    """Retrieve instructions for the agent from the database."""
    return list(AgentInstruction.objects.filter(agent=django_agent, is_enabled=True).values_list("instruction", flat=True))
