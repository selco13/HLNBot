# cogs/managers/role_manager.py
from typing import Dict, List, Optional, Tuple
import discord
import logging

logger = logging.getLogger('role_manager')

class RoleManager:
    """Handles role operations with proper error handling and rollback."""
    
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.role_cache: Dict[str, discord.Role] = {}
        self.pending_changes: List[Tuple[discord.Member, List[discord.Role], List[discord.Role]]] = []

    def get_role(self, role_name: str) -> Optional[discord.Role]:
        """Get role with caching."""
        if role_name not in self.role_cache:
            self.role_cache[role_name] = discord.utils.get(self.guild.roles, name=role_name)
        return self.role_cache[role_name]

    async def validate_role_hierarchy(
        self,
        member: discord.Member,
        roles_to_add: List[discord.Role],
        roles_to_remove: List[discord.Role]
    ) -> bool:
        """Validate role changes against hierarchy."""
        if not self.guild.me.guild_permissions.manage_roles:
            return False

        top_bot_role = self.guild.me.top_role
        return all(
            role < top_bot_role
            for role in roles_to_add + roles_to_remove
        )

    async def prepare_role_update(
        self,
        member: discord.Member,
        roles_to_add: List[str],
        roles_to_remove: List[str]
    ) -> bool:
        """Prepare role updates with validation."""
        try:
            # Get role objects
            add_roles = [self.get_role(name) for name in roles_to_add if name]
            remove_roles = [self.get_role(name) for name in roles_to_remove if name]

            # Filter out None values
            add_roles = [r for r in add_roles if r]
            remove_roles = [r for r in remove_roles if r]

            # Validate hierarchy
            if not await self.validate_role_hierarchy(member, add_roles, remove_roles):
                return False

            # Store pending changes
            self.pending_changes.append((member, add_roles, remove_roles))
            return True

        except Exception as e:
            logger.error(f"Error preparing role updates: {e}")
            return False

    async def execute_updates(self) -> Tuple[bool, List[str]]:
        """Execute all pending role updates with rollback capability."""
        if not self.pending_changes:
            return True, []

        successful_updates = []
        failed_updates = []

        try:
            for member, add_roles, remove_roles in self.pending_changes:
                try:
                    if remove_roles:
                        await member.remove_roles(*remove_roles, reason="Role update")
                    if add_roles:
                        await member.add_roles(*add_roles, reason="Role update")
                    successful_updates.append(member.id)
                except discord.Forbidden:
                    failed_updates.append(f"Missing permissions for {member}")
                    await self.rollback_changes(successful_updates)
                    return False, failed_updates
                except Exception as e:
                    failed_updates.append(f"Error updating {member}: {e}")
                    await self.rollback_changes(successful_updates)
                    return False, failed_updates

            return True, []

        finally:
            self.pending_changes.clear()

    async def rollback_changes(self, successful_member_ids: List[int]):
        """Rollback successful role changes."""
        for member_id in successful_member_ids:
            member = self.guild.get_member(member_id)
            if member:
                try:
                    original_roles = [role for role in member.roles]
                    await member.edit(roles=original_roles, reason="Role update rollback")
                except Exception as e:
                    logger.error(f"Error rolling back roles for {member}: {e}")
