from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as redis
import os
import json
import logging
from app.models import AgentEvent, EventHeader, EventPayload, UIRendering, TroubleshootingSessionContext

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="FinOpti Redis Gateway", version="1.0")

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis_session_store:6379")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

class SessionInitRequest(BaseModel):
    user_id: str
    session_id: str

class PublishRequest(BaseModel):
    channel: str
    message: dict

@app.on_event("startup")
async def startup_event():
    logger.info(f"Connected to Redis at {REDIS_URL}")

@app.get("/health")
async def health_check():
    try:
        await redis_client.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise HTTPException(status_code=503, detail="Redis unavailable")

@app.post("/session/init")
async def init_session(request: SessionInitRequest):
    """
    Initialize a new session channel.
    Task 1: Channel Creation
    Logic: Defines the canonical channel name.
    """
    try:
        clean_session_id = request.session_id.replace("session_", "") if request.session_id.startswith("session_") else request.session_id
        channel_name = f"channel:user_{request.user_id}:session_{clean_session_id}"
        
        # We don't strictly *need* to creation a channel in Redis (it's dynamic),
        # but we can set a key to track active sessions or metadata.
        # For now, we'll just log it and maybe set a TTL marker keys
        
        marker_key = f"meta:session:{request.session_id}"
        await redis_client.setex(marker_key, 86400, "active") # 24h TTL
        
        
        # Publish "Session Initialized" event (helps with debugging if listener is active)
        try:
             init_event = AgentEvent(
                header=EventHeader(
                    trace_id=f"init-{request.session_id}",
                    agent_name="RedisGateway",
                    agent_role="System"
                ),
                type="LIFECYCLE",
                payload=EventPayload(
                    message=f"Session {request.session_id} initialized for {request.user_id}",
                    severity="INFO"
                ),
                ui_rendering=UIRendering(
                    display_type="toast",
                    icon="🔌"
                )
             )
             await redis_client.publish(channel_name, init_event.model_dump_json())
        except Exception as e:
             logger.warning(f"Failed to publish init event: {e}")

        logger.info(f"Initialized session: {request.session_id} for user: {request.user_id}. Channel: {channel_name}")
        
        return {
            "status": "initialized",
            "channel": channel_name,
            "user_id": request.user_id,
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Failed to init session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PublishEventRequest(BaseModel):
    user_id: str
    session_id: str
    event: AgentEvent

# ...

@app.post("/event")
async def publish_event(request: PublishEventRequest):
    """
    Task 2: Message Standardization (Publishing)
    Validates the event schema before pushing to Redis.
    """
    try:
        clean_session_id = request.session_id.replace("session_", "") if request.session_id.startswith("session_") else request.session_id
        channel_name = f"channel:user_{request.user_id}:session_{clean_session_id}"
        
        # Publish request.event.model_dump_json()
        await redis_client.publish(channel_name, request.event.model_dump_json())
        
        return {"status": "published", "channel": channel_name, "event_id": request.event.header.event_id}
    except Exception as e:
        logger.error(f"Event publish failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from fastapi.responses import StreamingResponse
import asyncio

# ...

async def event_generator(channel_name: str):
    """
    Yields Redis messages as Server-Sent Events (SSE).
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                # SSE format: data: <payload>\n\n
                yield f"data: {message['data']}\n\n"
            await asyncio.sleep(0.1) # Prevent busy loop
    except asyncio.CancelledError:
        logger.info(f"Client disconnected from {channel_name}")
        await pubsub.unsubscribe(channel_name)

@app.get("/stream/{user_id}/{session_id}")
async def stream_events(user_id: str, session_id: str):
    """
    Task 3: Message Listener (Server-Sent Events)
    Streams events from Redis to the client.
    """
    clean_session_id = session_id.replace("session_", "") if session_id.startswith("session_") else session_id
    channel_name = f"channel:user_{user_id}:session_{clean_session_id}"
    logger.info(f"Starting stream for {channel_name}")
    
    return StreamingResponse(
        event_generator(channel_name),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
@app.get("/session/{session_id}/context", response_model=TroubleshootingSessionContext)
async def get_session_context(session_id: str):
    """
    Retrieve the structured troubleshooting context for a session.
    """
    try:
        clean_session_id = session_id.replace("session_", "") if session_id.startswith("session_") else session_id
        context_key = f"context:session:{clean_session_id}"
        data = await redis_client.get(context_key)
        if not data:
            return TroubleshootingSessionContext()
        return TroubleshootingSessionContext.model_validate_json(data)
    except Exception as e:
        logger.error(f"Failed to get session context: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/session/{session_id}/context")
async def update_session_context(session_id: str, context: TroubleshootingSessionContext):
    """
    Update the structured troubleshooting context for a session.
    """
    try:
        clean_session_id = session_id.replace("session_", "") if session_id.startswith("session_") else session_id
        context_key = f"context:session:{clean_session_id}"
        await redis_client.setex(context_key, 86400, context.model_dump_json())
        return {"status": "updated", "session_id": session_id}
    except Exception as e:
        logger.error(f"Failed to update session context: {e}")
        raise HTTPException(status_code=500, detail=str(e))
