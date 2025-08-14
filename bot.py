from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands
import logging
import logging.handlers
import os
import asyncio
import json
import time
from datetime import datetime
from functools import wraps

# Additional imports (optional, depending on your code structure)
from cogs.utils.shared_utils import BackupManager, SharedAuditLogger
from cogs.utils.profile_sync import ProfileSyncManager
from cogs.utils.coda_api import CodaAPIClient
from cogs.utils.daily_limit_manager import DailyLimitManager
from cogs.utils.rate_limit_manager import RateLimitManager
from cogs.utils.command_state_manager import CommandStateManager
from cogs.managers.nickname_manager import NicknameManager
# Add CodaManager import
from cogs.managers.coda_manager import CodaManager

##############################################################################
# Service Registry and Event System
##############################################################################
class ServiceRegistry:
    """
    A central registry for all services and managers to allow for looser coupling
    between cogs and services.
    """
    def __init__(self, bot):
        self.bot = bot
        self._services = {}
        
    def register(self, name, service):
        """Register a service with the registry."""
        self._services[name] = service
        logger.info(f"Registered service: {name}")
        
    def get(self, name):
        """Get a service from the registry."""
        if name not in self._services:
            logger.warning(f"Service not found: {name}")
            return None
        return self._services[name]
    
    def has(self, name):
        """Check if a service exists in the registry."""
        return name in self._services

class EventDispatcher:
    """
    Event system for inter-cog communication without direct dependencies.
    """
    def __init__(self, bot):
        self.bot = bot
        self._listeners = {}
        logger.info("Event dispatcher initialized")
        
    def register_listener(self, event_name, callback):
        """Register a callback for a specific event."""
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)
        logger.debug(f"Registered listener for event '{event_name}'")
        
    def remove_listener(self, event_name, callback):
        """Remove a callback from an event."""
        if event_name in self._listeners and callback in self._listeners[event_name]:
            self._listeners[event_name].remove(callback)
            logger.debug(f"Removed listener for event '{event_name}'")
            
    async def dispatch(self, event_name, *args, **kwargs):
        """Dispatch an event to all registered listeners."""
        if event_name not in self._listeners:
            logger.debug(f"No listeners for event '{event_name}'")
            return
            
        logger.debug(f"Dispatching event '{event_name}' to {len(self._listeners[event_name])} listeners")
        
        for callback in self._listeners[event_name]:
            try:
                # Schedule the callback to run but don't wait for it
                asyncio.create_task(callback(*args, **kwargs))
            except Exception as e:
                logger.error(f"Error dispatching event '{event_name}' to callback: {e}")

# Decorator for easier event listening
def event_listener(event_name):
    """Decorator to register a method as an event listener."""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            return await func(self, *args, **kwargs)
            
        # Add a flag for the event system to identify this method
        wrapper._event_listener = True
        wrapper._event_name = event_name
        return wrapper
    return decorator

##############################################################################
# State Manager for Shared State
##############################################################################
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
            
    async def get(self, namespace: str, key: str, default=None):
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
            
    async def set(self, namespace: str, key: str, value):
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
            
    async def delete(self, namespace: str, key: str):
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

##############################################################################
# 1) Logging setup
##############################################################################
def setup_logging():
    log_level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    
    detailed_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        filename='bot.log',
        encoding='utf-8',
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        mode='a'
    )
    file_handler.setFormatter(detailed_formatter)
    file_handler.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(simple_formatter)
    console_handler.setLevel(log_level)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress overly verbose logs
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    
    logger = logging.getLogger('bot')
    logger.setLevel(log_level)
    return logger

logger = setup_logging()
logger.info(f"Logging configured with level: {logging.getLevelName(logger.getEffectiveLevel())}")

##############################################################################
# 2) Load environment variables and check token
##############################################################################
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    logger.error("ERROR: DISCORD_BOT_TOKEN is empty or not set. Please check your .env file.")
    raise ValueError("DISCORD_BOT_TOKEN not found!")

logger.info(f"Token length is {len(TOKEN)} characters. (This is just to confirm non-empty.)")

# If you only want global commands, the guild IDs won't be used, but we'll still parse them in case
# you decide later to revert to guild-based commands.
def validate_guild_ids():
    guild_id_str = os.getenv('GUILD_ID')
    if not guild_id_str:
        logger.warning("GUILD_ID not set—only global commands will be used.")
        return []
    guild_ids = []
    for part in guild_id_str.split(','):
        part = part.strip()
        if part:
            try:
                gid = int(part)
                if gid <= 0:
                    raise ValueError("Guild IDs must be positive integers")
                guild_ids.append(gid)
            except ValueError:
                raise ValueError("GUILD_ID must contain valid positive integers, comma separated")
    return guild_ids

