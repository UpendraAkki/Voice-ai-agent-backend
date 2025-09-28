"""
Twilio Service for handling voice calls and webhooks
"""

import logging
from typing import Dict, Any
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from fastapi.responses import Response
from config import Settings

logger = logging.getLogger(__name__)


class TwilioService:
    """Service for Twilio integration"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        
    async def health_check(self) -> Dict[str, Any]:
        """Check Twilio service health"""
        try:
            # Try to fetch account info
            account = self.client.api.accounts(self.settings.twilio_account_sid).fetch()
            return {
                "status": "healthy",
                "account_sid": account.sid,
                "account_status": account.status
            }
        except Exception as e:
            logger.error(f"Twilio health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def generate_websocket_response(self, websocket_url: str) -> Response:
        """
        Generate TwiML response to connect call to WebSocket
        """
        try:
            response = VoiceResponse()
            
            # Add a greeting message
            response.say("Hello! I'm your AI assistant. Please wait while I connect you to our voice agent.")
            
            # Connect to WebSocket for real-time audio streaming
            connect = Connect()
            stream = connect.stream(url=websocket_url)
            
            # Configure stream parameters
            stream.parameter(name="track", value="both_tracks")
            stream.parameter(name="status_callback_url", value=f"{self.settings.base_url}/twilio/status")
            
            response.append(connect)
            
            response_content = str(response)
            
            return Response(
                content=response_content,
                media_type="application/xml",
                headers={"Content-Type": "application/xml"}
            )
            
        except Exception as e:
            logger.error(f"Error generating WebSocket TwiML: {str(e)}")
            return await self.generate_error_response("Technical error occurred")
    
    async def generate_error_response(self, message: str) -> Response:
        """Generate TwiML error response"""
        try:
            response = VoiceResponse()
            response.say(message)
            response.hangup()
            
            response_content = str(response)
            
            return Response(
                content=response_content,
                media_type="application/xml",
                headers={"Content-Type": "application/xml"}
            )
            
        except Exception as e:
            logger.error(f"Error generating error TwiML: {str(e)}")
            # Fallback simple response
            simple_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Say>Service unavailable</Say><Hangup/></Response>'
            return Response(
                content=simple_twiml,
                media_type="application/xml",
                headers={"Content-Type": "application/xml"}
            )
    
    async def generate_hold_response(self, message: str = "Please hold while we process your request") -> Response:
        """Generate TwiML response to put caller on hold"""
        try:
            twiml = TwiML()
            twiml.say(message)
            twiml.pause(length=2)
            
            response_content = str(twiml)
            
            return Response(
                content=response_content,
                media_type="application/xml",
                headers={"Content-Type": "application/xml"}
            )
            
        except Exception as e:
            logger.error(f"Error generating hold TwiML: {str(e)}")
            return await self.generate_error_response("Please hold")
    
    async def make_outbound_call(self, to_number: str, from_number: str = None) -> str:
        """Make an outbound call"""
        try:
            from_number = from_number or self.settings.twilio_phone_number
            
            call = self.client.calls.create(
                to=to_number,
                from_=from_number,
                url=f"{self.settings.base_url}/outbound-call-webhook"
            )
            
            logger.info(f"Outbound call initiated: {call.sid}")
            return call.sid
            
        except Exception as e:
            logger.error(f"Error making outbound call: {str(e)}")
            raise
    
    async def get_call_details(self, call_sid: str) -> Dict[str, Any]:
        """Get call details from Twilio"""
        try:
            call = self.client.calls(call_sid).fetch()
            
            return {
                "sid": call.sid,
                "status": call.status,
                "from": call.from_,
                "to": call.to,
                "start_time": call.start_time,
                "end_time": call.end_time,
                "duration": call.duration,
                "price": call.price,
                "direction": call.direction
            }
            
        except Exception as e:
            logger.error(f"Error fetching call details: {str(e)}")
            raise
    
    async def end_call(self, call_sid: str) -> bool:
        """End an active call"""
        try:
            call = self.client.calls(call_sid).update(status="completed")
            logger.info(f"Call {call_sid} ended successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error ending call {call_sid}: {str(e)}")
            return False
    
    async def send_sms(self, to_number: str, message: str, from_number: str = None) -> str:
        """Send SMS message"""
        try:
            from_number = from_number or self.settings.twilio_phone_number
            
            message = self.client.messages.create(
                body=message,
                from_=from_number,
                to=to_number
            )
            
            logger.info(f"SMS sent: {message.sid}")
            return message.sid
            
        except Exception as e:
            logger.error(f"Error sending SMS: {str(e)}")
            raise
