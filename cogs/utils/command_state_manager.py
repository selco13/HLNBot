import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional
import discord
from discord import app_commands
import asyncio
from datetime import datetime

logger = logging.getLogger('command_state')

class CommandStateManager:
    def __init__(self, bot):
        self.bot = bot
        self.state_file = Path('data/command_state.json')
        self.state_file.parent.mkdir(exist_ok=True)
        self.synced_commands: Dict[str, Dict[str, str]] = {}  # cog -> {command_name: command_id}
        self.pending_syncs: Dict[str, Set[app_commands.Command]] = {}
        self.sync_lock = asyncio.Lock()
        self.last_sync: Optional[datetime] = None
        self.sync_cooldown = 5  # seconds
        self.batch_size = 25  # commands per sync
        self.load_state()

    def load_state(self):
        """Load previously synced command state along with the last sync time."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.synced_commands = data.get("synced_commands", {})
                    last_sync_str = data.get("last_sync")
                    if last_sync_str:
                        self.last_sync = datetime.fromisoformat(last_sync_str)
                logger.info(f"Loaded state for {len(self.synced_commands)} cogs")
            else:
                logger.info("No previous command state file found.")
        except Exception as e:
            logger.error(f"Error loading command state: {e}")
            self.synced_commands = {}

    def save_state(self):
        """Save current command state and last sync time."""
        try:
            data = {
                "synced_commands": self.synced_commands,
                "last_sync": self.last_sync.isoformat() if self.last_sync else None
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Saved command state")
        except Exception as e:
            logger.error(f"Error saving command state: {e}")

    def record_command(self, cog_name: str, command_name: str, command_id: str):
        """Record a synced command."""
        if cog_name not in self.synced_commands:
            self.synced_commands[cog_name] = {}
        self.synced_commands[cog_name][command_name] = command_id
        self.save_state()

    def is_command_synced(self, cog_name: str, command_name: str) -> bool:
        """Check if a command is already synced."""
        return cog_name in self.synced_commands and command_name in self.synced_commands[cog_name]

    async def queue_sync(self, cog_name: str, commands: List[app_commands.Command]):
        """Queue commands for syncing with batching.
           Only add commands that are not already marked as synced.
        """
        for cmd in commands:
            if not self.is_command_synced(cog_name, cmd.name):
                if cog_name not in self.pending_syncs:
                    self.pending_syncs[cog_name] = set()
                self.pending_syncs[cog_name].add(cmd)
        
        now = datetime.now()
        if not self.last_sync or (now - self.last_sync).total_seconds() > self.sync_cooldown:
            await self.process_sync_queue()

    async def process_sync_queue(self):
        """Process queued commands in batches."""
        async with self.sync_lock:
            if not self.pending_syncs:
                return

            try:
                guild = discord.Object(id=self.bot.guild_id)
                
                # Flatten all pending commands into one list
                all_commands = []
                for cmds in self.pending_syncs.values():
                    all_commands.extend(list(cmds))

                # Process in batches
                for i in range(0, len(all_commands), self.batch_size):
                    batch = all_commands[i:i + self.batch_size]
                    
                    # Optionally clear these commands from Discord before syncing
                    self.bot.tree.clear_commands(guild=guild, commands=batch)
                    
                    await self.bot.rate_limiter.execute_with_ratelimit(
                        'guild_commands',
                        self.bot.tree.sync,
                        guild=guild,
                        commands=batch
                    )
                    
                    # Fetch the synced commands and update state
                    synced = await self.bot.tree.fetch_commands(guild=guild)
                    for cmd in synced:
                        # Here we use a placeholder for cog name.
                        # If you store cog info on the command (e.g., in a 'module' attribute), adjust accordingly.
                        cog_name = getattr(cmd, 'module', 'unknown')
                        self.record_command(cog_name, cmd.name, str(cmd.id))
                    
                    if i + self.batch_size < len(all_commands):
                        await asyncio.sleep(2)

                self.pending_syncs.clear()
                self.last_sync = datetime.now()
                self.save_state()
            except Exception as e:
                logger.error(f"Error processing sync queue: {e}")
                raise

    def get_synced_command_count(self) -> int:
        """Get total number of synced commands."""
        return sum(len(commands) for commands in self.synced_commands.values())
