import asyncio  # Added this import
import json
import logging
import time
import urllib.parse
from typing import Optional

import redis.asyncio as redis
from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication

# cloudpickle can be useful for serializing complex Python objects (e.g., functions, closures) for caching in Redis or for AI streaming responses/distributed processing
# try:
#     import cloudpickle  # type: ignore
# except ModuleNotFoundError:
#     pass
from apps.reggie.agents.agent_builder import AgentBuilder
from apps.reggie.models import ChatSession, EphemeralFile  # Added this import
from apps.reggie.utils.session_title import TITLE_MANAGER  # Added this import
from apps.reggie.agents.tools.filereader import FileReaderTools

logger = logging.getLogger(__name__)


# === Redis client for caching ===
REDIS_URL = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
try:
    redis_client: "redis.Redis" = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
except Exception as e:
    logger.warning(f"Failed to create Redis client: {e}")
    redis_client = None


def safe_json_serialize(obj):
    """
    Safely serialize an object to JSON, handling non-serializable types.
    """

    def _serialize_helper(item):
        if isinstance(item, (str, int, float, bool, type(None))):
            return item
        elif isinstance(item, (list, tuple)):
            return [_serialize_helper(x) for x in item]
        elif isinstance(item, dict):
            return {str(k): _serialize_helper(v) for k, v in item.items()}
        elif hasattr(item, "__dict__"):
            # Try to convert object to dict
            try:
                if hasattr(item, "to_dict"):
                    return _serialize_helper(item.to_dict())
                elif hasattr(item, "dict"):
                    return _serialize_helper(item.dict())
                else:
                    return _serialize_helper(item.__dict__)
            except Exception:
                return str(item)
        else:
            return str(item)

    try:
        serialized = _serialize_helper(obj)
        return json.dumps(serialized, ensure_ascii=False)
    except Exception as e:
        logger.error(f"JSON serialization failed: {e}")
        # Fallback: convert to string and escape
        return json.dumps({"error": "Serialization failed", "content": str(obj)[:1000]})


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

            # Initialize agno_files as empty list by default
            # agno_files = []
            file_texts = []

            # Only process files if we have a session_id
            if session_id:

                @database_sync_to_async
                def get_ephemeral_files():
                    return list(EphemeralFile.objects.filter(session_id=session_id).only("file", "mime_type", "name"))

                ephemeral_files = await get_ephemeral_files()

                # Process files asynchronously if we have any
                if ephemeral_files:
                    reader_tool = FileReaderTools()
                    extracted_texts = []
                    for ephemeral_file in ephemeral_files:
                        file_type = getattr(ephemeral_file, 'mime_type', None) or None
                        file_name = getattr(ephemeral_file, 'name', None) or None
                        with ephemeral_file.file.open('rb') as f:
                            file_bytes = f.read()
                        # Extract text using the tool, always pass file_type and file_name
                        text = reader_tool.read_file(content=file_bytes, file_type=file_type, file_name=file_name)
                        extracted_texts.append(f"\n--- File: {ephemeral_file.name} ({file_type}) ---\n{text}")

                    # Combine all extracted texts into the message content
                    if message:
                        message += "\n\n" + "\n\n".join(extracted_texts)
                    else:
                        message = "\n\n".join(extracted_texts)

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
            await self.stream_agent_response(agent_id, message, session_id, reasoning, file_texts)

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

    async def stream_agent_response(
        self, agent_id, message, session_id, reasoning: Optional[bool] = None, files: Optional[list] = None
    ):
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
            # logger.debug("Files: ", files)
            # print(files)
            # print(f"[DEBUG] Agent build time: {build_time:.2f}s")
            # Send agent build time debug message
            await self.send_body(
                f"data: {json.dumps({'debug': f'Agent build time: {build_time:.2f}s'})}\n\n".encode("utf-8"),
                more_body=True,
            )

            run_start = time.time()
            # print("[DEBUG] Starting agent.run")
            # import pprint
            # for f in files:
            #     print("📦 Verifying file passed to agent.run:")
            #     pprint.pprint(vars(f))

            #     # Hard fail if 'external' is missing
            #     assert hasattr(f, "external"), "❌ Missing 'external' field in AgnoFile"
            #     assert isinstance(f.external, dict), "❌ 'external' must be a dict"
            #     assert "data" in f.external, "❌ 'external' must include 'data'"
            #     print("✅ File structure is valid for GPT-4o")
            #
            # Do not add any file dicts to the 'files' field for the agent

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
                    if asyncio.iscoroutine(chat_title):
                        chat_title = await chat_title
                    if not chat_title or len(chat_title.strip()) < 6:
                        chat_title = TITLE_MANAGER._fallback_title(message)
                    logger.debug(
                        f"Attempting to serialize (ChatTitle event): {{'event': 'ChatTitle', 'title': {chat_title!r}}}"
                    )
                    chat_title_data = {"event": "ChatTitle", "title": chat_title}
                    chat_title_json = safe_json_serialize(chat_title_data)
                    await self.send_body(
                        f"data: {chat_title_json}\n\n".encode("utf-8"),
                        more_body=True,
                    )
                    await database_sync_to_async(ChatSession.objects.filter(id=session_id).update)(title=chat_title)
                    title_sent = True

                if chunk_count % 10 == 0:
                    logger.debug(f"[Agent:{agent_id}] {chunk_count} chunks processed")

                # Extract extra_data if present, but do not send it in every chunk
                extra_data = None
                if hasattr(chunk, "to_dict"):
                    event_data = chunk.to_dict()
                    if "extra_data" in event_data:
                        extra_data = event_data.pop("extra_data")
                elif hasattr(chunk, "dict"):
                    event_data = chunk.dict()
                    if "extra_data" in event_data:
                        extra_data = event_data.pop("extra_data")
                else:
                    event_data = str(chunk)

                # Aggregation logic
                is_simple_text_chunk = (
                    isinstance(event_data, dict)
                    and event_data.get("content_type") == "str"
                    and set(event_data.keys()) <= {"content", "content_type", "event"}
                )
                if is_simple_text_chunk:
                    chunk_text = event_data.get("content", "")
                    content_buffer += chunk_text
                    full_content += chunk_text
                    if len(content_buffer) >= 200 or content_buffer.endswith((".", "?", "!", "\n")):
                        flush_data = {
                            **event_data,
                            "content": content_buffer,
                        }
                        logger.debug(f"Attempting to serialize (string buffer flush): {flush_data!r}")
                        json_output = safe_json_serialize(flush_data)
                        await self.send_body(
                            f"data: {json_output}\n\n".encode("utf-8"),
                            more_body=True,
                        )
                        content_buffer = ""
                else:
                    if content_buffer:
                        flush_data = {
                            "content": content_buffer,
                            "content_type": "str",
                            "event": "RunResponse",
                        }
                        await self.send_body(
                            f"data: {safe_json_serialize(flush_data)}\n\n".encode("utf-8"),
                            more_body=True,
                        )
                        content_buffer = ""
                    logger.debug(f"Attempting to serialize (direct event_data): {event_data!r}")
                    json_output = safe_json_serialize(event_data)
                    await self.send_body(
                        f"data: {json_output}\n\n".encode("utf-8"),
                        more_body=True,
                    )

                # Save the last extra_data found (if any) for sending at the end
                # Only update last_extra_data if extra_data is non-empty and relevant
                if extra_data:
                    if (isinstance(extra_data, dict) and extra_data) or (isinstance(extra_data, list) and extra_data):
                        last_extra_data = extra_data

            # flush any remaining buffered content before finishing
            if content_buffer:
                full_content += content_buffer
                flush_data = {
                    "content": content_buffer,
                    "content_type": "str",
                    "event": "RunResponse",
                }
                await self.send_body(
                    f"data: {safe_json_serialize(flush_data)}\n\n".encode("utf-8"),
                    more_body=True,
                )
                content_buffer = ""

            # Send extra_data as a separate event at the end if it was found and is non-empty
            # if "last_extra_data" in locals() and last_extra_data:
            #     # Only send if last_extra_data is not empty (not None, not empty list/dict)
            #     if (isinstance(last_extra_data, dict) and last_extra_data) or (
            #         isinstance(last_extra_data, list) and last_extra_data
            #     ):
            #         references_event = {"event": "References", "extra_data": last_extra_data}
            #         await self.send_body(
            #             f"data: {safe_json_serialize(references_event)}\n\n".encode("utf-8"),
            #             more_body=True,
            #         )

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
