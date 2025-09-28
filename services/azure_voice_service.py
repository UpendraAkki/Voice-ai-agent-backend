"""
Azure Voice Service for integrating with Azure AI Foundry Voice Live API
"""

import logging
import json
import asyncio
import aiohttp
import websockets
import base64
from typing import Dict, List, Any, Optional, AsyncIterator
from datetime import datetime, timezone
from config import Settings
from models import VendorDetails, ConversationEntry, VoiceAgentConfig, RAGResponse

logger = logging.getLogger(__name__)


class AzureVoiceSession:
    """Represents an active Azure Voice session"""
    
    def __init__(self, session_id: str, websocket_url: str, config: VoiceAgentConfig):
        self.session_id = session_id
        self.websocket_url = websocket_url
        self.config = config
        self.websocket = None
        self.is_active = False
        self.conversation_buffer = []
        self.created_at = datetime.now(timezone.utc)


class AzureVoiceService:
    """Service for Azure AI Foundry Voice Live API integration"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.active_sessions: Dict[str, AzureVoiceSession] = {}
        self.session = None
        
    async def health_check(self) -> Dict[str, Any]:
        """Check Azure Voice service health"""
        try:
            headers = {
                "Ocp-Apim-Subscription-Key": self.settings.azure_voice_api_key,
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                # Azure Cognitive Services doesn't have a /health endpoint
                # Test with a basic endpoint instead
                async with session.get(
                    f"{self.settings.azure_voice_endpoint}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status < 400:
                        return {
                            "status": "healthy",
                            "endpoint": self.settings.azure_voice_endpoint,
                            "region": self.settings.azure_speech_region
                        }
                    else:
                        return {
                            "status": "degraded",
                            "error": f"HTTP {response.status}",
                            "endpoint": self.settings.azure_voice_endpoint
                        }
                        
        except Exception as e:
            logger.error(f"Azure Voice health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def create_voice_session(
        self, 
        call_session_id: str, 
        vendor_details: VendorDetails
    ) -> AzureVoiceSession:
        """Create a new Azure Voice session"""
        try:
            # Create voice agent configuration based on vendor details
            config = VoiceAgentConfig(
                voice_id="en-US-AriaNeural",  # Default voice
                speech_rate=1.0,
                speech_pitch=1.0,
                language="en-US",
                personality="professional",
                system_prompt=self._generate_system_prompt(vendor_details)
            )
            
            # Create session configuration
            session_config = {
                "sessionId": call_session_id,
                "voice": {
                    "name": config.voice_id,
                    "rate": config.speech_rate,
                    "pitch": config.speech_pitch
                },
                "language": config.language,
                "systemPrompt": config.system_prompt,
                "enableRAG": True,
                "conversationMode": "voice",
                "audioFormat": "audio/wav"
            }
            
            # Initialize session with Azure
            headers = {
                "Ocp-Apim-Subscription-Key": self.settings.azure_voice_api_key,
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.settings.azure_voice_endpoint}/sessions",
                    headers=headers,
                    json=session_config,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 201:
                        session_data = await response.json()
                        websocket_url = session_data.get("websocketUrl", "")
                        
                        # Create voice session
                        voice_session = AzureVoiceSession(
                            session_id=call_session_id,
                            websocket_url=websocket_url,
                            config=config
                        )
                        
                        # Connect to WebSocket
                        await self._connect_websocket(voice_session)
                        
                        # Store session
                        self.active_sessions[call_session_id] = voice_session
                        
                        logger.info(f"Azure Voice session created: {call_session_id}")
                        return voice_session
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create Azure Voice session: {error_text}")
                        raise Exception(f"Failed to create session: HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"Error creating Azure Voice session: {str(e)}")
            raise
    
    async def _connect_websocket(self, voice_session: AzureVoiceSession) -> bool:
        """Connect to Azure Voice WebSocket"""
        try:
            headers = {
                "Ocp-Apim-Subscription-Key": self.settings.azure_voice_api_key
            }
            
            voice_session.websocket = await websockets.connect(
                voice_session.websocket_url,
                extra_headers=headers,
                ping_interval=20,
                ping_timeout=10
            )
            
            voice_session.is_active = True
            logger.info(f"WebSocket connected for session {voice_session.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to Azure Voice WebSocket: {str(e)}")
            return False
    
    async def send_audio(self, voice_session: AzureVoiceSession, audio_data: str) -> bool:
        """Send audio data to Azure Voice session"""
        try:
            if not voice_session.is_active or not voice_session.websocket:
                return False
            
            # Prepare audio message
            message = {
                "type": "audio",
                "audioData": audio_data,
                "format": "audio/wav",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await voice_session.websocket.send(json.dumps(message))
            return True
            
        except Exception as e:
            logger.error(f"Error sending audio to Azure Voice: {str(e)}")
            return False
    
    async def send_text(self, voice_session: AzureVoiceSession, text: str) -> bool:
        """Send text message to Azure Voice session"""
        try:
            if not voice_session.is_active or not voice_session.websocket:
                return False
            
            message = {
                "type": "text",
                "text": text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await voice_session.websocket.send(json.dumps(message))
            return True
            
        except Exception as e:
            logger.error(f"Error sending text to Azure Voice: {str(e)}")
            return False
    
    async def send_rag_context(
        self, 
        voice_session: AzureVoiceSession, 
        rag_response: RAGResponse
    ) -> bool:
        """Send RAG context to Azure Voice session"""
        try:
            if not voice_session.is_active or not voice_session.websocket:
                return False
            
            message = {
                "type": "rag_context",
                "context": {
                    "answer": rag_response.answer,
                    "sources": rag_response.context,
                    "confidence": rag_response.confidence
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await voice_session.websocket.send(json.dumps(message))
            logger.info(f"RAG context sent to session {voice_session.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending RAG context: {str(e)}")
            return False
    
    async def listen_responses(self, voice_session: AzureVoiceSession) -> AsyncIterator[Dict[str, Any]]:
        """Listen for responses from Azure Voice session"""
        try:
            if not voice_session.websocket:
                return
            
            async for message in voice_session.websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get("type", "")
                    
                    if message_type == "audio":
                        yield {
                            "type": "audio",
                            "data": data.get("audioData", ""),
                            "format": data.get("format", "audio/wav")
                        }
                    
                    elif message_type == "transcript":
                        # Store conversation
                        voice_session.conversation_buffer.append({
                            "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                            "speaker": data.get("speaker", "assistant"),
                            "text": data.get("text", "")
                        })
                        
                        yield {
                            "type": "transcript",
                            "speaker": data.get("speaker", "assistant"),
                            "text": data.get("text", ""),
                            "confidence": data.get("confidence")
                        }
                    
                    elif message_type == "rag_query":
                        yield {
                            "type": "rag_query",
                            "question": data.get("question", ""),
                            "context": data.get("context", {})
                        }
                    
                    elif message_type == "session_end":
                        voice_session.is_active = False
                        yield {
                            "type": "session_end",
                            "reason": data.get("reason", "completed")
                        }
                        break
                    
                    elif message_type == "error":
                        logger.error(f"Azure Voice error: {data.get('error', 'Unknown error')}")
                        yield {
                            "type": "error",
                            "error": data.get("error", "Unknown error")
                        }
                        
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received from Azure Voice: {message}")
                except Exception as e:
                    logger.error(f"Error processing Azure Voice message: {str(e)}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Azure Voice WebSocket closed for session {voice_session.session_id}")
            voice_session.is_active = False
        except Exception as e:
            logger.error(f"Error listening to Azure Voice responses: {str(e)}")
            voice_session.is_active = False
    
    async def generate_conversation_summary(self, conversation_log: List[ConversationEntry]) -> str:
        """Generate conversation summary using OpenAI"""
        try:
            import openai
            
            openai.api_key = self.settings.openai_api_key
            
            # Prepare conversation text
            conversation_text = "\n".join([
                f"{entry.speaker}: {entry.text}" 
                for entry in conversation_log
            ])
            
            # Generate summary
            response = await openai.ChatCompletion.acreate(
                model=self.settings.openai_model,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant that creates concise summaries of customer service conversations. Include key points, issues discussed, and resolution status."
                    },
                    {
                        "role": "user", 
                        "content": f"Please summarize this customer service conversation:\n\n{conversation_text}"
                    }
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content.strip()
            logger.info("Conversation summary generated successfully")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating conversation summary: {str(e)}")
            return "Summary generation failed"
    
    async def cleanup_session(self, voice_session: AzureVoiceSession) -> bool:
        """Cleanup Azure Voice session"""
        try:
            # Close WebSocket connection
            if voice_session.websocket:
                await voice_session.websocket.close()
            
            # Mark as inactive
            voice_session.is_active = False
            
            # Remove from active sessions
            if voice_session.session_id in self.active_sessions:
                del self.active_sessions[voice_session.session_id]
            
            logger.info(f"Azure Voice session cleaned up: {voice_session.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up Azure Voice session: {str(e)}")
            return False
    
    def _generate_system_prompt(self, vendor_details: VendorDetails) -> str:
        """Generate system prompt based on vendor details"""
        base_prompt = f"""
        You are a professional AI customer service assistant for {vendor_details.vendor_name}.
        
        Business Information:
        - Company: {vendor_details.vendor_name}
        - Business Type: {vendor_details.business_type or 'General Business'}
        
        Instructions:
        1. Be professional, helpful, and courteous
        2. Use the company's knowledge base to answer questions accurately
        3. If you need additional information, ask clarifying questions
        4. If you cannot help with something, explain clearly and offer alternatives
        5. Always maintain a positive and solution-oriented approach
        6. Keep responses concise and relevant
        
        When you need information from the knowledge base, I will provide you with relevant context.
        """
        
        # Add business policies if available
        if vendor_details.business_policies:
            policies_text = json.dumps(vendor_details.business_policies, indent=2)
            base_prompt += f"\n\nBusiness Policies:\n{policies_text}"
        
        return base_prompt.strip()
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about active sessions"""
        active_count = len([s for s in self.active_sessions.values() if s.is_active])
        
        return {
            "total_sessions": len(self.active_sessions),
            "active_sessions": active_count,
            "session_details": [
                {
                    "session_id": s.session_id,
                    "is_active": s.is_active,
                    "created_at": s.created_at.isoformat(),
                    "conversation_entries": len(s.conversation_buffer)
                }
                for s in self.active_sessions.values()
            ]
        }
