from typing import Optional
from apps.reggie.models import TokenUsage, ModelProvider
from apps.reggie.models import Agent as DjangoAgent
from apps.users.models import CustomUser
from apps.teams.models import Team
from django.contrib.auth import get_user_model
from typing import Dict, List, Optional, Union

User = get_user_model()

def create_token_usage_record(
    user: Optional[CustomUser],
    session_id: str,
    agent_name: str,
    model_provider: str,
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
):
    """
    Helper function to create a TokenUsage record.
    """
    team = None
    if user and hasattr(user, "team"):
        team = user.team

    TokenUsage.objects.create(
        user=user,
        team=team,
        session_id=session_id,
        agent_name=agent_name,
        model_provider=model_provider,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=0.0, # TODO: Implement cost calculation
    )

def record_agent_token_usage(
    user: User,
    agent_id: str,
    metrics: Dict,
    session_id: Optional[str] = None,
) -> Optional[TokenUsage]:

    if not metrics:
        return None
    
    agent = DjangoAgent.objects.get(agent_id=agent_id)
    agent_name = agent.name
    if not agent_id:
        agent_name = ""    
    model = ModelProvider.objects.get(id = agent.model_id)
    
    input_tokens = metrics.get("input_tokens", 0)
    output_tokens = metrics.get("output_tokens", 0)
    total_tokens = metrics.get("total_tokens", 0)

    if isinstance(input_tokens, list):
        prompt_tokens = sum(input_tokens)
    else:
        prompt_tokens = input_tokens or 0
    
    if isinstance(output_tokens, list):
        completion_tokens = sum(output_tokens)
    else:
        completion_tokens = output_tokens or 0
    
    if isinstance(total_tokens, list):
        total_tokens = sum(total_tokens)
    elif not total_tokens:
        total_tokens = prompt_tokens + completion_tokens

    return create_token_usage_record(
        user=user,
        # operation_type="chat",
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        total_tokens=total_tokens,
        model_provider=model.provider,
        model_name=model.model_name,
        session_id=session_id,
        agent_name=agent_name,
    )