GUILD_IDS = validate_guild_ids()

def validate_env_variables():
    """Validate critical environment variables."""
    critical_vars = {
        'CODA_API_TOKEN': os.getenv('CODA_API_TOKEN'),
        'DOC_ID': os.getenv('DOC_ID'),
        'TABLE_ID': os.getenv('TABLE_ID')
    }
    
    for var_name, value in critical_vars.items():
        if value:
            logger.info(f"{var_name} length: {len(value)}")
        else:
            logger.error(f"{var_name} is not set!")
            
    table_id = critical_vars['TABLE_ID']
    if table_id and not table_id.startswith('grid-'):
        logger.warning(f"TABLE_ID format may be incorrect. Expected format: grid-XXXXXX, got: {table_id}")
        
    return all(critical_vars.values())

##############################################################################
# 3) Define Bot & Intents
##############################################################################
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
intents.messages = True
intents.voice_states = True
intents.reactions = True

class BaseCog(commands.Cog):
    """Base cog that provides standardized access to bot services."""
    
    def __init__(self, bot):
        self.bot = bot
        
    @property
    def coda_client(self):
        return self.bot.services.get('coda_client')
    
    @property
    def coda_manager(self):
        return self.bot.services.get('coda_manager')
        
    @property
    def audit_logger(self):
        return self.bot.services.get('audit_logger')
    
    @property
    def profile_sync(self):
        return self.bot.services.get('profile_sync')
    
    @property
    def rate_limiter(self):
        return self.bot.services.get('rate_limiter')
    
    @property
    def daily_limit_manager(self):
        return self.bot.services.get('daily_limit')
    
    @property
    def command_state(self):
        return self.bot.services.get('command_state')
    
    @property
    def sync_manager(self):
        return self.bot.services.get('sync_manager')
    
    @property
    def backup_manager(self):
        return self.bot.services.get('backup_manager')
    
    @property
    def nickname_manager(self):
        return self.bot.services.get('nickname_manager')
    
    @property
    def state_manager(self):
        return self.bot.services.get('state_manager')
    
    @property
    def event_dispatcher(self):
        return self.bot.services.get('event_dispatcher')
        
    def log_command_use(self, interaction, command_name):
        """Standard method to log command usage."""
        user = interaction.user
        if self.audit_logger:
            self.audit_logger.log(
                f"Command used: {command_name} by {user.name}#{user.discriminator} ({user.id})"
            )
        
    async def check_permissions(self, interaction, required_roles=None):
        """Standard method to check if a user has required roles."""
        if not required_roles:
            return True
            
        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in required_roles)
    
    async def dispatch_event(self, event_name: str, **kwargs):
        """
        Dispatch an event through the event dispatcher.
        Falls back to direct method calls for backward compatibility.
        """
        try:
            # Use event dispatcher if available
            if self.event_dispatcher:
                await self.event_dispatcher.dispatch(event_name, **kwargs)
                logger.debug(f"Dispatched event '{event_name}' through event dispatcher")
                return True
                
            # Fall back to direct method calls
            method_name = f"on_{event_name}"
            for cog_name, cog in self.bot.cogs.items():
                if hasattr(cog, method_name):
                    method = getattr(cog, method_name)
                    if callable(method):
                        try:
                            await method(**kwargs)
                            logger.debug(f"Called {cog_name}.{method_name} directly")
                        except Exception as e:
                            logger.error(f"Error calling {cog_name}.{method_name}: {e}")
                            
            return True
            
        except Exception as e:
            logger.error(f"Error dispatching event '{event_name}': {e}")
            return False

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            default_permissions=discord.Permissions(
                send_messages=True,
                read_messages=True,
                read_message_history=True,
                manage_messages=True,
                embed_links=True,
                external_emojis=True,
                add_reactions=True,
                view_channel=True
            ),
        )
        
        # Store guild IDs, though for global commands we won't use them
        self.guild_ids = GUILD_IDS
        # Fix: Add a singular guild_id attribute (e.g. first guild) for compatibility
        self.guild_id = self.guild_ids[0] if self.guild_ids else None
        
        self.initial_extensions = [
            'cogs.onboarding',
            'cogs.division_selection',
            'cogs.sync_commands',  # Single sync cog that replaces command_manager
            'cogs.aar',
            'cogs.banking',
            'cogs.administration',
            'cogs.fun',
            'cogs.news_updater',
            'cogs.payouts',
            'cogs.profile',
            'cogs.radio',
            'cogs.raid_protection',
            'cogs.welcome',
            'cogs.fleet_application',
            'cogs.ships',
            'cogs.eval',
            'cogs.srs',
            'cogs.missions',
            'cogs.mission_fleet_setup',
            'cogs.alert',
            'cogs.orders',
        ]

        # Initialize service registry
        self.services = ServiceRegistry(self)
        
        # Initialize event dispatcher
        self.event_dispatcher = EventDispatcher(self)
        self.services.register('event_dispatcher', self.event_dispatcher)
        
        # Initialize state manager
        self.state_manager = StateManager(self)
        self.services.register('state_manager', self.state_manager)
        
        # Initialize CodaAPIClient first
        coda_client = CodaAPIClient(os.getenv('CODA_API_TOKEN'))
        self.services.register('coda_client', coda_client)
        
        # Initialize CodaManager with the client
        coda_manager = CodaManager(
            coda_client=coda_client,
            doc_id=os.getenv('DOC_ID'),
            profile_table_id=os.getenv('TABLE_ID'),
            promotion_requests_table_id=os.getenv('PROMOTION_REQUESTS_TABLE_ID')
        )
        self.services.register('coda_manager', coda_manager)
        
        # Register all services in the registry
        self.services.register('daily_limit', DailyLimitManager())
        self.services.register('rate_limiter', RateLimitManager())
        self.services.register('command_state', CommandStateManager(self))
        self.services.register('profile_sync', ProfileSyncManager(self))
        self.services.register('audit_logger', SharedAuditLogger(self, int(os.getenv('AUDIT_LOG_CHANNEL_ID', 0))))
        self.services.register('backup_manager', BackupManager())
        
        # NicknameManager requires coda_manager, so get it from the registry
        self.services.register('nickname_manager', NicknameManager(coda_manager=coda_manager))
        
        # For backward compatibility, provide direct references to services
        self.daily_limit_manager = self.services.get('daily_limit')
        self.rate_limiter = self.services.get('rate_limiter')
        self.command_state = self.services.get('command_state')
        self.coda_client = coda_client  # Direct reference
        self.coda_manager = coda_manager  # Direct reference to new CodaManager
        self.profile_sync = self.services.get('profile_sync')
        self.audit_logger = self.services.get('audit_logger')
        self.backup_manager = self.services.get('backup_manager')
        self.nickname_manager = self.services.get('nickname_manager')
        
        logger.info("Bot services initialized")

    def get_all_commands(self):
        """Get all commands from all loaded cogs, for logging or reference."""
        all_commands = {}
        for cmd in self.tree.get_commands():
            all_commands[cmd.name] = 'unknown'
        for cog_name, cog in self.cogs.items():
            if hasattr(cog, 'get_app_commands'):
                for cmd in cog.get_app_commands():
                    clean_cog_name = cog_name.replace('Cog', '')
                    all_commands[cmd.name] = f"cogs.{clean_cog_name}"
        logger.info(
            f"Found {len(all_commands)} total commands across {len(set(all_commands.values()))} cogs"
        )
        return all_commands

    async def setup_hook(self):
        """
        Called automatically by discord.py when the bot starts.
        Modified to reduce command syncing and respect rate limits.
        """
        logger.info("Starting bot setup...")
        logger.info(f"DOC_ID length: {len(os.getenv('DOC_ID', ''))}")
        logger.info(f"TABLE_ID length: {len(os.getenv('TABLE_ID', ''))}")
        logger.info(f"CODA_API_TOKEN length: {len(os.getenv('CODA_API_TOKEN', ''))}")
    
        if not hasattr(self, 'tree') or self.tree is None:
            self.tree = app_commands.CommandTree(self)
            logger.info("Command tree initialized")
    
        # 1) Load all your extensions first
        for extension in self.initial_extensions:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension '{extension}'")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}")
    
        # 2) Wait a moment to ensure all commands are registered
        await asyncio.sleep(1)
        
        # 3) Get the SyncCommandsCog for sync_manager service
        sync_cog = self.get_cog('SyncCommandsCog')
        if sync_cog:
            self.services.register('sync_manager', sync_cog)
            logger.info("Registered SyncCommandsCog as sync_manager service")
        else:
            logger.warning("SyncCommandsCog not found for sync_manager service")
        
        # 4) Get commands registered by all cogs
        logger.info("Collecting commands...")
        all_commands = self.get_all_commands()
        logger.info(f"Collected {len(all_commands)} commands from cogs")
    
        # 5) Get all commands from the tree
        tree_commands = self.tree.get_commands()
        logger.info(f"Found {len(tree_commands)} commands in tree")
        
        # 6) Clear any existing guild restrictions to make all commands global
        for command in tree_commands:
            command.guilds = None  
            logger.info(f"Set '{command.name}' as global by overriding guilds = None")
        
        # 7) Register all event listeners from loaded cogs
        self._register_event_listeners()
        
        # 8) Start the state manager background task
        self.state_manager.start()
        
        # 9) Initialize CodaManager columns if available
        if hasattr(self.coda_manager, 'initialize_columns'):
            try:
                await self.coda_manager.initialize_columns()
                logger.info("CodaManager columns initialized")
            except Exception as e:
                logger.error(f"Failed to initialize CodaManager columns: {e}")
        
        # 10) IMPORTANT: Do NOT sync here - let the SyncCommandsCog handle syncing
        logger.info("Command setup complete. Not syncing commands automatically.")
        logger.info("Commands will be synced by SyncCommandsCog based on rate limits.")
        logger.info("Use /sync_commands to manually sync, or /sync_status to check status.")
    
    def _register_event_listeners(self):
        """Find and register all event listeners in loaded cogs."""
        listeners_count = 0
        for cog_name, cog in self.cogs.items():
            for attr_name in dir(cog):
                attr = getattr(cog, attr_name)
                if callable(attr) and hasattr(attr, '_event_listener') and attr._event_listener:
                    self.event_dispatcher.register_listener(attr._event_name, attr)
                    listeners_count += 1
                    logger.debug(f"Registered event listener {cog_name}.{attr_name} for event '{attr._event_name}'")
        
        logger.info(f"Registered {listeners_count} event listeners from cogs")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        
        # Additional diagnostic check of commands after bot is fully ready
        await asyncio.sleep(2)  # Wait a moment to ensure everything is settled
        
        tree_commands = self.tree.get_commands()
        global_commands = [cmd for cmd in tree_commands if cmd.guilds is None]
        guild_commands = [cmd for cmd in tree_commands if cmd.guilds is not None]
        
        logger.info(f"Bot ready with {len(global_commands)} global commands and {len(guild_commands)} guild-specific commands")
        if guild_commands:
            logger.warning(f"These commands are still guild-specific: {', '.join(cmd.name for cmd in guild_commands)}")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        error_message = "An error occurred while processing the command."
        if isinstance(error, app_commands.errors.MissingPermissions):
            error_message = "❌ You don't have the required permissions for this command."
        elif isinstance(error, discord.Forbidden):
            error_message = "❌ I don't have permission to perform this action."
        elif isinstance(error, app_commands.errors.CommandOnCooldown):
            error_message = f"❌ This command is on cooldown. Try again in {error.retry_after:.1f} seconds."
        elif isinstance(error, app_commands.errors.MissingRole):
            error_message = "❌ You're missing the required role for this command."
        elif isinstance(error, app_commands.errors.BotMissingPermissions):
            error_message = "❌ I'm missing the required permissions to perform this action."

        logger.error(
            f"App command error in {interaction.command.name if interaction.command else 'unknown'}: {str(error)}",
            exc_info=error
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
        except discord.HTTPException as e:
            logger.error(f"Could not send error message to user: {str(e)}")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.errors.CheckFailure):
            await ctx.send("You do not have permission to use this command.")
        else:
            logger.error(f"Command error: {error}")
            
    async def close(self):
        """Override close to properly shut down custom components."""
        logger.info("Bot is shutting down, cleaning up resources...")
        
        # Stop the state manager background task
        try:
            await self.state_manager.stop()
            logger.info("State manager stopped")
        except Exception as e:
            logger.error(f"Error stopping state manager: {e}")
        
        # Backup Coda data if coda_manager exists and has backup method
        if hasattr(self, 'coda_manager') and hasattr(self.coda_manager, 'backup_data'):
            try:
                await self.coda_manager.backup_data()
                logger.info("Coda data backed up")
            except Exception as e:
                logger.error(f"Error backing up Coda data: {e}")
        
        # Continue with normal shutdown
        logger.info("Proceeding with normal shutdown")
        await super().close()

##############################################################################
# 4) Main entry point
##############################################################################
async def main():
    bot = MyBot()
    # Add any custom checks or environment validations here
    validate_env_variables()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise