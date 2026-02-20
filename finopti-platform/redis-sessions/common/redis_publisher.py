import os
import json
import logging
import redis
import redis
try:
    from event_schema import AgentEvent, EventHeader, EventPayload, UIRendering
except ImportError:
    from .event_schema import AgentEvent, EventHeader, EventPayload, UIRendering

logger = logging.getLogger(__name__)

class RedisEventPublisher:
    def __init__(self, agent_name: str, agent_role: str, redis_url: str = None):
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis_session_store:6379")
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            logger.info(f"RedisEventPublisher connected to {self.redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None

    def publish_event(self, 
                      session_id: str, 
                      user_id: str,
                      trace_id: str,
                      msg_type: str, 
                      message: str, 
                      severity: str = "INFO",
                      display_type: str = "markdown",
                      icon: str = "🤖",
                      metadata: dict = None):
        """
        Publishes a structured event to the session channel.
        """
        if not self.redis_client:
            return

        try:
            event = AgentEvent(
                header=EventHeader(
                    trace_id=trace_id,
                    agent_name=self.agent_name,
                    agent_role=self.agent_role,
                    session_id=session_id
                ),
                type=msg_type,
                payload=EventPayload(
                    message=message,
                    severity=severity,
                    metadata=metadata or {}
                ),
                ui_rendering=UIRendering(
                    display_type=display_type,
                    icon=icon
                )
            )

            # Construct channel name (must match Gateway logic)
            # channel:user_{user_id}:session_{session_id}
            # Fallback for user_id if not present?
            # ADK might not strictly pass user_id in all events, so we might need it passed in.
            
            safe_user = user_id if user_id else "anonymous"
            clean_session_id = session_id.replace("session_", "") if session_id and session_id.startswith("session_") else session_id
            channel_name = f"channel:user_{safe_user}:session_{clean_session_id}"

            subscribers = self.redis_client.publish(channel_name, event.model_dump_json())
            logger.info(f"Published to {channel_name}: {subscribers} subscribers")
            
        except Exception as e:
            logger.error(f"Failed to publish event to {channel_name if 'channel_name' in locals() else 'unknown'}: {e}")

    def process_adk_event(self, event, session_id: str, user_id: str, trace_id: str = "system"):
        """
        Maps ADK internal events to AgentEvent schema.
        """
        try:
            # 1. Thought / Model Response
            if hasattr(event, 'content') and event.content and event.content.parts:
                text_content = ""
                for part in event.content.parts:
                     if part.text: text_content += part.text
                
                if text_content:
                    self.publish_event(
                        session_id=session_id, user_id=user_id, trace_id=trace_id,
                        msg_type="THOUGHT",
                        message=text_content,
                        display_type="markdown",
                        icon="🧠"
                    )

            # 2. Tool Calls
            # ADK structure varies widely. We look for 'tool_calls' or similar.
            # Usually event is ModelResponse or ToolRequest.
            # Let's inspect the object type or specific attributes.
            
            # Simple heuristic:
            # If it's a Tool Request (Client side in ADK terms)
            if hasattr(event, 'function_calls') and event.function_calls:
                 for fc in event.function_calls:
                     self.publish_event(
                        session_id=session_id, user_id=user_id, trace_id=trace_id,
                        msg_type="ACTION",
                        message=f"Running tool: {fc.name}",
                        display_type="console_log",
                        icon="🛠️",
                        metadata={"args": str(fc.args)}
                     )

        except Exception as e:
            logger.warning(f"Error processing ADK event: {e}")
