from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import discord

@dataclass
class RSVPResponse:
    member_id: int
    status: str
    timestamp: datetime
    ship_name: Optional[str] = None
    role: Optional[str] = None
    note: Optional[str] = None

class MissionRSVP:
    def __init__(self):
        self.responses: Dict[int, RSVPResponse] = {}
        self.confirmed: List[int] = []
        self.standby: List[int] = []
        self.declined: List[int] = []
        self.max_standby: int = 5

    async def add_response(
        self,
        member: discord.Member,
        status: str,
        ship_name: Optional[str] = None,
        role: Optional[str] = None,
        note: Optional[str] = None
    ) -> bool:
        """Add or update an RSVP response."""
        response = RSVPResponse(
            member_id=member.id,
            status=status,
            timestamp=datetime.now(),
            ship_name=ship_name,
            role=role,
            note=note
        )
        
        # Remove from previous lists if status changed
        self.confirmed = [m for m in self.confirmed if m != member.id]
        self.standby = [m for m in self.standby if m != member.id]
        self.declined = [m for m in self.declined if m != member.id]
        
        # Add to appropriate list
        if status == 'confirmed':
            self.confirmed.append(member.id)
        elif status == 'standby':
            if len(self.standby) < self.max_standby:
                self.standby.append(member.id)
            else:
                return False
        elif status == 'declined':
            self.declined.append(member.id)
            
        self.responses[member.id] = response
        return True

    def get_response(self, member_id: int) -> Optional[RSVPResponse]:
        """Get a member's RSVP response."""
        return self.responses.get(member_id)

    def to_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create an embed showing RSVP status."""
        embed = discord.Embed(
            title="Mission RSVP Status",
            color=discord.Color.blue()
        )
        
        # Confirmed participants
        confirmed_text = ""
        for member_id in self.confirmed:
            member = guild.get_member(member_id)
            response = self.responses[member_id]
            if member:
                confirmed_text += (
                    f"• {member.display_name} - {response.role or 'No role'} "
                    f"({response.ship_name or 'No ship'})\n"
                )
        embed.add_field(
            name=f"Confirmed ({len(self.confirmed)})",
            value=confirmed_text or "No confirmed participants",
            inline=False
        )
        
        # Standby list
        standby_text = ""
        for member_id in self.standby:
            member = guild.get_member(member_id)
            response = self.responses[member_id]
            if member:
                standby_text += f"• {member.display_name}"
                if response.note:
                    standby_text += f" - {response.note}"
                standby_text += "\n"
        embed.add_field(
            name=f"Standby ({len(self.standby)})",
            value=standby_text or "No standby participants",
            inline=False
        )
        
        return embed