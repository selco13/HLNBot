# cogs/administration.py

import config
import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING, Literal, Union
from datetime import datetime, timezone, timedelta
import asyncio
import time
from discord.ext import tasks

from .managers.promotion_manager import PromotionManager
from .managers.role_manager import RoleManager
from .managers.nickname_manager import NicknameManager
from .managers.coda_manager import CodaManager
from .views.promotion_views import (
    PromotionReviewView,
    PromotionDenialModal,
    PromotionOverrideView,
    OverrideConfirmationModal
)
from .views.certification_views import (
    CertificationGrantModal,
    CertificationsView,
    CertificationCategorySelectView
)
from .constants import (
    RANKS, FLEET_COMPONENTS, RANK_NUMBERS, RANK_ABBREVIATIONS,
    ALL_RANK_ABBREVIATIONS, ROLE_SPECIALIZATIONS, CERTIFICATIONS,
    CERTIFICATION_CATEGORIES, SHIP_CERTIFICATIONS
)

logger = logging.getLogger('administration')

# Certification role mappings - customize as needed
CERTIFICATION_ROLES = {
    "advanced_fighter": getattr(config, 'FIGHTER_PILOT_ROLE_ID', None),
    "multi_crew_helm": getattr(config, 'SHIP_CAPTAIN_ROLE_ID', None),
    "capital_helm": getattr(config, 'CAPITAL_HELMSMAN_ROLE_ID', None),
    "advanced_recon": getattr(config, 'RECON_SPECIALIST_ROLE_ID', None),
    "advanced_salvage": getattr(config, 'SALVAGE_SPECIALIST_ROLE_ID', None),
    "stellar_cartography": getattr(config, 'EXPLORER_ROLE_ID', None),
    "electronic_warfare": getattr(config, 'ELECTRONIC_WARFARE_ROLE_ID', None),
    # Add more mappings as needed
}

