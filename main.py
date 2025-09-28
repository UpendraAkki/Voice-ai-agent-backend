"""
FastAPI Middleware Server for Voice Agent Integration
Acts as a bridge between Twilio, Azure AI Foundry, and RAG system
"""

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json
import uuid

from config import Settings
from models import (
    TwilioWebhookRequest, 
    VendorDetails, 
    CallSession, 
    ConversationSummary,
    RAGRequest,
    RAGResponse
)
from services.twilio_service import TwilioService
from services.rag_service import RAGService
from services.azure_voice_service import AzureVoiceService
from services.openai_realtime_service import OpenAIRealtimeService
from services.supabase_service import SupabaseService
from services.websocket_manager import WebSocketManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Voice Agent Middleware",
    description="Middleware server for automating customer service using voice agents",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on your frontend domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize settings
settings = Settings()

# Initialize services
twilio_service = TwilioService(settings)
rag_service = RAGService(settings)
azure_voice_service = AzureVoiceService(settings)
openai_realtime_service = OpenAIRealtimeService(settings)
supabase_service = SupabaseService(settings)
websocket_manager = WebSocketManager()

# Store active call sessions
active_sessions: Dict[str, CallSession] = {}


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting Voice Agent Middleware Server...")
    await supabase_service.initialize()
    logger.info("Server started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Voice Agent Middleware Server...")
    # Close any active websocket connections
    await websocket_manager.disconnect_all()
    logger.info("Server shutdown complete")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Voice Agent Middleware Server is running",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    try:
        # Check all service connections
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "twilio": await twilio_service.health_check(),
                "rag": await rag_service.health_check(),
                "azure_voice": await azure_voice_service.health_check(),
                "openai_realtime": await openai_realtime_service.health_check(),
                "supabase": await supabase_service.health_check()
            },
            "active_sessions": len(active_sessions)
        }
        
        # Check if any service is unhealthy
        if not all(service["status"] == "healthy" for service in health_status["services"].values()):
            health_status["status"] = "degraded"
        
        return health_status
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@app.post("/incoming-call")
async def incoming_call_webhook(request: Request):
    """
    Twilio webhook endpoint for incoming calls
    This is the main entry point for voice calls
    """
    try:
        logger.info("🔍 DEBUG: Starting incoming call handler")
        
        # Parse Twilio webhook data
        form_data = await request.form()
        logger.info(f"🔍 DEBUG: Form data received: {dict(form_data)}")
        
        webhook_data = TwilioWebhookRequest.from_form_data(dict(form_data))
        logger.info(f"🔍 DEBUG: Webhook data parsed successfully")
        
        logger.info(f"Incoming call from {webhook_data.caller} to {webhook_data.called}")
        
        # Generate unique call session ID
        call_session_id = str(uuid.uuid4())
        logger.info(f"🔍 DEBUG: Generated session ID: {call_session_id}")
        
        # Create call session
        call_session = CallSession(
            session_id=call_session_id,
            call_sid=webhook_data.call_sid,
            caller_number=webhook_data.caller,
            called_number=webhook_data.called,
            start_time=datetime.now(timezone.utc),
            status="initiated"
        )
        logger.info(f"🔍 DEBUG: Call session created successfully")
        
        # Store session
        active_sessions[call_session_id] = call_session
        logger.info(f"🔍 DEBUG: Session stored in active_sessions")
        
        # Retrieve vendor details based on the called number
        logger.info(f"🔍 DEBUG: Retrieving vendor details for phone: {webhook_data.called}")
        vendor_details = await supabase_service.get_vendor_details_by_phone(webhook_data.called)
        logger.info(f"🔍 DEBUG: Vendor details retrieved: {vendor_details is not None}")
        
        if not vendor_details:
            logger.warning(f"No vendor details found for number {webhook_data.called}")
            # Return TwiML to handle unknown number
            return await twilio_service.generate_error_response(
                "Sorry, this number is not configured for voice agent support."
            )
        
        # Update session with vendor details
        call_session.vendor_details = vendor_details
        call_session.user_id = vendor_details.user_id
        logger.info(f"🔍 DEBUG: Session updated with vendor details")
        
        # Retrieve knowledge base for the vendor
        logger.info(f"🔍 DEBUG: Retrieving knowledge base for user: {vendor_details.user_id}")
        knowledge_base = await supabase_service.get_user_knowledge_base(vendor_details.user_id)
        logger.info(f"🔍 DEBUG: Knowledge base retrieved: {len(knowledge_base)} documents")
        
        # Prepare RAG context with text content instead of URLs
        rag_sources = []
        for doc in knowledge_base:
            # Use document name and type as text content instead of URL
            # This avoids issues with PDF URL processing
            text_content = f"Document: {doc['document_name']}\nType: {doc['document_type']}\nUpload Date: {doc['upload_date']}"
            
            rag_sources.append({
                "source": text_content,
                "source_type": "text",
                "metadata": {
                    "title": doc["document_name"],
                    "upload_date": doc["upload_date"],
                    "document_type": doc["document_type"],
                    "document_url": doc["document_url"]  # Keep URL in metadata for reference
                }
            })
        logger.info(f"🔍 DEBUG: RAG sources prepared: {len(rag_sources)} sources")
        
        # Initialize RAG system with vendor's knowledge base
        if rag_sources:
            logger.info(f"🔍 DEBUG: Initializing RAG system...")
            await rag_service.initialize_knowledge_base(call_session_id, rag_sources)
            logger.info(f"🔍 DEBUG: RAG system initialized successfully")
        
        # Generate TwiML response to connect to WebSocket  
        logger.info(f"🔍 DEBUG: Generating WebSocket URL...")
        websocket_url = f"wss://{request.url.hostname}/media-stream/{call_session_id}"
        logger.info(f"🔍 DEBUG: WebSocket URL: {websocket_url}")
        
        logger.info(f"🔍 DEBUG: Generating TwiML response...")
        twiml_response = await twilio_service.generate_websocket_response(websocket_url)
        logger.info(f"🔍 DEBUG: TwiML response generated successfully")
        
        # Update session status
        call_session.status = "connected"
        logger.info(f"🔍 DEBUG: Session status updated to connected")
        
        logger.info(f"Call session {call_session_id} initiated successfully")
        
        return twiml_response
        
    except Exception as e:
        logger.error(f"🔍 DEBUG: Error handling incoming call: {str(e)}")
        logger.error(f"🔍 DEBUG: Error type: {type(e).__name__}")
        import traceback
        logger.error(f"🔍 DEBUG: Full traceback: {traceback.format_exc()}")
        return await twilio_service.generate_error_response(
            "Sorry, we're experiencing technical difficulties. Please try again later."
        )


