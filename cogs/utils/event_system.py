# Create in cogs/utils/event_system.py

import asyncio
from functools import wraps
import logging

logger = logging.getLogger('bot.events')

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

# Modify bot.py to include the event system

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            # ... existing parameters ...
        )
        
        # Add event dispatcher to the bot
        self.event_dispatcher = EventDispatcher(self)
        self.services.register('event_dispatcher', self.event_dispatcher)
        
    async def setup_hook(self):
        # ... existing setup ...
        
        # After all extensions are loaded, register event listeners
        self._register_event_listeners()
        
    def _register_event_listeners(self):
        """Find and register all event listeners in loaded cogs."""
        for cog_name, cog in self.cogs.items():
            for attr_name in dir(cog):
                attr = getattr(cog, attr_name)
                if callable(attr) and hasattr(attr, '_event_listener') and attr._event_listener:
                    self.event_dispatcher.register_listener(attr._event_name, attr)
                    logger.info(f"Registered event listener {cog_name}.{attr_name} for event '{attr._event_name}'")

# Example usage in cogs:

class OnboardingCog(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
    
    @app_commands.command(name="complete_onboarding")
    async def complete_onboarding(self, interaction: discord.Interaction):
        # ... onboarding logic ...
        
        # Dispatch an event when onboarding is complete
        await self.bot.event_dispatcher.dispatch(
            'onboarding_complete', 
            user_id=interaction.user.id, 
            guild_id=interaction.guild_id
        )
        
        await interaction.response.send_message("Onboarding completed successfully!", ephemeral=True)

class WelcomeCog(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
    
    @event_listener('onboarding_complete')
    async def handle_onboarding_complete(self, user_id, guild_id):
        """React to the onboarding complete event."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Could not find guild with ID {guild_id}")
            return
            
        member = guild.get_member(user_id)
        if not member:
            logger.error(f"Could not find member with ID {user_id} in guild {guild_id}")
            return
            
        # Send welcome message
        welcome_channel_id = int(os.getenv('WELCOME_CHANNEL_ID', 0))
        if welcome_channel_id:
            channel = guild.get_channel(welcome_channel_id)
            if channel:
                await channel.send(f"Welcome to the organization, {member.mention}! Your onboarding is complete.")