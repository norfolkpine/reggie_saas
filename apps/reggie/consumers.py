import json
import time
import logging
import urllib.parse

from channels.generic.http import AsyncHttpConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.reggie.agents.agent_builder import AgentBuilder

logger = logging.getLogger(__name__)


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

            if not all([agent_id, message, session_id]):
                await self.send_headers(
                    headers=[(b"Content-Type", b"application/json")],
                    status=400,
                )
                await self.send_body(b'{"error": "Missing required parameters"}')
                return

            await self.send_headers(
                headers=[
                    (b"Content-Type", b"text/event-stream"),
                    (b"Cache-Control", b"no-cache"),
                    (b"Connection", b"keep-alive"),
                    (b"Access-Control-Allow-Origin", b"*"),
                ],
                status=200,
            )

            await self.stream_agent_response(agent_id, message, session_id)

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

    async def stream_agent_response(self, agent_id, message, session_id):
        try:
            total_start = time.time()
            build_start = time.time()
            builder = await database_sync_to_async(AgentBuilder)(
                agent_id=agent_id, user=self.scope["user"], session_id=session_id
            )
            agent = await database_sync_to_async(builder.build)()
            build_time = time.time() - build_start
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
            gen = await database_sync_to_async(agent.run)(message, stream=True)
            agent_iterator = iter(gen)
            chunk_count = 0
            completion_tokens = 0  # will be overwritten with metrics later
            content_buffer = ""  # aggregate small token chunks

            while True:
                chunk = await database_sync_to_async(lambda it: next(it, None))(agent_iterator)
                if chunk is None:
                    break

                chunk_count += 1

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
                    content_buffer += event_data.get("content", "")
                    # flush when buffer exceeds 40 chars or ends with sentence punctuation
                    if len(content_buffer) >= 40 or content_buffer.endswith((".", "?", "!", "\n")):
                        flush_data = {
                            **event_data,
                            "content": content_buffer,
                        }
                        await self.send_body(
                            f"data: {json.dumps(flush_data)}\n\n".encode("utf-8"),
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
                    await self.send_body(
                        f"data: {json.dumps(event_data)}\n\n".encode("utf-8"),
                        more_body=True,
                    )
                # print(f"[DEBUG] Sent event #{chunk_count}:", event_data)

            # flush any remaining buffered content before finishing
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

            # After streaming all chunks, send timing debug events
            run_time = time.time() - run_start
            logger.debug(f"[Agent:{agent_id}] agent.run total time: {run_time:.2f}s")
            # print(f"[DEBUG] agent.run total time: {run_time:.2f}s")
            await self.send_body(
                f"data: {json.dumps({'debug': f'agent.run total time: {run_time:.2f}s'})}\n\n".encode("utf-8"),
                more_body=True,
            )
            total_time = time.time() - total_start
            # Extract token usage metrics, if available
            if getattr(agent, "run_response", None) and getattr(agent.run_response, "metrics", None):
                metrics = agent.run_response.metrics
                prompt_tokens = metrics.get("input_tokens", 0)
                completion_tokens = metrics.get("output_tokens", 0)
                total_tokens = metrics.get("total_tokens", prompt_tokens + completion_tokens)
                await self.send_body(
                    f"data: {json.dumps({'debug': f'Prompt tokens: {prompt_tokens}'})}\n\n".encode("utf-8"),
                    more_body=True,
                )
                await self.send_body(
                    f"data: {json.dumps({'debug': f'Completion tokens: {completion_tokens}'})}\n\n".encode("utf-8"),
                    more_body=True,
                )
                await self.send_body(
                    f"data: {json.dumps({'debug': f'Total tokens: {total_tokens}'})}\n\n".encode("utf-8"),
                    more_body=True,
                )
            logger.debug(f"[Agent:{agent_id}] Total stream time: {total_time:.2f}s")
            # print(f"[DEBUG] Total stream time: {total_time:.2f}s")
            await self.send_body(
                f"data: {json.dumps({'debug': f'Total stream time: {total_time:.2f}s'})}\n\n".encode("utf-8"),
                more_body=True,
            )

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
