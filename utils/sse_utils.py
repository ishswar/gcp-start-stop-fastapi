"""
Server-Sent Events Utilities
Provides tools for streaming updates to clients
"""
from typing import List, Dict, Any, AsyncGenerator
import asyncio
import json
import time
import uuid
from fastapi import Request
from fastapi.responses import StreamingResponse
import logging

logger = logging.getLogger(__name__)

class SSEEvent:
    """Server-Sent Event class for formatting events"""
    
    def __init__(self, data: Any, event: str = None, id: str = None, retry: int = None):
        """
        Initialize an SSE event
        
        Args:
            data: Event data (will be JSON serialized)
            event: Optional event type
            id: Optional event ID
            retry: Optional reconnection time in milliseconds
        """
        self.data = data
        self.event = event
        self.id = id or str(uuid.uuid4())
        self.retry = retry
        
    def encode(self) -> str:
        """Encode the event as a string according to SSE format"""
        message = []
        
        if self.id:
            message.append(f"id: {self.id}")
            
        if self.event:
            message.append(f"event: {self.event}")
            
        if self.retry:
            message.append(f"retry: {self.retry}")
            
        if self.data:
            # Serialize data if it's not a string
            if not isinstance(self.data, str):
                payload = json.dumps(self.data)
            else:
                payload = self.data
                
            # Split payload by line and prefix each with "data: "
            for line in payload.split("\n"):
                message.append(f"data: {line}")
        else:
            message.append("data: ")
            
        return "\n".join(message) + "\n\n"

class SSEManager:
    """Manages SSE connections and event broadcasting"""
    
    def __init__(self):
        """Initialize the SSE manager"""
        self.operation_events = {}  # Dict to store events by operation ID
        
    def create_operation_stream(self, operation_id: str) -> None:
        """Create a new event stream for an operation"""
        if operation_id not in self.operation_events:
            self.operation_events[operation_id] = []
            logger.info(f"Created SSE stream for operation {operation_id}")
        
    def add_event(self, operation_id: str, event_type: str, data: Any) -> None:
        """Add an event to an operation's stream"""
        if operation_id not in self.operation_events:
            self.create_operation_stream(operation_id)
            
        event = SSEEvent(data=data, event=event_type)
        self.operation_events[operation_id].append(event)
        logger.debug(f"Added event to stream {operation_id}: {event_type}")
        
    def add_progress_update(self, operation_id: str, step: str, progress: int, message: str, status: str = "running") -> None:
        """
        Add a progress update event
        
        Args:
            operation_id: The operation ID
            step: Current step name
            progress: Progress percentage (0-100)
            message: Progress message
            status: Status (running, success, error)
        """
        data = {
            "step": step,
            "progress": progress,
            "message": message,
            "status": status,
            "timestamp": time.time()
        }
        self.add_event(operation_id, "progress", data)
        
    def add_completion_event(self, operation_id: str, success: bool, data: Any = None) -> None:
        """Add a completion event to an operation stream"""
        event_type = "success" if success else "error"
        self.add_event(operation_id, event_type, data)
        
        # Add a final progress event
        if success:
            self.add_progress_update(
                operation_id, "completed", 100, 
                "Operation completed successfully", "success"
            )
        else:
            self.add_progress_update(
                operation_id, "failed", 100, 
                "Operation failed", "error"
            )
        
    async def stream_events(self, operation_id: str, request: Request) -> AsyncGenerator[str, None]:
        """
        Stream events for a given operation
        
        Args:
            operation_id: The operation ID
            request: The request object to check for client disconnection
        """
        # Create the stream if it doesn't exist
        if operation_id not in self.operation_events:
            self.create_operation_stream(operation_id)
            
        # Send a connection established event
        yield SSEEvent(
            data={"message": "Connection established", "operation_id": operation_id},
            event="connected"
        ).encode()
        
        # Track which events we've already sent
        sent_events = 0
        
        # Stream until complete or client disconnects
        while True:
            # Check if there are new events
            current_events = self.operation_events.get(operation_id, [])
            
            # Send any new events
            for event in current_events[sent_events:]:
                yield event.encode()
                sent_events += 1
                
            # Check if we've reached the completion events
            if sent_events > 0 and any(e.event in ["success", "error"] 
                                    for e in current_events[sent_events-1:sent_events]):
                logger.info(f"SSE stream {operation_id} completed")
                break
                
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info(f"Client disconnected from SSE stream {operation_id}")
                break
                
            # Wait a bit before checking for new events
            await asyncio.sleep(0.5)
        
        # Clean up old streams (could add a background task to do this)
        if operation_id in self.operation_events and len(self.operation_events) > 100:
            del self.operation_events[operation_id]

# Global SSE manager instance
sse_manager = SSEManager()

def get_sse_response(operation_id: str, request: Request) -> StreamingResponse:
    """Create a streaming response for SSE"""
    return StreamingResponse(
        sse_manager.stream_events(operation_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable buffering in Nginx
        }
    ) 