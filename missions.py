from __future__ import annotations
from typing import Dict, List, Optional, Any, Set, Tuple, Union, TYPE_CHECKING
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import os
import json
import asyncio
import pytz
from datetime import datetime, timezone, timedelta
import uuid
from dateutil.parser import parse as dateutil_parse
from .utils.profile_events import ProfileEvent, ProfileEventType
from enum import Enum

if TYPE_CHECKING:
    from .utils.profile_events import ProfileEvent, ProfileEventType
    from .utils.sc_profile_types import SCProfile, StationRole, SCMissionRole
    from .mission_system.ship_data import Ship  # For ship lookups

# Points to your missions data file.
MISSIONS_DATA_FILE = 'data/missions.json'

# Import shared components
from .mission_system.shared import (
    MissionType, MissionStatus, MissionDifficulty, Participant,
    MissionSystemUtilities as utils
)
from .mission_system.ship_data import Ship  # For ship lookups

logger = logging.getLogger('missions')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='missions.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

GUILD_ID = int(os.getenv('GUILD_ID', 0))
ACTIVE_OPERATIONS_CHANNEL_ID = int(os.getenv('ACTIVE_OPERATIONS_CHANNEL_ID', 0))
VOICE_OPERATIONS_CHANNEL_ID = int(os.getenv('VOICE_OPERATIONS_CHANNEL_ID', 0))


async def mission_status_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    choices = []
    # Loop through all mission statuses from your MissionStatus enum.
    # Ensure MissionStatus is imported from your mission_system.shared module or wherever it is defined.
    for status in MissionStatus:
        if current.lower() in status.name.lower():
            choices.append(app_commands.Choice(name=status.name, value=status.name))
    return choices[:25]


async def mission_id_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for mission IDs - helps users select from existing missions."""
    choices = []
    
    # Get reference to the MissionCog
    mission_cog = interaction.client.get_cog('MissionCog')
    if not mission_cog:
        return choices
    
    # Search through missions by ID and name
    for mission_id, mission in mission_cog.missions.items():
        # Match by mission ID (first 8 chars) or mission name
        if (current.lower() in mission_id[:8].lower() or 
            current.lower() in mission.name.lower()):
            # Format the choice: "mission_name (ID: abcd1234)"
            display_name = f"{mission.name} (ID: {mission_id[:8]})"
            choices.append(app_commands.Choice(name=display_name, value=mission_id))
            
            # Return up to 25 choices (Discord limit)
            if len(choices) >= 25:
                break
                
    return choices


async def ship_name_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for ship names from the Ship class cache."""
    choices = []
    
    # Check if Ship class has a ships cache
    if hasattr(Ship, '_ships_cache') and Ship._ships_cache:
        # Get all ships and sort them by name
        ships = sorted(list(Ship._ships_cache.values()), key=lambda s: s.name)
        
        # Filter by current input if provided
        for ship in ships:
            ship_name = ship.name.split(" (")[0] if " (" in ship.name else ship.name
            if current.lower() in ship_name.lower():
                choices.append(app_commands.Choice(name=ship_name, value=ship_name))
                if len(choices) >= 25:
                    break
    
    return choices


async def role_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for common mission roles."""
    common_roles = [
        "Pilot", "Copilot", "Gunner", "Engineer", "Marine", "Medical", 
        "Security", "Scout", "Support", "Navigator", "Comms Officer",
        "Tactical Officer", "Mission Specialist", "Cargo Specialist"
    ]
    
    choices = []
    for role in common_roles:
        if current.lower() in role.lower():
            choices.append(app_commands.Choice(name=role, value=role))
            if len(choices) >= 25:
                break
                
    return choices


async def tags_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for mission tags, collecting from existing missions."""
    choices = []
    mission_cog = interaction.client.get_cog('MissionCog')
    
    if mission_cog:
        # Collect all unique tags from existing missions
        all_tags = set()
        for mission in mission_cog.missions.values():
            all_tags.update(mission.tags)
        
        # Add common predefined tags
        predefined_tags = {
            "Combat", "Mining", "Salvage", "Trading", "Exploration", 
            "Bounty", "Escort", "Search", "Rescue", "Delivery", 
            "PVP", "PVE", "Training", "Classified", "High Risk"
        }
        all_tags.update(predefined_tags)
        
        # Filter by current input
        current_tags = current.split(',')
        current_filter = current_tags[-1].strip().lower() if current_tags else ""
        
        # Build choices excluding tags already in the input
        existing_tags = [tag.strip() for tag in current_tags[:-1]]
        for tag in sorted(all_tags):
            if current_filter in tag.lower() and tag not in existing_tags:
                # Calculate what the full tag string would be if this choice is selected
                result_value = ", ".join(filter(None, existing_tags + [tag]))
                choices.append(app_commands.Choice(name=tag, value=result_value))
                if len(choices) >= 25:
                    break
    
    return choices


async def requirements_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for mission requirements."""
    common_requirements = [
        "Voice Required", "Experienced Pilots Only", "Entry Level Friendly",
        "Medium Risk", "High Risk", "Combat Experience Required",
        "Mining Experience Required", "Multiple Ships Required",
        "All Ships Provided", "Bring Your Own Ship", "Long Duration",
        "Short Duration", "Good Standing Required", "Organization Members Only",
        "Open To All", "Team Players Only", "Specific Ship Types Required"
    ]
    
    choices = []
    # Same approach as tags - handle comma-separated values
    current_reqs = current.split(',')
    current_filter = current_reqs[-1].strip().lower() if current_reqs else ""
    
    existing_reqs = [req.strip() for req in current_reqs[:-1]]
    for req in common_requirements:
        if current_filter in req.lower() and req not in existing_reqs:
            result_value = ", ".join(filter(None, existing_reqs + [req]))
            choices.append(app_commands.Choice(name=req, value=result_value))
            if len(choices) >= 25:
                break
                
    return choices


async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    choices = []
    for tz in pytz.common_timezones:
        if current.lower() in tz.lower():
            choices.append(app_commands.Choice(name=tz, value=tz))
            if len(choices) >= 25:
                break
    return choices

async def time_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for common time formats."""
    common_times = [
        "00:00", "01:00", "02:00", "03:00", "04:00", "05:00", 
        "06:00", "07:00", "08:00", "09:00", "10:00", "11:00",
        "12:00", "13:00", "14:00", "15:00", "16:00", "17:00",
        "18:00", "19:00", "20:00", "21:00", "22:00", "23:00",
        "7:00 AM", "8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM", "12:00 PM",
        "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM", "6:00 PM",
        "7:00 PM", "8:00 PM", "9:00 PM", "10:00 PM"
    ]
    
    choices = []
    for time in common_times:
        if current.lower() in time.lower():
            choices.append(app_commands.Choice(name=time, value=time))
            if len(choices) >= 25:
                break
    return choices

async def date_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for date options."""
    from datetime import datetime, timedelta
    
    # Generate date options: today, tomorrow, next few days, next weekend
    today = datetime.now()
    date_options = []
    
    # Today and next 14 days
    for i in range(15):
        day = today + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        if i == 0:
            label = f"Today ({date_str})"
        elif i == 1:
            label = f"Tomorrow ({date_str})"
        else:
            label = f"{day.strftime('%A, %b %d')} ({date_str})"
        date_options.append((label, date_str))
    
    # Next weekend (Saturday and Sunday)
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7  # If today is Saturday, get next Saturday
    
    next_saturday = today + timedelta(days=days_until_saturday)
    next_sunday = next_saturday + timedelta(days=1)
    
    date_options.append((f"Next Saturday ({next_saturday.strftime('%Y-%m-%d')})", 
                         next_saturday.strftime("%Y-%m-%d")))
    date_options.append((f"Next Sunday ({next_sunday.strftime('%Y-%m-%d')})", 
                         next_sunday.strftime("%Y-%m-%d")))
    
    choices = []
    # Filter by current input
    for label, date_value in date_options:
        if current.lower() in label.lower() or current.lower() in date_value.lower():
            choices.append(app_commands.Choice(name=label, value=date_value))
    
    return choices[:25]  # Limit to 25 choices (Discord max)

async def duration_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for common mission durations in minutes."""
    common_durations = [
        "15", "30", "45", "60", "90", "120", "150", "180", "240", "300"
    ]
    
    duration_labels = {
        "15": "15 minutes - Quick mission",
        "30": "30 minutes - Short mission",
        "45": "45 minutes - Short mission",
        "60": "1 hour - Standard mission",
        "90": "1.5 hours - Medium mission",
        "120": "2 hours - Medium mission",
        "150": "2.5 hours - Extended mission",
        "180": "3 hours - Long mission",
        "240": "4 hours - Major operation",
        "300": "5 hours - Extended operation"
    }
    
    choices = []
    current_str = str(current).strip()
    
    # First try exact matches
    for duration in common_durations:
        if current_str == duration:
            choices.append(app_commands.Choice(name=duration_labels[duration], value=int(duration)))
            break
            
    # Then try partial matches if we didn't get an exact match
    if not choices:
        for duration in common_durations:
            if current_str in duration:
                choices.append(app_commands.Choice(name=duration_labels[duration], value=int(duration)))
            
            # Also try to match the descriptive part of the label
            elif current_str and current_str in duration_labels[duration].lower():
                choices.append(app_commands.Choice(name=duration_labels[duration], value=int(duration)))
                
            if len(choices) >= 25:
                break
                
    # If no matches and the user entered a valid number, include it
    if not choices and current_str.isdigit():
        value = int(current_str)
        if 1 <= value <= 1440:  # Limit to 24 hours in minutes
            choices.append(app_commands.Choice(name=f"{value} minutes - Custom duration", value=value))
    
    return choices

