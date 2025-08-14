import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import time
import discord

logger = logging.getLogger('rate_limit')

class RateBucket:
    def __init__(self, bucket_hash: str):
        self.bucket_hash = bucket_hash
        self.limit = 0
        self.remaining = 0
        self.reset_time = 0
        self.reset_after = 0
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    def update_from_headers(self, headers: Dict[str, str]):
        """Update bucket information from Discord response headers."""
        try:
            if 'X-RateLimit-Limit' in headers:
                self.limit = int(headers['X-RateLimit-Limit'])
            if 'X-RateLimit-Remaining' in headers:
                self.remaining = int(headers['X-RateLimit-Remaining'])
            if 'X-RateLimit-Reset-After' in headers:
                self.reset_after = float(headers['X-RateLimit-Reset-After'])
                self.reset_time = time.time() + self.reset_after
            self.last_update = time.time()
        except (ValueError, KeyError) as e:
            logger.error(f"Error updating bucket from headers: {e}")

class RateLimitManager:
    def __init__(self):
        self.buckets: Dict[str, RateBucket] = {}
        self.global_lock = asyncio.Lock()
        self.global_limit_remaining = 50  # Discord's default global limit
        self.global_reset_after = 1.0
        self.last_global_reset = time.time()

    async def pre_request_check(self, bucket_hash: str = "default") -> float:
        """Check if we can make a request, return wait time if needed."""
        async with self.global_lock:
            now = time.time()
            
            # Check global rate limit
            if self.global_limit_remaining <= 0:
                time_since_reset = now - self.last_global_reset
                if time_since_reset < 1.0:
                    return 1.0 - time_since_reset
                self.global_limit_remaining = 50
                self.last_global_reset = now

            # Check bucket-specific rate limit
            bucket = self.buckets.get(bucket_hash)
            if bucket:
                async with bucket.lock:
                    if bucket.remaining <= 0 and now < bucket.reset_time:
                        return bucket.reset_time - now
                    if now >= bucket.reset_time:
                        bucket.remaining = bucket.limit

            self.global_limit_remaining -= 1
            return 0

    async def handle_429(self, response: Any, bucket_hash: str = "default") -> float:
        """Handle rate limit response, return retry_after time."""
        try:
            data = await response.json()
            retry_after = float(data.get('retry_after', 60))
            is_global = data.get('global', False)

            if is_global:
                logger.warning(f"Global rate limit hit, retry after {retry_after}s")
                async with self.global_lock:
                    self.global_limit_remaining = 0
                    self.global_reset_after = retry_after
                    self.last_global_reset = time.time() + retry_after
            else:
                logger.warning(f"Bucket rate limit hit for {bucket_hash}, retry after {retry_after}s")
                if bucket_hash not in self.buckets:
                    self.buckets[bucket_hash] = RateBucket(bucket_hash)
                bucket = self.buckets[bucket_hash]
                async with bucket.lock:
                    bucket.remaining = 0
                    bucket.reset_after = retry_after
                    bucket.reset_time = time.time() + retry_after

            # Add extra buffer to prevent edge cases
            return retry_after + 0.5

        except Exception as e:
            logger.error(f"Error handling 429 response: {e}")
            return 60.0  # Default fallback retry time

    async def update_bucket(self, headers: Dict[str, str], bucket_hash: str = "default"):
        """Update rate limit information from response headers."""
        if 'X-RateLimit-Bucket' in headers:
            actual_bucket = headers['X-RateLimit-Bucket']
            if actual_bucket != bucket_hash:
                bucket_hash = actual_bucket
                
        if bucket_hash not in self.buckets:
            self.buckets[bucket_hash] = RateBucket(bucket_hash)
            
        self.buckets[bucket_hash].update_from_headers(headers)

    async def execute_with_ratelimit(self, bucket_hash: str, coroutine, *args, **kwargs):
        """Execute a coroutine with rate limit handling."""
        max_retries = 5
        base_retry_delay = 5
        
        for attempt in range(max_retries):
            # Check if we need to wait before making request
            wait_time = await self.pre_request_check(bucket_hash)
            if wait_time > 0:
                logger.info(f"Rate limit precheck: waiting {wait_time:.2f}s before request")
                await asyncio.sleep(wait_time)

            try:
                response = await coroutine(*args, **kwargs)
                
                # Update rate limit info from headers
                if hasattr(response, 'headers'):
                    await self.update_bucket(dict(response.headers), bucket_hash)
                
                return response

            except discord.HTTPException as e:
                if e.status == 429:  # Rate limit hit
                    retry_after = await self.handle_429(e.response, bucket_hash)
                    logger.warning(
                        f"Rate limit hit on attempt {attempt + 1}/{max_retries}. "
                        f"Waiting {retry_after:.2f}s"
                    )
                    
                    # Add exponential backoff for repeated rate limits
                    total_wait = retry_after + (base_retry_delay * (2 ** attempt))
                    await asyncio.sleep(total_wait)
                    continue
                    
                raise  # Re-raise other HTTP exceptions

        raise RuntimeError(f"Max retries ({max_retries}) exceeded for rate limited request")
