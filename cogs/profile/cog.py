"""Main profile cog implementation with fleet system integration."""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import aiohttp
import asyncio
import secrets
import string
import io
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone
from pydantic import ValidationError
from logging.handlers import RotatingFileHandler

# Import BaseCog instead of commands.Cog
from cogs.utils.base_cog import BaseCog

# Import local modules avoiding circular imports
from .cache import ProfileCache
from .constants import (
    DOC_ID, TABLE_ID, GUILD_ID, AVAILABLE_AWARDS,
    FIELD_ID_NUMBER, FIELD_DISCORD_USERNAME, FIELD_DIVISION, FIELD_FLEET_WING, FIELD_RANK, FIELD_AWARDS,
    FIELD_CERTIFICATIONS, FIELD_SPECIALIZATION, FIELD_JOIN_DATE, FIELD_DISCORD_USER_ID,
    FIELD_STATUS, FIELD_SECURITY_CLEARANCE, FIELD_CLASSIFIED_INFO, FIELD_COMPLETED_MISSIONS,
    FIELD_MISSION_COUNT, FIELD_MISSION_TYPES, FIELD_SPECIAL_OPERATIONS, FIELD_STRATEGIC_PLANNING,
    FIELD_COMBAT_MISSIONS, FIELD_STRATEGIC_ASSESSMENT, FIELD_COMMAND_EVALUATION, FIELD_FLEET_OPERATIONS,
    FIELD_SHIP_ASSIGNMENT, DIVISION_TO_FLEET_WING, FLEET_WING_ICONS
)
from .formatters import MilitaryIDFormatter, WatermarkGenerator
from .models import ProfileData
from .security import SecurityClearance, get_security_classification, get_clearance_code
from .utils import parse_list_field, get_rank_info, calculate_service_time
from .commands import ProfileCommandExtensions
from .fleet import FleetIntegration
from .ships_integration import ShipIntegrationMethods
from .timeline_utils import generate_career_timeline_data, CareerTimelineView
from .ui import (
    ProfileView, PaginatedContentView, BulkAwardModal, 
    ComparisonView, AchievementUnlockModal, DivisionReportView, FleetReportView,
    StatusChangeModal, MemberSearchView, AwardGalleryView
)

# Setup Logging
logger = logging.getLogger('profile')
logger.setLevel(logging.DEBUG)

