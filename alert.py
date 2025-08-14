from typing import Optional, Dict, List, Any
import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
from enum import Enum
from datetime import datetime, timedelta
import asyncio
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

# Alert level definitions
class AlertLevel(Enum):
    LEVEL_1 = {
        'name': 'Peaceful Operations',
        'color': discord.Color.green(),
        'status': 'No known threats. Standard operating procedures in effect.',
        'measures': 'Regular monitoring, routine intelligence sweeps, and typical cyber-security protocols.',
        'timeout': None  # No automatic timeout for level 1
    }
    LEVEL_2 = {
        'name': 'Increased Vigilance', 
        'color': discord.Color.blue(),
        'status': 'Low-level threats or unidentified activities observed. Potential for external interest.',
        'measures': 'Heightened security protocols, additional intelligence briefings, increased cyber-security measures.',
        'timeout': timedelta(hours=24)
    }
    LEVEL_3 = {
        'name': 'Potential Threat',
        'color': discord.Color.gold(),
        'status': 'Intelligence suggests a potential impending threat, possibly from adversaries or related entities.',
        'measures': 'Mandatory security briefings, enhanced ship and facility lockdown procedures, limited external communications.',
        'timeout': timedelta(hours=12)
    }
    LEVEL_4 = {
        'name': 'Imminent Threat',
        'color': discord.Color.orange(),
        'status': 'Confirmed hostile intent or activity detected. adversaries or other external entities actively targeting HLN.',
        'measures': 'Full operational security measures, immediate halt of non-essential activities, increased combat patrols, and initiation of counter-intelligence operations.',
        'timeout': timedelta(hours=6)
    }
    LEVEL_5 = {
        'name': 'Critical Threat',
        'color': discord.Color.red(),
        'status': 'Direct attack or infiltration underway from known threats or other high-level adversaries.',
        'measures': 'All hands on deck. Full combat readiness, immediate shelter and lockdown procedures, activation of emergency response teams, and counter-assault measures.',
        'timeout': timedelta(hours=3)
    }

class AlertHistory:
    def __init__(self, max_size: int = 100):
        self.history: List[Dict[str, Any]] = []
        self.max_size = max_size

    def add_entry(self, level: AlertLevel, user: discord.User, reason: Optional[str] = None):
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level.name,
            'user': str(user),
            'user_id': user.id,
            'reason': reason
        }
        self.history.append(entry)
        if len(self.history) > self.max_size:
            self.history.pop(0)

    def get_recent(self, count: int = 10) -> List[Dict[str, Any]]:
        return self.history[-count:]

class AlertCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.current_alert_level = AlertLevel.LEVEL_1
        self.alert_channel_id = int(os.getenv('ALERT_CHANNEL_ID', 0))
        self.last_alert_message: Optional[discord.Message] = None
        
        # Load configuration
        self.config = self.load_config()
        self.alert_history = AlertHistory(max_size=self.config.get('history_size', 100))
        self.last_alert_change = datetime.utcnow()
        self.rate_limit = self.config.get('rate_limit', 300)
        self.authorized_roles = self.config.get('authorized_roles', [])
        self.notification_roles = self.config.get('notification_roles', {})
        
        # Setup logging
        self.logger = logging.getLogger('alert_system')
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            filename='logs/alert_system.log',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=5,
            encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    async def send_alert_message(self, level: AlertLevel, reason: Optional[str] = None):
        """Send or update alert level message."""
        try:
            channel = self.bot.get_channel(self.alert_channel_id)
            if not channel:
                self.logger.error(f"Alert channel with ID {self.alert_channel_id} not found")
                return

            embed = discord.Embed(
                title="**HLN Alert System**",
                description=f"**Alert Level {list(AlertLevel).index(level) + 1} - {level.value['name']}**",
                color=level.value['color'],
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(name="Status", value=level.value['status'], inline=False)
            embed.add_field(name="Measures", value=level.value['measures'], inline=False)
            
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)

            # Add recent history
            recent_history = self.alert_history.get_recent(5)
            if recent_history:
                history_text = "\n".join(
                    f"Level {h['level'].split('_')[1]} - {h['user']} - {h['timestamp']}"
                    for h in recent_history
                )
                embed.add_field(name="Recent Changes", value=history_text, inline=False)

            if self.last_alert_message:
                try:
                    await self.last_alert_message.edit(embed=embed)
                except discord.NotFound:
                    self.last_alert_message = await channel.send(embed=embed)
            else:
                self.last_alert_message = await channel.send(embed=embed)

            # Handle high-priority notifications
            if list(AlertLevel).index(level) + 1 >= 4:
                await self.handle_high_priority_notifications(level, channel, embed)

            # Schedule timeout if configured
            if level.value['timeout']:
                await self.schedule_alert_timeout(level)

        except Exception as e:
            self.logger.error(f"Error sending alert message: {e}", exc_info=True)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            import yaml
            config_path = 'config/alert_system.yaml'
            
            # Create default config if it doesn't exist
            if not os.path.exists(config_path):
                os.makedirs('config', exist_ok=True)
                default_config = {
                    'authorized_roles': ['Admin', 'Moderator', 'Security Officer'],
                    'notification_roles': {
                        4: ['member', 'security'],
                        5: ['member', 'security', 'emergency-response']
                    },
                    'rate_limit': 300,
                    'history_size': 100
                }
                with open(config_path, 'w') as f:
                    yaml.dump(default_config, f)
                return default_config
                
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.error(f"Error loading config: {e}", exc_info=True)
            return {}

    async def handle_high_priority_notifications(self, level: AlertLevel, channel: discord.TextChannel, embed: discord.Embed):
        """Handle notifications for high-priority alerts."""
        try:
            level_index = list(AlertLevel).index(level) + 1
            roles_to_notify = self.notification_roles.get(level_index, [])
            
            if not roles_to_notify:
                return
                
            # Get the roles from the guild
            notification_roles = []
            for role_name in roles_to_notify:
                role = discord.utils.get(channel.guild.roles, name=role_name)
                if role:
                    notification_roles.append(role)
                else:
                    self.logger.warning(f"Could not find role {role_name}")
            
            if not notification_roles:
                return

            alert_embed = discord.Embed(
                title="🚨 URGENT: High Alert Notification 🚨",
                description=(
                    f"**Alert Level {level_index} - {level.value['name']}** has been activated.\n\n"
                    f"**Status:** {level.value['status']}\n\n"
                    f"**Required Measures:**\n{level.value['measures']}"
                ),
                color=level.value['color']
            )
            
            # Mention all relevant roles
            mentions = " ".join(role.mention for role in notification_roles)
            await channel.send(content=mentions, embed=alert_embed)
            
            # Log the notifications
            role_names = [role.name for role in notification_roles]
            self.logger.info(f"High Alert Level {level_index} notifications sent to roles: {', '.join(role_names)}")

        except Exception as e:
            self.logger.error(f"Error sending high-priority notifications: {e}", exc_info=True)

    async def schedule_alert_timeout(self, level: AlertLevel):
        """Schedule automatic alert level decrease."""
        if not level.value['timeout']:
            return

        async def timeout_task():
            await asyncio.sleep(level.value['timeout'].total_seconds())
            
            # Check if we're still at this level
            if self.current_alert_level == level:
                previous_level = list(AlertLevel)[list(AlertLevel).index(level) - 1]
                await self.set_alert_level(previous_level, self.bot.user, "Automatic timeout")

        asyncio.create_task(timeout_task())

    async def set_alert_level(self, level: AlertLevel, user: discord.User, reason: Optional[str] = None):
        """Internal method to set alert level."""
        self.current_alert_level = level
        self.last_alert_change = datetime.utcnow()
        self.alert_history.add_entry(level, user, reason)
        await self.send_alert_message(level, reason)

    @app_commands.command(name="alert_level")
    @app_commands.describe(
        level="The alert level to set (1-5)",
        reason="Reason for the alert level change"
    )
    async def set_alert_level_command(
        self,
        interaction: discord.Interaction,
        level: int,
        reason: Optional[str] = None
    ):
        """Set the current alert level."""
        if not 1 <= level <= 5:
            await interaction.response.send_message(
                "❌ Alert level must be between 1 and 5.",
                ephemeral=True
            )
            return

        # Check permissions
        has_permission = False
        if interaction.user.guild_permissions.administrator:
            has_permission = True
        else:
            user_roles = [role.name for role in interaction.user.roles]
            has_permission = any(role in self.authorized_roles for role in user_roles)
        
        if not has_permission:
            await interaction.response.send_message(
                "❌ You do not have permission to change alert levels.",
                ephemeral=True
            )
            return

        # Rate limiting check
        time_since_last = (datetime.utcnow() - self.last_alert_change).total_seconds()
        if time_since_last < self.rate_limit:
            minutes = int((self.rate_limit - time_since_last) // 60)
            seconds = int((self.rate_limit - time_since_last) % 60)
            time_str = f"{minutes} minutes and {seconds} seconds" if minutes > 0 else f"{seconds} seconds"
            
            await interaction.response.send_message(
                f"❌ Please wait {time_str} before changing the alert level.",
                ephemeral=True
            )
            return

        new_level = list(AlertLevel)[level - 1]
        await self.set_alert_level(new_level, interaction.user, reason)

        await interaction.response.send_message(
            f"✅ Alert level set to Level {level} - {new_level.value['name']}",
            ephemeral=True
        )

    @set_alert_level_command.autocomplete('level')
    async def alert_level_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        """Provide autocomplete for alert levels."""
        choices = []
        for idx, level in enumerate(AlertLevel, 1):
            name = f"Level {idx} - {level.value['name']}"
            choices.append(app_commands.Choice(name=name, value=idx))
        
        # Filter based on current input if provided
        if current:
            choices = [
                choice for choice in choices 
                if current.lower() in choice.name.lower() or 
                str(choice.value) == current
            ]
            
        return choices[:25]  # Discord limits to 25 choices

    @app_commands.command(name="alert_history")
    async def view_alert_history(
        self,
        interaction: discord.Interaction,
        count: Optional[int] = 10
    ):
        """View alert level change history."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You do not have permission to view alert history.",
                ephemeral=True
            )
            return

        history = self.alert_history.get_recent(count)
        
        if not history:
            await interaction.response.send_message(
                "No alert history available.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Alert Level Change History",
            color=discord.Color.blue()
        )

        for entry in history:
            embed.add_field(
                name=f"Level {entry['level'].split('_')[1]}",
                value=f"Changed by: {entry['user']}\n"
                      f"Time: {entry['timestamp']}\n"
                      f"Reason: {entry['reason'] or 'No reason provided'}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    """Set up the AlertCog."""
    try:
        # Removed explicit guild reference so it can be used globally
        cog = AlertCog(bot)
        await bot.add_cog(cog)
        logging.getLogger('alert_system').info("Successfully loaded AlertCog globally.")
        
    except Exception as e:
        logging.getLogger('alert_system').error(f"Failed to load AlertCog: {e}", exc_info=True)
        raise e
