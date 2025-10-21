import asyncio  # Added this import
import json
import logging
import time
import urllib.parse

import redis.asyncio as redis
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from rest_framework import permissions

# --- Add stop-stream endpoint ---
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.opie.agents.agent_builder import AgentBuilder
from apps.opie.agents.tools.filereader import FileReaderTools
from apps.opie.models import ChatSession, EphemeralFile
from apps.teams.models import Team
from apps.opie.utils.session_title import TITLE_MANAGER
from apps.opie.utils.token_usage import record_agent_token_usage

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
        if isinstance(item, str | int | float | bool | type(None)):
            return item
        elif isinstance(item, list | tuple):
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
        request_start = time.time()
        # Allow CORS preflight without authentication
        if self.scope.get("method") == "OPTIONS":
            # Get CORS settings from Django settings and match request origin
            request_origin = None
            headers = dict(self.scope.get("headers", []))
            origin_header = headers.get(b"origin", b"").decode("utf-8")

            # Check if request origin is in allowed origins
            if origin_header and hasattr(settings, "CORS_ALLOWED_ORIGINS"):
                if origin_header in settings.CORS_ALLOWED_ORIGINS:
                    request_origin = origin_header
                else:
                    # Fallback to first allowed origin
                    request_origin = (
                        settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else "http://localhost:5173"
                    )
            else:
                # Fallback to first allowed origin
                request_origin = (
                    settings.CORS_ALLOWED_ORIGINS[0]
                    if hasattr(settings, "CORS_ALLOWED_ORIGINS") and settings.CORS_ALLOWED_ORIGINS
                    else "http://localhost:5173"
                )

            await self.send_headers(
                headers=[
                    (b"Access-Control-Allow-Origin", request_origin.encode()),
                    (b"Access-Control-Allow-Methods", b"POST, OPTIONS"),
                    (b"Access-Control-Allow-Headers", b"authorization, content-type, credentials, X-CSRFToken"),
                    (b"Access-Control-Allow-Credentials", b"true"),
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
            file_texts = []

            # Always define llm_input as the user's message by default
            llm_input = message if message else ""
            # Only process files if we have a session_id
            if session_id:

                @database_sync_to_async
                def get_ephemeral_files():
                    return list(EphemeralFile.objects.filter(session_id=session_id).only("file", "mime_type", "name"))

                t_files_start = time.time()
                ephemeral_files = await get_ephemeral_files()
                logger.info(
                    f"[TIMING] handle: get_ephemeral_files in {time.time() - t_files_start:.3f}s (total {time.time() - request_start:.3f}s)"
                )

                # Process files asynchronously if we have any
                if ephemeral_files:
                    reader_tool = FileReaderTools()
                    extracted_texts = []
                    attachments = []
                    for ephemeral_file in ephemeral_files:
                        file_type = getattr(ephemeral_file, "mime_type", None) or None
                        file_name = getattr(ephemeral_file, "name", None) or None
                        with ephemeral_file.file.open("rb") as f:
                            file_bytes = f.read()
                        # Extract text using the tool, always pass file_type and file_name
                        text = reader_tool.read_file(content=file_bytes, file_type=file_type, file_name=file_name)
                        extracted_texts.append(f"\n--- File: {ephemeral_file.name} ({file_type}) ---\n{text}")
                        # Build attachment metadata
                        attachments.append(
                            {
                                "uuid": str(ephemeral_file.uuid),
                                "name": ephemeral_file.name,
                                "url": ephemeral_file.file.url if hasattr(ephemeral_file.file, "url") else None,
                                "mime_type": ephemeral_file.mime_type,
                            }
                        )
                    # Prepend extracted file text to user message for LLM input
                    if extracted_texts:
                        llm_input = "\n\n".join(extracted_texts) + "\n\n" + (message if message else "")
                    if attachments:
                        if not hasattr(self, "_experimental_attachments"):
                            self._experimental_attachments = attachments
                        else:
                            self._experimental_attachments.extend(attachments)
            # Use llm_input for the LLM
            print("[LLM INPUT]", llm_input[:100])  # Print first 100 chars for debug

            # Get CORS settings from Django settings and match request origin
            request_origin = None
            headers = dict(self.scope.get("headers", []))
            origin_header = headers.get(b"origin", b"").decode("utf-8")

            # Check if request origin is in allowed origins
            if origin_header and hasattr(settings, "CORS_ALLOWED_ORIGINS"):
                if origin_header in settings.CORS_ALLOWED_ORIGINS:
                    request_origin = origin_header
                else:
                    # Fallback to first allowed origin
                    request_origin = (
                        settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else "http://localhost:5173"
                    )
            else:
                # Fallback to first allowed origin
                request_origin = (
                    settings.CORS_ALLOWED_ORIGINS[0]
                    if hasattr(settings, "CORS_ALLOWED_ORIGINS") and settings.CORS_ALLOWED_ORIGINS
                    else "http://localhost:5173"
                )

            await self.send_headers(
                headers=[
                    (b"Content-Type", b"text/event-stream"),
                    (b"Cache-Control", b"no-cache"),
                    (b"X-Accel-Buffering", b"no"),  # Disable nginx buffering (if behind nginx)
                    (b"CF-Cache-Status", b"BYPASS"),  # Cloudflare: bypass cache
                    (b"CF-Ray", b"streaming"),  # Cloudflare: mark as streaming
                    (b"Access-Control-Allow-Origin", request_origin.encode()),
                    (b"Access-Control-Allow-Credentials", b"true"),
                ],
                status=200,
            )
            # When constructing the user_msg dict for history, include only the user message
            user_msg = {
                "role": "user",
                "content": message if message else "",
                "content_for_history": message if message else "",
                "created_at": int(time.time()),
                "timestamp": int(time.time()),
            }
            self._user_msg_dict = user_msg
            await self.stream_agent_response(agent_id, llm_input, session_id, reasoning, file_texts)

        except Exception as e:
            logger.exception("Unexpected error in handle()")
            try:
                await self.send_body(
                    f"data: {json.dumps({'error': str(e)})}\n\n".encode(),
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
        """Authenticate user using Django's session middleware approach"""
        try:
            from django.contrib.auth.models import AnonymousUser
            from django.contrib.sessions.backends.db import SessionStore

            # Get session key from cookies
            headers = dict(self.scope.get("headers", []))
            cookie_header = headers.get(b"cookie", b"").decode("utf-8")

            print(f"Cookie header: {cookie_header}")

            if not cookie_header:
                print("No cookie header found")
                self.scope["user"] = AnonymousUser()
                return False

            # Extract session key
            import re

            session_match = re.search(r"bh_opie_sessionid=([^;]+)", cookie_header)
            if not session_match:
                print("No session cookie found")
                self.scope["user"] = AnonymousUser()
                return False

            session_key = session_match.group(1)
            print(f"Session key: {session_key}")

            # Create session store and get user ID from session
            @database_sync_to_async
            def get_user_from_session():
                session_store = SessionStore(session_key=session_key)

                if not session_store.exists(session_key):
                    print("Session does not exist")
                    return None

                # Get user ID from session
                user_id = session_store.get("_auth_user_id")
                if not user_id:
                    print("No user ID in session")
                    return None

                # Get user from database
                try:
                    from django.contrib.auth import get_user_model

                    User = get_user_model()
                    user = User.objects.get(id=user_id)
                    return user
                except User.DoesNotExist:
                    print(f"User not found for ID: {user_id}")
                    return None

            user = await get_user_from_session()

            if user and user.is_authenticated:
                self.scope["user"] = user
                print(f"Authenticated user: {user.email if hasattr(user, 'email') else user.id}")
                return True
            else:
                print("User not authenticated")
                self.scope["user"] = AnonymousUser()
                return False

        except Exception as e:
            print(f"Authentication error: {e}")
            import traceback

            traceback.print_exc()
            self.scope["user"] = AnonymousUser()
            return False

    async def stream_agent_response(
        self, agent_id, message, session_id, reasoning: bool | None = None, files: list | None = None
    ):
        """Stream an agent response, utilising Redis caching for identical requests. Supports interruption via stop flag in Redis."""
        # Build Agent (AgentBuilder internally caches DB-derived inputs)
        build_start = time.time()
        builder = await database_sync_to_async(AgentBuilder)(
            agent_id=agent_id, user=self.scope["user"], session_id=session_id
        )
        agent = await database_sync_to_async(builder.build)(enable_reasoning=reasoning)
        build_time = time.time() - build_start

        # --- Clear stop flag at the start of a new stream ---
        if redis_client:
            try:
                await redis_client.delete(f"stop_stream:{session_id}")
            except Exception as e:
                logger.warning(f"Could not clear stop flag for session {session_id}: {e}")

        try:
            total_start = time.time()
            full_content = ""  # aggregate streamed text
            logger.debug(f"[Agent:{agent_id}] Agent build time: {build_time:.2f}s")

            # Send agent build time debug message
            await self.send_body(
                f"data: {json.dumps({'debug': f'Agent build time: {build_time:.2f}s'})}\n\n".encode(),
                more_body=True,
            )

            run_start = time.time()
            print("[LLM INPUT]", message[:100])  # Print first 100 chars for debug
            
            stream_generator = await database_sync_to_async(agent.run)(
                message,
                stream=True,
                stream_intermediate_steps=True
            )
            
            agent_iterator = iter(stream_generator)
            chunk_count = 0
            content_buffer = ""  # aggregate small token chunks
            title_sent = False  # ensure ChatTitle event emitted only once

            # --- Track last non-empty extra_data ---
            last_extra_data = None

            # --- Streaming loop with stop flag check ---
            while True:
                # --- Check for stop flag in Redis ---
                if redis_client:
                    try:
                        stop_flag = await redis_client.get(f"stop_stream:{session_id}")
                        if stop_flag:
                            logger.info(
                                f"[Agent:{agent_id}] Stop flag detected for session {session_id}, interrupting stream."
                            )
                            break
                    except Exception as e:
                        logger.warning(f"Could not check stop flag for session {session_id}: {e}")

                chunk = await database_sync_to_async(lambda it: next(it, None))(agent_iterator)
                if chunk is None:
                    break

                chunk_count += 1

                if not title_sent:

                    chat_title = await database_sync_to_async(TITLE_MANAGER.get_or_create_title)(session_id, message)

                    if not chat_title or len(chat_title.strip()) < 6:
                        chat_title = await sync_to_async(TITLE_MANAGER._fallback_title)(message)
                    logger.debug(
                        f"Attempting to serialize (ChatTitle event): {{'event': 'ChatTitle', 'title': {chat_title!r}}}"
                    )
                    chat_title_data = {"event": "ChatTitle", "title": chat_title}
                    chat_title_json = safe_json_serialize(chat_title_data)
                    await self.send_body(
                        f"data: {chat_title_json}\n\n".encode(),
                        more_body=True,
                    )
                    await database_sync_to_async(ChatSession.objects.filter(id=session_id).update)(title=chat_title)
                    title_sent = True

                if chunk_count % 10 == 0:
                    logger.debug(f"[Agent:{agent_id}] {chunk_count} chunks processed")

                extra_data = None
                event_data = None
                
                try:
                    if hasattr(chunk, "to_dict"):
                        event_data = chunk.to_dict()
                        if "extra_data" in event_data:
                            extra_data = event_data.pop("extra_data")
                    elif hasattr(chunk, "dict"):
                        event_data = chunk.dict()
                        if "extra_data" in event_data:
                            extra_data = event_data.pop("extra_data")
                    elif hasattr(chunk, "__dict__"):
                        event_data = chunk.__dict__.copy()
                        if "extra_data" in event_data:
                            extra_data = event_data.pop("extra_data")
                    else:
                        # event_data = {"content": str(chunk), "content_type": "str", "event": "RunResponse"}
                        event_data = str(chunk)
                except Exception as e:
                    logger.warning(f"Error processing chunk: {e}")
                    event_data = {"content": str(chunk), "content_type": "str", "event": "RunResponse"}

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
                            f"data: {json_output}\n\n".encode(),
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
                            f"data: {safe_json_serialize(flush_data)}\n\n".encode(),
                            more_body=True,
                        )
                        content_buffer = ""
                    logger.debug(f"Attempting to serialize (direct event_data): {event_data!r}")
                    json_output = safe_json_serialize(event_data)
                    await self.send_body(
                        f"data: {json_output}\n\n".encode(),
                        more_body=True,
                    )

                if extra_data and (
                    (isinstance(extra_data, dict) and extra_data) or (isinstance(extra_data, list) and extra_data)
                ):
                    last_extra_data = extra_data

            if content_buffer:
                full_content += content_buffer
                flush_data = {
                    "content": content_buffer,
                    "content_type": "str",
                    "event": "RunResponse",
                }
                await self.send_body(
                    f"data: {safe_json_serialize(flush_data)}\n\n".encode(),
                    more_body=True,
                )
                content_buffer = ""

            if last_extra_data:
                references_event = {"event": "References", "extra_data": last_extra_data}
                await self.send_body(
                    f"data: {safe_json_serialize(references_event)}\n\n".encode(),
                    more_body=True,
                )

            run_time = time.time() - run_start
            logger.debug(f"[Agent:{agent_id}] agent.run total time: {run_time:.2f}s")
            total_time = time.time() - total_start
            
            try:

                last_run = agent.get_last_run_output()
                if last_run and last_run.messages:
                    last_assistant_message = next(
                        (msg for msg in reversed(last_run.messages) 
                        if msg.role == "assistant"), None
                    )
                    last_user_message = next(
                        (msg for msg in reversed(last_run.messages)
                        if msg.role == "user"), None
                    )
                    if last_assistant_message and last_assistant_message.metrics:
                        metrics_dict = last_assistant_message.metrics.to_dict()
                        assistant_message = last_assistant_message.content
                    if last_user_message:
                        user_message = last_user_message.content
                
                if hasattr(agent, 'last_run') and agent.last_run:
                    if hasattr(agent.last_run, 'metrics'):
                        metrics_dict = agent.last_run.metrics.to_dict()
                    if hasattr(agent.last_run, 'citations'):
                        citations = agent.last_run.citations
                
                elif hasattr(agent, '_last_run_output') and agent._last_run_output:
                    if hasattr(agent._last_run_output, 'metrics'):
                        metrics_dict = agent._last_run_output.metrics.to_dict()
                    if hasattr(agent._last_run_output, 'citations'):
                        citations = agent._last_run_output.citations

                if 'metrics_dict' in locals():
                    prompt_tokens = metrics_dict.get("input_tokens", 0) or metrics_dict.get("prompt_tokens", 0)
                    completion_tokens = metrics_dict.get("output_tokens", 0) or metrics_dict.get("completion_tokens", 0)
                    total_tokens = metrics_dict.get("total_tokens", prompt_tokens + completion_tokens)
                    
                    logger.debug(
                        f"[Agent:{agent_id}] Token usage — prompt: {prompt_tokens}, completion: {completion_tokens}, total: {total_tokens}"
                    )

                    # Record token usage
                    try:
                        await database_sync_to_async(record_agent_token_usage)(
                            user=self.scope["user"], 
                            agent_id=agent_id, 
                            metrics=metrics_dict,
                            session_id=session_id,
                            chat_name=chat_title,
                            user_msg=user_message,
                            assistant_msg=assistant_message,
                            request_id=f"{session_id}-{agent_id}-{int(time.time())}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to record token usage: {e}")
                else:
                    logger.debug(f"[Agent:{agent_id}] No metrics available after streaming")

                # Send citations if we found them
                if 'citations' in locals() and citations:
                    citations_payload = {
                        "event": "Citations",
                        "citations": citations,
                    }
                    await self.send_body(
                        f"data: {json.dumps(citations_payload)}\n\n".encode(),
                        more_body=True,
                    )
                    logger.debug(f"[Citations: {citations}]")
                else:
                    logger.debug(f"[Agent:{agent_id}] No citations available after streaming")
                    
            except Exception as e:
                logger.error(f"Error accessing metrics/citations after streaming: {e}")
                import traceback
                traceback.print_exc()

            logger.debug(f"[Agent:{agent_id}] Total stream time: {total_time:.2f}s")

        except Exception as e:
            logger.exception(f"[Agent:{agent_id}] error during streaming")
            try:
                await self.send_body(
                    f"data: {json.dumps({'error': str(e)})}\n\n".encode(),
                    more_body=True,
                )
            except RuntimeError:
                logger.warning("Client disconnected before error could be sent")

        finally:
            try:
                await self.send_body(b"data: [DONE]\n\n", more_body=False)
            except RuntimeError:
                logger.info("[DONE] could not be sent — client disconnected before end of stream.")


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def stop_stream(request):
    session_id = request.data.get("session_id")
    if not session_id:
        return Response({"error": "Missing session_id"}, status=400)
    if not redis_client:
        return Response({"error": "Redis unavailable"}, status=500)
    try:
        import redis as sync_redis
        sync_client = sync_redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        sync_client.set(f"stop_stream:{session_id}", "1", ex=60)  # auto-expire after 60s
        return Response({"status": "ok"})
    except Exception as e:
        return Response({"error": str(e)}, status=500)


class VaultIngestionConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles WebSocket connections for real-time vault ingestion progress.
    """
    async def connect(self):
        """
        Accepts the WebSocket connection and starts listening to the
        Redis Stream for the given task.
        """
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.stream_key = f"ingest:events:vault:{self.task_id}"
        self.last_id = '$'  # Start reading new events from the stream

        await self.accept()
        logger.info(f"WebSocket connected for vault ingestion task: {self.task_id}")

        # Start a background task to pump messages from Redis to the client
        self.pump_task = asyncio.create_task(self.pump_stream_events())

    async def disconnect(self, code):
        """
        Cleans up the background task when the client disconnects.
        """
        logger.info(f"WebSocket disconnected for vault ingestion task: {self.task_id}")
        if hasattr(self, 'pump_task'):
            self.pump_task.cancel()

    async def pump_stream_events(self):
        """
        Listens to a Redis Stream and forwards events to the WebSocket client.
        """
        try:
            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            while True:
                # Wait for new messages on the stream
                response = await r.xread({self.stream_key: self.last_id}, block=5000, count=10)
                if response:
                    for stream, events in response:
                        for event_id, data in events:
                            self.last_id = event_id
                            # The data from redis is already a dict of strings
                            # We can convert percent to a float if it exists
                            if 'percent' in data:
                                try:
                                    data['percent'] = float(data['percent'])
                                except (ValueError, TypeError):
                                    pass # Keep it as a string if conversion fails
                            await self.send_json(data)
                await asyncio.sleep(0.1) # Small sleep to prevent tight loop if stream is empty
        except asyncio.CancelledError:
            # This is expected when the client disconnects
            logger.info(f"Stream pump for task {self.task_id} was cancelled.")
        except Exception as e:
            logger.error(f"Error in Redis stream pump for task {self.task_id}: {e}", exc_info=True)
            # Optionally, send an error to the client
            try:
                await self.send_json({"error": "An internal error occurred while streaming progress."})
            except Exception:
                pass # Client may have disconnected
        finally:
            if 'r' in locals() and r:
                await r.close()