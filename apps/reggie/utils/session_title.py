"""Utility for AI-generated chat session titles."""

import logging
import time

import redis
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from django.conf import settings

from apps.reggie.utils.token_usage import create_token_usage_record

logger = logging.getLogger(__name__)

# === Redis client (independent of consumers) ===
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client = redis.Redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
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
    def _generate_ai_title(self, message: str, session_id: str) -> str:
        """Call the LLM to create a concise title."""
        title_agent = Agent(
            model=self.model,
            instructions=(
                "Create a concise, descriptive chat session title (3-6 words) based on the user's first message. Ensure the response mentions the topic. E.g. Country. If the message is just Hi, call it New Chat."
                "Avoid quotation marks and punctuation beyond normal words. Return ONLY the title text."
            ),
        )
        try:
            start = time.perf_counter()
            response = title_agent.run(f"Create a title for this message: {message}")
            if hasattr(response, "metrics"):
                metrics = response.metrics
                create_token_usage_record(
                    user=None,
                    session_id=session_id,
                    agent_name="Title Agent",
                    model_provider="openai",
                    model_name=self.model.id,
                    input_tokens=metrics.get("input_tokens", 0),
                    output_tokens=metrics.get("output_tokens", 0),
                    total_tokens=metrics.get("total_tokens", 0),
                )
            elapsed = time.perf_counter() - start
            logger.debug(f"[session_title] LLM title generation took {elapsed:.2f}s")
            logger.debug(f"[session_title] Raw LLM response: {response.content!r}")
            title = response.content.strip().strip('"').strip("'")
            logger.debug(f"[session_title] Parsed title: {title!r} (len={len(title)})")
            return title or self._fallback_title(message)
        except Exception as e:
            logger.warning(f"[session_title] LLM title generation failed: {e}")
            return self._fallback_title(message)

    @staticmethod
    def _fallback_title(message: str) -> str:
        # Build a fallback title of at least 6 characters using up to 6 words
        words = message.split()
        fallback = " ".join(words[:6]).capitalize()
        if len(fallback) < 6:
            extra = " ".join(words[6:8])
            fallback = f"{fallback} {extra}".strip()
        return fallback or "New Session"

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
        title = self._generate_ai_title(first_message, session_id)
        # if not title or len(title.strip()) < 6:
        #     logger.debug("[session_title] Title too short or empty, using fallback")
        #     title = self._fallback_title(first_message)
        logger.debug(f"[session_title] Final title for session {session_id}: {title!r}")

        # Persist caches
        self._memory_cache[session_id] = title
        self._redis_set(session_id, title)
        return title


# Shared instance for easy import
TITLE_MANAGER = AISessionTitleManager()
