"""Fleet integration for profile system."""

import discord
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger('profile.fleet')

class FleetIntegration:
    """Fleet system integration for profiles."""
    
    def __init__(self, cog):
        self.cog = cog
        
    async def assign_ship(self, member: discord.Member, ship_name: str, position: str = None) -> bool:
        """
        Assign a member to a ship with optional position/role.
        
        Args:
            member: The Discord member
            ship_name: Name of the ship
            position: Position on the ship (optional)
            
        Returns:
            bool: Success or failure
        """
        try:
            # Get the member's profile
            member_row = await self.cog.get_member_row(member.id)
            if not member_row:
                logger.error(f"No profile found for {member.id}")
                return False
                
            # Format ship assignment with position if provided
            if position:
                ship_assignment = f"{ship_name} ({position})"
            else:
                ship_assignment = ship_name
                
            # Update the profile
            success = await self.cog.update_profile(
                member,
                {'Ship Assignment': ship_assignment},
                f"Ship assignment updated to {ship_name}"
            )
            
            if success:
                # Try to add ship-specific role if it exists
                ship_role_name = f"Ship: {ship_name}"
                ship_role = discord.utils.get(member.guild.roles, name=ship_role_name)
                
                if ship_role:
                    await member.add_roles(ship_role, reason=f"Assigned to {ship_name}")
                    
                # If position is provided, try to add position role
                if position:
                    position_role_name = f"{position}"
                    position_role = discord.utils.get(member.guild.roles, name=position_role_name)
                    
                    if position_role:
                        await member.add_roles(position_role, reason=f"Assigned as {position}")
                        
                logger.info(f"Successfully assigned {member.id} to {ship_name}")
                return True
            else:
                logger.error(f"Failed to update profile for {member.id}")
                return False
                
        except Exception as e:
            logger.error(f"Error in assign_ship: {e}")
            return False
            
    async def unassign_ship(self, member: discord.Member) -> bool:
        """
        Remove a member from their current ship assignment.
        
        Args:
            member: The Discord member
            
        Returns:
            bool: Success or failure
        """
        try:
            # Get the member's profile
            member_row = await self.cog.get_member_row(member.id)
            if not member_row:
                logger.error(f"No profile found for {member.id}")
                return False
                
            # Get current ship assignment
            current_ship = member_row.get('values', {}).get('Ship Assignment', '')
            
            if not current_ship or current_ship == 'Unassigned':
                logger.info(f"Member {member.id} is already unassigned")
                return True
                
            # Update the profile
            success = await self.cog.update_profile(
                member,
                {'Ship Assignment': 'Unassigned'},
                f"Removed from ship assignment: {current_ship}"
            )
            
            if success:
                # Remove ship-related roles
                ship_roles = [role for role in member.roles if role.name.startswith("Ship:")]
                position_roles = [role for role in member.roles if role.name in 
                                 ["Captain", "XO", "Pilot", "Engineer", "Marine", "Medic"]]
                
                if ship_roles or position_roles:
                    await member.remove_roles(*ship_roles, *position_roles, 
                                           reason="Removed from ship assignment")
                    
                logger.info(f"Successfully unassigned {member.id} from ship")
                return True
            else:
                logger.error(f"Failed to update profile for {member.id}")
                return False
                
        except Exception as e:
            logger.error(f"Error in unassign_ship: {e}")
            return False
            
    async def get_ship_crew(self, ship_name: str) -> List[Dict[str, Any]]:
        """
        Get all crew members assigned to a specific ship.
        
        Args:
            ship_name: Name of the ship
            
        Returns:
            List of crew member data
        """
        try:
            # Import constants here to avoid circular imports
            import os
            DOC_ID = os.getenv("DOC_ID")
            TABLE_ID = os.getenv("TABLE_ID")
            FIELD_SHIP_ASSIGNMENT = "Ship Assignment"  # Use column name
            
            # Build query for Coda
            query = f'"{FIELD_SHIP_ASSIGNMENT}" ~* "{ship_name}"'
            
            # Get all matching rows
            rows = await self.cog.coda_client.get_rows(
                DOC_ID,
                TABLE_ID,
                query=query
            )
            
            if not rows:
                logger.info(f"No crew members found for ship: {ship_name}")
                return []
                
            # Parse crew data
            crew_data = []
            for row in rows:
                values = row.get('values', {})
                discord_id = values.get('Discord User ID')
                
                if not discord_id:
                    continue
                    
                # Extract position from ship assignment if available
                ship_assignment = values.get('Ship Assignment', '')
                position = None
                
                if '(' in ship_assignment and ')' in ship_assignment:
                    position = ship_assignment.split('(')[1].split(')')[0]
                    
                crew_member = {
                    'discord_id': discord_id,
                    'name': values.get('Discord Username', 'Unknown'),
                    'rank': values.get('Rank', 'N/A'),
                    'fleet_wing': values.get('Fleet Wing', values.get('Division', 'N/A')),
                    'specialization': values.get('Specialization', 'N/A'),
                    'position': position
                }
                
                crew_data.append(crew_member)
                
            return crew_data
            
        except Exception as e:
            logger.error(f"Error in get_ship_crew: {e}")
            return []
            
    async def generate_ship_roster_embed(self, guild: discord.Guild, ship_name: str) -> discord.Embed:
        """
        Generate an embed showing the ship's crew roster.
        
        Args:
            guild: Discord guild
            ship_name: Name of the ship
            
        Returns:
            Discord embed with ship roster
        """
        try:
            # Get ship crew
            crew_data = await self.get_ship_crew(ship_name)
            
            if not crew_data:
                embed = discord.Embed(
                    title=f"Ship Roster: {ship_name}",
                    description="No crew members assigned to this ship.",
                    color=discord.Color.blue()
                )
                return embed
                
            # Create embed
            embed = discord.Embed(
                title=f"Ship Roster: {ship_name}",
                description=f"Current crew: {len(crew_data)} members",
                color=discord.Color.blue()
            )
            
            # Get actual member objects
            leadership = []
            officers = []
            crew = []
            
            for data in crew_data:
                try:
                    member = guild.get_member(int(data['discord_id']))
                    if not member:
                        continue
                        
                    # Determine crew category
                    rank = data['rank'].lower()
                    position = data['position'].lower() if data['position'] else None
                    
                    if position in ['captain', 'commander', 'xo']:
                        leadership.append((member, data))
                    elif 'captain' in rank or 'commander' in rank or 'lieutenant' in rank:
                        officers.append((member, data))
                    else:
                        crew.append((member, data))
                except Exception as e:
                    logger.error(f"Error processing crew member: {e}")
                    continue
                    
            # Add leadership
            if leadership:
                leadership_text = "\n".join([
                    f"**{data['position'] or 'Commander'}:** {member.mention} ({data['rank']})"
                    for member, data in leadership
                ])
                embed.add_field(name="Leadership", value=leadership_text, inline=False)
                
            # Add officers
            if officers:
                officers_text = "\n".join([
                    f"**{data['position'] or data['specialization'] or 'Officer'}:** {member.mention} ({data['rank']})"
                    for member, data in officers
                ])
                embed.add_field(name="Officers", value=officers_text, inline=False)
                
            # Add crew
            if crew:
                crew_text = "\n".join([
                    f"**{data['position'] or data['specialization'] or 'Crew'}:** {member.mention} ({data['rank']})"
                    for member, data in crew
                ])
                embed.add_field(name="Crew", value=crew_text, inline=False)
                
            # Add footer
            embed.set_footer(text=f"Ship roster as of {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            
            return embed
            
        except Exception as e:
            logger.error(f"Error in generate_ship_roster_embed: {e}")
            
            # Return error embed
            embed = discord.Embed(
                title=f"Ship Roster: {ship_name}",
                description=f"Error generating ship roster: {str(e)}",
                color=discord.Color.red()
            )
            return embed

    async def get_fleet_wing_ships(self, fleet_wing: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all ships and crew assigned to a specific fleet wing.
        
        Args:
            fleet_wing: Name of the fleet wing
            
        Returns:
            Dictionary mapping ship names to crew lists
        """
        try:
            # First get all members in the fleet wing
            import os
            DOC_ID = os.getenv("DOC_ID")
            TABLE_ID = os.getenv("TABLE_ID")
            FIELD_FLEET_WING = "Fleet Wing"
            FIELD_DIVISION = "Division"
            
            # Check both fleet wing and division fields
            query = f'"{FIELD_FLEET_WING}":"{fleet_wing}" OR "{FIELD_DIVISION}":"{fleet_wing}"'
            
            # Hard-code division to fleet wing mapping for backward compatibility
            DIVISION_TO_FLEET_WING = {
                "Command Staff": "Command Staff",
                "HQ": "Fleet Command",
                "Tactical": "Navy Fleet",
                "Operations": "Industrial & Logistics Wing",
                "Support": "Support & Medical Fleet",
                "Non-Division": "Non-Fleet",
                "Ambassador": "Ambassador",
                "Associate": "Associate"
            }
            
            # For backward compatibility with old divisions
            for div, wing in DIVISION_TO_FLEET_WING.items():
                if wing == fleet_wing:
                    query += f' OR "{FIELD_DIVISION}":"{div}"'
                    
            # Get all matching rows
            rows = await self.cog.coda_client.get_rows(
                DOC_ID,
                TABLE_ID,
                query=query
            )
            
            if not rows:
                logger.info(f"No members found in fleet wing: {fleet_wing}")
                return {}
                
            # Group by ship
            ships = {}
            
            for row in rows:
                values = row.get('values', {})
                ship_assignment = values.get('Ship Assignment', '')
                
                if not ship_assignment or ship_assignment == 'Unassigned':
                    continue
                    
                # Extract base ship name
                if '(' in ship_assignment:
                    ship_name = ship_assignment.split('(')[0].strip()
                    position = ship_assignment.split('(')[1].split(')')[0].strip()
                else:
                    ship_name = ship_assignment.strip()
                    position = None
                    
                # Add to ships dictionary
                if ship_name not in ships:
                    ships[ship_name] = []
                    
                member_data = {
                    'discord_id': values.get('Discord User ID'),
                    'name': values.get('Discord Username', 'Unknown'),
                    'rank': values.get('Rank', 'N/A'),
                    'specialization': values.get('Specialization', 'N/A'),
                    'position': position
                }
                
                ships[ship_name].append(member_data)
                
            return ships
            
        except Exception as e:
            logger.error(f"Error in get_fleet_wing_ships: {e}")
            return {}