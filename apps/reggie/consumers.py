import json
import logging
import time
import urllib.parse
from typing import Optional

try:
    import cloudpickle  # type: ignore
except ModuleNotFoundError:
    pass

import asyncio  # Added this import

import redis.asyncio as redis
from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.reggie.agents.agent_builder import AgentBuilder
from apps.reggie.models import ChatSession, EphemeralFile  # Added this import
from apps.reggie.utils.session_title import TITLE_MANAGER  # Added this import
from agno.media import File as AgnoFile  # Added this import

logger = logging.getLogger(__name__)


# === Redis client for caching ===
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client: "redis.Redis" = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
except Exception as e:
    logger.warning(f"Failed to create Redis client: {e}")
    redis_client = None


class StreamAgentConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        # Allow CORS preflight without authentication
        if self.scope.get("method") == "OPTIONS":
            await self.send_headers(
                headers=[
                    (b"Access-Control-Allow-Origin", b"*"),
                    (b"Access-Control-Allow-Methods", b"POST, OPTIONS"),
                    (b"Access-Control-Allow-Headers", b"authorization, content-type"),
                ],
                status=200,
            )
            await self.send_body(b"", more_body=False)
            return

        if not await self.authenticate_user():
            await self.send_headers(
                headers=[(b"Content-Type", b"application/json")],
                status=401,
            )
            await self.send_body(b'{"error": "Authentication required"}')
            return

        try:
            request_data = self.parse_body(body)
            agent_id = request_data.get("agent_id")
            message = request_data.get("message")
            session_id = request_data.get("session_id")
            # Optional flag to enable chain-of-thought reasoning
            reasoning = bool(request_data["reasoning"]) if "reasoning" in request_data else None

            if not all([agent_id, message, session_id]):
                await self.send_headers(
                    headers=[(b"Content-Type", b"application/json")],
                    status=400,
                )
                await self.send_body(b'{"error": "Missing required parameters"}')
                return

            # Retrieve associated ephemeral files
            ephemeral_files = await database_sync_to_async(EphemeralFile.objects.filter)(session_id=session_id)
            agno_files = []

            for ephemeral_file in ephemeral_files:
                with ephemeral_file.file.open("rb") as f:
                    agno_file = AgnoFile(
                        content=f.read(),
                        mime_type=ephemeral_file.mime_type
                    )
                    agno_files.append(agno_file)

            await self.send_headers(
                headers=[
                    (b"Content-Type", b"text/event-stream"),
                    (b"Cache-Control", b"no-cache"),
                    (b"Connection", b"keep-alive"),
                    (b"Access-Control-Allow-Origin", b"*"),
                ],
                status=200,
            )

            # Pass files to the agent
            await self.stream_agent_response(agent_id, message, session_id, reasoning, agno_files)

        except Exception as e:
            logger.exception("Unexpected error in handle()")
            try:
                await self.send_body(
                    f"data: {json.dumps({'error': str(e)})}\n\n".encode("utf-8"),
                    more_body=True,
                )
            except RuntimeError:
                logger.warning("Client disconnected during error message")

    def parse_body(self, body):
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            form_data = urllib.parse.parse_qs(body.decode("utf-8"))
            return {k: v[0] for k, v in form_data.items()}

    async def authenticate_user(self):
        try:
            headers = dict(self.scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8")
            if not auth_header:
                self.scope["user"] = AnonymousUser()
                return False

            jwt_auth = JWTAuthentication()
            token = await database_sync_to_async(jwt_auth.get_validated_token)(auth_header.split(" ")[1])
            user = await database_sync_to_async(jwt_auth.get_user)(token)

            self.scope["user"] = user if user and user.is_authenticated else AnonymousUser()
            return user.is_authenticated
        except Exception as e:
            logger.exception(f"Authentication error: {e}")
            self.scope["user"] = AnonymousUser()
            return False

    async def stream_agent_response(self, agent_id, message, session_id, reasoning: Optional[bool] = None, files: Optional[list] = None):
        """Stream an agent response, utilising Redis caching for identical requests."""
        # Build Agent (AgentBuilder internally caches DB-derived inputs)
        build_start = time.time()
        builder = await database_sync_to_async(AgentBuilder)(
            agent_id=agent_id, user=self.scope["user"], session_id=session_id
        )
        agent = await database_sync_to_async(builder.build)(enable_reasoning=reasoning)
        build_time = time.time() - build_start

        try:
            total_start = time.time()
            full_content = ""  # aggregate streamed text
            prompt_tokens = 0  # will be filled from metrics later
            logger.debug(f"[Agent:{agent_id}] Agent build time: {build_time:.2f}s")
            # print(f"[DEBUG] Agent build time: {build_time:.2f}s")
            # Send agent build time debug message
            await self.send_body(
                f"data: {json.dumps({'debug': f'Agent build time: {build_time:.2f}s'})}\n\n".encode("utf-8"),
                more_body=True,
            )

            run_start = time.time()
            # print("[DEBUG] Starting agent.run")
            gen = await database_sync_to_async(agent.run)(
                message,
                stream=True,
                # Removed show_full_reasoning to avoid incompatibility with KnowledgeBase.search
                stream_intermediate_steps=bool(reasoning),
                files=files,
            )
            agent_iterator = iter(gen)
            chunk_count = 0
            completion_tokens = 0  # will be overwritten with metrics later
            content_buffer = ""  # aggregate small token chunks
            title_sent = False  # ensure ChatTitle event emitted only once

            while True:
                chunk = await database_sync_to_async(lambda it: next(it, None))(agent_iterator)
                if chunk is None:
                    break

                chunk_count += 1

                # After first chunk, send ChatTitle once
                if not title_sent:
                    chat_title = TITLE_MANAGER.get_or_create_title(session_id, message)
                    # print(chat_title) # Consider if this debug print is needed
                    if asyncio.iscoroutine(chat_title):
                        chat_title = await chat_title
                    if not chat_title or len(chat_title.strip()) < 6:
                        chat_title = TITLE_MANAGER._fallback_title(message)

                    # Logging for the ChatTitle event data before serialization
                    logger.debug(
                        f"Attempting to serialize (ChatTitle event): {{'event': 'ChatTitle', 'title': {chat_title!r}}}"
                    )
                    try:
                        chat_title_json = json.dumps({"event": "ChatTitle", "title": chat_title})
                    except Exception as serialization_error:
                        logger.error(
                            f"JSON serialization error for ChatTitle event: {serialization_error}", exc_info=True
                        )
                        logger.error(f"Problematic ChatTitle data: {{'event': 'ChatTitle', 'title': {chat_title!r}}}")
                        # Optionally send an error or handle gracefully
                        # For now, let it proceed without sending the title if serialization fails, or re-raise
                        chat_title_json = json.dumps(
                            {"event": "ChatTitle", "title": "Error generating title"}
                        )  # Fallback title

                    await self.send_body(
                        f"data: {chat_title_json}\n\n".encode("utf-8"),
                        more_body=True,
                    )
                    # Persist title to DB (fire-and-forget)
                    await database_sync_to_async(ChatSession.objects.filter(id=session_id).update)(title=chat_title)
                    title_sent = True

                if chunk_count % 10 == 0:
                    logger.debug(f"[Agent:{agent_id}] {chunk_count} chunks processed")

                if hasattr(chunk, "to_dict"):
                    event_data = chunk.to_dict()
                    # print(f"[DEBUG] Sending event #{chunk_count}:", event_data)
                elif hasattr(chunk, "dict"):
                    # will print after assignment:
                    event_data = chunk.dict()
                    # print(f"[DEBUG] Sending event #{chunk_count}:", event_data)
                else:
                    event_data = str(chunk)
                    # print(f"[DEBUG] Sending event #{chunk_count}:", event_data)

                # Aggregation logic
                if isinstance(event_data, dict) and event_data.get("content_type") == "str":
                    chunk_text = event_data.get("content", "")
                    content_buffer += chunk_text
                    full_content += chunk_text
                    # flush when buffer exceeds 40 chars or ends with sentence punctuation
                    if len(content_buffer) >= 40 or content_buffer.endswith((".", "?", "!", "\n")):
                        flush_data = {
                            **event_data,  # event_data comes from the current chunk
                            "content": content_buffer,
                        }
                        # ADD LOGGING HERE:
                        logger.debug("Attempting to serialize (string buffer flush): {flush_data!r}")
                        # You might want to specifically log event_data if it's complex:
                        # logger.debug(f"event_data for string buffer flush: {{event_data!r}}")
                        try:
                            json_output = json.dumps(flush_data)
                        except Exception as serialization_error:
                            logger.error(
                                f"JSON serialization error for string buffer flush: {serialization_error}",
                                exc_info=True,
                            )
                            logger.error("Problematic flush_data (string buffer): {flush_data!r}")
                            # Decide how to handle this - maybe send an error chunk to frontend
                            # For now, re-raise to see it clearly, or send an error message
                            await self.send_body(
                                f"data: {json.dumps({'error': 'Serialization error during string buffer flush', 'detail': str(serialization_error)})}\n\n".encode(
                                    "utf-8"
                                ),
                                more_body=True,
                            )
                            raise  # Or handle more gracefully by not stopping the whole stream

                        await self.send_body(
                            f"data: {json_output}\n\n".encode("utf-8"),
                            more_body=True,
                        )
                        content_buffer = ""
                else:
                    # flush buffered content first
                    if content_buffer:
                        flush_data = {
                            "content": content_buffer,
                            "content_type": "str",
                            "event": "RunResponse",
                        }
                        await self.send_body(
                            f"data: {json.dumps(flush_data)}\n\n".encode("utf-8"),
                            more_body=True,
                        )
                        content_buffer = ""

                    # THIS IS LIKELY THE MORE PROBLEMATIC ONE if event_data itself is complex (e.g. contains tools)
                    # ADD LOGGING HERE:
                    logger.debug("Attempting to serialize (direct event_data): {event_data!r}")
                    try:
                        json_output = json.dumps(event_data)
                    except Exception as serialization_error:
                        logger.error(
                            f"JSON serialization error for direct event_data: {serialization_error}", exc_info=True
                        )
                        logger.error("Problematic event_data: {event_data!r}")
                        # Decide how to handle this
                        await self.send_body(
                            f"data: {json.dumps({'error': 'Serialization error for direct event_data', 'detail': str(serialization_error)})}\n\n".encode(
                                "utf-8"
                            ),
                            more_body=True,
                        )
                        raise  # Or handle more gracefully

                    await self.send_body(
                        f"data: {json_output}\n\n".encode("utf-8"),
                        more_body=True,
                    )
                # print(f"[DEBUG] Sent event #{chunk_count}:", event_data)

            # flush any remaining buffered content before finishing
            if content_buffer:
                full_content += content_buffer
                flush_data = {
                    "content": content_buffer,
                    "content_type": "str",
                    "event": "RunResponse",
                }
                await self.send_body(
                    f"data: {json.dumps(flush_data)}\n\n".encode("utf-8"),
                    more_body=True,
                )
                content_buffer = ""

            # After streaming all chunks, record timing metrics
            run_time = time.time() - run_start
            logger.debug(f"[Agent:{agent_id}] agent.run total time: {run_time:.2f}s")
            total_time = time.time() - total_start
            # Extract token usage metrics, if available; log internally but do not send to client
            if getattr(agent, "run_response", None) and getattr(agent.run_response, "metrics", None):
                metrics = agent.run_response.metrics
                prompt_tokens = metrics.get("input_tokens", 0)
                completion_tokens = metrics.get("output_tokens", 0)
                total_tokens = metrics.get("total_tokens", prompt_tokens + completion_tokens)
                # TODO: Persist token usage for billing, e.g.
                # TokenUsage.objects.create(
                #     user=self.scope["user"],
                #     agent_id=agent_id,
                #     session_id=session_id,
                #     prompt_tokens=prompt_tokens,
                #     completion_tokens=completion_tokens,
                #     total_tokens=total_tokens,
                #     timestamp=timezone.now(),
                # )
                logger.debug(
                    f"[Agent:{agent_id}] Token usage — prompt: {prompt_tokens}, completion: {completion_tokens}, total: {total_tokens}"
                )

                # ---- Send citations if available ----
                try:
                    if getattr(agent, "run_response", None) and getattr(agent.run_response, "citations", None):
                        citations_payload = {
                            "event": "Citations",
                            "citations": agent.run_response.citations,
                        }
                        await self.send_body(
                            f"data: {json.dumps(citations_payload)}\n\n".encode("utf-8"),
                            more_body=True,
                        )
                except RuntimeError:
                    logger.warning("Client disconnected before citations could be sent")
                except Exception as citation_err:
                    logger.exception(f"Error sending citations: {citation_err}")
                logger.debug(f"[Citations: {agent.run_response.citations})")

            logger.debug(f"[Agent:{agent_id}] Total stream time: {total_time:.2f}s")

        except Exception as e:
            logger.exception(f"[Agent:{agent_id}] error during streaming")
            try:
                await self.send_body(
                    f"data: {json.dumps({'error': str(e)})}\n\n".encode("utf-8"),
                    more_body=True,
                )
            except RuntimeError:
                logger.warning("Client disconnected before error could be sent")

        finally:
            try:
                await self.send_body(b"data: [DONE]\n\n", more_body=False)
            except RuntimeError:
                logger.info("[DONE] could not be sent — client disconnected before end of stream.")
