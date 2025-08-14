# cogs/welcome.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
from typing import Optional
from datetime import datetime

# Import BaseCog and event_listener
from bot import BaseCog, event_listener

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Constants
GUILD_ID = int(os.getenv('GUILD_ID'))
WELCOME_CHANNEL_ID = int(os.getenv('WELCOME_CHANNEL_ID'))
STAFF_NOTIFICATION_CHANNEL_ID = int(os.getenv('STAFF_NOTIFICATION_CHANNEL_ID'))
NOTIFY_STAFF_ON_JOIN = False  # Set to False to avoid duplicate notifications with OnboardingCog

# Setup Logging
logger = logging.getLogger('welcome')

class WelcomeCog(BaseCog):
    """
    Handles welcome messages and member join events.
    Now using the BaseCog class for standardized service access and event_listener for events.
    """
    def __init__(self, bot):
        super().__init__(bot)
        self.notify_staff = NOTIFY_STAFF_ON_JOIN
        self.welcome_channel_id = WELCOME_CHANNEL_ID
        logger.info("WelcomeCog initialized")

    @app_commands.command(
        name='toggle_join_notifications',
        description='Toggle staff notifications for new member joins'
    )
    @app_commands.default_permissions(administrator=True)
    async def toggle_join_notifications(self, interaction: discord.Interaction):
        """Toggle whether staff gets notified when new members join."""
        self.notify_staff = not self.notify_staff
        status = "enabled" if self.notify_staff else "disabled"
        
        # Log command usage using BaseCog standard method
        self.log_command_use(interaction, "toggle_join_notifications")
        
        await interaction.response.send_message(
            f"✅ Staff notifications for new members have been {status}.",
            ephemeral=True
        )
        logger.info(f"Staff notifications toggled to {status} by {interaction.user}")

    # Using event_listener decorator instead of commands.Cog.listener
    @event_listener('onboarding_complete')
    async def on_onboarding_complete(self, member, member_type, rank):
        """Handle onboarding completion events through the event dispatcher."""
        logger.info(f"Received onboarding_complete event for {member} as {member_type} with rank {rank}")
        
        welcome_channel = self.bot.get_channel(self.welcome_channel_id)
        if welcome_channel:
            await welcome_channel.send(
                f"🎉 Please welcome our newest {member_type.lower()}, {member.mention}! "
                f"They've completed their onboarding process and joined as a {rank}."
            )
            
            # Log to audit log if available
            if self.audit_logger:
                await self.audit_logger.log(
                    f"New member {member} completed onboarding as {member_type} with rank {rank}"
                )
    
    # For backward compatibility, keep the original method as well
    @commands.Cog.listener()
    async def on_onboarding_complete_legacy(self, member, member_type, rank):
        """Legacy method for backward compatibility."""
        logger.info(f"Legacy onboarding complete event for {member} as {member_type}")
        await self.on_onboarding_complete(member, member_type, rank)
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Handle member join events if staff notification is enabled."""
        # Skip if notifications disabled or if member is a bot
        if not self.notify_staff or member.bot:
            return
            
        try:
            # Only log join to the state manager
            if self.state_manager:
                await self.state_manager.set(
                    "member_joins",
                    str(member.id),
                    {
                        "joined_at": datetime.now().isoformat(),
                        "username": str(member),
                        "id": member.id,
                        "guild_id": member.guild.id
                    }
                )
                
            # Note: Main welcome message is handled by OnboardingCog
            
        except Exception as e:
            logger.error(f"Error in on_member_join: {e}")
            
    # Example method using service registry
    async def get_member_data(self, member_id: int):
        """Example method demonstrating the use of services through BaseCog."""
        try:
            # Using coda_client through BaseCog property
            if self.coda_client:
                response = await self.coda_client.request(
                    'GET',
                    f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                    params={
                        'query': f'"Discord User ID":{member_id}',
                        'useColumnNames': 'true',
                        'limit': 1
                    }
                )
                
                if response and 'items' in response and len(response['items']) > 0:
                    return response['items'][0].get('values', {})
            
            return None
        except Exception as e:
            logger.error(f"Error getting member data: {e}")
            return None

async def setup(bot):
    """Setup function that handles cog registration."""
    await bot.add_cog(WelcomeCog(bot))
    logger.info("WelcomeCog loaded")