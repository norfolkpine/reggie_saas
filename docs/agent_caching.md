# Agent Caching Strategy in Production

## Overview

To achieve fast and robust agent instantiation in a Django/Channels production environment, we use a **hybrid caching strategy**:

1. **In-Memory Per-Process Cache**: For ultra-fast repeated requests handled by the same worker process (like Streamlit's session state).
2. **Redis Config Cache**: For cross-worker speedup, we cache only the agent’s expensive-to-compute, serializable configuration (not the full agent object) in Redis. This allows all workers to benefit from cached DB/model lookups.
3. **Safe Fallback**: If neither cache has the agent/config, the agent is built from scratch and then cached.

---

## Why Not Just Cache the Full Agent?

- Python objects like agents often contain non-serializable resources (DB connections, weakrefs, etc.), which cannot be pickled for Redis.
- Streamlit is fast because it keeps the agent in memory per user session, but this doesn't work across multiple Django/Channels workers.
- Caching only the serializable config/state in Redis avoids serialization errors and enables cross-worker cache hits.

---

## How It Works

1. **On each request:**
    - Check the in-memory cache for the agent object.
    - If not found, check Redis for the agent’s config/state (model, instructions, etc.).
    - If found in Redis, attempt to rebuild the agent using the cached config (if supported).
    - If not found in Redis, build the agent from scratch (DB/model lookups), then cache its config in Redis and the full object in memory.

2. **Cache Keys:**
    - Both caches are keyed by `(agent_id, user_id, session_id, reasoning)` to ensure correct agent context.

3. **Serialization:**
    - Only serializable agent config is stored in Redis (as JSON).
    - The full agent object is stored in memory (per process).

---

## Summary Table

| Approach                | Fast? | Cross-worker? | Handles Unpicklable? | Recommended for...         |
|-------------------------|-------|---------------|----------------------|----------------------------|
| Streamlit/session_state | Yes   | N/A           | Yes                  | Streamlit apps             |
| In-memory dict          | Yes   | No            | Yes                  | Django dev, low traffic    |
| Redis full agent        | No    | Yes           | No                   | Not recommended (errors)   |
| Redis config only       | Yes   | Yes           | Yes                  | Large scale, prod systems  |

---

## Implementation Notes

- The in-memory cache is a global Python dict in the consumer module.
- The Redis cache stores only the agent’s serializable config/state, not the full object.
- The `_rebuild_agent_from_config` method is a placeholder. If you want to reconstruct the agent from config (without DB hits), implement this using your agent/model factory logic. For now, it always falls back to a full build, which is safe and robust.
- Cache TTL is set to 1 hour by default.

---

## Example Usage (Pseudo-code)

```python
# In-memory cache
_AGENT_CACHE = {}

# Redis config cache (JSON)
async def get_or_build_agent(agent_id, user, session_id, reasoning):
    key = ... # based on agent_id, user_id, session_id, reasoning
    agent = _AGENT_CACHE.get(key)
    if agent:
        return agent
    if redis_client:
        cfg = await redis_client.get(cfg_key)
        if cfg:
            agent = rebuild_agent_from_config(cfg)
            if agent:
                _AGENT_CACHE[key] = agent
                return agent
    # Build from scratch
    agent = build_agent_from_db(...)
    _AGENT_CACHE[key] = agent
    if redis_client:
        await redis_client.set(cfg_key, serialize_agent_config(agent), ex=3600)
    return agent
```

---

## Benefits
- **Fastest possible response for hot requests** (in-memory cache).
- **Cross-worker speedup** for cold requests (Redis config cache).
- **No serialization errors** from unpicklable objects.
- **Safe fallback** to full build if needed.

---

## Further Optimization
- Implement a full `rebuild_agent_from_config` to avoid DB/model lookups entirely if all needed config is cached.
- Monitor cache hit/miss rates and tune TTL as needed.