async def earnings_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Autocomplete for common earnings amounts."""
    common_earnings = [
        ("10000", "10,000 aUEC - Small mission"),
        ("25000", "25,000 aUEC - Standard mission"),
        ("50000", "50,000 aUEC - Profitable mission"),
        ("100000", "100,000 aUEC - High-value mission"),
        ("250000", "250,000 aUEC - Major operation"),
        ("500000", "500,000 aUEC - Critical operation"),
        ("1000000", "1,000,000 aUEC - Exceptional value")
    ]
    
    choices = []
    current_str = str(current).strip().replace(",", "")
    
    # Check if current is a number and add exact match
    if current_str.isdigit():
        value = int(current_str)
        choices.append(app_commands.Choice(name=f"{value:,} aUEC - Custom amount", value=value))
    
    # Add suggestions
    for value_str, label in common_earnings:
        if current_str in value_str:
            choices.append(app_commands.Choice(name=label, value=int(value_str)))
        elif current_str and current_str in label.lower():
            choices.append(app_commands.Choice(name=label, value=int(value_str)))
            
        if len(choices) >= 25:
            break
    
    return choices

class MissionRSVP:
    def __init__(self):
        self.responses = {}   # Store RSVP responses keyed by user ID
        self.confirmed = []   # List of confirmed user IDs
        self.standby = []     # List of standby user IDs
        self.declined = []    # List of declined user IDs


class RSVPResponse:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Mission:
    """Enhanced mission class with timezone-aware datetime handling."""
    def __init__(
        self,
        name: str,
        leader_id: int,
        mission_type: MissionType,
        description: str,
        start_time: datetime,
        min_participants: int,
        anticipated_earnings: int = 0,
        max_participants: Optional[int] = None,
        required_ships: List[str] = None,
        status: MissionStatus = MissionStatus.RECRUITING,
        participants: Dict[int, Participant] = None,
        tags: List[str] = None,
        difficulty: Union[str, MissionDifficulty] = MissionDifficulty.NORMAL,
        estimated_duration: Optional[int] = None,
        requirements: List[str] = None,
        template_id: Optional[str] = None,
        briefing: str = "",
        **kwargs
    ):
        self.name = name
        self.leader_id = leader_id
        self.mission_type = mission_type
        self.description = description
        self.anticipated_earnings = anticipated_earnings
        self.actual_earnings = 0
        self.earnings_per_participant = {}
        # Ensure start_time is timezone-aware and in UTC
        if start_time.tzinfo is None:
            self.start_time = pytz.utc.localize(start_time)
        elif start_time.tzinfo != timezone.utc:
            self.start_time = start_time.astimezone(timezone.utc)
        else:
            self.start_time = start_time
        self.min_participants = min_participants
        self.max_participants = max_participants
        self.required_ships = required_ships or []
        self.status = status
        self.participants = participants or {}
        self.tags = tags or []
        self.difficulty = difficulty if isinstance(difficulty, MissionDifficulty) else MissionDifficulty.NORMAL
        self.estimated_duration = estimated_duration
        self.requirements = requirements or []
        self.creation_time = datetime.now(timezone.utc)
        self.mission_id = str(uuid.uuid4())
        self.message_id: Optional[int] = None
        self.channel_id: Optional[int] = None
        self.event_id: Optional[int] = None
        self.voice_channel_id: Optional[int] = None
        self.reminded_at: Set[float] = set()
        self.objectives = utils.parse_objectives(description)
        self.rsvp = MissionRSVP()
        self.template_id = template_id
        self.briefing = briefing
        self.history: List[Dict[str, Any]] = []

    def to_dict(self) -> dict:
        """Enhanced conversion of mission to dictionary for storage."""
        # Convert history entries to ensure all datetime objects are serialized
        serialized_history = []
        for entry in self.history:
            serialized_entry = entry.copy()
            if 'timestamp' in serialized_entry and isinstance(serialized_entry['timestamp'], datetime):
                serialized_entry['timestamp'] = serialized_entry['timestamp'].isoformat()
            serialized_history.append(serialized_entry)
    
        base_dict = {
            'name': self.name,
            'leader_id': self.leader_id,
            'mission_type': self.mission_type.name,
            'description': self.description,
            'start_time': self.start_time.isoformat(),
            'min_participants': self.min_participants,
            'max_participants': self.max_participants,
            'required_ships': self.required_ships,
            'status': self.status.name,
            'participants': {
                str(user_id): participant.to_dict()
                for user_id, participant in self.participants.items()
            },
            'tags': self.tags,
            'difficulty': self.difficulty.name if isinstance(self.difficulty, MissionDifficulty) else self.difficulty,
            'estimated_duration': self.estimated_duration,
            'requirements': self.requirements,
            'creation_time': self.creation_time.isoformat(),
            'mission_id': self.mission_id,
            'message_id': self.message_id,
            'channel_id': self.channel_id,
            'event_id': self.event_id,
            'voice_channel_id': self.voice_channel_id,
            'reminded_at': list(self.reminded_at),
            'objectives': self.objectives,
            'template_id': getattr(self, 'template_id', None),
            'briefing': getattr(self, 'briefing', ''),
            'history': serialized_history,
            'rsvp': {
                'responses': {
                    str(mid): resp.__dict__ for mid, resp in self.rsvp.responses.items()
                },
                'confirmed': self.rsvp.confirmed,
                'standby': self.rsvp.standby,
                'declined': self.rsvp.declined
            }
        }
        return base_dict

    @classmethod
    def from_dict(cls, data: dict) -> Mission:
        """Enhanced creation of mission from dictionary data."""
        try:
            mission_data = data.copy()
            mission_data['mission_type'] = MissionType[mission_data['mission_type']]
            mission_data['status'] = MissionStatus[mission_data['status']]
            if 'difficulty' in mission_data:
                diff_str = mission_data['difficulty']
                try:
                    mission_data['difficulty'] = MissionDifficulty[diff_str.upper()]
                except KeyError:
                    mission_data['difficulty'] = MissionDifficulty.NORMAL
            mission_data['start_time'] = datetime.fromisoformat(mission_data['start_time'])
            if mission_data['start_time'].tzinfo is None:
                mission_data['start_time'] = pytz.utc.localize(mission_data['start_time'])
            raw_participants = mission_data.pop('participants', {})
            participants = {}
            for user_id, p_data in raw_participants.items():
                try:
                    participants[int(user_id)] = Participant.from_dict(p_data)
                except Exception as e:
                    logger.error(f"Error parsing participant data for user {user_id}: {e}")
                    continue
            mission_data['participants'] = participants
            post_fields = {
                'mission_id': mission_data.pop('mission_id', None),
                'creation_time': datetime.fromisoformat(mission_data.pop('creation_time')),
                'message_id': mission_data.pop('message_id', None),
                'channel_id': mission_data.pop('channel_id', None),
                'event_id': mission_data.pop('event_id', None),
                'voice_channel_id': mission_data.pop('voice_channel_id', None),
                'reminded_at': set(mission_data.pop('reminded_at', [])),
                'objectives': mission_data.pop('objectives', []),
                'history': mission_data.pop('history', []),
                'rsvp': mission_data.pop('rsvp', {}),
                'template_id': mission_data.pop('template_id', None),
                'briefing': mission_data.pop('briefing', '')
            }
            if post_fields['creation_time'].tzinfo is None:
                post_fields['creation_time'] = pytz.utc.localize(post_fields['creation_time'])
                
            # Process history entries to convert timestamp strings back to datetime objects
            history_entries = []
            for entry in post_fields['history']:
                if isinstance(entry, dict):
                    if 'timestamp' in entry and isinstance(entry['timestamp'], str):
                        try:
                            entry['timestamp'] = datetime.fromisoformat(entry['timestamp'])
                        except ValueError:
                            entry['timestamp'] = datetime.now(timezone.utc)
                    history_entries.append(entry)
                
            mission_data['template_id'] = post_fields['template_id']
            mission_data['briefing'] = post_fields['briefing']
            mission = cls(**mission_data)
            mission.creation_time = post_fields['creation_time']
            if post_fields['mission_id']:
                mission.mission_id = post_fields['mission_id']
            mission.message_id = post_fields['message_id']
            mission.channel_id = post_fields['channel_id']
            mission.event_id = post_fields['event_id']
            mission.voice_channel_id = post_fields['voice_channel_id']
            mission.reminded_at = post_fields['reminded_at']
            mission.objectives = post_fields['objectives']
            mission.history = history_entries
            rsvp_data = post_fields['rsvp']
            if rsvp_data:
                for user_id, response_data in rsvp_data.get('responses', {}).items():
                    response = RSVPResponse(**response_data)
                    mission.rsvp.responses[int(user_id)] = response
                mission.rsvp.confirmed = rsvp_data.get('confirmed', [])
                mission.rsvp.standby = rsvp_data.get('standby', [])
                mission.rsvp.declined = rsvp_data.get('declined', [])
            return mission
        except Exception as e:
            logger.error(f"Error creating mission from dictionary: {e}")
            raise

    def add_participant(self, user_id: int, ship_name: str, role: str) -> bool:
        """Add a participant to the mission."""
        if self.max_participants and len(self.participants) >= self.max_participants:
            return False
        self.participants[user_id] = Participant(
            user_id=user_id,
            ship_name=ship_name,
            role=role
        )
        if len(self.participants) >= self.min_participants:
            self.status = MissionStatus.READY
        return True

    def remove_participant(self, user_id: int) -> bool:
        """Remove a participant from the mission."""
        if user_id not in self.participants:
            return False
        del self.participants[user_id]
        if len(self.participants) < self.min_participants:
            self.status = MissionStatus.RECRUITING
        return True

    def to_embed(self, bot: commands.Bot) -> discord.Embed:
        """Convert mission to Discord embed with improved formatting."""
        guild = bot.get_guild(GUILD_ID)
        embed = discord.Embed(
            title=f"📋 {self.name}",
            description=self.description,
            color=utils.get_status_color(self.status)
        )
        leader = guild.get_member(self.leader_id) if guild else None
        details = (
            f"**Type:** {self.mission_type.value}\n"
            f"**Status:** {self.status.value}\n"
            f"**Leader:** {leader.mention if leader else 'Unknown'}\n"
            f"**Start:** <t:{int(self.start_time.timestamp())}:f>\n"
            f"**Duration:** {self.estimated_duration} minutes"
        )
        embed.add_field(name="Mission Details", value=details, inline=False)
        if self.objectives:
            objectives = "\n".join(f"• {obj}" for obj in self.objectives)
            embed.add_field(name="Objectives", value=objectives, inline=False)
        participant_count = len(self.participants)
        required = f"/{self.max_participants}" if self.max_participants else ""
        roster = ""
        for participant in self.participants.values():
            member = guild.get_member(participant.user_id)
            if member:
                roster += f"• **{member.display_name}** - {participant.role} ({participant.ship_name})\n"
        embed.add_field(
            name=f"Roster ({participant_count}{required})",
            value=roster if roster else "No participants yet",
            inline=False
        )
        if self.required_ships:
            ships = "\n".join(f"• {ship}" for ship in self.required_ships)
            embed.add_field(name="Required Ships", value=ships, inline=False)
        if self.voice_channel_id:
            voice_channel = bot.get_channel(self.voice_channel_id)
            if voice_channel:
                embed.add_field(name="Voice Channel", value=voice_channel.mention, inline=False)
        embed.set_footer(text=f"Mission ID: {self.mission_id[:8]}")
        return embed

    def add_history_entry(self, action: str, actor_id: int, details: str):
        """Add an entry to mission history."""
        timestamp = datetime.now(timezone.utc)
        self.history.append({
            'timestamp': timestamp,
            'action': action,
            'actor_id': actor_id,
            'details': details
        })

    def get_history_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create an embed showing mission history."""
        embed = discord.Embed(
            title="Mission History",
            color=discord.Color.blue()
        )
        for entry in reversed(self.history[-10:]):
            actor = guild.get_member(entry['actor_id'])
            actor_name = actor.display_name if actor else "Unknown"
            timestamp = entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            embed.add_field(
                name=f"{entry['action']} - {timestamp}",
                value=f"By: {actor_name}\nDetails: {entry['details']}",
                inline=False
            )
        return embed
    

