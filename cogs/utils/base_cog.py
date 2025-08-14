# cogs/utils/base_cog.py

import discord
from discord.ext import commands
import logging
from typing import Optional, Dict, Any, List, Callable, Union

logger = logging.getLogger('base_cog')

class BaseCog(commands.Cog):
    """
    Base cog class that provides standardized access to bot services.
    All cogs should inherit from this class for consistent service access.
    """
    
    def __init__(self, bot):
        self.bot = bot
        
    @property
    def coda_manager(self):
        """Get the CodaManager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('coda_manager'):
            return self.bot.services.get('coda_manager')
        return getattr(self.bot, 'coda_manager', None) or self.bot.coda_client  # Fallback to direct reference
        
    @property
    def coda_client(self):
        """Get the Coda API client."""
        if hasattr(self.bot, 'services') and self.bot.services.has('coda_client'):
            return self.bot.services.get('coda_client')
        return getattr(self.bot, 'coda_client', None)
        
    @property
    def audit_logger(self):
        """Get the audit logger service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('audit_logger'):
            return self.bot.services.get('audit_logger')
        return getattr(self.bot, 'audit_logger', None)
    
    @property
    def profile_sync(self):
        """Get the profile sync service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('profile_sync'):
            return self.bot.services.get('profile_sync')
        return getattr(self.bot, 'profile_sync', None)
    
    @property
    def rate_limiter(self):
        """Get the rate limiter service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('rate_limiter'):
            return self.bot.services.get('rate_limiter')
        return getattr(self.bot, 'rate_limiter', None)
    
    @property
    def daily_limit_manager(self):
        """Get the daily limit manager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('daily_limit'):
            return self.bot.services.get('daily_limit')
        return getattr(self.bot, 'daily_limit_manager', None)
    
    @property
    def command_state(self):
        """Get the command state manager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('command_state'):
            return self.bot.services.get('command_state')
        return getattr(self.bot, 'command_state', None)
    
    @property
    def sync_manager(self):
        """Get the command sync manager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('sync_manager'):
            return self.bot.services.get('sync_manager')
        return getattr(self.bot, 'sync_manager', None)
    
    @property
    def backup_manager(self):
        """Get the backup manager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('backup_manager'):
            return self.bot.services.get('backup_manager')
        return getattr(self.bot, 'backup_manager', None)
    
    @property
    def nickname_manager(self):
        """Get the nickname manager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('nickname_manager'):
            return self.bot.services.get('nickname_manager')
        return getattr(self.bot, 'nickname_manager', None)
    
    @property
    def state_manager(self):
        """Get the state manager service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('state_manager'):
            return self.bot.services.get('state_manager')
        return None  # No fallback since this is a new service
    
    @property
    def event_dispatcher(self):
        """Get the event dispatcher service."""
        if hasattr(self.bot, 'services') and self.bot.services.has('event_dispatcher'):
            return self.bot.services.get('event_dispatcher')
        return getattr(self.bot, 'event_dispatcher', None)
    
    def log_command_use(self, interaction: discord.Interaction, command_name: str):
        """
        Standard method to log command usage.
        
        Args:
            interaction: The Discord interaction
            command_name: Name of the command being used
        """
        user = interaction.user
        if self.audit_logger:
            self.audit_logger.log(
                f"Command used: {command_name} by {user.name}#{user.discriminator} ({user.id})"
            )
        else:
            logger.info(f"Command used: {command_name} by {user.name}#{user.discriminator} ({user.id})")
    
    async def check_permissions(self, interaction: discord.Interaction, required_roles: List[int] = None) -> bool:
        """
        Standard method to check if a user has required roles.
        
        Args:
            interaction: The Discord interaction
            required_roles: List of role IDs required for permission
            
        Returns:
            bool: True if user has the required roles, False otherwise
        """
        if not required_roles:
            return True
            
        user_roles = [role.id for role in interaction.user.roles]
        return any(role_id in user_roles for role_id in required_roles)
    
    async def dispatch_event(self, event_name: str, **kwargs):
        """
        Dispatch an event through the event dispatcher.
        Falls back to direct method calls for backward compatibility.
        
        Args:
            event_name: Name of the event to dispatch
            **kwargs: Event parameters
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
    
    async def get_member_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get member data from Coda.
        Convenience method that uses coda_manager if available.
        
        Args:
            user_id: Discord user ID
            
        Returns:
            Optional[Dict[str, Any]]: Member data or None if not found
        """
        try:
            if self.coda_manager and hasattr(self.coda_manager, 'get_member_data'):
                return await self.coda_manager.get_member_data(user_id)
                
            if self.coda_client:
                # Direct API call if no coda_manager
                import os
                
                response = await self.coda_client.request(
                    'GET',
                    f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                    params={
                        'query': f'"Discord User ID":"{user_id}"',
                        'useColumnNames': 'true',
                        'limit': 1
                    }
                )
                
                if response and 'items' in response and len(response['items']) > 0:
                    item = response['items'][0]
                    data = item.get('values', {})
                    data['id'] = item.get('id')
                    return data
                    
            return None
            
        except Exception as e:
            logger.error(f"Error getting member data: {e}")
            return None
    
    async def update_member_nickname(self, 
                                     member: discord.Member, 
                                     new_rank: str = None, 
                                     rank_prefix: str = None, 
                                     member_type: str = None,
                                     division: str = None,
                                     specialization: str = None) -> bool:
        """
        Update a member's nickname using the nickname manager.
        
        Args:
            member: Discord member
            new_rank: New rank name (optional)
            rank_prefix: Rank prefix (optional)
            member_type: Member type (optional)
            division: Division (optional)
            specialization: Specialization (optional)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.nickname_manager:
                logger.warning("No nickname manager available")
                return False
                
            if rank_prefix:
                # Simple prefix-based update
                return await self.nickname_manager.update_nickname_with_prefix(member, rank_prefix)
            elif new_rank and member_type:
                # Full rank-based update
                success, _, _ = await self.nickname_manager.update_nickname(
                    member,
                    new_rank,
                    member_type,
                    division or 'Non-Division',
                    specialization
                )
                return success
            else:
                logger.warning("Insufficient parameters for nickname update")
                return False
                
        except Exception as e:
            logger.error(f"Error updating member nickname: {e}")
            return False