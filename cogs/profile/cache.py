"""Caching system for profile data."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from cachetools import TTLCache

logger = logging.getLogger('profile.cache')

class ProfileCache:
    """Improved caching system for profile data."""
    
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """
        Initialize the cache.
        
        Args:
            max_size: Maximum number of entries in the cache
            ttl: Time-to-live for cache entries in seconds
        """
        self.cache = TTLCache(maxsize=max_size, ttl=ttl)
        self.lock = asyncio.Lock()
        self._background_task = None
        self._hit_count = 0
        self._miss_count = 0
        logger.info(f"Initialized profile cache with size={max_size}, ttl={ttl}s")

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get an item from the cache."""
        async with self.lock:
            try:
                value = self.cache[key]
                self._hit_count += 1
                logger.debug(f"Cache hit for {key}")
                return value
            except KeyError:
                self._miss_count += 1
                logger.debug(f"Cache miss for {key}")
                return None

    async def set(self, key: str, value: Dict[str, Any]):
        """Set an item in the cache."""
        async with self.lock:
            self.cache[key] = value
            logger.debug(f"Cache set for {key}")

    async def invalidate(self, key: str):
        """Invalidate a specific cache entry."""
        async with self.lock:
            self.cache.pop(key, None)
            logger.debug(f"Cache invalidated for {key}")
            
    async def bulk_invalidate(self, keys: List[str]):
        """Invalidate multiple cache entries at once."""
        async with self.lock:
            for key in keys:
                self.cache.pop(key, None)
            logger.debug(f"Bulk invalidated {len(keys)} cache entries")
            
    async def prefetch(self, keys: List[str], fetcher_func: Callable):
        """
        Prefetch multiple items into cache using a single API call.
        
        Args:
            keys: List of keys to prefetch
            fetcher_func: Async function that takes a list of keys and returns a dict of {key: value}
        """
        missing_keys = []
        async with self.lock:
            for key in keys:
                if key not in self.cache:
                    missing_keys.append(key)
        
        if missing_keys:
            # Fetch all missing items in a batch
            items = await fetcher_func(missing_keys)
            
            # Store in cache
            async with self.lock:
                for key, item in items.items():
                    self.cache[key] = item
            
            logger.debug(f"Prefetched {len(items)} items into cache")

    async def start_cleanup(self):
        """Start background cache cleanup task."""
        if self._background_task is None:
            self._background_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Started cache cleanup task")

    async def stop_cleanup(self):
        """Stop background cache cleanup task."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
            logger.info("Stopped cache cleanup task")

    async def _cleanup_loop(self):
        """Periodically clean expired cache entries."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                async with self.lock:
                    before_count = len(self.cache)
                    # TTLCache handles expiration automatically, but we'll ensure cleanup
                    self.cache.expire()
                    after_count = len(self.cache)
                    if before_count > after_count:
                        logger.debug(f"Cache cleanup: removed {before_count - after_count} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache usage."""
        hit_rate = 0
        if (self._hit_count + self._miss_count) > 0:
            hit_rate = self._hit_count / (self._hit_count + self._miss_count)
            
        return {
            "size": len(self.cache),
            "max_size": self.cache.maxsize,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": hit_rate,
            "ttl": self.cache.ttl
        }