@app.websocket("/media-stream/{call_session_id}")
async def media_stream_endpoint(websocket: WebSocket, call_session_id: str):
    """
    Enhanced WebSocket endpoint for real-time voice communication
    Connects Twilio call with OpenAI Real-time API and RAG system
    """
    logger.info(f"Client connected to media stream: {call_session_id}")
    await websocket.accept()
    
    try:
        # Get call session
        if call_session_id not in active_sessions:
            await websocket.close(code=4004, reason="Call session not found")
            return
        
        call_session = active_sessions[call_session_id]
        call_session.websocket_connected = True
        
        # Generate system message with vendor context
        system_message = await _generate_system_message(call_session.vendor_details)
        
        # Create OpenAI Real-time session
        openai_session = await openai_realtime_service.create_session(
            session_id=call_session_id,
            system_message=system_message,
            voice="alloy",
            temperature=0.8,
            initial_greeting="Hello! How can I assist you today?"
        )
        
        # Store session reference
        call_session.azure_session = openai_session
        
        async def handle_rag_integration():
            """Handle RAG queries and context injection"""
            try:
                async for event in openai_realtime_service.handle_openai_to_twilio(
                    openai_session, 
                    websocket,
                    on_speech_started=lambda data: logger.info("Speech interruption handled")
                ):
                    if event["type"] == "rag_query":
                        # Extract question from the event
                        question = event["data"].get("arguments", {}).get("question", "")
                        if question:
                            # Query RAG system
                            rag_response = await rag_service.query_knowledge_base(
                                call_session_id, question, include_sources=True
                            )
                            
                            # Inject context back into conversation
                            await openai_realtime_service.inject_rag_context(
                                openai_session, rag_response.answer, question
                            )
                            
                            # Log conversation
                            call_session.conversation_log.append({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "speaker": "system",
                                "text": f"RAG Query: {question}",
                                "rag_response": rag_response.answer
                            })
                    
                    elif event["type"] == "conversation_item":
                        # Log conversation items
                        item = event["data"].get("item", {})
                        if item.get("content"):
                            for content in item["content"]:
                                if content.get("type") == "text":
                                    call_session.conversation_log.append({
                                        "timestamp": datetime.now(timezone.utc).isoformat(),
                                        "speaker": item.get("role", "assistant"),
                                        "text": content.get("text", "")
                                    })
                        
            except Exception as e:
                logger.error(f"Error in RAG integration: {str(e)}")
        
        # Run both handlers concurrently
        await asyncio.gather(
            openai_realtime_service.handle_twilio_to_openai(
                openai_session, 
                websocket,
                on_session_start=lambda data: logger.info(f"OpenAI session started: {data['session_id']}")
            ),
            handle_rag_integration()
        )
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {call_session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {call_session_id}: {str(e)}")
    finally:
        # Cleanup
        await cleanup_call_session(call_session_id)


async def _generate_system_message(vendor_details: VendorDetails) -> str:
    """Generate system message based on vendor details"""
    base_message = f"""
    You are a professional AI customer service assistant for {vendor_details.vendor_name}.
    
    Your role is to:
    1. Greet customers warmly and professionally
    2. Listen to their questions and concerns
    3. Provide helpful and accurate information
    4. Use the knowledge base when you need specific information
    5. Be empathetic and solution-oriented
    6. Keep responses concise but complete
    
    Business Information:
    - Company: {vendor_details.vendor_name}
    - Business Type: {vendor_details.business_type or 'General Business'}
    """
    
    if vendor_details.business_policies:
        policies = json.dumps(vendor_details.business_policies, indent=2)
        base_message += f"\n\nBusiness Policies:\n{policies}"
    
    base_message += """
    
    When you need specific information that might be in the knowledge base, 
    feel free to search for it. I will provide you with relevant context to help answer the customer's questions.
    
    Always maintain a professional, friendly, and helpful tone.
    """
    
    return base_message.strip()


async def handle_rag_query(call_session_id: str, rag_query: Dict):
    """Handle RAG queries during conversation"""
    try:
        call_session = active_sessions.get(call_session_id)
        if not call_session:
            return
        
        question = rag_query.get("question", "")
        
        # Query RAG system
        rag_response = await rag_service.query_knowledge_base(
            call_session_id,
            question,
            include_sources=True
        )
        
        # Send response back to Azure Voice Agent
        await azure_voice_service.send_rag_context(
            call_session.azure_session,
            rag_response
        )
        
        logger.info(f"RAG query processed for session {call_session_id}")
        
    except Exception as e:
        logger.error(f"Error handling RAG query: {str(e)}")


async def cleanup_call_session(call_session_id: str):
    """Cleanup call session and save conversation summary"""
    try:
        if call_session_id not in active_sessions:
            return
        
        call_session = active_sessions[call_session_id]
        call_session.end_time = datetime.now(timezone.utc)
        call_session.status = "completed"
        
        # Calculate call duration
        duration = (call_session.end_time - call_session.start_time).total_seconds()
        
        # Generate conversation summary
        if call_session.conversation_log:
            summary = await azure_voice_service.generate_conversation_summary(
                call_session.conversation_log
            )
        else:
            summary = "No conversation recorded"
        
        # Save to database
        await supabase_service.save_call_metrics(
            user_id=call_session.user_id,
            call_id=call_session.call_sid,
            call_duration=int(duration),
            transcript=json.dumps(call_session.conversation_log),
            summary=summary,
            start_time=call_session.start_time,
            end_time=call_session.end_time,
            vendor_details=call_session.vendor_details
        )
        
        # Cleanup OpenAI/Azure session
        if hasattr(call_session, 'azure_session') and call_session.azure_session:
            if isinstance(call_session.azure_session, dict):
                # OpenAI Real-time session
                await openai_realtime_service.close_session(call_session.azure_session)
            else:
                # Legacy Azure session
                await azure_voice_service.cleanup_session(call_session.azure_session)
        
        # Remove from active sessions
        del active_sessions[call_session_id]
        
        # Disconnect WebSocket
        await websocket_manager.disconnect(call_session_id)
        
        logger.info(f"Call session {call_session_id} cleaned up successfully")
        
    except Exception as e:
        logger.error(f"Error cleaning up call session {call_session_id}: {str(e)}")


@app.get("/sessions")
async def get_active_sessions():
    """Get all active call sessions (for debugging)"""
    sessions = {}
    for session_id, session in active_sessions.items():
        sessions[session_id] = {
            "call_sid": session.call_sid,
            "caller": session.caller_number,
            "status": session.status,
            "start_time": session.start_time.isoformat(),
            "duration": (datetime.now(timezone.utc) - session.start_time).total_seconds()
        }
    return sessions


@app.post("/test-rag")
async def test_rag_endpoint(rag_request: RAGRequest):
    """Test endpoint for RAG system"""
    try:
        response = await rag_service.test_query(
            question=rag_request.question,
            sources=rag_request.sources,
            include_sources=rag_request.include_sources
        )
        return response
    except Exception as e:
        logger.error(f"RAG test error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/active-sessions")
async def get_active_sessions_alt():
    """Alternative endpoint for active sessions"""
    return {
        "sessions": [
            {
                "session_id": session_id,
                "phone_number": session.caller_number,
                "status": session.status,
                "start_time": session.start_time.isoformat(),
                "vendor_name": session.vendor_details.vendor_name if session.vendor_details else None
            }
            for session_id, session in active_sessions.items()
        ]
    }

@app.get("/call-metrics/{user_id}")
async def get_call_metrics(user_id: str):
    """Get call metrics for a specific user"""
    try:
        metrics = await supabase_service.get_user_statistics(user_id)
        return metrics
    except Exception as e:
        logger.error(f"Error fetching call metrics: {str(e)}")
        return {"error": "Failed to fetch call metrics"}

@app.post("/vendor-mapping")
async def create_vendor_mapping(request: Request):
    """Create vendor phone mapping"""
    try:
        data = await request.json()
        
        success = await supabase_service.create_vendor_mapping(
            user_id=data.get("user_id"),
            vendor_name=data.get("vendor_name"),
            phone_number=data.get("phone_number"),
            business_type=data.get("business_type"),
            business_policies=data.get("business_policies")
        )
        
        if success:
            return {
                "success": True,
                "vendor_id": f"vendor_{data.get('user_id')}_{data.get('phone_number', '').replace('+', '')}",
                "message": "Vendor mapping created successfully"
            }
        else:
            return {"success": False, "error": "Failed to create vendor mapping"}
            
    except Exception as e:
        logger.error(f"Error creating vendor mapping: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
