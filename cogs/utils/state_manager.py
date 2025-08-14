# Create in cogs/utils/state_manager.py

import json
import os
import asyncio
import logging
from typing import Any, Dict, List, Optional, Set
import time

logger = logging.getLogger('bot.state')

class StateManager:
    """
    Manages shared state between cogs with persistence and caching.
    """
    def __init__(self, bot, cache_ttl=300, save_interval=60):
        self.bot = bot
        self.cache_ttl = cache_ttl  # Time to live for cache entries in seconds
        self.save_interval = save_interval  # How often to save state to disk in seconds
        self._state = {}
        self._cache = {}  # Cache with timestamps
        self._cache_hits = 0
        self._cache_misses = 0
        self._dirty = False  # Tracks if state has changed since last save
        self._state_file = "bot_state.json"
        self._lock = asyncio.Lock()
        
        # Load initial state from disk
        self._load_state()
        
        # Start the background save task
        self._save_task = None
        logger.info("State manager initialized")
        
    def start(self):
        """Start the background save task."""
        if self._save_task is None:
            self._save_task = asyncio.create_task(self._background_save())
            logger.info("Started background state saving task")
            
    async def stop(self):
        """Stop the background save task and save state."""
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
            self._save_task = None
            
        # Final save
        await self._save_state()
        logger.info("State manager stopped")
        
    def _load_state(self):
        """Load state from disk."""
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, 'r') as f:
                    self._state = json.load(f)
                logger.info(f"Loaded state from {self._state_file} with {len(self._state)} keys")
            except Exception as e:
                logger.error(f"Error loading state: {e}")
                self._state = {}
        else:
            logger.info("No state file found, starting with empty state")
            self._state = {}
            
    async def _save_state(self):
        """Save state to disk."""
        async with self._lock:
            if not self._dirty:
                return
                
            try:
                with open(self._state_file, 'w') as f:
                    json.dump(self._state, f)
                self._dirty = False
                logger.info(f"Saved state to {self._state_file}")
            except Exception as e:
                logger.error(f"Error saving state: {e}")
                
    async def _background_save(self):
        """Background task to periodically save state."""
        try:
            while True:
                await asyncio.sleep(self.save_interval)
                await self._save_state()
                # Clean expired cache entries
                self._clean_cache()
        except asyncio.CancelledError:
            logger.info("Background save task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in background save task: {e}")
            
    def _clean_cache(self):
        """Remove expired cache entries."""
        now = time.time()
        expired_keys = [k for k, (_, timestamp) in self._cache.items() 
                       if now - timestamp > self.cache_ttl]
        
        for key in expired_keys:
            del self._cache[key]
            
        if expired_keys:
            logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")
            
    async def get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get a value from state."""
        cache_key = f"{namespace}:{key}"
        
        # Check cache first
        if cache_key in self._cache:
            value, timestamp = self._cache[cache_key]
            # Check if expired
            if time.time() - timestamp <= self.cache_ttl:
                self._cache_hits += 1
                return value
                
        # Cache miss or expired
        self._cache_misses += 1
        
        async with self._lock:
            # Namespace doesn't exist
            if namespace not in self._state:
                return default
                
            # Key doesn't exist
            if key not in self._state[namespace]:
                return default
                
            value = self._state[namespace][key]
            
            # Update cache
            self._cache[cache_key] = (value, time.time())
            
            return value
            
    async def set(self, namespace: str, key: str, value: Any) -> None:
        """Set a value in state."""
        async with self._lock:
            # Ensure namespace exists
            if namespace not in self._state:
                self._state[namespace] = {}
                
            # Set value
            self._state[namespace][key] = value
            self._dirty = True
            
            # Update cache
            self._cache[f"{namespace}:{key}"] = (value, time.time())
            
    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a key from state. Returns True if key existed."""
        cache_key = f"{namespace}:{key}"
        
        # Remove from cache
        if cache_key in self._cache:
            del self._cache[cache_key]
            
        async with self._lock:
            # Namespace doesn't exist
            if namespace not in self._state:
                return False
                
            # Key doesn't exist
            if key not in self._state[namespace]:
                return False
                
            # Delete key
            del self._state[namespace][key]
            self._dirty = True
            
            # Clean up empty namespace
            if not self._state[namespace]:
                del self._state[namespace]
                
            return True
            
    async def get_namespace(self, namespace: str) -> Dict[str, Any]:
        """Get all keys and values in a namespace."""
        async with self._lock:
            if namespace not in self._state:
                return {}
                
            return dict(self._state[namespace])
            
    async def delete_namespace(self, namespace: str) -> bool:
        """Delete an entire namespace. Returns True if namespace existed."""
        # Remove relevant cache entries
        cache_keys = [k for k in self._cache.keys() if k.startswith(f"{namespace}:")]
        for key in cache_keys:
            del self._cache[key]
            
        async with self._lock:
            if namespace not in self._state:
                return False
                
            del self._state[namespace]
            self._dirty = True
            return True
            
    def get_stats(self) -> Dict[str, Any]:
        """Get stats about the state manager."""
        return {
            "namespaces": len(self._state),
            "total_keys": sum(len(ns) for ns in self._state.values()),
            "cache_size": len(self._cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_ratio": (
                self._cache_hits / (self._cache_hits + self._cache_misses)
                if (self._cache_hits + self._cache_misses) > 0
                else 0
            )
        }

# Example usage in cogs:

class MissionsCog(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.state = bot.services.get('state_manager')
        
    @app_commands.command(name="start_mission")
    async def start_mission(self, interaction: discord.Interaction, mission_name: str):
        # Create a new mission instance
        mission_id = f"mission_{int(time.time())}"
        
        mission_data = {
            "name": mission_name,
            "leader_id": interaction.user.id,
            "started_at": time.time(),
            "status": "active",
            "participants": [interaction.user.id],
            "objectives_completed": 0
        }
        
        # Store in state
        await self.state.set("missions", mission_id, mission_data)
        
        # Update user's active mission
        await self.state.set("user_missions", str(interaction.user.id), mission_id)
        
        await interaction.response.send_message(f"Mission '{mission_name}' has been started! ID: {mission_id}", ephemeral=True)
        
    @app_commands.command(name="join_mission")
    async def join_mission(self, interaction: discord.Interaction, mission_id: str):
        # Get mission data
        mission_data = await self.state.get("missions", mission_id)
        if not mission_data:
            await interaction.response.send_message("Mission not found.", ephemeral=True)
            return
            
        if mission_data["status"] != "active":
            await interaction.response.send_message("This mission is not active and cannot be joined.", ephemeral=True)
            return
            
        if interaction.user.id in mission_data["participants"]:
            await interaction.response.send_message("You are already participating in this mission.", ephemeral=True)
            return
            
        # Add user to mission
        mission_data["participants"].append(interaction.user.id)
        await self.state.set("missions", mission_id, mission_data)
        
        # Update user's active mission
        await self.state.set("user_missions", str(interaction.user.id), mission_id)
        
        # Notify mission leader
        leader = interaction.guild.get_member(mission_data["leader_id"])
        if leader:
            try:
                await leader.send(f"{interaction.user.display_name} has joined your mission '{mission_data['name']}'")
            except discord.Forbidden:
                pass  # Can't DM the leader
                
        await interaction.response.send_message(f"You have joined the mission '{mission_data['name']}'!", ephemeral=True)