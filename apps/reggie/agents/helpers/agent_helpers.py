# helpers/agent_helpers.py

from typing import List
from apps.reggie.models import Agent, AgentInstruction

def get_agent_instructions(agent: Agent) -> List[str]:
    return list(
        AgentInstruction.objects.filter(agent=agent, is_enabled=True)
        .values_list("instruction", flat=True)
    )
