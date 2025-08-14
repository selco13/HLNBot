# cogs/aar.py
from __future__ import annotations
from typing import Dict, List, Optional, Any, Set, Tuple, TYPE_CHECKING

import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
from datetime import datetime, timezone
from enum import Enum
import json
import aiohttp
import asyncio
from dataclasses import dataclass, field, asdict
import re

# Define enums before they're used
class AARType(Enum):
    COMBAT = "Combat Operation"
    MINING = "Mining Operation"
    TRADING = "Trading Run"
    EXPLORATION = "Exploration"
    MEDICAL = "Medical Mission"
    TRAINING = "Training Exercise"
    OTHER = "Other Operation"

class AAROutcome(Enum):
    SUCCESS = "Success"
    PARTIAL = "Partial Success"
    FAILURE = "Failure"
    CANCELLED = "Cancelled"
    INCOMPLETE = "Incomplete"

class AARMedal(Enum):
    # Existing Generic Medals
    VALOR = "Medal of Valor"
    SERVICE = "Service Medal"
    COMBAT = "Combat Medal"
    EXPLORATION = "Explorer's Medal"
    LEADERSHIP = "Leadership Medal"
    TRAINING = "Training Excellence"
    TEAMWORK = "Teamwork Medal"
    
    # New Specific Awards
    HLN_STARWARD = "HLN Starward Medal"
    GALACTIC_SERVICE_GOLD = "Galactic Service Ribbon in Gold"
    GALACTIC_SERVICE_SILVER = "Galactic Service Ribbon in Silver"
    GALACTIC_SERVICE = "Galactic Service Ribbon"
    INNOVATORS_CREST_EXCELLENCE = "Innovator's Crest of Excellence"
    INNOVATORS_CREST_DISTINCTION = "Innovator's Crest of Distinction"
    INNOVATORS_CREST = "Innovator's Crest"
    DIVISIONAL_EXCELLENCE = "Divisional Excellence Trophy"
    UNIT_CITATION = "Unit Citation Ribbon"

if TYPE_CHECKING:
    from .mission_system.shared import (
        MissionType, MissionStatus, Participant,
        MissionSystemUtilities as utils
    )
    from .utils.profile_events import ProfileEvent, ProfileEventType
    from .utils.sc_profile_types import SCProfile, CareerPath, ExperienceLevel

# Configure logging
logger = logging.getLogger('aar')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='aar.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# Load environment variables
GUILD_ID = int(os.getenv('GUILD_ID', 0))
CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
DOC_ID = os.getenv('DOC_ID')
AAR_TABLE_ID = os.getenv('AAR_TABLE_ID')
AAR_CHANNEL_ID = int(os.getenv('AAR_CHANNEL_ID', 0))
STAFF_NOTIFICATION_CHANNEL_ID = int(os.getenv('STAFF_NOTIFICATION_CHANNEL_ID', 0))

@dataclass
class AARParticipant:
    """Represents a participant in an AAR with enhanced details."""
    user_id: int
    ship: str
    role: str
    contribution: Optional[str] = None
    medals: List[AARMedal] = field(default_factory=list)
    performance_notes: Optional[str] = None
    key_actions: List[str] = field(default_factory=list)
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    promotion_recommended: bool = False
    promotion_reason: Optional[str] = None
    promotion_achievements: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'user_id': self.user_id,
            'ship': self.ship,
            'role': self.role,
            'contribution': self.contribution,
            'medals': [medal.name for medal in self.medals],
            'performance_notes': self.performance_notes,
            'key_actions': self.key_actions,
            'joined_at': self.joined_at.isoformat(),
            'promotion_recommended': self.promotion_recommended,
            'promotion_reason': self.promotion_reason,
            'promotion_achievements': self.promotion_achievements
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AARParticipant':
        """Create AARParticipant from dictionary data."""
        data = data.copy()
        
        # Convert medals if present
        if 'medals' in data and isinstance(data['medals'], list):
            medals = []
            for medal in data['medals']:
                if isinstance(medal, str):
                    try:
                        medals.append(AARMedal[medal])
                    except KeyError:
                        continue
                elif isinstance(medal, AARMedal):
                    medals.append(medal)
            data['medals'] = medals

        # Convert joined_at if it's a string
        if 'joined_at' in data and isinstance(data['joined_at'], str):
            data['joined_at'] = datetime.fromisoformat(data['joined_at'])

        # Remove any fields not in the class
        valid_fields = {
            'user_id', 'ship', 'role', 'contribution', 'medals', 
            'performance_notes', 'key_actions', 'joined_at',
            'promotion_recommended', 'promotion_reason', 'promotion_achievements'
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)
        
    def to_embed_field(self, bot: commands.Bot) -> str:
        """Convert participant data to embed field string."""
        member = bot.get_guild(GUILD_ID).get_member(self.user_id)
        
        field_text = []
        if member:
            field_text.append(f"**Member:** {member.mention}")
        field_text.append(f"**Role:** {self.role}")
        field_text.append(f"**Ship:** {self.ship}")
        
        if self.contribution:
            field_text.append(f"**Contribution:** {self.contribution}")
        
        if self.performance_notes:
            field_text.append(f"**Notes:** {self.performance_notes}")
            
        if self.key_actions:
            actions = "\n".join(f"• {action}" for action in self.key_actions)
            field_text.append(f"**Key Actions:**\n{actions}")
        
        if self.medals:
            medals = "\n".join(f"• {medal.value}" for medal in self.medals)
            field_text.append(f"**Medals:**\n{medals}")
            
        return "\n".join(field_text)

