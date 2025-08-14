import discord
from discord.ext import commands
import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .profile_events import ProfileEvent, ProfileEventType, ProfileUpdateBatch
# from .shared_utils import AsyncTimer, CodaAPIManager  # Removed CodaAPIManager references
from .shared_utils import AsyncTimer  # keep this if you still use it
from .coda_api import CodaAPIClient

logger = logging.getLogger('profile_sync')

class ProfileSyncManager:
    """Manages synchronization of profile data across systems."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.coda = CodaAPIClient(os.getenv('CODA_API_TOKEN'))
        self.update_queue: asyncio.Queue[ProfileUpdateBatch] = asyncio.Queue()
        self.processing = False
        self.batch_size = 10
        self.batch_delay = 1.0
        self.pending_updates: Dict[int, ProfileUpdateBatch] = {}
        self.lock = asyncio.Lock()
        
    async def start(self):
        self.processing = True
        asyncio.create_task(self._process_updates())
        
    async def stop(self):
        self.processing = False
        
    async def queue_update(self, event: ProfileEvent) -> bool:
        try:
            member_id = event.member_id
            async with self.lock:
                if member_id not in self.pending_updates:
                    self.pending_updates[member_id] = ProfileUpdateBatch(
                        member_id=member_id,
                        updates={},
                        events=[],
                        requires_role_sync=False
                    )
                batch = self.pending_updates[member_id]
                batch.events.append(event)

                updates = await self._event_to_updates(event)
                batch.updates.update(updates)
                batch.requires_role_sync = batch.requires_role_sync or self._requires_role_sync(event)

                if self._is_high_priority(event):
                    await self._process_batch(batch)
                    del self.pending_updates[member_id]
            return True
        except Exception as e:
            logger.error(f"Error queueing update: {e}")
            return False

    async def _process_updates(self):
        while self.processing:
            try:
                async with AsyncTimer("Profile Update Batch"):
                    async with self.lock:
                        batches = list(self.pending_updates.values())
                        self.pending_updates.clear()

                    if batches:
                        batches.sort(key=lambda b: self._get_batch_priority(b))
                        
                        for i in range(0, len(batches), self.batch_size):
                            chunk = batches[i:i + self.batch_size]
                            await asyncio.gather(*(self._process_batch(b) for b in chunk))
                            await asyncio.sleep(self.batch_delay)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in update processor: {e}")
                await asyncio.sleep(5)

    async def _process_batch(self, batch: ProfileUpdateBatch) -> bool:
        try:
            success = await self._update_coda(batch.member_id, batch.updates)
            if not success:
                return False
            if batch.requires_role_sync:
                await self._sync_roles(batch.member_id)
            await self._notify_cogs(batch)
            return True
        except Exception as e:
            logger.error(f"Error processing batch for {batch.member_id}: {e}")
            return False

    async def _update_coda(self, member_id: int, updates: Dict[str, Any]) -> bool:
        try:
            data = {
                'row': {
                    'cells': [
                        {'column': k, 'value': v}
                        for k, v in updates.items()
                    ]
                }
            }
            response = await self.coda.request(
                'PUT',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("PROFILE_TABLE_ID")}/rows/{member_id}',
                data=data
            )
            return response is not None
        except Exception as e:
            logger.error(f"Error updating Coda: {e}")
            return False

    async def _sync_roles(self, member_id: int):
        """Synchronize Discord roles with profile data, if needed."""
        try:
            guild = self.bot.get_guild(int(os.getenv('GUILD_ID')))
            if not guild:
                return
            member = guild.get_member(member_id)
            if not member:
                return
            profile_cog = self.bot.get_cog('ProfileManagerCog')
            if not profile_cog:
                return
            profile = await profile_cog.get_profile(member_id)
            if not profile:
                return
            
            # Implementation to sync roles – if actually used in your org logic
            # ...
        except Exception as e:
            logger.error(f"Error syncing roles for {member_id}: {e}")

    async def _notify_cogs(self, batch: ProfileUpdateBatch):
        """Notify other cogs of profile updates. Remove references to missing cogs."""
        try:
            events_by_type = {}
            for event in batch.events:
                events_by_type.setdefault(event.event_type, []).append(event)
                
            if ProfileEventType.MISSION_COMPLETE in events_by_type:
                mission_cog = self.bot.get_cog('MissionCog')
                if mission_cog:
                    await mission_cog.handle_profile_update(batch.member_id, events_by_type[ProfileEventType.MISSION_COMPLETE])

            if ProfileEventType.CERTIFICATION_GRANTED in events_by_type:
                ships_cog = self.bot.get_cog('ShipsCog')
                if ships_cog:
                    await ships_cog.handle_certification_update(batch.member_id, events_by_type[ProfileEventType.CERTIFICATION_GRANTED])

            if ProfileEventType.EVALUATION_COMPLETE in events_by_type:
                eval_cog = self.bot.get_cog('EvaluationCog')
                if eval_cog:
                    await eval_cog.handle_profile_update(batch.member_id, events_by_type[ProfileEventType.EVALUATION_COMPLETE])

        except Exception as e:
            logger.error(f"Error notifying cogs: {e}")

    async def _event_to_updates(self, event: ProfileEvent) -> Dict[str, Any]:
        updates = {}
        if event.event_type == ProfileEventType.ONBOARDING_COMPLETE:
            updates = {
                'status': 'Active',
                'join_date': event.timestamp.isoformat(),
                **event.data
            }
        elif event.event_type == ProfileEventType.MISSION_COMPLETE:
            # Example usage
            mission_data = event.data
            # ...
        return updates

    def _requires_role_sync(self, event: ProfileEvent) -> bool:
        # Mark this True if certain event changes require a role refresh
        return event.event_type in (
            ProfileEventType.ONBOARDING_COMPLETE,
            ProfileEventType.CERTIFICATION_GRANTED
        )

    def _is_high_priority(self, event: ProfileEvent) -> bool:
        # Return True for any event that must be processed immediately
        return False

    def _get_batch_priority(self, batch: ProfileUpdateBatch) -> int:
        # Basic numeric priority sorting logic
        return 0

# Removed any ExampleCog references if it was leftover or not relevant.
