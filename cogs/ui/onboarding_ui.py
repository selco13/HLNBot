# cogs/ui/onboarding_ui.py

import discord
from discord.ui import View, Button, Select
from discord import ui, SelectOption
import logging
import os
import uuid
import random
import string
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union, Tuple
from ..utils.id_generator import generate_member_id, RANK_CODES

# Configure logging
logger = logging.getLogger('onboarding')

# Constants
TOKEN_EXPIRY_HOURS = 24
TIMEOUT_MINUTES = 15

# Coda column mapping
CODA_COLUMN_MAPPING = {
    "registration_token": "c-rYfZufmMWt",
    "token_expiry": "Token Expiry",
    "status": "Status",
    "registration_completed": "Registration Completed"
}

# Onboarding states
class OnboardingState:
    WELCOME = "welcome"
    BASIC_INFO = "basic_info"
    REVIEW = "review"
    COMPLETE = "complete"
    CANCELED = "canceled"

class OnboardingManager:
    """Manages onboarding sessions for users."""
    
    def __init__(self, bot):
        self.bot = bot
        self.sessions = {}  # Dictionary to store active sessions
        
    def start_session(self, user_id: int) -> str:
        """
        Start a new onboarding session for a user.
        Returns the session ID.
        """
        session_id = str(uuid.uuid4()).replace('-', '')
        
        self.sessions[session_id] = {
            "user_id": user_id,
            "started_at": datetime.now(timezone.utc),
            "state": OnboardingState.WELCOME,
            "data": {}
        }
        
        logger.info(f"Started onboarding session {session_id} for user {user_id}")
        return session_id
        
    def end_session(self, session_id: str) -> bool:
        """
        End an onboarding session.
        Returns True if successful, False otherwise.
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            user_id = session["user_id"]
            del self.sessions[session_id]
            logger.info(f"Ended onboarding session {session_id} for user {user_id}")
            return True
        return False
        
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID."""
        return self.sessions.get(session_id)
        
    def get_session_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a session by user ID."""
        for session_id, session in self.sessions.items():
            if session["user_id"] == user_id:
                return session
        return None
        
    def update_session_state(self, session_id: str, new_state: str) -> bool:
        """
        Update a session's state.
        Returns True if successful, False otherwise.
        """
        if session_id in self.sessions:
            old_state = self.sessions[session_id]["state"]
            self.sessions[session_id]["state"] = new_state
            logger.debug(f"Session {session_id} state changing from {old_state} to {new_state}")
            return True
        return False
        
    def update_session_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """
        Update a session's data.
        Returns True if successful, False otherwise.
        """
        if session_id in self.sessions:
            self.sessions[session_id]["data"].update(data)
            logger.debug(f"Session {session_id} data updated with {list(data.keys())}")
            return True
        return False
        
    def generate_token(self, length: int = 8) -> str:
        """Generate a random token for registration."""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        
    async def create_coda_record(self, session_id: str) -> Optional[str]:
        """
        Create a record in Coda with the user's information.
        Returns the row ID if successful, None otherwise.
        """
        session = self.get_session(session_id)
        if not session:
            logger.error(f"No active session found for {session_id}")
            return None
            
        try:
            # Prepare the data for Coda
            user_id = session["user_id"]
            member_type = session["data"].get("member_type", "Member")
            discord_name = session["data"].get("discord_name", "")
            handle = session["data"].get("handle", "")
            referral = session["data"].get("referral", "")
            
            # Generate a registration token
            token = self.generate_token()
            
            # Set token expiry time
            expiry_time = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS)
            
            # Generate a unique HLN member ID
            # First, determine rank based on member type
            rank = "Crewman Recruit" if member_type == "Member" else "Associate"
            
            # Generate the ID
            member_id = await generate_member_id(self.bot.coda_client, member_type)
            
            # Create row data
            row_data = {
                'rows': [{
                    'cells': [
                        {'column': 'Discord User ID', 'value': str(user_id)},
                        {'column': 'Discord Username', 'value': discord_name},
                        {'column': CODA_COLUMN_MAPPING["registration_token"], 'value': token},
                        {'column': 'Token Expiry', 'value': expiry_time.isoformat()},
                        {'column': 'Type', 'value': member_type},
                        {'column': 'Status', 'value': 'Pending'},
                        {'column': 'Onboarding Started', 'value': datetime.now(timezone.utc).isoformat()},
                        {'column': 'Division', 'value': 'Non-Division'},
                        {'column': 'In-Game Handle', 'value': handle},
                        {'column': 'ID Number', 'value': member_id},
                        {'column': 'Rank', 'value': rank}
                    ]
                }]
            }
            
            # Add referral if provided
            if referral:
                row_data['rows'][0]['cells'].append({'column': 'Referred By', 'value': referral})
                
            # Log the request for debugging
            logger.debug(f"Coda request data: {row_data}")
            
            # Send request to Coda
            response = await self.bot.coda_client.request(
                'POST',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                data=row_data
            )
            
            # Check if response was successful and contains addedRowIds
            if response and 'addedRowIds' in response and response['addedRowIds']:
                row_id = response['addedRowIds'][0]
                logger.info(f"Created Coda record {row_id} for session {session_id}")
                
                # Save token and row ID to session
                session["data"]["token"] = token
                session["data"]["row_id"] = row_id
                session["data"]["member_id"] = member_id
                
                return row_id
            else:
                # Log the response for debugging
                logger.error(f"Failed to create Coda record: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating Coda record for session {session_id}: {e}")
            return None


class OnboardingWelcomeView(View):
    """View with buttons for selecting member type."""
    
    def __init__(self, manager: OnboardingManager, user_id: int):
        super().__init__(timeout=TIMEOUT_MINUTES * 60)  # Convert minutes to seconds
        self.manager = manager
        self.user_id = user_id
        self.session_id = manager.start_session(user_id)
        
    async def on_timeout(self):
        """Handle timeout by ending the session."""
        self.manager.update_session_state(self.session_id, OnboardingState.CANCELED)
        self.manager.end_session(self.session_id)
        
    @ui.button(label="Join as Member", style=discord.ButtonStyle.primary, custom_id="member")
    async def member_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle Member button click."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your onboarding session.",
                ephemeral=True
            )
            return
            
        # Update session data
        self.manager.update_session_data(self.session_id, {"member_type": "Member"})
        self.manager.update_session_state(self.session_id, OnboardingState.BASIC_INFO)
        
        logger.info(f"'Member' button clicked by {interaction.user}.")
        
        # Show basic info form
        await self.show_basic_info_form(interaction)
        
    @ui.button(label="Join as Associate", style=discord.ButtonStyle.secondary, custom_id="associate")
    async def associate_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle Associate button click."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This is not your onboarding session.",
                ephemeral=True
            )
            return
            
        # Update session data
        self.manager.update_session_data(self.session_id, {"member_type": "Associate"})
        self.manager.update_session_state(self.session_id, OnboardingState.BASIC_INFO)
        
        logger.info(f"'Associate' button clicked by {interaction.user}.")
        
        # Show basic info form
        await self.show_basic_info_form(interaction)
        
    async def show_basic_info_form(self, interaction: discord.Interaction):
        """Show basic info collection form."""
        # Create and show the modal
        modal = BasicInfoModal(self.manager, self.session_id)
        await interaction.response.send_modal(modal)


class BasicInfoModal(ui.Modal):
    """Modal for collecting basic user information."""
    
    def __init__(self, manager: OnboardingManager, session_id: str):
        super().__init__(title="Basic Information")
        self.manager = manager
        self.session_id = session_id
        
        # SC Handle field - will be used for nickname
        self.handle = ui.TextInput(
            label="Star Citizen Handle",
            placeholder="Your in-game handle (will be used as your nickname)",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.handle)
        
        # Referral field
        self.referral = ui.TextInput(
            label="Referred By (Optional)",
            placeholder="Who referred you to our org?",
            style=discord.TextStyle.short,
            required=False,
            max_length=100
        )
        self.add_item(self.referral)
        
    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        try:
            # Update session data
            self.manager.update_session_data(
                self.session_id,
                {
                    "discord_name": str(interaction.user),  # Keep track of Discord name
                    "handle": self.handle.value,  # SC handle will be used for nickname
                    "referral": self.referral.value if self.referral.value else None
                }
            )
            
            logger.info(f"User {interaction.user.id} submitted basic info form for session {self.session_id}")
            
            # Update session state
            self.manager.update_session_state(self.session_id, OnboardingState.REVIEW)
            
            # Create record in Coda
            row_id = await self.manager.create_coda_record(self.session_id)
            
            if row_id:
                # Get the session for token
                session = self.manager.get_session(self.session_id)
                token = session["data"].get("token", "ERROR")
                
                # Create review embed
                embed = discord.Embed(
                    title="Registration Review",
                    description="Please review your information below.",
                    color=discord.Color.blue()
                )
                
                session_data = session["data"]
                member_type = session_data.get("member_type", "Member")
                
                embed.add_field(
                    name="Member Type",
                    value=member_type,
                    inline=True
                )
                
                embed.add_field(
                    name="Star Citizen Handle",
                    value=self.handle.value,
                    inline=True
                )
                
                embed.add_field(
                    name="Discord Username",
                    value=str(interaction.user),
                    inline=True
                )
                
                if self.referral.value:
                    embed.add_field(
                        name="Referred By",
                        value=self.referral.value,
                        inline=True
                    )
                    
                embed.add_field(
                    name="Registration Token",
                    value=f"`{token}`",
                    inline=False
                )
                
                embed.add_field(
                    name="Next Steps",
                    value=(
                        f"1. Copy your registration token above.\n"
                        f"2. Use the `/register token:{token}` command to complete your registration.\n"
                        f"3. Your token will expire in {TOKEN_EXPIRY_HOURS} hours.\n"
                        f"4. Your Discord nickname will be set to your Star Citizen handle with rank prefix."
                    ),
                    inline=False
                )
                
                # Create complete button
                complete_view = CompleteView(self.manager, self.session_id, token)
                
                # Send review message
                await interaction.response.send_message(
                    embed=embed,
                    view=complete_view,
                    ephemeral=True
                )
                
            else:
                # Handle record creation failure
                embed = discord.Embed(
                    title="Registration Error",
                    description="There was an error creating your registration. Please try again later.",
                    color=discord.Color.red()
                )
                
                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )
                
                # End the session
                self.manager.update_session_state(self.session_id, OnboardingState.CANCELED)
                self.manager.end_session(self.session_id)
                
        except Exception as e:
            logger.error(f"Error in BasicInfoModal: {e}")
            await interaction.response.send_message(
                "An error occurred. Please try again later.",
                ephemeral=True
            )
            
            # End the session
            self.manager.update_session_state(self.session_id, OnboardingState.CANCELED)
            self.manager.end_session(self.session_id)


class CompleteView(View):
    """View with button to complete registration."""
    
    def __init__(self, manager: OnboardingManager, session_id: str, token: str):
        super().__init__(timeout=TIMEOUT_MINUTES * 60)  # Convert minutes to seconds
        self.manager = manager
        self.session_id = session_id
        self.token = token
        
    async def on_timeout(self):
        """Handle timeout by ending the session."""
        self.manager.update_session_state(self.session_id, OnboardingState.CANCELED)
        self.manager.end_session(self.session_id)
        
    @ui.button(label="Complete Registration", style=discord.ButtonStyle.success, custom_id="complete")
    async def complete_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle Complete button click."""
        session = self.manager.get_session(self.session_id)
        if not session or session["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "This is not your registration session.",
                ephemeral=True
            )
            return
            
        # Update session state
        self.manager.update_session_state(self.session_id, OnboardingState.COMPLETE)
        
        # Create embed with registration instructions
        embed = discord.Embed(
            title="Registration Instructions",
            description=(
                "Thank you for completing the onboarding process!\n\n"
                "To finalize your registration, please use the following command:"
            ),
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Command",
            value=f"`/register token:{self.token}`",
            inline=False
        )
        
        embed.add_field(
            name="Token Expiry",
            value=f"Your token will expire in {TOKEN_EXPIRY_HOURS} hours.",
            inline=False
        )
        
        # Try to send a DM
        try:
            await interaction.user.send(embed=embed)
            await interaction.response.send_message(
                "✅ Registration instructions have been sent to your DMs.\n"
                "Please check your direct messages to complete the registration process.",
                ephemeral=True
            )
        except discord.Forbidden:
            # DMs are closed
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            
        # End the session
        self.manager.end_session(self.session_id)
        
    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """Handle Cancel button click."""
        session = self.manager.get_session(self.session_id)
        if not session or session["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "This is not your registration session.",
                ephemeral=True
            )
            return
            
        # Update session state
        self.manager.update_session_state(self.session_id, OnboardingState.CANCELED)
        
        # End the session
        self.manager.end_session(self.session_id)
        
        await interaction.response.send_message(
            "❌ Registration canceled. You can restart the process anytime with the `/start` command.",
            ephemeral=True
        )