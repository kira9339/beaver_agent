import asyncio
import time
from typing import Optional
from collections import deque


class RateLimiter:
    """API rate limiter"""
    
    def __init__(
        self, 
        requests_per_minute: int = 60,
        tokens_per_minute: int = 90000
    ):
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        
        # request timestamp queue
        self.request_times = deque()
        # token usage records
        self.token_usage = deque()
        
        self._lock = asyncio.Lock()
    
    async def acquire(self, estimated_tokens: Optional[int] = None) -> None:
        """Acquire access permission"""
        async with self._lock:
            current_time = time.time()
            
            # clean up old records
            self._cleanup_old_records(current_time)
            
            # check request frequency limit
            if len(self.request_times) >= self.requests_per_minute:
                sleep_time = 60 - (current_time - self.request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    current_time = time.time()
                    self._cleanup_old_records(current_time)
            
            # check token usage limit
            if estimated_tokens:
                current_token_usage = sum(
                    usage for _, usage in self.token_usage
                )
                
                if current_token_usage + estimated_tokens > self.tokens_per_minute:
                    # wait until next minute
                    if self.token_usage:
                        sleep_time = 60 - (current_time - self.token_usage[0][0])
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                            current_time = time.time()
                            self._cleanup_old_records(current_time)
            
            # record this request
            self.request_times.append(current_time)
            if estimated_tokens:
                self.token_usage.append((current_time, estimated_tokens))
    
    def _cleanup_old_records(self, current_time: float) -> None:
        """Clean up old records"""
        # clean up requests older than 1 minute
        while self.request_times and current_time - self.request_times[0] > 60:
            self.request_times.popleft()
        
        # clean up token usage records older than 1 minute
        while self.token_usage and current_time - self.token_usage[0][0] > 60:
            self.token_usage.popleft()
    
    def get_status(self) -> dict:
        """Get current status"""
        current_time = time.time()
        self._cleanup_old_records(current_time)
        
        current_requests = len(self.request_times)
        current_tokens = sum(usage for _, usage in self.token_usage)
        
        return {
            "requests_used": current_requests,
            "requests_limit": self.requests_per_minute,
            "tokens_used": current_tokens,
            "tokens_limit": self.tokens_per_minute,
            "requests_remaining": max(0, self.requests_per_minute - current_requests),
            "tokens_remaining": max(0, self.tokens_per_minute - current_tokens),
        }