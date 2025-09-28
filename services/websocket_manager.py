"""
WebSocket Manager for handling real-time connections
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """Represents a WebSocket connection"""
    
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.connected_at = datetime.now(timezone.utc)
        self.is_active = True
        self.last_ping = datetime.now(timezone.utc)


class WebSocketManager:
    """Manages WebSocket connections for voice calls"""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.ping_interval = 30  # seconds
        self._ping_task = None
        
    async def connect(self, websocket: WebSocket, session_id: str) -> bool:
        """Accept a new WebSocket connection"""
        try:
            await websocket.accept()
            
            connection = WebSocketConnection(websocket, session_id)
            self.connections[session_id] = connection
            
            logger.info(f"WebSocket connected: {session_id}")
            
            # Start ping task if not already running
            if not self._ping_task or self._ping_task.done():
                self._ping_task = asyncio.create_task(self._ping_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting WebSocket {session_id}: {str(e)}")
            return False
    
    async def disconnect(self, session_id: str) -> bool:
        """Disconnect a WebSocket connection"""
        try:
            if session_id in self.connections:
                connection = self.connections[session_id]
                connection.is_active = False
                
                try:
                    await connection.websocket.close()
                except:
                    pass  # Connection might already be closed
                
                del self.connections[session_id]
                logger.info(f"WebSocket disconnected: {session_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket {session_id}: {str(e)}")
            return False
    
    async def disconnect_all(self) -> int:
        """Disconnect all WebSocket connections"""
        disconnected = 0
        
        session_ids = list(self.connections.keys())
        for session_id in session_ids:
            if await self.disconnect(session_id):
                disconnected += 1
        
        # Cancel ping task
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        
        logger.info(f"Disconnected {disconnected} WebSocket connections")
        return disconnected
    
    async def send_message(self, session_id: str, message: Dict) -> bool:
        """Send a message to a specific WebSocket"""
        try:
            if session_id not in self.connections:
                logger.warning(f"No WebSocket connection found for session {session_id}")
                return False
            
            connection = self.connections[session_id]
            if not connection.is_active:
                logger.warning(f"WebSocket connection is not active for session {session_id}")
                return False
            
            await connection.websocket.send_text(json.dumps(message))
            return True
            
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected during send: {session_id}")
            await self.disconnect(session_id)
            return False
        except Exception as e:
            logger.error(f"Error sending message to {session_id}: {str(e)}")
            return False
    
    async def send_audio(self, session_id: str, audio_data: str) -> bool:
        """Send audio data to a specific WebSocket"""
        try:
            message = {
                "event": "media",
                "media": {
                    "track": "outbound",
                    "chunk": "1",
                    "timestamp": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
                    "payload": audio_data
                }
            }
            
            return await self.send_message(session_id, message)
            
        except Exception as e:
            logger.error(f"Error sending audio to {session_id}: {str(e)}")
            return False
    
    async def send_text(self, session_id: str, text: str) -> bool:
        """Send text message to a specific WebSocket"""
        try:
            message = {
                "event": "text",
                "text": text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            return await self.send_message(session_id, message)
            
        except Exception as e:
            logger.error(f"Error sending text to {session_id}: {str(e)}")
            return False
    
    async def send_control(self, session_id: str, control_type: str, data: Dict = None) -> bool:
        """Send control message to a specific WebSocket"""
        try:
            message = {
                "event": "control",
                "type": control_type,
                "data": data or {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            return await self.send_message(session_id, message)
            
        except Exception as e:
            logger.error(f"Error sending control message to {session_id}: {str(e)}")
            return False
    
    async def broadcast_message(self, message: Dict, exclude_sessions: List[str] = None) -> int:
        """Broadcast a message to all connected WebSockets"""
        exclude_sessions = exclude_sessions or []
        sent_count = 0
        
        for session_id in list(self.connections.keys()):
            if session_id not in exclude_sessions:
                if await self.send_message(session_id, message):
                    sent_count += 1
        
        return sent_count
    
    async def get_connection_info(self, session_id: str) -> Optional[Dict]:
        """Get information about a WebSocket connection"""
        if session_id not in self.connections:
            return None
        
        connection = self.connections[session_id]
        return {
            "session_id": session_id,
            "connected_at": connection.connected_at.isoformat(),
            "is_active": connection.is_active,
            "last_ping": connection.last_ping.isoformat(),
            "duration": (datetime.now(timezone.utc) - connection.connected_at).total_seconds()
        }
    
    async def get_all_connections(self) -> List[Dict]:
        """Get information about all WebSocket connections"""
        connections_info = []
        
        for session_id in self.connections:
            info = await self.get_connection_info(session_id)
            if info:
                connections_info.append(info)
        
        return connections_info
    
    async def is_connected(self, session_id: str) -> bool:
        """Check if a WebSocket is connected and active"""
        if session_id not in self.connections:
            return False
        
        connection = self.connections[session_id]
        return connection.is_active
    
    async def _ping_loop(self):
        """Background task to ping all connections"""
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                
                # Get list of session IDs to avoid modification during iteration
                session_ids = list(self.connections.keys())
                
                for session_id in session_ids:
                    try:
                        if session_id in self.connections:
                            connection = self.connections[session_id]
                            
                            if connection.is_active:
                                # Send ping
                                await connection.websocket.ping()
                                connection.last_ping = datetime.now(timezone.utc)
                            else:
                                # Remove inactive connection
                                await self.disconnect(session_id)
                                
                    except Exception as e:
                        logger.warning(f"Ping failed for session {session_id}: {str(e)}")
                        await self.disconnect(session_id)
                
        except asyncio.CancelledError:
            logger.info("WebSocket ping loop cancelled")
        except Exception as e:
            logger.error(f"Error in WebSocket ping loop: {str(e)}")
    
    def get_stats(self) -> Dict:
        """Get WebSocket manager statistics"""
        active_connections = sum(1 for conn in self.connections.values() if conn.is_active)
        
        return {
            "total_connections": len(self.connections),
            "active_connections": active_connections,
            "ping_interval": self.ping_interval,
            "ping_task_running": self._ping_task and not self._ping_task.done()
        }
