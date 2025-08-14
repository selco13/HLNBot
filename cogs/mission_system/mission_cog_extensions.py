"""Updates to the Mission class to support fleet assignments."""

from typing import Dict, List, Optional, Set, Any, Union
import discord
from discord.ext import commands
from .shared import MissionType, MissionStatus, MissionDifficulty, Participant
import uuid
from datetime import datetime, timezone
import pytz
import logging
import os

logger = logging.getLogger('missions')

class FleetAssignment:
    """Tracks assignment of fleet assets to a mission."""
    
    def __init__(self):
        self.assigned_ships: Set[str] = set()  # Registry numbers
        self.assigned_flight_groups: Set[str] = set()  # Flight group IDs/names
        self.assigned_squadrons: Set[str] = set()  # Squadron IDs/names
        
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'assigned_ships': list(self.assigned_ships),
            'assigned_flight_groups': list(self.assigned_flight_groups),
            'assigned_squadrons': list(self.assigned_squadrons)
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'FleetAssignment':
        """Create from dictionary data."""
        instance = cls()
        instance.assigned_ships = set(data.get('assigned_ships', []))
        instance.assigned_flight_groups = set(data.get('assigned_flight_groups', []))
        instance.assigned_squadrons = set(data.get('assigned_squadrons', []))
        return instance


class Mission:
    """Enhanced mission class with timezone-aware datetime handling and fleet assignment support."""
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
        fleet_assignment: Optional[FleetAssignment] = None,
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
        self.objectives = []
        self.rsvp = None  # This will be initialized separately
        self.template_id = template_id
        self.briefing = briefing
        self.history: List[Dict[str, Any]] = []
        self.fleet_assignment = fleet_assignment or FleetAssignment()

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
            'fleet_assignment': self.fleet_assignment.to_dict() if self.fleet_assignment else {},
        }
        
        # Include RSVP data if available
        if hasattr(self, 'rsvp') and self.rsvp is not None:
            base_dict['rsvp'] = {
                'responses': {
                    str(mid): resp.__dict__ for mid, resp in self.rsvp.responses.items()
                },
                'confirmed': self.rsvp.confirmed,
                'standby': self.rsvp.standby,
                'declined': self.rsvp.declined
            }
            
        return base_dict

    @classmethod
    def from_dict(cls, data: dict) -> 'Mission':
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
            
            # Extract fields that aren't part of __init__
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
                'briefing': mission_data.pop('briefing', ''),
                'fleet_assignment': mission_data.pop('fleet_assignment', {})
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
                
            # Process fleet_assignment
            fleet_assignment = None
            if post_fields['fleet_assignment']:
                fleet_assignment = FleetAssignment.from_dict(post_fields['fleet_assignment'])
            mission_data['fleet_assignment'] = fleet_assignment
                
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
            
            # Create RSVP object if needed
            from .mission_rsvp import MissionRSVP, RSVPResponse
            mission.rsvp = MissionRSVP()
            
            # Process RSVP data if available
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
        """Convert mission to Discord embed with improved formatting and fleet assignments."""
        from .mission_fleet_integration import format_fleet_assignments_for_embed
        from .shared import MissionSystemUtilities as utils
        
        guild = bot.get_guild(int(os.getenv('GUILD_ID', 0)))
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
            
        # Add fleet assignments if available
        fleet_assignments = format_fleet_assignments_for_embed(self)
        if fleet_assignments:
            embed.add_field(name="Fleet Assets", value=fleet_assignments, inline=False)
            
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