class AdministrationCog(commands.Cog):
    """Handles administrative commands and promotion system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._guild = None
        self._ready = asyncio.Event()  # Add an event to track readiness
        
        # Initialize managers that don't require guild access
        self.coda_manager = CodaManager(
            bot.coda_client,
            config.DOC_ID,
            config.TABLE_ID,
            config.PROMOTION_REQUESTS_TABLE_ID
        )
        self.nickname_manager = NicknameManager()
        
        # Load config
        self.config = {
            'ADMIN_NOTIFICATIONS_CHANNEL_ID': config.ADMIN_NOTIFICATIONS_CHANNEL_ID,
            'GUILD_ID': config.GUILD_ID,
            'CERTIFICATION_CHANNEL_ID': getattr(config, 'CERTIFICATION_CHANNEL_ID', None),
            'TRAINING_CHANNEL_ID': getattr(config, 'TRAINING_CHANNEL_ID', None),
            'CERT_EXPIRY_DAYS': getattr(config, 'CERT_EXPIRY_DAYS', 180),  # Default to 180 days
            'CERT_WARNING_DAYS': getattr(config, 'CERT_WARNING_DAYS', 14)  # Default to 14 days warning
        }

        # Initialize these after bot is ready
        self.promotion_manager = None
        
        # Start scheduled tasks after bot is ready
        self.certification_expiry_check.start()
        self.daily_certification_report.start()

    def cog_unload(self):
        """Called when the cog is unloaded."""
        # Stop scheduled tasks
        self.certification_expiry_check.cancel()
        self.daily_certification_report.cancel()

    @property
    async def guild(self) -> Optional[discord.Guild]:
        """Get the guild, waiting for ready if necessary."""
        await self._ready.wait()  # Wait for the ready event
        return self._guild

    async def ensure_managers(self):
        """Ensure all managers are initialized."""
        if not self.promotion_manager:
            self.promotion_manager = PromotionManager(self.bot)

    async def cog_before_invoke(self, ctx: commands.Context):
        """Ensure everything is initialized before running commands."""
        await self._ready.wait()
        await self.ensure_managers()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check before processing interactions."""
        await self._ready.wait()
        await self.ensure_managers()
        return True

    async def admin_command_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use admin commands."""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return False
        
        has_permission = await self.has_required_rank(interaction.user)
        if not has_permission:
            await interaction.response.send_message(
                "❌ You do not have permission to use this command. Captain or higher rank required.",
                ephemeral=True
            )
        return has_permission

    # === COMMAND GROUP STRUCTURE ===
    # We'll use a more structured approach with nested command groups

    # Main admin group
    admin = app_commands.Group(
        name="admin",
        description="Administrative commands"
    )
    
    # Member management subgroup
    member = app_commands.Group(
        name="member",
        description="Member management commands",
        parent=admin
    )
    
    # Certification management subgroup
    certification = app_commands.Group(
        name="certification",
        description="Certification management commands",
        parent=admin
    )

    @commands.Cog.listener()
    async def on_ready(self):
        """Handle cog startup after bot is ready."""
        try:
            # Get guild now that bot is ready
            self._guild = self.bot.get_guild(self.config['GUILD_ID'])
            if not self._guild:
                logger.warning(f"Could not find guild with ID {self.config['GUILD_ID']} - will retry on first use")
            
            # Initialize managers that need guild access
            await self.ensure_managers()
            
            # Signal that we're ready
            self._ready.set()
            
            logger.info("AdministrationCog is ready")
            
        except Exception as e:
            logger.error(f"Error in AdministrationCog on_ready: {e}")

    # === MEMBER MANAGEMENT COMMANDS ===
    
    @member.command(name="promote")
    @app_commands.describe(
        member='The member to promote',
        fleet_component='The fleet component of the member',
        new_rank='The new standard rank to assign',
        specialization='(Optional) The role specialization',
        override_time='(Optional) Override time-in-grade requirements'
    )
    async def promote_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        fleet_component: str,
        new_rank: str,
        specialization: Optional[str] = None,
        override_time: Optional[bool] = False
    ):
        """Promote a member to a new rank."""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        if not await self.has_required_rank(interaction.user):
            await interaction.followup.send(
                "❌ You do not have permission to use this command.",
                ephemeral=True
            )
            return
    
        # Handle time override permissions
        if override_time and not await self.has_override_permission(interaction.user):
            await interaction.followup.send(
                "❌ Only high-ranking officers can override time-in-grade requirements.",
                ephemeral=True
            )
            return
    
        # Log override usage
        if override_time:
            logger.info(
                f"Time-in-grade override used by {interaction.user.name} ({interaction.user.id}) "
                f"for promotion of {member.name} ({member.id}) to {new_rank}"
            )
    
        # Get current rank before promotion
        current_rank = "Recruit"  # Default fallback
        profile_cog = self.bot.get_cog('ProfileCog')
        if profile_cog:
            try:
                member_row = await profile_cog.get_member_row(member.id)
                if member_row and 'values' in member_row:
                    current_rank = member_row['values'].get('Rank', current_rank)
            except Exception as e:
                logger.error(f"Error fetching current rank: {e}")
    
        # Execute promotion - updated to use fleet_component parameter
        success = await self.promotion_manager.promote_member(
            interaction=interaction,
            member=member,
            fleet_component=fleet_component,
            new_rank=new_rank,
            specialization=specialization,
            override_time=override_time
        )
    
        if not success:
            await interaction.followup.send(
                "❌ Promotion failed. Check logs for details.",
                ephemeral=True
            )
            return
        
        # DM the member with congratulations
        try:
            promotion_dm = (
                f"🎖️ **Congratulations on your promotion!** 🎖️\n\n"
                f"You have been promoted from **{current_rank}** to **{new_rank}**.\n\n"
                f"Fleet Component: {fleet_component}\n"
                f"{f'Specialization: {specialization}' if specialization else ''}\n\n"
                f"Keep up the excellent work!\n"
                f"*Promotion authorized by {interaction.user.display_name}*"
            )
            await member.send(promotion_dm)
            logger.info(f"Sent promotion DM to {member.name}")
        except discord.Forbidden:
            logger.warning(f"Could not send promotion DM to {member.name}")
        except Exception as e:
            logger.error(f"Error sending promotion DM: {e}")
        
        # Send announcement to the server channel
        try:
            announcement_channel = self.bot.get_channel(1058522039582982176)
            if announcement_channel:
                embed = discord.Embed(
                    title="🎖️ Promotion Announcement 🎖️",
                    description=f"Congratulations to {member.mention} on their promotion!",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Previous Rank", value=current_rank, inline=True)
                embed.add_field(name="New Rank", value=new_rank, inline=True)
                embed.add_field(name="Fleet Component", value=fleet_component, inline=True)
                if specialization:
                    embed.add_field(name="Specialization", value=specialization, inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Promoted by {interaction.user.display_name} • {datetime.now().strftime('%Y-%m-%d')}")
                
                await announcement_channel.send(content=f"🎉 **ATTENTION!** A promotion has been awarded! 🎉", embed=embed)
                logger.info(f"Sent promotion announcement for {member.name} to channel {announcement_channel.name}")
            else:
                logger.error(f"Could not find announcement channel with ID 1058522039582982176")
        except Exception as e:
            logger.error(f"Error sending promotion announcement: {e}")
    
        # Return success message
        await interaction.followup.send(
            f"✅ Successfully promoted {member.mention} to {new_rank} in {fleet_component}.",
            ephemeral=True
        )

    @promote_member.autocomplete('fleet_component')
    async def fleet_component_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for fleet component names."""
        fleet_components = list(FLEET_COMPONENTS.keys())
        return [
            app_commands.Choice(name=comp, value=comp)
            for comp in fleet_components
            if current.lower() in comp.lower()
        ][:25]

    @promote_member.autocomplete('new_rank')
    async def rank_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for rank names."""
        ranks = [rank[0] for rank in RANKS]
        return [
            app_commands.Choice(name=rank, value=rank)
            for rank in ranks
            if current.lower() in rank.lower()
        ][:25]

    @promote_member.autocomplete('specialization')
    async def specialization_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for specializations."""
        # Get the fleet component from the interaction data
        options = interaction.data.get('options', [])
        fleet_component_option = next((opt for opt in options if opt.get('name') == 'fleet_component'), None)
        
        if fleet_component_option:
            fleet_component = fleet_component_option.get('value', '').strip()
            
            # Get specializations for this fleet component
            fleet_data = ROLE_SPECIALIZATIONS.get(fleet_component, {})
            specializations = list(fleet_data.keys())
            
            return [
                app_commands.Choice(name=spec, value=spec)
                for spec in sorted(specializations)
                if current.lower() in spec.lower()
            ][:25]
        else:
            # If no fleet component selected yet, show all specializations
            specializations = set()
            for fleet_data in ROLE_SPECIALIZATIONS.values():
                specializations.update(fleet_data.keys())
            
            return [
                app_commands.Choice(name=spec, value=spec)
                for spec in sorted(specializations)
                if current.lower() in spec.lower()
            ][:25]

    async def has_required_rank(self, member: discord.Member) -> bool:
        """Check if member has required rank for administrative actions."""
        from .constants import REQUIRED_STANDARD_RANKS
        await self._ready.wait()  # Wait for ready state
        return any(role.name in REQUIRED_STANDARD_RANKS for role in member.roles)

    async def has_override_permission(self, member: discord.Member) -> bool:
        """Check if member has permission to override time requirements."""
        from .constants import HIGH_RANKS
        await self._ready.wait()  # Wait for ready state
        return any(role.name in HIGH_RANKS for role in member.roles)

    @member.command(name="review")
    @app_commands.describe(
        user_id='Discord ID of the member to promote',
        recommendation_reason='Reason for promotion recommendation',
        aar_id='ID of the AAR containing the recommendation (optional)'
    )
    async def review_promotion(
        self,
        interaction: discord.Interaction,
        user_id: str,
        recommendation_reason: str,
        aar_id: Optional[str] = None
    ):
        """Create a promotion review request with optional AAR reference."""
        if not await self.admin_command_permissions(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            # Clean up user_id and get member
            user_id = user_id.strip()
            if '[' in user_id:
                user_id = user_id.split('[ID: ')[-1].strip(']')
            
            user_id_int = int(user_id)
            member = interaction.guild.get_member(user_id_int)
            
            if not member:
                await interaction.followup.send("❌ Member not found in the guild.", ephemeral=True)
                return

            # Get current rank and member data
            current_rank = self.promotion_manager.get_member_standard_rank(member)
            logger.info(f"Current rank for {member.display_name}: {current_rank}")
            
            member_data = await self.coda_manager.get_member_data(user_id_int)
            if not member_data:
                await interaction.followup.send("❌ Member record not found in database.", ephemeral=True)
                return

            # Get fleet component info
            fleet_component = member_data.get('Fleet Component', member_data.get('Division', 'Non-Fleet'))
            specialization = member_data.get('Specialization')

            # Determine next rank
            proposed_rank = await self.promotion_manager.determine_next_rank(
                current_rank,
                fleet_component,
                specialization
            )
            
            if not proposed_rank:
                await interaction.followup.send(
                    "❌ Could not determine next rank for promotion.",
                    ephemeral=True
                )
                return

            logger.info(f"Proposing rank {proposed_rank} for {member.display_name}")

            # Create promotion request
            success = await self.coda_manager.create_promotion_request(
                user_id_int,
                current_rank,
                proposed_rank,
                recommendation_reason,
                f"AAR: {aar_id}" if aar_id else None
            )

            if success:
                # Get eligibility details
                eligible, eligibility_details = await self.promotion_manager.check_promotion_eligibility(
                    member,
                    current_rank,
                    proposed_rank,
                    override_time=False
                )

                # Create embed
                embed = discord.Embed(
                    title="New Promotion Recommendation",
                    description="A promotion recommendation has been submitted for review",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                # Add member info
                embed.add_field(
                    name="Member",
                    value=f"{member.mention} ({member.display_name})",
                    inline=True
                )
                embed.add_field(
                    name="Current Rank",
                    value=current_rank,
                    inline=True
                )
                embed.add_field(
                    name="Proposed Rank",
                    value=proposed_rank,
                    inline=True
                )
                
                # Add fleet component info
                if fleet_component != "Non-Fleet":
                    embed.add_field(
                        name="Fleet Component",
                        value=fleet_component,
                        inline=True
                    )
                    if specialization:
                        embed.add_field(
                            name="Specialization",
                            value=specialization,
                            inline=True
                        )

                # Add recommendation info
                embed.add_field(
                    name="Recommendation Reason",
                    value=recommendation_reason,
                    inline=False
                )
                
                if aar_id:
                    embed.add_field(
                        name="AAR Reference",
                        value=aar_id,
                        inline=False
                    )

                embed.set_footer(
                    text=f"Recommended by {interaction.user.display_name}",
                    icon_url=interaction.user.display_avatar.url
                )

                # Create view and send message
                view = PromotionReviewView(self, user_id_int, proposed_rank, eligibility_details)
                admin_channel = interaction.guild.get_channel(self.config['ADMIN_NOTIFICATIONS_CHANNEL_ID'])
                
                if admin_channel:
                    await admin_channel.send(embed=embed, view=view)
                    await interaction.followup.send(
                        "✅ Promotion recommendation submitted for review. Command staff has been notified.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Could not find admin notification channel. Please contact a server administrator.",
                        ephemeral=True
                    )
                    logger.error(f"Admin notifications channel {self.config['ADMIN_NOTIFICATIONS_CHANNEL_ID']} not found")
            else:
                await interaction.followup.send(
                    "❌ Failed to create promotion request. Please try again later.",
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"Error in review_promotion: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your request. Please try again later.",
                ephemeral=True
            )

    @review_promotion.autocomplete('user_id')
    async def review_promotion_user_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for Discord user IDs."""
        try:
            if not current:
                # If no input, show first 25 members sorted by display name
                members = sorted(
                    interaction.guild.members, 
                    key=lambda m: m.display_name.lower()
                )[:25]
                return [
                    app_commands.Choice(
                        name=f"{m.display_name} ({m.name}) [ID: {m.id}]", 
                        value=str(m.id)
                    ) for m in members
                ]
            
            # Try direct ID match first
            if current.isdigit():
                member = interaction.guild.get_member(int(current))
                if member:
                    return [
                        app_commands.Choice(
                            name=f"{member.display_name} ({member.name}) [ID: {member.id}]", 
                            value=str(member.id)
                        )
                    ]
            
            # Match across multiple attributes
            matches = [
                m for m in interaction.guild.members 
                if (current.lower() in str(m.id) or 
                    current.lower() in m.name.lower() or 
                    current.lower() in (m.display_name or '').lower())
            ]
            
            # Sort matches by relevance
            matches.sort(key=lambda m: (
                not str(m.id).startswith(current),
                not current.lower() in m.name.lower(),
                not current.lower() in (m.display_name or '').lower(),
                (m.display_name or m.name).lower()
            ))
            
            return [
                app_commands.Choice(
                    name=f"{m.display_name} ({m.name}) [ID: {m.id}]", 
                    value=str(m.id)
                ) for m in matches[:25]
            ]

        except Exception as e:
            logger.error(f"Error in user_id autocomplete: {e}")
            return []

    @review_promotion.autocomplete('aar_id')
    async def review_promotion_aar_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for AAR IDs."""
        try:
            recent_aars = []
            aar_cog = self.bot.get_cog('AARCog')
            
            if aar_cog and hasattr(aar_cog, 'get_recent_aars'):
                recent_aars = await aar_cog.get_recent_aars(25)
            else:
                # If AAR functionality isn't available, return empty list
                return []
            
            if not current:
                return [
                    app_commands.Choice(
                        name=f"{aar['mission_name']} (ID: {aar['id']}) [{aar['date']}]", 
                        value=aar['id']
                    ) for aar in recent_aars
                ]
            
            current = current.strip().lower()
            matches = [
                aar for aar in recent_aars
                if (current in aar['id'].lower() or 
                    current in aar['mission_name'].lower())
            ]
            
            matches.sort(key=lambda x: (
                x['id'].lower() == current,
                current in x['mission_name'].lower(),
                current in x['id'].lower()
            ), reverse=True)
            
            return [
                app_commands.Choice(
                    name=f"{aar['mission_name']} (ID: {aar['id']}) [{aar['date']}]",
                    value=aar['id']
                ) for aar in matches[:25]
            ]
        except Exception as e:
            logger.error(f"Error in AAR autocomplete: {e}")
            return []

    # === CERTIFICATION MANAGEMENT COMMANDS ===

    @certification.command(name="manage")
    @app_commands.describe(
        action='The action to perform',
        member='The member to manage certification for',
        certification='The certification to manage',
        notes='Additional notes or reason (optional)',
        bulk_target='For bulk grants: Role ID/mention or Fleet Component name (optional)',
        duration='For training: Duration in minutes (optional)',
        location='For training: Location information (optional)',
        date_time='For training: Date and time (YYYY-MM-DD HH:MM) (optional)'
    )
    async def manage_certification(
        self,
        interaction: discord.Interaction,
        action: Literal['grant', 'revoke', 'check', 'bulk_grant', 'schedule_training', 'record_assessment'],
        member: Optional[discord.Member] = None,
        certification: Optional[str] = None,
        notes: Optional[str] = None,
        bulk_target: Optional[str] = None,
        duration: Optional[int] = None,
        location: Optional[str] = None,
        date_time: Optional[str] = None,
        assessment_result: Optional[Literal['pass', 'fail', 'incomplete']] = None
    ):
        """Manage member certifications with various actions."""
        if not await self.admin_command_permissions(interaction):
            return

        await interaction.response.defer(ephemeral=True)
        
        # Validate required parameters based on action
        if action in ['grant', 'revoke', 'check', 'record_assessment'] and not member:
            await interaction.followup.send("❌ You must specify a member for this action.", ephemeral=True)
            return
            
        if action in ['grant', 'revoke', 'bulk_grant', 'schedule_training', 'record_assessment'] and not certification:
            await interaction.followup.send("❌ You must specify a certification for this action.", ephemeral=True)
            return
            
        if action == 'bulk_grant' and not bulk_target:
            await interaction.followup.send("❌ You must specify a role or fleet component for bulk grants.", ephemeral=True)
            return
            
        if action == 'schedule_training' and (not date_time or not duration or not location):
            await interaction.followup.send("❌ Training schedule requires date_time, duration, and location.", ephemeral=True)
            return
            
        if action == 'record_assessment' and not assessment_result:
            await interaction.followup.send("❌ Assessment record requires a result (pass/fail/incomplete).", ephemeral=True)
            return
            
        # Execute the appropriate action
        try:
            if action == 'grant':
                await self._grant_certification(interaction, member, certification, notes)
            elif action == 'revoke':
                await self._revoke_certification(interaction, member, certification, notes)
            elif action == 'check':
                await self._check_certification_status(interaction, member)
            elif action == 'bulk_grant':
                await self._bulk_grant_certification(interaction, certification, bulk_target, notes)
            elif action == 'schedule_training':
                await self._schedule_certification_training(interaction, certification, date_time, duration, location, notes)
            elif action == 'record_assessment':
                await self._record_certification_assessment(interaction, member, certification, assessment_result, notes)
        except Exception as e:
            logger.error(f"Error in manage_certification ({action}): {e}")
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    async def _grant_certification(self, interaction, member, certification, notes=None):
        """Grant a certification to a member."""
        # Get certification info
        cert_info = CERTIFICATIONS.get(certification)
        if not cert_info:
            # Fallback to ship certifications if not found
            ship_cert = SHIP_CERTIFICATIONS.get(certification)
            if ship_cert:
                cert_name = ship_cert.get('name', certification)
            else:
                await interaction.followup.send(
                    "❌ Invalid certification ID.",
                    ephemeral=True
                )
                return
        else:
            cert_name = cert_info.get('name', certification)
        
        # Check prerequisites if applicable
        if cert_info and 'prerequisites' in cert_info:
            for prereq in cert_info.get('prerequisites', []):
                has_prereqs = await self.coda_manager.check_certification(member.id, prereq)
                if not has_prereqs:
                    prereq_name = CERTIFICATIONS.get(prereq, {}).get('name', prereq)
                    await interaction.followup.send(
                        f"❌ {member.mention} does not have the required prerequisite: **{prereq_name}**",
                        ephemeral=True
                    )
                    return

        # Grant the certification
        success = await self.coda_manager.add_certification(member.id, certification)
        if success:
            # Send confirmation to command user
            await interaction.followup.send(
                f"✅ Granted **{cert_name}** certification to {member.mention}",
                ephemeral=True
            )
            
            # Send DM to member
            try:
                dm_message = (
                    f"🏆 **Certification Granted** 🏆\n\n"
                    f"You have been granted the **{cert_name}** certification.\n\n"
                    f"*Certification authorized by {interaction.user.display_name}*"
                )
                if notes:
                    dm_message += f"\n\nNotes: {notes}"
                    
                await member.send(dm_message)
                logger.info(f"Sent certification DM to {member.name}")
            except discord.Forbidden:
                logger.warning(f"Could not send certification DM to {member.name}")
            
            # Log the action
            await self.coda_manager.log_certification_change(
                member.id,
                certification,
                'granted',
                interaction.user.id
            )
            
            # Update certification roles if applicable
            await self.update_certification_roles(member)
            
            # Send announcement to certification channel if configured
            if self.config.get('CERTIFICATION_CHANNEL_ID'):
                await self._send_certification_announcement(member, certification, cert_name, cert_info, interaction.user)
                    
            # Set certification expiry date if configured
            if self.config.get('CERT_EXPIRY_DAYS'):
                expiry_date = datetime.now() + timedelta(days=self.config['CERT_EXPIRY_DAYS'])
                await self.set_certification_expiry(member.id, certification, expiry_date)
        else:
            await interaction.followup.send(
                "❌ Failed to grant certification.",
                ephemeral=True
            )
    
    async def _send_certification_announcement(self, member, certification, cert_name, cert_info, granter):
        try:
            cert_channel = self.bot.get_channel(self.config['CERTIFICATION_CHANNEL_ID'])
            if cert_channel:
                category = cert_info.get('category', 'general').title() if cert_info else 'Ship'
                # Get the applicable fleet components for this certification
                fleet_components_text = ""
                if cert_info and 'fleet_components' in cert_info:
                    fleet_components_text = ", ".join(cert_info['fleet_components'])
                
                embed = discord.Embed(
                    title="🏆 New Certification Granted",
                    description=f"{member.mention} has earned a new qualification!",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Certification", value=cert_name, inline=True)
                embed.add_field(name="Category", value=category, inline=True)
                if fleet_components_text:
                    embed.add_field(name="Applicable Fleet Components", value=fleet_components_text, inline=False)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Granted by {granter.display_name} • {datetime.now().strftime('%Y-%m-%d')}")
                
                await cert_channel.send(embed=embed)
                logger.info(f"Sent certification announcement for {member.name}")
        except Exception as e:
            logger.error(f"Error sending certification announcement: {e}")

    async def _revoke_certification(self, interaction, member, certification, notes=None):
        """Revoke a certification from a member."""
        # Get certification info
        cert_info = CERTIFICATIONS.get(certification)
        if not cert_info:
            # Fallback to ship certifications
            ship_cert = SHIP_CERTIFICATIONS.get(certification)
            if ship_cert:
                cert_name = ship_cert.get('name', certification)
            else:
                await interaction.followup.send(
                    "❌ Invalid certification ID.",
                    ephemeral=True
                )
                return
        else:
            cert_name = cert_info.get('name', certification)
        
        # Check if the member has this certification
        has_cert = await self.coda_manager.check_certification(member.id, certification)
        if not has_cert:
            await interaction.followup.send(
                f"❌ {member.mention} does not have the **{cert_name}** certification.",
                ephemeral=True
            )
            return
        
        # Check if this certification is a prerequisite for others
        prerequisites_for = []
        for cert_id, info in CERTIFICATIONS.items():
            if certification in info.get('prerequisites', []):
                prerequisites_for.append((cert_id, info.get('name', cert_id)))
        
        if prerequisites_for:
            prereq_list = "\n".join([f"• {name}" for _, name in prerequisites_for])
            await interaction.followup.send(
                f"⚠️ **Warning:** This certification is a prerequisite for:\n{prereq_list}\n\n"
                f"Revoking it may affect the member's eligibility for these certifications.",
                ephemeral=True
            )
        
        # Revoke the certification
        success = await self.coda_manager.remove_certification(member.id, certification)
        if success:
            await interaction.followup.send(
                f"✅ Revoked **{cert_name}** certification from {member.mention}",
                ephemeral=True
            )
            
            # Notify the member
            try:
                revoke_message = (
                    f"📢 **Certification Update** 📢\n\n"
                    f"Your **{cert_name}** certification has been revoked.\n\n"
                    f"*Action performed by {interaction.user.display_name}*"
                )
                if notes:
                    revoke_message += f"\n\nReason: {notes}"
                    
                await member.send(revoke_message)
            except discord.Forbidden:
                logger.warning(f"Could not send certification revocation message to {member.name}")
            
            # Update certification roles if applicable
            await self.update_certification_roles(member)
            
            # Log the action
            await self.coda_manager.log_certification_change(
                member.id,
                certification,
                'revoked',
                interaction.user.id
            )
            
            # Remove certification expiry
            await self.remove_certification_expiry(member.id, certification)
        else:
            await interaction.followup.send(
                "❌ Failed to revoke certification.",
                ephemeral=True
            )

    async def _check_certification_status(self, interaction, member):
        """View all certifications a member has."""
        try:
            member_certs = await self.coda_manager.get_member_certifications(member.id)
            
            if not member_certs:
                await interaction.followup.send(
                    f"{member.mention} has no certifications.",
                    ephemeral=True
                )
                return
            
            # Create categories for organizing certifications
            categories = {
                "combat": {"basic": [], "advanced": []},
                "industrial": {"basic": [], "advanced": []},
                "technical": {"basic": [], "advanced": []},
                "medical": {"basic": [], "advanced": []},
                "specialized": {"basic": [], "advanced": []},
                "command": {"basic": [], "advanced": []},
                "exploration": {"basic": [], "advanced": []},
                "ship": {"basic": [], "advanced": []},
                "other": {"basic": [], "advanced": []}
            }
            
            # Sort certifications by category and level
            for cert_id in member_certs:
                # Try CERTIFICATIONS first
                if cert_id in CERTIFICATIONS:
                    info = CERTIFICATIONS[cert_id]
                    category = info.get("category", "other")
                    level = info.get("level", "basic")
                    name = info.get("name", cert_id)
                # Try SHIP_CERTIFICATIONS as fallback
                elif cert_id in SHIP_CERTIFICATIONS:
                    info = SHIP_CERTIFICATIONS[cert_id]
                    category = "ship"
                    level = "advanced" if "HEAVY" in cert_id or "LARGE" in cert_id else "basic"
                    name = info.get("name", cert_id)
                else:
                    # Unknown certification
                    category = "other"
                    level = "basic"
                    name = cert_id
                
                if category in categories:
                    if level in categories[category]:
                        categories[category][level].append(name)
            
            # Create embed
            embed = discord.Embed(
                title=f"Certifications for {member.display_name}",
                description=f"Member has {len(member_certs)} certification(s)",
                color=discord.Color.blue()
            )
            
            # Add fields for each category
            for category, levels in categories.items():
                basic_certs = levels.get("basic", [])
                advanced_certs = levels.get("advanced", [])
                
                if basic_certs:
                    embed.add_field(
                        name=f"Basic {category.title()}",
                        value="\n".join(f"• {cert}" for cert in basic_certs),
                        inline=False
                    )
                    
                if advanced_certs:
                    embed.add_field(
                        name=f"Advanced {category.title()}",
                        value="\n".join(f"• {cert}" for cert in advanced_certs),
                        inline=False
                    )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in certification_status: {e}")
            await interaction.followup.send(
                "❌ Failed to retrieve certification status.",
                ephemeral=True
            )

    async def _bulk_grant_certification(self, interaction, certification, target, reason="Bulk certification grant"):
        """Grant a certification to multiple members at once."""
        # Check for high rank requirement
        if not await self.has_override_permission(interaction.user):
            await interaction.followup.send(
                "❌ Only high-ranking officers can perform bulk certification grants.",
                ephemeral=True
            )
            return
        
        try:
            # Get certification info
            cert_info = CERTIFICATIONS.get(certification)
            if not cert_info:
                # Fallback to ship certifications
                ship_cert = SHIP_CERTIFICATIONS.get(certification)
                if ship_cert:
                    cert_name = ship_cert.get('name', certification)
                else:
                    await interaction.followup.send(
                        "❌ Invalid certification ID.",
                        ephemeral=True
                    )
                    return
            else:
                cert_name = cert_info.get('name', certification)
            
            # Determine target members
            target_members = []
            
            # Check if target is a role ID or mention
            if target.startswith('<@&') and target.endswith('>'):
                # It's a role mention
                role_id = int(target.replace('<@&', '').replace('>', ''))
                role = interaction.guild.get_role(role_id)
                if role:
                    target_members = [member for member in interaction.guild.members if role in member.roles]
                    target_description = f"Role: {role.name}"
                else:
                    await interaction.followup.send("❌ Invalid role mention.", ephemeral=True)
                    return
            elif target.isdigit():
                # It's a role ID
                role = interaction.guild.get_role(int(target))
                if role:
                    target_members = [member for member in interaction.guild.members if role in member.roles]
                    target_description = f"Role: {role.name}"
                else:
                    await interaction.followup.send("❌ Invalid role ID.", ephemeral=True)
                    return
            else:
                # Assume it's a fleet component string
                fleet_component = target
                for member in interaction.guild.members:
                    member_data = await self.coda_manager.get_member_data(member.id)
                    if member_data and (
                        member_data.get('Fleet Component') == fleet_component or
                        member_data.get('Division') == fleet_component  # For backward compatibility
                    ):
                        target_members.append(member)
                target_description = f"Fleet Component: {fleet_component}"
            
            if not target_members:
                await interaction.followup.send(
                    "❌ No members found matching the specified criteria.",
                    ephemeral=True
                )
                return
            
            # Confirm with user
            confirm_embed = discord.Embed(
                title="Bulk Certification Grant Confirmation",
                description=f"You are about to grant **{cert_name}** to **{len(target_members)}** members.\n\n"
                            f"Target: {target_description}\n\n"
                            f"Reason: {reason}\n\n"
                            f"Do you want to continue?",
                color=discord.Color.orange()
            )
            
            # Create confirmation buttons
            confirm_view = discord.ui.View(timeout=60)
            
            confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.green)
            async def confirm_callback(confirm_interaction: discord.Interaction):
                await confirm_interaction.response.defer(ephemeral=True)
                
                # Grant certification to all target members
                success_count = 0
                failed_count = 0
                already_had_count = 0
                
                for member in target_members:
                    # Check if member already has certification
                    has_cert = await self.coda_manager.check_certification(member.id, certification)
                    if has_cert:
                        already_had_count += 1
                        continue
                    
                    # Grant certification
                    success = await self.coda_manager.add_certification(member.id, certification)
                    if success:
                        success_count += 1
                        
                        # Log the action
                        await self.coda_manager.log_certification_change(
                            member.id,
                            certification,
                            'granted',
                            interaction.user.id
                        )
                        
                        # Set certification expiry date if configured
                        if self.config.get('CERT_EXPIRY_DAYS'):
                            expiry_date = datetime.now() + timedelta(days=self.config['CERT_EXPIRY_DAYS'])
                            await self.set_certification_expiry(member.id, certification, expiry_date)
                        
                        # Update certification roles
                        await self.update_certification_roles(member)
                    else:
                        failed_count += 1
                
                # Send result
                result_embed = discord.Embed(
                    title="Bulk Certification Grant Results",
                    description=f"Certification: **{cert_name}**\n"
                                f"Target: {target_description}\n"
                                f"Reason: {reason}",
                    color=discord.Color.green()
                )
                
                result_embed.add_field(
                    name="Results",
                    value=f"✅ Successfully granted to **{success_count}** members\n"
                          f"⚠️ **{already_had_count}** members already had this certification\n"
                          f"❌ Failed to grant to **{failed_count}** members",
                    inline=False
                )
                
                await confirm_interaction.followup.send(embed=result_embed, ephemeral=True)
                
                # Log the bulk action
                logger.info(
                    f"Bulk certification grant: {certification} ({cert_name}) to {success_count} members "
                    f"by {interaction.user.name} ({interaction.user.id}). "
                    f"Reason: {reason}"
                )
                
                # Disable all buttons on the original message
                for item in confirm_view.children:
                    item.disabled = True
                
                await interaction.edit_original_response(view=confirm_view)
            
            confirm_button.callback = confirm_callback
            
            cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red)
            async def cancel_callback(cancel_interaction: discord.Interaction):
                await cancel_interaction.response.defer(ephemeral=True)
                
                await cancel_interaction.followup.send(
                    "✅ Bulk certification grant cancelled.",
                    ephemeral=True
                )
                
                # Disable all buttons on the original message
                for item in confirm_view.children:
                    item.disabled = True
                
                await interaction.edit_original_response(view=confirm_view)
            
            cancel_button.callback = cancel_callback
            
            confirm_view.add_item(confirm_button)
            confirm_view.add_item(cancel_button)
            
            await interaction.followup.send(embed=confirm_embed, view=confirm_view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in bulk_grant_certification: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your request.",
                ephemeral=True
            )

    async def _schedule_certification_training(self, interaction, certification, date_time, duration, location, notes=""):
        """Schedule a certification training session."""
        # Get certification info
        cert_info = CERTIFICATIONS.get(certification)
        if not cert_info:
            cert_info = SHIP_CERTIFICATIONS.get(certification)
            if not cert_info:
                await interaction.followup.send(
                    "❌ Invalid certification ID.",
                    ephemeral=True
                )
                return
        
        cert_name = cert_info.get('name', certification)
        
        # Parse date and time
        try:
            training_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
        except ValueError:
            await interaction.followup.send(
                "❌ Invalid date/time format. Use YYYY-MM-DD HH:MM",
                ephemeral=True
            )
            return
        
        # Create training session
        training_id = f"TRAIN-{int(time.time())}"
        
        # Create announcement embed
        embed = discord.Embed(
            title=f"📚 {cert_name} Training",
            description=f"A training session has been scheduled for the **{cert_name}** certification.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Date & Time",
            value=training_time.strftime("%Y-%m-%d %H:%M"),
            inline=True
        )
        
        embed.add_field(
            name="Duration",
            value=f"{duration} minutes",
            inline=True
        )
        
        embed.add_field(
            name="Location",
            value=location,
            inline=True
        )
        
        # Add fleet components if available
        if cert_info and 'fleet_components' in cert_info:
            fleet_components_text = ", ".join(cert_info['fleet_components'])
            embed.add_field(
                name="Applicable Fleet Components",
                value=fleet_components_text,
                inline=False
            )
        
        if notes:
            embed.add_field(
                name="Additional Information",
                value=notes,
                inline=False
            )
        
        embed.add_field(
            name="Sign Up",
            value="React with ✅ to sign up for this training session.",
            inline=False
        )
        
        embed.set_footer(
            text=f"Organized by {interaction.user.display_name} • ID: {training_id}",
            icon_url=interaction.user.display_avatar.url
        )
        
        # Send to an appropriate channel
        channel_id = self.config.get('TRAINING_CHANNEL_ID')
        if channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                announcement = await channel.send(embed=embed)
                await announcement.add_reaction("✅")
                
                await interaction.followup.send(
                    f"✅ Training session for **{cert_name}** scheduled and announced.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Could not find training announcements channel.",
                    ephemeral=True
                )
        else:
            await interaction.followup.send(
                "❌ Training channel not configured. Please contact an administrator.",
                ephemeral=True
            )

    async def _record_certification_assessment(self, interaction, member, certification, result, notes=""):
        """Record a certification assessment result."""
        # Get certification info
        cert_info = CERTIFICATIONS.get(certification)
        if not cert_info:
            cert_info = SHIP_CERTIFICATIONS.get(certification)
            if not cert_info:
                await interaction.followup.send(
                    "❌ Invalid certification ID.",
                    ephemeral=True
                )
                return
        
        cert_name = cert_info.get('name', certification)
        
        # Record assessment (implement this based on your Coda structure)
        assessment_id = f"ASSESS-{int(time.time())}"
        
        # If passed, grant certification
        if result == 'pass':
            success = await self.coda_manager.add_certification(member.id, certification)
            if success:
                # Set certification expiry date if configured
                if self.config.get('CERT_EXPIRY_DAYS'):
                    expiry_date = datetime.now() + timedelta(days=self.config['CERT_EXPIRY_DAYS'])
                    await self.set_certification_expiry(member.id, certification, expiry_date)
                
                # Update certification roles
                await self.update_certification_roles(member)
                
                await interaction.followup.send(
                    f"✅ Assessment recorded and **{cert_name}** certification granted to {member.mention}",
                    ephemeral=True
                )
                
                # Send DM to member
                try:
                    dm_message = (
                        f"🏆 **Certification Assessment Passed** 🏆\n\n"
                        f"Congratulations! You have passed the assessment for the **{cert_name}** certification.\n\n"
                        f"Assessment notes: {notes}\n\n"
                        f"*Assessment conducted by {interaction.user.display_name}*"
                    )
                    await member.send(dm_message)
                except discord.Forbidden:
                    logger.warning(f"Could not send certification DM to {member.name}")
            else:
                await interaction.followup.send(
                    f"✅ Assessment recorded but failed to grant certification to {member.mention}",
                    ephemeral=True
                )
        else:
            # Just record the assessment
            await interaction.followup.send(
                f"✅ {result.title()} assessment for **{cert_name}** recorded for {member.mention}",
                ephemeral=True
            )
            
            # Send DM to member with feedback
            try:
                result_text = "needs more training" if result == 'incomplete' else "did not pass"
                dm_message = (
                    f"📝 **Certification Assessment Result** 📝\n\n"
                    f"Your assessment for the **{cert_name}** certification {result_text}.\n\n"
                    f"Assessment notes: {notes}\n\n"
                    f"*Assessment conducted by {interaction.user.display_name}*"
                )
                await member.send(dm_message)
            except discord.Forbidden:
                logger.warning(f"Could not send certification DM to {member.name}")
        
        # Log the assessment
        logger.info(
            f"Certification assessment: {certification} ({cert_name}) for {member.name} - Result: {result} "
            f"by {interaction.user.name} ({interaction.user.id})"
        )

    @manage_certification.autocomplete('certification')
    async def certification_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for certification names."""
        # Get all certifications from both dictionaries
        all_certs = []
        
        # Add from CERTIFICATIONS
        for cert_id, info in CERTIFICATIONS.items():
            all_certs.append((cert_id, info.get('name', cert_id), info.get('category', 'other')))
        
        # Add from SHIP_CERTIFICATIONS
        for cert_id, info in SHIP_CERTIFICATIONS.items():
            all_certs.append((cert_id, info.get('name', cert_id), 'ship'))
        
        # Filter based on search term
        filtered_certs = []
        if current:
            # Filter by name or category
            filtered_certs = [
                (cert_id, name, category) 
                for cert_id, name, category in all_certs
                if current.lower() in name.lower() or current.lower() in category.lower()
            ]
        else:
            # No filter, return all
            filtered_certs = all_certs
        
        # Sort by category and name
        filtered_certs.sort(key=lambda x: (x[2], x[1]))
        
        # Create choices with category prefix
        return [
            app_commands.Choice(
                name=f"[{category.title()}] {name}",
                value=cert_id
            )
            for cert_id, name, category in filtered_certs[:25]  # Discord limit
        ]

    @manage_certification.autocomplete('bulk_target')
    async def bulk_target_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for bulk target (fleet components only)."""
        # Get action from options
        options = interaction.data.get('options', [])
        action_option = next((opt for opt in options if opt.get('name') == 'action'), None)
        
        if not action_option or action_option.get('value') != 'bulk_grant':
            return []
            
        # Return fleet components for autocomplete
        fleet_components = list(FLEET_COMPONENTS.keys())
        return [
            app_commands.Choice(name=f"Fleet: {comp}", value=comp)
            for comp in fleet_components
            if not current or current.lower() in comp.lower()
        ][:25]

    @certification.command(name="info")
    @app_commands.describe(
        info_type='Type of information to view',
        certification='Certification to view information about',
        category='Category to view progression path for (when info_type is "path")'
    )
    async def certification_info(
        self,
        interaction: discord.Interaction,
        info_type: Literal['prerequisites', 'path', 'eligible', 'report', 'leaderboard'],
        certification: Optional[str] = None, 
        category: Optional[str] = None
    ):
        """View information about certifications."""
        await interaction.response.defer(ephemeral=True)
        
        if info_type in ['prerequisites', 'eligible'] and not certification:
            await interaction.followup.send("❌ You must specify a certification.", ephemeral=True)
            return
            
        if info_type == 'path' and not category:
            await interaction.followup.send("❌ You must specify a category.", ephemeral=True)
            return
            
        try:
            if info_type == 'prerequisites':
                await self._certification_prerequisites(interaction, certification)
            elif info_type == 'path':
                await self._certification_path(interaction, category)
            elif info_type == 'eligible':
                await self._certification_eligible(interaction, certification)
            elif info_type == 'report':
                await self._certification_report(interaction)
            elif info_type == 'leaderboard':
                await self._certification_leaderboard(interaction)
        except Exception as e:
            logger.error(f"Error in certification_info ({info_type}): {e}")
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    async def _certification_prerequisites(self, interaction, certification):
        """View prerequisites for a certification."""
        # Get certification info
        cert_info = CERTIFICATIONS.get(certification)
        if not cert_info:
            # Fallback to ship certifications
            ship_cert = SHIP_CERTIFICATIONS.get(certification)
            if ship_cert:
                cert_name = ship_cert.get('name', certification)
                prerequisites = ship_cert.get('prerequisites', [])
            else:
                await interaction.followup.send(
                    "❌ Invalid certification ID.",
                    ephemeral=True
                )
                return
        else:
            cert_name = cert_info.get('name', certification)
            prerequisites = cert_info.get('prerequisites', [])
        
        # Create embed
        embed = discord.Embed(
            title=f"Prerequisites for {cert_name}",
            color=discord.Color.blue()
        )
        
        # Add certification info
        category = cert_info.get('category', 'general').title() if cert_info else 'Ship'
        level = cert_info.get('level', 'basic').title() if cert_info else 'Unknown'
        
        embed.add_field(
            name="Certification",
            value=cert_name,
            inline=True
        )
        embed.add_field(
            name="Category",
            value=category,
            inline=True
        )
        embed.add_field(
            name="Level",
            value=level,
            inline=True
        )
        
        # Add applicable fleet components if available
        if cert_info and 'fleet_components' in cert_info:
            fleet_components_text = ", ".join(cert_info['fleet_components'])
            embed.add_field(
                name="Applicable Fleet Components",
                value=fleet_components_text,
                inline=False
            )
        
        # Add prerequisites
        if prerequisites:
            prereq_text = ""
            for prereq_id in prerequisites:
                # Get prerequisite name
                prereq_name = prereq_id
                if prereq_id in CERTIFICATIONS:
                    prereq_name = CERTIFICATIONS[prereq_id].get('name', prereq_id)
                elif prereq_id in SHIP_CERTIFICATIONS:
                    prereq_name = SHIP_CERTIFICATIONS[prereq_id].get('name', prereq_id)
                
                prereq_text += f"• {prereq_name}\n"
            
            embed.add_field(
                name="Prerequisites",
                value=prereq_text,
                inline=False
            )
        else:
            embed.add_field(
                name="Prerequisites",
                value="No prerequisites required.",
                inline=False
            )
        
        # Find certifications that require this as a prerequisite
        required_for = []
        for cert_id, info in CERTIFICATIONS.items():
            if certification in info.get('prerequisites', []):
                required_for.append((cert_id, info.get('name', cert_id)))
        
        # Add required for
        if required_for:
            required_text = ""
            for cert_id, name in required_for:
                required_text += f"• {name}\n"
            
            embed.add_field(
                name="Required For",
                value=required_text,
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _certification_path(self, interaction, category):
        """View the progression path for certifications in a category."""
        # Filter certifications by category
        category_certs = {
            cert_id: info for cert_id, info in CERTIFICATIONS.items()
            if info.get('category', '').lower() == category.lower()
        }
        
        if not category_certs:
            await interaction.followup.send(
                f"❌ No certifications found for category: {category}",
                ephemeral=True
            )
            return
        
        # Create a visual representation using embeds
        embed = discord.Embed(
            title=f"{category.title()} Certification Path",
            description="This progression chart shows the recommended certification path.",
            color=discord.Color.blue()
        )
        
        # Group by level
        basic_certs = {cert_id: info for cert_id, info in category_certs.items() if info.get('level') == 'basic'}
        advanced_certs = {cert_id: info for cert_id, info in category_certs.items() if info.get('level') == 'advanced'}
        
        # Add basic certifications
        if basic_certs:
            basic_text = ""
            for cert_id, info in basic_certs.items():
                fleet_components = ", ".join(info.get('fleet_components', []))
                fleet_text = f" (Fleet: {fleet_components})" if fleet_components else ""
                basic_text += f"• {info.get('name', cert_id)}{fleet_text}\n"
            
            embed.add_field(
                name="Basic Certifications",
                value=basic_text,
                inline=False
            )
        
        # Add advanced certifications with prerequisites
        if advanced_certs:
            advanced_text = ""
            for cert_id, info in advanced_certs.items():
                prereqs = info.get('prerequisites', [])
                prereq_names = []
                
                for prereq in prereqs:
                    if prereq in CERTIFICATIONS:
                        prereq_names.append(CERTIFICATIONS[prereq].get('name', prereq))
                    else:
                        prereq_names.append(prereq)
                
                prereq_text = f" (Requires: {', '.join(prereq_names)})" if prereq_names else ""
                fleet_components = ", ".join(info.get('fleet_components', []))
                fleet_text = f" (Fleet: {fleet_components})" if fleet_components else ""
                
                advanced_text += f"• {info.get('name', cert_id)}{prereq_text}{fleet_text}\n"
            
            embed.add_field(
                name="Advanced Certifications",
                value=advanced_text,
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _certification_eligible(self, interaction, certification):
        """Check which members are eligible for a certification."""            
        # Get certification info
        cert_info = CERTIFICATIONS.get(certification)
        if not cert_info:
            cert_info = SHIP_CERTIFICATIONS.get(certification)
            if not cert_info:
                await interaction.followup.send(
                    "❌ Invalid certification ID.",
                    ephemeral=True
                )
                return
        
        cert_name = cert_info.get('name', certification)
        prerequisites = cert_info.get('prerequisites', [])
        
        # If no prerequisites, everyone is eligible
        if not prerequisites:
            await interaction.followup.send(
                f"ℹ️ The certification **{cert_name}** has no prerequisites. All members are eligible.",
                ephemeral=True
            )
            return
        
        # Get all members
        all_members = await self.coda_manager.get_all_members()
        
        # Check eligibility for each member
        eligible_members = []
        ineligible_members = []
        
        for member_data in all_members:
            user_id = member_data.get('Discord User ID')
            if not user_id:
                continue
                
            try:
                # Get certifications
                certifications = member_data.get('Certifications', '')
                # Normalize certifications
                if isinstance(certifications, str):
                    cert_list = [cert.strip() for cert in certifications.split(',') if cert.strip()]
                elif isinstance(certifications, list):
                    cert_list = certifications
                else:
                    cert_list = []
                
                # Check if member already has this certification
                if certification in cert_list:
                    continue
                
                # Check if member has all prerequisites
                has_all_prereqs = True
                missing_prereqs = []
                for prereq in prerequisites:
                    if prereq not in cert_list:
                        has_all_prereqs = False
                        missing_prereqs.append(prereq)
                
                # Try to get the member from the guild
                member = interaction.guild.get_member(int(user_id))
                if member:
                    if has_all_prereqs:
                        eligible_members.append(member)
                    else:
                        ineligible_members.append((member, missing_prereqs))
            except (ValueError, TypeError):
                continue
        
        # Create embed
        embed = discord.Embed(
            title=f"Eligibility for {cert_name}",
            description=f"Prerequisites: {', '.join([CERTIFICATIONS.get(p, {}).get('name', p) for p in prerequisites])}",
            color=discord.Color.blue()
        )
        
        # Add applicable fleet components if available
        if 'fleet_components' in cert_info:
            fleet_components_text = ", ".join(cert_info['fleet_components'])
            embed.add_field(
                name="Applicable Fleet Components",
                value=fleet_components_text,
                inline=False
            )
        
        # Add eligible members
        if eligible_members:
            eligible_text = ""
            for member in eligible_members[:20]:  # Limit to 20 members
                eligible_text += f"• {member.mention} ({member.display_name})\n"
            
            if len(eligible_members) > 20:
                eligible_text += f"...and {len(eligible_members) - 20} more."
            
            embed.add_field(
                name=f"Eligible Members ({len(eligible_members)})",
                value=eligible_text,
                inline=False
            )
        else:
            embed.add_field(
                name="Eligible Members",
                value="No members are currently eligible.",
                inline=False
            )
        
        # Add ineligible members with missing prerequisites
        if ineligible_members and len(ineligible_members) <= 10:
            ineligible_text = ""
            for member, missing_prereqs in ineligible_members[:10]:
                missing_names = [CERTIFICATIONS.get(p, {}).get('name', p) for p in missing_prereqs]
                ineligible_text += f"• {member.mention}: Missing {', '.join(missing_names)}\n"
            
            embed.add_field(
                name="Close to Eligible",
                value=ineligible_text,
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _certification_report(self, interaction):
        """Generate a report of certification statistics across the organization."""
        try:
            # Get certification report
            report = await self.coda_manager.get_certification_report()
            
            if not report:
                await interaction.followup.send(
                    "❌ Failed to generate certification report.",
                    ephemeral=True
                )
                return
            
            # Create embed
            embed = discord.Embed(
                title="Certification Report",
                description="Statistics about certifications across the organization",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Add general statistics
            embed.add_field(
                name="General Statistics",
                value=(
                    f"**Total Members:** {report.get('total_members', 0)}\n"
                    f"**Members with Certifications:** {report.get('members_with_certs', 0)} "
                    f"({round(report.get('members_with_certs', 0) / max(1, report.get('total_members', 1)) * 100)}%)\n"
                    f"**Total Certifications Granted:** {report.get('total_certs_granted', 0)}\n"
                    f"**Average Certifications per Member:** "
                    f"{round(report.get('total_certs_granted', 0) / max(1, report.get('members_with_certs', 1)), 1)}"
                ),
                inline=False
            )
            
            # Add most common certifications
            most_common = report.get('most_common_certs', [])
            if most_common:
                most_common_text = ""
                for cert_id, count in most_common:
                    # Get certification name
                    cert_name = cert_id
                    if cert_id in CERTIFICATIONS:
                        cert_name = CERTIFICATIONS[cert_id].get('name', cert_id)
                    elif cert_id in SHIP_CERTIFICATIONS:
                        cert_name = SHIP_CERTIFICATIONS[cert_id].get('name', cert_id)
                    
                    most_common_text += f"• **{cert_name}**: {count} members\n"
                
                embed.add_field(
                    name="Most Common Certifications",
                    value=most_common_text,
                    inline=False
                )
            
            # Add least common certifications
            least_common = report.get('least_common_certs', [])
            if least_common:
                least_common_text = ""
                for cert_id, count in least_common:
                    # Get certification name
                    cert_name = cert_id
                    if cert_id in CERTIFICATIONS:
                        cert_name = CERTIFICATIONS[cert_id].get('name', cert_id)
                    elif cert_id in SHIP_CERTIFICATIONS:
                        cert_name = SHIP_CERTIFICATIONS[cert_id].get('name', cert_id)
                    
                    least_common_text += f"• **{cert_name}**: {count} members\n"
                
                embed.add_field(
                    name="Least Common Certifications",
                    value=least_common_text,
                    inline=False
                )
            
            # Add footer
            embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error generating certification report: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the certification report.",
                ephemeral=True
            )

    async def _certification_leaderboard(self, interaction):
        """Display a leaderboard of members with the most certifications."""
        try:
            # Get all members with certifications
            all_members = await self.coda_manager.get_all_members()
            
            # Count certifications per member
            member_certs = []
            for member_data in all_members:
                user_id = member_data.get('Discord User ID')
                if not user_id:
                    continue
                    
                certifications = member_data.get('Certifications', '')
                
                # Normalize certifications
                if isinstance(certifications, str):
                    cert_list = [cert.strip() for cert in certifications.split(',') if cert.strip()]
                elif isinstance(certifications, list):
                    cert_list = certifications
                else:
                    cert_list = []
                    
                if cert_list:
                    try:
                        # Try to get the member from the guild
                        member = interaction.guild.get_member(int(user_id))
                        if member:
                            member_certs.append((member, len(cert_list)))
                    except (ValueError, TypeError):
                        continue
            
            # Sort by number of certifications (descending)
            member_certs.sort(key=lambda x: x[1], reverse=True)
            
            # Create leaderboard embed
            embed = discord.Embed(
                title="Certification Leaderboard",
                description="Members with the most certifications",
                color=discord.Color.gold()
            )
            
            # Add top 15 members
            top_members = member_certs[:15]
            if top_members:
                leaderboard_text = ""
                for i, (member, count) in enumerate(top_members, 1):
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                    leaderboard_text += f"{medal} **{member.display_name}**: {count} certifications\n"
                
                embed.description = leaderboard_text
            else:
                embed.description = "No members with certifications found."
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error generating certification leaderboard: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the leaderboard.",
                ephemeral=True
            )

    @certification_info.autocomplete('certification')
    async def info_certification_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for certification names."""
        return await self.certification_autocomplete(interaction, current)

    @certification_info.autocomplete('category')
    async def certification_category_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for certification categories."""
        categories = sorted(list(set([info.get('category', 'other') for _, info in CERTIFICATIONS.items()])))
        
        return [
            app_commands.Choice(name=category.title(), value=category)
            for category in categories
            if current.lower() in category.lower()
        ][:25]

    # === USER-FACING CERTIFICATION COMMANDS ===

    @app_commands.command(name="certifications")
    async def certifications(self, interaction: discord.Interaction):
        """View your certifications and progress."""
        await interaction.response.defer(ephemeral=True)
        
        # Get member's certifications
        member_certs = await self.coda_manager.get_member_certifications(interaction.user.id)
        
        if not member_certs:
            await interaction.followup.send(
                "You don't have any certifications yet. Talk to a training officer to get started!",
                ephemeral=True
            )
            return
        
        # Get member's fleet component
        member_data = await self.coda_manager.get_member_data(interaction.user.id)
        if member_data:
            fleet_component = member_data.get('Fleet Component', member_data.get('Division', 'Non-Fleet'))
        else:
            fleet_component = "Non-Fleet"
        
        # Create categories
        categories = {
            "combat": {"basic": [], "advanced": []},
            "industrial": {"basic": [], "advanced": []},
            "technical": {"basic": [], "advanced": []},
            "medical": {"basic": [], "advanced": []},
            "specialized": {"basic": [], "advanced": []},
            "command": {"basic": [], "advanced": []},
            "exploration": {"basic": [], "advanced": []},
            "ship": {"basic": [], "advanced": []},
            "other": {"basic": [], "advanced": []}
        }
        
        # Sort certifications by category and level
        for cert_id in member_certs:
            if cert_id in CERTIFICATIONS:
                info = CERTIFICATIONS[cert_id]
                category = info.get("category", "other")
                level = info.get("level", "basic")
                name = info.get("name", cert_id)
            elif cert_id in SHIP_CERTIFICATIONS:
                info = SHIP_CERTIFICATIONS[cert_id]
                category = "ship"
                level = "advanced" if "HEAVY" in cert_id or "LARGE" in cert_id else "basic"
                name = info.get("name", cert_id)
            else:
                category = "other"
                level = "basic"
                name = cert_id
            
            if category in categories:
                if level in categories[category]:
                    categories[category][level].append(name)
        
        # Create embed
        embed = discord.Embed(
            title=f"Your Certifications - {fleet_component}",
            description=f"You have {len(member_certs)} certification(s)",
            color=discord.Color.blue()
        )
        
        # Add fields for each category
        for category, levels in categories.items():
            basic_certs = levels.get("basic", [])
            advanced_certs = levels.get("advanced", [])
            
            if basic_certs:
                embed.add_field(
                    name=f"Basic {category.title()}",
                    value="\n".join(f"• {cert}" for cert in basic_certs),
                    inline=False
                )
                
            if advanced_certs:
                embed.add_field(
                    name=f"Advanced {category.title()}",
                    value="\n".join(f"• {cert}" for cert in advanced_certs),
                    inline=False
                )
        
        # Add recommended next certifications based on fleet component
        recommended = []
        for cert_id, info in CERTIFICATIONS.items():
            if cert_id in member_certs:
                continue
            
            # Check if this certification is applicable to the member's fleet component
            applicable_fleets = info.get('fleet_components', [])
            if applicable_fleets and fleet_component not in applicable_fleets:
                continue
                
            prerequisites = info.get('prerequisites', [])
            if not prerequisites:
                continue
                
            # Check if member has all prerequisites
            has_all_prereqs = True
            for prereq in prerequisites:
                if prereq not in member_certs:
                    has_all_prereqs = False
                    break
            
            if has_all_prereqs:
                recommended.append(info.get('name', cert_id))
        
        if recommended:
            embed.add_field(
                name="Recommended Next Certifications",
                value="\n".join(f"• {cert}" for cert in recommended[:5]),
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =============== CERTIFICATION MANAGEMENT HELPERS ===============

    async def update_certification_roles(self, member: discord.Member):
        """Update member's roles based on certifications."""
        if not self._guild:
            return
        
        try:
            # Get member's certifications
            member_certs = await self.coda_manager.get_member_certifications(member.id)
            
            # Check each role mapping
            for cert_id, role_id in CERTIFICATION_ROLES.items():
                if not role_id:  # Skip mappings without role IDs
                    continue
                    
                role = self._guild.get_role(role_id)
                if not role:
                    continue
                    
                has_cert = cert_id in member_certs
                has_role = role in member.roles
                
                if has_cert and not has_role:
                    # Grant role
                    await member.add_roles(role, reason=f"Certified in {cert_id}")
                    logger.info(f"Granted {role.name} role to {member.name} based on certification")
                elif not has_cert and has_role:
                    # Remove role
                    await member.remove_roles(role, reason=f"No longer certified in {cert_id}")
                    logger.info(f"Removed {role.name} role from {member.name} based on certification")
        except Exception as e:
            logger.error(f"Error updating certification roles: {e}")

    async def set_certification_expiry(self, user_id: int, certification: str, expiry_date: datetime):
        """Set expiry date for a certification."""
        try:
            # Get member data
            member_data = await self.coda_manager.get_member_data(user_id)
            if not member_data:
                return False
                
            # Get current expiry data
            expiry_data = member_data.get('Certification Expiry', '')
            
            # Parse existing expiry data (format: cert_id:YYYY-MM-DD,cert_id:YYYY-MM-DD)
            expiry_dict = {}
            if expiry_data:
                for entry in expiry_data.split(','):
                    if ':' in entry:
                        cert, date_str = entry.strip().split(':', 1)
                        expiry_dict[cert.strip()] = date_str.strip()
            
            # Set new expiry date
            expiry_dict[certification] = expiry_date.strftime("%Y-%m-%d")
            
            # Format back to string
            new_expiry_data = ','.join([f"{cert}:{date}" for cert, date in expiry_dict.items()])
            
            # Update in database
            return await self.coda_manager.update_member_info(
                member_data['id'],
                {'Certification Expiry': new_expiry_data}
            )
            
        except Exception as e:
            logger.error(f"Error setting certification expiry: {e}")
            return False

    async def remove_certification_expiry(self, user_id: int, certification: str):
        """Remove expiry date for a certification."""
        try:
            # Get member data
            member_data = await self.coda_manager.get_member_data(user_id)
            if not member_data:
                return False
                
            # Get current expiry data
            expiry_data = member_data.get('Certification Expiry', '')
            if not expiry_data:
                return True  # No expiry data to remove
                
            # Parse existing expiry data
            expiry_dict = {}
            for entry in expiry_data.split(','):
                if ':' in entry:
                    cert, date_str = entry.strip().split(':', 1)
                    if cert.strip() != certification:  # Skip the one we're removing
                        expiry_dict[cert.strip()] = date_str.strip()
            
            # Format back to string
            new_expiry_data = ','.join([f"{cert}:{date}" for cert, date in expiry_dict.items()])
            
            # Update in database
            return await self.coda_manager.update_member_info(
                member_data['id'],
                {'Certification Expiry': new_expiry_data}
            )
            
        except Exception as e:
            logger.error(f"Error removing certification expiry: {e}")
            return False

    @tasks.loop(hours=24)
    async def certification_expiry_check(self):
        """Check for certifications that need renewal."""
        if not self._ready.is_set():
            await self._ready.wait()
            
        # Set to run at a specific time
        now = datetime.now()
        if now.hour != 8 or now.minute != 0:  # 8:00 AM
            return
            
        try:
            # Get all members
            all_members = await self.coda_manager.get_all_members()
            
            current_time = datetime.now()
            expiring_soon = []
            expired = []
            
            for member_data in all_members:
                user_id = member_data.get('Discord User ID')
                if not user_id:
                    continue
                    
                cert_expiry = member_data.get('Certification Expiry', '')
                if not cert_expiry:
                    continue
                    
                # Parse expiry data (format: cert_id:YYYY-MM-DD,cert_id:YYYY-MM-DD)
                expiry_entries = [entry.strip() for entry in cert_expiry.split(',') if entry.strip()]
                
                for entry in expiry_entries:
                    if ':' not in entry:
                        continue
                        
                    cert_id, expiry_date_str = entry.split(':', 1)
                    cert_id = cert_id.strip()
                    expiry_date_str = expiry_date_str.strip()
                    
                    try:
                        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d")
                        
                        # Get certification name
                        cert_name = cert_id
                        if cert_id in CERTIFICATIONS:
                            cert_name = CERTIFICATIONS[cert_id].get('name', cert_id)
                        elif cert_id in SHIP_CERTIFICATIONS:
                            cert_name = SHIP_CERTIFICATIONS[cert_id].get('name', cert_id)
                        
                        # Get member
                        member = self._guild.get_member(int(user_id))
                        if not member:
                            continue
                            
                        # Check if expired
                        days_until_expiry = (expiry_date - current_time).days
                        
                        if days_until_expiry <= 0:
                            # Already expired
                            expired.append((member, cert_id, cert_name, abs(days_until_expiry)))
                        elif days_until_expiry <= self.config.get('CERT_WARNING_DAYS', 14):
                            # Expiring soon
                            expiring_soon.append((member, cert_id, cert_name, days_until_expiry))
                            
                    except (ValueError, TypeError):
                        continue
            
            # Send notifications if any are expiring soon or expired
            if (expiring_soon or expired) and self.config.get('ADMIN_NOTIFICATIONS_CHANNEL_ID'):
                channel = self.bot.get_channel(self.config['ADMIN_NOTIFICATIONS_CHANNEL_ID'])
                if channel:
                    embed = discord.Embed(
                        title="Certification Renewal Report",
                        description="Status of certifications that need attention",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    # Add expiring soon section
                    if expiring_soon:
                        expiry_text = ""
                        for member, cert_id, cert_name, days in sorted(expiring_soon, key=lambda x: x[3]):
                            expiry_text += f"• {member.mention} - **{cert_name}** expires in {days} days\n"
                        
                        embed.add_field(
                            name="Expiring Soon",
                            value=expiry_text,
                            inline=False
                        )
                    
                    # Add expired section
                    if expired:
                        expired_text = ""
                        for member, cert_id, cert_name, days in sorted(expired, key=lambda x: x[3], reverse=True):
                            expired_text += f"• {member.mention} - **{cert_name}** expired {days} days ago\n"
                        
                        embed.add_field(
                            name="Expired Certifications",
                            value=expired_text,
                            inline=False
                        )
                    
                    await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error checking certification expirations: {e}")

    @tasks.loop(hours=24)
    async def daily_certification_report(self):
        """Send a daily certification report to command staff."""
        if not self._ready.is_set():
            await self._ready.wait()
            
        # Set to run at a specific time
        now = datetime.now()
        if now.hour != 7 or now.minute != 0:  # 7:00 AM
            return
            
        # Get certification statistics
        report = await self.coda_manager.get_certification_report()
        if not report:
            return
        
        # Create report embed
        embed = discord.Embed(
            title="Daily Certification Report",
            description="Summary of certifications across the organization",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add general statistics
        embed.add_field(
            name="Statistics",
            value=(
                f"**Total Members:** {report.get('total_members', 0)}\n"
                f"**Members with Certifications:** {report.get('members_with_certs', 0)}\n"
                f"**Total Certifications Granted:** {report.get('total_certs_granted', 0)}\n"
                f"**Average per Member:** {round(report.get('total_certs_granted', 0) / max(1, report.get('members_with_certs', 1)), 1)}"
            ),
            inline=False
        )
        
        # Send to command staff channel
        if self.config.get('ADMIN_NOTIFICATIONS_CHANNEL_ID'):
            try:
                channel = self.bot.get_channel(self.config['ADMIN_NOTIFICATIONS_CHANNEL_ID'])
                if channel:
                    await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Error sending daily certification report: {e}")

    async def cog_load(self) -> None:
        """Called when the cog is loaded."""
        logger.info("Loading AdministrationCog...")
        try:
            # Initialize Coda columns
            if not await self.coda_manager.initialize_columns():
                raise ValueError("Failed to initialize Coda columns")
            logger.info("Successfully initialized Coda columns")

        except Exception as e:
            logger.error(f"Failed to load AdministrationCog: {e}")
            raise

    async def cog_unload(self) -> None:
        """Called when the cog is unloaded."""
        logger.info("Unloading AdministrationCog...")
        # Cleanup code here if needed

async def setup(bot: commands.Bot):
    """Set up the AdministrationCog."""
    try:
        await bot.add_cog(AdministrationCog(bot))
        logger.info("Successfully loaded AdministrationCog")
    except Exception as e:
        logger.error(f"Failed to load AdministrationCog: {e}")