# cogs/sync_commands.py

import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio
import json
import os
from datetime import datetime, timedelta

logger = logging.getLogger('sync_commands')

class SyncCommandsCog(commands.Cog):
    """
    Cog for managing command syncing with strict rate limit protection
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sync_lock = asyncio.Lock()
        self.sync_file = "sync_status.json"
        self.status = self._load_status()
        
        # Strict rate limiting
        self.min_sync_interval = timedelta(days=1)  # Only sync once per day
        self.emergency_cooldown = False  # Set to True during rate limit emergencies
        
        if self.emergency_cooldown:
            logger.warning("⚠️ EMERGENCY COOLDOWN ACTIVE: Command syncing is severely restricted")
        
        # Set is_syncing based on time since last attempt
        last_attempt = self.status.get("last_attempt")
        self.is_syncing = False
        if last_attempt:
            last_time = datetime.fromtimestamp(last_attempt)
            self.is_syncing = (datetime.now() - last_time) < timedelta(minutes=10)
        
        logger.info(f"SyncCommandsCog initialized - Last sync: {self._get_last_sync_time_str()}")
    
    def _load_status(self):
        """Load sync status from file"""
        default_status = {
            "last_sync": None,
            "last_attempt": None,
            "commands_synced": 0,
            "total_syncs": 0,
            "errors": [],
            "known_commands": []
        }
        
        if os.path.exists(self.sync_file):
            try:
                with open(self.sync_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading sync status: {e}")
        
        return default_status
    
    def _save_status(self):
        """Save sync status to file"""
        try:
            with open(self.sync_file, 'w') as f:
                json.dump(self.status, f)
        except Exception as e:
            logger.error(f"Error saving sync status: {e}")
    
    def _get_last_sync_time_str(self):
        """Get a formatted string of when the last sync occurred"""
        if not self.status.get("last_sync"):
            return "Never"
            
        last_time = datetime.fromtimestamp(self.status["last_sync"])
        time_since = datetime.now() - last_time
        days = time_since.days
        hours = time_since.seconds // 3600
        
        if days > 0:
            return f"{last_time.strftime('%Y-%m-%d %H:%M:%S')} ({days}d {hours}h ago)"
        else:
            return f"{last_time.strftime('%Y-%m-%d %H:%M:%S')} ({hours}h ago)"
    
    def _record_error(self, error_msg):
        """Record an error in the status file"""
        errors = self.status.get("errors", [])
        errors.append({
            "time": datetime.now().timestamp(),
            "message": str(error_msg)
        })
        
        # Keep only the last 10 errors
        self.status["errors"] = errors[-10:]
        self._save_status()
    
    def is_bot_owner():
        """Check if the user is the bot owner"""
        async def predicate(interaction: discord.Interaction) -> bool:
            return await interaction.client.is_owner(interaction.user)
        return app_commands.check(predicate)
    
    @app_commands.command(
        name="sync_commands",
        description="Manually sync slash commands (owner only, use with caution)"
    )
    @is_bot_owner()
    async def sync_commands(self, interaction: discord.Interaction, force: bool = False):
        """
        Sync commands with strict rate limit protection
        
        Parameters:
        -----------
        force: bool
            If True, ignore cooldown restrictions (emergency use only)
        """
        await interaction.response.defer(ephemeral=True)
        
        # Block if already syncing
        if self.is_syncing:
            hours_ago = (datetime.now() - datetime.fromtimestamp(self.status.get("last_attempt", 0))).seconds / 3600
            await interaction.followup.send(
                f"⛔ A sync attempt is already in progress or was started {hours_ago:.1f} hours ago and may be stuck.\n"
                f"If you believe this is an error, restart the bot to clear the sync lock.",
                ephemeral=True
            )
            return
        
        # Check cooldown
        if not force and self.status.get("last_sync"):
            last_sync = datetime.fromtimestamp(self.status["last_sync"])
            time_since_sync = datetime.now() - last_sync
            
            # Emergency cooldown enforces a much longer period between syncs
            required_interval = timedelta(days=7) if self.emergency_cooldown else self.min_sync_interval
            
            if time_since_sync < required_interval:
                wait_time = required_interval - time_since_sync
                days = wait_time.days
                hours = wait_time.seconds // 3600
                
                await interaction.followup.send(
                    f"⚠️ **Rate Limit Protection**: Commands were synced {time_since_sync.days} days and "
                    f"{time_since_sync.seconds // 3600} hours ago.\n\n"
                    f"Please wait {days} days and {hours} hours before syncing again to avoid rate limits.\n\n"
                    "**Note**: Discord strictly limits how often you can sync commands. "
                    "Excessive syncing can block your bot for up to 24 hours.",
                    ephemeral=True
                )
                return
        
        # Perform the sync with lock protection
        async with self.sync_lock:
            try:
                self.is_syncing = True
                self.status["last_attempt"] = datetime.now().timestamp()
                self._save_status()
                
                await interaction.followup.send(
                    "🔄 Starting command sync... This may take a moment.",
                    ephemeral=True
                )
                
                # Get current commands
                current_commands = set(cmd.name for cmd in self.bot.tree.get_commands())
                known_commands = set(self.status.get("known_commands", []))
                
                # Only sync if there are new commands or force is used
                if not force and current_commands.issubset(known_commands):
                    self.is_syncing = False
                    await interaction.followup.send(
                        "✅ No new commands to sync. All commands are already registered with Discord.\n"
                        "Use `force=True` if you need to sync anyway.",
                        ephemeral=True
                    )
                    return
                
                # Log what's happening
                new_commands = current_commands - known_commands
                if new_commands:
                    logger.info(f"Found {len(new_commands)} new commands to sync: {', '.join(new_commands)}")
                
                # Make all commands global
                for cmd in self.bot.tree.get_commands():
                    cmd.guilds = None
                
                # Sync commands
                start_time = datetime.now()
                synced = await self.bot.tree.sync()
                elapsed = (datetime.now() - start_time).total_seconds()
                
                # Update status
                self.status["last_sync"] = datetime.now().timestamp()
                self.status["commands_synced"] = len(synced)
                self.status["total_syncs"] = self.status.get("total_syncs", 0) + 1
                self.status["known_commands"] = list(current_commands)
                self._save_status()
                
                message = (
                    f"✅ Successfully synced {len(synced)} commands in {elapsed:.2f} seconds!\n\n"
                    f"**New commands added**: {len(new_commands)}\n"
                    f"**Total syncs performed**: {self.status['total_syncs']}\n"
                    "Note: It may take a few minutes for all commands to appear in Discord."
                )
                
                if self.emergency_cooldown:
                    message += (
                        "\n\n⚠️ **EMERGENCY COOLDOWN ACTIVE**: You cannot sync again for 7 days "
                        "due to rate limit protection."
                    )
                
                await interaction.followup.send(message, ephemeral=True)
                logger.info(f"Command sync completed: {len(synced)} commands in {elapsed:.2f} seconds")
                
            except discord.HTTPException as e:
                error_msg = f"HTTP Error during sync: {e.status} {e.text}"
                logger.error(error_msg)
                self._record_error(error_msg)
                
                cooldown_msg = (
                    "You've hit Discord's rate limit for command registration.\n\n"
                    "**IMPORTANT**: Do not attempt to sync again for at least 24 hours or "
                    "your bot may be temporarily blocked from registering commands."
                )
                
                await interaction.followup.send(
                    f"❌ {error_msg}\n\n{cooldown_msg}",
                    ephemeral=True
                )
                
            except Exception as e:
                error_msg = f"Error during sync: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self._record_error(error_msg)
                
                await interaction.followup.send(
                    f"❌ An unexpected error occurred: {str(e)}",
                    ephemeral=True
                )
                
            finally:
                self.is_syncing = False
    
    @app_commands.command(
        name="sync_status",
        description="Check the status of command syncing"
    )
    async def sync_status_command(self, interaction: discord.Interaction):
        """Check the status of command syncing"""
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(
            title="Command Sync Status",
            description="Status of Discord slash command registration",
            color=discord.Color.blue()
        )
        
        # Last sync info
        if self.status.get("last_sync"):
            last_sync_time = datetime.fromtimestamp(self.status["last_sync"])
            time_since = datetime.now() - last_sync_time
            days = time_since.days
            hours = time_since.seconds // 3600
            
            embed.add_field(
                name="Last Successful Sync",
                value=f"{last_sync_time.strftime('%Y-%m-%d %H:%M:%S')} ({days}d {hours}h ago)",
                inline=False
            )
            
            embed.add_field(
                name="Commands Synced",
                value=str(self.status.get("commands_synced", 0)),
                inline=True
            )
            
            embed.add_field(
                name="Total Syncs",
                value=str(self.status.get("total_syncs", 0)),
                inline=True
            )
        else:
            embed.add_field(
                name="Last Sync",
                value="No sync has been performed yet",
                inline=False
            )
        
        # Command counts and status
        current_commands = len(self.bot.tree.get_commands())
        known_commands = len(self.status.get("known_commands", []))
        
        embed.add_field(
            name="Command Count",
            value=f"Current: {current_commands} | Registered: {known_commands}",
            inline=False
        )
        
        # Cooldown status
        if self.status.get("last_sync"):
            last_sync = datetime.fromtimestamp(self.status["last_sync"])
            time_since_sync = datetime.now() - last_sync
            
            required_interval = timedelta(days=7) if self.emergency_cooldown else self.min_sync_interval
            
            if time_since_sync < required_interval:
                wait_time = required_interval - time_since_sync
                days = wait_time.days
                hours = wait_time.seconds // 3600
                
                status = f"⏳ On cooldown ({days}d {hours}h remaining)"
            else:
                status = "✅ Ready to sync"
        else:
            status = "✅ Ready for first sync"
        
        embed.add_field(
            name="Current Status",
            value=status,
            inline=False
        )
        
        # Emergency status
        if self.emergency_cooldown:
            embed.add_field(
                name="⚠️ EMERGENCY MODE ACTIVE",
                value="Strict rate limiting is enabled to prevent Discord API blocks",
                inline=False
            )
        
        # Recent errors
        if self.status.get("errors"):
            recent_errors = self.status["errors"][-3:]  # Show last 3 errors
            error_text = ""
            
            for error in recent_errors:
                error_time = datetime.fromtimestamp(error["time"]).strftime("%Y-%m-%d %H:%M")
                error_msg = error["message"]
                if len(error_msg) > 100:
                    error_msg = error_msg[:97] + "..."
                error_text += f"• {error_time}: {error_msg}\n"
            
            embed.add_field(
                name="Recent Errors",
                value=error_text if error_text else "None",
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    """Set up the SyncCommandsCog"""
    await bot.add_cog(SyncCommandsCog(bot))
    logger.info("SyncCommandsCog loaded with emergency rate limit protection")