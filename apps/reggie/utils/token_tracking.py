"""
Token usage tracking utilities for recording LLM usage across the system.
"""
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Union

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.teams.models import Team

from ..models import TokenUsage

User = get_user_model()
logger = logging.getLogger(__name__)


def record_token_usage(
    user: User,
    team: Team,
    operation_type: str = "chat",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: Optional[int] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    request_id: Optional[str] = None,
    cost_usd: Optional[Decimal] = None,
) -> TokenUsage:
    """
    Record token usage for billing and analytics.
    
    Args:
        user: User who generated the tokens
        team: Team that owns this usage
        operation_type: Type of operation (chat, embedding, rerank, tool, insights)
        prompt_tokens: Number of input/prompt tokens
        completion_tokens: Number of output/completion tokens
        total_tokens: Total tokens (auto-calculated if not provided)
        provider: LLM provider (e.g., openai, anthropic)
        model: Model name (e.g., gpt-4, claude-3)
        session_id: Session ID for grouping requests
        conversation_id: Conversation ID if applicable
        agent_id: Agent ID if applicable
        request_id: Unique request ID for idempotency
        cost_usd: Estimated cost in USD
        
    Returns:
        TokenUsage instance
    """
    try:
        with transaction.atomic():
            # Auto-calculate total tokens if not provided
            if total_tokens is None:
                total_tokens = prompt_tokens + completion_tokens
            
            # Check for existing record with same request_id (idempotency)
            if request_id:
                existing = TokenUsage.objects.filter(request_id=request_id).first()
                if existing:
                    logger.debug(f"Token usage already recorded for request_id: {request_id}")
                    return existing
            
            token_usage = TokenUsage.objects.create(
                user=user,
                team=team,
                operation_type=operation_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                provider=provider,
                model=model,
                session_id=session_id,
                conversation_id=conversation_id,
                agent_id=agent_id,
                request_id=request_id,
                cost_usd=cost_usd or Decimal("0.0"),
            )
            
            logger.debug(
                f"Recorded token usage: {user.email} - {operation_type} - {total_tokens} tokens"
            )
            return token_usage
            
    except Exception as e:
        logger.error(f"Failed to record token usage: {e}")
        # Don't raise the exception to avoid breaking the main flow
        # Return a dummy instance for compatibility
        return TokenUsage(
            user=user,
            team=team,
            operation_type=operation_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
        )


def record_agent_token_usage(
    user: User,
    team: Team,
    agent_id: str,
    metrics: Dict,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    request_id: Optional[str] = None,
    provider: str = "openai",
    model: str = "gpt-4",
) -> Optional[TokenUsage]:
    """
    Record token usage from agent metrics (AGNO framework).
    
    Args:
        user: User who generated the tokens
        team: Team that owns this usage
        agent_id: Agent ID
        metrics: Metrics dict from agent.run_response.metrics
        session_id: Session ID for grouping requests
        conversation_id: Conversation ID if applicable
        request_id: Unique request ID for idempotency
        provider: LLM provider
        model: Model name
        
    Returns:
        TokenUsage instance or None if no metrics
    """
    if not metrics:
        return None
    
    # Handle both single values and arrays (multiple model calls)
    input_tokens = metrics.get("input_tokens", 0)
    output_tokens = metrics.get("output_tokens", 0)
    total_tokens = metrics.get("total_tokens", 0)
    
    # If arrays, sum them up
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
    
    return record_token_usage(
        user=user,
        team=team,
        operation_type="chat",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        provider=provider,
        model=model,
        session_id=session_id,
        conversation_id=conversation_id,
        agent_id=agent_id,
        request_id=request_id,
    )


def record_embedding_token_usage(
    user: User,
    team: Team,
    tokens_used: int,
    provider: str = "openai",
    model: str = "text-embedding-3-small",
    request_id: Optional[str] = None,
) -> TokenUsage:
    """
    Record token usage for embedding operations.
    
    Args:
        user: User who generated the tokens
        team: Team that owns this usage
        tokens_used: Number of tokens used for embeddings
        provider: LLM provider
        model: Model name
        request_id: Unique request ID for idempotency
        
    Returns:
        TokenUsage instance
    """
    return record_token_usage(
        user=user,
        team=team,
        operation_type="embedding",
        prompt_tokens=tokens_used,
        completion_tokens=0,
        total_tokens=tokens_used,
        provider=provider,
        model=model,
        request_id=request_id,
    )


def get_user_token_usage_summary(
    user: User,
    team: Optional[Team] = None,
    days: int = 30,
) -> Dict:
    """
    Get token usage summary for a user.
    
    Args:
        user: User to get summary for
        team: Optional team filter
        days: Number of days to look back
        
    Returns:
        Dictionary with usage summary
    """
    from django.db.models import Sum, Count
    from django.utils import timezone
    
    queryset = TokenUsage.objects.filter(user=user)
    
    if team:
        queryset = queryset.filter(team=team)
    
    # Filter by date range
    start_date = timezone.now() - timezone.timedelta(days=days)
    queryset = queryset.filter(created_at__gte=start_date)
    
    summary = queryset.aggregate(
        total_tokens=Sum("total_tokens"),
        prompt_tokens=Sum("prompt_tokens"),
        completion_tokens=Sum("completion_tokens"),
        total_cost=Sum("cost_usd"),
        request_count=Count("id"),
    )
    
    return {
        "user": user.email,
        "team": team.name if team else None,
        "period_days": days,
        "total_tokens": summary["total_tokens"] or 0,
        "prompt_tokens": summary["prompt_tokens"] or 0,
        "completion_tokens": summary["completion_tokens"] or 0,
        "total_cost": float(summary["total_cost"] or 0),
        "request_count": summary["request_count"] or 0,
    }


def get_team_token_usage_summary(
    team: Team,
    days: int = 30,
) -> Dict:
    """
    Get token usage summary for a team.
    
    Args:
        team: Team to get summary for
        days: Number of days to look back
        
    Returns:
        Dictionary with usage summary
    """
    from django.db.models import Sum, Count
    from django.utils import timezone
    
    # Filter by date range
    start_date = timezone.now() - timezone.timedelta(days=days)
    queryset = TokenUsage.objects.filter(team=team, created_at__gte=start_date)
    
    summary = queryset.aggregate(
        total_tokens=Sum("total_tokens"),
        prompt_tokens=Sum("prompt_tokens"),
        completion_tokens=Sum("completion_tokens"),
        total_cost=Sum("cost_usd"),
        request_count=Count("id"),
        unique_users=Count("user", distinct=True),
    )
    
    return {
        "team": team.name,
        "period_days": days,
        "total_tokens": summary["total_tokens"] or 0,
        "prompt_tokens": summary["prompt_tokens"] or 0,
        "completion_tokens": summary["completion_tokens"] or 0,
        "total_cost": float(summary["total_cost"] or 0),
        "request_count": summary["request_count"] or 0,
        "unique_users": summary["unique_users"] or 0,
    }
