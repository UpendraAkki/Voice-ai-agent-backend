"""
OpenAI Real-time API Service for Voice Conversations
Enhanced implementation based on best practices
"""

import json
import base64
import asyncio
import websockets
import logging
from typing import Dict, Optional, List, AsyncIterator, Callable, Any
from datetime import datetime, timezone

from config import Settings

logger = logging.getLogger(__name__)


class OpenAIRealtimeService:
    """Enhanced OpenAI Real-time API service for voice conversations"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.endpoint = settings.openai_realtime_endpoint
        self.api_key = settings.openai_api_key
        
        # Event types to log for debugging
        self.log_event_types = [
            'error', 'response.content.done', 'rate_limits.updated',
            'response.done', 'input_audio_buffer.committed',
            'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
            'session.created', 'response.audio.delta', 'conversation.item.created'
        ]
        
        # Show timing calculations for debugging
        self.show_timing_math = settings.debug
    
    async def create_session(
        self, 
        session_id: str,
        system_message: str,
        voice: str = "alloy",
        temperature: float = 0.8,
        initial_greeting: Optional[str] = None
    ) -> Dict:
        """Create a new OpenAI real-time session"""
        try:
            # Connect to OpenAI Real-time API
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            openai_ws = await websockets.connect(
                self.endpoint,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10
            )
            
            # Initialize session configuration
            await self._initialize_session(
                openai_ws, 
                system_message, 
                voice, 
                temperature
            )
            
            # Send initial greeting if provided
            if initial_greeting:
                await self._send_initial_greeting(openai_ws, initial_greeting)
            
            session_data = {
                "session_id": session_id,
                "websocket": openai_ws,
                "created_at": datetime.now(timezone.utc),
                "is_active": True,
                "voice": voice,
                "system_message": system_message,
                # Connection state
                "latest_media_timestamp": 0,
                "last_assistant_item": None,
                "mark_queue": [],
                "response_start_timestamp": None
            }
            
            logger.info(f"OpenAI real-time session created: {session_id}")
            return session_data
            
        except Exception as e:
            logger.error(f"Error creating OpenAI session: {str(e)}")
            raise
    
    async def _initialize_session(
        self, 
        websocket, 
        system_message: str, 
        voice: str, 
        temperature: float
    ):
        """Initialize OpenAI session with configuration"""
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw", 
                "voice": voice,
                "instructions": system_message,
                "modalities": ["text", "audio"],
                "temperature": temperature,
                "max_response_output_tokens": 4096
            }
        }
        
        logger.info(f"Sending session update: {session_update['session']['voice']}")
        await websocket.send(json.dumps(session_update))
    
    async def _send_initial_greeting(self, websocket, greeting_text: str):
        """Send initial conversation item for AI to speak first"""
        initial_item = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"Please say: {greeting_text}"
                    }
                ]
            }
        }
        
        await websocket.send(json.dumps(initial_item))
        await websocket.send(json.dumps({"type": "response.create"}))
        logger.info("Initial greeting sent to OpenAI")
    
    async def handle_twilio_to_openai(
        self, 
        session_data: Dict, 
        twilio_ws, 
        on_session_start: Optional[Callable] = None
    ):
        """Handle audio from Twilio to OpenAI"""
        try:
            openai_ws = session_data["websocket"]
            
            async for message in twilio_ws.iter_text():
                data = json.loads(message)
                
                if data['event'] == 'media':
                    # Forward audio to OpenAI
                    session_data["latest_media_timestamp"] = int(data['media']['timestamp'])
                    
                    audio_append = {
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }
                    await openai_ws.send(json.dumps(audio_append))
                
                elif data['event'] == 'start':
                    # Stream started
                    stream_sid = data['start']['streamSid']
                    session_data["stream_sid"] = stream_sid
                    session_data["response_start_timestamp"] = None
                    session_data["latest_media_timestamp"] = 0
                    session_data["last_assistant_item"] = None
                    
                    logger.info(f"Twilio stream started: {stream_sid}")
                    
                    if on_session_start:
                        await on_session_start(session_data)
                
                elif data['event'] == 'mark':
                    # Handle mark events for timing
                    if session_data["mark_queue"]:
                        session_data["mark_queue"].pop(0)
                        
        except Exception as e:
            logger.error(f"Error in Twilio to OpenAI handler: {str(e)}")
            raise
    
    async def handle_openai_to_twilio(
        self, 
        session_data: Dict, 
        twilio_ws,
        on_audio_response: Optional[Callable] = None,
        on_text_response: Optional[Callable] = None,
        on_speech_started: Optional[Callable] = None
    ) -> AsyncIterator[Dict]:
        """Handle responses from OpenAI to Twilio"""
        try:
            openai_ws = session_data["websocket"]
            
            async for openai_message in openai_ws:
                response = json.loads(openai_message)
                
                # Log important events
                if response['type'] in self.log_event_types:
                    logger.info(f"OpenAI event: {response['type']}")
                    if self.settings.debug:
                        logger.debug(f"Full response: {response}")
                
                # Handle audio responses
                if response.get('type') == 'response.audio.delta' and 'delta' in response:
                    await self._handle_audio_delta(response, session_data, twilio_ws)
                    
                    if on_audio_response:
                        await on_audio_response(response, session_data)
                
                # Handle text responses
                elif response.get('type') == 'response.text.delta':
                    if on_text_response:
                        await on_text_response(response, session_data)
                
                # Handle speech interruption
                elif response.get('type') == 'input_audio_buffer.speech_started':
                    logger.info("Speech interruption detected")
                    await self._handle_speech_interruption(session_data, twilio_ws)
                    
                    if on_speech_started:
                        await on_speech_started(session_data)
                
                # Handle conversation items for RAG integration
                elif response.get('type') == 'conversation.item.created':
                    yield {
                        "type": "conversation_item",
                        "data": response,
                        "session_id": session_data["session_id"]
                    }
                
                # Handle function calls for RAG queries
                elif response.get('type') == 'response.function_call_arguments.delta':
                    yield {
                        "type": "rag_query",
                        "data": response,
                        "session_id": session_data["session_id"]
                    }
                
                # Handle completion events
                elif response.get('type') == 'response.done':
                    yield {
                        "type": "response_complete",
                        "data": response,
                        "session_id": session_data["session_id"]
                    }
                    
        except Exception as e:
            logger.error(f"Error in OpenAI to Twilio handler: {str(e)}")
            raise
    
    async def _handle_audio_delta(self, response: Dict, session_data: Dict, twilio_ws):
        """Handle audio delta from OpenAI"""
        try:
            # Encode audio for Twilio
            audio_payload = base64.b64encode(
                base64.b64decode(response['delta'])
            ).decode('utf-8')
            
            # Send to Twilio
            audio_delta = {
                "event": "media",
                "streamSid": session_data.get("stream_sid"),
                "media": {
                    "payload": audio_payload
                }
            }
            await twilio_ws.send_json(audio_delta)
            
            # Track timing for interruption handling
            if session_data["response_start_timestamp"] is None:
                session_data["response_start_timestamp"] = session_data["latest_media_timestamp"]
                if self.show_timing_math:
                    logger.debug(f"Response start timestamp: {session_data['response_start_timestamp']}ms")
            
            # Update last assistant item
            if response.get('item_id'):
                session_data["last_assistant_item"] = response['item_id']
            
            # Send mark for timing
            await self._send_mark(twilio_ws, session_data)
            
        except Exception as e:
            logger.error(f"Error handling audio delta: {str(e)}")
    
    async def _handle_speech_interruption(self, session_data: Dict, twilio_ws):
        """Handle speech interruption from user"""
        try:
            if (session_data["mark_queue"] and 
                session_data["response_start_timestamp"] is not None):
                
                # Calculate elapsed time
                elapsed_time = (session_data["latest_media_timestamp"] - 
                              session_data["response_start_timestamp"])
                
                if self.show_timing_math:
                    logger.debug(f"Interruption after {elapsed_time}ms")
                
                # Truncate the current response
                if session_data["last_assistant_item"]:
                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": session_data["last_assistant_item"],
                        "content_index": 0,
                        "audio_end_ms": elapsed_time
                    }
                    await session_data["websocket"].send(json.dumps(truncate_event))
                
                # Clear Twilio audio buffer
                await twilio_ws.send_json({
                    "event": "clear", 
                    "streamSid": session_data.get("stream_sid")
                })
                
                # Reset state
                session_data["mark_queue"].clear()
                session_data["last_assistant_item"] = None
                session_data["response_start_timestamp"] = None
                
        except Exception as e:
            logger.error(f"Error handling speech interruption: {str(e)}")
    
    async def _send_mark(self, twilio_ws, session_data: Dict):
        """Send timing mark to Twilio"""
        try:
            stream_sid = session_data.get("stream_sid")
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"}
                }
                await twilio_ws.send_json(mark_event)
                session_data["mark_queue"].append('responsePart')
                
        except Exception as e:
            logger.error(f"Error sending mark: {str(e)}")
    
    async def inject_rag_context(self, session_data: Dict, context: str, question: str):
        """Inject RAG context into the conversation"""
        try:
            openai_ws = session_data["websocket"]
            
            context_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Context for the question '{question}': {context}"
                        }
                    ]
                }
            }
            
            await openai_ws.send(json.dumps(context_item))
            logger.info("RAG context injected into conversation")
            
        except Exception as e:
            logger.error(f"Error injecting RAG context: {str(e)}")
    
    async def close_session(self, session_data: Dict):
        """Close OpenAI session"""
        try:
            session_data["is_active"] = False
            
            if session_data.get("websocket"):
                await session_data["websocket"].close()
            
            logger.info(f"OpenAI session closed: {session_data['session_id']}")
            
        except Exception as e:
            logger.error(f"Error closing OpenAI session: {str(e)}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for OpenAI Real-time API"""
        try:
            # Test connection to OpenAI
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            async with websockets.connect(
                self.endpoint,
                additional_headers=headers,
                close_timeout=5
            ) as ws:
                # Send a test session update
                test_update = {
                    "type": "session.update",
                    "session": {"modalities": ["text", "audio"]}
                }
                await ws.send(json.dumps(test_update))
                
                # Wait for response
                response = await asyncio.wait_for(ws.recv(), timeout=5)
                response_data = json.loads(response)
                
                if response_data.get("type") == "session.updated":
                    return {
                        "status": "healthy",
                        "endpoint": self.endpoint,
                        "model": "gpt-4o-realtime-preview"
                    }
                else:
                    return {
                        "status": "degraded",
                        "error": "Unexpected response"
                    }
                    
        except Exception as e:
            logger.error(f"OpenAI health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
