"""
Vault Consumer - Handles streaming responses for vault AI chat.
"""

import asyncio
import json
import logging
import time
import urllib.parse

import redis.asyncio as redis
from channels.db import database_sync_to_async
from channels.generic.http import AsyncHttpConsumer
from django.conf import settings

from apps.opie.agents.vault_agent import VaultAgentBuilder
from apps.opie.models import ChatSession, Project

logger = logging.getLogger(__name__)

# Redis client for caching (reuse from main consumers)
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
        return json.dumps({"error": "Serialization failed", "content": str(obj)[:1000]})


class VaultStreamConsumer(AsyncHttpConsumer):
    """Consumer for handling vault AI chat streaming."""

    async def handle(self, body):
        request_start = time.time()

        # Handle CORS preflight
        if self.scope.get("method") == "OPTIONS":
            await self.handle_cors_preflight()
            return

        # Authenticate user
        if not await self.authenticate_user():
            await self.send_headers(
                headers=[(b"Content-Type", b"application/json")],
                status=401,
            )
            await self.send_body(b'{"error": "Authentication required"}')
            return

        try:
            request_data = self.parse_body(body)
            project_id = request_data.get("project_id")
            folder_id = request_data.get("folder_id")
            file_ids = request_data.get("file_ids", [])
            message = request_data.get("message")
            session_id = request_data.get("session_id")
            reasoning = bool(request_data.get("reasoning", False))
            agent_id = request_data.get("agentId")

            if not all([project_id, message, session_id, agent_id]):
                await self.send_headers(
                    headers=[(b"Content-Type", b"application/json")],
                    status=400,
                )
                await self.send_body(b'{"error": "Missing required parameters"}')
                return

            # Verify user has access to the project
            @database_sync_to_async
            def check_project_access():
                try:
                    project = Project.objects.get(uuid=project_id)
                    # Check if user is owner or member
                    if project.owner == self.scope["user"]:
                        return True
                    if self.scope["user"] in project.members.all():
                        return True
                    # Check team access
                    if project.team:
                        from apps.teams.models import Membership
                        if Membership.objects.filter(user=self.scope["user"], team=project.team).exists():
                            return True
                    return False
                except Project.DoesNotExist:
                    return False

            if not await check_project_access():
                await self.send_headers(
                    headers=[(b"Content-Type", b"application/json")],
                    status=403,
                )
                await self.send_body(b'{"error": "Access denied to this project"}')
                return

            # Set up CORS headers for streaming
            request_origin = await self.get_request_origin()
            await self.send_headers(
                headers=[
                    (b"Content-Type", b"text/event-stream"),
                    (b"Cache-Control", b"no-cache"),
                    (b"Connection", b"keep-alive"),
                    (b"Access-Control-Allow-Origin", request_origin.encode()),
                    (b"Access-Control-Allow-Credentials", b"true"),
                ],
                status=200,
            )

            # Stream the vault agent response
            await self.stream_vault_response(
                project_id=project_id,
                folder_id=folder_id,
                file_ids=file_ids,
                message=message,
                agent_id=agent_id,
                session_id=session_id,
                reasoning=reasoning,
            )

        except Exception as e:
            logger.exception("Unexpected error in vault handle()")
            try:
                await self.send_body(
                    f"data: {json.dumps({'error': str(e)})}\n\n".encode(),
                    more_body=True,
                )
            except RuntimeError:
                logger.warning("Client disconnected during error message")

    def parse_body(self, body):
        """Parse the request body."""
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            form_data = urllib.parse.parse_qs(body.decode("utf-8"))
            return {k: v[0] for k, v in form_data.items()}

    async def handle_cors_preflight(self):
        """Handle CORS preflight requests."""
        request_origin = await self.get_request_origin()
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

    async def get_request_origin(self):
        """Get the request origin for CORS."""
        headers = dict(self.scope.get("headers", []))
        origin_header = headers.get(b"origin", b"").decode("utf-8")

        if origin_header and hasattr(settings, "CORS_ALLOWED_ORIGINS"):
            if origin_header in settings.CORS_ALLOWED_ORIGINS:
                return origin_header
            else:
                return settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else "http://localhost:5173"
        else:
            return (
                settings.CORS_ALLOWED_ORIGINS[0]
                if hasattr(settings, "CORS_ALLOWED_ORIGINS") and settings.CORS_ALLOWED_ORIGINS
                else "http://localhost:5173"
            )

    async def authenticate_user(self):
        """Authenticate user using Django's session middleware approach."""
        try:
            from django.contrib.auth.models import AnonymousUser
            from django.contrib.sessions.backends.db import SessionStore

            headers = dict(self.scope.get("headers", []))
            cookie_header = headers.get(b"cookie", b"").decode("utf-8")

            if not cookie_header:
                self.scope["user"] = AnonymousUser()
                return False

            import re
            session_match = re.search(r"bh_reggie_sessionid=([^;]+)", cookie_header)
            if not session_match:
                self.scope["user"] = AnonymousUser()
                return False

            session_key = session_match.group(1)

            @database_sync_to_async
            def get_user_from_session():
                session_store = SessionStore(session_key=session_key)

                if not session_store.exists(session_key):
                    return None

                user_id = session_store.get("_auth_user_id")
                if not user_id:
                    return None

                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    user = User.objects.get(id=user_id)
                    return user
                except User.DoesNotExist:
                    return None

            user = await get_user_from_session()

            if user and user.is_authenticated:
                self.scope["user"] = user
                return True
            else:
                self.scope["user"] = AnonymousUser()
                return False

        except Exception as e:
            logger.exception(f"Authentication error: {e}")
            self.scope["user"] = AnonymousUser()
            return False

    async def stream_vault_response(
        self,
        project_id: str,
        folder_id: str,
        agent_id: str,
        file_ids: list,
        message: str,
        session_id: str,
        reasoning: bool = False,
    ):
        """Stream the vault agent response."""
        build_start = time.time()

        # Build the vault agent
        builder = await database_sync_to_async(VaultAgentBuilder)(
            agent_id = agent_id,
            project_id=project_id,
            user=self.scope["user"],
            session_id=session_id,
            folder_id=folder_id,
            file_ids=file_ids,
        )
        agent = await database_sync_to_async(builder.build)(enable_reasoning=reasoning)
        build_time = time.time() - build_start

        # Clear stop flag at the start
        if redis_client:
            try:
                await redis_client.delete(f"stop_stream:{session_id}")
            except Exception as e:
                logger.warning(f"Could not clear stop flag for session {session_id}: {e}")

        try:
            total_start = time.time()
            full_content = ""

            logger.debug(f"[VaultAgent:{project_id}] Agent build time: {build_time:.2f}s")

            # Send build time debug message
            await self.send_body(
                f"data: {json.dumps({'debug': f'Vault agent build time: {build_time:.2f}s'})}\n\n".encode(),
                more_body=True,
            )

            # Generate title for the chat
            @database_sync_to_async
            def get_or_create_title():
                try:
                    # Get the project name for title
                    project = Project.objects.get(uuid=project_id)
                    title = f"Vault Chat - {project.name[:30]}"
                    # Update session title if needed
                    ChatSession.objects.filter(id=session_id).update(title=title)
                    return title
                except Exception as e:
                    logger.error(f"Failed to create title: {e}")
                    return "Vault Chat"

            chat_title = await get_or_create_title()

            # Send title event
            await self.send_body(
                f"data: {json.dumps({'event': 'ChatTitle', 'title': chat_title})}\n\n".encode(),
                more_body=True,
            )

            # Run the agent
            run_start = time.time()
            gen = await database_sync_to_async(agent.run)(
                message,
                stream=True,
                stream_intermediate_steps=True,
            )
            agent_iterator = iter(gen)
            chunk_count = 0
            content_buffer = ""
            last_extra_data = None

            # Stream the response
            while True:
                # Check for stop flag
                if redis_client:
                    try:
                        stop_flag = await redis_client.get(f"stop_stream:{session_id}")
                        if stop_flag:
                            logger.info(f"[VaultAgent] Stop flag detected for session {session_id}")
                            break
                    except Exception as e:
                        logger.warning(f"Could not check stop flag: {e}")

                chunk = await database_sync_to_async(lambda it: next(it, None))(agent_iterator)
                if chunk is None:
                    break

                chunk_count += 1

                # Process the chunk
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

                # Handle text aggregation
                is_simple_text_chunk = (
                    isinstance(event_data, dict)
                    and event_data.get("content_type") == "str"
                    and set(event_data.keys()) <= {"content", "content_type", "event"}
                )

                if is_simple_text_chunk:
                    chunk_text = event_data.get("content", "")
                    content_buffer += chunk_text
                    full_content += chunk_text

                    # Flush buffer periodically
                    if len(content_buffer) >= 200 or content_buffer.endswith((".", "?", "!", "\n")):
                        flush_data = {
                            **event_data,
                            "content": content_buffer,
                        }
                        await self.send_body(
                            f"data: {safe_json_serialize(flush_data)}\n\n".encode(),
                            more_body=True,
                        )
                        content_buffer = ""
                else:
                    # Flush any buffered content first
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

                    # Send the non-text chunk
                    await self.send_body(
                        f"data: {safe_json_serialize(event_data)}\n\n".encode(),
                        more_body=True,
                    )

                # Save extra data for references
                if extra_data and (
                    (isinstance(extra_data, dict) and extra_data) or (isinstance(extra_data, list) and extra_data)
                ):
                    last_extra_data = extra_data

            # Flush any remaining content
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

            # Send references if available
            if last_extra_data:
                references_event = {"event": "References", "extra_data": last_extra_data}
                await self.send_body(
                    f"data: {safe_json_serialize(references_event)}\n\n".encode(),
                    more_body=True,
                )

            # Send citations if available
            if getattr(agent, "run_response", None) and getattr(agent.run_response, "citations", None):
                citations_payload = {
                    "event": "Citations",
                    "citations": agent.run_response.citations,
                }
                await self.send_body(
                    f"data: {json.dumps(citations_payload)}\n\n".encode(),
                    more_body=True,
                )

            # Log timing
            run_time = time.time() - run_start
            total_time = time.time() - total_start
            logger.debug(f"[VaultAgent] Run time: {run_time:.2f}s, Total time: {total_time:.2f}s")

        except Exception as e:
            logger.exception(f"[VaultAgent] Error during streaming: {e}")
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
                logger.info("Client disconnected before stream completion")