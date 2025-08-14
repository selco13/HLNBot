import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
import time
import json
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Union, Tuple

logger = logging.getLogger('command_registry')

class CommandRegistry:
    """
    Centralized registry for tracking and managing commands across all cogs.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.commands = {}  # Stores all registered commands and metadata
        self.sync_history = {}  # Tracks when commands were last synced
        self.registry_file = Path('data/command_registry.json')
        self.registry_file.parent.mkdir(exist_ok=True)
        self.sync_lock = asyncio.Lock()  # Prevent multiple syncs happening at once
        self.load_registry()
        logger.info("CommandRegistry initialized")

    def load_registry(self):
        """Load previously registered commands from file."""
        try:
            if self.registry_file.exists():
                with open(self.registry_file, 'r') as f:
                    data = json.load(f)
                    self.commands = data.get('commands', {})
                    self.sync_history = data.get('sync_history', {})
                logger.info(f"Loaded command registry with {len(self.commands)} commands")
            else:
                logger.info("No existing command registry found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading command registry: {e}")
            self.commands = {}
            self.sync_history = {}

    def save_registry(self):
        """Save the current registry state to file."""
        try:
            data = {
                'commands': self.commands,
                'sync_history': self.sync_history
            }
            with open(self.registry_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved command registry with {len(self.commands)} commands")
        except Exception as e:
            logger.error(f"Error saving command registry: {e}")

    def register_command(self, command: app_commands.Command, cog_name: str, is_global: bool = True):
        """
        Register a command with the registry.
        
        Args:
            command: The application command to register
            cog_name: The name of the cog this command belongs to
            is_global: Whether this command should be global (True) or guild-specific (False)
        """
        command_id = f"{cog_name}:{command.name}"
        self.commands[command_id] = {
            "name": command.name,
            "cog": cog_name,
            "description": command.description,
            "is_global": is_global,
            "synced": False,
            "last_updated": time.time()
        }
        logger.debug(f"Registered command {command_id} (global: {is_global})")
        self.save_registry()
        
        # Make command global if requested
        if is_global:
            command.guilds = None
            
        return command

    def register_group(self, group: app_commands.Group, cog_name: str, is_global: bool = True):
        """Register a command group and all its subcommands."""
        group_id = f"{cog_name}:{group.name}"
        self.commands[group_id] = {
            "name": group.name,
            "cog": cog_name,
            "description": group.description,
            "is_global": is_global,
            "is_group": True,
            "synced": False,
            "subcommands": [],
            "last_updated": time.time()
        }
        
        # Make group global if requested
        if is_global:
            group.guilds = None
            
        # Register all subcommands in this group
        for cmd in group.commands:
            sub_id = f"{group_id}:{cmd.name}"
            self.commands[sub_id] = {
                "name": cmd.name,
                "cog": cog_name,
                "parent": group.name,
                "description": cmd.description,
                "is_global": is_global,
                "synced": False,
                "last_updated": time.time()
            }
            self.commands[group_id]["subcommands"].append(cmd.name)
            
        logger.debug(f"Registered command group {group_id} with {len(group.commands)} subcommands (global: {is_global})")
        self.save_registry()
        return group

    def get_command_info(self, command_name: str, cog_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get information about a specific command."""
        if cog_name:
            command_id = f"{cog_name}:{command_name}"
            return self.commands.get(command_id)
        
        # If cog not specified, look in all cogs
        for cmd_id, cmd_info in self.commands.items():
            if cmd_info["name"] == command_name:
                return cmd_info
        return None
        
    def get_cog_commands(self, cog_name: str) -> List[Dict[str, Any]]:
        """Get all commands for a specific cog."""
        return [
            cmd_info for cmd_id, cmd_info in self.commands.items()
            if cmd_info["cog"] == cog_name
        ]
    
    async def sync_commands(self, guild_id: Optional[int] = None) -> Tuple[int, List[str]]:
        """
        Sync all commands to Discord.
        
        Args:
            guild_id: If provided, syncs to the specified guild; otherwise syncs globally
            
        Returns:
            Tuple of (number of commands synced, list of error messages)
        """
        async with self.sync_lock:
            try:
                # Start with clean tree if doing a full sync
                self.bot.tree.clear_commands(guild=discord.Object(id=guild_id) if guild_id else None)
                
                # Check if we're doing a global sync
                is_global_sync = guild_id is None
                
                # Set sync target for log messages
                sync_target = "globally" if is_global_sync else f"to guild {guild_id}"
                logger.info(f"Starting command sync {sync_target}")
                
                # If we have a guild ID, create the guild object for syncing
                guild = discord.Object(id=guild_id) if guild_id else None
                
                # Sync commands with rate limiting
                try:
                    # If your bot has a rate limiter, use it; otherwise just sync
                    if hasattr(self.bot, 'rate_limiter'):
                        synced = await self.bot.rate_limiter.execute_with_ratelimit(
                            'guild_commands' if guild_id else 'global_commands',
                            self.bot.tree.sync,
                            guild=guild
                        )
                    else:
                        synced = await self.bot.tree.sync(guild=guild)
                    
                    # Update sync history
                    sync_key = str(guild_id) if guild_id else "global"
                    self.sync_history[sync_key] = {
                        "last_sync": time.time(),
                        "commands_synced": len(synced),
                        "success": True
                    }
                    
                    # Mark all relevant commands as synced
                    synced_names = [cmd.name for cmd in synced]
                    for cmd_id, cmd_info in self.commands.items():
                        if cmd_info["name"] in synced_names:
                            if (is_global_sync and cmd_info["is_global"]) or (guild_id and not cmd_info["is_global"]):
                                self.commands[cmd_id]["synced"] = True
                    
                    self.save_registry()
                    logger.info(f"Successfully synced {len(synced)} commands {sync_target}")
                    return len(synced), []
                    
                except discord.HTTPException as e:
                    error_msg = f"HTTP error syncing commands {sync_target}: {e}"
                    logger.error(error_msg)
                    
                    # Update sync history with failure
                    sync_key = str(guild_id) if guild_id else "global"
                    self.sync_history[sync_key] = {
                        "last_sync": time.time(),
                        "success": False,
                        "error": str(e)
                    }
                    self.save_registry()
                    
                    return 0, [error_msg]
                    
            except Exception as e:
                error_msg = f"Error syncing commands {sync_target}: {e}"
                logger.error(error_msg, exc_info=True)
                return 0, [error_msg]

    def make_all_commands_global(self):
        """Set all commands to be global."""
        try:
            # Update all commands in the registry
            for cmd_id in self.commands:
                self.commands[cmd_id]["is_global"] = True
            
            # Update all commands in the command tree
            for command in self.bot.tree.get_commands():
                command.guilds = None
                logger.info(f"Set '{command.name}' as global")
            
            self.save_registry()
            logger.info("All commands set to global")
            return True
        except Exception as e:
            logger.error(f"Error making commands global: {e}")
            return False

    def get_all_commands(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered commands."""
        return self.commands
    
    def get_sync_status(self, guild_id: Optional[int] = None) -> Dict[str, Any]:
        """Get the sync status for global or guild-specific commands."""
        sync_key = str(guild_id) if guild_id else "global"
        return self.sync_history.get(sync_key, {
            "last_sync": None,
            "commands_synced": 0,
            "success": False
        })