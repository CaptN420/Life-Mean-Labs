"""
Request Queue - handles concurrent requests with proper serialization.
"""

import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Request:
    """A single debate request."""
    request_id: str
    user_input: str
    timestamp: datetime
    callback: Optional[Callable] = None
    
    def __hash__(self):
        return hash(self.request_id)
    
    def __eq__(self, other):
        if isinstance(other, Request):
            return self.request_id == other.request_id
        return False


class RequestQueue:
    """
    Central request queue for serializing debate requests.
    Ensures only one debate runs at a time (configurable).
    """
    
    def __init__(self, max_concurrent: int = 1):
        self.max_concurrent = max_concurrent
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processing = set()
        self._lock = asyncio.Lock()
        self._stats = {
            'total_requests': 0,
            'processed': 0,
            'failed': 0,
            'avg_wait_time_ms': 0.0
        }
    
    async def enqueue(self, request: Request) -> asyncio.Future:
        """
        Add a request to the queue and return a future for the result.
        
        Args:
            request: The debate request
            
        Returns:
            Future that will resolve with the result
        """
        self._stats['total_requests'] += 1
        
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        request.callback = lambda result: future.set_result(result) if not future.done() else None
        
        await self._queue.put(request)
        logger.info(f"Request {request.request_id} enqueued. Queue size: {self._queue.qsize()}")
        
        return future
    
    async def process_next(self) -> Optional[Request]:
        """Get the next request from the queue."""
        try:
            request = self._queue.get_nowait()
            async with self._lock:
                self._processing.add(request.request_id)
            return request
        except asyncio.QueueEmpty:
            return None
    
    def mark_complete(self, request_id: str) -> None:
        """Mark a request as completed."""
        async def _mark():
            async with self._lock:
                if request_id in self._processing:
                    self._processing.discard(request_id)
                self._stats['processed'] += 1
        
        asyncio.create_task(_mark())
    
    def mark_failed(self, request_id: str) -> None:
        """Mark a request as failed."""
        async def _mark():
            async with self._lock:
                if request_id in self._processing:
                    self._processing.discard(request_id)
                self._stats['failed'] += 1
        
        asyncio.create_task(_mark())
    
    @property
    def is_processing(self) -> bool:
        """Check if any requests are currently being processed."""
        return len(self._processing) > 0
    
    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()
    
    @property
    def stats(self) -> dict:
        """Get queue statistics."""
        return self._stats.copy()
