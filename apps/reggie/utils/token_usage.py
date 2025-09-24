from typing import Optional
from apps.reggie.models import TokenUsage, Team
from apps.users.models import CustomUser

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
