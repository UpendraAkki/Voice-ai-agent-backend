"""
Supabase Service for database operations
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from supabase import create_client, Client
from config import Settings
from models import VendorDetails, DatabaseCallMetrics, DatabaseKnowledgeBase

logger = logging.getLogger(__name__)


class SupabaseService:
    """Service for Supabase database operations"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Client = None
        
    async def initialize(self) -> bool:
        """Initialize Supabase client"""
        try:
            # Create Supabase client with minimal options
            self.client = create_client(
                supabase_url=self.settings.supabase_url,
                supabase_key=self.settings.supabase_service_key  # Use service key for backend operations
            )
            logger.info("Supabase client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {str(e)}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Supabase connection health"""
        try:
            if not self.client:
                return {"status": "unhealthy", "error": "Client not initialized"}
            
            # Simple query to test connection
            result = self.client.table("call_metrics").select("count", count="exact").execute()
            
            return {
                "status": "healthy",
                "connection": "active",
                "total_records": result.count if hasattr(result, 'count') else 0
            }
        except Exception as e:
            logger.error(f"Supabase health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def get_vendor_details_by_phone(self, phone_number: str) -> Optional[VendorDetails]:
        """Get vendor details by phone number using existing database structure"""
        try:
            # Since you don't have a vendors table, we'll create a phone-to-user mapping
            # You can update this mapping based on your actual data
            
            # Phone number to user_id mapping (you can expand this or store it in a table)
            phone_to_user_mapping = {
                "+1234567890": "e357d1d4-a8d3-4e7d-b45e-bf8855332818",  # From your knowledge_base sample
                "+0987654321": "e357d1d4-a8d3-4e7d-b45e-bf8855332818",  # Test number
                # Add more mappings as needed
            }
            
            # Get user_id from mapping
            user_id = phone_to_user_mapping.get(phone_number)
            
            if not user_id:
                logger.warning(f"No user mapping found for phone {phone_number}")
                return None
            
            # Get user's knowledge base to verify they exist and get some details
            knowledge_base = await self.get_user_knowledge_base(user_id)
            
            if not knowledge_base:
                logger.warning(f"No knowledge base found for user {user_id}")
                return None
            
            # Create vendor details from available data
            vendor_details = VendorDetails(
                user_id=user_id,
                vendor_name=f"User {user_id[:8]}",  # Use first 8 chars of user_id as name
                vendor_id=f"vendor_{user_id[:8]}",
                phone_number=phone_number,
                business_type="General",  # Default business type
                business_policies={
                    "support_languages": ["English"],
                    "business_hours": "24/7",
                    "max_call_duration": 1800
                },
                api_version="1.0",
                additional_info={
                    "knowledge_base_documents": len(knowledge_base),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            )
            
            logger.info(f"Found vendor details for phone {phone_number}: user_id={user_id}, documents={len(knowledge_base)}")
            return vendor_details
                
        except Exception as e:
            logger.error(f"Error fetching vendor details: {str(e)}")
            return None
    
    async def get_user_knowledge_base(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all knowledge base documents for a user"""
        try:
            result = self.client.table("knowledge_base").select("*").eq("user_id", user_id).execute()
            
            if result.data:
                return result.data
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error fetching knowledge base for user {user_id}: {str(e)}")
            return []
    
    async def save_call_metrics(
        self,
        user_id: str,
        call_id: str,
        call_duration: int,
        transcript: str,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        vendor_details: VendorDetails
    ) -> bool:
        """Save call metrics to database"""
        try:
            call_data = {
                "user_id": user_id,
                "call_id": call_id,
                "call_duration": call_duration,
                "transcript": transcript,
                "summary": summary,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "vendor_details": json.dumps(vendor_details.to_dict()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            result = self.client.table("call_metrics").insert(call_data).execute()
            
            if result.data:
                logger.info(f"Call metrics saved successfully for call {call_id}")
                return True
            else:
                logger.error(f"Failed to save call metrics: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error saving call metrics: {str(e)}")
            return False
    
    async def get_call_metrics(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent call metrics for a user"""
        try:
            result = (
                self.client.table("call_metrics")
                .select("*")
                .eq("user_id", user_id)
                .order("start_time", desc=True)
                .limit(limit)
                .execute()
            )
            
            return result.data if result.data else []
            
        except Exception as e:
            logger.error(f"Error fetching call metrics: {str(e)}")
            return []
    
    async def get_call_by_id(self, call_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get specific call metrics by call ID"""
        try:
            result = (
                self.client.table("call_metrics")
                .select("*")
                .eq("call_id", call_id)
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            
            return result.data if result.data else None
            
        except Exception as e:
            logger.error(f"Error fetching call {call_id}: {str(e)}")
            return None
    
    async def update_call_summary(self, call_id: str, user_id: str, summary: str) -> bool:
        """Update call summary"""
        try:
            result = (
                self.client.table("call_metrics")
                .update({
                    "summary": summary,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                .eq("call_id", call_id)
                .eq("user_id", user_id)
                .execute()
            )
            
            if result.data:
                logger.info(f"Call summary updated for call {call_id}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error updating call summary: {str(e)}")
            return False
    
    async def add_knowledge_base_document(
        self,
        user_id: str,
        document_name: str,
        document_url: str,
        document_type: str,
        file_size: int,
        clerk_id: Optional[str] = None
    ) -> bool:
        """Add document to knowledge base"""
        try:
            doc_data = {
                "user_id": user_id,
                "clerk_id": clerk_id,
                "document_name": document_name,
                "document_url": document_url,
                "document_type": document_type,
                "file_size": file_size,
                "upload_date": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            result = self.client.table("knowledge_base").insert(doc_data).execute()
            
            if result.data:
                logger.info(f"Document added to knowledge base: {document_name}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error adding document to knowledge base: {str(e)}")
            return False
    
    async def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get user statistics"""
        try:
            # Get call statistics
            call_result = (
                self.client.table("call_metrics")
                .select("call_duration")
                .eq("user_id", user_id)
                .execute()
            )
            
            # Get document statistics  
            doc_result = (
                self.client.table("knowledge_base")
                .select("file_size")
                .eq("user_id", user_id)
                .execute()
            )
            
            calls = call_result.data if call_result.data else []
            documents = doc_result.data if doc_result.data else []
            
            total_calls = len(calls)
            total_duration = sum(call.get("call_duration", 0) for call in calls)
            avg_duration = total_duration / total_calls if total_calls > 0 else 0
            
            total_documents = len(documents)
            total_storage = sum(doc.get("file_size", 0) for doc in documents)
            
            return {
                "total_calls": total_calls,
                "total_duration": total_duration,
                "average_duration": avg_duration,
                "total_documents": total_documents,
                "total_storage": total_storage
            }
            
        except Exception as e:
            logger.error(f"Error fetching user statistics: {str(e)}")
            return {
                "total_calls": 0,
                "total_duration": 0,
                "average_duration": 0,
                "total_documents": 0,
                "total_storage": 0
            }
    
    async def create_vendor_mapping(
        self,
        user_id: str,
        vendor_name: str,
        phone_number: str,
        business_type: str = None,
        business_policies: Dict[str, Any] = None
    ) -> bool:
        """Create vendor phone mapping (you'll need to create this table)"""
        try:
            # This assumes you create a vendors table
            vendor_data = {
                "user_id": user_id,
                "vendor_name": vendor_name,
                "vendor_id": f"vendor_{user_id}_{phone_number.replace('+', '')}",
                "phone_number": phone_number,
                "business_type": business_type,
                "business_policies": business_policies,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            result = self.client.table("vendors").insert(vendor_data).execute()
            
            if result.data:
                logger.info(f"Vendor mapping created for {vendor_name}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error creating vendor mapping: {str(e)}")
            return False
    
    async def delete_call_metrics(self, call_id: str, user_id: str) -> bool:
        """Delete call metrics"""
        try:
            result = (
                self.client.table("call_metrics")
                .delete()
                .eq("call_id", call_id)
                .eq("user_id", user_id)
                .execute()
            )
            
            logger.info(f"Call metrics deleted for call {call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting call metrics: {str(e)}")
            return False
