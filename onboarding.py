# cogs/onboarding.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple, Union
from discord.utils import find
from .ui.onboarding_ui import (
    OnboardingManager, OnboardingWelcomeView, OnboardingState,
    TOKEN_EXPIRY_HOURS, CODA_COLUMN_MAPPING  # Import the column mapping
)

logger = logging.getLogger('onboarding')

class OnboardingCog(commands.Cog):
    """Handles the improved onboarding process for new members."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = OnboardingManager(bot)
        self.welcome_channel_id = int(os.getenv('WELCOME_CHANNEL_ID'))
        self.staff_channel_id = int(os.getenv('STAFF_NOTIFICATION_CHANNEL_ID'))
        self.guild_id = int(os.getenv('GUILD_ID'))
        
        # Get coda_client from service registry if available
        if hasattr(bot, 'services') and bot.services.has('coda_client'):
            self.coda_client = bot.services.get('coda_client')
        else:
            self.coda_client = bot.coda_client
            
        # Get event_dispatcher if available
        if hasattr(bot, 'services') and bot.services.has('event_dispatcher'):
            self.event_dispatcher = bot.services.get('event_dispatcher')
        else:
            self.event_dispatcher = None
            
        logger.info("OnboardingCog initialized")
        
    @app_commands.command(
        name="startonboarding",
        description="Begin the onboarding process."
    )
    async def start(self, interaction: discord.Interaction):
        """Start the onboarding process."""
        logger.info(f"'/startonboarding' command invoked by {interaction.user} ({interaction.user.id})")
        await interaction.response.defer(ephemeral=True)
        
        # Check if user is already registered
        try:
            # Check if user already has an active session
            active_session = self.manager.get_session_by_user(interaction.user.id)
            if active_session:
                logger.info(f"User {interaction.user.id} already has an active session")
                await interaction.followup.send(
                    "You already have an active onboarding session. Please complete or cancel it before starting a new one.",
                    ephemeral=True
                )
                return
            
            # Check if user is already registered
            is_registered = await self.check_if_registered(interaction.user.id)
            
            if is_registered:
                logger.info(f"User {interaction.user.id} is already registered")
                await interaction.followup.send(
                    "❌ You have already completed the registration process.",
                    ephemeral=True
                )
                return
                
            # Create welcome message
            embed = discord.Embed(
                title="Welcome to the HLN Discord Server!",
                description=(
                    "Thank you for joining our community! To get started, "
                    "please select how you'd like to join us."
                ),
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Member",
                value=(
                    "Join as a full member with access to all member channels and activities.\n"
                    "You'll start as a Crewman Recruit in the Non-Division section."
                ),
                inline=False
            )
            
            embed.add_field(
                name="Associate",
                value=(
                    "Participate in select activities without full member responsibilities.\n"
                    "You'll be assigned as an Associate in the Non-Division section."
                ),
                inline=False
            )
            
            # Send welcome message with buttons
            welcome_view = OnboardingWelcomeView(self.manager, interaction.user.id)
            await interaction.followup.send(
                embed=embed,
                view=welcome_view,
                ephemeral=True
            )
            
            logger.info(f"Sent welcome view to {interaction.user.id}")
            
        except Exception as e:
            logger.error(f"Error in start command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while starting onboarding. Please try again later.",
                ephemeral=True
            )
    
    # Event dispatcher
    async def trigger_onboarding_complete_event(self, member: discord.Member, member_type: str, rank: str):
        """Dispatch an event when onboarding is complete for other cogs to listen to."""
        try:
            # Use event_dispatcher if available, otherwise fall back to direct method call
            if self.event_dispatcher:
                await self.event_dispatcher.dispatch(
                    'onboarding_complete',
                    member=member,
                    member_type=member_type,
                    rank=rank
                )
                logger.info(f"Dispatched onboarding_complete event for {member.id}")
            else:
                # Legacy direct method call for backward compatibility
                welcome_cog = self.bot.get_cog("WelcomeCog")
                if welcome_cog and hasattr(welcome_cog, "on_onboarding_complete"):
                    await welcome_cog.on_onboarding_complete(member, member_type, rank)
                    logger.info(f"Triggered on_onboarding_complete event for {member.id}")
            
        except Exception as e:
            logger.error(f"Error triggering onboarding_complete event: {e}")
            
    @app_commands.command(
        name="register",
        description="Complete your registration with a token."
    )
    @app_commands.describe(token="Your registration token")
    async def register(self, interaction: discord.Interaction, token: str):
        """Complete registration with token."""
        logger.info(f"'/register' command invoked by {interaction.user.id} with token '{token}'")
        await interaction.response.defer(ephemeral=True)
        
        if not token or len(token) != 8:
            logger.warning(f"Invalid token format provided by {interaction.user.id}: '{token}'")
            await interaction.followup.send(
                "❌ Invalid token format. Please ensure you've entered the correct token.",
                ephemeral=True
            )
            return
            
        try:
            # Validate token and get member data
            user_data = await self.validate_token(token.upper())
            
            if not user_data:
                logger.warning(f"Invalid or expired token provided by {interaction.user.id}: '{token}'")
                await interaction.followup.send(
                    "❌ Invalid or expired token. Please use the `/start` command to begin again.",
                    ephemeral=True
                )
                return
                
            # Check if token belongs to this user
            if str(user_data.get('Discord User ID')) != str(interaction.user.id):
                logger.warning(f"User {interaction.user.id} attempted to use token belonging to {user_data.get('Discord User ID')}")
                await interaction.followup.send(
                    "❌ This token doesn't belong to you. Please use your own token.",
                    ephemeral=True
                )
                return
                
            # Check if token is expired
            token_expiry = user_data.get('Token Expiry')
            if token_expiry:
                expiry_time = datetime.fromisoformat(token_expiry.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expiry_time:
                    logger.warning(f"Expired token used by {interaction.user.id}, expired at {expiry_time}")
                    await interaction.followup.send(
                        "❌ This token has expired. Please use `/start` to receive a new token.",
                        ephemeral=True
                    )
                    return
                    
            # Complete registration
            member_type = user_data.get('Type', 'Member')
            
            # Ensure we're using the member from the interaction
            if interaction.guild:
                member = interaction.guild.get_member(interaction.user.id)
                if not member:
                    try:
                        member = await interaction.guild.fetch_member(interaction.user.id)
                    except discord.NotFound:
                        logger.error(f"Could not find member {interaction.user.id} in guild")
                        # Continue with user object, our updated methods will handle conversion
                        member = interaction.user
                
                # Use the member object if available
                user_to_update = member
            else:
                # Fallback to user object if no guild context
                user_to_update = interaction.user
                
            # Assign roles
            success, error = await self.assign_roles(user_to_update, member_type)
            if not success:
                logger.error(f"Error assigning roles to {interaction.user.id}: {error}")
                await interaction.followup.send(
                    f"❌ Error assigning roles: {error}",
                    ephemeral=True
                )
                return
                
            # Update nickname
            nickname_success = await self.update_nickname(user_to_update, member_type)
            if not nickname_success:
                logger.warning(f"Failed to update nickname for {interaction.user.id}")
                # Continue despite nickname failure - this is non-critical
                
            # Get current date for Join Date
            current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                
            # Mark registration as complete in database
            completion_success = await self.complete_registration(user_data.get('id'))
            if not completion_success:
                logger.error(f"Failed to mark registration as complete for {interaction.user.id}")
                # We will continue anyway since the roles are assigned
                
            # Send welcome message
            embed = discord.Embed(
                title="Registration Complete",
                description="Welcome aboard! Your registration has been successfully completed.",
                color=discord.Color.green()
            )
            
            # Get HLN ID
            hln_id = user_data.get('ID Number', 'Not assigned')
            rank = user_data.get('Rank', 'Crewman Recruit' if member_type == 'Member' else 'Associate')
            
            embed.add_field(
                name="Your Assignment",
                value=(
                    f"**HLN ID:** {hln_id}\n"
                    f"**Type:** {member_type}\n"
                    f"**Rank:** {rank}\n"
                    f"**Division:** Non-Division\n"
                    f"**Join Date:** {current_date}"
                ),
                inline=False
            )
            
            embed.add_field(
                name="Next Steps",
                value=(
                    "1. Explore the server channels\n"
                    "2. Introduce yourself in #introductions\n"
                    "3. Check out scheduled events\n"
                    "4. Read the rules and guidelines"
                ),
                inline=False
            )
            
            if member_type == "Member":
                embed.add_field(
                    name="Division Assignment",
                    value=(
                        "All new members begin in Non-Division. When you are promoted to Crewman rank, "
                        "you will be able to choose a specialized division."
                    ),
                    inline=False
                )
            
            embed.set_footer(text="If you have any questions, feel free to ask in #help")
            
            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )
            
            # Determine rank based on member type
            rank = rank or ('Crewman Recruit' if member_type == 'Member' else 'Associate')
            
            # Trigger the onboarding complete event
            await self.trigger_onboarding_complete_event(user_to_update, member_type, rank)
            
            # Log completion
            logger.info(f"Registration completed for {interaction.user.id}")
            
        except Exception as e:
            logger.error(f"Error in registration: {e}")
            await interaction.followup.send(
                "❌ An error occurred during registration. Please try again later or contact an administrator.",
                ephemeral=True
            )
            
    async def check_if_registered(self, user_id: int) -> bool:
        """Check if a user is already registered in the database."""
        try:
            response = await self.coda_client.request(
                'GET',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                params={
                    'query': f'"Discord User ID":{user_id}',
                    'useColumnNames': 'true',
                    'limit': 1
                }
            )
            
            if response and 'items' in response and len(response['items']) > 0:
                user_data = response['items'][0].get('values', {})
                status = user_data.get('Status')
                return status == 'Active'
            return False
            
        except Exception as e:
            logger.error(f"Error checking registration status for {user_id}: {e}")
            return False
            
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate registration token and get associated user data."""
        try:
            # Query Coda for the token using column ID directly
            response = await self.coda_client.request(
                'GET',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                params={
                    'query': f'"c-rYfZufmMWt":"{token}"',  # Use column ID directly for reliability
                    'useColumnNames': 'true',
                    'limit': 1
                }
            )
            
            if response and 'items' in response and len(response['items']) > 0:
                item = response['items'][0]
                # Get the row data
                row_data = item.get('values', {})
                # Include the row ID
                row_data['id'] = item.get('id')
                return row_data
                
            logger.warning(f"Token not found: {token}")
            return None
            
        except Exception as e:
            logger.error(f"Error validating token {token}: {e}")
            return None
            
    async def assign_roles(
        self, 
        user: Union[discord.User, discord.Member], 
        member_type: str
    ) -> Tuple[bool, Optional[str]]:
        """Assign initial roles based on member type."""
        try:
            # Check if we have a User object instead of a Member object
            if not hasattr(user, 'guild') or user.guild is None:
                # Get the guild from the bot
                guild = self.bot.get_guild(self.guild_id)
                if not guild:
                    return False, "Could not find guild"
                    
                # Convert User to Member
                try:
                    member = await guild.fetch_member(user.id)
                    if not member:
                        return False, f"Could not find member with ID {user.id} in guild"
                except discord.NotFound:
                    return False, f"User {user.id} is not a member of the guild"
            else:
                # Already a Member object
                member = user
                
            # Define roles to assign
            role_names = ["Non-Division"]  # Everyone gets Non-Division
            
            if member_type == "Member":
                role_names.append("Crewman Recruit")  # Members get Crewman Recruit
            else:  # Associate
                role_names.append("Associate")  # Associates get Associate role
                
            # Get role objects
            roles_to_add = []
            guild = member.guild
            
            for role_name in role_names:
                role = discord.utils.get(guild.roles, name=role_name)
                if role:
                    roles_to_add.append(role)
                else:
                    logger.warning(f"Role not found: {role_name}")
                    
            # Add roles
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Onboarding completion")
                logger.info(f"Assigned roles to {member.id}: {[r.name for r in roles_to_add]}")
                return True, None
            else:
                return False, "No valid roles found"
                
        except discord.Forbidden:
            return False, "Bot lacks permission to assign roles"
        except Exception as e:
            logger.error(f"Error assigning roles to {user.id}: {e}")
            return False, str(e)
            
    async def update_nickname(
        self, 
        user: Union[discord.User, discord.Member], 
        member_type: str
    ) -> bool:
        """Update member's nickname with rank prefix and their Star Citizen handle."""
        try:
            # Check if we have a User object instead of a Member object
            if not hasattr(user, 'guild') or user.guild is None:
                # Get the guild from the bot
                guild = self.bot.get_guild(self.guild_id)
                if not guild:
                    logger.warning(f"Could not find guild for user {user.id}")
                    return False
                    
                # Convert User to Member
                try:
                    member = await guild.fetch_member(user.id)
                    if not member:
                        logger.warning(f"Could not find member with ID {user.id} in guild")
                        return False
                except discord.NotFound:
                    logger.warning(f"User {user.id} is not a member of the guild")
                    return False
            else:
                # Already a Member object
                member = user
                
            # Check for nickname_manager in services
            if hasattr(self.bot, 'services') and self.bot.services.has('nickname_manager'):
                nickname_manager = self.bot.services.get('nickname_manager')
                rank_prefix = "CWR" if member_type == "Member" else "ASC"
                division = "Non-Division"  # All new members start in Non-Division
                
                # The method signature requires member_type and division
                return await nickname_manager.update_nickname(member, member_type, division)
            
            # Legacy nickname management if no nickname_manager service
            # Get the user data from Coda to find their SC handle
            user_data = await self.get_member_data(member.id)
            
            # Get the Star Citizen handle from user data
            if user_data and 'In-Game Handle' in user_data and user_data['In-Game Handle']:
                sc_handle = user_data['In-Game Handle']
            else:
                # If we can't find the SC handle, use their current name as fallback
                sc_handle = member.display_name
                # Remove any existing rank prefix
                if ' ' in sc_handle:
                    parts = sc_handle.split(' ')
                    if parts[0] in ["CWR", "ASC"]:  # Common prefixes
                        sc_handle = ' '.join(parts[1:])
                    
            # Add prefix based on member type
            if member_type == "Member":
                new_nickname = f"CWR {sc_handle}"  # Crewman Recruit
            else:
                new_nickname = f"ASC {sc_handle}"  # Associate
                
            # Ensure nickname is within Discord's limits
            if len(new_nickname) > 32:
                new_nickname = new_nickname[:32]
                
            # Update nickname
            await member.edit(nick=new_nickname)
            logger.info(f"Updated nickname for {member.id}: {new_nickname}")
            return True
            
        except discord.Forbidden:
            logger.warning(f"Bot lacks permission to change nickname for {user.id}")
            return False
        except Exception as e:
            logger.error(f"Error updating nickname for {user.id}: {e}")
            return False
            
    async def get_member_data(self, member_id: int) -> Optional[Dict[str, Any]]:
        """Get member data from Coda database."""
        try:
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
            logger.error(f"Error getting member data for {member_id}: {e}")
            return None
            
    async def complete_registration(self, row_id: str) -> bool:
        """Mark registration as complete in the database and set Join Date."""
        try:
            # Get current date in YYYY-MM-DD format
            current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            
            # Update registration status
            response = await self.coda_client.request(
                'PUT',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows/{row_id}',
                data={
                    'row': {
                        'cells': [
                            {'column': 'Status', 'value': 'Active'},
                            {'column': CODA_COLUMN_MAPPING["registration_token"], 'value': ''},  # Clear token after use
                            {'column': 'Join Date', 'value': current_date}  # Add Join Date in YYYY-MM-DD format
                        ]
                    }
                }
            )
            
            if response is not None:
                logger.info(f"Marked registration complete for row {row_id} with Join Date {current_date}")
                return True
            else:
                logger.error(f"Failed to update Coda record: {row_id}")
                return False
            
        except Exception as e:
            logger.error(f"Error completing registration for row {row_id}: {e}")
            return False
            
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Send welcome DM to new members."""
        logger.info(f"New member joined: {member} ({member.id})")
        
        # Skip bots
        if member.bot:
            return
            
        try:
            # Create welcome embed
            embed = discord.Embed(
                title=f"Welcome to the HLN Discord, {member.name}!",
                description="We're glad to have you here! To get started, please follow these steps:",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Step 1",
                value="Go to the server and use the `/start` command to begin the onboarding process.",
                inline=False
            )
            
            embed.add_field(
                name="Step 2",
                value="Follow the prompts to provide your information.",
                inline=False
            )
            
            embed.add_field(
                name="Step 3",
                value="Use the verification token (sent at the end of onboarding) with the `/register` command to complete your registration.",
                inline=False
            )
            
            embed.add_field(
                name="Note",
                value="All new members start in the Non-Division section. If you join as a member, you'll be assigned as a Crewman Recruit.",
                inline=False
            )
            
            embed.set_footer(text="If you need help, please ask in the server's help channel.")
            
            # Send welcome DM
            dm_sent = False
            try:
                await member.send(embed=embed)
                logger.info(f"Sent welcome DM to {member.id}")
                dm_sent = True
            except discord.Forbidden:
                logger.warning(f"Cannot send DM to {member.id} - DMs disabled")
                
                # Send message in welcome channel
                welcome_channel = member.guild.get_channel(self.welcome_channel_id)
                if welcome_channel:
                    await welcome_channel.send(
                        f"{member.mention} Welcome to the server! I couldn't send you a DM. "
                        "Please use the `/start` command to begin the onboarding process.",
                        delete_after=300  # Delete after 5 minutes
                    )
            
            # Notify staff
            staff_channel = member.guild.get_channel(self.staff_channel_id)
            if staff_channel:
                # Calculate account age
                account_age = datetime.now(timezone.utc) - member.created_at.replace(tzinfo=timezone.utc)
                
                staff_embed = discord.Embed(
                    title="New Member Joined",
                    description=f"{member.mention} has joined the server.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                staff_embed.add_field(name="Username", value=str(member), inline=True)
                staff_embed.add_field(name="ID", value=member.id, inline=True)
                staff_embed.add_field(name="Account Age", value=f"{account_age.days} days", inline=True)
                staff_embed.add_field(name="DM Status", value="Sent" if dm_sent else "Failed - DMs disabled", inline=True)
                staff_embed.set_thumbnail(url=member.display_avatar.url)
                
                await staff_channel.send(embed=staff_embed)
                logger.info(f"Sent staff notification for new member {member}")
                
        except Exception as e:
            logger.error(f"Error handling new member {member.id}: {e}")
            
    @app_commands.command(
        name="onboarding_status",
        description="Check your onboarding status."
    )
    async def onboarding_status(self, interaction: discord.Interaction):
        """Check onboarding status for a user."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check for active session first
            active_session = self.manager.get_session_by_user(interaction.user.id)
            if active_session:
                state = active_session["state"]
                
                embed = discord.Embed(
                    title="Your Onboarding Status",
                    description="You have an active onboarding session in progress.",
                    color=discord.Color.gold()
                )
                
                embed.add_field(
                    name="Current State",
                    value=state,
                    inline=True
                )
                
                started_at = active_session["started_at"]
                embed.add_field(
                    name="Started At",
                    value=started_at.strftime("%Y-%m-%d %H:%M UTC"),
                    inline=True
                )
                
                embed.add_field(
                    name="Next Steps",
                    value="Please complete your active onboarding session. If you've closed the window, use `/start` to receive a new session.",
                    inline=False
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Check user registration status in database
            response = await self.coda_client.request(
                'GET',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                params={
                    'query': f'"Discord User ID":{interaction.user.id}',
                    'useColumnNames': 'true',
                    'limit': 1
                }
            )
            
            if not response or 'items' not in response or len(response['items']) == 0:
                await interaction.followup.send(
                    "You haven't started the onboarding process yet. Please use `/start` to begin.",
                    ephemeral=True
                )
                return
                
            # Get user data
            user_data = response['items'][0].get('values', {})
            status = user_data.get('Status', 'Unknown')
            
            # Create status embed
            embed = discord.Embed(
                title="Your Onboarding Status",
                color=discord.Color.blue()
            )
            
            if status == 'Active':
                embed.description = "✅ Your onboarding is complete! You have full access to the server."
                embed.color = discord.Color.green()
            elif status == 'Pending':
                embed.description = "⏳ Your onboarding is in progress. Please complete it using your registration token."
                embed.color = discord.Color.gold()
                
                # Check if they have a token
                token = user_data.get('Registration Token')
                if token:
                    token_expiry = user_data.get('Token Expiry')
                    if token_expiry:
                        expiry_time = datetime.fromisoformat(token_expiry.replace('Z', '+00:00'))
                        if datetime.now(timezone.utc) > expiry_time:
                            embed.add_field(
                                name="Token Status",
                                value="❌ Your token has expired. Please use `/start` to get a new token.",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name="Your Token",
                                value=f"`{token}`",
                                inline=False
                            )
                            
                            embed.add_field(
                                name="Complete Registration",
                                value=f"Use `/register token:{token}` to complete your registration.",
                                inline=False
                            )
                            
                            # Calculate time until expiry
                            time_left = expiry_time - datetime.now(timezone.utc)
                            hours = time_left.seconds // 3600
                            minutes = (time_left.seconds % 3600) // 60
                            
                            embed.add_field(
                                name="Token Expires In",
                                value=f"{time_left.days} days, {hours} hours, {minutes} minutes",
                                inline=False
                            )
                else:
                    embed.add_field(
                        name="No Token Found",
                        value="Please use `/start` to begin the process again.",
                        inline=False
                    )
            else:
                embed.description = f"Status: {status}"
                embed.color = discord.Color.light_grey()
                
            # Add user info
            embed.add_field(
                name="Member Type",
                value=user_data.get('Type', 'Not specified'),
                inline=True
            )
            
            if user_data.get('Division'):
                embed.add_field(
                    name="Division",
                    value=user_data.get('Division'),
                    inline=True
                )
                
            # Add timestamps
            if user_data.get('Onboarding Started'):
                started_at = datetime.fromisoformat(user_data.get('Onboarding Started').replace('Z', '+00:00'))
                embed.add_field(
                    name="Started",
                    value=started_at.strftime("%Y-%m-%d %H:%M UTC"),
                    inline=True
                )
                
            if user_data.get('Registration Completed'):
                completed_at = datetime.fromisoformat(user_data.get('Registration Completed').replace('Z', '+00:00'))
                embed.add_field(
                    name="Completed",
                    value=completed_at.strftime("%Y-%m-%d %H:%M UTC"),
                    inline=True
                )
                
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error checking onboarding status for {interaction.user.id}: {e}")
            await interaction.followup.send(
                "❌ An error occurred while checking your status. Please try again later.",
                ephemeral=True
            )

async def setup(bot: commands.Bot):
    cog = OnboardingCog(bot)
    await bot.add_cog(cog)
    # Add a reference to the cog for backward compatibility with any code that might look for it
    bot.onboarding_cog = cog
    logger.info("OnboardingCog loaded")