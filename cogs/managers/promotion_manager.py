# cogs/managers/promotion_manager.py

import discord
import logging
import os
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone, timedelta

# Import constants from the constants module
from ..constants import (
    RANKS, RANK_NUMBERS, RANK_ABBREVIATIONS, 
    STANDARD_TO_DIVISION_RANK, DIVISION_TO_STANDARD_RANK,
    TIME_IN_GRADE, FLEET_COMPONENTS, DIVISION_CODES,
    DIVISION_TO_FLEET_WING
)

logger = logging.getLogger('promotion_manager')

class PromotionManager:
    """Manager class for handling member promotions with fleet-based structure support."""
    
    def __init__(self, bot):
        self.bot = bot
        
    async def promote_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        division: str = None,  # Keep for backward compatibility
        fleet_component: str = None,  # Add new parameter for fleet-based structure
        new_rank: str = None,
        specialization: str = None,
        override_time: bool = False
    ) -> bool:
        """
        Promote a member to a new rank.
        
        Args:
            interaction: Discord interaction
            member: The member to promote
            division: (Legacy) The division of the member
            fleet_component: The fleet component of the member
            new_rank: The new rank to assign
            specialization: Optional role specialization
            override_time: Whether to override time-in-grade requirements
            
        Returns:
            bool: Success or failure
        """
        try:
            # Use fleet_component if provided, otherwise fall back to division
            component = fleet_component or division
            if not component:
                logger.error(f"No fleet component or division provided for {member.name}")
                return False
                
            # Get current rank
            current_rank = self.get_member_standard_rank(member)
            
            # Check eligibility
            if not override_time:
                eligible, details = await self.check_promotion_eligibility(
                    member, current_rank, new_rank, override_time
                )
                
                if not eligible:
                    await interaction.followup.send(
                        f"❌ Member is not eligible for promotion: {details}",
                        ephemeral=True
                    )
                    return False
            
            # Update roles
            success = await self.update_member_roles(
                member, component, new_rank, specialization
            )
            
            if not success:
                return False
                
            # Update database record
            profile_cog = self.bot.get_cog('ProfileCog')
            if profile_cog:
                updates = {'Rank': new_rank}
                
                # Update fleet component and/or division
                if 'Fleet' in component or 'Wing' in component:
                    # It's a fleet component name
                    updates['Fleet Wing'] = component
                    # Also update the legacy division field if needed
                    for old_div, new_wing in DIVISION_TO_FLEET_WING.items():
                        if new_wing == component:
                            updates['Division'] = old_div
                            break
                else:
                    # It's a legacy division name
                    updates['Division'] = component
                    # Also update the Fleet Wing field
                    fleet_wing = DIVISION_TO_FLEET_WING.get(component, component)
                    updates['Fleet Wing'] = fleet_wing
                
                if specialization:
                    updates['Specialization'] = specialization
                    
                # Update rank date
                updates['Rank Date'] = datetime.now().strftime("%Y-%m-%d")
                
                success = await profile_cog.update_profile(
                    member,
                    updates,
                    f"Promoted from {current_rank} to {new_rank}"
                )
                
                if not success:
                    logger.error(f"Failed to update profile record for {member.name}")
                    # Continue anyway since we've already updated the roles
            
            # Update nickname
            await self.update_member_nickname(member, component, new_rank, specialization)
            
            return True
            
        except Exception as e:
            logger.error(f"Error in promote_member: {e}")
            return False
            
    def get_member_standard_rank(self, member: discord.Member) -> str:
        """
        Get the member's standard rank based on their roles.
        
        Args:
            member: Discord member
            
        Returns:
            str: The standard rank name or 'Recruit' if not found
        """
        # Check for rank roles in order (highest to lowest)
        for rank_name, _ in RANKS:
            role = discord.utils.get(member.roles, name=rank_name)
            if role:
                return rank_name
                
        # Check for specialized rank roles (e.g. division-specific roles)
        for role in member.roles:
            role_name = role.name.lower()
            
            # Check if this role matches a specialized rank
            for div_key, (std_rank, _, _) in DIVISION_TO_STANDARD_RANK.items():
                if role_name == div_key[2]:  # div_key[2] is the specialized rank name
                    return std_rank
        
        return 'Recruit'  # Default
        
    async def determine_next_rank(
        self,
        current_rank: str,
        fleet_component: str,
        specialization: str = None
    ) -> Optional[str]:
        """
        Determine the next rank in the progression.
        
        Args:
            current_rank: Current rank
            fleet_component: Fleet component or division
            specialization: Role specialization
            
        Returns:
            str: Next rank name or None if not determinable
        """
        try:
            # Find current rank in the rank list
            current_idx = -1
            for idx, (rank_name, _) in enumerate(RANKS):
                if rank_name.lower() == current_rank.lower():
                    current_idx = idx
                    break
                    
            if current_idx == -1:
                logger.warning(f"Could not find rank {current_rank} in rank list")
                return None
                
            # If it's the highest rank, there's no next rank
            if current_idx == 0:
                return None
                
            # Otherwise, return the next higher rank
            next_rank, _ = RANKS[current_idx - 1]
            return next_rank
            
        except Exception as e:
            logger.error(f"Error determining next rank: {e}")
            return None
            
    async def check_promotion_eligibility(
        self,
        member: discord.Member,
        current_rank: str,
        new_rank: str,
        override_time: bool = False
    ) -> Tuple[bool, str]:
        """
        Check if a member is eligible for promotion.
        
        Args:
            member: Discord member
            current_rank: Current rank
            new_rank: Proposed new rank
            override_time: Whether to override time requirements
            
        Returns:
            Tuple[bool, str]: (eligible, reason)
        """
        try:
            # Check if new rank is higher than current
            current_idx = -1
            new_idx = -1
            
            for idx, (rank_name, _) in enumerate(RANKS):
                if rank_name.lower() == current_rank.lower():
                    current_idx = idx
                if rank_name.lower() == new_rank.lower():
                    new_idx = idx
                    
            if current_idx == -1 or new_idx == -1:
                return False, "Invalid rank specified"
                
            # Lower index means higher rank (Admiral is 0)
            if new_idx >= current_idx:
                return False, f"{new_rank} is not a promotion from {current_rank}"
                
            # If more than one rank jump
            if current_idx - new_idx > 1:
                return False, f"Cannot skip ranks - must go through intermediate ranks"
                
            # If time override is set, skip time checks
            if override_time:
                return True, "Time-in-grade requirements overridden"
                
            # Check time-in-grade requirements
            profile_cog = self.bot.get_cog('ProfileCog')
            if profile_cog:
                member_row = await profile_cog.get_member_row(member.id)
                if member_row and 'values' in member_row:
                    values = member_row['values']
                    
                    # Check rank date
                    rank_date_str = values.get('Rank Date')
                    if not rank_date_str:
                        return False, "No rank date found"
                        
                    try:
                        rank_date = datetime.strptime(rank_date_str[:10], "%Y-%m-%d")  # Extract just the date portion
                        days_in_rank = (datetime.now() - rank_date).days
                        
                        # Get requirements
                        requirements = TIME_IN_GRADE.get(current_rank, {'days': 30, 'missions': 5})
                        required_days = requirements.get('days', 30)
                        required_missions = requirements.get('missions', 5)
                        
                        # Check days
                        if days_in_rank < required_days:
                            return False, f"Not enough time in current rank. Needs {required_days} days, has {days_in_rank}."
                            
                        # Check missions
                        mission_count = int(values.get('Mission Count', 0))
                        if mission_count < required_missions:
                            return False, f"Not enough missions completed. Needs {required_missions}, has {mission_count}."
                            
                        # All checks passed
                        return True, f"Eligible for promotion. {days_in_rank} days in rank, {mission_count} missions."
                    except Exception as e:
                        logger.error(f"Error checking promotion eligibility dates: {e}")
                        return False, f"Error checking dates: {str(e)}"
            
            # If we can't check the profile, assume eligible
            return True, "Eligibility could not be fully verified"
            
        except Exception as e:
            logger.error(f"Error checking promotion eligibility: {e}")
            return False, f"Error: {str(e)}"
            
    async def update_member_roles(
        self,
        member: discord.Member,
        fleet_component: str,
        new_rank: str,
        specialization: str = None
    ) -> bool:
        """
        Update a member's roles based on their new rank and fleet component.
        
        Args:
            member: Discord member
            fleet_component: Fleet component or division
            new_rank: New rank
            specialization: Optional role specialization
            
        Returns:
            bool: Success or failure
        """
        try:
            # Get current roles to remove
            to_remove = []
            
            # Remove all rank roles
            for rank_name, _ in RANKS:
                role = discord.utils.get(member.roles, name=rank_name)
                if role:
                    to_remove.append(role)
            
            # Add new rank role
            rank_role = discord.utils.get(member.guild.roles, name=new_rank)
            if not rank_role:
                logger.error(f"Could not find role for rank {new_rank}")
                return False
                
            # Remove old specialized roles if needed
            # This would depend on how your specialized roles are named
            
            # Get fleet component role
            fleet_component_role = discord.utils.get(member.guild.roles, name=fleet_component)
            
            # Apply role changes
            try:
                # Remove old roles
                if to_remove:
                    await member.remove_roles(*to_remove, reason=f"Promotion to {new_rank}")
                
                # Add new rank role
                await member.add_roles(rank_role, reason=f"Promotion to {new_rank}")
                
                # Add fleet component role if it exists and member doesn't have it
                if fleet_component_role and fleet_component_role not in member.roles:
                    await member.add_roles(fleet_component_role, reason=f"Assignment to {fleet_component}")
                    
                return True
            except discord.Forbidden:
                logger.error(f"Bot lacks permission to modify roles for {member.name}")
                return False
            except Exception as e:
                logger.error(f"Error updating roles: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error in update_member_roles: {e}")
            return False
            
    async def update_member_nickname(
        self,
        member: discord.Member,
        fleet_component: str,
        new_rank: str,
        specialization: str = None
    ) -> bool:
        """
        Update a member's nickname with their new rank.
        
        Args:
            member: Discord member
            fleet_component: Fleet component or division
            new_rank: New rank
            specialization: Optional role specialization
            
        Returns:
            bool: Success or failure
        """
        try:
            # Determine the proper rank abbreviation based on specialization
            rank_abbrev = None
            
            # Check for specialized rank
            if specialization and fleet_component:
                key = (fleet_component.lower(), specialization.lower(), new_rank.lower())
                if key in STANDARD_TO_DIVISION_RANK:
                    _, rank_abbrev = STANDARD_TO_DIVISION_RANK[key]
            
            # Fallback to standard abbreviation
            if not rank_abbrev:
                rank_abbrev = RANK_ABBREVIATIONS.get(new_rank)
                
            if not rank_abbrev:
                logger.warning(f"Could not find abbreviation for {new_rank}")
                return False
                
            # Get base name (remove any existing rank prefix)
            current_nick = member.nick or member.name
            base_name = current_nick
            
            for abbrev in RANK_ABBREVIATIONS.values():
                if current_nick.startswith(f"{abbrev} "):
                    base_name = current_nick[len(abbrev)+1:]
                    break
            
            # Create new nickname
            new_nick = f"{rank_abbrev} {base_name}"
            
            # Update nickname
            try:
                await member.edit(nick=new_nick)
                return True
            except discord.Forbidden:
                logger.warning(f"Bot lacks permission to change nickname for {member.name}")
                return False
            except Exception as e:
                logger.error(f"Error updating nickname: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error in update_member_nickname: {e}")
            return False