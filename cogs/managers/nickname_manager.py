# cogs/managers/nickname_manager.py

import discord
import logging
from typing import Optional, Tuple, Dict, Any
import asyncio
from datetime import datetime, timezone
from ..constants import (
    RANKS, DIVISION_CODES, RANK_ABBREVIATIONS,
    ALL_RANK_ABBREVIATIONS, DIVISION_RANKS, STANDARD_RANK_ABBREVIATIONS,
    RANK_NUMBERS
)

logger = logging.getLogger('nickname_manager')

class NicknameManager:
    """
    Handles all nickname-related operations.
    Updated to work with Service Registry pattern.
    """

    def __init__(self, coda_manager=None):
        self.coda_manager = coda_manager
        self._cache = {}
        self._cache_lock = asyncio.Lock()  # Added for thread safety
        self._cache_expiry = 3600  # 1 hour cache expiry for nicknames
        logger.info("NicknameManager initialized")

    def remove_rank_abbreviation(self, nickname: Optional[str]) -> str:
        """Remove existing rank abbreviations from nickname."""
        if not nickname:
            return ''
        
        # Split the nickname into parts
        parts = nickname.split()
        if not parts:
            return nickname
        
        # Check if the first part is a rank abbreviation
        first_part = parts[0]
        
        # Check against ALL_RANK_ABBREVIATIONS
        if first_part in ALL_RANK_ABBREVIATIONS:
            # If so, return everything after the first part
            return ' '.join(parts[1:])
        
        # Check for "Rank Name" format (e.g., "Lt JG")
        if len(parts) >= 2:
            first_two = f"{parts[0]} {parts[1]}"
            if first_two in ALL_RANK_ABBREVIATIONS:
                return ' '.join(parts[2:])
        
        # No rank prefix found
        return nickname

    def get_rank_abbreviation(self, rank_name: str, member_type: str, division: Optional[str] = None, specialization: Optional[str] = None) -> str:
        """Get the correct rank abbreviation."""
        if not rank_name:
            return ''
            
        # Handle Associate case first
        if member_type == 'Associate':
            return 'ASC'
            
        # Always prioritize division-specific rank abbreviation when available
        if division and specialization and division in DIVISION_RANKS:
            if specialization in DIVISION_RANKS[division]:
                for div_rank_name, std_rank_name, div_abbr, _ in DIVISION_RANKS[division][specialization]:
                    if std_rank_name.lower() == rank_name.lower():
                        logger.debug(f"Found specialized rank abbreviation: {div_abbr} for {rank_name}")
                        return div_abbr

        # Use standard rank abbreviations as fallback
        abbrev = STANDARD_RANK_ABBREVIATIONS.get(rank_name.lower())
        if abbrev:
            return abbrev
            
        logger.warning(f"No rank abbreviation found for {rank_name}")
        return ''

    def get_rank_number(self, rank_name: str, member_type: str) -> int:
        """Get the rank number for ID generation."""
        if not rank_name:
            return 21  # Default to lowest rank
            
        if member_type == 'Associate':
            return 50  # Special rank number for associates
            
        return RANK_NUMBERS.get(rank_name, 21)  # Default to Crewman Recruit (21)

    async def update_id_number(
        self,
        member: discord.Member,
        new_rank: str,
        member_type: str,
        current_id: str
    ) -> Optional[str]:
        """Update the rank portion of the ID number if needed."""
        try:
            if not current_id or '-' not in current_id:
                return None

            # Split the current ID (format: DIV-RANK-XXXX)
            div_code, rank_num, unique = current_id.split('-')
            
            # Get new rank number
            current_rank_num = rank_num
            new_rank_num = str(self.get_rank_number(new_rank, member_type)).zfill(2)
            
            # Only create new ID if rank number changed
            if current_rank_num != new_rank_num:
                new_id = f"{div_code}-{new_rank_num}-{unique}"
                logger.info(f"Updating ID number for {member}: {current_id} -> {new_id}")
                return new_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error updating ID number for {member}: {e}")
            return None

    async def update_member_id(self, discord_user_id: int, new_id: str, doc_id=None, table_id=None) -> bool:
        """Update a member's ID number in Coda."""
        try:
            if not self.coda_manager:
                logger.error("No Coda manager available")
                return False
                
            member_row = await self.coda_manager.get_member_data(discord_user_id)
            if not member_row:
                logger.error(f"No member data found for {discord_user_id}")
                return False
                
            # Update the ID Number
            updates = {
                'ID Number': new_id
            }
            
            # Use either direct update_member_info or the service interface
            if hasattr(self.coda_manager, 'update_member_info'):
                # Direct method call
                return await self.coda_manager.update_member_info(member_row['id'], updates)
            elif hasattr(self.coda_manager, 'request'):
                # If using CodaAPIClient directly
                response = await self.coda_manager.request(
                    'PUT',
                    f'docs/{doc_id}/tables/{table_id}/rows/{member_row["id"]}',
                    data={
                        'row': {
                            'cells': [
                                {'column': 'ID Number', 'value': new_id}
                            ]
                        }
                    }
                )
                return response is not None
            
            logger.error("Coda manager doesn't have expected methods")
            return False
            
        except Exception as e:
            logger.error(f"Error updating member ID for {discord_user_id}: {e}")
            return False

    async def generate_new_nickname(
        self,
        member: discord.Member,
        new_rank: str,
        member_type: str,
        division: str,
        specialization: Optional[str] = None
    ) -> str:
        """Generate new nickname with appropriate rank abbreviation."""
        try:
            current_name = member.display_name
            
            # Debug logging
            logger.debug(f"Current nickname: '{current_name}', rank: '{new_rank}', division: '{division}', specialization: '{specialization}'")
            
            # Get the base name (remove any existing rank abbreviation)
            base_name = self.remove_rank_abbreviation(current_name)
            logger.debug(f"Base name after removing rank: '{base_name}'")
            
            # Special handling for Marines in Tactical Division
            if division == "Tactical" and specialization == "Marines":
                # Find the appropriate Marine rank that corresponds to the standard rank
                marine_abbrev = None
                if "Marines" in DIVISION_RANKS.get("Tactical", {}):
                    marine_ranks = DIVISION_RANKS["Tactical"]["Marines"]
                    for _, std_rank, marine_abbr, _ in marine_ranks:
                        if std_rank.lower() == new_rank.lower():
                            marine_abbrev = marine_abbr
                            break
                
                if marine_abbrev:
                    logger.debug(f"Using Marine rank abbreviation: {marine_abbrev}")
                    new_nickname = f"{marine_abbrev} {base_name}"
                    
                    # Clean up double spaces
                    while '  ' in new_nickname:
                        new_nickname = new_nickname.replace('  ', ' ')
                    
                    new_nickname = new_nickname.strip()
                    
                    # Handle Discord's nickname length limit
                    if len(new_nickname) > 32:
                        max_base_length = 32 - len(marine_abbrev) - 1
                        base_name = base_name[:max_base_length]
                        new_nickname = f"{marine_abbrev} {base_name}"
                    
                    logger.info(f"Setting Marine nickname: '{current_name}' -> '{new_nickname}'")
                    return new_nickname
            
            # Standard handling for non-Marine ranks
            rank_abbr = self.get_rank_abbreviation(new_rank, member_type, division, specialization)
            logger.debug(f"Found rank abbreviation: '{rank_abbr}'")
            
            # If we have a rank abbreviation, add it to the base name
            if rank_abbr:
                new_nickname = f"{rank_abbr} {base_name}"
            else:
                new_nickname = base_name
                
            # Clean up double spaces
            while '  ' in new_nickname:
                new_nickname = new_nickname.replace('  ', ' ')
            
            new_nickname = new_nickname.strip()
                
            # Handle Discord's nickname length limit
            if len(new_nickname) > 32:
                if rank_abbr:
                    max_base_length = 32 - len(rank_abbr) - 1
                    base_name = base_name[:max_base_length]
                    new_nickname = f"{rank_abbr} {base_name}"
                else:
                    new_nickname = base_name[:32]
                
            logger.info(f"Setting nickname: '{current_name}' -> '{new_nickname}'")
            return new_nickname

        except Exception as e:
            logger.error(f"Error generating nickname: {e}")
            return member.display_name

    async def update_nickname(
        self,
        member: discord.Member,
        new_rank: str,
        member_type: str,
        division: str,
        specialization: Optional[str] = None,
        current_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Update member's nickname with new rank and optionally update ID number.
        Returns: (success, error_message, new_id_number)
        """
        try:
            # Check if current nickname already has correct specialized rank (for Marines)
            current_nickname = member.display_name
            
            # Special handling for Marines
            if division == "Tactical" and specialization == "Marines":
                # Find matching marine rank abbreviation
                marine_abbrev = None
                if "Marines" in DIVISION_RANKS.get("Tactical", {}):
                    marine_ranks = DIVISION_RANKS["Tactical"]["Marines"]
                    for _, std_rank, marine_abbr, _ in marine_ranks:
                        if std_rank.lower() == new_rank.lower():
                            marine_abbrev = marine_abbr
                            break
                
                # Check if current nickname already has the correct marine rank
                if marine_abbrev and current_nickname.startswith(f"{marine_abbrev} "):
                    logger.info(f"Marine nickname already has correct rank abbreviation: '{current_nickname}'")
                    # Skip nickname update but still check ID
                else:
                    # Generate new nickname
                    new_nickname = await self.generate_new_nickname(
                        member,
                        new_rank,
                        member_type,
                        division,
                        specialization
                    )
                    
                    # Update if different
                    if new_nickname != current_nickname:
                        await member.edit(nick=new_nickname)
                        logger.info(f"Updated marine nickname for {member.id}: {new_nickname}")
                        
                        # Cache the new nickname
                        await self._cache_nickname(member.id, new_nickname)
            else:
                # Standard rank handling for non-Marines
                # Get correct abbreviation for comparison
                rank_abbr = self.get_rank_abbreviation(new_rank, member_type, division, specialization)
                
                # Check if current nickname already starts with correct rank
                if rank_abbr and current_nickname.startswith(f"{rank_abbr} "):
                    logger.info(f"Nickname already has correct rank abbreviation: '{current_nickname}'")
                    # Skip nickname update but still check ID
                else:
                    # Generate new nickname
                    new_nickname = await self.generate_new_nickname(
                        member,
                        new_rank,
                        member_type,
                        division,
                        specialization
                    )
                    
                    # Update if different
                    if new_nickname != current_nickname:
                        await member.edit(nick=new_nickname)
                        logger.info(f"Updated nickname for {member.id}: {new_nickname}")
                        
                        # Cache the new nickname
                        await self._cache_nickname(member.id, new_nickname)
            
            # Handle ID update if needed
            new_id = None
            if current_id:
                new_id = await self.update_id_number(
                    member,
                    new_rank,
                    member_type,
                    current_id
                )
                
                # Only update in Coda if we have a new ID and it's different
                if new_id and new_id != current_id and self.coda_manager:
                    # Pass doc_id and table_id from coda_manager
                    doc_id = getattr(self.coda_manager, 'doc_id', None)
                    table_id = getattr(self.coda_manager, 'profile_table_id', None)
                    
                    if not doc_id:
                        doc_id = getattr(self.coda_manager, 'DOC_ID', None) or os.getenv('DOC_ID')
                        
                    if not table_id:
                        table_id = getattr(self.coda_manager, 'TABLE_ID', None) or os.getenv('TABLE_ID')
                    
                    if doc_id and table_id:
                        await self.update_member_id(
                            member.id,
                            new_id,
                            doc_id=doc_id,
                            table_id=table_id
                        )
                    else:
                        logger.error("Missing doc_id or table_id in coda_manager")
            
            return True, None, new_id
            
        except discord.Forbidden:
            error_msg = "Bot lacks permission to change nicknames"
            logger.warning(f"{error_msg} for {member.id}")
            return False, error_msg, None
        except Exception as e:
            error_msg = f"Error updating nickname: {str(e)}"
            logger.error(f"{error_msg} for {member.id}")
            return False, error_msg, None
    
    # Added for simple rank prefix updates (for compatibility with event-based architecture)
    async def update_nickname_with_prefix(self, member: discord.Member, rank_prefix: str) -> bool:
        """
        Simplified method to update nickname with just a rank prefix.
        This is useful for basic onboarding where we only have the rank prefix.
        """
        try:
            current_name = member.display_name
            
            # Get base name (remove existing rank if any)
            base_name = self.remove_rank_abbreviation(current_name)
            
            # Create new nickname
            new_nickname = f"{rank_prefix} {base_name}".strip()
            
            # Handle Discord's nickname length limit
            if len(new_nickname) > 32:
                max_base_length = 32 - len(rank_prefix) - 1
                base_name = base_name[:max_base_length]
                new_nickname = f"{rank_prefix} {base_name}"
            
            # Update if different
            if new_nickname != current_name:
                await member.edit(nick=new_nickname)
                logger.info(f"Updated nickname with prefix for {member.id}: {new_nickname}")
                
                # Cache the new nickname
                await self._cache_nickname(member.id, new_nickname)
                
            return True
            
        except discord.Forbidden:
            logger.warning(f"Bot lacks permission to change nickname for {member.id}")
            return False
        except Exception as e:
            logger.error(f"Error updating nickname with prefix for {member.id}: {e}")
            return False
    
    # Added for caching
    async def _cache_nickname(self, member_id: int, nickname: str) -> None:
        """Cache a nickname to avoid unnecessary Discord API calls."""
        async with self._cache_lock:
            self._cache[member_id] = {
                'nickname': nickname,
                'timestamp': datetime.now(timezone.utc).timestamp()
            }
    
    async def get_cached_nickname(self, member_id: int) -> Optional[str]:
        """Get a cached nickname if available and not expired."""
        async with self._cache_lock:
            cached = self._cache.get(member_id)
            if not cached:
                return None
                
            # Check if expired
            now = datetime.now(timezone.utc).timestamp()
            if now - cached['timestamp'] > self._cache_expiry:
                # Expired
                del self._cache[member_id]
                return None
                
            return cached['nickname']
    
    # For bulk operations
    async def bulk_update_nicknames(self, guild: discord.Guild, ranks_data: Dict[int, Dict[str, Any]], limit: int = 0) -> Tuple[int, int]:
        """
        Bulk update nicknames for members based on rank data.
        
        Args:
            guild: The Discord guild
            ranks_data: Dictionary mapping user IDs to rank info dicts with keys:
                        'rank', 'member_type', 'division', 'specialization'
            limit: Maximum number of members to update (0 for all)
            
        Returns:
            Tuple of (success_count, failure_count)
        """
        success_count = 0
        failure_count = 0
        
        try:
            # Get all member IDs to update
            member_ids = list(ranks_data.keys())
            
            # Apply limit if specified
            if limit > 0:
                member_ids = member_ids[:limit]
                
            logger.info(f"Starting bulk nickname update for {len(member_ids)} members")
            
            # Process in batches to avoid rate limits
            batch_size = 10
            for i in range(0, len(member_ids), batch_size):
                batch = member_ids[i:i+batch_size]
                
                for user_id in batch:
                    member = guild.get_member(user_id)
                    if not member:
                        logger.warning(f"Member {user_id} not found in guild")
                        failure_count += 1
                        continue
                        
                    # Get rank data
                    rank_data = ranks_data[user_id]
                    
                    try:
                        success, _, _ = await self.update_nickname(
                            member,
                            rank_data.get('rank', ''),
                            rank_data.get('member_type', 'Member'),
                            rank_data.get('division', ''),
                            rank_data.get('specialization'),
                            rank_data.get('id_number')
                        )
                        
                        if success:
                            success_count += 1
                        else:
                            failure_count += 1
                            
                    except Exception as e:
                        logger.error(f"Error updating nickname for {user_id}: {e}")
                        failure_count += 1
                        
                # Sleep between batches to avoid rate limits
                if i + batch_size < len(member_ids):
                    await asyncio.sleep(5)
                    
            logger.info(f"Bulk nickname update complete: {success_count} successes, {failure_count} failures")
            return success_count, failure_count
            
        except Exception as e:
            logger.error(f"Error in bulk_update_nicknames: {e}")
            return success_count, failure_count