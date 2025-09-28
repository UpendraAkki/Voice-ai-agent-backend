"""
RAG Service for integrating with the Azure RAG Function
"""

import logging
import json
import aiohttp
from typing import Dict, List, Any, Optional
from config import Settings
from models import RAGSource, RAGResponse

logger = logging.getLogger(__name__)


class RAGService:
    """Service for RAG system integration"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.rag_endpoint
        self.api_key = settings.rag_api_key
        self.session_knowledge_bases: Dict[str, List[RAGSource]] = {}
        
    async def health_check(self) -> Dict[str, Any]:
        """Check RAG service health"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                # Fix the URL - the base_url doesn't include /api/rag
                url = self.base_url
                if not url.endswith('/api/rag'):
                    url = f"https://{url}/api/rag"
                
                async with session.get(
                    f"{url}?action=stats",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "healthy",
                            "rag_stats": data
                        }
                    else:
                        return {
                            "status": "unhealthy",
                            "error": f"HTTP {response.status}"
                        }
        except Exception as e:
            logger.error(f"RAG health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def initialize_knowledge_base(self, session_id: str, sources: List[RAGSource]) -> bool:
        """Initialize knowledge base for a call session"""
        try:
            # Store sources for this session
            self.session_knowledge_bases[session_id] = sources
            
            # Add each document to the RAG system
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                for source in sources:
                    payload = {
                        "source": source.source,
                        "source_type": source.source_type,
                        "metadata": source.metadata or {}
                    }
                    
                    async with session.post(
                        f"{self.base_url}?action=add_document",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to add document {source.source}: HTTP {response.status}")
                        else:
                            result = await response.json()
                            logger.info(f"Added document: {result.get('message', 'Success')}")
            
            logger.info(f"Knowledge base initialized for session {session_id} with {len(sources)} sources")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing knowledge base for session {session_id}: {str(e)}")
            return False
    
    async def query_knowledge_base(
        self, 
        session_id: str, 
        question: str, 
        max_context_tokens: int = 3000,
        include_sources: bool = True
    ) -> RAGResponse:
        """Query the knowledge base for a specific session"""
        try:
            sources = self.session_knowledge_bases.get(session_id, [])
            
            payload = {
                "question": question,
                "sources": [source.dict() for source in sources],
                "max_context_tokens": max_context_tokens,
                "include_sources": include_sources
            }
            
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                async with session.post(
                    f"{self.base_url}?action=rag_query",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        return RAGResponse(
                            answer=data.get("answer", "I couldn't find relevant information."),
                            context=data.get("context", []),
                            sources=data.get("sources", []),
                            confidence=data.get("confidence")
                        )
                    else:
                        error_text = await response.text()
                        logger.error(f"RAG query failed: HTTP {response.status} - {error_text}")
                        return RAGResponse(
                            answer="I'm sorry, I'm having trouble accessing the information right now."
                        )
                        
        except Exception as e:
            logger.error(f"Error querying knowledge base: {str(e)}")
            return RAGResponse(
                answer="I'm experiencing technical difficulties. Please try rephrasing your question."
            )
    
    async def test_query(
        self, 
        question: str, 
        sources: Optional[List[RAGSource]] = None,
        include_sources: bool = True
    ) -> Dict[str, Any]:
        """Test RAG query endpoint"""
        try:
            payload = {
                "question": question,
                "include_sources": include_sources
            }
            
            if sources:
                payload["sources"] = [source.dict() for source in sources]
            
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                async with session.post(
                    f"{self.base_url}?action=rag_query",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    data = await response.json()
                    return {
                        "status_code": response.status,
                        "response": data
                    }
                    
        except Exception as e:
            logger.error(f"RAG test query error: {str(e)}")
            return {
                "status_code": 500,
                "error": str(e)
            }
    
    async def add_document_to_session(
        self, 
        session_id: str, 
        source: RAGSource
    ) -> bool:
        """Add a single document to an existing session"""
        try:
            # Add to session sources
            if session_id not in self.session_knowledge_bases:
                self.session_knowledge_bases[session_id] = []
            
            self.session_knowledge_bases[session_id].append(source)
            
            # Add to RAG system
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                payload = {
                    "source": source.source,
                    "source_type": source.source_type,
                    "metadata": source.metadata or {}
                }
                
                async with session.post(
                    f"{self.base_url}?action=add_document",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Document added to session {session_id}")
                        return True
                    else:
                        logger.error(f"Failed to add document: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error adding document to session {session_id}: {str(e)}")
            return False
    
    async def clear_session_knowledge_base(self, session_id: str) -> bool:
        """Clear knowledge base for a specific session"""
        try:
            # Remove from local storage
            if session_id in self.session_knowledge_bases:
                del self.session_knowledge_bases[session_id]
            
            # Clear RAG system (this affects all sessions, consider session isolation)
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                
                async with session.post(
                    f"{self.base_url}?action=clear",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Knowledge base cleared for session {session_id}")
                        return True
                    else:
                        logger.error(f"Failed to clear knowledge base: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Error clearing knowledge base for session {session_id}: {str(e)}")
            return False
    
    async def get_session_sources(self, session_id: str) -> List[RAGSource]:
        """Get all sources for a session"""
        return self.session_knowledge_bases.get(session_id, [])