class ShipCategorySelect(discord.ui.Select):
    """Select menu for choosing ship categories"""
    def __init__(self, ships_view):
        self.ships_view = ships_view
        # Get unique manufacturers/categories from ships
        categories = set()
        for ship in Ship._ships_cache.values():
            manufacturer = ship.manufacturer if hasattr(ship, 'manufacturer') else 'Other'
            categories.add(manufacturer)
        
        # Sort categories alphabetically
        sorted_categories = sorted(list(categories))
        
        # Create options (add All option first)
        options = [discord.SelectOption(label="All Ships", value="all")]
        for category in sorted_categories[:24]:  # Max 25 options including "All"
            options.append(discord.SelectOption(label=category, value=category))
            
        super().__init__(
            placeholder="Select ship category/manufacturer",
            min_values=1, 
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        # Filter ships by selected category
        selected_category = self.values[0]
        self.ships_view.current_category = selected_category
        self.ships_view.page = 0  # Reset to first page
        
        # Update the ships select menu
        await self.ships_view.update_ship_select()
        await interaction.response.edit_message(view=self.ships_view)


class ShipsSelect(discord.ui.Select):
    """Select menu for choosing ships from the filtered category"""
    def __init__(self, ships_view, ships):
        self.ships_view = ships_view
        self.mission = ships_view.mission
        
        # Create options from the provided ships list
        options = []
        for ship in ships[:25]:  # Discord limit of 25 options
            display_name = ship.name.split(" (")[0] if " (" in ship.name else ship.name
            is_selected = ship.name in self.mission.required_ships
            options.append(discord.SelectOption(
                label=display_name, 
                value=ship.name,
                default=is_selected
            ))
            
        super().__init__(
            placeholder="Select required ships", 
            min_values=0, 
            max_values=len(options) if options else 1,
            options=options
        )
        
        # Disable if no options
        self.disabled = len(options) == 0

    async def callback(self, interaction: discord.Interaction):
        # Update the mission's required_ships
        # We need to preserve selections from other pages
        updated_selections = []
        
        # Keep ships from other pages/categories that are still selected
        for ship_name in self.mission.required_ships:
            if ship_name not in [option.value for option in self.options]:
                updated_selections.append(ship_name)
                
        # Add current selections
        updated_selections.extend(self.values)
        
        # Update mission
        self.mission.required_ships = updated_selections
        
        # Acknowledge the interaction
        await interaction.response.send_message(
            f"Required ships updated to: {', '.join(updated_selections) if updated_selections else 'None'}",
            ephemeral=True
        )
        
        # Save mission data
        self.ships_view.cog.save_missions()


class PaginationRow(discord.ui.View):
    """Row of pagination buttons"""
    def __init__(self, parent_view):
        super().__init__(timeout=None)
        self.parent_view = parent_view
        
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.parent_view.page > 0:
            self.parent_view.page -= 1
            await self.parent_view.update_ship_select()
            await interaction.response.edit_message(view=self.parent_view)
        else:
            await interaction.response.send_message("Already on the first page.", ephemeral=True)
            
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.parent_view.page + 1) * 25 < len(self.parent_view.get_filtered_ships()):
            self.parent_view.page += 1
            await self.parent_view.update_ship_select()
            await interaction.response.edit_message(view=self.parent_view)
        else:
            await interaction.response.send_message("No more ships to display.", ephemeral=True)
        
    @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Ship selection complete. Selected: "
            f"{', '.join(self.parent_view.mission.required_ships) if self.parent_view.mission.required_ships else 'None'}",
            ephemeral=True
        )
        # Update the mission embed
        await self.parent_view.cog.update_mission_view(self.parent_view.mission)
        # End the view - add try-except to handle case where message is already deleted
        try:
            await interaction.message.delete()
        except discord.errors.NotFound:
            pass  # Message already deleted, that's fine


class ImprovedShipsView(discord.ui.View):
    """Improved view for selecting required ships with pagination and filtering"""
    def __init__(self, cog: MissionCog, mission: Mission):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.cog = cog
        self.mission = mission
        self.page = 0
        self.current_category = "all"
        
        # Add the category selector
        self.add_item(ShipCategorySelect(self))
        
        # Add initial ship selector
        self.ship_select = None
        
        # Add pagination row (separate view that acts as a component row)
        self.pagination_row = PaginationRow(self)
        for item in self.pagination_row.children:
            self.add_item(item)
        
    def get_filtered_ships(self):
        """Get ships filtered by current category"""
        all_ships = list(Ship._ships_cache.values())
        
        if self.current_category == "all":
            filtered_ships = all_ships
        else:
            filtered_ships = [
                ship for ship in all_ships 
                if hasattr(ship, 'manufacturer') and ship.manufacturer == self.current_category
            ]
        
        # Sort alphabetically
        return sorted(filtered_ships, key=lambda s: s.name)
    
    async def update_ship_select(self):
        """Update the ship select menu based on current page and category"""
        # Get all ships for the current filter
        filtered_ships = self.get_filtered_ships()
        
        # Calculate page bounds
        start_idx = self.page * 25
        end_idx = min(start_idx + 25, len(filtered_ships))
        
        # Get ships for current page
        page_ships = filtered_ships[start_idx:end_idx]
        
        # Remove old ship select if it exists
        if self.ship_select:
            self.remove_item(self.ship_select)
        
        # Create new ship select
        self.ship_select = ShipsSelect(self, page_ships)
        self.add_item(self.ship_select)


async def select_required_ships(interaction: discord.Interaction, mission: Mission, cog: MissionCog):
    """Show the improved ship selection interface"""
    view = ImprovedShipsView(cog, mission)
    await view.update_ship_select()  # Initialize the ship select menu
    await interaction.followup.send(
        "Select required ships for the mission.\n"
        "You can filter by manufacturer and navigate through pages.",
        view=view,
        ephemeral=True
    )


