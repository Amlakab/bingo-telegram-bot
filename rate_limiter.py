# rate_limiter.py
from collections import defaultdict
import time
from datetime import datetime

class RateLimiter:
    def __init__(self, max_requests=10, time_window=60):
        """
        Initialize rate limiter
        
        Args:
            max_requests: Maximum requests allowed in time_window
            time_window: Time window in seconds (default: 60 seconds)
        """
        self.requests = defaultdict(list)
        self.max_requests = max_requests
        self.time_window = time_window
    
    def is_allowed(self, user_id):
        """
        Check if user is allowed to make a request
        
        Returns:
            bool: True if allowed, False if rate limited
            int: Remaining requests
        """
        now = time.time()
        
        # Clean old requests (older than time_window)
        self.requests[user_id] = [
            t for t in self.requests[user_id] 
            if now - t < self.time_window
        ]
        
        # Check if user exceeded limit
        if len(self.requests[user_id]) >= self.max_requests:
            return False, 0
        
        # Add current request
        self.requests[user_id].append(now)
        remaining = self.max_requests - len(self.requests[user_id])
        return True, remaining
    
    def get_remaining(self, user_id):
        """Get remaining requests for user"""
        now = time.time()
        self.requests[user_id] = [
            t for t in self.requests[user_id] 
            if now - t < self.time_window
        ]
        return self.max_requests - len(self.requests[user_id])
    
    def reset(self, user_id):
        """Reset rate limit for a user"""
        if user_id in self.requests:
            del self.requests[user_id]