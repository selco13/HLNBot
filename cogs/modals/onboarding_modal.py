import discord
from discord import ui
from discord.ui import TextInput
import re
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Set, Tuple
from cogs.utils.id_generator import generate_member_id, RANK_CODES

# Configure logging
logger = logging.getLogger('onboarding')

VALID_TIMEZONES: Set[str] = {
    'UTC', 'GMT', 'EST', 'EDT', 'CST', 'CDT', 'MST', 'MDT', 'PST', 'PDT',
    *[f'UTC{i:+d}' for i in range(-12, 15)],
    *[f'GMT{i:+d}' for i in range(-12, 15)]
}

class OnboardingSurveyModal(ui.Modal):
    def __init__(self, cog, row_id: str, member_type: str, guild_id: int):
        super().__init__(title="Onboarding Survey")
        self.cog = cog
        self.row_id = row_id
        self.member_type = member_type
        self.guild_id = guild_id

        # Discord Handle field
        self.discord_handle = TextInput(
            label="Discord Handle",
            placeholder="Your Discord username (e.g., username#1234)",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.discord_handle)

        # Star Citizen Handle field
        self.sc_handle = TextInput(
            label="Star Citizen Handle",
            placeholder="Your Star Citizen username",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.sc_handle)

        # Timezone field
        self.timezone = TextInput(
            label="Time Zone",
            placeholder="Your time zone (e.g., UTC, EST, PST)",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.timezone)

        # Gameplay field
        self.gameplay = TextInput(
            label="Preferred Gameplay Activities",
            placeholder="What activities interest you? (Combat, Mining, Trading, etc.)",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.gameplay)

        # Interests field
        self.interests = TextInput(
            label="Other Interests",
            placeholder="What other interests or hobbies do you have?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.interests)

    async def validate_timezone(self, timezone_str: str) -> Tuple[bool, str]:
        """Validate timezone with expanded format support."""
        timezone_str = timezone_str.upper().strip()
        
        # Check direct matches
        if timezone_str in VALID_TIMEZONES:
            return True, ""
            
        # Check UTC/GMT offset format
        offset_pattern = r'^(UTC|GMT)?[+-]\d{1,2}(:?\d{2})?$'
        if re.match(offset_pattern, timezone_str):
            try:
                # Try to parse the offset
                if 'UTC' not in timezone_str and 'GMT' not in timezone_str:
                    timezone_str = f'UTC{timezone_str}'
                offset = int(re.findall(r'[+-]\d+', timezone_str)[0])
                if -12 <= offset <= 14:
                    return True, ""
            except (ValueError, IndexError):
                pass
            
        return False, (
            "Please provide a valid timezone (e.g., UTC, EST, PST, UTC+2). "
            "If using an offset, it must be between UTC-12 and UTC+14."
        )

    async def validate_handle(self, handle: str, field_name: str) -> Tuple[bool, str]:
        """Validate handle fields."""
        handle = handle.strip()
        if len(handle) < 2 or len(handle) > 32:
            return False, f"{field_name} must be between 2 and 32 characters."
        if not re.match(r'^[a-zA-Z0-9._-]+$', handle):
            return False, f"{field_name} can only contain letters, numbers, dots, dashes, and underscores."
        return True, ""

    async def validate_content(self, value: str, field_name: str, min_length: int = 50) -> Tuple[bool, str]:
        """Validate content fields."""
        value = value.strip()
        if len(value) < min_length:
            return False, f"{field_name} must be at least {min_length} characters long."
        if len(set(value.lower())) < 10:
            return False, f"{field_name} must contain varied and meaningful content."
        if re.search(r'(.)\1{10,}', value):
            return False, f"{field_name} contains too many repeated characters."
        words = [w for w in value.split() if len(w) >= 3]
        if len(words) < 5:
            return False, f"{field_name} must contain at least 5 meaningful words."
        return True, ""

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
                # Get the session for token and member ID
                session = self.manager.get_session(self.session_id)
                token = session["data"].get("token", "ERROR")
                member_id = session["data"].get("member_id", "ND-20-0000")
                
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
                    name="HLN ID",
                    value=member_id,
                    inline=True
                )
                
                embed.add_field(
                    name="Rank",
                    value="Crewman Recruit" if member_type == "Member" else "Associate",
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
                        f"Thank you for completing the onboarding survey! 🎉\n\n"
                        f"To finish your registration, please use the following token "
                        f"with the `/register` command in the server:\n\n"
                        f"**Your Token:** `{token}`\n\n"
                        f"This token will expire in 24 hours. If it expires, you can "
                        f"use the `/start` command again to receive a new token.\n\n"
                        f"Once registered, you'll have access to our community channels "
                        f"and can start participating in activities!"
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

    async def handle_error(self, interaction: discord.Interaction, error: Exception):
        """Handle errors during modal processing."""
        error_context = {
            'user_id': interaction.user.id,
            'guild_id': self.guild_id,
            'row_id': self.row_id,
            'member_type': self.member_type
        }
        logger.error(
            f"Error in OnboardingSurveyModal: {error}",
            extra={'error_context': error_context},
            exc_info=True
        )

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred while processing your survey. Please try again later.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred while processing your survey. Please try again later.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error sending error message: {e}")