@dataclass
class AAR:
    """Enhanced After Action Report class."""
    mission_name: str
    aar_type: AARType
    outcome: AAROutcome
    description: str
    leader_id: int
    member_earnings: float
    org_earnings: float
    objectives: List[str]
    participants: Dict[int, AARParticipant] = field(default_factory=dict)
    lessons_learned: Optional[str] = None
    followup_actions: Optional[str] = None
    creation_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    debrief_notes: Optional[str] = None
    completed_objectives: List[str] = field(default_factory=list)
    resources_used: Optional[Dict[str, int]] = None
    mission_achievements: List[str] = field(default_factory=list)
    technical_issues: List[str] = field(default_factory=list)
    combat_stats: Optional[Dict[str, Any]] = None
    mission_video_url: Optional[str] = None
    screenshots: List[str] = field(default_factory=list)
    aar_id: str = field(default_factory=lambda: os.urandom(8).hex())
    finalized: bool = False
    mission_id: Optional[str] = None  # Store the original mission ID for reference
    message_id: Optional[int] = None  # Store message ID for updating
    fleet_assignments: Optional[Dict[str, List[str]]] = None  # Store fleet assignments data

    def to_dict(self) -> dict:
        """Convert AAR to dictionary for storage."""
        data = asdict(self)
        data['aar_type'] = self.aar_type.name
        data['outcome'] = self.outcome.name
        data['creation_time'] = self.creation_time.isoformat()
        data['participants'] = {
            str(user_id): participant.to_dict()
            for user_id, participant in self.participants.items()
        }
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'AAR':
        """Create AAR from dictionary data."""
        data = data.copy()
        
        # Handle aar_type conversion
        if isinstance(data['aar_type'], str):
            data['aar_type'] = AARType[data['aar_type']]
        
        # Handle outcome conversion
        if isinstance(data['outcome'], str):
            data['outcome'] = AAROutcome[data['outcome']]
        
        # Convert creation_time
        if isinstance(data['creation_time'], str):
            data['creation_time'] = datetime.fromisoformat(data['creation_time'])

        # Handle participants conversion
        if 'participants' in data:
            if isinstance(data['participants'], dict):
                converted_participants = {}
                for user_id, p_data in data['participants'].items():
                    try:
                        converted_participants[int(user_id)] = AARParticipant.from_dict(p_data)
                    except Exception as e:
                        logger.error(f"Error converting participant {user_id}: {e}")
                data['participants'] = converted_participants

        # Initialize any missing fields with default values
        for field in [
            'lessons_learned', 'followup_actions', 'debrief_notes',
            'resources_used', 'combat_stats', 'mission_video_url',
            'mission_id', 'message_id', 'fleet_assignments'
        ]:
            if field not in data:
                data[field] = None

        for field in ['completed_objectives', 'mission_achievements', 'technical_issues', 'screenshots']:
            if field not in data:
                data[field] = []

        return cls(**data)

    def to_embed(self, bot: commands.Bot) -> discord.Embed:
        """Convert AAR to Discord embed with field length limiting."""
        embed = discord.Embed(
            title=f"After Action Report: {self.mission_name}",
            description=self.description,
            color=self.get_status_color(),
            timestamp=self.creation_time
        )
        leader = bot.get_guild(GUILD_ID).get_member(self.leader_id)
        embed.add_field(
            name="📋 Mission Details",
            value=(
                f"**Type:** {self.aar_type.value}\n"
                f"**Outcome:** {self.outcome.value}\n"
                f"**Leader:** {leader.mention if leader else 'Unknown'}\n"
                f"**Created:** {discord.utils.format_dt(self.creation_time, 'F')}"
            ),
            inline=False
        )
    
        # Objectives completion
        completed = len(self.completed_objectives)
        total = len(self.objectives)
        completion_rate = (completed / total * 100) if total > 0 else 0
        objectives_text = ""
        for idx, obj in enumerate(self.objectives):
            status = "✅" if obj in self.completed_objectives else "❌"
            objectives_text += f"{status} {obj}\n"
            
            # Truncate if getting too long
            if len(objectives_text) > 970:
                objectives_text = objectives_text[:970] + "...\n(too many objectives to display)"
                break
                
        if objectives_text:
            embed.add_field(
                name=f"🎯 Objectives ({completed}/{total} - {completion_rate:.1f}%)",
                value=objectives_text,
                inline=False
            )
    
        # Earnings
        total_earnings = self.member_earnings + self.org_earnings
        embed.add_field(
            name="💰 Earnings",
            value=(
                f"**Member Earnings:** {self.member_earnings:,.0f} aUEC\n"
                f"**Organization Cut:** {self.org_earnings:,.0f} aUEC\n"
                f"**Total Value:** {total_earnings:,.0f} aUEC"
            ),
            inline=False
        )
    
        # Participants - Handle this carefully to avoid overflowing
        if self.participants:
            # First determine how many participants we can display in full
            total_length = 0
            participants_text = []
            
            for user_id, participant in self.participants.items():
                member = bot.get_guild(GUILD_ID).get_member(user_id)
                
                # Format participant info
                participant_info = ""
                if member:
                    participant_info += f"**Member:** {member.mention}\n"
                else:
                    participant_info += f"**Member:** Unknown (ID: {user_id})\n"
                    
                participant_info += f"**Role:** {participant.role}\n"
                participant_info += f"**Ship:** {participant.ship}\n"
                
                if participant.contribution:
                    participant_info += f"**Contribution:** {participant.contribution}\n"
                
                if participant.performance_notes:
                    # Truncate long performance notes
                    notes = participant.performance_notes
                    if len(notes) > 100:
                        notes = notes[:97] + "..."
                    participant_info += f"**Notes:** {notes}\n"
                    
                if participant.key_actions:
                    actions = "\n".join(f"• {action}" for action in participant.key_actions[:3])
                    if len(participant.key_actions) > 3:
                        actions += f"\n• ...and {len(participant.key_actions) - 3} more"
                    participant_info += f"**Key Actions:**\n{actions}\n"
                
                if participant.medals:
                    medals_list = [medal.value for medal in participant.medals]
                    if len(medals_list) <= 3:
                        medals = "\n".join(f"• {medal}" for medal in medals_list)
                    else:
                        medals = "\n".join(f"• {medal}" for medal in medals_list[:2])
                        medals += f"\n• ...and {len(medals_list) - 2} more"
                    participant_info += f"**Medals:**\n{medals}\n"
                
                # Check if adding this would exceed the limit
                if total_length + len(participant_info) + 2 > 1000:  # +2 for the extra newlines
                    # If we're on the first participant, we need to truncate
                    if not participants_text:
                        # Truncate this participant's info to fit
                        max_length = 1000 - total_length - 2
                        participant_info = participant_info[:max_length - 20] + "...(truncated)"
                        participants_text.append(participant_info)
                    
                    # Add a note about remaining participants
                    remaining = len(self.participants) - len(participants_text)
                    if remaining > 0:
                        participants_text.append(f"\n...and {remaining} more participant(s)")
                    break
                
                # Add this participant's info
                participants_text.append(participant_info)
                total_length += len(participant_info) + 2  # +2 for the extra newlines
            
            # Join all participant text with newlines between entries
            final_text = "\n\n".join(participants_text)
            
            # Double-check length to be absolutely sure
            if len(final_text) > 1024:
                final_text = final_text[:1020] + "..."
            
            embed.add_field(
                name=f"👥 Participants ({len(self.participants)})",
                value=final_text or "No participants recorded",
                inline=False
            )
    
        # Fleet Assignments
        if self.fleet_assignments and any(self.fleet_assignments.values()):
            fleet_text = []
            
            if self.fleet_assignments.get('squadrons'):
                fleet_text.append("**Squadrons:**")
                fleet_text.extend(f"• {sq}" for sq in self.fleet_assignments['squadrons'][:5])
                if len(self.fleet_assignments['squadrons']) > 5:
                    fleet_text.append(f"• ...and {len(self.fleet_assignments['squadrons']) - 5} more")
                
            if self.fleet_assignments.get('flight_groups'):
                fleet_text.append("**Flight Groups:**")
                fleet_text.extend(f"• {fg}" for fg in self.fleet_assignments['flight_groups'][:5])
                if len(self.fleet_assignments['flight_groups']) > 5:
                    fleet_text.append(f"• ...and {len(self.fleet_assignments['flight_groups']) - 5} more")
                
            if self.fleet_assignments.get('ships'):
                fleet_text.append("**Ships:**")
                fleet_text.extend(f"• {ship}" for ship in self.fleet_assignments['ships'][:5])
                if len(self.fleet_assignments['ships']) > 5:
                    fleet_text.append(f"• ...and {len(self.fleet_assignments['ships']) - 5} more")
                
            if fleet_text:
                # Ensure we don't exceed field length limit
                fleet_value = "\n".join(fleet_text)
                if len(fleet_value) > 1024:
                    fleet_value = fleet_value[:1020] + "..."
                    
                embed.add_field(
                    name="⚓ Fleet Assets",
                    value=fleet_value,
                    inline=False
                )
    
        # Achievements
        if self.mission_achievements:
            achievements_text = "\n".join(f"• {achievement}" for achievement in self.mission_achievements[:10])
            if len(self.mission_achievements) > 10:
                achievements_text += f"\n• ...and {len(self.mission_achievements) - 10} more"
                
            embed.add_field(
                name="🏆 Achievements",
                value=achievements_text,
                inline=False
            )
    
        # Combat stats
        if self.combat_stats:
            combat_text = []
            for stat_name, stat_value in list(self.combat_stats.items())[:8]:  # Limit to 8 stats
                if isinstance(stat_value, (int, float)):
                    combat_text.append(f"**{stat_name}:** {stat_value:,}")
                else:
                    combat_text.append(f"**{stat_name}:** {stat_value}")
            
            if len(self.combat_stats) > 8:
                combat_text.append(f"...and {len(self.combat_stats) - 8} more stats")
                
            if combat_text:
                embed.add_field(
                    name="⚔️ Combat Statistics",
                    value="\n".join(combat_text),
                    inline=False
                )
    
        # Resources
        if self.resources_used:
            resources_items = list(self.resources_used.items())
            resources_text = "\n".join(
                f"**{name}:** {amount:,}"
                for name, amount in resources_items[:10]  # Limit to 10 resources
            )
            
            if len(resources_items) > 10:
                resources_text += f"\n...and {len(resources_items) - 10} more resources"
                
            embed.add_field(
                name="📦 Resources Used",
                value=resources_text,
                inline=False
            )
    
        # Technical issues
        if self.technical_issues:
            issues_text = "\n".join(f"• {issue}" for issue in self.technical_issues[:8])
            if len(self.technical_issues) > 8:
                issues_text += f"\n• ...and {len(self.technical_issues) - 8} more issues"
                
            embed.add_field(
                name="🔧 Technical Issues",
                value=issues_text,
                inline=False
            )
    
        # Lessons learned & actions - ensure these don't exceed limits
        if self.lessons_learned:
            if len(self.lessons_learned) > 1024:
                lessons = self.lessons_learned[:1020] + "..."
            else:
                lessons = self.lessons_learned
                
            embed.add_field(
                name="📝 Lessons Learned",
                value=lessons,
                inline=False
            )
    
        if self.followup_actions:
            if len(self.followup_actions) > 1024:
                actions = self.followup_actions[:1020] + "..."
            else:
                actions = self.followup_actions
                
            embed.add_field(
                name="📋 Follow-up Actions",
                value=actions,
                inline=False
            )
    
        if self.debrief_notes:
            if len(self.debrief_notes) > 1024:
                notes = self.debrief_notes[:1020] + "..."
            else:
                notes = self.debrief_notes
                
            embed.add_field(
                name="📔 Debrief Notes",
                value=notes,
                inline=False
            )
    
        # Media links
        media_links = []
        if self.mission_video_url:
            media_links.append(f"📹 [Mission Recording]({self.mission_video_url})")
        if self.screenshots:
            for i, url in enumerate(self.screenshots[:5]):
                media_links.append(f"📸 [Screenshot {i+1}]({url})")
            if len(self.screenshots) > 5:
                media_links.append(f"...and {len(self.screenshots) - 5} more screenshots")
                
        if media_links:
            embed.add_field(
                name="📸 Media",
                value="\n".join(media_links),
                inline=False
            )
    
        # Status footer
        status = "✅ Finalized" if self.finalized else "📝 In Progress"
        embed.set_footer(text=f"AAR ID: {self.aar_id} | Status: {status}")
        return embed

    def get_status_color(self) -> discord.Color:
        """Get color based on mission outcome."""
        colors = {
            AAROutcome.SUCCESS: discord.Color.green(),
            AAROutcome.PARTIAL: discord.Color.gold(),
            AAROutcome.FAILURE: discord.Color.red(),
            AAROutcome.CANCELLED: discord.Color.light_grey(),
            AAROutcome.INCOMPLETE: discord.Color.orange()
        }
        return colors.get(self.outcome, discord.Color.default())

