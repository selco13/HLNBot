"""Timeline utilities for career visualization."""

import discord
import logging
import json
import io
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger('profile.timeline')

async def generate_career_timeline_data(member: discord.Member, member_data: dict) -> Dict[str, Any]:
    """
    Generate data structure for career timeline visualization.
    
    Args:
        member: Discord member
        member_data: Profile data from database
        
    Returns:
        Dictionary with timeline data
    """
    try:
        from .utils import parse_list_field
        
        values = member_data.get('values', {})
        
        # Base profile data
        profile_data = {
            "name": member.display_name,
            "joinDate": values.get('Join Date', ''),
            "initialRank": "Crewman Recruit",
            "currentRank": values.get('Rank', 'Crewman Recruit'),
            "fleetWing": values.get('Fleet Wing', values.get('Division', 'Unknown')),
            "awards": [],
            "completedMissions": [],
            "certifications": [],
            "promotions": []
        }
        
        # Parse awards
        awards_raw = values.get('Awards', [])
        profile_data["awards"] = parse_list_field(awards_raw)
        
        # Parse missions
        missions_raw = values.get('Completed Missions', [])
        profile_data["completedMissions"] = parse_list_field(missions_raw)
        
        # Parse certifications
        certifications_raw = values.get('Certifications', [])
        profile_data["certifications"] = parse_list_field(certifications_raw)
        
        # Generate sample promotion data (in a real setup, you'd track this)
        join_date = values.get('Join Date')
        if join_date:
            # Generate some plausible promotion dates based on join date
            try:
                join_dt = datetime.strptime(join_date, "%Y-%m-%d")
                
                # Add some sample promotions based on join date
                # In production, you would store real promotion history
                profile_data["promotions"] = []
                
                # Only add promotion history if they've been in for a while
                current_date = datetime.now()
                days_since_join = (current_date - join_dt).days
                
                if days_since_join > 30:
                    profile_data["promotions"].append({
                        "date": (join_dt + timedelta(days=30)).strftime("%Y-%m-%d"),
                        "rank": "Crewman Apprentice", 
                        "citation": "Initial training completion"
                    })
                    
                if days_since_join > 90:
                    profile_data["promotions"].append({
                        "date": (join_dt + timedelta(days=90)).strftime("%Y-%m-%d"),
                        "rank": "Crewman",
                        "citation": "Successful completion of probationary period"
                    })
                    
                # Add current rank as final promotion if above Crewman
                current_rank = values.get('Rank', 'Crewman Recruit')
                if current_rank not in ['Crewman Recruit', 'Crewman Apprentice', 'Crewman']:
                    profile_data["promotions"].append({
                        "date": (join_dt + timedelta(days=min(days_since_join - 15, 180))).strftime("%Y-%m-%d"),
                        "rank": current_rank,
                        "citation": "Exemplary service and dedication"
                    })
            except Exception as date_err:
                logger.error(f"Error processing dates: {date_err}")
        
        return profile_data
        
    except Exception as e:
        logger.error(f"Error generating timeline data: {e}")
        return {}

class CareerTimelineView(discord.ui.View):
    """View for displaying the career timeline."""
    
    def __init__(self, member: discord.Member, timeline_data: Dict[str, Any]):
        super().__init__(timeout=300)
        self.member = member
        self.timeline_data = timeline_data
        
    @discord.ui.button(label="View Timeline", style=discord.ButtonStyle.primary)
    async def view_timeline(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View the career timeline in a dedicated message."""
        await interaction.response.defer(thinking=True)
        
        try:
            # Format the timeline data into a rich embed
            embed = discord.Embed(
                title=f"Career Timeline for {self.member.display_name}",
                description="Major events in chronological order",
                color=discord.Color.blue()
            )
            
            embed.set_thumbnail(url=self.member.display_avatar.url)
            
            # Add enlistment if available
            if self.timeline_data.get("joinDate"):
                embed.add_field(
                    name=f"📆 Enlisted ({self.timeline_data['joinDate']})",
                    value=f"Joined as {self.timeline_data['initialRank']}",
                    inline=False
                )
            
            # Add promotions
            for promotion in self.timeline_data.get("promotions", []):
                embed.add_field(
                    name=f"⭐ Promotion to {promotion['rank']} ({promotion['date']})",
                    value=promotion['citation'],
                    inline=False
                )
                
            # Add most significant awards (limit to 3)
            awards = self.timeline_data.get("awards", [])
            if awards:
                for i, award in enumerate(awards[:3]):
                    parts = award.split(" - ")
                    award_name = parts[0]
                    citation = parts[1] if len(parts) > 1 else "No citation provided"
                    date = parts[2] if len(parts) > 2 else "Unknown date"
                    
                    embed.add_field(
                        name=f"🏅 Awarded {award_name} ({date})",
                        value=citation,
                        inline=False
                    )
                
                # If more awards, add a count
                if len(awards) > 3:
                    embed.add_field(
                        name="Additional Awards",
                        value=f"And {len(awards) - 3} more awards not shown",
                        inline=False
                    )
                    
            # Add recent missions (limit to 3)
            missions = self.timeline_data.get("completedMissions", [])
            if missions:
                for i, mission in enumerate(missions[:3]):
                    parts = mission.split(" - ")
                    mission_name = parts[0]
                    details = " - ".join(parts[1:]) if len(parts) > 1 else "No details provided"
                    
                    embed.add_field(
                        name=f"🚀 Mission: {mission_name}",
                        value=details,
                        inline=False
                    )
                    
                # If more missions, add a count
                if len(missions) > 3:
                    embed.add_field(
                        name="Additional Missions",
                        value=f"And {len(missions) - 3} more missions not shown",
                        inline=False
                    )
            
            embed.set_footer(text="For interactive timeline, use the web dashboard")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error displaying timeline: {e}")
            await interaction.followup.send("Error displaying timeline.", ephemeral=True)