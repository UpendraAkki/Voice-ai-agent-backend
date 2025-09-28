"""
Configuration settings for the Voice Agent Middleware
"""

import os
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load environment variables from .env.local in project root
project_root = Path(__file__).parent.parent
env_local_path = project_root / ".env.local"
if env_local_path.exists():
    load_dotenv(env_local_path)
    print(f"✅ Loaded environment variables from {env_local_path}")

# Also load from backend .env if it exists
backend_env_path = Path(__file__).parent / ".env"
if backend_env_path.exists():
    load_dotenv(backend_env_path)
    print(f"✅ Loaded environment variables from {backend_env_path}")


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Server settings
    base_url: str = Field(default="http://localhost:8000", env="BASE_URL")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Twilio settings
    twilio_account_sid: str = Field(default="demo_account_sid", env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="demo_auth_token", env="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(default="+1234567890", env="TWILIO_PHONE_NUMBER")
    
    # Azure AI Foundry settings (supporting multiple environment variable names)
    azure_speech_key: str = Field(default="demo_speech_key")
    azure_speech_region: str = Field(default="eastus")
    azure_voice_endpoint: str = Field(default="https://demo.endpoint.com")
    azure_voice_api_key: str = Field(default="demo_api_key")
    ai_foundry_project_name: str = Field(default="demo_project")
    ai_foundry_agent_id: str = Field(default="demo_agent")
    azure_voice_api_version: str = Field(default="2024-10-01")
    
    # OpenAI Real-time API settings (using dedicated Azure OpenAI WebSocket API)
    openai_api_key: str = Field(default="demo_openai_key")
    openai_realtime_endpoint: str = Field(
        default="wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    )
    azure_openai_websocket_endpoint: str = Field(
        default="wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    )
    azure_openai_websocket_api_key: str = Field(default="demo_websocket_key")
    
    # RAG System settings
    rag_endpoint: str = Field(
        default="https://rag-function-app-1758997681.azurewebsites.net/api/rag",
        env="RAG_ENDPOINT"
    )
    rag_api_key: Optional[str] = Field(default=None, env="RAG_API_KEY")
    
    # Supabase settings (supporting multiple environment variable names)
    supabase_url: str = Field(default="https://demo.supabase.co")
    supabase_anon_key: str = Field(default="demo_anon_key")
    supabase_service_key: str = Field(default="demo_service_key")
    
    def __init__(self, **kwargs):
        # Handle Azure Voice Live API from .env.local
        if not kwargs.get('azure_voice_endpoint'):
            kwargs['azure_voice_endpoint'] = (
                os.getenv('AZURE_VOICE_LIVE_ENDPOINT') or 
                os.getenv('AZURE_VOICE_ENDPOINT') or 
                "https://demo.endpoint.com"
            )
        
        if not kwargs.get('azure_voice_api_key'):
            kwargs['azure_voice_api_key'] = (
                os.getenv('AZURE_VOICE_LIVE_API_KEY') or 
                os.getenv('AZURE_VOICE_API_KEY') or 
                "demo_api_key"
            )
        
        # Handle AI Foundry settings
        if not kwargs.get('ai_foundry_project_name'):
            kwargs['ai_foundry_project_name'] = os.getenv('AI_FOUNDRY_PROJECT_NAME', 'demo_project')
        
        if not kwargs.get('ai_foundry_agent_id'):
            kwargs['ai_foundry_agent_id'] = os.getenv('AI_FOUNDRY_AGENT_ID', 'demo_agent')
        
        if not kwargs.get('azure_voice_api_version'):
            kwargs['azure_voice_api_version'] = os.getenv('AZURE_VOICE_LIVE_API_VERSION', '2024-10-01')
        
        # Handle OpenAI API key (use dedicated WebSocket API key)
        if not kwargs.get('openai_api_key'):
            kwargs['openai_api_key'] = (
                os.getenv('AZURE_OPENAI_WEBSOCKET_API_KEY') or 
                os.getenv('AZURE_VOICE_LIVE_API_KEY') or 
                os.getenv('OPENAI_API_KEY') or 
                "demo_openai_key"
            )
        
        # Handle Azure OpenAI WebSocket API key (dedicated for WebSocket connections)
        if not kwargs.get('azure_openai_websocket_api_key'):
            kwargs['azure_openai_websocket_api_key'] = (
                os.getenv('AZURE_OPENAI_WEBSOCKET_API_KEY') or 
                os.getenv('AZURE_VOICE_LIVE_API_KEY') or 
                "demo_websocket_key"
            )
        
        # Handle OpenAI Real-time endpoint (use dedicated WebSocket endpoint)
        if not kwargs.get('openai_realtime_endpoint'):
            # First try dedicated WebSocket endpoint variable
            ws_endpoint = os.getenv('AZURE_OPENAI_WEBSOCKET_ENDPOINT')
            if ws_endpoint:
                kwargs['openai_realtime_endpoint'] = ws_endpoint
            else:
                # Fallback to standard OpenAI endpoint
                kwargs['openai_realtime_endpoint'] = (
                    os.getenv('OPENAI_REALTIME_ENDPOINT') or 
                    "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
                )
        
        # Handle Azure OpenAI WebSocket endpoint (separate from Azure Voice Live endpoint)
        if not kwargs.get('azure_openai_websocket_endpoint'):
            kwargs['azure_openai_websocket_endpoint'] = (
                os.getenv('AZURE_OPENAI_WEBSOCKET_ENDPOINT') or 
                kwargs.get('openai_realtime_endpoint') or
                "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
            )
        
        # Handle Supabase URL from multiple possible env vars
        if not kwargs.get('supabase_url'):
            kwargs['supabase_url'] = (
                os.getenv('NEXT_PUBLIC_SUPABASE_URL') or 
                os.getenv('SUPABASE_URL') or 
                "https://demo.supabase.co"
            )
        
        # Handle Supabase anon key from multiple possible env vars  
        if not kwargs.get('supabase_anon_key'):
            kwargs['supabase_anon_key'] = (
                os.getenv('NEXT_PUBLIC_SUPABASE_ANON_KEY') or 
                os.getenv('SUPABASE_ANON_KEY') or 
                "demo_anon_key"
            )
        
        # Handle Supabase service key from multiple possible env vars
        if not kwargs.get('supabase_service_key'):
            kwargs['supabase_service_key'] = (
                os.getenv('SUPABASE_SERVICE_ROLE_KEY') or 
                os.getenv('SUPABASE_SERVICE_KEY') or 
                "demo_service_key"
            )
        
        super().__init__(**kwargs)
    
    # Legacy OpenAI settings (for conversation summaries)
    openai_model: str = Field(default="gpt-4o-mini", env="OPENAI_MODEL")
    
    # WebSocket settings
    websocket_timeout: int = Field(default=300, env="WEBSOCKET_TIMEOUT")  # 5 minutes
    max_connections: int = Field(default=100, env="MAX_CONNECTIONS")
    
    # Logging settings
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = [".env", "../.env.local", ".env.local"]  # Check backend .env, then project root .env.local
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra environment variables not defined in the model


# Global settings instance - instantiated after environment variables are loaded
settings = Settings()