class MissionCogExtensions:
    """
    Extension methods for the MissionCog class to support fleet features.
    This class is meant to be used as a mixin or utility class for MissionCog.
    """
    
    @staticmethod
    async def assign_fleet_to_mission(cog, mission_id: str, fleet_assignment: FleetAssignment) -> bool:
        """
        Assign fleet assets to a mission.
        
        Args:
            cog: The MissionCog instance
            mission_id: The ID of the mission to assign fleet to
            fleet_assignment: The FleetAssignment object containing the assets to assign
            
        Returns:
            bool: True if successful, False otherwise
        """
        mission = cog.missions.get(mission_id)
        if not mission:
            logger.error(f"Mission not found: {mission_id}")
            return False
            
        # Ensure mission has fleet_assignment attribute
        if not hasattr(mission, 'fleet_assignment'):
            mission.fleet_assignment = FleetAssignment()
            
        # Update fleet assignments
        mission.fleet_assignment.assigned_ships.update(fleet_assignment.assigned_ships)
        mission.fleet_assignment.assigned_flight_groups.update(fleet_assignment.assigned_flight_groups)
        mission.fleet_assignment.assigned_squadrons.update(fleet_assignment.assigned_squadrons)
        
        # Save mission data
        cog.save_missions()
        
        # Add history entry
        mission.add_history_entry(
            "fleet_assignment",
            0,  # System action
            f"Assigned fleet assets: {len(fleet_assignment.assigned_ships)} ships, "
            f"{len(fleet_assignment.assigned_flight_groups)} flight groups, "
            f"{len(fleet_assignment.assigned_squadrons)} squadrons"
        )
        
        # Update mission view
        await cog.update_mission_view(mission)
        
        return True
        
    @staticmethod
    async def remove_fleet_from_mission(cog, mission_id: str, fleet_assignment: FleetAssignment) -> bool:
        """
        Remove fleet assets from a mission.
        
        Args:
            cog: The MissionCog instance
            mission_id: The ID of the mission to remove fleet from
            fleet_assignment: The FleetAssignment object containing the assets to remove
            
        Returns:
            bool: True if successful, False otherwise
        """
        mission = cog.missions.get(mission_id)
        if not mission:
            logger.error(f"Mission not found: {mission_id}")
            return False
            
        # Ensure mission has fleet_assignment attribute
        if not hasattr(mission, 'fleet_assignment'):
            mission.fleet_assignment = FleetAssignment()
            return True  # Nothing to remove
            
        # Remove fleet assignments
        mission.fleet_assignment.assigned_ships -= fleet_assignment.assigned_ships
        mission.fleet_assignment.assigned_flight_groups -= fleet_assignment.assigned_flight_groups
        mission.fleet_assignment.assigned_squadrons -= fleet_assignment.assigned_squadrons
        
        # Save mission data
        cog.save_missions()
        
        # Add history entry
        mission.add_history_entry(
            "fleet_removal",
            0,  # System action
            f"Removed fleet assets: {len(fleet_assignment.assigned_ships)} ships, "
            f"{len(fleet_assignment.assigned_flight_groups)} flight groups, "
            f"{len(fleet_assignment.assigned_squadrons)} squadrons"
        )
        
        # Update mission view
        await cog.update_mission_view(mission)
        
        return True
        
    @staticmethod
    def get_missions_with_fleet_asset(cog, asset_type: str, asset_id: str) -> List[Mission]:
        """
        Get all missions that have a specific fleet asset assigned.
        
        Args:
            cog: The MissionCog instance
            asset_type: The type of asset ('ship', 'flight_group', or 'squadron')
            asset_id: The ID or name of the asset
            
        Returns:
            List[Mission]: List of missions with the asset assigned
        """
        missions = []
        
        for mission in cog.missions.values():
            if not hasattr(mission, 'fleet_assignment'):
                continue
                
            if asset_type == 'ship' and asset_id in mission.fleet_assignment.assigned_ships:
                missions.append(mission)
            elif asset_type == 'flight_group' and asset_id in mission.fleet_assignment.assigned_flight_groups:
                missions.append(mission)
            elif asset_type == 'squadron' and asset_id in mission.fleet_assignment.assigned_squadrons:
                missions.append(mission)
                
        return missions