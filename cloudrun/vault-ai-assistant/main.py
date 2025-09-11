import json
import logging
import os
import asyncio
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from llama_index.core import VectorStoreIndex, get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.llms.anthropic import Anthropic
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

# === Load environment variables ===
from dotenv import load_dotenv
load_dotenv()

# === Config Variables ===
POSTGRES_URL = os.getenv("POSTGRES_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DJANGO_API_URL = os.getenv("DJANGO_API_URL", "http://localhost:8000")
DJANGO_API_KEY = os.getenv("DJANGO_API_KEY")

# Validate required environment variables
if not POSTGRES_URL:
    raise ValueError("POSTGRES_URL environment variable is required")
if not DJANGO_API_KEY:
    raise ValueError("DJANGO_API_KEY environment variable is required for chat history")

# === Logging Setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("vault_ai_assistant")

# === Request Models ===
class VaultChatRequest(BaseModel):
    message: str = Field(..., description="User query message")
    project_id: str = Field(..., description="Project ID to query from")
    user_id: str = Field(..., description="User ID making the request")
    session_id: str = Field(..., description="Chat session ID")
    max_results: int = Field(default=5, description="Maximum number of results to retrieve")
    temperature: float = Field(default=0.7, description="LLM temperature for response generation")
    model_provider: str = Field(default="openai", description="LLM provider (openai, google, anthropic)")
    model_name: str = Field(default="gpt-4o-mini", description="LLM model name")

class VaultChatHistoryEntry(BaseModel):
    role: str
    content: str
    timestamp: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events for the FastAPI app."""
    # Test Django API connectivity
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{DJANGO_API_URL.rstrip('/')}/health/",
                headers={
                    "Authorization": f"Api-Key {DJANGO_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=5.0
            )
            if response.status_code in [200, 500]:
                logger.info("✅ Django API connectivity verified")
            else:
                logger.warning(f"⚠️ Django API returned status {response.status_code}")
    except Exception as e:
        logger.warning(f"⚠️ Could not verify Django API connectivity: {e}")
    
    yield
    
    # Cleanup
    logger.info("Shutting down vault AI assistant...")

app = FastAPI(lifespan=lifespan)

def get_vector_store(project_id: str, embedding_dim: int = 1536):
    """Create PGVector store for a specific project."""
    async_engine = create_async_engine(
        POSTGRES_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )
    engine = create_engine(
        POSTGRES_URL,
        pool_size=5,
        max_overflow=0,
        pool_timeout=30,
        pool_recycle=1800,
    )

    return PGVectorStore(
        engine=engine,
        async_engine=async_engine,
        table_name="vault_embeddings",  # Dedicated table for vault embeddings
        embed_dim=embedding_dim,
        schema_name="ai",  # Use ai schema as specified
        perform_setup=True,
    )

def get_embedder(provider: str = "openai", model: str = "text-embedding-ada-002"):
    """Get appropriate embedder based on provider."""
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        return OpenAIEmbedding(model=model, api_key=OPENAI_API_KEY)
    else:
        raise ValueError(f"Unsupported embedding provider: {provider}. Only 'openai' is supported.")

def get_llm(provider: str, model: str, temperature: float = 0.7):
    """Get appropriate LLM based on provider."""
    if provider == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        return OpenAI(model=model, api_key=OPENAI_API_KEY, temperature=temperature)
    elif provider == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        return Anthropic(model=model, temperature=temperature)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}. Supported: 'openai', 'anthropic'")

async def get_chat_history(session_id: str) -> List[VaultChatHistoryEntry]:
    """Retrieve chat history from Django API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{DJANGO_API_URL.rstrip('/')}/reggie/api/v1/chat-sessions/{session_id}/history/",
                headers={
                    "Authorization": f"Api-Key {DJANGO_API_KEY}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            response.raise_for_status()
            history_data = response.json()
            return [VaultChatHistoryEntry(**entry) for entry in history_data]
    except Exception as e:
        logger.warning(f"Could not retrieve chat history for session {session_id}: {e}")
        return []

async def save_chat_message(session_id: str, role: str, content: str):
    """Save chat message to Django API."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DJANGO_API_URL.rstrip('/')}/reggie/api/v1/chat-sessions/{session_id}/messages/",
                headers={
                    "Authorization": f"Api-Key {DJANGO_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "role": role,
                    "content": content,
                    "timestamp": "now"
                },
                timeout=10.0
            )
            response.raise_for_status()
    except Exception as e:
        logger.warning(f"Could not save chat message for session {session_id}: {e}")

async def generate_streaming_response(request: VaultChatRequest):
    """Generate streaming response for vault chat."""
    try:
        # Get embedder - assuming OpenAI text-embedding-ada-002 for now
        embedder = get_embedder("openai", "text-embedding-ada-002")
        
        # Get vector store
        vector_store = get_vector_store(request.project_id)
        
        # Create index
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store, 
            embed_model=embedder
        )
        
        # Create retriever with metadata filtering for project
        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=request.max_results,
            filters={
                "project_id": request.project_id,
                "user_uuid": request.user_id  # Ensure user can only access their own data
            }
        )
        
        # Get LLM
        llm = get_llm(request.model_provider, request.model_name, request.temperature)
        
        # Create query engine
        response_synthesizer = get_response_synthesizer(
            llm=llm,
            streaming=True,
            response_mode="compact"
        )
        
        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            response_synthesizer=response_synthesizer,
        )
        
        # Get chat history
        history = await get_chat_history(request.session_id)
        
        # Build context from history
        context = ""
        if history:
            context = "\n".join([f"{entry.role}: {entry.content}" for entry in history[-5:]])  # Last 5 messages
            context = f"Previous conversation:\n{context}\n\nCurrent question: "
        
        # Prepare query with context
        query_with_context = f"{context}{request.message}"
        
        # Save user message
        await save_chat_message(request.session_id, "user", request.message)
        
        # Stream the response
        streaming_response = query_engine.query(query_with_context)
        
        full_response = ""
        
        # Send initial data
        yield f"data: {json.dumps({'event': 'start', 'session_id': request.session_id})}\n\n"
        
        # Stream response chunks
        for chunk in streaming_response.response_gen:
            full_response += chunk
            data = {
                "event": "chunk",
                "content": chunk,
                "content_type": "str"
            }
            yield f"data: {json.dumps(data)}\n\n"
        
        # Send sources/references if available
        if hasattr(streaming_response, 'source_nodes') and streaming_response.source_nodes:
            sources = []
            for node in streaming_response.source_nodes:
                source_info = {
                    "content": node.text[:200] + "..." if len(node.text) > 200 else node.text,
                    "score": getattr(node, 'score', None),
                    "metadata": node.metadata
                }
                sources.append(source_info)
            
            references_data = {
                "event": "References",
                "sources": sources
            }
            yield f"data: {json.dumps(references_data)}\n\n"
        
        # Save assistant response
        await save_chat_message(request.session_id, "assistant", full_response)
        
        # Send completion
        yield f"data: {json.dumps({'event': 'complete'})}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.exception(f"Error in generate_streaming_response: {e}")
        error_data = {
            "event": "error",
            "error": str(e)
        }
        yield f"data: {json.dumps(error_data)}\n\n"
        yield "data: [DONE]\n\n"

@app.post("/vault/chat/stream")
async def vault_chat_stream(request: VaultChatRequest):
    """Stream vault AI assistant response."""
    return StreamingResponse(
        generate_streaming_response(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )

@app.get("/")
async def root():
    return {"message": "Vault AI Assistant service is alive!"}

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "vault-ai-assistant"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8081))
    uvicorn.run("main:app", host="0.0.0.0", port=port)