# apps/reggie/utils/agent_cache.py

import hashlib
from django.core.cache import cache
from apps.reggie.agents.agent_builder import AgentBuilder


def get_cache_key(agent_id: str, user_id: int, session_id: str) -> str:
    base = f"{agent_id}:{user_id}:{session_id}"
    return "agent_ready:" + hashlib.sha256(base.encode()).hexdigest()


def cached_agent(agent_id: str, user, session_id: str, ttl: int = 1800):
    """
    Avoid redundant rebuilds by caching a readiness flag in Redis.
    Agent is rebuilt fresh from DB each time but avoids repeat work like validation.
    """
    key = get_cache_key(agent_id, user.id, session_id)
    already_initialized = cache.get(key)

    builder = AgentBuilder(agent_id=agent_id, user=user, session_id=session_id)
    agent = builder.build()

    # Optional: skip heavy features
    agent.read_chat_history = False
    agent.num_history_responses = 0

    if not already_initialized:
        # You could also preload some memory or knowledge here
        cache.set(key, True, timeout=ttl)

    return agent
