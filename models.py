"""
Data models for the Voice Agent Middleware
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import json


class TwilioWebhookRequest(BaseModel):
    """Twilio webhook request data"""
    call_sid: str
    account_sid: str
    caller: str = Field(alias="From")
    called: str = Field(alias="To")
    call_status: str = Field(alias="CallStatus")
    direction: str = Field(alias="Direction")
    
    @classmethod
    def from_form_data(cls, form_data: Dict[str, str]) -> "TwilioWebhookRequest":
        """Create instance from Twilio form data"""
        return cls(
            call_sid=form_data.get("CallSid", ""),
            account_sid=form_data.get("AccountSid", ""),
            From=form_data.get("From", ""),  # Use alias name
            To=form_data.get("To", ""),      # Use alias name
            CallStatus=form_data.get("CallStatus", ""),  # Use alias name
            Direction=form_data.get("Direction", "")     # Use alias name
        )


class VendorDetails(BaseModel):
    """Vendor/business details"""
    user_id: str
    vendor_name: str
    vendor_id: str
    phone_number: str
    business_type: Optional[str] = None
    business_policies: Optional[Dict[str, Any]] = None
    api_version: Optional[str] = None
    additional_info: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage"""
        return self.dict()


class ConversationEntry(BaseModel):
    """Single conversation entry"""
    timestamp: str
    speaker: str  # 'user' or 'assistant'
    text: str
    confidence: Optional[float] = None


class CallSession(BaseModel):
    """Active call session"""
    session_id: str
    call_sid: str
    caller_number: str
    called_number: str
    user_id: Optional[str] = None
    vendor_details: Optional[VendorDetails] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str  # 'initiated', 'connected', 'in_progress', 'completed', 'failed'
    websocket_connected: bool = False
    azure_session: Optional[Any] = None
    conversation_log: List[ConversationEntry] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True


class RAGSource(BaseModel):
    """RAG source document"""
    source: str  # URL, file path, or text content
    source_type: str = "auto"  # text, pdf, docx, url, image, auto
    metadata: Optional[Dict[str, Any]] = None


class RAGRequest(BaseModel):
    """RAG query request"""
    question: str
    sources: Optional[List[RAGSource]] = None
    max_context_tokens: int = 3000
    include_sources: bool = True


class RAGResponse(BaseModel):
    """RAG query response"""
    answer: str
    context: List[str] = Field(default_factory=list)
    sources: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float] = None


class ConversationSummary(BaseModel):
    """Call conversation summary"""
    call_id: str
    summary: str
    key_points: List[str] = Field(default_factory=list)
    sentiment: Optional[str] = None
    resolution_status: Optional[str] = None
    follow_up_required: bool = False


class VoiceAgentConfig(BaseModel):
    """Voice agent configuration"""
    voice_id: str = "en-US-AriaNeural"
    speech_rate: float = 1.0
    speech_pitch: float = 1.0
    language: str = "en-US"
    personality: str = "professional"
    system_prompt: Optional[str] = None


class DatabaseCallMetrics(BaseModel):
    """Database model for call metrics"""
    id: Optional[str] = None
    user_id: str
    clerk_id: Optional[str] = None
    call_id: str
    call_duration: int  # in seconds
    transcript: str  # JSON string of conversation log
    summary: str
    start_time: str  # ISO format
    end_time: str  # ISO format
    vendor_details: str  # JSON string of vendor details
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DatabaseKnowledgeBase(BaseModel):
    """Database model for knowledge base documents"""
    id: Optional[str] = None
    user_id: str
    clerk_id: Optional[str] = None
    document_name: str
    document_url: str
    document_type: str
    file_size: int
    upload_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WebSocketMessage(BaseModel):
    """WebSocket message structure"""
    type: str  # 'audio', 'text', 'control', 'error'
    data: Any
    timestamp: Optional[str] = None
    session_id: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str  # 'healthy', 'degraded', 'unhealthy'
    message: Optional[str] = None
    timestamp: str
    details: Optional[Dict[str, Any]] = None
