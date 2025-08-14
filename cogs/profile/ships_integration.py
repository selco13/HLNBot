"""Integration methods for profile cog to work with ships registry."""

import discord
import logging
from typing import List, Optional

logger = logging.getLogger('profile.ships_integration')

class ShipIntegrationMethods:
    """Methods for integrating profile system with ship registry."""
    
    async def get_flight_group_members(self, flight_group_name: str) -> List[discord.Member]:
        """
        Get all members assigned to a flight group.
        
        This method is called by the ships cog to display member information.
        
        Args:
            flight_group_name: Name of the flight group
            
        Returns:
            List of discord.Member objects
        """
        try:
            # Import needed constants
            import os
            DOC_ID = os.getenv("DOC_ID")
            TABLE_ID = os.getenv("TABLE_ID") or os.getenv("PROFILE_TABLE_ID")
            FIELD_FLIGHT_GROUP = "Flight Group"  # Use column name instead of ID for flexibility
            
            # Query for members assigned to this flight group
            query = f'"{FIELD_FLIGHT_GROUP}":"{flight_group_name}"'
            
            rows = await self.coda_client.get_rows(
                DOC_ID,
                TABLE_ID,
                query=query
            )
            
            # Extract member IDs and get member objects
            members = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = self.bot.get_guild(int(self.GUILD_ID)).get_member(int(discord_id))
                        if member:
                            members.append(member)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            return members
            
        except Exception as e:
            logger.error(f"Error getting flight group members: {e}")
            return []
            
    async def get_squadron_members(self, squadron_name: str) -> List[discord.Member]:
        """
        Get all members assigned to a squadron.
        
        This method is called by the ships cog to display member information.
        
        Args:
            squadron_name: Name of the squadron
            
        Returns:
            List of discord.Member objects
        """
        try:
            # Import needed constants
            import os
            DOC_ID = os.getenv("DOC_ID")
            TABLE_ID = os.getenv("TABLE_ID") or os.getenv("PROFILE_TABLE_ID")
            FIELD_SQUADRON = "Squadron"  # Use column name instead of ID for flexibility
            
            # Query for members assigned to this squadron
            query = f'"{FIELD_SQUADRON}":"{squadron_name}"'
            
            rows = await self.coda_client.get_rows(
                DOC_ID,
                TABLE_ID,
                query=query
            )
            
            # Extract member IDs and get member objects
            members = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = self.bot.get_guild(int(self.GUILD_ID)).get_member(int(discord_id))
                        if member:
                            members.append(member)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            return members
            
        except Exception as e:
            logger.error(f"Error getting squadron members: {e}")
            return []
            
    async def update_member_assignment(
        self,
        member: discord.Member,
        flight_group: Optional[str] = None,
        squadron: Optional[str] = None,
        position: Optional[str] = None
    ) -> bool:
        """
        Update a member's flight group and squadron assignment.
        
        Args:
            member: Discord member
            flight_group: Flight group name (None to remove)
            squadron: Squadron name (None to remove)
            position: Position in flight group (None to remove)
            
        Returns:
            bool: Success or failure
        """
        try:
            updates = {}
            
            # Add flight group if provided
            if flight_group is not None:
                updates['Flight Group'] = flight_group
                
            # Add squadron if provided
            if squadron is not None:
                updates['Squadron'] = squadron
                
            # Add position to ship assignment if provided
            if position is not None:
                # Get current ship assignment
                member_row = await self.get_member_row(member.id)
                if member_row:
                    ship_assignment = member_row.get('values', {}).get('Ship Assignment', '')
                    
                    # Add position in parentheses if there's a ship assignment
                    if ship_assignment and ship_assignment != 'Unassigned':
                        # Remove any existing position
                        if '(' in ship_assignment:
                            ship_assignment = ship_assignment.split('(')[0].strip()
                            
                        # Add new position
                        updates['Ship Assignment'] = f"{ship_assignment} ({position})"
            
            # Only proceed if there are updates to make
            if not updates:
                return True
                
            # Update the profile
            success = await self.update_profile(
                member,
                updates,
                f"Updated flight assignment"
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating member assignment: {e}")
            return False