class JoinMissionModal(discord.ui.Modal):
    """Modal for joining a mission with ship and role selection"""
    def __init__(self, mission: Mission, cog: MissionCog):
        super().__init__(title=f"Join Mission: {mission.name}")
        self.mission = mission
        self.cog = cog
        
        # Ship input field with suggestions
        ship_suggestions = ""
        if hasattr(Ship, '_ships_cache') and Ship._ships_cache:
            # Get some examples to show in the placeholder
            ships = sorted(list(Ship._ships_cache.values()), key=lambda s: s.name)
            ship_examples = [s.name.split(" (")[0] if " (" in s.name else s.name for s in ships[:5]]
            ship_suggestions = f"Examples: {', '.join(ship_examples)}"
            
        self.ship_input = discord.ui.TextInput(
            label="Ship Name",
            placeholder=ship_suggestions,
            required=True,
            max_length=100
        )
        
        # Role input field with common role suggestions
        roles = ["Pilot", "Copilot", "Gunner", "Engineer", "Marine", "Medical", "Security", "Scout", "Support"]
        role_suggestions = f"Common roles: {', '.join(roles)}"
        
        self.role_input = discord.ui.TextInput(
            label="Role",
            placeholder=role_suggestions,
            required=True,
            max_length=50
        )
        
        # Add the inputs to the modal
        self.add_item(self.ship_input)
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction):
        ship = self.ship_input.value.strip()
        role = self.role_input.value.strip()
        
        try:
            # Check if user is already participating
            if interaction.user.id in self.mission.participants:
                await interaction.response.send_message(
                    "You are already a participant in this mission.",
                    ephemeral=True
                )
                return
                
            # Check if mission is full
            if self.mission.max_participants and len(self.mission.participants) >= self.mission.max_participants:
                await interaction.response.send_message(
                    "This mission is full. Contact the mission leader if you still want to join.",
                    ephemeral=True
                )
                return
                
            # Add participant directly to mission
            success = self.mission.add_participant(interaction.user.id, ship, role)
            
            if success:
                # Add history entry
                self.mission.add_history_entry(
                    "join_mission",
                    interaction.user.id,
                    f"Joined as {role} on {ship}"
                )
                
                # Save changes
                self.cog.save_missions()
                
                await interaction.response.send_message(
                    f"✅ You've joined the mission as {role} on {ship}!", 
                    ephemeral=True
                )
                
                # Update mission embed
                await self.cog.update_mission_view(self.mission)
            else:
                await interaction.response.send_message(
                    f"❌ Failed to join mission. The mission may be full.", 
                    ephemeral=True
                )
        except Exception as e:
            import logging
            logger = logging.getLogger('missions')
            logger.error(f"Error in join mission modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while trying to join the mission.", 
                ephemeral=True
            )


class LeaveMissionConfirm(discord.ui.View):
    """Confirmation view for leaving a mission"""
    def __init__(self, mission: Mission, cog: MissionCog):
        super().__init__(timeout=60)
        self.mission = mission
        self.cog = cog
        
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove participant
        if interaction.user.id in self.mission.participants:
            success = self.mission.remove_participant(interaction.user.id)
            if success:
                self.mission.add_history_entry(
                    "leave_mission",
                    interaction.user.id,
                    "Left the mission"
                )
                self.cog.save_missions()
                await interaction.response.send_message("You have left the mission.", ephemeral=True)
                # Update mission embed
                await self.cog.update_mission_view(self.mission)
            else:
                await interaction.response.send_message(
                    "Failed to leave the mission. Please try again.", 
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "You are not a participant in this mission.", 
                ephemeral=True
            )
        self.stop()
        
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action canceled.", ephemeral=True)
        self.stop()


