# utils/sync_manager.py

import discord
from discord import app_commands
from discord.ext import commands  # Add this import
import asyncio
import logging
from typing import List, Dict, Set
import json
from datetime import datetime, timedelta
from pathlib import Path
from .daily_limit_manager import DailyLimitManager

logger = logging.getLogger('sync_commands')

BOT_OWNER_ID = 330171394019033099  # Your bot owner ID

def is_bot_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.id == BOT_OWNER_ID
    return app_commands.check(predicate)

class CommandSyncManager:
    def __init__(self, bot):
        self.bot = bot
        self.synced_commands: Dict[str, Set[str]] = {}
        self.sync_file = Path('data/synced_commands.json')
        self.sync_file.parent.mkdir(exist_ok=True)
        self.load_synced_commands()
        logger.info("CommandSyncManager initialized")

    def load_synced_commands(self):
        """Load previously synced commands from file."""
        try:
            if self.sync_file.exists():
                with open(self.sync_file, 'r') as f:
                    data = json.load(f)
                    self.synced_commands = {
                        cog: set(commands) 
                        for cog, commands in data.items()
                    }
                    logger.info(f"Loaded synced commands: {self.synced_commands}")
        except Exception as e:
            logger.error(f"Error loading synced commands: {e}")
            self.synced_commands = {}

    def save_synced_commands(self):
        """Save currently synced commands to file."""
        try:
            data = {
                cog: list(commands) 
                for cog, commands in self.synced_commands.items()
            }
            with open(self.sync_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("Saved synced commands")
        except Exception as e:
            logger.error(f"Error saving synced commands: {e}")

    async def is_command_synced(self, cog_name: str, command_name: str) -> bool:
        """Check if a command is already synced."""
        return (cog_name in self.synced_commands and 
                command_name in self.synced_commands[cog_name])

    def record_synced_command(self, cog_name: str, command_name: str):
        """Record that a command has been synced."""
        if cog_name not in self.synced_commands:
            self.synced_commands[cog_name] = set()
        self.synced_commands[cog_name].add(command_name)
        self.save_synced_commands()
        logger.info(f"Recorded synced command: {cog_name}.{command_name}")

    def get_synced_command_count(self) -> int:
        """Get total number of synced commands."""
        return sum(len(commands) for commands in self.synced_commands.values())

    def get_unsynced_commands(self, cog_name: str, commands: List[app_commands.Command]) -> List[app_commands.Command]:
        """Get list of commands that aren't synced yet."""
        if cog_name not in self.synced_commands:
            return commands
        
        return [
            cmd for cmd in commands 
            if cmd.name not in self.synced_commands[cog_name]
        ]

    def clear_synced_commands(self):
        """Clear the record of synced commands."""
        self.synced_commands.clear()
        self.save_synced_commands()
        logger.info("Cleared synced commands record")

    async def force_sync(self, guild_id: int) -> bool:
        """Force a sync of all commands."""
        try:
            guild = discord.Object(id=guild_id)
            
            # Clear existing commands
            self.bot.tree.clear_commands(guild=guild)
            
            # Sync with rate limiting
            await self.bot.rate_limiter.execute_with_ratelimit(
                'guild_commands',
                self.bot.tree.sync,
                guild=guild
            )
            
            # Clear and update our command state
            self.clear_synced_commands()
            
            # Fetch new commands and record them
            synced = await self.bot.tree.fetch_commands(guild=guild)
            for cmd in synced:
                cog_name = getattr(cmd, 'module', 'unknown')
                self.record_synced_command(cog_name, cmd.name)
            
            logger.info(f"Force synced {len(synced)} commands")
            return True
            
        except Exception as e:
            logger.error(f"Error during force sync: {e}")
            return False

class ManualSyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sync_commands",
        description="Manually sync slash commands to the current guild."
    )
    @is_bot_owner()
    async def sync_commands(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            success = await self.bot.sync_manager.force_sync(self.bot.guild_id)
            
            if success:
                await interaction.followup.send(
                    "✅ Successfully synced commands to the guild!\n"
                    "Note: It may take a few minutes for all commands to appear.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while syncing commands.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in sync_commands: {e}")
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

    @sync_commands.error
    async def sync_commands_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
        else:
            logger.error(f"Error in sync_commands: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ManualSyncCog(bot))
    logger.info("ManualSyncCog loaded")
