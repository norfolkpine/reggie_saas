"""Utility for AI-generated chat session titles."""

import logging
import time

import redis.asyncio as redis
from django.conf import settings

from agno.agent import Agent
from agno.models.openai import OpenAIChat

logger = logging.getLogger(__name__)

# === Redis client (independent of consumers) ===
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client: "redis.Redis" = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
except Exception as e:
    logger.warning(f"[session_title] Failed to create Redis client: {e}")
    redis_client = None


class AISessionTitleManager:
    """Generate and cache concise AI-generated titles for chat sessions."""

    CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days

    def __init__(self, model=None):
        self.model = model or OpenAIChat(id="gpt-4o-mini")
        self._memory_cache: dict[str, str] = {}

    # ---------------------------------------------------------------------
    # Redis helpers
    # ---------------------------------------------------------------------
    def _redis_get(self, session_id: str) -> str | None:
        if redis_client is None:
            return None
        try:
            return redis_client.get(f"chat_title:{session_id}")
        except Exception as e:
            logger.debug(f"[session_title] Redis get error: {e}")
            return None

    def _redis_set(self, session_id: str, title: str) -> None:
        if redis_client is None:
            return
        try:
            redis_client.setex(f"chat_title:{session_id}", self.CACHE_TTL_SECONDS, title)
        except Exception as e:
            logger.debug(f"[session_title] Redis set error: {e}")

    # ---------------------------------------------------------------------
    # Title generation
    # ---------------------------------------------------------------------
    def _generate_ai_title(self, message: str) -> str:
        """Call the LLM to create a concise title."""
        title_agent = Agent(
            model=self.model,
            instructions=(
                "Create a short, descriptive title (3-6 words) for a chat session "
                "based on the user's first message. Ensure it is atleast 5 characters and a meaningful e.g. Question: What is the capital of France? Session title would become Capital of France, NOT what is the capital Return ONLY the title."
            ),
        )
        try:
            start = time.perf_counter()
            response = title_agent.run(f"Create a title for this message: {message}")
            elapsed = time.perf_counter() - start
            logger.debug(f"[session_title] LLM title generation took {elapsed:.2f}s")
            title = response.content.strip().strip("\"").strip("'")
            return title or self._fallback_title(message)
        except Exception as e:
            logger.warning(f"[session_title] LLM title generation failed: {e}")
            return self._fallback_title(message)

    @staticmethod
    def _fallback_title(message: str) -> str:
        words = message.split()[:4]
        return " ".join(words).capitalize() or "New Session"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_or_create_title(self, session_id: str, first_message: str) -> str:
        # In-process cache
        if session_id in self._memory_cache:
            return self._memory_cache[session_id]

        # Redis cache
        cached = self._redis_get(session_id)
        if cached:
            self._memory_cache[session_id] = cached
            return cached

        # Generate new title
        title = self._generate_ai_title(first_message)

        # Persist caches
        self._memory_cache[session_id] = title
        self._redis_set(session_id, title)
        return title


# Shared instance for easy import
TITLE_MANAGER = AISessionTitleManager()