handler = RotatingFileHandler(
    filename='profiles.log',
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=5,
    encoding='utf-8',
    mode='a'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# Define CODA_COLUMN_MAPPING for column verification
CODA_COLUMN_MAPPING = {
    "ID Number": FIELD_ID_NUMBER,
    "Discord Username": FIELD_DISCORD_USERNAME,
    "Division": FIELD_DIVISION,
    "Fleet Wing": FIELD_FLEET_WING,
    "Rank": FIELD_RANK,
    "Awards": FIELD_AWARDS,
    "Certifications": FIELD_CERTIFICATIONS,
    "Specialization": FIELD_SPECIALIZATION,
    "Join Date": FIELD_JOIN_DATE,
    "Discord User ID": FIELD_DISCORD_USER_ID,
    "Status": FIELD_STATUS,
    "Security Clearance": FIELD_SECURITY_CLEARANCE,
    "Classified Information": FIELD_CLASSIFIED_INFO,
    "Completed Missions": FIELD_COMPLETED_MISSIONS,
    "Mission Count": FIELD_MISSION_COUNT,
    "Mission Types": FIELD_MISSION_TYPES,
    "Special Operations": FIELD_SPECIAL_OPERATIONS,
    "Strategic Planning": FIELD_STRATEGIC_PLANNING,
    "Combat Missions": FIELD_COMBAT_MISSIONS,
    "Strategic Assessment": FIELD_STRATEGIC_ASSESSMENT,
    "Command Evaluation": FIELD_COMMAND_EVALUATION,
    "Fleet Operations": FIELD_FLEET_OPERATIONS,
    "Ship Assignment": FIELD_SHIP_ASSIGNMENT
}

# Create a database lock to prevent race conditions
class ProfileCog(BaseCog, ProfileCommandExtensions, ShipIntegrationMethods):
    """Improved cog for managing member profiles, service records, and military information."""
    
    def __init__(self, bot: commands.Bot):
        # Initialize BaseCog
        super().__init__(bot)
        
        # Initialize services with BaseCog's property accessors
        self.cache = ProfileCache()  # Maintain custom cache for now
        self.formatter = MilitaryIDFormatter()
        self.watermark = WatermarkGenerator()
        self.db_lock = asyncio.Lock()  # Add a lock for database operations
        logger.info("ProfileCog initialized")
        
        self.fleet_integration = FleetIntegration(self)

    async def cog_load(self):
        """Called when the cog is loaded."""
        await self.cache.start_cleanup()
        
        # Verify column IDs if in debug mode
        # This helps catch column mapping issues early during development
        try:
            if os.getenv("DEBUG_MODE", "false").lower() == "true":
                logger.info("Debug mode enabled, verifying column IDs...")
                await self.verify_column_ids()
        except Exception as e:
            logger.warning(f"Column verification failed but continuing: {e}")
        
        logger.info("ProfileCog loaded with fleet system support")
        
        # Check for updates to make to existing profiles
        try:
            if os.getenv("RUN_MAINTENANCE", "false").lower() == "true":
                logger.info("Maintenance mode enabled, scheduling profile validations...")
                self.bot.loop.create_task(self.run_maintenance_tasks())
        except Exception as e:
            logger.warning(f"Failed to schedule maintenance: {e}")
        
    async def run_maintenance_tasks(self):
        """Run maintenance tasks on profiles."""
        try:
            # Wait a bit after startup before running maintenance
            await asyncio.sleep(60)
            
            logger.info("Running profile maintenance tasks...")
            guild = self.bot.get_guild(GUILD_ID)
            if not guild:
                logger.error(f"Could not find guild with ID {GUILD_ID}")
                return
                
            # Get active members and validate their profiles
            validated_count = 0
            fixed_count = 0
            
            async for member in guild.fetch_members(limit=None):
                if member.bot:
                    continue
                    
                try:
                    # Get and validate member's profile
                    member_row = await self.get_member_row(member.id)
                    if member_row:
                        was_fixed, changes = await self.validate_member_profile(member, member_row)
                        validated_count += 1
                        
                        if was_fixed:
                            fixed_count += 1
                            logger.info(f"Fixed profile for {member} ({member.id}): {changes}")
                except Exception as e:
                    logger.error(f"Error validating profile for {member}: {e}")
                    
                # Sleep briefly to avoid overloading the API
                await asyncio.sleep(0.5)
                
            logger.info(f"Profile maintenance complete. Validated {validated_count} profiles, fixed {fixed_count}.")
            
        except Exception as e:
            logger.error(f"Error in maintenance tasks: {e}")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        await self.cache.stop_cleanup()
        logger.info("ProfileCog unloaded")

    async def get_member_row(self, discord_user_id: int) -> Optional[Dict[str, Any]]:
        """Enhanced member data retrieval with proper caching."""
        cache_key = str(discord_user_id)
        
        # Check cache first
        cached_data = await self.cache.get(cache_key)
        if cached_data:
            logger.debug(f"Cache hit for user {discord_user_id}")
            return cached_data
    
        # Fetch from Coda if not in cache
        try:
            logger.debug(f"Cache miss for user {discord_user_id} - fetching from Coda")
            
            # Use the exact column ID for Discord User ID for more reliability
            discord_id_field = FIELD_DISCORD_USER_ID  # This should be 'c-QgM-J6GI3o'
            
            # Build query using column ID instead of name for more reliability
            query = f'"{discord_id_field}":"{discord_user_id}"'
            
            async with self.db_lock:  # Add lock for database operations
                rows = await self.coda_client.get_rows(
                    DOC_ID,
                    TABLE_ID,
                    query=query,
                    limit=1
                )
    
            if rows and len(rows) > 0:
                member_data = rows[0]
                await self.cache.set(cache_key, member_data)
                return member_data
            
            # If user is not found in the database but profile is requested,
            # we might want to check if they're in the onboarding process
            logger.debug(f"No data found for user {discord_user_id}, checking if in onboarding process")
            
            # If an onboarding_cog exists, we can check if there's a pending record
            onboarding_cog = self.bot.get_cog("OnboardingCog")
            if onboarding_cog and hasattr(onboarding_cog, "coda_client"):
                # Query for pending registrations
                pending_query = f'"{discord_id_field}":"{discord_user_id}" AND "Status":"Pending"'
                async with self.db_lock:  # Add lock for database operations
                    pending_rows = await onboarding_cog.coda_client.get_rows(
                        DOC_ID,
                        TABLE_ID,
                        query=pending_query,
                        limit=1
                    )
                
                if pending_rows and len(pending_rows) > 0:
                    logger.info(f"User {discord_user_id} has a pending registration")
                    # Return None but maybe set a flag that user has a pending registration
                    return None
            
            logger.debug(f"No data found for user {discord_user_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching member row: {e}")
            return None

    async def verify_column_ids(self) -> bool:
        """Verify that the column IDs used in the code match those in the Coda table.
        
        This helps detect issues with column IDs early by checking them against the actual table.
        
        Returns:
            bool: True if all column IDs are valid, False otherwise
        """
        if not hasattr(self, 'coda_client') or not self.coda_client:
            logger.error("Cannot verify column IDs: Coda client not available")
            return False
            
        try:
            # Get the table metadata to check column IDs
            async with self.db_lock:  # Add lock for database operations
                response = await self.coda_client.request(
                    'GET',
                    f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}'
                )
            
            if not response or 'columns' not in response:
                logger.error(f"Failed to get table metadata: {response}")
                return False
                
            # Extract column IDs from the response
            coda_columns = {col['id']: col['name'] for col in response['columns']}
            
            # Check each column ID used in the code
            for internal_name, column_id in CODA_COLUMN_MAPPING.items():
                # Skip columns that use names instead of IDs (they start with c-)
                if not column_id.startswith('c-'):
                    logger.warning(f"Column '{internal_name}' uses name '{column_id}' instead of ID")
                    continue
                    
                if column_id not in coda_columns:
                    logger.error(f"Column ID '{column_id}' for '{internal_name}' not found in Coda table")
                    return False
                    
                logger.debug(f"Verified column ID {column_id} ({internal_name}) -> '{coda_columns[column_id]}'")
                
            logger.info("All column IDs successfully verified")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying column IDs: {e}")
            return False

    def map_and_validate_profile(self, row: dict, user_id: int) -> Optional[dict]:
        try:
            raw_values = row.get('values', {})
            mission_count_raw = raw_values.get("Mission Count", '')
            current_rank = raw_values.get("Rank", '')
            
            # Compute the rank index based on the current_rank using the RANKS list
            from cogs.constants import RANKS
            computed_rank_index = next(
                (i for i, (r, _) in enumerate(RANKS) if r.lower() == current_rank.lower()),
                0  # Default to 0 if no match is found
            )
            
            # Get fleet wing (with backward compatibility)
            fleet_wing = raw_values.get("Fleet Wing")
            if not fleet_wing:
                division = raw_values.get("Division", 'N/A')
                fleet_wing = DIVISION_TO_FLEET_WING.get(division, division)
            
            mapped_data = {
                "id_number": raw_values.get("ID Number"),
                "discord_username": raw_values.get("Discord Username", "Unknown"),
                "discord_user_id": str(user_id),
                "division": raw_values.get("Division"),
                "fleet_wing": fleet_wing,
                "rank": current_rank,
                "rank_index": computed_rank_index,
                "awards": parse_list_field(raw_values.get("Awards")),
                "certifications": parse_list_field(raw_values.get("Certifications")),
                "specialization": raw_values.get("Specialization"),
                "join_date": raw_values.get("Join Date"),
                "status": raw_values.get("Status"),
                "security_clearance": raw_values.get("Security Clearance"),
                "classified_information": raw_values.get("Classified Information"),
                "completed_missions": parse_list_field(raw_values.get("Completed Missions")),
                "mission_count": mission_count_raw if mission_count_raw not in ('', None) else 0,
                "mission_type": parse_list_field(raw_values.get("Mission Type")),
                "special_operations": parse_list_field(raw_values.get("Special_Operations")),
                "strategic_planning": raw_values.get("Strategic_Planning"),
                "combat_missions": parse_list_field(raw_values.get("Combat_Missions")),
                "strategic_assessment": raw_values.get("Strategic_Assessment"),
                "command_evaluation": raw_values.get("Command_Evaluation"),
                "fleet_operations": raw_values.get("Fleet_Operations"),
                "ship_assignment": raw_values.get("Ship Assignment", 'Unassigned')
            }
            
            # Validate using the Pydantic model
            ProfileData(**mapped_data)
            return mapped_data
        
        except ValidationError as e:
            logger.error(f"Validation error for user {user_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error mapping profile data for user {user_id}: {e}")
            return None

    async def update_profile(
        self,
        member: discord.Member,
        updates: Dict[str, Any],
        reason: str = None
    ) -> bool:
        """Update a member's profile."""
        try:
            # Get document and table IDs 
            doc_id = DOC_ID
            table_id = TABLE_ID or os.getenv('PROFILE_TABLE_ID')
            
            if not doc_id or not table_id:
                logger.error(f"Missing environment variables for Coda. DOC_ID: {doc_id}, TABLE_ID: {table_id}")
                return False
            
            # Update directly via Coda API
            try:
                member_id_str = str(member.id)
                
                async with self.db_lock:  # Add lock for database operations
                    # Get the row ID
                    rows = await self.coda_client.get_rows(
                        doc_id,
                        table_id,
                        query=f'"Discord User ID":"{member_id_str}"',
                        limit=1
                    )
                    
                    if not rows:
                        logger.error(f"Could not find row for member {member_id_str}")
                        return False
                        
                    row_id = rows[0]['id']
                    
                    # Update the row
                    update_cells = [
                        {'column': key, 'value': value}
                        for key, value in updates.items()
                    ]
                    
                    response = await self.coda_client.request(
                        'PUT',
                        f'docs/{doc_id}/tables/{table_id}/rows/{row_id}',
                        data={'row': {'cells': update_cells}}
                    )
                
                if response:
                    logger.info(f"Successfully updated profile for {member_id_str}")
                    
                    # Handle backup and logging
                    try:
                        if self.backup_manager:
                            await self.backup_manager.create_backup(
                                {'member_id': member.id, 'updates': updates},
                                'profile_update'
                            )
                    except Exception as backup_err:
                        logger.warning(f"Backup warning (non-critical): {backup_err}")
                    
                    try:
                        await self.audit_logger.log_action(
                            'profile_update',
                            self.bot.user,
                            member,
                            f"Profile updated: {', '.join(f'{k}={v}' for k,v in updates.items())}"
                        )
                    except Exception as log_err:
                        logger.warning(f"Audit log warning (non-critical): {log_err}")
                    
                    # *** IMPORTANT - Ensure cache is invalidated properly ***
                    try:
                        # Forcibly invalidate cache
                        await self.cache.invalidate(member_id_str)
                        logger.debug(f"Cache invalidated for {member_id_str}")
                        
                        # Double-check: Clear the cache completely for this user
                        if hasattr(self.cache, 'bulk_invalidate'):
                            await self.cache.bulk_invalidate([member_id_str])
                    except Exception as cache_err:
                        logger.warning(f"Cache invalidation warning: {cache_err}")
                    
                    # Handle events
                    try:
                        if self.profile_sync:
                            event = ProfileEvent(
                                event_type="profile_updated",
                                member_id=member.id,
                                timestamp=datetime.now(timezone.utc),
                                data=updates,
                                reason=reason
                            )
                            await self.profile_sync.queue_update(event)
                    except Exception as sync_err:
                        logger.warning(f"Sync manager warning: {sync_err}")
                    
                    # Dispatch event
                    await self.dispatch_event(
                        'profile_updated',
                        member_id=member.id,
                        updates=updates,
                        reason=reason
                    )
                    
                    return True
                else:
                    logger.error(f"Failed to update row for member {member_id_str}")
                    return False
                    
            except Exception as api_err:
                logger.error(f"Error updating profile via direct API: {api_err}")
                return False
    
        except Exception as e:
            logger.error(f"Error updating profile for {member.id}: {e}")
            return False

    async def add_award_to_member(
        self,
        member: discord.Member,
        award: str,
        citation: str,
        awarded_by: int = None,
        notify_member: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Internal method to add an award to a member's profile.
        
        Args:
            member: Discord member to award
            award: Award name/ID to give
            citation: Citation text for the award
            awarded_by: ID of the user who awarded this (optional)
            notify_member: Whether to send a DM to the member
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Find the full award details from available awards
            full_award = None
            for entry in AVAILABLE_AWARDS:
                # Take just the portion before " - "
                short_name = entry.split(' - ')[0]
                # If that short_name starts with the user-chosen 'award', treat it as a match
                if short_name.startswith(award):
                    full_award = entry
                    break
    
            if not full_award:
                return False, "Invalid or unknown award specified."
    
            # Get the member's current profile from Coda
            member_row = await self.get_member_row(member.id)
            if not member_row:
                return False, "No profile found for this member."
    
            values = member_row.get('values', {})
            current_awards = parse_list_field(values.get(FIELD_AWARDS, []))
    
            # Format the new award with citation and date stamp
            short_portion = full_award.split(' - ')[0]
            timestamp = datetime.now().strftime('%Y-%m-%d')
            formatted_award = f"{short_portion} - {citation} - {timestamp}"
    
            # Check if the member already has this award
            if any(a.startswith(short_portion) for a in current_awards):
                return False, f"Member already has the {short_portion} award."
    
            # 1. Add to the awards list in Coda
            current_awards.append(formatted_award)
    
            # 2. Add the Discord role
            # First, check if the role exists
            award_role_name = short_portion
            award_role = discord.utils.get(member.guild.roles, name=award_role_name)
            
            # If role doesn't exist, create it with a gold/bronze color
            if not award_role:
                try:
                    award_role = await member.guild.create_role(
                        name=award_role_name,
                        color=discord.Color.from_rgb(207, 181, 59),  # Gold color
                        reason=f"Created for award: {short_portion}"
                    )
                    logger.info(f"Created new award role: {award_role_name}")
                except discord.Forbidden:
                    logger.error(f"No permission to create award role: {award_role_name}")
                except Exception as e:
                    logger.error(f"Error creating award role: {e}")
                    
            # Add the role to the member if it exists
            role_added = False
            if award_role:
                try:
                    await member.add_roles(award_role, reason=f"Award granted: {citation}")
                    role_added = True
                    logger.info(f"Added award role {award_role_name} to {member.name}")
                except discord.Forbidden:
                    logger.error(f"No permission to assign role {award_role_name} to {member.name}")
                except Exception as e:
                    logger.error(f"Error assigning award role: {e}")
    
            # 3. Update the profile in Coda
            success = await self.update_profile(
                member,
                {FIELD_AWARDS: ','.join(current_awards)},
                f"Award added: {short_portion}"
            )
            
            if not success:
                return False, "Failed to update the database record."
                    
            # 4. Send DM to member if requested
            if notify_member:
                try:
                    await member.send(
                        f"🎖️ Congratulations! You have been awarded the {short_portion}!\n\n"
                        f"**Citation:** {citation}\n"
                        f"**Awarded on:** {timestamp}"
                    )
                    dm_sent = True
                except discord.Forbidden:
                    dm_sent = False
                    logger.warning(f"Could not send award DM to {member.name}")
            else:
                dm_sent = False
            
            # 5. Log the award
            if hasattr(self, 'audit_logger'):
                awarder_id = awarded_by or 0
                try:
                    if awarder_id:
                        awarder = member.guild.get_member(awarder_id)
                        if awarder:
                            await self.audit_logger.log_action(
                                'award_granted',
                                awarder,
                                member,
                                f"Awarded {short_portion} - Citation: {citation}"
                            )
                        else:
                            await self.audit_logger.log_action(
                                'award_granted',
                                self.bot.user,
                                member,
                                f"Awarded {short_portion} - Citation: {citation} (on behalf of user ID {awarder_id})"
                            )
                    else:
                        await self.audit_logger.log_action(
                            'award_granted',
                            self.bot.user,
                            member,
                            f"Awarded {short_portion} - Citation: {citation}"
                        )
                except Exception as e:
                    logger.error(f"Error logging award: {e}")
            
            # 6. Dispatch award_granted event
            if hasattr(self, 'dispatch_event'):
                try:
                    await self.dispatch_event(
                        'award_granted',
                        member_id=member.id,
                        award=short_portion,
                        citation=citation,
                        timestamp=timestamp,
                        granted_by=awarded_by
                    )
                except Exception as e:
                    logger.error(f"Error dispatching award event: {e}")
            
            # Return success with details
            return True, {
                "award": short_portion,
                "citation": citation,
                "timestamp": timestamp,
                "role_added": role_added,
                "dm_sent": dm_sent
            }
        
        except Exception as e:
            logger.error(f"Error in add_award_to_member: {e}", exc_info=True)
            return False, f"Internal error: {str(e)}"

    async def batch_update_profiles(
        self,
        updates: Dict[int, Dict[str, Any]],
        reason: str = None
    ) -> Dict[int, bool]:
        """
        Update multiple profiles in a batch.
        
        Args:
            updates: Dict mapping Discord user IDs to their updates
            reason: Reason for updates
            
        Returns:
            Dict mapping Discord user IDs to success status
        """
        results = {}
        try:
            doc_id = DOC_ID
            table_id = TABLE_ID or os.getenv('PROFILE_TABLE_ID')
            
            if not doc_id or not table_id:
                logger.error(f"Missing environment variables for Coda. DOC_ID: {doc_id}, TABLE_ID: {table_id}")
                return {user_id: False for user_id in updates.keys()}
            
            async with self.db_lock:  # Add lock for database operations
                # Get all rows and build a map of Discord ID -> Row ID
                discord_to_row = {}
                
                # Create query with all Discord IDs
                discord_ids = list(updates.keys())
                
                # Get rows in batches of 25 (Coda API limit)
                for i in range(0, len(discord_ids), 25):
                    batch = discord_ids[i:i+25]
                    query = ' OR '.join([f'"Discord User ID":"{id}"' for id in batch])
                    
                    rows = await self.coda_client.get_rows(
                        doc_id,
                        table_id,
                        query=query
                    )
                    
                    for row in rows:
                        discord_id = row.get('values', {}).get('Discord User ID')
                        if discord_id:
                            discord_to_row[discord_id] = row['id']
                
                # Prepare batch updates
                batch_operations = []
                for user_id, user_updates in updates.items():
                    row_id = discord_to_row.get(str(user_id))
                    if not row_id:
                        logger.warning(f"No row found for user {user_id}")
                        results[user_id] = False
                        continue
                        
                    # Create update operation
                    update_cells = [
                        {'column': key, 'value': value}
                        for key, value in user_updates.items()
                    ]
                    
                    batch_operations.append({
                        'row_id': row_id,
                        'cells': update_cells
                    })
                
                # Process in batches of 10
                for i in range(0, len(batch_operations), 10):
                    batch = batch_operations[i:i+10]
                    
                    # Create batch request data
                    rows_data = [{
                        'id': op['row_id'],
                        'cells': op['cells']
                    } for op in batch]
                    
                    response = await self.coda_client.request(
                        'PATCH',
                        f'docs/{doc_id}/tables/{table_id}/rows',
                        data={'rows': rows_data}
                    )
                    
                    if response and 'resultSummary' in response:
                        succeeded = response['resultSummary'].get('updated', 0)
                        
                        # Mark corresponding user_ids as succeeded or failed
                        for j, op in enumerate(batch):
                            user_id = None
                            for uid, rid in discord_to_row.items():
                                if rid == op['row_id']:
                                    user_id = int(uid)
                                    break
                                    
                            if user_id and user_id in updates:
                                # Consider as success if j < succeeded
                                results[user_id] = j < succeeded
                    else:
                        # Mark all as failed if the entire batch failed
                        for op in batch:
                            user_id = None
                            for uid, rid in discord_to_row.items():
                                if rid == op['row_id']:
                                    user_id = int(uid)
                                    break
                                    
                            if user_id and user_id in updates:
                                results[user_id] = False
            
            # Invalidate cache for updated users
            await self.cache.bulk_invalidate([str(user_id) for user_id in updates.keys()])
            
            # Log updates
            logger.info(f"Batch updated {sum(results.values())}/{len(updates)} profiles. Reason: {reason}")
            
            # Dispatch batch_profiles_updated event
            await self.dispatch_event(
                'batch_profiles_updated',
                updates=updates,
                results=results,
                reason=reason
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch_update_profiles: {e}")
            return {user_id: False for user_id in updates.keys()}

    async def validate_member_profile(
        self,
        member: discord.Member,
        profile_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate and fix member profile data if needed.
        Updated to handle fleet-based structure.
        
        Args:
            member: The member to validate
            profile_data: The member's profile data
            
        Returns:
            Tuple of (was_fixed, list_of_changes)
        """
        # Import needed constants for rank handling
        from .constants import (
            RANK_NUMBERS, RANK_ABBREVIATIONS, ALL_RANK_ABBREVIATIONS, 
            STANDARD_TO_DIVISION_RANK, DIVISION_RANKS, DIVISION_TO_FLEET_WING,
            FLEET_WING_ICONS
        )
        
        values = profile_data.get('values', {})
        changes = []
        needs_update = False
        updates = {}
    
        try:
            current_rank = values.get('Rank')
            
            # Handle migration from division to fleet wing
            current_division = values.get('Division')
            current_fleet_wing = values.get('Fleet Wing')
            
            # If we don't have a fleet wing but have a division, update it
            if not current_fleet_wing and current_division:
                fleet_wing = DIVISION_TO_FLEET_WING.get(current_division, current_division)
                # Only update if it would change to a different value
                if fleet_wing != current_division:
                    updates['Fleet Wing'] = fleet_wing
                    changes.append(f"Migrated Division '{current_division}' to Fleet Wing '{fleet_wing}'")
                    needs_update = True
            else:
                # Use fleet wing if available, otherwise fallback to division
                fleet_wing = current_fleet_wing or current_division or 'Non-Wing'
            
            current_id = values.get('ID Number')
            specialization = values.get('Specialization')
            member_type = values.get('Type', 'Member')
            current_nick = member.nick or member.name
            
            # Special handling for Marines in Marine Expeditionary Force
            if fleet_wing == "Marine Expeditionary Force":
                marine_abbrev = None
                # Define marine ranks directly if needed
                marine_ranks = [
                    ("Colonel", "Col", "Fleet Captain", "FltCpt"),
                    ("Lieutenant Colonel", "LtCol", "Captain", "Cpt"),
                    ("Major", "Maj", "Commander", "Cmdr"),
                    ("Captain", "Capt", "Lieutenant Commander", "LtCmdr"),
                    ("First Lieutenant", "1stLt", "Lieutenant", "Lt"),
                    ("Second Lieutenant", "2ndLt", "Lieutenant Junior Grade", "LtJG"),
                    ("Sergeant Major", "SgtMaj", "Chief Petty Officer", "CPO"),
                    ("Master Sergeant", "MSgt", "Petty Officer 1st Class", "PO1"),
                    ("Sergeant First Class", "SFC", "Petty Officer 2nd Class", "PO2"),
                    ("Staff Sergeant", "SSgt", "Petty Officer 3rd Class", "PO3"),
                    ("Sergeant", "Sgt", "Master Crewman", "MCr"),
                    ("Corporal", "Cpl", "Senior Crewman", "SCr"),
                    ("Lance Corporal", "LCpl", "Crewman", "Cr"),
                    ("Private First Class", "PFC", "Crewman Apprentice", "CrApp"),
                    ("Private", "Pvt", "Crewman Recruit", "CrRec")
                ]
                
                for specialized_name, specialized_abbrev, standard_rank, standard_abbrev in marine_ranks:
                    if standard_rank.lower() == (current_rank or "").lower() or specialized_name.lower() == (current_rank or "").lower():
                        # Overwrite the row's 'Rank' field with the specialized name
                        old_rank = values.get('Rank')
                        if old_rank != specialized_name:
                            values['Rank'] = specialized_name
                            updates['Rank'] = specialized_name  # Will update Coda
                            changes.append(f"Changed rank from {old_rank} to {specialized_name}")
                            needs_update = True
                        
                        # Set the correct Marine abbreviation for nickname
                        marine_abbrev = specialized_abbrev
                        break
                
                if marine_abbrev:
                    # If the user doesn't have the correct marine rank prefix in their nickname, fix it
                    if not current_nick.startswith(f"{marine_abbrev} "):
                        # Remove any existing rank abbreviation from the front
                        base_name = current_nick
                        for abbr in ALL_RANK_ABBREVIATIONS:
                            if current_nick.startswith(f"{abbr} "):
                                base_name = current_nick[len(abbr)+1:]
                                break
                        
                        new_nick = f"{marine_abbrev} {base_name}"
                        if new_nick != current_nick:
                            try:
                                await member.edit(nick=new_nick)
                                changes.append(f"Updated nickname to '{new_nick}'")
                            except Exception as e:
                                logger.error(f"Error updating nickname for {member}: {e}")
                else:
                    logger.warning(f"Could not find Marine rank for standard rank: {current_rank}")
            
            # Backward compatibility for Marines in Tactical division
            elif fleet_wing == "Tactical" and specialization == "Marines":
                marine_abbrev = None
                if "Marines" in DIVISION_RANKS.get("Tactical", {}):
                    marine_ranks = DIVISION_RANKS["Tactical"]["Marines"]
                    for specialized_name, specialized_abbrev, standard_rank, standard_abbrev in marine_ranks:
                        if standard_rank.lower() == (current_rank or "").lower():
                            # Overwrite the row's 'Rank' field with the specialized name
                            old_rank = values.get('Rank')
                            if old_rank != specialized_name:
                                values['Rank'] = specialized_name
                                updates['Rank'] = specialized_name  # Will update Coda
                                changes.append(f"Changed rank from {old_rank} to {specialized_name}")
                                needs_update = True
                            
                            # Set the correct Marine abbreviation for nickname
                            marine_abbrev = specialized_abbrev
                            break
                
                if marine_abbrev:
                    # If the user doesn't have the correct marine rank prefix in their nickname, fix it
                    if not current_nick.startswith(f"{marine_abbrev} "):
                        # Remove any existing rank abbreviation from the front
                        base_name = current_nick
                        for abbr in ALL_RANK_ABBREVIATIONS:
                            if current_nick.startswith(f"{abbr} "):
                                base_name = current_nick[len(abbr)+1:]
                                break
                        
                        new_nick = f"{marine_abbrev} {base_name}"
                        if new_nick != current_nick:
                            try:
                                await member.edit(nick=new_nick)
                                changes.append(f"Updated nickname to '{new_nick}'")
                            except Exception as e:
                                logger.error(f"Error updating nickname for {member}: {e}")
                else:
                    logger.warning(f"Could not find Marine rank for standard rank: {current_rank}")
    
            else:
                # Regular rank handling for non-Marines
                rank_abbrev = None
            
                # First check for a division-specific rank abbreviation
                if current_rank and fleet_wing and specialization:
                    div_key = (fleet_wing.lower(), specialization.lower(), current_rank.lower())
                    if div_key in STANDARD_TO_DIVISION_RANK:
                        div_rank_name, div_abbrev = STANDARD_TO_DIVISION_RANK[div_key]
                        rank_abbrev = div_abbrev
                        # Update the rank field with the division-specific rank name
                        values[FIELD_RANK] = div_rank_name
                        logger.debug(f"Found fleet-specific rank: {div_rank_name} ({div_abbrev})")
                
                # Fall back to the standard abbreviation if no division-specific one was found
                if not rank_abbrev and current_rank:
                    rank_abbrev = RANK_ABBREVIATIONS.get(current_rank)
                
                logger.debug(f"Current nickname: '{current_nick}', rank: '{current_rank}', fleet wing: '{fleet_wing}', specialization: '{specialization}', abbrev: '{rank_abbrev}'")
                
                # Only proceed if we found a valid rank abbreviation
                if rank_abbrev:
                    # Check if the current nickname already has the correct rank abbreviation
                    if not current_nick.startswith(f"{rank_abbrev} "):
                        # Get base name (remove any existing rank abbreviation)
                        base_name = current_nick
                        for abbr in ALL_RANK_ABBREVIATIONS:
                            if current_nick.startswith(f"{abbr} "):
                                base_name = current_nick[len(abbr)+1:]
                                logger.debug(f"Found prefix '{abbr}', base name: '{base_name}'")
                                break
                        
                        # Create new nickname with correct rank
                        new_nick = f"{rank_abbrev} {base_name}"
                        
                        # Only update if it would change the nickname
                        if new_nick != current_nick:
                            try:
                                logger.info(f"Setting nickname: '{current_nick}' -> '{new_nick}'")
                                await member.edit(nick=new_nick)
                                changes.append(f"Updated nickname to {new_nick}")
                            except Exception as e:
                                logger.error(f"Error updating nickname: {e}")
    
            # Check if ID number format matches current rank
            if current_id and current_rank and current_rank in RANK_NUMBERS:
                parts = current_id.split('-')
                if len(parts) == 3:
                    div_code, rank_num, unique = parts
                    expected_rank_num = str(RANK_NUMBERS[current_rank]).zfill(2)
                    
                    if rank_num != expected_rank_num:
                        new_id = f"{div_code}-{expected_rank_num}-{unique}"
                        logger.info(f"Updating ID number: {current_id} -> {new_id}")
                        updates[FIELD_ID_NUMBER] = new_id
                        changes.append(f"Updated ID number from {current_id} to {new_id}")
                        needs_update = True
                        
            # Add or fix ship assignment if needed
            await self.fix_ship_assignment(member, values, updates, changes)
            if 'Ship Assignment' in updates:
                needs_update = True
    
            # Update profile if needed
            if needs_update:
                try:
                    success = await self.update_profile(
                        member,
                        updates,
                        reason="Automatic profile validation fix"
                    )
                    if not success:
                        logger.error(f"Failed to update profile for {member.id}")
                except Exception as e:
                    logger.error(f"Error in update_profile: {e}")
    
            return bool(changes), changes
            
        except Exception as e:
            logger.error(f"Error validating profile for {member.id}: {e}", exc_info=True)
            return False, []
    
    async def fix_ship_assignment(self, member: discord.Member, values: dict, updates: dict, changes: list) -> bool:
        """
        Fix ship assignment if needed (consolidated helper method).
        
        Args:
            member: The Discord member
            values: The profile values
            updates: Dictionary to track updates
            changes: List to track changes made
            
        Returns:
            bool: True if ship assignment was fixed, False otherwise
        """
        try:
            # Check ship assignment
            ship_assignment = values.get('Ship Assignment')
            if ship_assignment is None or ship_assignment == '':
                # Only set a default if the field is truly empty
                updates['Ship Assignment'] = 'Unassigned'
                changes.append("Added default ship assignment")
                return True
                
            # If ship is "Unassigned" but should be something else based on Command_History
            if ship_assignment == 'Unassigned':
                command_history = values.get('Command_History', '')
                if '[Current]' in command_history:
                    # Extract the current ship from Command_History
                    try:
                        ships = []
                        for part in command_history.split(','):
                            part = part.strip()
                            if '[Current]' in part:
                                ship = part.split('[Current]')[0].strip()
                                ships.append(ship)
                                
                        if ships:
                            # Use the first current ship
                            correct_ship = ships[0]
                            updates['Ship Assignment'] = correct_ship
                            changes.append(f"Fixed ship assignment from 'Unassigned' to '{correct_ship}'")
                            return True
                    except Exception as ship_err:
                        logger.error(f"Error extracting ships from command history: {ship_err}")
            return False
        except Exception as e:
            logger.error(f"Error in fix_ship_assignment: {e}")
            return False

# Add to create_profile_embed method in ProfileCog to directly access the raw values

    async def create_profile_embed(
        self,
        member: discord.Member,
        member_row: dict,
        viewer: discord.Member,
        is_mobile: bool = False
    ) -> discord.Embed:
        """Enhanced profile embed creation with direct field access."""
        values = member_row.get('values', {})
        
        # Debug: Log raw values to help troubleshoot field access
        logger.debug(f"Raw profile values for {member.id}: {values.keys()}")
        
        # Get and validate clearance levels
        target_clearance = SecurityClearance.get_clearance_from_member(member)
        viewer_clearance = SecurityClearance.get_clearance_from_member(viewer)
        
        # Create base embed
        embed = discord.Embed(
            title="",
            description=(
                self.formatter.create_mobile_header(values.get("Rank", 'N/A'), values, member)
                if is_mobile else
                self.formatter.create_header(values.get("Rank", 'N/A'), values, member)
            ),
            color=discord.Color.from_rgb(34, 51, 34)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
    
        # Add basic fields (always visible)
        embed.add_field(
            name="IDENTIFICATION",
            value=self.formatter.format_basic_info(values, is_mobile),
            inline=False
        )
    
        # Add quick stats
        embed.add_field(
            name="STATISTICS",
            value=self.formatter.format_quick_stats(values, is_mobile),
            inline=False
        )
    
        # Add service record
        embed.add_field(
            name="SERVICE RECORD",
            value=self.formatter.format_service_record(values, is_mobile),
            inline=False
        )
    
        # Add grouped certifications
        embed.add_field(
            name="CERTIFICATIONS",
            value=self.formatter.format_grouped_certifications(values, is_mobile),
            inline=False
        )
    
        # Add awards with direct field access to ensure it works
        awards = []
        if 'Awards' in values and values['Awards']:
            from .utils import parse_list_field
            awards = parse_list_field(values['Awards'])
        
        if awards:
            awards_text = "```yaml\n" + "\n".join([f"◈ {award}" for award in awards]) + "\n```"
        else:
            awards_text = "```yaml\nNo decorations awarded\n```"
            
        embed.add_field(
            name="DECORATIONS AND AWARDS",
            value=awards_text,
            inline=False
        )
    
        # Add classified fields if authorized
        if SecurityClearance.can_view_full_profile(viewer_clearance, target_clearance):
            await self._add_classified_fields(embed, values, member_row, is_mobile)
    
        # Add security footer
        self._add_security_footer(embed, target_clearance, viewer)
    
        return embed

    async def create_service_record_embed(
        self,
        member: discord.Member,
        member_row: dict,
        viewer: discord.Member,
        is_mobile: bool = False
    ) -> discord.Embed:
        """Create service record embed with proper security handling."""
        values = member_row.get('values', {})
        
        target_clearance = SecurityClearance.get_clearance_from_member(member)
        viewer_clearance = SecurityClearance.get_clearance_from_member(viewer)
        
        embed = discord.Embed(
            title="SERVICE RECORD",
            color=discord.Color.from_rgb(34, 51, 34)
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        # Basic service info (visible to all)
        join_date = values.get(FIELD_JOIN_DATE, 'Unknown')
        service_time = calculate_service_time(join_date)
        missions_completed = values.get(FIELD_MISSION_COUNT, 0)
        
        # Get fleet wing (with backward compatibility)
        fleet_wing = values.get(FIELD_FLEET_WING)
        if not fleet_wing:
            division = values.get(FIELD_DIVISION, 'N/A')
            fleet_wing = DIVISION_TO_FLEET_WING.get(division, division)
        
        ship_assignment = values.get(FIELD_SHIP_ASSIGNMENT, 'Unassigned')
        
        basic_info = (
            f"Time in Service: {service_time}\n"
            f"Missions Completed: {missions_completed}\n"
            f"Current Assignment: {fleet_wing}\n"
            f"Ship Assignment: {ship_assignment}"
        )
        
        embed.add_field(
            name="SERVICE INFORMATION",
            value=f"```yaml\n{basic_info}\n```",
            inline=False
        )

        # Add certifications
        embed.add_field(
            name="CERTIFICATIONS",
            value=self.formatter.format_certifications(values, is_mobile),
            inline=False
        )

        # Add classified information if authorized
        if SecurityClearance.can_view_full_profile(viewer_clearance, target_clearance):
            # Add evaluation data if available
            strategic_assessment = values.get(FIELD_STRATEGIC_ASSESSMENT)
            if strategic_assessment:
                embed.add_field(
                    name="PERFORMANCE EVALUATION",
                    value=f"```yaml\n{strategic_assessment}\n```",
                    inline=False
                )
                
            # Add command evaluation if available
            command_eval = values.get(FIELD_COMMAND_EVALUATION)
            if command_eval:
                embed.add_field(
                    name="COMMAND ASSESSMENT",
                    value=f"```yaml\n{command_eval}\n```",
                    inline=False
                )

            # Add special operations history if available
            spec_ops = values.get(FIELD_SPECIAL_OPERATIONS)
            if spec_ops:
                embed.add_field(
                    name="SPECIAL OPERATIONS HISTORY",
                    value=f"```yaml\n{spec_ops}\n```",
                    inline=False
                )

        # Add footer with security classification
        watermark = self.watermark.generate_pattern(target_clearance.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"{watermark} • Generated: {timestamp} UTC")

        return embed

    async def create_combat_log_embed(
        self, 
        member: discord.Member, 
        member_row: dict, 
        viewer: discord.Member,
        is_mobile: bool = False
    ) -> discord.Embed:
        """Create combat log embed."""
        values = member_row.get('values', {})
        target_clearance = SecurityClearance.get_clearance_from_member(member)
        viewer_clearance = SecurityClearance.get_clearance_from_member(viewer)

        embed = discord.Embed(title="COMBAT RECORD", color=discord.Color.from_rgb(34, 51, 34))
        embed.set_thumbnail(url=member.display_avatar.url)

        # Combat decorations (visible to all)
        awards = parse_list_field(values.get(FIELD_AWARDS, []))
        combat_awards = [f"◈ {a}" for a in awards]
        if combat_awards:
            combat_record = "```yaml\n" + "\n".join(combat_awards) + "```"
        else:
            combat_record = "```yaml\nNo combat decorations recorded```"

        embed.add_field(name="COMBAT DECORATIONS", value=combat_record, inline=False)

        # Add classified combat information if authorized
        if SecurityClearance.can_view_full_profile(viewer_clearance, target_clearance):
            combat_missions = values.get(FIELD_COMBAT_MISSIONS)
            if combat_missions:
                embed.add_field(
                    name="CLASSIFIED COMBAT OPERATIONS",
                    value=f"```yaml\n{combat_missions}\n```",
                    inline=False
                )

        watermark = self.watermark.generate_pattern(target_clearance.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"{watermark} • Generated: {timestamp} UTC")

        return embed

    async def create_qualifications_embed(
        self, 
        member: discord.Member, 
        member_row: dict, 
        viewer: discord.Member,
        is_mobile: bool = False
    ) -> discord.Embed:
        """Create qualifications embed."""
        values = member_row.get('values', {})
        target_clearance = SecurityClearance.get_clearance_from_member(member)
        viewer_clearance = SecurityClearance.get_clearance_from_member(viewer)

        embed = discord.Embed(title="QUALIFICATIONS AND TRAINING", color=discord.Color.from_rgb(34, 51, 34))
        embed.set_thumbnail(url=member.display_avatar.url)

        # Basic certifications (visible to all)
        embed.add_field(
            name="CERTIFIED QUALIFICATIONS",
            value=self.formatter.format_certifications(values, is_mobile),
            inline=False
        )

        # Add classified qualifications if authorized
        if SecurityClearance.can_view_full_profile(viewer_clearance, target_clearance):
            special_ops = values.get(FIELD_SPECIAL_OPERATIONS)
            if special_ops:
                embed.add_field(
                    name="SPECIALIZED TRAINING",
                    value=f"```yaml\n{special_ops}\n```",
                    inline=False
                )

        watermark = self.watermark.generate_pattern(target_clearance.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"{watermark} • Generated: {timestamp} UTC")

        return embed

    async def create_mission_log_embed(
        self, 
        member: discord.Member, 
        member_row: dict, 
        viewer: discord.Member,
        is_mobile: bool = False
    ) -> discord.Embed:
        """Create mission log embed."""
        values = member_row.get('values', {})
        target_clearance = SecurityClearance.get_clearance_from_member(member)
        viewer_clearance = SecurityClearance.get_clearance_from_member(viewer)

        embed = discord.Embed(title="MISSION LOG", color=discord.Color.from_rgb(34, 51, 34))
        embed.set_thumbnail(url=member.display_avatar.url)

        # Basic mission log (visible to all)
        embed.add_field(
            name="COMPLETED MISSIONS",
            value=self.formatter.format_mission_log(values, is_mobile),
            inline=False
        )

        # Add classified mission information if authorized
        if SecurityClearance.can_view_full_profile(viewer_clearance, target_clearance):
            strategic_planning = values.get(FIELD_STRATEGIC_PLANNING)
            if strategic_planning:
                embed.add_field(
                    name="STRATEGIC OPERATIONS",
                    value=f"```yaml\n{strategic_planning}\n```",
                    inline=False
                )

        watermark = self.watermark.generate_pattern(target_clearance.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"{watermark} • Generated: {timestamp} UTC")

        return embed

    async def create_classified_info_embed(
        self, 
        member: discord.Member, 
        member_row: dict, 
        viewer: discord.Member,
        is_mobile: bool = False
    ) -> Optional[discord.Embed]:
        """Create classified information embed if authorized."""
        values = member_row.get('values', {})
        target_clearance = SecurityClearance.get_clearance_from_member(member)
        viewer_clearance = SecurityClearance.get_clearance_from_member(viewer)

        if not SecurityClearance.can_view_full_profile(viewer_clearance, target_clearance):
            return None

        embed = discord.Embed(title="CLASSIFIED INFORMATION", color=discord.Color.from_rgb(34, 51, 34))
        embed.set_thumbnail(url=member.display_avatar.url)

        classified_info = self.formatter.format_classified_info(values, values.get(FIELD_RANK, 'N/A'))
        if classified_info:
            embed.add_field(name="CLASSIFIED DATA", value=classified_info, inline=False)

        # Add additional classified fields
        for field_name, field_title in [
            (FIELD_STRATEGIC_ASSESSMENT, "STRATEGIC ASSESSMENT"),
            (FIELD_COMMAND_EVALUATION, "COMMAND EVALUATION"),
            (FIELD_SPECIAL_OPERATIONS, "SPECIAL OPERATIONS")
        ]:
            if values.get(field_name):
                embed.add_field(
                    name=field_title,
                    value=f"```yaml\n{values[field_name]}\n```",
                    inline=False
                )

        watermark = self.watermark.generate_pattern(target_clearance.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"{watermark} • Generated: {timestamp} UTC")

        return embed
        
    async def _add_classified_fields(
        self,
        embed: discord.Embed,
        values: Dict[str, Any],
        member_row: Dict[str, Any],
        is_mobile: bool = False
    ):
        """Add classified fields to embed with proper security checks."""
        rank = values.get(FIELD_RANK, 'N/A')
        
        # Add classified information if available
        classified_info = self.formatter.format_classified_info(values, rank)
        if classified_info:
            embed.add_field(
                name="CLASSIFIED INFORMATION",
                value=classified_info,
                inline=False
            )

        # Add specialized information fields
        # On mobile, only show the most critical specialized information
        if is_mobile:
            # Just show the most important field for mobile
            if values.get(FIELD_STRATEGIC_ASSESSMENT):
                embed.add_field(
                    name="STRATEGIC ASSESSMENT",
                    value=f"```yaml\n{values[FIELD_STRATEGIC_ASSESSMENT]}\n```",
                    inline=False
                )
        else:
            # Show all specialized information fields for desktop
            specialized_fields = [
                (FIELD_SPECIAL_OPERATIONS, 'SPECIAL OPERATIONS'),
                (FIELD_STRATEGIC_PLANNING, 'STRATEGIC PLANNING'),
                (FIELD_COMBAT_MISSIONS, 'COMBAT MISSIONS'),
                (FIELD_STRATEGIC_ASSESSMENT, 'STRATEGIC ASSESSMENT'),
                (FIELD_COMMAND_EVALUATION, 'COMMAND EVALUATION')
            ]

            for field_key, field_name in specialized_fields:
                if values.get(field_key):
                    embed.add_field(
                        name=field_name,
                        value=f"```yaml\n{values[field_key]}\n```",
                        inline=False
                    )

    def _add_security_footer(
        self,
        embed: discord.Embed,
        clearance: SecurityClearance,
        viewer: discord.Member
    ):
        """Add security classification footer to embed."""
        watermark = self.watermark.generate_pattern(clearance.name)
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(
            text=f"{watermark} • Generated: {timestamp} UTC • "
                 f"Viewed by: {viewer.display_name}"
        )

    async def award_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Provides autocomplete suggestions for the 'award' argument."""
        # We'll build a list of potential matches
        filtered = [a for a in AVAILABLE_AWARDS if current.lower() in a.lower()]
    
        choices = []
        for aw in filtered:
            # Truncate the displayed label to 100 characters
            truncated_label = aw[:100]
    
            # The 'value' will be the short name (before the dash), also truncated
            short_portion = aw.split(' - ')[0]
            truncated_value = short_portion[:100]
    
            # Build the Choice
            choices.append(
                app_commands.Choice(
                    name=truncated_label,
                    value=truncated_value
                )
            )
    
        # Return up to 25 results
        return choices[:25]

    async def process_bulk_awards(self, members, award, citation, awarded_by=None):
        """Process awards for multiple members."""
        results = []
        
        for member in members:
            try:
                success, result = await self.add_award_to_member(
                    member=member,
                    award=award,
                    citation=citation,
                    awarded_by=awarded_by,
                    notify_member=True
                )
                
                if success:
                    results.append((member, True, "Success"))
                else:
                    results.append((member, False, result))
                    
            except Exception as e:
                results.append((member, False, f"Error: {str(e)}"))
                
        return results

    async def add_mission_completion(
        self,
        user_id: int,
        mission_name: str,
        mission_type: str,
        role: str,
        ship: str
    ) -> bool:
        """Add mission completion to user's profile."""
        try:
            guild = self.bot.get_guild(GUILD_ID)
            if not guild:
                logger.error(f"Could not find guild with ID {GUILD_ID}")
                return False
                
            member = guild.get_member(user_id)
            if not member:
                logger.error(f"Could not find member with ID {user_id}")
                return False
    
            member_row = await self.get_member_row(user_id)
            if not member_row:
                logger.error(f"No profile found for user {user_id}")
                return False
    
            values = member_row.get('values', {})
            completed_missions = parse_list_field(values.get(FIELD_COMPLETED_MISSIONS, []))
            mission_types = parse_list_field(values.get(FIELD_MISSION_TYPES, []))
            
            # Format new mission completion with in-game date (current date + 930 years)
            current_date = datetime.now(timezone.utc)
            ingame_year = current_date.year + 930
            ingame_date = f"{ingame_year}-{current_date.month:02d}-{current_date.day:02d}"
            
            new_completion = f"{mission_name} ({mission_type}) - {role} on {ship} - {ingame_date}"
            completed_missions.append(new_completion)
            
            # Update mission stats
            mission_count = int(values.get(FIELD_MISSION_COUNT, 0)) + 1
            if mission_type not in mission_types:
                mission_types.append(mission_type)
    
            updates = {
                FIELD_COMPLETED_MISSIONS: ','.join(completed_missions[-10:]),  # Keep last 10
                FIELD_MISSION_COUNT: mission_count,
                FIELD_MISSION_TYPES: ','.join(mission_types)
            }
    
            success = await self.update_profile(
                member,
                updates,
                reason="Mission completion"
            )
            
            if success:
                # Dispatch mission_completed event
                await self.dispatch_event(
                    'mission_completed',
                    user_id=user_id,
                    mission_name=mission_name,
                    mission_type=mission_type,
                    role=role,
                    ship=ship,
                    timestamp=ingame_date
                )
                
            return success
    
        except Exception as e:
            logger.error(f"Error adding mission completion for user {user_id}: {e}")
            return False

    async def restore_ship_assignment(self, member_id: int) -> bool:
        """Fix the ship assignment if it was incorrectly set to Unassigned."""
        try:
            # Get the member's profile
            member_row = await self.get_member_row(member_id)
            if not member_row:
                logger.error(f"No profile found for member {member_id}")
                return False
                
            values = member_row.get('values', {})
            updates = {}
            changes = []
            
            # Use the consolidated helper method
            fixed = await self.fix_ship_assignment(
                self.bot.get_guild(int(GUILD_ID)).get_member(member_id),
                values,
                updates,
                changes
            )
            
            # If updates were made, apply them
            if updates and 'Ship Assignment' in updates:
                success = await self.update_profile(
                    self.bot.get_guild(int(GUILD_ID)).get_member(member_id),
                    updates,
                    reason="Fixing incorrect ship assignment"
                )
                
                if success:
                    logger.info(f"Successfully restored ship assignment for {member_id}")
                    return True
                    
            return fixed
        except Exception as e:
            logger.error(f"Error in restore_ship_assignment: {e}")
            return False

    # Fleet System Commands
    @app_commands.command(
        name="fleet_report",
        description="Generate a report of all members in a fleet wing"
    )
    @app_commands.choices(fleet_wing=[
        app_commands.Choice(name="Navy Fleet", value="Navy Fleet"),
        app_commands.Choice(name="Marine Expeditionary Force", value="Marine Expeditionary Force"),
        app_commands.Choice(name="Industrial & Logistics Wing", value="Industrial & Logistics Wing"),
        app_commands.Choice(name="Support & Medical Fleet", value="Support & Medical Fleet"),
        app_commands.Choice(name="Exploration & Intelligence Wing", value="Exploration & Intelligence Wing"),
        app_commands.Choice(name="Command Staff", value="Command Staff"),
        app_commands.Choice(name="Non-Wing", value="Non-Wing"),
        app_commands.Choice(name="HQ", value="HQ"),
        app_commands.Choice(name="Ambassador", value="Ambassador"),
        app_commands.Choice(name="Associate", value="Associate")
    ])
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def fleet_report(
        self,
        interaction: discord.Interaction,
        fleet_wing: str
    ):
        """Generate a report showing all members in a specified fleet wing."""
        # Log command usage
        self.log_command_use(interaction, "fleet_report")
        
        await interaction.response.defer()
        
        try:
            # Get all members in the fleet wing from Coda
            from .constants import DOC_ID, TABLE_ID, FIELD_FLEET_WING, FIELD_DIVISION
            
            # Need to check both fields during transition period
            query = f'"{FIELD_FLEET_WING}":"{fleet_wing}" OR "{FIELD_DIVISION}":"{fleet_wing}"'
            
            # Also check old division name that maps to this wing
            for old_div, new_wing in DIVISION_TO_FLEET_WING.items():
                if new_wing == fleet_wing:
                    query += f' OR "{FIELD_DIVISION}":"{old_div}"'
            
            async with self.db_lock:  # Add lock for database operations
                rows = await self.coda_client.get_rows(
                    DOC_ID,
                    TABLE_ID,
                    query=query,
                    limit=100  # Increased limit to handle larger wings
                )
            
            if not rows:
                await interaction.followup.send(f"No members found in {fleet_wing} wing.", ephemeral=True)
                return
            
            # Create a list of (member, data) tuples for all members we can find
            members_data = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = interaction.guild.get_member(int(discord_id))
                        if member:
                            members_data.append((member, row))
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            if not members_data:
                await interaction.followup.send(
                    f"Found {len(rows)} records, but none of the members are in this server.",
                    ephemeral=True
                )
                return
            
            # Create initial embed to display
            from .ui import FleetReportView
            view = FleetReportView(self, fleet_wing, members_data)
            embed = await view.get_current_page_embed()
            
            await interaction.followup.send(embed=embed, view=view)
            
            # Dispatch fleet_report_generated event
            await self.dispatch_event(
                'fleet_report_generated',
                fleet_wing=fleet_wing,
                member_count=len(members_data)
            )
            
        except Exception as e:
            logger.error(f"Error generating fleet report: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while generating the report.", ephemeral=True)

    @app_commands.command(
        name="set_ship_assignment",
        description="Assign a member to a ship"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def set_ship_assignment(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        ship_name: str
    ):
        """Assign a member to a specific ship."""
        # Log command usage
        self.log_command_use(interaction, "set_ship_assignment")
        
        await interaction.response.defer()
        
        try:
            # Get the member's profile
            member_row = await self.get_member_row(member.id)
            if not member_row:
                await interaction.followup.send(f"No profile found for {member.mention}.", ephemeral=True)
                return
            
            # Update the ship assignment
            success = await self.update_profile(
                member,
                {'Ship Assignment': ship_name},
                f"Ship assignment updated by {interaction.user}"
            )
            
            if success:
                await interaction.followup.send(f"✅ {member.mention} has been assigned to {ship_name}.")
                
                # Log the assignment
                await self.audit_logger.log_action(
                    'ship_assignment',
                    interaction.user,
                    member,
                    f"Assigned to ship: {ship_name}"
                )
                
                # Dispatch ship_assignment_updated event
                await self.dispatch_event(
                    'ship_assignment_updated',
                    member_id=member.id,
                    ship_name=ship_name,
                    updated_by=interaction.user.id
                )
            else:
                await interaction.followup.send("❌ Failed to update ship assignment.", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error setting ship assignment: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while updating ship assignment.", ephemeral=True)

    @app_commands.command(
            name="migrate_to_fleet",
            description="Migrate profiles from division-based to fleet-based structure"
    )
    async def migrate_to_fleet_command(
        self,
        interaction: discord.Interaction
    ):
        """Command to migrate the system to fleet-based structure."""
        # Log command usage
        self.log_command_use(interaction, "migrate_to_fleet")
        
        # Check if user is server owner or has Admin role
        if not (interaction.user.id == interaction.guild.owner_id or 
                any(role.name == 'Command Staff' for role in interaction.user.roles)):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # Import the migration function
            from .migration import run_fleet_system_migration
            
            # Start the migration
            await interaction.followup.send("Starting migration to fleet-based system... This may take a while.")
            
            # Run the migration
            success = await run_fleet_system_migration(self.bot, interaction.guild.id, self)
            
            if success:
                await interaction.followup.send("✅ Migration to fleet-based system completed successfully!")
            else:
                await interaction.followup.send("⚠️ Migration completed with some errors. Check the logs for details.")
                
        except Exception as e:
            logger.error(f"Error in migration: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred during migration. Check the logs for details.")

    # Original commands unchanged
    @app_commands.command(
        name='profile',
        description='Display the military service record of a member'
    )
    @app_commands.describe(member='The member whose profile to display (optional)')
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Display a member's military service record with proper security clearance handling."""
        # Log command usage
        self.log_command_use(interaction, "profile")
        
        await interaction.response.defer()
        target_member = member or interaction.user
        viewer = interaction.user
    
        logger.debug(f"Retrieving profile for {target_member.name} (ID: {target_member.id})")
        
        try:
            # Try to fix ship assignment first if needed
            await self.restore_ship_assignment(target_member.id)
            
            # Force a fresh fetch from Coda to avoid cached data issues
            await self.cache.invalidate(str(target_member.id))
            
            # Get the member row
            member_row = await self.get_member_row(target_member.id)
            if not member_row:
                await interaction.followup.send("❌ No service record found.", ephemeral=True)
                return
    
            # Map and validate the profile data, computing the rank index
            validated_data = self.map_and_validate_profile(member_row, target_member.id)
            if not validated_data:
                await interaction.followup.send("❌ Invalid service record data.", ephemeral=True)
                return
    
            # Update the member_row with the computed rank index so that the embed uses the correct value
            if "rank_index" in validated_data:
                member_row["values"]["rank_index"] = validated_data["rank_index"]
    
            # Validate and potentially fix profile data (which may also update nicknames or other fields)
            was_fixed, changes = await self.validate_member_profile(target_member, member_row)
            if was_fixed:
                # Refetch the member row after changes have been applied
                await self.cache.invalidate(str(target_member.id))
                member_row = await self.get_member_row(target_member.id)
                
                # Optionally, notify the user of the automatic updates
                if viewer == target_member or any(role.name in ['Admin', 'Command Staff', 'Fleet Command'] for role in viewer.roles):
                    change_message = "\n".join([f"• {change}" for change in changes])
                    await interaction.followup.send(
                        f"ℹ️ Profile data was automatically updated:\n{change_message}",
                        ephemeral=True
                    )
    
            # Create the embed using the updated member_row
            embed = await self.create_profile_embed(target_member, member_row, viewer)
            view = ProfileView(self, target_member, member_row, viewer)
            await interaction.followup.send(embed=embed, view=view)
    
        except Exception as e:
            logger.error(f"Error creating profile for {target_member}: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while retrieving the service record.",
                ephemeral=True
            )

    @app_commands.command(
        name="add_award",
        description="Add an award to a member's profile"
    )
    @app_commands.autocomplete(award=award_autocomplete)
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def add_award(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        award: str,
        citation: str
    ):
        """
        Add an award to a member's profile.
        Updates both Discord roles and Coda database.
        """
        # Log command usage
        self.log_command_use(interaction, "add_award")
        
        await interaction.response.defer()
        
        progress_embed = discord.Embed(
            title="Adding Award...",
            description=f"Processing award for {member.mention}",
            color=discord.Color.blue()
        )
        progress_embed.add_field(name="Status", value="🔍 Validating award...", inline=False)
        progress_message = await interaction.followup.send(embed=progress_embed)
    
        try:
            # Step 1: First validate the award (pre-check to provide better UI feedback)
            full_award = None
            for entry in AVAILABLE_AWARDS:
                short_name = entry.split(' - ')[0]
                if short_name.startswith(award):
                    full_award = entry
                    break
    
            if not full_award:
                progress_embed.color = discord.Color.red()
                progress_embed.add_field(name="Error", value="❌ Invalid or unknown award specified.", inline=False)
                await progress_message.edit(embed=progress_embed)
                return
    
            # Update progress
            progress_embed.set_field_at(0, name="Status", value="✅ Award validated\n🔍 Fetching member profile...", inline=False)
            await progress_message.edit(embed=progress_embed)
    
            # Step 2: Check if the profile exists
            member_row = await self.get_member_row(member.id)
            if not member_row:
                progress_embed.color = discord.Color.red()
                progress_embed.add_field(name="Error", value="❌ No profile found for this member.", inline=False)
                await progress_message.edit(embed=progress_embed)
                return
    
            # Update progress
            progress_embed.set_field_at(0, name="Status", value="✅ Award validated\n✅ Member profile found\n🔍 Processing award...", inline=False)
            await progress_message.edit(embed=progress_embed)
    
            # Step 3: Check if member already has this award
            values = member_row.get('values', {})
            current_awards = parse_list_field(values.get(FIELD_AWARDS, []))
            short_portion = full_award.split(' - ')[0]
            
            if any(a.startswith(short_portion) for a in current_awards):
                progress_embed.color = discord.Color.red()
                progress_embed.add_field(name="Error", value=f"❌ {member.mention} already has the {short_portion} award.", inline=False)
                await progress_message.edit(embed=progress_embed)
                return
    
            # Update progress for database update
            progress_embed.set_field_at(0, name="Status", value="✅ Award validated\n✅ Member profile found\n✅ Award processed\n🔍 Updating database...", inline=False)
            await progress_message.edit(embed=progress_embed)
            
            # Step 4: Use the internal method to add the award
            success, result = await self.add_award_to_member(
                member=member,
                award=award,
                citation=citation,
                awarded_by=interaction.user.id,
                notify_member=True  # Send DM
            )
            
            if success:
                # Handle success
                award_details = result
                short_portion = award_details["award"]
                timestamp = award_details["timestamp"]
                role_added = award_details["role_added"]
                dm_sent = award_details["dm_sent"]
                
                # Create detailed success embed
                progress_embed.color = discord.Color.green()
                progress_embed.title = "Award Added Successfully"
                
                # Include all status steps from original implementation
                progress_embed.set_field_at(
                    0, 
                    name="Status", 
                    value=(
                        "✅ Award validated\n✅ Member profile found\n"
                        "✅ Award processed\n✅ Database updated\n"
                        f"{'✅' if role_added else '⚠️'} Role assigned\n"
                        f"{'✅' if dm_sent else '⚠️'} Notification sent"
                    ),
                    inline=False
                )
                
                # Add award details to the embed
                progress_embed.add_field(name="Award", value=short_portion, inline=True)
                progress_embed.add_field(name="Citation", value=citation, inline=True)
                progress_embed.add_field(name="Date", value=timestamp, inline=True)
                
                # Add notes for any warnings
                if not role_added:
                    progress_embed.add_field(
                        name="Note",
                        value="⚠️ Could not assign Discord role. Missing permissions or role creation failed.",
                        inline=False
                    )
                    
                if not dm_sent:
                    progress_embed.add_field(
                        name="Note",
                        value="⚠️ Unable to send DM notification to the member",
                        inline=False
                    )
            else:
                # Handle error
                progress_embed.color = discord.Color.red()
                progress_embed.add_field(name="Error", value=f"❌ {result}", inline=False)
                
            await progress_message.edit(embed=progress_embed)
            
        except Exception as e:
            logger.error(f"Error adding award: {e}", exc_info=True)
            progress_embed.color = discord.Color.red()
            progress_embed.add_field(
                name="Error", 
                value=f"❌ An error occurred: {str(e)}", 
                inline=False
            )
            await progress_message.edit(embed=progress_embed)

    @app_commands.command(
        name="remove_award", 
        description="Remove an award from a member's profile"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def remove_award(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        award: str
    ):
        """Remove an award from a member's profile."""
        # Log command usage
        self.log_command_use(interaction, "remove_award")
        
        await interaction.response.defer()

        try:
            member_row = await self.get_member_row(member.id)
            if not member_row:
                await interaction.followup.send("❌ No profile found for this member.", ephemeral=True)
                return

            values = member_row.get('values', {})
            current_awards = parse_list_field(values.get(FIELD_AWARDS, []))
            
            # Find and remove the award
            updated_awards = [a for a in current_awards if not a.startswith(award)]
            
            if len(updated_awards) == len(current_awards):
                await interaction.followup.send("❌ Award not found in member's profile.", ephemeral=True)
                return

            # Try to remove the Discord role if it exists
            award_role = discord.utils.get(interaction.guild.roles, name=award)
            if award_role and award_role in member.roles:
                try:
                    await member.remove_roles(award_role, reason=f"Award removed by {interaction.user}")
                    logger.info(f"Removed award role {award} from {member.name}")
                except Exception as e:
                    logger.error(f"Error removing award role: {e}")
                    await interaction.followup.send(
                        "⚠️ Could not remove the Discord role, but will update the profile.",
                        ephemeral=True
                    )

            success = await self.update_profile(
                member,
                {FIELD_AWARDS: ','.join(updated_awards)},
                f"Award removed by {interaction.user}"
            )

            if success:
                await interaction.followup.send(f"✅ Successfully removed {award} from {member.mention}'s profile.")
                
                # Log the action
                await self.audit_logger.log_action(
                    'award_removed',
                    interaction.user,
                    member,
                    f"Removed award: {award}"
                )
                
                # Dispatch award_removed event
                await self.dispatch_event(
                    'award_removed',
                    member_id=member.id,
                    award=award,
                    removed_by=interaction.user.id
                )
            else:
                await interaction.followup.send("❌ Failed to update profile.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error removing award: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while removing the award.", ephemeral=True)

    @app_commands.command(
        name="bulk_award",
        description="Add an award to multiple members at once"
    )
    @app_commands.autocomplete(award=award_autocomplete)
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def bulk_award(
        self,
        interaction: discord.Interaction,
        award: str,
        citation: str
    ):
        """Add an award to multiple members - opens a member selection modal."""
        # Log command usage
        self.log_command_use(interaction, "bulk_award")
        
        modal = BulkAwardModal(self, award, citation)
        await interaction.response.send_modal(modal)

    # Import command methods from ProfileCommandExtensions
    @app_commands.command(
        name="division_report",
        description="Generate a report of all members in a division (legacy command)"
    )
    @app_commands.choices(division=[
        app_commands.Choice(name="Command Staff", value="Command Staff"),
        app_commands.Choice(name="Tactical", value="Tactical"),
        app_commands.Choice(name="Operations", value="Operations"),
        app_commands.Choice(name="Support", value="Support"),
        app_commands.Choice(name="Non-Division", value="Non-Division"),
        app_commands.Choice(name="HQ", value="HQ"),
        app_commands.Choice(name="Ambassador", value="Ambassador"),
        app_commands.Choice(name="Associate", value="Associate")
    ])
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def division_report(
        self,
        interaction: discord.Interaction,
        division: str
    ):
        """Generate a report showing all members in a specified division."""
        # Log command usage
        self.log_command_use(interaction, "division_report")
        
        await interaction.response.defer()
        
        try:
            # Get all members in the division from Coda
            query = f'"Division":"{division}"'
            
            async with self.db_lock:  # Add lock for database operations
                rows = await self.coda_client.get_rows(
                    DOC_ID,
                    TABLE_ID,
                    query=query,
                    limit=100  # Increased limit to handle larger divisions
                )
            
            if not rows:
                await interaction.followup.send(f"No members found in {division} division.", ephemeral=True)
                return
            
            # Create a list of (member, data) tuples for all members we can find
            members_data = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = interaction.guild.get_member(int(discord_id))
                        if member:
                            members_data.append((member, row))
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            if not members_data:
                await interaction.followup.send(
                    f"Found {len(rows)} records, but none of the members are in this server.",
                    ephemeral=True
                )
                return
            
            # Create initial embed to display
            view = DivisionReportView(self, division, members_data)
            embed = await view.get_current_page_embed()
            
            await interaction.followup.send(embed=embed, view=view)
            
            # Dispatch division_report_generated event
            await self.dispatch_event(
                'division_report_generated',
                division=division,
                member_count=len(members_data)
            )
            
        except Exception as e:
            logger.error(f"Error generating division report: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while generating the report.", ephemeral=True)

    @app_commands.command(
        name="compare_profiles",
        description="Compare two members' profiles side by side"
    )
    async def compare_profiles(
        self,
        interaction: discord.Interaction,
        member1: discord.Member,
        member2: discord.Member
    ):
        """Compare two member profiles side by side."""
        # Log command usage
        self.log_command_use(interaction, "compare_profiles")
        
        await interaction.response.defer()
        
        try:
            # Get profile data for both members
            data1 = await self.get_member_row(member1.id)
            data2 = await self.get_member_row(member2.id)
            
            if not data1:
                await interaction.followup.send(f"No profile found for {member1.mention}.", ephemeral=True)
                return
                
            if not data2:
                await interaction.followup.send(f"No profile found for {member2.mention}.", ephemeral=True)
                return
            
            # Create the comparison view
            view = ComparisonView(self, member1, member2, data1, data2, interaction.user)
            embed = await view.create_comparison_embed()
            
            # Try to get comparison chart if available
            try:
                from .visualizations import generate_service_comparison
                chart = await generate_service_comparison(
                    data1.get('values', {}), 
                    data2.get('values', {}),
                    member1.display_name,
                    member2.display_name
                )
                
                if chart:
                    await interaction.followup.send(embed=embed, view=view, file=chart)
                else:
                    await interaction.followup.send(embed=embed, view=view)
            except Exception as chart_err:
                logger.warning(f"Chart generation failed: {chart_err}")
                await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error comparing profiles: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while comparing profiles.", ephemeral=True)

    @app_commands.command(
        name="export_profile",
        description="Export a member's profile as a PDF document"
    )
    async def export_profile(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):
        """Export a member's profile as a PDF document."""
        # Log command usage
        self.log_command_use(interaction, "export_profile")
        
        await interaction.response.defer(ephemeral=True)
        
        target_member = member or interaction.user
        
        try:
            pdf_buffer = await self.generate_profile_pdf(target_member)
            file = discord.File(
                fp=pdf_buffer, 
                filename=f"{target_member.name}_profile.pdf"
            )
            await interaction.followup.send(
                f"Here's the exported profile for {target_member.display_name}:",
                file=file,
                ephemeral=True
            )
        except ImportError:
            await interaction.followup.send(
                "PDF export is not available. The server does not have the required libraries installed.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error exporting profile: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while exporting the profile.", ephemeral=True)

    @app_commands.command(
        name="search_members",
        description="Search for members by certifications, awards, or other criteria"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def search_members(
        self,
        interaction: discord.Interaction,
        search_type: str = "certification",
        query: str = ""
    ):
        """Search for members based on certifications, awards, or other criteria."""
        # Log command usage
        self.log_command_use(interaction, "search_members")
        
        await interaction.response.defer()
        
        try:
            # Build query based on search type
            coda_query = None
            if search_type == "certification":
                coda_query = f'"Certifications" ~* "{query}"'
            elif search_type == "award":
                coda_query = f'"Awards" ~* "{query}"'
            
            if not coda_query:
                await interaction.followup.send("Invalid search type selected.", ephemeral=True)
                return
            
            # Query Coda
            async with self.db_lock:  # Add lock for database operations
                rows = await self.coda_client.get_rows(
                    DOC_ID,
                    TABLE_ID,
                    query=coda_query,
                    limit=100
                )
            
            if not rows:
                await interaction.followup.send(f"No members found matching '{query}'.", ephemeral=True)
                return
            
            # Create a list of (member, data) tuples for all members we can find
            members_data = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = interaction.guild.get_member(int(discord_id))
                        if member:
                            members_data.append((member, row))
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            if not members_data:
                await interaction.followup.send(
                    f"Found {len(rows)} matching records, but none of the members are in this server.",
                    ephemeral=True
                )
                return
            
            # Create view to display results
            view = MemberSearchView(self, members_data, search_type, query)
            embed = await view.get_current_page_embed()
            
            await interaction.followup.send(embed=embed, view=view)
            
            # Dispatch member_search_completed event
            await self.dispatch_event(
                'member_search_completed',
                search_type=search_type,
                query=query,
                results_count=len(members_data)
            )
            
        except Exception as e:
            logger.error(f"Error searching members: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while searching members.", ephemeral=True)

    @app_commands.command(
        name="set_status",
        description="Change a member's status (Active, Inactive, etc.)"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def set_status(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        """Change a member's status between Active, Inactive, etc."""
        # Log command usage
        self.log_command_use(interaction, "set_status")
        
        try:
            # Get the member's current status
            member_row = await self.get_member_row(member.id)
            if not member_row:
                await interaction.response.send_message(
                    f"No profile found for {member.mention}.",
                    ephemeral=True
                )
                return
                
            current_status = member_row.get('values', {}).get('Status', "Unknown")
            
            # Show the status change modal
            modal = StatusChangeModal(self, member, current_status)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error showing status modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while preparing the status change.",
                ephemeral=True
            )

    @app_commands.command(
        name="send_achievement",
        description="Send an achievement unlock notification to a member"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def send_achievement(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        """Send an achievement unlock notification to a member."""
        # Log command usage
        self.log_command_use(interaction, "send_achievement")
        
        try:
            # Show the achievement configuration modal
            modal = AchievementUnlockModal(f"Achievement for {member.display_name}", self, member)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logger.error(f"Error showing achievement modal: {e}", exc_info=True)
            await interaction.response.send_message(
                "An error occurred while preparing the achievement notification.",
                ephemeral=True
            )

    @app_commands.command(
        name="view_awards",
        description="View a member's awards in a gallery format"
    )
    async def view_awards(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):
        """View a member's awards in a gallery format."""
        # Log command usage
        self.log_command_use(interaction, "view_awards")
        
        await interaction.response.defer()
        
        target_member = member or interaction.user
        
        try:
            # Get the member's profile
            member_row = await self.get_member_row(target_member.id)
            if not member_row:
                await interaction.followup.send(f"No profile found for {target_member.mention}.", ephemeral=True)
                return
                
            # Extract awards
            values = member_row.get('values', {})
            awards = parse_list_field(values.get(FIELD_AWARDS, []))
            
            if not awards:
                await interaction.followup.send(f"{target_member.display_name} has not received any awards yet.", ephemeral=True)
                return
                
            # Create award gallery
            view = AwardGalleryView(awards)
            embed = view.get_current_embed()
            
            # Try to also generate award chart
            try:
                from .visualizations import generate_award_chart
                chart = await generate_award_chart(awards)
                if chart:
                    await interaction.followup.send(embed=embed, view=view, file=chart)
                else:
                    await interaction.followup.send(embed=embed, view=view)
            except Exception as chart_err:
                logger.warning(f"Chart generation failed: {chart_err}")
                await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error displaying awards: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while retrieving awards.", ephemeral=True)

    @app_commands.command(
        name="repair_fleet_system",
        description="Fix common issues with the fleet system"
    )
    @app_commands.checks.has_any_role('Admin')
    async def repair_fleet_system_command(
        self,
        interaction: discord.Interaction
    ):
        """Admin command to repair fleet system issues."""
        # Log command usage
        self.log_command_use(interaction, "repair_fleet_system")
        
        await interaction.response.defer()
        
        try:
            # Import the repair function
            from .error_fixes import repair_fleet_system
            
            # Run the repairs
            await interaction.followup.send("Starting fleet system repairs... This may take a while.")
            
            # Run the repair
            results = await repair_fleet_system(self, interaction.guild.id)
            
            await interaction.followup.send(f"Fleet system repair results:\n{results}")
            
        except Exception as e:
            logger.error(f"Error in fleet system repair: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred during repair. Check the logs for details.")

    def log_command_use(self, interaction: discord.Interaction, command_name: str):
        """Log command usage."""
        logger.info(f"{interaction.user.name} ({interaction.user.id}) used /{command_name}")

    @add_award.error
    @remove_award.error
    @bulk_award.error
    async def award_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for award commands."""
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "❌ You don't have permission to manage awards.", 
                ephemeral=True
            )
        else:
            logger.error(f"Error in award command: {error}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.", 
                ephemeral=True
            )

    # Add error handlers for fleet system commands
    @fleet_report.error
    @set_ship_assignment.error
    @migrate_to_fleet_command.error
    @repair_fleet_system_command.error
    async def fleet_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Error handler for fleet system commands."""
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.", 
                ephemeral=True
            )
        else:
            logger.error(f"Error in fleet command: {error}", exc_info=True)
            await interaction.response.send_message(
                "❌ An error occurred while processing the command.", 
                ephemeral=True
            )
            
    # Command to export fleet members to CSV
    async def export_fleet_to_csv(self, fleet_wing: str, members_data: List[tuple]) -> str:
        """Export fleet wing members to CSV format."""
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow([
            "Name", "Discord ID", "Rank", "Specialization", "Status", 
            "ID Number", "Join Date", "Service Time", "Mission Count", 
            "Ship Assignment", "Certifications", "Awards"
        ])
        
        # Write data rows
        for member, data in members_data:
            values = data.get('values', {})
            
            from .utils import parse_list_field, calculate_service_time
            certifications = ', '.join(parse_list_field(values.get('Certifications', [])))
            awards = ', '.join(parse_list_field(values.get('Awards', [])))
            join_date = values.get('Join Date', 'Unknown')
            service_time = calculate_service_time(join_date)
            ship_assignment = values.get('Ship Assignment', 'Unassigned')
            
            writer.writerow([
                member.display_name,
                member.id,
                values.get('Rank', 'N/A'),
                values.get('Specialization', 'N/A'),
                values.get('Status', 'Unknown'),
                values.get('ID Number', 'N/A'),
                join_date,
                service_time,
                values.get('Mission Count', 0),
                ship_assignment,
                certifications,
                awards
            ])
        
        return output.getvalue()

    # Backward compatibility function
    async def export_division_to_csv(self, division: str, members_data: List[tuple]) -> str:
        """Backward compatibility function for exporting division members to CSV."""
        return await self.export_fleet_to_csv(division, members_data)