class InteractiveMissionView(discord.ui.View):
    """Enhanced mission view with join/leave buttons and other interactive elements"""
    def __init__(self, cog: MissionCog, mission: Mission):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.mission = mission
        
        # Disable buttons based on mission status
        is_active = mission.status in [MissionStatus.RECRUITING, MissionStatus.READY]
        is_completed = mission.status in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]
        
        # Set button states
        self.join_button.disabled = not is_active
        self.leave_button.disabled = not is_active
        
        # Additional state management
        if mission.max_participants and len(mission.participants) >= mission.max_participants:
            self.join_button.disabled = True
            self.join_button.label = "Full"
    
    @discord.ui.button(label="Join Mission", style=discord.ButtonStyle.success, custom_id="join_mission")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prevent joining if already in the mission
        if interaction.user.id in self.mission.participants:
            await interaction.response.send_message(
                "You are already a participant in this mission.",
                ephemeral=True
            )
            return
            
        # Prevent joining if mission is full
        if self.mission.max_participants and len(self.mission.participants) >= self.mission.max_participants:
            await interaction.response.send_message(
                "This mission is full. Contact the mission leader if you still want to join.",
                ephemeral=True
            )
            return
            
        # Open the join modal
        await interaction.response.send_modal(JoinMissionModal(self.mission, self.cog))
    
    @discord.ui.button(label="Leave Mission", style=discord.ButtonStyle.danger, custom_id="leave_mission")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user is a participant
        if interaction.user.id not in self.mission.participants:
            await interaction.response.send_message(
                "You are not a participant in this mission.",
                ephemeral=True
            )
            return
            
        # Prevent the leader from leaving unless they reassign leadership
        if interaction.user.id == self.mission.leader_id:
            await interaction.response.send_message(
                "As the mission leader, you cannot leave the mission. "
                "You need to transfer leadership or cancel the mission.",
                ephemeral=True
            )
            return
            
        # Show confirmation
        view = LeaveMissionConfirm(self.mission, self.cog)
        await interaction.response.send_message(
            "Are you sure you want to leave this mission?",
            view=view,
            ephemeral=True
        )
    
    @discord.ui.button(label="Mission Details", style=discord.ButtonStyle.secondary, custom_id="mission_details")
    async def details_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show detailed mission information"""
        # Create a detailed embed
        embed = discord.Embed(
            title=f"📋 Mission Details: {self.mission.name}",
            description=self.mission.description,
            color=utils.get_status_color(self.status)
        )
        
        # Mission information
        embed.add_field(
            name="Mission Info",
            value=(
                f"**Type:** {self.mission.mission_type.value}\n"
                f"**Status:** {self.mission.status.value}\n"
                f"**Difficulty:** {self.mission.difficulty.value if isinstance(self.mission.difficulty, MissionDifficulty) else self.mission.difficulty}\n"
                f"**Expected Duration:** {self.mission.estimated_duration or 'Unknown'} minutes\n"
                f"**Anticipated Earnings:** {self.mission.anticipated_earnings:,} aUEC\n"
                f"**Mission ID:** {self.mission.mission_id[:8]}"
            ),
            inline=False
        )
        
        # Time information
        embed.add_field(
            name="Schedule",
            value=(
                f"**Start Time:** <t:{int(self.mission.start_time.timestamp())}:F>\n"
                f"**Local Time:** <t:{int(self.mission.start_time.timestamp())}:t>\n"
                f"**Time Until Start:** <t:{int(self.mission.start_time.timestamp())}:R>\n"
                f"**Created:** <t:{int(self.mission.creation_time.timestamp())}:R>"
            ),
            inline=False
        )
        
        # Participant information
        guild = interaction.guild
        roster = ""
        for uid, participant in self.mission.participants.items():
            member = guild.get_member(uid)
            name = member.display_name if member else "Unknown Member"
            roster += f"• **{name}** - {participant.role} ({participant.ship_name})\n"
            
        embed.add_field(
            name=f"Roster ({len(self.mission.participants)}/{self.mission.max_participants or '∞'})",
            value=roster if roster else "No participants yet",
            inline=False
        )
        
        # Requirements information
        if self.mission.requirements:
            requirements = "\n".join(f"• {req}" for req in self.mission.requirements)
            embed.add_field(name="Requirements", value=requirements, inline=False)
            
        # Required ships
        if self.mission.required_ships:
            ships = "\n".join(f"• {ship}" for ship in self.mission.required_ships)
            embed.add_field(name="Required Ships", value=ships, inline=False)
            
        # Mission tags
        if self.mission.tags:
            tags = ", ".join(f"`{tag}`" for tag in self.mission.tags)
            embed.add_field(name="Tags", value=tags, inline=False)
            
        # Mission briefing if available
        if self.mission.briefing:
            embed.add_field(name="Briefing", value=self.mission.briefing[:1024], inline=False)
            
        # Voice channel info if available
        if self.mission.voice_channel_id:
            voice_channel = interaction.guild.get_channel(self.mission.voice_channel_id)
            if voice_channel:
                embed.add_field(name="Voice Channel", value=voice_channel.mention, inline=False)
                
        # Send detailed information
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Leader-only buttons conditionally added during initialization
    async def add_leader_buttons(self, user_id: int):
        if user_id == self.mission.leader_id:
            # Edit mission button
            edit_button = discord.ui.Button(
                label="Edit Mission", 
                style=discord.ButtonStyle.primary,
                custom_id="edit_mission",
                disabled=self.mission.status in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]
            )
            edit_button.callback = self.edit_mission_callback
            self.add_item(edit_button)
            
            # Add "Start Mission" button if mission is READY
            if self.mission.status == MissionStatus.READY:
                start_button = discord.ui.Button(
                    label="Start Mission", 
                    style=discord.ButtonStyle.success,
                    custom_id="start_mission"
                )
                start_button.callback = self.start_mission_callback
                self.add_item(start_button)
            # Add "Complete Mission" button if mission is IN_PROGRESS
            elif self.mission.status == MissionStatus.IN_PROGRESS:
                complete_button = discord.ui.Button(
                    label="Complete Mission", 
                    style=discord.ButtonStyle.success,
                    custom_id="complete_mission"
                )
                complete_button.callback = self.complete_mission_callback
                self.add_item(complete_button)
            
            # Cancel mission button
            cancel_button = discord.ui.Button(
                label="Cancel Mission", 
                style=discord.ButtonStyle.danger,
                custom_id="cancel_mission",
                disabled=self.mission.status in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]
            )
            cancel_button.callback = self.cancel_mission_callback
            self.add_item(cancel_button)
    
    # Callback for edit button
    async def edit_mission_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.mission.leader_id:
            await interaction.response.send_message(
                "Only the mission leader can edit this mission.",
                ephemeral=True
            )
            return
            
        await interaction.response.send_message(
            "To edit mission parameters like time, description, etc., please use the command system. "
            "Ship requirements can be updated through the mission details page.",
            ephemeral=True
        )
    
    # Callback for start button
    async def start_mission_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.mission.leader_id:
            await interaction.response.send_message(
                "Only the mission leader can start this mission.",
                ephemeral=True
            )
            return
            
        if self.mission.status != MissionStatus.READY:
            await interaction.response.send_message(
                f"Cannot start mission: current status is {self.mission.status.value}",
                ephemeral=True
            )
            return
            
        # Start the mission
        await interaction.response.defer(ephemeral=True)
        await self.cog.start_mission(self.mission)
        await interaction.followup.send("Mission started successfully!", ephemeral=True)
    
    # Callback for complete button
    async def complete_mission_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.mission.leader_id:
            await interaction.response.send_message(
                "Only the mission leader can complete this mission.",
                ephemeral=True
            )
            return
            
        if self.mission.status != MissionStatus.IN_PROGRESS:
            await interaction.response.send_message(
                f"Cannot complete mission: current status is {self.mission.status.value}",
                ephemeral=True
            )
            return
            
        # Complete the mission
        await interaction.response.defer(ephemeral=True)
        success = await self.cog.complete_mission(self.mission.mission_id)
        if success:
            await interaction.followup.send("Mission completed successfully!", ephemeral=True)
        else:
            await interaction.followup.send("Failed to complete mission. Please try again.", ephemeral=True)
    
    # Callback for cancel button
    async def cancel_mission_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.mission.leader_id:
            await interaction.response.send_message(
                "Only the mission leader can cancel this mission.",
                ephemeral=True
            )
            return
            
        # Show confirmation
        class CancelConfirmView(discord.ui.View):
            def __init__(self, parent_view):
                super().__init__(timeout=60)
                self.parent_view = parent_view
                
            @discord.ui.button(label="Confirm Cancel", style=discord.ButtonStyle.danger)
            async def confirm_button(self, confirm_interaction: discord.Interaction, button: discord.ui.Button):
                # Cancel the mission
                self.parent_view.mission.status = MissionStatus.CANCELLED
                self.parent_view.mission.add_history_entry(
                    "cancel_mission",
                    confirm_interaction.user.id,
                    "Mission cancelled by leader"
                )
                self.parent_view.cog.save_missions()
                
                # Notify all participants
                channel = self.parent_view.cog.bot.get_channel(self.parent_view.mission.channel_id)
                if channel:
                    mentions = []
                    for uid in self.parent_view.mission.participants:
                        member = confirm_interaction.guild.get_member(uid)
                        if member:
                            mentions.append(member.mention)
                    
                    if mentions:
                        await channel.send(
                            f"⚠️ **MISSION CANCELLED** ⚠️\n"
                            f"The mission '{self.parent_view.mission.name}' has been cancelled.\n"
                            f"{' '.join(mentions)}"
                        )
                
                # Update view
                await self.parent_view.cog.update_mission_view(self.parent_view.mission)
                await confirm_interaction.response.send_message("Mission cancelled successfully.", ephemeral=True)
                self.stop()
                
            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel_button(self, cancel_interaction: discord.Interaction, button: discord.ui.Button):
                await cancel_interaction.response.send_message("Action cancelled.", ephemeral=True)
                self.stop()
        
        view = CancelConfirmView(self)
        await interaction.response.send_message(
            "⚠️ Are you sure you want to cancel this mission? This action cannot be undone.",
            view=view,
            ephemeral=True
        )


# Function to create and setup an interactive mission view
async def create_interactive_mission_view(cog: MissionCog, mission: Mission, user_id: Optional[int] = None):
    """Create and configure an interactive mission view with appropriate buttons"""
    view = InteractiveMissionView(cog, mission)
    
    # Add leader buttons if user_id matches mission leader
    if user_id and user_id == mission.leader_id:
        await view.add_leader_buttons(user_id)
    elif user_id and mission.status not in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]:
        # If not leader but an admin, check if they should have leader buttons
        guild = cog.bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member and member.guild_permissions.administrator:
                await view.add_leader_buttons(user_id)
    
    return view


class MissionCog(commands.Cog):
    """Enhanced mission management cog with timezone-aware operations and persistent views."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.coda = bot.coda_client  # Add coda client
        self.missions: Dict[str, Mission] = {}
        self._profile_cog = None  # Profile cog reference
        self.load_missions()
        self.reminder_task.start()
        logger.info(f"MissionCog initialized with {len(self.missions)} missions")
    
    @property
    def profile_cog(self):
        if self._profile_cog is None:
            self._profile_cog = self.bot.get_cog('ProfileCog')
        return self._profile_cog
        
    def load_missions(self):
        try:
            if not os.path.exists(MISSIONS_DATA_FILE):
                logger.info("No missions data file found, creating a new one.")
                self.missions = {}
                self.save_missions()
                return
            with open(MISSIONS_DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    logger.info("Missions data file is empty, initializing with empty dictionary.")
                    self.missions = {}
                    self.save_missions()
                    return
                try:
                    data = json.loads(content)
                    self.missions = {}
                    for mission_id, mission_data in data.items():
                        try:
                            self.missions[mission_id] = Mission.from_dict(mission_data)
                        except Exception as e:
                            logger.error(f"Failed to load mission {mission_id}: {e}")
                    logger.info(f"Successfully loaded {len(self.missions)} missions.")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in missions data file: {e}")
                    logger.info("Creating backup of corrupted file and starting with empty missions.")
                    backup_name = f"{MISSIONS_DATA_FILE}.backup.{int(datetime.now().timestamp())}"
                    os.rename(MISSIONS_DATA_FILE, backup_name)
                    self.missions = {}
                    self.save_missions()
        except Exception as e:
            logger.error(f"Failed to load missions: {e}")
            self.missions = {}

        
    async def complete_mission(self, mission_id: str) -> bool:
        """Complete a mission and update its status and participant profiles."""
        try:
            mission = self.missions.get(mission_id)
            if not mission:
                logger.error(f"Mission not found: {mission_id}")
                return False
                
            # Update mission status
            mission.status = MissionStatus.COMPLETED
            mission.add_history_entry(
                "complete_mission",
                mission.leader_id,
                f"Mission completed with {len(mission.participants)} participants"
            )
            
            # Update UI
            await self.update_mission_view(mission)
            
            # Get ProfileCog to update participant profiles
            profile_cog = self.bot.get_cog('ProfileCog')
            if profile_cog:
                for user_id, participant in mission.participants.items():
                    # Format mission type string
                    mission_type = mission.mission_type.name if hasattr(mission.mission_type, 'name') else str(mission.mission_type)
                    
                    # Call profile_cog to add mission completion
                    try:
                        success = await profile_cog.add_mission_completion(
                            user_id=user_id,
                            mission_name=mission.name,
                            mission_type=mission_type,
                            role=participant.role,
                            ship=participant.ship_name
                        )
                        if not success:
                            logger.warning(f"Failed to update profile for participant {user_id} in mission {mission_id}")
                    except Exception as e:
                        logger.error(f"Error updating profile for user {user_id}: {e}")
            else:
                logger.warning(f"Could not find ProfileCog to update participant profiles for mission {mission_id}")
            
            # Notify participants
            channel = self.bot.get_channel(mission.channel_id)
            if channel:
                mentions = []
                for user_id in mission.participants:
                    member = channel.guild.get_member(user_id)
                    if member:
                        mentions.append(member.mention)
                        
                # Send completion message
                completion_embed = discord.Embed(
                    title=f"Mission Complete: {mission.name}",
                    description=f"The mission has been successfully completed!",
                    color=discord.Color.green()
                )
                
                if mission.anticipated_earnings > 0:
                    completion_embed.add_field(
                        name="Earnings", 
                        value=f"{mission.anticipated_earnings:,} aUEC", 
                        inline=False
                    )
                    
                if mentions:
                    await channel.send(
                        f"🏆 **MISSION COMPLETED** 🏆\n{' '.join(mentions)}",
                        embed=completion_embed
                    )
                else:
                    await channel.send(embed=completion_embed)
                    
            # Save mission data
            self.save_missions()
            return True
            
        except Exception as e:
            logger.error(f"Error completing mission: {e}")
            return False

    def cog_unload(self):
        self.reminder_task.cancel()
        self.save_missions()
        for mission in self.missions.values():
            if mission.voice_channel_id:
                asyncio.create_task(self.cleanup_voice_channel(mission))

    @tasks.loop(minutes=1)
    async def reminder_task(self):
        try:
            now = datetime.now(timezone.utc)
            for mission in list(self.missions.values()):
                if mission.status not in [MissionStatus.RECRUITING, MissionStatus.READY]:
                    continue
                time_until = mission.start_time - now
                minutes_until = time_until.total_seconds() / 60
                if minutes_until in [30, 15, 5] and minutes_until not in mission.reminded_at:
                    await self.send_mission_reminder(mission)
                    mission.reminded_at.add(minutes_until)
                    logger.info(f"Sent {int(minutes_until)} minute reminder for mission '{mission.name}'")
                if 0 <= minutes_until <= 1 and mission.status == MissionStatus.READY:
                    await self.start_mission(mission)
                    logger.info(f"Auto-started mission '{mission.name}'")
        except Exception as e:
            logger.error(f"Error in reminder task: {e}")

    async def cleanup_voice_channel(self, mission: Mission):
        if mission.voice_channel_id:
            try:
                channel = self.bot.get_channel(mission.voice_channel_id)
                if channel:
                    await channel.delete()
                    logger.info(f"Deleted voice channel for mission {mission.name}")
            except Exception as e:
                logger.error(f"Error deleting voice channel for mission {mission.name}: {e}")

    def save_missions(self):
        try:
            data = {}
            for mission_id, mission in self.missions.items():
                try:
                    if not isinstance(mission.mission_type, MissionType):
                        logger.error(f"Invalid mission_type for mission {mission_id}")
                        continue
                    if not isinstance(mission.status, MissionStatus):
                        logger.error(f"Invalid status for mission {mission_id}")
                        continue
                    data[mission_id] = mission.to_dict()
                except Exception as e:
                    logger.error(f"Failed to serialize mission {mission_id}: {e}")
                    continue
            directory = os.path.dirname(MISSIONS_DATA_FILE)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
            with open(MISSIONS_DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"Saved {len(self.missions)} missions to {MISSIONS_DATA_FILE}")
        except Exception as e:
            logger.error(f"Failed to save missions: {e}")
            try:
                backup_file = f"{MISSIONS_DATA_FILE}.emergency.{int(datetime.now().timestamp())}"
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
                logger.info(f"Created emergency backup at {backup_file}")
            except Exception as backup_error:
                logger.error(f"Failed to create emergency backup: {backup_error}")

    async def start_mission(self, mission: Mission):
        try:
            mission.status = MissionStatus.IN_PROGRESS
            self.save_missions()
            channel = self.bot.get_channel(mission.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(mission.message_id)
                    # Create a new interactive view with leader buttons.
                    view = await create_interactive_mission_view(self, mission, mission.leader_id)
                    await message.edit(embed=mission.to_embed(self.bot), view=view)
                except Exception as e:
                    logger.error(f"Failed to update mission message: {e}")
            if mission.voice_channel_id:
                voice_channel = self.bot.get_channel(mission.voice_channel_id)
                if voice_channel:
                    guild = self.bot.get_guild(GUILD_ID)
                    for participant in mission.participants.values():
                        member = guild.get_member(participant.user_id)
                        if member and member.voice:
                            try:
                                await member.move_to(voice_channel)
                            except Exception as e:
                                logger.error(f"Failed to move {member} to voice channel: {e}")
            mentions = [
                channel.guild.get_member(p.user_id).mention
                for p in mission.participants.values()
                if channel.guild.get_member(p.user_id)
            ]
            mention_text = " ".join(mentions) if mentions else "No participants to mention."
            await channel.send(f"🚀 Mission '{mission.name}' has started!\n{mention_text}")
        except Exception as e:
            logger.error(f"Error starting mission '{mission.name}': {e}")

    async def send_mission_reminder(self, mission: Mission):
        if not mission.channel_id:
            return
        channel = self.bot.get_channel(mission.channel_id)
        if not channel:
            return
        time_until = mission.start_time - datetime.now(timezone.utc)
        minutes_until = int(time_until.total_seconds() / 60)
        embed = discord.Embed(
            title=f"Mission Reminder: {mission.name}",
            description=(
                f"Mission starting <t:{int(mission.start_time.timestamp())}:R>!\n\n"
                f"**Type:** {mission.mission_type.value}\n"
                f"**Status:** {mission.status.value}\n"
                f"Time until start: {minutes_until} minutes"
            ),
            color=utils.get_status_color(mission.status)
        )
        if mission.briefing:
            embed.add_field(name="Briefing", value=mission.briefing[:1024], inline=False)
        participant_mentions = []
        for user_id in mission.participants:
            member = channel.guild.get_member(user_id)
            if member:
                participant_mentions.append(member.mention)
        content = "Mission Reminder!" if not participant_mentions else " ".join(participant_mentions)
        await channel.send(content=content, embed=embed)

    async def create_mission_from_order(self, order: Any) -> None:
        from .mission_system.shared import MissionType, MissionStatus, MissionDifficulty, Participant
        try:
            try:
                mission_type_enum = MissionType[order.mission_type.upper()]
            except KeyError:
                mission_type_enum = MissionType.NORMAL
            estimated_duration = int((order.end_date - order.start_date).total_seconds() // 60)
            mission = Mission(
                name=order.title,
                leader_id=order.author_id,
                mission_type=mission_type_enum,
                description=order.description,
                start_time=order.start_date,
                min_participants=1,
                max_participants=10,
                required_ships=[],
                status=MissionStatus.RECRUITING,
                participants={},
                tags=[],
                difficulty=MissionDifficulty.NORMAL,
                estimated_duration=estimated_duration,
                requirements=[],
                template_id=order.order_id,
                briefing="Mission created from order."
            )
            self.missions[mission.mission_id] = mission
            self.save_missions()
            channel = self.bot.get_channel(ACTIVE_OPERATIONS_CHANNEL_ID)
            if channel:
                view = await create_interactive_mission_view(self, mission, order.author_id)
                message = await channel.send(embed=mission.to_embed(self.bot), view=view)
                mission.message_id = message.id
                mission.channel_id = channel.id
                self.save_missions()
        except Exception as e:
            logger.error(f"Error creating mission from order: {e}")

    @app_commands.command(name="create_mission", description="Create a new mission")
    @app_commands.describe(
        name="Mission name",
        mission_type="Type of mission",
        description="Mission description",
        time="Time (e.g., 3:00 PM, 15:00, 1500)",
        timezone="Your timezone (e.g., US/Pacific, UTC)",
        date="Mission date (MM/DD/YYYY or YYYY-MM-DD)",
        min_participants="Minimum participants required (default: 2)",
        max_participants="Maximum participants allowed (optional)",
        anticipated_earnings="Expected total mission earnings in aUEC",
        difficulty="Mission difficulty level",
        duration="Estimated duration in minutes",
        tags="Mission tags (comma-separated)",
        requirements="Special requirements (comma-separated)"
    )
    @app_commands.choices(
        mission_type=[app_commands.Choice(name=mt.value, value=mt.name) for mt in MissionType],
        difficulty=[app_commands.Choice(name=md.value, value=md.name) for md in MissionDifficulty]
    )
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_commands.autocomplete(time=time_autocomplete)
    @app_commands.autocomplete(date=date_autocomplete)
    @app_commands.autocomplete(duration=duration_autocomplete)
    @app_commands.autocomplete(anticipated_earnings=earnings_autocomplete)
    @app_commands.autocomplete(tags=tags_autocomplete)
    @app_commands.autocomplete(requirements=requirements_autocomplete)
    async def create_mission(
        self,
        interaction: discord.Interaction,
        name: str,
        mission_type: str,
        description: str,
        time: str,
        timezone: str = "UTC",
        date: Optional[str] = None,
        min_participants: Optional[int] = 2,
        max_participants: Optional[int] = None,
        anticipated_earnings: Optional[int] = 0,
        difficulty: str = "Normal",
        duration: Optional[int] = None,
        tags: Optional[str] = None,
        requirements: Optional[str] = None
    ):
        await interaction.response.defer()
        try:
            mission_type_enum = MissionType[mission_type]
            utc_datetime = await self.parse_mission_time(time, timezone, date)
            if not utc_datetime:
                await interaction.followup.send("Invalid time format.", ephemeral=True)
                return
            mission = Mission(
                name=name,
                leader_id=interaction.user.id,
                mission_type=mission_type_enum,
                description=description,
                start_time=utc_datetime,
                min_participants=min_participants,
                max_participants=max_participants,
                required_ships=[],
                tags=[t.strip() for t in tags.split(',')] if tags else [],
                difficulty=difficulty,
                estimated_duration=duration,
                requirements=[r.strip() for r in requirements.split(',')] if requirements else [],
                anticipated_earnings=anticipated_earnings
            )
            self.missions[mission.mission_id] = mission
            self.save_missions()
            if VOICE_OPERATIONS_CHANNEL_ID:
                voice_channel = await self.create_voice_channel(interaction.guild, name)
                if voice_channel:
                    mission.voice_channel_id = voice_channel.id
                    self.save_missions()
            if mission.voice_channel_id:
                await self.create_scheduled_event(interaction.guild, mission)
            channel = self.bot.get_channel(ACTIVE_OPERATIONS_CHANNEL_ID)
            if not channel:
                await interaction.followup.send("Could not find operations channel.", ephemeral=True)
                return
                
            # Create interactive mission view instead of old view
            view = await create_interactive_mission_view(self, mission, interaction.user.id)
            message = await channel.send(embed=mission.to_embed(self.bot), view=view)
            mission.message_id = message.id
            mission.channel_id = channel.id
            self.save_missions()
            success_msg = f"✅ Mission '{name}' created for <t:{int(utc_datetime.timestamp())}:F>!"
            if mission.voice_channel_id:
                voice_channel = self.bot.get_channel(mission.voice_channel_id)
                if voice_channel:
                    success_msg += f"\nVoice channel: {voice_channel.mention}"
            await interaction.followup.send(success_msg, ephemeral=True)
            
            # Use the improved ship selection
            await select_required_ships(interaction, mission, self)
            logger.info(f"Created mission: {name} for {utc_datetime} UTC")
        except Exception as e:
            logger.error(f"Error creating mission: {e}")
            await interaction.followup.send(f"Error creating mission: {str(e)}", ephemeral=True)

    @app_commands.command(name="join_mission", description="Join an existing mission")
    @app_commands.describe(
        mission_id="The ID of the mission to join",
        ship="Your ship for this mission",
        role="Your role for this mission"
    )
    @app_commands.autocomplete(mission_id=mission_id_autocomplete)
    @app_commands.autocomplete(ship=ship_name_autocomplete)
    @app_commands.autocomplete(role=role_autocomplete)
    async def join_mission(
        self,
        interaction: discord.Interaction,
        mission_id: str,
        ship: str,
        role: str
    ):
        """Join a mission with autocomplete for ship and role selection"""
        await interaction.response.defer(ephemeral=True)
        
        # Find the mission
        mission = self.missions.get(mission_id)
        if not mission:
            await interaction.followup.send(f"❌ Mission with ID `{mission_id}` not found.", ephemeral=True)
            return
            
        # Check if already a participant
        if interaction.user.id in mission.participants:
            await interaction.followup.send("You are already a participant in this mission.", ephemeral=True)
            return
            
        # Check if mission is full
        if mission.max_participants and len(mission.participants) >= mission.max_participants:
            await interaction.followup.send("This mission is full. Contact the mission leader if you still want to join.", ephemeral=True)
            return
            
        # Add participant
        success, message = await self.add_participant(
            mission_id,
            interaction.user,
            ship,
            role
        )
        
        if success:
            # Update mission view
            await self.update_mission_view(mission)
            
            await interaction.followup.send(
                f"✅ You've joined mission '{mission.name}' as {role} on {ship}!",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Failed to join mission: {message or 'Unknown error'}",
                ephemeral=True
            )

    @app_commands.command(name="leave_mission", description="Leave a mission you've joined")
    @app_commands.describe(mission_id="The ID of the mission to leave")
    @app_commands.autocomplete(mission_id=mission_id_autocomplete)
    async def leave_mission(self, interaction: discord.Interaction, mission_id: str):
        """Leave a mission with autocomplete for mission selection"""
        await interaction.response.defer(ephemeral=True)
        
        # Find the mission
        mission = self.missions.get(mission_id)
        if not mission:
            await interaction.followup.send(f"❌ Mission with ID `{mission_id}` not found.", ephemeral=True)
            return
            
        # Check if user is a participant
        if interaction.user.id not in mission.participants:
            await interaction.followup.send("You are not a participant in this mission.", ephemeral=True)
            return
            
        # Prevent the leader from leaving unless they reassign leadership
        if interaction.user.id == mission.leader_id:
            await interaction.followup.send(
                "As the mission leader, you cannot leave the mission. "
                "You need to transfer leadership or cancel the mission.",
                ephemeral=True
            )
            return
            
        # Remove participant
        success = mission.remove_participant(interaction.user.id)
        if success:
            mission.add_history_entry(
                "leave_mission",
                interaction.user.id,
                "Left the mission via command"
            )
            self.save_missions()
            
            # Update mission view
            await self.update_mission_view(mission)
            
            await interaction.followup.send(f"You have left mission '{mission.name}'.", ephemeral=True)
        else:
            await interaction.followup.send("Failed to leave the mission. Please try again.", ephemeral=True)
    
    async def parse_mission_time(
        self,
        time_str: str,
        timezone_str: str,
        date_str: Optional[str] = None
    ) -> Optional[datetime]:
        try:
            target_tz = pytz.timezone(timezone_str)
            current_date = datetime.now()
            if ':' in time_str:
                time_str = time_str.upper()
                is_pm = 'PM' in time_str
                clean_time = time_str.replace("AM", "").replace("PM", "").strip()
                hours, minutes = map(int, clean_time.split(':'))
                if is_pm and hours < 12:
                    hours += 12
                elif not is_pm and hours == 12:
                    hours = 0
            else:
                hours = int(time_str[:2])
                minutes = int(time_str[2:]) if len(time_str) > 2 else 0
            if date_str:
                mission_date = dateutil_parse(date_str).date()
            else:
                mission_date = current_date.date()
            naive_datetime = datetime.combine(
                mission_date,
                datetime.strptime(f"{hours:02d}:{minutes:02d}", "%H:%M").time()
            )
            local_datetime = target_tz.localize(naive_datetime)
            return local_datetime.astimezone(timezone.utc)
        except Exception as e:
            logger.error(f"Error parsing time: {e}")
            return None
            
    async def validate_role_assignment(
        self,
        member: discord.Member,
        ship: str,
        role: str
    ) -> Tuple[bool, Optional[str]]:
        if not self.profile_cog:
            return True, None
        profile = await self.profile_cog.get_profile(member.id)
        if not profile:
            return True, None
        mission_role = SCMissionRole(
            member_id=member.id,
            ship_name=ship,
            station=StationRole(role)
        )
        can_assign, reason = mission_role.can_assign(profile)
        return can_assign, reason

    async def add_participant(
        self,
        mission_id: str,
        member: discord.Member,
        ship: str,
        role: str
    ) -> tuple[bool, Optional[str]]:
        try:
            can_assign, reason = await self.validate_role_assignment(member, ship, role)
            if not can_assign:
                return False, reason
            mission = self.missions.get(mission_id)
            if not mission:
                return False, "Mission not found"
            success = mission.add_participant(member.id, ship, role)
            if not success:
                return False, "Failed to add participant"
            if self.profile_cog:
                await self.profile_cog.sync_manager.queue_update(
                    ProfileEvent(
                        event_type=ProfileEventType.MISSION_JOIN,
                        member_id=member.id,
                        timestamp=datetime.now(timezone.utc),
                        data={
                            'mission_id': mission_id,
                            'ship': ship,
                            'role': role
                        }
                    )
                )
            return True, None
        except Exception as e:
            logger.error(f"Error adding participant: {e}")
            return False, str(e)

    async def create_voice_channel(
        self,
        guild: discord.Guild,
        mission_name: str
    ) -> Optional[discord.VoiceChannel]:
        try:
            category = self.bot.get_channel(VOICE_OPERATIONS_CHANNEL_ID)
            if isinstance(category, discord.CategoryChannel):
                return await category.create_voice_channel(
                    name=f"🎯│{mission_name}",
                    reason=f"Mission voice channel for {mission_name}"
                )
        except Exception as e:
            logger.error(f"Failed to create voice channel: {e}")
        return None

    async def create_scheduled_event(self, guild: discord.Guild, mission: Mission):
        try:
            if guild and mission.voice_channel_id:
                voice_channel = self.bot.get_channel(mission.voice_channel_id)
                event = await guild.create_scheduled_event(
                    name=mission.name,
                    description=mission.description,
                    start_time=mission.start_time,
                    end_time=(
                        mission.start_time + timedelta(minutes=mission.estimated_duration)
                        if mission.estimated_duration else None
                    ),
                    channel=voice_channel,
                    entity_type=discord.EntityType.voice,
                    privacy_level=discord.PrivacyLevel.guild_only
                )
                mission.event_id = event.id
                self.save_missions()
        except Exception as e:
            logger.error(f"Failed to create scheduled event: {e}")


    @app_commands.command(
        name="update_mission_status",
        description="Update the status of an existing mission"
    )
    @app_commands.describe(
        mission_id="The ID of the mission to update",
        status="The new status for the mission"
    )
    @app_commands.autocomplete(mission_id=mission_id_autocomplete)
    @app_commands.autocomplete(status=mission_status_autocomplete)
    async def update_mission_status(self, interaction: discord.Interaction, mission_id: str, status: str):
        """
        Update the status of a mission.
        Only the mission leader or an administrator can update the mission status.
        """
        await interaction.response.defer(ephemeral=True)
        
        # Look up the mission by its mission_id.
        mission = self.missions.get(mission_id)
        if not mission:
            await interaction.followup.send(f"❌ Mission with ID `{mission_id}` not found.", ephemeral=True)
            return

        # Convert the provided status string to a MissionStatus enum member.
        try:
            new_status = MissionStatus[status.upper()]
        except KeyError:
            await interaction.followup.send(f"❌ Invalid status: `{status}`. Please choose a valid status.", ephemeral=True)
            return

        # Check permissions: only the mission leader or an administrator can update.
        if interaction.user.id != mission.leader_id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You do not have permission to update this mission's status.", ephemeral=True)
            return

        old_status = mission.status
        mission.status = new_status
        mission.add_history_entry("update_status", interaction.user.id, f"Status changed from {old_status.name} to {new_status.name}")
        
        # Save the updated mission data.
        self.save_missions()
        
        # Update the mission view so the changes are reflected.
        await self.update_mission_view(mission)
        
        await interaction.followup.send(f"✅ Mission status updated from `{old_status.name}` to `{new_status.name}`.", ephemeral=True)

    @app_commands.command(
        name="edit_mission",
        description="Edit mission details"
    )
    @app_commands.describe(
        mission_id="The ID of the mission to edit",
        name="New mission name (optional)",
        description="New mission description (optional)",
        time="New time (e.g., 3:00 PM, 15:00) (optional)",
        timezone="Timezone for the new time (optional)",
        date="New date (MM/DD/YYYY or YYYY-MM-DD) (optional)",
        anticipated_earnings="New expected earnings (optional)",
        duration="New estimated duration in minutes (optional)"
    )
    @app_commands.autocomplete(mission_id=mission_id_autocomplete)
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    @app_commands.autocomplete(time=time_autocomplete)
    @app_commands.autocomplete(date=date_autocomplete)
    @app_commands.autocomplete(anticipated_earnings=earnings_autocomplete)
    @app_commands.autocomplete(duration=duration_autocomplete)
    async def edit_mission(
        self,
        interaction: discord.Interaction,
        mission_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        time: Optional[str] = None,
        timezone: Optional[str] = None,
        date: Optional[str] = None,
        anticipated_earnings: Optional[int] = None,
        duration: Optional[int] = None
    ):
        """Edit mission details with a more comprehensive command that includes autocomplete"""
        await interaction.response.defer(ephemeral=True)
        
        # Find the mission
        mission = self.missions.get(mission_id)
        if not mission:
            await interaction.followup.send(f"❌ Mission with ID `{mission_id}` not found.", ephemeral=True)
            return
            
        # Check permissions
        if interaction.user.id != mission.leader_id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ You don't have permission to edit this mission.", ephemeral=True)
            return
            
        # Track what was changed
        changes = []
        
        # Update name if provided
        if name:
            old_name = mission.name
            mission.name = name
            changes.append(f"Name: '{old_name}' → '{name}'")
            
        # Update description if provided
        if description:
            old_desc = mission.description
            mission.description = description
            mission.objectives = utils.parse_objectives(description)
            changes.append("Description updated")
            
        # Update time if provided
        if time and timezone:
            try:
                new_datetime = await self.parse_mission_time(time, timezone, date)
                if new_datetime:
                    old_time = mission.start_time
                    mission.start_time = new_datetime
                    changes.append(f"Time: <t:{int(old_time.timestamp())}:f> → <t:{int(new_datetime.timestamp())}:f>")
            except Exception as e:
                await interaction.followup.send(f"❌ Error updating time: {e}", ephemeral=True)
                return
                
        # Update earnings if provided
        if anticipated_earnings is not None:
            old_earnings = mission.anticipated_earnings
            mission.anticipated_earnings = anticipated_earnings
            changes.append(f"Anticipated earnings: {old_earnings:,} → {anticipated_earnings:,} aUEC")
            
        # Update duration if provided
        if duration is not None:
            old_duration = mission.estimated_duration
            mission.estimated_duration = duration
            changes.append(f"Estimated duration: {old_duration or 'unknown'} → {duration} minutes")
            
        # If no changes were made
        if not changes:
            await interaction.followup.send("No changes were made to the mission.", ephemeral=True)
            return
            
        # Save changes
        mission.add_history_entry(
            "edit_mission",
            interaction.user.id,
            f"Edited mission details: {', '.join(changes)}"
        )
        self.save_missions()
        
        # Update scheduled event if it exists
        if mission.event_id and (name or description or time or duration):
            guild = interaction.guild
            try:
                event = await guild.fetch_scheduled_event(mission.event_id)
                await event.edit(
                    name=mission.name if name else event.name,
                    description=mission.description if description else event.description,
                    start_time=mission.start_time if time else event.start_time,
                    end_time=(
                        mission.start_time + timedelta(minutes=mission.estimated_duration)
                        if duration and mission.estimated_duration else event.end_time
                    )
                )
            except Exception as e:
                logger.error(f"Failed to update scheduled event: {e}")
        
        # Update mission view
        await self.update_mission_view(mission)
        
        # Notify leader
        await interaction.followup.send(
            f"✅ Mission successfully updated!\n" + "\n".join([f"- {change}" for change in changes]),
            ephemeral=True
        )
        
        # Notify participants if significant changes
        if time or date or name:
            channel = self.bot.get_channel(mission.channel_id)
            if channel:
                mentions = []
                for uid in mission.participants:
                    if uid != interaction.user.id:  # Don't mention the editor
                        member = interaction.guild.get_member(uid)
                        if member:
                            mentions.append(member.mention)
                
                if mentions:
                    notify_embed = discord.Embed(
                        title=f"Mission Updated: {mission.name}",
                        description=f"The mission has been updated by {interaction.user.mention}.",
                        color=discord.Color.blue()
                    )
                    
                    for change in changes:
                        if "Time" in change or "Name" in change:
                            notify_embed.add_field(name="Change", value=change, inline=False)
                    
                    await channel.send(
                        f"ℹ️ **MISSION UPDATED** ℹ️\n{' '.join(mentions)}",
                        embed=notify_embed
                    )

    @app_commands.command(name="list_missions", description="List all active missions")
    @app_commands.describe(
        status="Filter missions by status (optional)",
        show_all="Show all missions including completed and cancelled ones"
    )
    @app_commands.autocomplete(status=mission_status_autocomplete)
    async def list_missions(
        self, 
        interaction: discord.Interaction,
        status: Optional[str] = None,
        show_all: Optional[bool] = False
    ):
        """List missions with filtering options using autocomplete for status"""
        await interaction.response.defer(ephemeral=True)
        
        # Filter missions by status if provided
        filtered_missions = []
        for mission in self.missions.values():
            # Skip completed/cancelled missions unless show_all is True
            if not show_all and mission.status in [MissionStatus.COMPLETED, MissionStatus.CANCELLED]:
                continue
                
            # Apply status filter if provided
            if status:
                try:
                    status_enum = MissionStatus[status.upper()]
                    if mission.status == status_enum:
                        filtered_missions.append(mission)
                except KeyError:
                    # Invalid status, ignore filter
                    filtered_missions.append(mission)
            else:
                filtered_missions.append(mission)
                
        # Sort missions by start time
        filtered_missions.sort(key=lambda m: m.start_time)
        
        # Create embed
        embed = discord.Embed(
            title="Mission List",
            description=f"Found {len(filtered_missions)} mission(s)",
            color=discord.Color.blue()
        )
        
        # Add mission entries
        for mission in filtered_missions[:25]:  # Limit to 25 missions to avoid hitting embed limits
            status_emoji = {
                MissionStatus.RECRUITING: "🔍",
                MissionStatus.READY: "✅",
                MissionStatus.IN_PROGRESS: "🚀",
                MissionStatus.COMPLETED: "🏆",
                MissionStatus.CANCELLED: "❌"
            }.get(mission.status, "❓")
            
            # Create field with mission details
            field_value = (
                f"**Type:** {mission.mission_type.value}\n"
                f"**Start:** <t:{int(mission.start_time.timestamp())}:R>\n"
                f"**Participants:** {len(mission.participants)}/{mission.max_participants or '∞'}\n"
                f"**ID:** `{mission.mission_id[:8]}`"
            )
            
            embed.add_field(
                name=f"{status_emoji} {mission.name} ({mission.status.value})",
                value=field_value,
                inline=False
            )
            
        # Add note if some missions were omitted
        if len(filtered_missions) > 25:
            embed.set_footer(text=f"Showing 25/{len(filtered_missions)} missions. Use filters to narrow down results.")
            
        await interaction.followup.send(embed=embed, ephemeral=True)

    # Method to update mission view to use interactive components
    async def update_mission_view(self, mission: Mission):
        """Update the mission embed with interactive components"""
        channel = self.bot.get_channel(mission.channel_id)
        if channel:
            try:
                message = await channel.fetch_message(mission.message_id)
                view = await create_interactive_mission_view(self, mission, mission.leader_id)
                await message.edit(embed=mission.to_embed(self.bot), view=view)
            except Exception as e:
                logger.error(f"Failed to update mission view: {e}")

# Replace the old MissionView class
class MissionView(discord.ui.View):
    """Legacy class maintained for compatibility"""
    def __init__(self, cog: MissionCog, mission: Mission):
        super().__init__(timeout=None)
        self.cog = cog
        self.mission = mission
        # This is now just a wrapper for InteractiveMissionView


async def setup(bot: commands.Bot):
    """Add persistent view handlers for mission interactions"""
    # First register the cog
    cog = MissionCog(bot)
    await bot.add_cog(cog)
    
    # Now register persistent view handlers for existing missions
    for mission_id, mission in cog.missions.items():
        if mission.message_id and mission.channel_id:
            view = await create_interactive_mission_view(cog, mission)
            # Add the view to Discord's persistent views
            bot.add_view(view, message_id=mission.message_id)