class AARFeedbackView(discord.ui.View):
    def __init__(self, cog: 'AARCommands', aar: AAR):
        super().__init__(timeout=None)  # Set timeout to None for persistent view
        self.cog = cog
        self.aar = aar
        self.custom_id_prefix = f"aar_{aar.aar_id}"

    @discord.ui.button(
        label="Finalize AAR", 
        style=discord.ButtonStyle.red,
        custom_id="finalize_aar"
    )
    async def finalize_aar(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle finalizing the AAR."""
        try:
            if self.aar.finalized:
                await interaction.response.send_message("✅ This AAR is already finalized.", ephemeral=True)
                return

            # Defer the response since we'll be doing multiple operations
            await interaction.response.defer()

            self.aar.finalized = True
            await self.cog.save_aar(self.aar)

            # Update the message with the new embed and remove the view
            await interaction.edit_original_response(
                embed=self.aar.to_embed(self.cog.bot),
                view=None
            )

            # Send finalization confirmation
            await interaction.followup.send("✅ AAR has been finalized.", ephemeral=True)

            # Process profile updates for all participants
            profile_cog = self.cog.bot.get_cog('ProfileCog')
            if profile_cog:
                for user_id, participant in self.aar.participants.items():
                    try:
                        # Update profile with mission completion
                        await profile_cog.add_mission_completion(
                            user_id=user_id,
                            mission_name=self.aar.mission_name,
                            mission_type=self.aar.aar_type.value,
                            role=participant.role,
                            ship=participant.ship
                        )

                        # Add any medals awarded
                        if participant.medals:
                            for medal in participant.medals:
                                try:
                                    citation = participant.performance_notes or f"Awarded for exemplary performance during {self.aar.mission_name}"
                                    await profile_cog.add_award(
                                        member=interaction.guild.get_member(user_id),
                                        award=medal.value,
                                        citation=citation
                                    )
                                except Exception as medal_error:
                                    logger.error(f"Error adding medal {medal.value} to profile for user {user_id}: {medal_error}")

                    except Exception as e:
                        logger.error(f"Error updating profile for user {user_id}: {e}")

            # Send completion notification to original mission channel if possible
            if self.aar.mission_id:
                try:
                    mission_cog = self.cog.bot.get_cog('MissionCog')
                    if mission_cog:
                        mission = mission_cog.missions.get(self.aar.mission_id)
                        if mission and mission.channel_id:
                            channel = self.cog.bot.get_channel(mission.channel_id)
                            if channel:
                                summary_embed = discord.Embed(
                                    title=f"Mission Complete: AAR Finalized",
                                    description=f"The After Action Report for mission '{self.aar.mission_name}' has been finalized.",
                                    color=discord.Color.green()
                                )
                                summary_embed.add_field(
                                    name="Outcome",
                                    value=self.aar.outcome.value,
                                    inline=True
                                )
                                summary_embed.add_field(
                                    name="Earnings",
                                    value=f"{self.aar.member_earnings:,.0f} aUEC",
                                    inline=True
                                )
                                
                                view = discord.ui.View(timeout=None)
                                button = discord.ui.Button(
                                    label="View Full AAR",
                                    style=discord.ButtonStyle.url,
                                    url=f"https://discord.com/channels/{GUILD_ID}/{AAR_CHANNEL_ID}/{self.aar.message_id}"
                                    if hasattr(self.aar, 'message_id') and self.aar.message_id else discord.utils.MISSING
                                )
                                view.add_item(button)
                                
                                await channel.send(embed=summary_embed, view=view)
                except Exception as e:
                    logger.error(f"Error sending mission completion notification: {e}")

        except Exception as e:
            logger.error(f"Error finalizing AAR: {e}")
            await interaction.followup.send(
                "❌ An error occurred while finalizing the AAR.", 
                ephemeral=True
            )

    @discord.ui.button(
        label="Edit AAR Details", 
        style=discord.ButtonStyle.primary,
        custom_id="edit_aar_details"
    )
    async def edit_aar_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the AAR details editing modal."""
        try:
            if self.aar.finalized:
                await interaction.response.send_message("This AAR is already finalized and cannot be edited.", ephemeral=True)
                return
                
            # Only allow leader or admins to edit
            if interaction.user.id != self.aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only the mission leader or administrators can edit this AAR.", ephemeral=True)
                return
                
            # Create and send the modal
            modal = AARDetailsModal(self.cog, self.aar)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error opening AAR edit modal: {e}")
            await interaction.response.send_message("An error occurred while trying to edit the AAR.", ephemeral=True)
    
    @discord.ui.button(
        label="Add Combat Stats", 
        style=discord.ButtonStyle.secondary,
        custom_id="add_combat_stats_button",
        row=1
    )
    async def add_combat_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add combat statistics to the AAR."""
        try:
            if self.aar.finalized:
                await interaction.response.send_message("This AAR is already finalized and cannot be edited.", ephemeral=True)
                return
                
            # Only allow leader or admins to edit
            if interaction.user.id != self.aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only the mission leader or administrators can edit this AAR.", ephemeral=True)
                return
                
            # Create and send the modal
            modal = CombatStatsModal(self.cog, self.aar)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error opening combat stats modal: {e}")
            await interaction.response.send_message("An error occurred while trying to add combat statistics.", ephemeral=True)

    @discord.ui.button(
        label="Add Media", 
        style=discord.ButtonStyle.secondary,
        custom_id="add_media_button",
        row=1
    )
    async def add_media(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add media links to the AAR."""
        try:
            if self.aar.finalized:
                await interaction.response.send_message("This AAR is already finalized and cannot be edited.", ephemeral=True)
                return
                
            # Only allow leader or admins to edit
            if interaction.user.id != self.aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only the mission leader or administrators can edit this AAR.", ephemeral=True)
                return
                
            # Create and send the modal
            modal = MediaLinksModal(self.cog, self.aar)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error opening media links modal: {e}")
            await interaction.response.send_message("An error occurred while trying to add media links.", ephemeral=True)
            
    @discord.ui.button(
        label="Award Medals", 
        style=discord.ButtonStyle.primary,
        custom_id="award_medals_button",
        row=1
    )
    async def award_medals(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Award medals to mission participants."""
        try:
            if self.aar.finalized:
                await interaction.response.send_message("This AAR is already finalized. Medals can no longer be added.", ephemeral=True)
                return
                
            # Only allow leader or admins to award medals
            if interaction.user.id != self.aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only the mission leader or administrators can award medals.", ephemeral=True)
                return
                
            if not self.aar.participants:
                await interaction.response.send_message("There are no participants to award medals to.", ephemeral=True)
                return
            
            # Create the medal selection view
            view = MedalSelectionView(self.cog, self.aar)
            await interaction.response.send_message("Select participants and medals to award:", view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error opening medal selection: {e}")
            await interaction.response.send_message("An error occurred while trying to award medals.", ephemeral=True)
    
    @discord.ui.button(
        label="Edit Participant Notes", 
        style=discord.ButtonStyle.secondary,
        custom_id="edit_participant_notes_button",
        row=2
    )
    async def edit_participant_notes(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Edit notes for mission participants."""
        try:
            if self.aar.finalized:
                await interaction.response.send_message("This AAR is already finalized. Participant notes can no longer be edited.", ephemeral=True)
                return
                
            # Only allow leader or admins to edit notes
            if interaction.user.id != self.aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only the mission leader or administrators can edit participant notes.", ephemeral=True)
                return
                
            if not self.aar.participants:
                await interaction.response.send_message("There are no participants to edit notes for.", ephemeral=True)
                return
            
            # Create the participant selection dropdown
            options = []
            guild = interaction.guild
            
            for user_id, participant in self.aar.participants.items():
                member = guild.get_member(user_id)
                display_name = member.display_name if member else f"Unknown User ({user_id})"
                options.append(discord.SelectOption(
                    label=display_name,
                    value=str(user_id),
                    description=f"{participant.role} on {participant.ship}"
                ))
            
            # Create select menu and send
            select = ParticipantSelect(self.cog, self.aar, options)
            view = discord.ui.View(timeout=300)
            view.add_item(select)
            
            await interaction.response.send_message(
                "Select a participant to edit their notes:",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error opening participant notes selection: {e}")
            await interaction.response.send_message("An error occurred while trying to edit participant notes.", ephemeral=True)

class MedalSelectionView(discord.ui.View):
    """View for selecting participants and medals to award."""
    
    def __init__(self, cog, aar):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.aar = aar
        self.selected_user_ids = []
        self.selected_medals = []
        
        # Add participant selector
        self.add_item(ParticipantSelectMenu(self, aar))
        
        # Add medal selector
        self.add_item(MedalSelectMenu(self))
        
        # Add award button
        award_button = discord.ui.Button(
            label="Award Selected Medals",
            style=discord.ButtonStyle.success,
            disabled=True
        )
        award_button.callback = self.award_medals_callback
        self.add_item(award_button)
        self.award_button = award_button
        
    def update_button_state(self):
        """Update the award button's enabled/disabled state."""
        self.award_button.disabled = not (self.selected_user_ids and self.selected_medals)
        
    async def award_medals_callback(self, interaction: discord.Interaction):
        """Process awarding medals to selected participants."""
        try:
            if not self.selected_user_ids or not self.selected_medals:
                await interaction.response.send_message("Please select at least one participant and one medal.", ephemeral=True)
                return
                
            # Award medals to each selected participant
            awarded_to = []
            for user_id in self.selected_user_ids:
                participant = self.aar.participants.get(int(user_id))
                if participant:
                    # Convert medal strings to enum values
                    for medal_name in self.selected_medals:
                        try:
                            medal = AARMedal[medal_name]
                            # Only add if not already awarded
                            if medal not in participant.medals:
                                participant.medals.append(medal)
                        except KeyError:
                            logger.error(f"Invalid medal name: {medal_name}")
                    
                    # Get member name for display
                    member = self.cog.bot.get_guild(GUILD_ID).get_member(int(user_id))
                    if member:
                        awarded_to.append(member.display_name)
            
            if awarded_to:
                # Save the AAR
                await self.cog.save_aar(self.aar)
                
                # Create a nice confirmation message
                medal_names = [AARMedal[m].value for m in self.selected_medals if m in AARMedal.__members__]
                medals_text = ", ".join(medal_names)
                participants_text = ", ".join(awarded_to)
                
                await interaction.response.send_message(
                    f"✅ Successfully awarded {medals_text} to {participants_text}.",
                    ephemeral=True
                )
                
                # Update the AAR embed
                channel = self.cog.bot.get_channel(AAR_CHANNEL_ID)
                if channel and self.aar.message_id:
                    try:
                        message = await channel.fetch_message(self.aar.message_id)
                        embed = self.aar.to_embed(self.cog.bot)
                        view = AARFeedbackView(self.cog, self.aar) if not self.aar.finalized else None
                        await message.edit(embed=embed, view=view)
                    except discord.NotFound:
                        logger.error(f"Could not find message {self.aar.message_id} in channel {AAR_CHANNEL_ID}")
                    except Exception as e:
                        logger.error(f"Error updating AAR message: {e}")
            else:
                await interaction.response.send_message("No valid participants selected.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error awarding medals: {e}")
            await interaction.response.send_message("❌ An error occurred while awarding medals.", ephemeral=True)

class ParticipantSelectMenu(discord.ui.Select):
    """Select menu for choosing participants to award medals to."""
    
    def __init__(self, parent_view, aar):
        self.parent_view = parent_view
        
        # Create options from participants
        options = []
        guild = parent_view.cog.bot.get_guild(GUILD_ID)
        
        for user_id, participant in aar.participants.items():
            member = guild.get_member(user_id)
            display_name = member.display_name if member else f"Unknown User ({user_id})"
            options.append(discord.SelectOption(
                label=display_name,
                value=str(user_id),
                description=f"{participant.role} on {participant.ship}"
            ))
        
        if not options:
            options = [discord.SelectOption(label="No participants", value="none", disabled=True)]
            
        super().__init__(
            placeholder="Select participants...",
            min_values=1,
            max_values=min(len(options), 25) if options[0].value != "none" else 1,  # Maximum 25 or all participants
            options=options
        )
        
    async def callback(self, interaction: discord.Interaction):
        """Handle participant selection."""
        if self.values[0] == "none":
            await interaction.response.send_message("No participants available to select.", ephemeral=True)
            return
            
        self.parent_view.selected_user_ids = self.values
        self.parent_view.update_button_state()
        await interaction.response.defer()

class MedalSelectMenu(discord.ui.Select):
    """Select menu for choosing medals to award."""
    
    def __init__(self, parent_view):
        self.parent_view = parent_view
        
        # Create options from AARMedal enum
        options = []
        for medal in AARMedal:
            options.append(discord.SelectOption(
                label=medal.value,
                value=medal.name
            ))
        
        super().__init__(
            placeholder="Select medals to award...",
            min_values=1,
            max_values=min(len(options), 25),  # Maximum 25 or all medals
            options=options
        )
        
    async def callback(self, interaction: discord.Interaction):
        """Handle medal selection."""
        self.parent_view.selected_medals = self.values
        self.parent_view.update_button_state()
        await interaction.response.defer()

class ParticipantSelect(discord.ui.Select):
    """Select menu for choosing a participant to edit notes for."""
    
    def __init__(self, cog, aar, options):
        super().__init__(
            placeholder="Select a participant...",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.cog = cog
        self.aar = aar
        
    async def callback(self, interaction: discord.Interaction):
        """Handle participant selection."""
        try:
            user_id = int(self.values[0])
            participant = self.aar.participants.get(user_id)
            
            if not participant:
                await interaction.response.send_message("Participant not found.", ephemeral=True)
                return
                
            # Show modal to edit notes
            modal = ParticipantNotesModal(self.cog, self.aar, user_id)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error in participant select callback: {e}")
            await interaction.response.send_message("An error occurred while processing your selection.", ephemeral=True)

class AARDetailsModal(discord.ui.Modal, title="Edit AAR Details"):
    """Modal for editing basic AAR details."""
    
    def __init__(self, cog, aar):
        super().__init__()
        self.cog = cog
        self.aar = aar
        
        # Lessons learned field
        self.lessons_learned = discord.ui.TextInput(
            label="Lessons Learned",
            style=discord.TextStyle.paragraph,
            placeholder="What did the team learn from this mission?",
            required=False,
            default=aar.lessons_learned or "",
            max_length=1000
        )
        self.add_item(self.lessons_learned)
        
        # Followup actions field
        self.followup_actions = discord.ui.TextInput(
            label="Follow-up Actions",
            style=discord.TextStyle.paragraph,
            placeholder="What needs to be done following this mission?",
            required=False,
            default=aar.followup_actions or "",
            max_length=1000
        )
        self.add_item(self.followup_actions)
        
        # Debrief notes field
        self.debrief_notes = discord.ui.TextInput(
            label="Debrief Notes",
            style=discord.TextStyle.paragraph,
            placeholder="Additional debrief notes",
            required=False,
            default=aar.debrief_notes or "",
            max_length=1000
        )
        self.add_item(self.debrief_notes)
        
        # Mission achievements field
        achievements_text = "\n".join(aar.mission_achievements) if aar.mission_achievements else ""
        self.mission_achievements = discord.ui.TextInput(
            label="Mission Achievements (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="List mission achievements, one per line",
            required=False,
            default=achievements_text,
            max_length=1000
        )
        self.add_item(self.mission_achievements)
        
        # Technical issues field
        issues_text = "\n".join(aar.technical_issues) if aar.technical_issues else ""
        self.technical_issues = discord.ui.TextInput(
            label="Technical Issues (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="List any technical issues encountered, one per line",
            required=False,
            default=issues_text,
            max_length=1000
        )
        self.add_item(self.technical_issues)
        
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted form."""
        try:
            # Update the AAR details
            self.aar.lessons_learned = self.lessons_learned.value
            self.aar.followup_actions = self.followup_actions.value
            self.aar.debrief_notes = self.debrief_notes.value
            self.aar.mission_achievements = [a.strip() for a in self.mission_achievements.value.split('\n') if a.strip()]
            self.aar.technical_issues = [i.strip() for i in self.technical_issues.value.split('\n') if i.strip()]
            
            # Save the AAR
            await self.cog.save_aar(self.aar)
            
            await interaction.response.send_message("✅ AAR details updated successfully.", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error updating AAR details: {e}")
            await interaction.response.send_message("❌ An error occurred while updating AAR details.", ephemeral=True)

class CombatStatsModal(discord.ui.Modal, title="Add Combat Statistics"):
    """Modal for adding combat statistics to an AAR."""
    
    def __init__(self, cog, aar):
        super().__init__()
        self.cog = cog
        self.aar = aar
        
        # Initialize existing stats or create empty dict
        combat_stats = aar.combat_stats or {}
        
        # Enemy kills field
        self.enemy_kills = discord.ui.TextInput(
            label="Enemy Kills",
            placeholder="Number of enemy ships/NPCs defeated",
            required=False,
            default=str(combat_stats.get('Enemy Kills', '')),
            max_length=100
        )
        self.add_item(self.enemy_kills)
        
        # Friendly losses field
        self.friendly_losses = discord.ui.TextInput(
            label="Friendly Losses",
            placeholder="Number of friendly ships lost",
            required=False,
            default=str(combat_stats.get('Friendly Losses', '')),
            max_length=100
        )
        self.add_item(self.friendly_losses)
        
        # Damage dealt field
        self.damage_dealt = discord.ui.TextInput(
            label="Damage Dealt",
            placeholder="Total damage dealt to enemies",
            required=False,
            default=str(combat_stats.get('Damage Dealt', '')),
            max_length=100
        )
        self.add_item(self.damage_dealt)
        
        # Ammunition used field
        self.ammunition_used = discord.ui.TextInput(
            label="Ammunition Used",
            placeholder="Ammunition expended during combat",
            required=False,
            default=str(combat_stats.get('Ammunition Used', '')),
            max_length=100
        )
        self.add_item(self.ammunition_used)
        
        # Other combat stats field
        other_stats = ""
        for key, value in combat_stats.items():
            if key not in ['Enemy Kills', 'Friendly Losses', 'Damage Dealt', 'Ammunition Used']:
                other_stats += f"{key}: {value}\n"
                
        self.other_stats = discord.ui.TextInput(
            label="Other Combat Stats (Key: Value)",
            style=discord.TextStyle.paragraph,
            placeholder="Other combat statistics in 'Key: Value' format, one per line",
            required=False,
            default=other_stats,
            max_length=1000
        )
        self.add_item(self.other_stats)
        
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted form."""
        try:
            # Create a new combat stats dictionary
            combat_stats = {}
            
            # Add the main stats if provided
            if self.enemy_kills.value:
                combat_stats['Enemy Kills'] = self.enemy_kills.value
            if self.friendly_losses.value:
                combat_stats['Friendly Losses'] = self.friendly_losses.value
            if self.damage_dealt.value:
                combat_stats['Damage Dealt'] = self.damage_dealt.value
            if self.ammunition_used.value:
                combat_stats['Ammunition Used'] = self.ammunition_used.value
                
            # Parse other stats
            if self.other_stats.value:
                for line in self.other_stats.value.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        combat_stats[key.strip()] = value.strip()
            
            # Update the AAR
            self.aar.combat_stats = combat_stats
            
            # Save the AAR
            await self.cog.save_aar(self.aar)
            
            await interaction.response.send_message("✅ Combat statistics updated successfully.", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error updating combat stats: {e}")
            await interaction.response.send_message("❌ An error occurred while updating combat statistics.", ephemeral=True)

class MediaLinksModal(discord.ui.Modal, title="Add Media Links"):
    """Modal for adding media links to an AAR."""
    
    def __init__(self, cog, aar):
        super().__init__()
        self.cog = cog
        self.aar = aar
        
        # Video URL field
        self.video_url = discord.ui.TextInput(
            label="Mission Video URL",
            placeholder="Link to mission recording/video",
            required=False,
            default=aar.mission_video_url or "",
            max_length=500
        )
        self.add_item(self.video_url)
        
        # Screenshot URLs field
        screenshots_text = "\n".join(aar.screenshots) if aar.screenshots else ""
        self.screenshots = discord.ui.TextInput(
            label="Screenshot URLs (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="Links to screenshots, one per line",
            required=False,
            default=screenshots_text,
            max_length=1000
        )
        self.add_item(self.screenshots)
        
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted form."""
        try:
            # Update the AAR
            self.aar.mission_video_url = self.video_url.value if self.video_url.value else None
            self.aar.screenshots = [url.strip() for url in self.screenshots.value.split('\n') if url.strip()]
            
            # Save the AAR
            await self.cog.save_aar(self.aar)
            
            await interaction.response.send_message("✅ Media links updated successfully.", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error updating media links: {e}")
            await interaction.response.send_message("❌ An error occurred while updating media links.", ephemeral=True)

class ParticipantNotesModal(discord.ui.Modal):
    """Modal for editing participant notes."""
    
    def __init__(self, cog, aar, user_id):
        # Get member name for title
        member = cog.bot.get_guild(GUILD_ID).get_member(user_id) 
        title = f"Edit Notes for {member.display_name if member else 'Participant'}"
        super().__init__(title=title)
        
        self.cog = cog
        self.aar = aar
        self.user_id = user_id
        participant = aar.participants.get(user_id)
        
        # Performance notes field
        self.performance_notes = discord.ui.TextInput(
            label="Performance Notes",
            style=discord.TextStyle.paragraph,
            placeholder="Enter performance notes for this participant",
            required=False,
            default=participant.performance_notes or "",
            max_length=1000
        )
        self.add_item(self.performance_notes)
        
        # Key actions field
        key_actions_text = "\n".join(participant.key_actions) if participant.key_actions else ""
        self.key_actions = discord.ui.TextInput(
            label="Key Actions (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="Enter key actions performed by this participant, one per line",
            required=False,
            default=key_actions_text,
            max_length=1000
        )
        self.add_item(self.key_actions)
        
        # Contribution field
        self.contribution = discord.ui.TextInput(
            label="Contribution",
            placeholder="Describe this participant's contribution to the mission",
            required=False,
            default=participant.contribution or "",
            max_length=500
        )
        self.add_item(self.contribution)
        
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted form."""
        try:
            participant = self.aar.participants.get(self.user_id)
            if not participant:
                await interaction.response.send_message("Participant not found.", ephemeral=True)
                return
                
            # Update the participant information
            participant.performance_notes = self.performance_notes.value
            participant.key_actions = [action.strip() for action in self.key_actions.value.split('\n') if action.strip()]
            participant.contribution = self.contribution.value
            
            # Save the AAR
            await self.cog.save_aar(self.aar)
            
            # Update the AAR view
            if self.aar.message_id:
                channel = self.cog.bot.get_channel(AAR_CHANNEL_ID)
                if channel:
                    try:
                        message = await channel.fetch_message(self.aar.message_id)
                        embed = self.aar.to_embed(self.cog.bot)
                        
                        if not self.aar.finalized:
                            # Include view only if not finalized
                            await message.edit(embed=embed, view=AARFeedbackView(self.cog, self.aar))
                        else:
                            # Don't include view if finalized
                            await message.edit(embed=embed)
                            
                    except discord.NotFound:
                        logger.error(f"Message {self.aar.message_id} not found in channel {AAR_CHANNEL_ID}")
                    except Exception as e:
                        logger.error(f"Error updating AAR message: {e}")
            
            await interaction.response.send_message("✅ Participant notes updated successfully.", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error updating participant notes: {e}")
            await interaction.response.send_message("❌ An error occurred while updating participant notes.", ephemeral=True)
            
class MissionCompleteView(discord.ui.View):
    """View displayed when a mission is completed, to create an AAR."""
    
    def __init__(self, cog, mission):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.mission = mission
        
    @discord.ui.button(
        label="Create After Action Report",
        style=discord.ButtonStyle.primary,
        custom_id="create_aar_button"
    )
    async def create_aar_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle creating an AAR from the completed mission."""
        try:
            # Check if user has permission (mission leader or admin)
            if interaction.user.id != self.mission.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Only the mission leader or administrators can create an AAR.", ephemeral=True)
                return
                
            # Start with a deferred response since AAR creation might take time
            await interaction.response.defer(ephemeral=True)
            
            # Create AAR from mission
            aar_id = await self.cog.create_aar_from_mission(self.mission)
            
            if aar_id:
                await interaction.followup.send(
                    f"✅ After Action Report created successfully! AAR ID: {aar_id}",
                    ephemeral=True
                )
                
                # Disable the button after creation
                self.create_aar_button.disabled = True
                self.create_aar_button.label = "AAR Created"
                self.create_aar_button.style = discord.ButtonStyle.success
                
                # Try to update original message
                try:
                    await interaction.message.edit(view=self)
                except:
                    pass
            else:
                await interaction.followup.send(
                    "❌ Failed to create After Action Report. Please try again or use the /aar create command.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error creating AAR from mission complete view: {e}")
            await interaction.followup.send(
                "❌ An error occurred while creating the After Action Report.",
                ephemeral=True
            )

# Helper for mission ID autocomplete
async def mission_id_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Provide autocomplete choices for mission IDs."""
    choices = []
    mission_cog = interaction.client.get_cog('MissionCog')
    
    if mission_cog:
        # Search through missions by ID and name
        for mission_id, mission in mission_cog.missions.items():
            # Match by mission ID (first 8 chars) or mission name
            if (current.lower() in mission_id[:8].lower() or 
                current.lower() in mission.name.lower()):
                # Format the choice to show name and short ID
                display_name = f"{mission.name} (ID: {mission_id[:8]})"
                choices.append(app_commands.Choice(name=display_name, value=mission_id))
                
                # Return up to 25 choices (Discord limit)
                if len(choices) >= 25:
                    break
                    
    return choices

# Helper for AAR ID autocomplete
async def aar_id_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provides autocomplete options for AAR IDs."""
    try:
        # Debug logging
        print(f"AAR autocomplete called with search term: '{current}'")
        
        # Get the cog by its registered name ("aar") instead of class name ("AARCommands")
        aar_cog = interaction.client.get_cog('aar')
        if not aar_cog:
            print("AAR cog not found by name 'aar', trying alternative names...")
            # Try fallback names in case cog registration changed
            for cog_name in interaction.client.cogs:
                if 'aar' in cog_name.lower():
                    print(f"Found AAR cog with name: {cog_name}")
                    aar_cog = interaction.client.get_cog(cog_name)
                    break
        
        if not aar_cog:
            print("No AAR cog found - cannot provide autocomplete options")
            return []
            
        # Get reports directly from the cog
        reports = getattr(aar_cog, 'reports', {})
        print(f"Found {len(reports)} AARs in the system")
        
        # Build choices
        choices = []
        for aar_id, aar in reports.items():
            mission_name = getattr(aar, 'mission_name', 'Unknown Mission')
            
            # Simple string matching on either mission name or AAR ID
            if current.lower() in mission_name.lower() or current.lower() in aar_id.lower():
                status_marker = "✅" if getattr(aar, 'finalized', False) else "📝"
                display_name = f"{status_marker} {mission_name} ({aar_id[:8]})"
                
                choices.append(app_commands.Choice(name=display_name, value=aar_id))
                
                # Limit to 25 choices (Discord limit)
                if len(choices) >= 25:
                    break
                    
        print(f"Returning {len(choices)} autocomplete choices")
        return choices
        
    except Exception as e:
        # Print the error to console
        print(f"AAR AUTOCOMPLETE ERROR: {e}")
        import traceback
        traceback.print_exc()
        
        # Return an error choice so user knows something went wrong
        return [app_commands.Choice(name="ERROR - See console log", value="error")]

class AARCommands(commands.GroupCog, name="aar"):
    """After Action Report command group for mission debriefs and analysis."""
    
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.guild_id = GUILD_ID
        self.session = aiohttp.ClientSession()
        self.reports: Dict[str, AAR] = {}
        self.column_cache: Dict[str, str] = {}
        self.last_column_fetch: Optional[datetime] = None
        self.load_reports()
        self.aar_channel_id = AAR_CHANNEL_ID
        self.staff_notification_channel_id = STAFF_NOTIFICATION_CHANNEL_ID
        logger.info("Initialized AARCommands cog")

    @property
    def profile_cog(self):
        return self.bot.get_cog('ProfileCog')
        
    def load_reports(self):
        """Load AARs from file with backward compatibility."""
        try:
            if os.path.exists('aar_data.json'):
                with open('aar_data.json', 'r') as f:
                    data = json.load(f)
                    self.reports = {}
                    for aar_id, aar_data in data.items():
                        try:
                            # Create AAR object
                            aar = AAR.from_dict(aar_data)
                            self.reports[aar_id] = aar
                        except Exception as conversion_error:
                            logger.error(f"Error converting AAR {aar_id}: {conversion_error}")

                    logger.info(f"Loaded {len(self.reports)} AARs from file")
            else:
                logger.info("No AAR data file found, initializing empty reports dictionary")
                self.reports = {}
        except Exception as e:
            logger.error(f"Error loading AARs: {e}")
            self.reports = {}

    def save_reports(self):
        """Save AARs to file."""
        try:
            # Only save if there are actually reports
            if self.reports:
                data = {aar_id: aar.to_dict() for aar_id, aar in self.reports.items()}
                with open('aar_data.json', 'w') as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Saved {len(self.reports)} AARs to file")
            else:
                logger.warning("No AARs to save - skipping file write")
        except Exception as e:
            logger.error(f"Error saving AARs: {e}")

    async def save_aar(self, aar: AAR):
        """Save a single AAR and update storage."""
        try:
            self.reports[aar.aar_id] = aar
            self.save_reports()
            # Also update the message if it exists
            if self.aar_channel_id and aar.message_id:
                channel = self.bot.get_channel(self.aar_channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(aar.message_id)
                        if not aar.finalized:
                            # If not finalized, include the view
                            await message.edit(
                                embed=aar.to_embed(self.bot),
                                view=AARFeedbackView(self, aar)
                            )
                        else:
                            # If finalized, don't include the view parameter
                            await message.edit(
                                embed=aar.to_embed(self.bot)
                            )
                    except discord.NotFound:
                        logger.error(f"Failed to find AAR message {aar.message_id} in channel {self.aar_channel_id}")
                    except Exception as e:
                        logger.error(f"Failed to update AAR message: {e}")
        except Exception as e:
            logger.error(f"Error saving AAR: {e}")

    async def create_aar_from_mission(self, mission: Any) -> Optional[str]:
        """Create an AAR from a completed mission with enhanced data transfer."""
        try:
            # Import necessary types for type conversion
            from .mission_system.shared import MissionType, MissionStatus, Participant

            # Convert mission type to AAR type with proper error handling
            try:
                aar_type = AARType[mission.mission_type.name]
            except (KeyError, AttributeError):
                # Fallback mapping for mission types
                type_mapping = {
                    'COMBAT': AARType.COMBAT,
                    'MINING': AARType.MINING,
                    'TRADING': AARType.TRADING,
                    'EXPLORATION': AARType.EXPLORATION,
                    'MEDICAL': AARType.MEDICAL,
                    'TRAINING': AARType.TRAINING,
                    'SALVAGE': AARType.OTHER,
                    'LOGISTICS': AARType.OTHER,
                    'SPECIAL': AARType.OTHER
                }
                mission_type_str = str(getattr(mission, 'mission_type', '')).upper()
                aar_type = type_mapping.get(mission_type_str, AARType.OTHER)

            # Determine outcome based on mission status
            outcome = AAROutcome.SUCCESS
            if hasattr(mission, 'status'):
                status_mapping = {
                    'CANCELLED': AAROutcome.CANCELLED,
                    'INCOMPLETE': AAROutcome.INCOMPLETE,
                    'FAILED': AAROutcome.FAILURE,
                    'PARTIAL': AAROutcome.PARTIAL
                }
                
                status_str = str(getattr(mission, 'status', '')).upper()
                outcome = status_mapping.get(status_str, AAROutcome.SUCCESS)

            # Process participants with error handling
            participants = {}
            for user_id, p_data in getattr(mission, 'participants', {}).items():
                try:
                    if isinstance(p_data, tuple):
                        ship_name, role = p_data
                    elif hasattr(p_data, 'ship_name') and hasattr(p_data, 'role'):
                        ship_name = p_data.ship_name
                        role = p_data.role
                    else:
                        ship_name = 'Unknown Ship'
                        role = 'Unknown Role'

                    participant = AARParticipant(
                        user_id=int(user_id),
                        ship=ship_name,
                        role=role,
                        joined_at=getattr(mission, 'creation_time', datetime.now(timezone.utc))
                    )
                    
                    participants[int(user_id)] = participant
                except Exception as e:
                    logger.error(f"Error processing participant {user_id}: {e}")
                    continue

            # Get objectives with fallback
            objectives = []
            completed_objectives = []
            
            if hasattr(mission, 'objectives'):
                objectives = mission.objectives.copy()
                if hasattr(mission, 'completed_objectives'):
                    completed_objectives = mission.completed_objectives.copy()

            # Calculate earnings if available
            member_earnings = getattr(mission, 'member_earnings', 0) or getattr(mission, 'anticipated_earnings', 0)
            org_earnings = getattr(mission, 'org_earnings', 0)

            # Process fleet assignments if available
            fleet_assignments = None
            if hasattr(mission, 'fleet_assignment'):
                fleet_assignments = {
                    'ships': list(getattr(mission.fleet_assignment, 'assigned_ships', [])),
                    'flight_groups': list(getattr(mission.fleet_assignment, 'assigned_flight_groups', [])),
                    'squadrons': list(getattr(mission.fleet_assignment, 'assigned_squadrons', []))
                }

            # Create AAR
            aar = AAR(
                mission_name=mission.name,
                aar_type=aar_type,
                outcome=outcome,
                description=getattr(mission, 'description', 'No description provided'),
                leader_id=mission.leader_id,
                member_earnings=member_earnings,
                org_earnings=org_earnings,
                objectives=objectives,
                completed_objectives=completed_objectives,
                participants=participants,
                creation_time=datetime.now(timezone.utc),
                mission_id=mission.mission_id,  # Store the original mission ID
                fleet_assignments=fleet_assignments  # Include fleet assignments
            )

            # Save the AAR
            self.reports[aar.aar_id] = aar
            self.save_reports()

            # Send to AAR channel if configured
            if self.aar_channel_id:
                try:
                    channel = self.bot.get_channel(self.aar_channel_id)
                    if channel:
                        view = AARFeedbackView(self, aar)
                        message = await channel.send(embed=aar.to_embed(self.bot), view=view)
                        aar.message_id = message.id  # Store the message ID
                        self.save_reports()
                except Exception as e:
                    logger.error(f"Failed to send AAR notification: {e}")

            logger.info(f"Created AAR {aar.aar_id} from mission: {mission.name}")
            return aar.aar_id

        except Exception as e:
            logger.error(f"Error creating AAR from mission: {e}", exc_info=True)
            return None

    async def on_mission_completed(self, mission):
        """Event handler for when a mission is completed."""
        try:
            # Create a completion notification with an AAR creation button
            channel = self.bot.get_channel(mission.channel_id)
            if not channel:
                logger.error(f"Channel not found for mission {mission.mission_id}")
                return
                
            embed = discord.Embed(
                title="Mission Completed",
                description=f"The mission '{mission.name}' has been marked as completed.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Next Steps",
                value="The mission leader can now create an After Action Report to record details about the mission.",
                inline=False
            )
            
            view = MissionCompleteView(self, mission)
            await channel.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error handling mission completion: {e}")

    async def add_medals_to_profile(self, user_id: int, medals: List[AARMedal], citation: str = None) -> bool:
        """Add medals to a user's profile."""
        try:
            profile_cog = self.profile_cog
            if not profile_cog:
                logger.error("Profile cog not available")
                return False
                    
            member = self.bot.get_guild(GUILD_ID).get_member(user_id)
            if not member:
                logger.error(f"Member not found for user ID {user_id}")
                return False
            
            success_count = 0    
            for medal in medals:
                # Format medal name and citation
                medal_name = medal.value
                medal_citation = citation or f"Awarded for participation in a mission"
                
                try:
                    # Add the award using the profile cog's internal method
                    success, result = await profile_cog.add_award_to_member(
                        member=member,
                        award=medal_name,
                        citation=medal_citation,
                        awarded_by=self.bot.user.id,  # System-awarded
                        notify_member=True  # Send DM to member
                    )
                    
                    if success:
                        logger.info(f"Added medal {medal_name} to {member.display_name}'s profile")
                        success_count += 1
                    else:
                        logger.warning(f"Failed to add medal {medal_name} to profile for user {user_id}: {result}")
                except Exception as e:
                    logger.error(f"Error adding medal {medal_name} to profile for user {user_id}: {e}")
                        
            return success_count > 0
                
        except Exception as e:
            logger.error(f"Error adding medals to profile: {e}")
            return False

    # Command implementation
    @app_commands.command(name="create", description="Create a new After Action Report")
    @app_commands.describe(
        mission_id="ID of the completed mission to create AAR from",
        custom_name="Optional custom name for the AAR (defaults to mission name)",
        outcome="Outcome of the mission"
    )
    @app_commands.autocomplete(mission_id=mission_id_autocomplete)
    @app_commands.choices(outcome=[
        app_commands.Choice(name="Success", value="SUCCESS"),
        app_commands.Choice(name="Partial Success", value="PARTIAL"),
        app_commands.Choice(name="Failure", value="FAILURE"),
        app_commands.Choice(name="Cancelled", value="CANCELLED"),
        app_commands.Choice(name="Incomplete", value="INCOMPLETE")
    ])
    async def create_aar(
        self, 
        interaction: discord.Interaction, 
        mission_id: str,
        outcome: str,
        custom_name: Optional[str] = None
    ):
        """Create a new After Action Report from a completed mission."""
        await interaction.response.defer()
        
        try:
            # Get the mission cog
            mission_cog = self.bot.get_cog('MissionCog')
            if not mission_cog:
                await interaction.followup.send("❌ Mission system not available.", ephemeral=True)
                return
                
            # Get the mission
            mission = mission_cog.missions.get(mission_id)
            if not mission:
                await interaction.followup.send("❌ Mission not found with that ID.", ephemeral=True)
                return
                
            # Check if user is the mission leader or admin
            if interaction.user.id != mission.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Only the mission leader or administrators can create an AAR.", ephemeral=True)
                return
            
            # Set the mission outcome - Map AAR outcomes to mission statuses
            from .mission_system.shared import MissionStatus
            
            # Get available statuses in MissionStatus enum
            available_statuses = [status.name for status in MissionStatus]
            logger.info(f"Available mission statuses: {available_statuses}")
            
            # Handle status mapping with safety checks
            try:
                # Only map to statuses we know exist
                if "COMPLETED" in available_statuses:
                    if outcome in ["SUCCESS", "PARTIAL", "FAILURE"]:
                        mission.status = MissionStatus.COMPLETED
                        
                if "CANCELLED" in available_statuses and outcome == "CANCELLED":
                    mission.status = MissionStatus.CANCELLED
                    
                # For INCOMPLETE, check different possible statuses
                if outcome == "INCOMPLETE":
                    if "INCOMPLETE" in available_statuses:
                        mission.status = MissionStatus.INCOMPLETE
                    else:
                        # Fallbacks if INCOMPLETE doesn't exist
                        if "IN_PROGRESS" in available_statuses:
                            mission.status = MissionStatus.IN_PROGRESS
                        else:
                            mission.status = MissionStatus.COMPLETED
            except Exception as status_error:
                logger.error(f"Error setting mission status: {status_error}")
                # Use a safe default
                if "COMPLETED" in available_statuses:
                    mission.status = MissionStatus.COMPLETED
            
            # Create AAR from mission
            aar_id = await self.create_aar_from_mission(mission)
            
            if not aar_id:
                await interaction.followup.send("❌ Failed to create AAR. Please try again.", ephemeral=True)
                return
                
            # Apply custom name if provided
            if custom_name:
                aar = self.reports[aar_id]
                aar.mission_name = custom_name
                await self.save_aar(aar)
                
            # Show success message with link to AAR
            embed = discord.Embed(
                title="AAR Created Successfully",
                description=f"After Action Report for mission '{mission.name}' has been created.",
                color=discord.Color.green()
            )
            
            # Add a button to view the AAR
            view = discord.ui.View()
            aar = self.reports[aar_id]
            if aar.message_id:
                button = discord.ui.Button(
                    label="View AAR",
                    style=discord.ButtonStyle.url,
                    url=f"https://discord.com/channels/{GUILD_ID}/{AAR_CHANNEL_ID}/{aar.message_id}"
                )
                view.add_item(button)
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error creating AAR: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while creating the AAR.", ephemeral=True)

    @app_commands.command(name="view", description="View an After Action Report")
    @app_commands.describe(aar_id="ID or name of the AAR to view")
    @app_commands.autocomplete(aar_id=aar_id_autocomplete)
    async def view_aar(self, interaction: discord.Interaction, aar_id: str):
        """View an existing After Action Report."""
        await interaction.response.defer()
        
        try:
            # Get the AAR
            aar = self.reports.get(aar_id)
            if not aar:
                await interaction.followup.send("❌ AAR not found with that ID.", ephemeral=True)
                return
                
            # Create the embed
            embed = aar.to_embed(self.bot)
            
            # Create the view only for non-finalized AARs
            if not aar.finalized:
                view = AARFeedbackView(self, aar)
                await interaction.followup.send(embed=embed, view=view)
            else:
                # For finalized AARs, don't include the view parameter
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error viewing AAR: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while viewing the AAR.", ephemeral=True)

    @app_commands.command(name="list", description="List After Action Reports")
    @app_commands.describe(
        show_all="Show all AARs including finalized ones",
        mission_name="Filter by mission name",
        leader="Filter by mission leader"
    )
    async def list_aars(
        self, 
        interaction: discord.Interaction,
        show_all: Optional[bool] = False,
        mission_name: Optional[str] = None,
        leader: Optional[discord.Member] = None
    ):
        """List After Action Reports with optional filtering."""
        await interaction.response.defer()
        
        try:
            # Filter reports
            filtered_reports = []
            for aar in self.reports.values():
                # Skip finalized AARs unless show_all is True
                if aar.finalized and not show_all:
                    continue
                    
                # Filter by mission name if provided
                if mission_name and mission_name.lower() not in aar.mission_name.lower():
                    continue
                    
                # Filter by leader if provided
                if leader and aar.leader_id != leader.id:
                    continue
                    
                filtered_reports.append(aar)
                
            if not filtered_reports:
                await interaction.followup.send("No AARs found matching the criteria.", ephemeral=True)
                return
                
            # Sort reports by creation time, newest first
            filtered_reports.sort(key=lambda a: a.creation_time, reverse=True)
            
            # Create embed for listing
            embed = discord.Embed(
                title="After Action Reports",
                description=f"Found {len(filtered_reports)} report(s)",
                color=discord.Color.blue()
            )
            
            # Add up to 10 reports to the embed
            for i, aar in enumerate(filtered_reports[:10]):
                leader = interaction.guild.get_member(aar.leader_id)
                leader_name = leader.display_name if leader else "Unknown"
                
                status = "✅ Finalized" if aar.finalized else "📝 In Progress"
                created = discord.utils.format_dt(aar.creation_time, style='R')
                
                embed.add_field(
                    name=f"{i+1}. {aar.mission_name}",
                    value=(
                        f"**ID:** {aar.aar_id[:8]}\n"
                        f"**Type:** {aar.aar_type.value}\n"
                        f"**Leader:** {leader_name}\n"
                        f"**Created:** {created}\n"
                        f"**Status:** {status}"
                    ),
                    inline=(i % 2 == 0)  # Alternate inline
                )
                
            if len(filtered_reports) > 10:
                embed.set_footer(text=f"Showing 10 of {len(filtered_reports)} reports. Use filters to narrow results.")
                
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error listing AARs: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while listing AARs.", ephemeral=True)

    @app_commands.command(name="delete", description="Delete an After Action Report")
    @app_commands.describe(aar_id="ID of the AAR to delete")
    @app_commands.autocomplete(aar_id=aar_id_autocomplete)
    @app_commands.default_permissions(administrator=True)
    async def delete_aar(self, interaction: discord.Interaction, aar_id: str):
        """Delete an After Action Report (admin only)."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check permissions
            if not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Only administrators can delete AARs.", ephemeral=True)
                return
                
            # Get the AAR
            aar = self.reports.get(aar_id)
            if not aar:
                await interaction.followup.send("❌ AAR not found with that ID.", ephemeral=True)
                return
                
            # Create confirmation view
            view = discord.ui.View(timeout=60)
            
            async def confirm_callback(confirm_interaction: discord.Interaction):
                if confirm_interaction.user.id != interaction.user.id:
                    await confirm_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                    return
                    
                # Delete the AAR message if it exists
                if aar.message_id:
                    channel = self.bot.get_channel(AAR_CHANNEL_ID)
                    if channel:
                        try:
                            message = await channel.fetch_message(aar.message_id)
                            await message.delete()
                        except discord.NotFound:
                            pass
                        except Exception as e:
                            logger.error(f"Error deleting AAR message: {e}")
                
                # Remove from reports dictionary
                if aar_id in self.reports:
                    del self.reports[aar_id]
                    self.save_reports()
                    
                await confirm_interaction.response.edit_message(
                    content=f"✅ AAR for mission '{aar.mission_name}' has been deleted.",
                    view=None
                )
                
            async def cancel_callback(cancel_interaction: discord.Interaction):
                if cancel_interaction.user.id != interaction.user.id:
                    await cancel_interaction.response.send_message("This cancellation is not for you.", ephemeral=True)
                    return
                    
                await cancel_interaction.response.edit_message(
                    content="❌ AAR deletion cancelled.",
                    view=None
                )
                
            # Add buttons to the view
            confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
            confirm_button.callback = confirm_callback
            
            cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
            cancel_button.callback = cancel_callback
            
            view.add_item(confirm_button)
            view.add_item(cancel_button)
            
            # Send confirmation message
            await interaction.followup.send(
                f"⚠️ Are you sure you want to delete the AAR for mission '{aar.mission_name}'? This action cannot be undone.",
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error deleting AAR: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while deleting the AAR.", ephemeral=True)

    @app_commands.command(name="update_objectives", description="Update completed objectives in an AAR")
    @app_commands.describe(
        aar_id="ID of the AAR to update",
        objective_numbers="Comma-separated list of objective numbers to mark as completed (e.g., '1,3,4')"
    )
    @app_commands.autocomplete(aar_id=aar_id_autocomplete)
    async def update_objectives(
        self, 
        interaction: discord.Interaction, 
        aar_id: str,
        objective_numbers: str
    ):
        """Update which objectives were completed in an AAR."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the AAR
            aar = self.reports.get(aar_id)
            if not aar:
                await interaction.followup.send("❌ AAR not found with that ID.", ephemeral=True)
                return
                
            # Check if user is the AAR leader or admin
            if interaction.user.id != aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Only the mission leader or administrators can update objectives.", ephemeral=True)
                return
                
            # Check if AAR is already finalized
            if aar.finalized:
                await interaction.followup.send("❌ This AAR is already finalized and cannot be modified.", ephemeral=True)
                return
                
            # Parse objective numbers
            try:
                # Parse numbers and adjust to 0-indexed
                objective_indices = [int(num.strip()) - 1 for num in objective_numbers.split(',') if num.strip()]
                
                # Validate indices are in range
                valid_indices = [idx for idx in objective_indices if 0 <= idx < len(aar.objectives)]
                
                if not valid_indices:
                    await interaction.followup.send(
                        f"❌ No valid objective numbers provided. Please use numbers between 1 and {len(aar.objectives)}.", 
                        ephemeral=True
                    )
                    return
                    
                # Update completed objectives
                aar.completed_objectives = [aar.objectives[idx] for idx in valid_indices]
                await self.save_aar(aar)
                
                # Show success message
                completion_rate = len(aar.completed_objectives) / len(aar.objectives) * 100 if aar.objectives else 0
                await interaction.followup.send(
                    f"✅ Objectives updated successfully. {len(aar.completed_objectives)}/{len(aar.objectives)} completed ({completion_rate:.1f}%).",
                    ephemeral=True
                )
                
            except ValueError:
                await interaction.followup.send("❌ Invalid input. Please provide a comma-separated list of numbers.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error updating objectives: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while updating objectives.", ephemeral=True)

    @app_commands.command(name="add_participant", description="Add a participant to an AAR")
    @app_commands.describe(
        aar_id="ID of the AAR",
        member="Member to add as a participant",
        ship="Ship used by the participant",
        role="Role of the participant"
    )
    @app_commands.autocomplete(aar_id=aar_id_autocomplete)
    async def add_participant(
        self, 
        interaction: discord.Interaction, 
        aar_id: str,
        member: discord.Member,
        ship: str,
        role: str
    ):
        """Add a participant to an existing AAR."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the AAR
            aar = self.reports.get(aar_id)
            if not aar:
                await interaction.followup.send("❌ AAR not found with that ID.", ephemeral=True)
                return
                
            # Check if user is the AAR leader or admin
            if interaction.user.id != aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Only the mission leader or administrators can add participants.", ephemeral=True)
                return
                
            # Check if AAR is already finalized
            if aar.finalized:
                await interaction.followup.send("❌ This AAR is already finalized and cannot be modified.", ephemeral=True)
                return
                
            # Check if member is already a participant
            if member.id in aar.participants:
                await interaction.followup.send(f"❌ {member.display_name} is already a participant in this AAR.", ephemeral=True)
                return
                
            # Add the participant
            participant = AARParticipant(
                user_id=member.id,
                ship=ship,
                role=role,
                joined_at=datetime.now(timezone.utc)
            )
            
            aar.participants[member.id] = participant
            await self.save_aar(aar)
            
            await interaction.followup.send(
                f"✅ Added {member.display_name} as a participant in role '{role}' with ship '{ship}'.",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error adding participant: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while adding the participant.", ephemeral=True)

    @app_commands.command(name="remove_participant", description="Remove a participant from an AAR")
    @app_commands.describe(
        aar_id="ID of the AAR",
        member="Member to remove from the AAR"
    )
    @app_commands.autocomplete(aar_id=aar_id_autocomplete)
    async def remove_participant(
        self, 
        interaction: discord.Interaction, 
        aar_id: str,
        member: discord.Member
    ):
        """Remove a participant from an existing AAR."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the AAR
            aar = self.reports.get(aar_id)
            if not aar:
                await interaction.followup.send("❌ AAR not found with that ID.", ephemeral=True)
                return
                
            # Check if user is the AAR leader or admin
            if interaction.user.id != aar.leader_id and not interaction.user.guild_permissions.administrator:
                await interaction.followup.send("❌ Only the mission leader or administrators can remove participants.", ephemeral=True)
                return
                
            # Check if AAR is already finalized
            if aar.finalized:
                await interaction.followup.send("❌ This AAR is already finalized and cannot be modified.", ephemeral=True)
                return
                
            # Check if member is a participant
            if member.id not in aar.participants:
                await interaction.followup.send(f"❌ {member.display_name} is not a participant in this AAR.", ephemeral=True)
                return
                
            # Remove the participant
            del aar.participants[member.id]
            await self.save_aar(aar)
            
            await interaction.followup.send(
                f"✅ Removed {member.display_name} from the AAR participants.",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Error removing participant: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while removing the participant.", ephemeral=True)

    async def cog_load(self):
        """Register persistent views when the cog loads."""
        # Register persistent views for any active AARs
        for aar in self.reports.values():
            if not aar.finalized:
                self.bot.add_view(AARFeedbackView(self, aar))

    async def cog_unload(self):
        """Save data when the cog is unloaded."""
        self.save_reports()
        await self.session.close()

async def setup(bot: commands.Bot):
    """Setup the AAR cog."""
    await bot.add_cog(AARCommands(bot))
    logger.info("AAR cog loaded successfully")