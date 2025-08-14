import discord
import logging
from typing import Tuple, Optional, List
from ..constants import RANK_ABBREVIATIONS

logger = logging.getLogger('onboarding')

class RoleHandler:
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.role_cache = {}

    def get_role(self, role_name: str) -> Optional[discord.Role]:
        """Get role with caching."""
        if role_name not in self.role_cache:
            self.role_cache[role_name] = discord.utils.get(self.guild.roles, name=role_name)
        return self.role_cache[role_name]

    async def assign_initial_roles(
        self,
        member: discord.Member,
        member_type: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Assign initial roles to new member.
        Members get Non-Division + Crewman Recruit
        Associates get Associate role
        """
        try:
            roles_to_add = []
            
            # Remove any existing rank roles
            current_rank_roles = [
                role for role in member.roles 
                if any(rank_name in role.name for rank_name, _ in RANK_ABBREVIATIONS.items())
            ]
            if current_rank_roles:
                await member.remove_roles(*current_rank_roles, reason="Onboarding reset")
            
            # Assign new roles
            if member_type == "Member":
                non_div_role = self.get_role('Non-Division')
                rank_role = self.get_role('Crewman Recruit')
                if non_div_role and rank_role:
                    roles_to_add.extend([non_div_role, rank_role])
            else:  # Associate
                associate_role = self.get_role('Associate')
                if associate_role:
                    roles_to_add.append(associate_role)

            if not roles_to_add:
                logger.error(f"Could not find required roles for {member_type}")
                return False, "Required roles not found"

            await member.add_roles(*roles_to_add, reason="Onboarding completion")
            logger.info(f"Assigned roles to {member}: {[r.name for r in roles_to_add]}")
            return True, None

        except discord.Forbidden:
            logger.error(f"Missing permissions to assign roles to {member}")
            return False, "Bot lacks permission to assign roles"
        except Exception as e:
            logger.error(f"Error assigning roles to {member}: {e}")
            return False, f"Error assigning roles: {str(e)}"

    async def update_nickname(
        self,
        member: discord.Member,
        member_type: str
    ) -> Tuple[bool, Optional[str]]:
        """Update member nickname with appropriate rank abbreviation."""
        try:
            # Use CWR for Members, ASC for Associates
            rank_abbrev = "CWR" if member_type == "Member" else "ASC"
            
            # Remove any existing rank prefix
            current_name = member.display_name
            name_parts = current_name.split()
            if len(name_parts) > 1 and name_parts[0] in RANK_ABBREVIATIONS.values():
                base_name = ' '.join(name_parts[1:])
            else:
                base_name = current_name
            
            new_nickname = f"{rank_abbrev} {base_name}"
            
            # Ensure nickname doesn't exceed Discord's limit
            if len(new_nickname) > 32:
                new_nickname = f"{rank_abbrev} {base_name[:29-len(rank_abbrev)]}"
            
            await member.edit(nick=new_nickname)
            logger.info(f"Updated nickname for {member} to {new_nickname}")
            return True, None

        except discord.Forbidden:
            logger.error(f"Missing permissions to change nickname for {member}")
            return False, "Bot lacks permission to change nicknames"
        except Exception as e:
            logger.error(f"Error updating nickname for {member}: {e}")
            return False, f"Error updating nickname: {str(e)}"