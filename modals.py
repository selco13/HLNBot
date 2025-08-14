import discord
from discord import ui
from discord.ui import TextInput
import re
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Set, Tuple

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

        self.discord_handle = TextInput(
            label="Discord Handle",
            placeholder="Your full Discord username (e.g., username#1234)",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.discord_handle)

        self.timezone = TextInput(
            label="Time Zone",
            placeholder="Your time zone (e.g., UTC, EST, PST)",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.timezone)

        self.gameplay = TextInput(
            label="Preferred Gameplay Activities",
            placeholder="What activities interest you? (Combat, Mining, Trading, etc.)",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.gameplay)

        self.interests = TextInput(
            label="Other Interests",
            placeholder="What other interests or hobbies do you have?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.interests)

        self.reason = TextInput(
            label="Reason for Joining",
            placeholder="Why do you want to join our organization?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

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

    async def validate_discord_handle(self, handle: str) -> Tuple[bool, str]:
        handle = handle.strip()
        if len(handle) < 2 or len(handle) > 32:
            return False, "Discord handle must be between 2 and 32 characters."
        if not re.match(r'^[a-zA-Z0-9._]+$', handle):
            return False, "Discord handle can only contain letters, numbers, dots, and underscores."
        return True, ""

    async def validate_content(self, value: str, field_name: str, min_length: int = 50) -> Tuple[bool, str]:
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
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Validate Discord handle
            is_valid, error_message = await self.validate_discord_handle(self.discord_handle.value)
            if not is_valid:
                await interaction.followup.send(f"❌ {error_message}", ephemeral=True)
                return

            # Validate timezone
            is_valid, error_message = await self.validate_timezone(self.timezone.value)
            if not is_valid:
                await interaction.followup.send(f"❌ {error_message}", ephemeral=True)
                return

            # Validate content fields
            content_fields = [
                (self.gameplay.value, "Gameplay Activities", 100),
                (self.interests.value, "Other Interests", 50),
                (self.reason.value, "Reason for Joining", 100)
            ]
            
            for value, field_name, min_length in content_fields:
                is_valid, error_message = await self.validate_content(value, field_name, min_length)
                if not is_valid:
                    await interaction.followup.send(f"❌ {error_message}", ephemeral=True)
                    return

            # Prepare updates for Coda - using the correct column names
            updates = {
                'Star Citizen Handle': self.discord_handle.value,  # Changed from 'Discord Handle'
                'Discord Username': str(interaction.user),  # Added this
                'Preferred Gameplay': self.gameplay.value,
                'Other Interests': self.interests.value,
                'Reason for Association': self.reason.value,  # Changed from 'Reason for Joining'
                'Started At': datetime.now(timezone.utc).isoformat(),  # Changed from 'Last Updated'
            }
            
            # Update member info in Coda with retries
            max_retries = 3
            success = False
            for attempt in range(max_retries):
                try:
                    success = await self.cog.update_member_info(self.row_id, updates)
                    if success:
                        break
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(1 * (attempt + 1))

            if not success:
                await interaction.followup.send(
                    "❌ There was an error saving your responses. Please try again later.",
                    ephemeral=True
                )
                logger.error(f"Failed to update member info for row ID: {self.row_id}")
                return

            # Get the member's token
            member_row = await self.cog.get_member_row_by_discord_id(str(interaction.user.id))
            if not member_row or 'Token' not in member_row.get('values', {}):
                await interaction.followup.send(
                    "❌ Error retrieving your registration token. Please contact an administrator.",
                    ephemeral=True
                )
                logger.error(f"Failed to retrieve token for user {interaction.user.id}")
                return

            token = member_row['values']['Token']

            try:
                # Send DM with registration instructions
                dm_message = (
                    f"Thank you for completing the onboarding survey! 🎉\n\n"
                    f"To finish your registration, please use the following token "
                    f"with the `/register` command in the server:\n\n"
                    f"**Your Token:** `{token}`\n\n"
                    f"This token will expire in 24 hours. If it expires, you can "
                    f"use the `/start` command again to receive a new token.\n\n"
                    f"Once registered, you'll have access to our community channels "
                    f"and can start participating in activities!"
                )
                await interaction.user.send(dm_message)
                await interaction.followup.send(
                    "✅ Survey completed successfully! Please check your DMs for registration instructions.",
                    ephemeral=True
                )
                logger.info(f"Successfully sent registration token to {interaction.user}")

            except discord.Forbidden:
                await interaction.followup.send(
                    f"✅ Survey completed! Here is your registration token: `{token}`\n"
                    "Please use this token with the `/register` command to complete your registration.\n\n"
                    "**Important:** Please enable DMs to receive important org notifications.",
                    ephemeral=True
                )
                logger.warning(f"Could not DM registration token to {interaction.user} - DMs disabled")

        except Exception as e:
            logger.error(f"Error in OnboardingSurveyModal: {e}", exc_info=True)
            try:
                await interaction.followup.send(
                    "❌ An error occurred while processing your survey. Please try again later.",
                    ephemeral=True
                )
            except discord.NotFound:
                pass

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors gracefully."""
        await self.log_error(error, interaction, "modal_error")
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
            await self.log_error(e, interaction, "error_handling_failed")
                
    async def log_error(self, error: Exception, interaction: discord.Interaction, context: str = ""):
        """Enhanced error logging with context."""
        error_context = {
            'user_id': interaction.user.id,
            'guild_id': self.guild_id,
            'row_id': self.row_id,
            'member_type': self.member_type,
            'context': context
        }
        logger.error(
            f"Error in OnboardingSurveyModal: {error}",
            extra={'error_context': error_context},
            exc_info=True
        )
