# cogs/raid_protection.py

import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction
import logging
import config
from collections import defaultdict
from datetime import datetime, timedelta
import asyncio
import re

class RaidProtectionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Anti-Spam Tracking
        self.user_message_times = defaultdict(list)  # {user_id: [timestamps]}
        
        # Anti-Raid Tracking
        self.join_times = []  # [timestamps]

        # Raid Protection Enabled State
        self.raid_protection_enabled = config.RAID_PROTECTION_ENABLED

        # Start the cleanup task
        self.cleanup_task.start()

        # Compile regex patterns for adult website detection
        self.adult_website_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in config.ADULT_WEBSITE_PATTERNS
        ]

    def user_has_rank_role(self, member) -> bool:
        """Check if user has any rank roles."""
        # First check if we have a Member object rather than a User
        if not isinstance(member, discord.Member):
            return False
            
        member_role_names = [role.name for role in member.roles]
        return any(rank_name in member_role_names for rank_name, _ in config.STANDARD_RANKS)  # Use config.STANDARD_RANKS


    def cog_unload(self):
        self.cleanup_task.cancel()

    @tasks.loop(seconds=60)  # Runs every minute
    async def cleanup_task(self):
        """Cleans up old message and join timestamps to prevent memory leaks."""
        current_time = datetime.utcnow()
        
        # Clean up Anti-Spam data
        for user_id, timestamps in list(self.user_message_times.items()):
            self.user_message_times[user_id] = [
                ts for ts in timestamps if current_time - ts < timedelta(seconds=config.SPAM_TIMEFRAME)
            ]
            if not self.user_message_times[user_id]:
                del self.user_message_times[user_id]
            
        # Clean up Anti-Raid data
        self.join_times = [
            ts for ts in self.join_times if current_time - ts < timedelta(seconds=config.RAID_TIMEFRAME)
        ]

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle incoming messages."""
        if message.author.bot:
            return

        # Convert User to Member if in a guild
        member = None
        if message.guild:
            member = message.guild.get_member(message.author.id)
        
        # Skip rank checks for DMs or if member not found
        if not message.guild or not member:
            return
            
        if self.user_has_rank_role(member):
            # Skip moderation for ranked members
            return

        user_id = message.author.id
        current_time = datetime.utcnow()
        self.user_message_times[user_id].append(current_time)

        # Check for spam messages containing adult website links
        if config.ANTI_ADULT_SPAM_ENABLED:
            if self.contains_adult_website(message.content):
                # Delete the message
                try:
                    await message.delete()
                    logging.info(f"Deleted message from {message.author} containing adult website spam.")
                except discord.Forbidden:
                    logging.error(f"Permission denied when deleting message from {message.author}.")
                except Exception as e:
                    logging.error(f"Failed to delete message from {message.author}: {e}")

                # Mute or ban the user based on configuration
                guild = message.guild
                action = config.ADULT_SPAM_ACTION.lower()
                if action == 'ban':
                    try:
                        await guild.ban(message.author, reason="Anti-Spam: Adult website spam.")
                        logging.info(f"Banned user {message.author} for adult website spam.")
                    except discord.Forbidden:
                        logging.error(f"Permission denied when banning {message.author}.")
                    except Exception as e:
                        logging.error(f"Failed to ban {message.author}: {e}")
                elif action == 'mute':
                    mute_role = await self.get_or_create_mute_role(guild)
                    if mute_role:
                        try:
                            await message.author.add_roles(mute_role, reason="Anti-Spam: Adult website spam.")
                            logging.info(f"Muted user {message.author} for adult website spam.")
                        except discord.Forbidden:
                            logging.error(f"Permission denied when muting {message.author}.")
                        except Exception as e:
                            logging.error(f"Failed to mute {message.author}: {e}")
                else:
                    logging.error(f"Invalid ADULT_SPAM_ACTION configuration: {action}")

                # Log the action
                await self.log_action(
                    guild,
                    f"User {message.author.mention} has been {action} for posting adult website spam."
                )

                # Clear the user's message times to prevent repeated actions
                del self.user_message_times[user_id]
                return  # Exit early since we've handled this message

        # Existing Anti-Spam Logic
        if config.ANTI_SPAM_ENABLED:
            # Check for general spam
            message_times = self.user_message_times[user_id]
            # Remove old timestamps
            self.user_message_times[user_id] = [
                ts for ts in message_times if current_time - ts < timedelta(seconds=config.SPAM_TIMEFRAME)
            ]
            if len(self.user_message_times[user_id]) > config.SPAM_MESSAGE_LIMIT:
                # Mute the user
                guild = message.guild
                if guild is None:
                    return  # Ignore if not in a guild

                mute_role = await self.get_or_create_mute_role(guild)
                if not mute_role:
                    return  # Unable to proceed without a mute role

                member = message.author
                try:
                    await member.add_roles(mute_role, reason="Anti-Spam: Excessive messaging.")
                    await message.channel.send(f"⚠️ {member.mention} has been muted for spamming.")
                    logging.info(f"Muted user {member} for spamming.")
                except discord.Forbidden:
                    logging.error(f"Permission denied when muting {member}.")
                except Exception as e:
                    logging.error(f"Failed to mute {member}: {e}")

                # Log the action
                await self.log_action(
                    guild,
                    f"User {member.mention} has been muted for spamming."
                )

                # Clear the user's message times to prevent repeated actions
                del self.user_message_times[user_id]

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.raid_protection_enabled or not config.ANTI_RAID_ENABLED:
            return  # Protection is disabled

        # Check if the user has a rank role
        if self.user_has_rank_role(member):
            return  # Do not take action against users with rank roles

        current_time = datetime.utcnow()
        self.join_times.append(current_time)

        # Remove old timestamps
        self.join_times = [
            ts for ts in self.join_times if current_time - ts < timedelta(seconds=config.RAID_TIMEFRAME)
        ]

        # Check for raid
        if len(self.join_times) > config.RAID_JOIN_LIMIT:
            guild = member.guild
            logging.warning("Possible raid detected. Taking action.")

            # Take action based on configuration
            action = config.RAID_ACTION.lower()
            if action == 'ban':
                try:
                    await member.ban(reason="Anti-Raid: Mass joining detected.")
                    await self.send_alert(guild, f"⚠️ {member.mention} was banned due to a suspected raid.")
                    logging.info(f"Banned user {member} for raid.")
                except discord.Forbidden:
                    logging.error(f"Permission denied when banning {member}.")
                except Exception as e:
                    logging.error(f"Failed to ban {member}: {e}")
            elif action == 'kick':
                try:
                    await member.kick(reason="Anti-Raid: Mass joining detected.")
                    await self.send_alert(guild, f"⚠️ {member.mention} was kicked due to a suspected raid.")
                    logging.info(f"Kicked user {member} for raid.")
                except discord.Forbidden:
                    logging.error(f"Permission denied when kicking {member}.")
                except Exception as e:
                    logging.error(f"Failed to kick {member}: {e}")
            elif action == 'mute':
                mute_role = await self.get_or_create_mute_role(guild)
                if not mute_role:
                    return  # Unable to proceed without a mute role

                try:
                    await member.add_roles(mute_role, reason="Anti-Raid: Mass joining detected.")
                    await self.send_alert(guild, f"⚠️ {member.mention} was muted due to a suspected raid.")
                    logging.info(f"Muted user {member} for raid.")
                except discord.Forbidden:
                    logging.error(f"Permission denied when muting {member}.")
                except Exception as e:
                    logging.error(f"Failed to mute {member}: {e}")
            else:
                logging.error(f"Invalid RAID_ACTION configuration: {action}")

            # Log the action
            await self.log_action(
                guild,
                f"Raid detected! Action taken: {action.upper()} on user {member.mention}."
            )

            # Clear join times to prevent repeated actions
            self.join_times.clear()

    async def get_or_create_mute_role(self, guild):
        """Helper function to get or create the Muted role."""
        mute_role = discord.utils.get(guild.roles, name="Muted")
        if not mute_role:
            # Create Muted role if it doesn't exist
            try:
                mute_role = await guild.create_role(name="Muted", reason="Creating Muted role for raid protection.")
                for channel in guild.channels:
                    await channel.set_permissions(mute_role, send_messages=False, add_reactions=False)
                logging.info("Created 'Muted' role and updated channel permissions.")
            except Exception as e:
                logging.error(f"Failed to create 'Muted' role: {e}")
                return None
        return mute_role

    def contains_adult_website(self, content):
        """Checks if the content contains any adult website patterns."""
        for pattern in self.adult_website_patterns:
            if pattern.search(content):
                return True
        return False

    async def log_action(self, guild, message):
        """Logs actions to the designated logging channel."""
        logging_channel = guild.get_channel(config.LOGGING_CHANNEL_ID)
        if logging_channel:
            embed = discord.Embed(
                title="Raid Protection Action",
                description=message,
                color=0xFF0000,
                timestamp=datetime.utcnow()
            )
            await logging_channel.send(embed=embed)
        else:
            logging.warning(f"Logging channel with ID {config.LOGGING_CHANNEL_ID} not found.")

    async def send_alert(self, guild, message):
        """Sends an alert message to the logging channel."""
        logging_channel = guild.get_channel(config.LOGGING_CHANNEL_ID)
        if logging_channel:
            await logging_channel.send(message)
        else:
            logging.warning(f"Logging channel with ID {config.LOGGING_CHANNEL_ID} not found.")

    # Removed @app_commands.guilds(...) so it syncs globally
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="configure_raid_protection",
        description="Configure raid protection settings."
    )
    @app_commands.describe(
        anti_spam="Enable or disable anti-spam",
        anti_raid="Enable or disable anti-raid",
        anti_adult_spam="Enable or disable anti-adult-spam",
        spam_limit="Number of messages considered as spam",
        spam_timeframe="Timeframe in seconds for spam detection",
        raid_limit="Number of joins considered as a raid",
        raid_timeframe="Timeframe in seconds for raid detection",
        raid_action="Action to take on raid detection (ban/kick/mute)",
        adult_spam_action="Action to take on adult spam detection (ban/mute)"
    )
    async def configure_raid_protection(
        self,
        interaction: Interaction,
        anti_spam: bool,
        anti_raid: bool,
        anti_adult_spam: bool,
        spam_limit: int,
        spam_timeframe: int,
        raid_limit: int,
        raid_timeframe: int,
        raid_action: str,
        adult_spam_action: str
    ):
        """Configure raid protection settings."""
        # Update configuration
        config.ANTI_SPAM_ENABLED = anti_spam
        config.ANTI_RAID_ENABLED = anti_raid
        config.ANTI_ADULT_SPAM_ENABLED = anti_adult_spam
        config.SPAM_MESSAGE_LIMIT = spam_limit
        config.SPAM_TIMEFRAME = spam_timeframe
        config.RAID_JOIN_LIMIT = raid_limit
        config.RAID_TIMEFRAME = raid_timeframe
        config.RAID_ACTION = raid_action.lower()
        config.ADULT_SPAM_ACTION = adult_spam_action.lower()

        # Recompile regex patterns in case they were updated
        self.adult_website_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in config.ADULT_WEBSITE_PATTERNS
        ]

        # Confirmation message
        embed = discord.Embed(
            title="Raid Protection Configuration Updated",
            color=0x00FF00,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Anti-Spam Enabled", value=str(anti_spam), inline=False)
        embed.add_field(name="Anti-Raid Enabled", value=str(anti_raid), inline=False)
        embed.add_field(name="Anti-Adult-Spam Enabled", value=str(anti_adult_spam), inline=False)
        embed.add_field(name="Spam Limit", value=f"{spam_limit} messages per {spam_timeframe} seconds", inline=False)
        embed.add_field(name="Raid Join Limit", value=f"{raid_limit} joins per {raid_timeframe} seconds", inline=False)
        embed.add_field(name="Raid Action", value=raid_action.capitalize(), inline=False)
        embed.add_field(name="Adult Spam Action", value=adult_spam_action.capitalize(), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logging.info(f"Raid protection settings updated by {interaction.user}.")

    # Removed @app_commands.guilds(...) so it syncs globally
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="toggle_raid_protection",
        description="Toggle raid protection features on or off."
    )
    @app_commands.describe(
        enable="Enable or disable raid protection.",
        duration="Duration in minutes to keep the setting (optional)."
    )
    async def toggle_raid_protection(
        self,
        interaction: Interaction,
        enable: bool,
        duration: int = None
    ):
        """Toggle raid protection features on or off."""
        self.raid_protection_enabled = enable

        status = "enabled" if enable else "disabled"
        message = f"Raid protection has been **{status}**."

        if duration and not enable:
            # Schedule re-enabling after duration
            self.bot.loop.create_task(self.enable_raid_protection_after_delay(duration, interaction.guild))
            message += f" It will be re-enabled automatically in {duration} minutes."

        await interaction.response.send_message(message, ephemeral=True)
        logging.info(f"Raid protection {status} by {interaction.user}.")

        # Log the action
        await self.log_action(
            interaction.guild,
            f"Raid protection has been **{status}** by {interaction.user.mention}."
        )

    async def enable_raid_protection_after_delay(self, duration, guild):
        """Re-enables raid protection after a specified delay."""
        await asyncio.sleep(duration * 60)  # Convert minutes to seconds
        self.raid_protection_enabled = True
        logging.info("Raid protection re-enabled after delay.")

        # Send notification to logging channel
        await self.log_action(
            guild,
            "Raid protection has been automatically re-enabled after the scheduled delay."
        )

async def setup(bot):
    await bot.add_cog(RaidProtectionCog(bot))
