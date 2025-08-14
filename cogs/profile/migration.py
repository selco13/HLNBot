"""Migration utilities for transitioning from division-based to fleet-based structure."""

import asyncio
import logging
import discord
from typing import Dict, List, Optional, Any, Tuple
from discord.ext import commands

logger = logging.getLogger('profile.migration')

async def run_fleet_system_migration(bot: commands.Bot, guild_id: int, cog) -> bool:
    """
    Migrate from the division-based system to the fleet-based system.
    
    Args:
        bot: The Discord bot instance
        guild_id: The ID of the guild to update
        cog: The profile cog instance
        
    Returns:
        bool: True if migration was successful, False if there were errors
    """
    # Import constants needed for migration
    from .constants import (
        DOC_ID, TABLE_ID, DIVISION_TO_FLEET_WING, 
        FIELD_DIVISION, FIELD_FLEET_WING, FIELD_SHIP_ASSIGNMENT,
        FIELD_SPECIALIZATION
    )
    
    logger.info("Starting migration to fleet-based system")
    
    try:
        # Get the guild
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.error(f"Could not find guild with ID {guild_id}")
            return False
            
        # Get all profile records from the database
        logger.info("Fetching all profile records")
        rows = await cog.coda_client.get_rows(
            DOC_ID,
            TABLE_ID,
            limit=1000  # Set a high limit to get all records
        )
        
        if not rows:
            logger.warning("No profile records found to migrate")
            return True  # Nothing to migrate
            
        logger.info(f"Found {len(rows)} profiles to migrate")
        
        # Track stats
        total_profiles = len(rows)
        updated_profiles = 0
        skipped_profiles = 0
        error_profiles = 0
        
        # Create specialized mappings for certain combinations
        specialized_mapping = {
            # Division + Specialization -> Fleet Wing
            ('Tactical', 'Marines'): 'Marine Expeditionary Force',
            ('Tactical', 'Marine'): 'Marine Expeditionary Force',
            ('Operations', 'Salvage'): 'Industrial & Logistics Wing',
            ('Support', 'Medical'): 'Support & Medical Fleet',
            ('HQ', 'Command'): 'Fleet Command',
            # Add more specialized mappings as needed
        }
        
        # Mapping from specialization to the correct fleet specialization
        specialization_mapping = {
            'Marines': 'Ground Forces',
            'Marine': 'Ground Forces',
            'Salvage': 'Salvage Operations',
            'Medical': 'Medical',
            'Command': 'Command',
            # Add more mappings as needed
        }
        
        # Process each profile
        for row in rows:
            try:
                values = row.get('values', {})
                discord_id = values.get('Discord User ID')
                if not discord_id:
                    logger.warning(f"Profile missing Discord User ID, skipping: {row.get('id')}")
                    skipped_profiles += 1
                    continue
                    
                # Get the member if they're in the guild
                member = None
                try:
                    member = guild.get_member(int(discord_id))
                except (ValueError, TypeError):
                    logger.warning(f"Invalid Discord ID: {discord_id}")
                
                # Check current values
                current_division = values.get(FIELD_DIVISION)
                current_fleet_wing = values.get(FIELD_FLEET_WING)
                current_ship = values.get(FIELD_SHIP_ASSIGNMENT)
                current_specialization = values.get(FIELD_SPECIALIZATION)
                
                # Prepare updates
                updates = {}
                
                # Only update fleet wing if it's not already set
                if not current_fleet_wing:
                    # Check for specialized mapping based on division + specialization
                    if current_division and current_specialization:
                        mapping_key = (current_division, current_specialization)
                        if mapping_key in specialized_mapping:
                            # Use specialized mapping
                            new_fleet_wing = specialized_mapping[mapping_key]
                            logger.info(f"Using specialized mapping for {discord_id}: ({current_division}, {current_specialization}) -> {new_fleet_wing}")
                        else:
                            # Use standard division mapping
                            new_fleet_wing = DIVISION_TO_FLEET_WING.get(current_division, current_division)
                            logger.info(f"Using standard mapping for {discord_id}: {current_division} -> {new_fleet_wing}")
                    elif current_division:
                        # Only have division to work with
                        new_fleet_wing = DIVISION_TO_FLEET_WING.get(current_division, current_division)
                        logger.info(f"Using standard mapping for {discord_id}: {current_division} -> {new_fleet_wing}")
                    else:
                        # No division or specialization to map from
                        new_fleet_wing = 'Non-Fleet'
                        logger.warning(f"No division for {discord_id}, setting default fleet wing: {new_fleet_wing}")
                    
                    updates[FIELD_FLEET_WING] = new_fleet_wing
                
                # Handle specialization mapping
                if current_specialization:
                    # Map existing specialization to a fleet-compatible one
                    if current_specialization in specialization_mapping:
                        new_specialization = specialization_mapping[current_specialization]
                        if current_specialization != new_specialization:
                            logger.info(f"Mapping specialization for {discord_id}: {current_specialization} -> {new_specialization}")
                            updates[FIELD_SPECIALIZATION] = new_specialization
                # Set default specialization if none exists
                elif not current_specialization and (current_fleet_wing or updates.get(FIELD_FLEET_WING)):
                    fleet_wing = current_fleet_wing or updates.get(FIELD_FLEET_WING)
                    
                    # Map fleet wing to default specialization
                    if fleet_wing == "Navy Fleet":
                        updates[FIELD_SPECIALIZATION] = "Command"
                    elif fleet_wing == "Marine Expeditionary Force":
                        updates[FIELD_SPECIALIZATION] = "Ground Forces"
                    elif fleet_wing == "Industrial & Logistics Wing":
                        updates[FIELD_SPECIALIZATION] = "Naval Operations"
                    elif fleet_wing == "Support & Medical Fleet":
                        updates[FIELD_SPECIALIZATION] = "Medical"
                    elif fleet_wing == "Exploration & Intelligence Wing":
                        # Default value - can be set if needed
                        pass
                
                # Add ship assignment if missing
                if not current_ship:
                    updates[FIELD_SHIP_ASSIGNMENT] = 'Unassigned'
                    logger.info(f"Adding default ship assignment for {discord_id}")
                
                if not updates:
                    logger.debug(f"No updates needed for {discord_id}")
                    skipped_profiles += 1
                    continue
                
                # Update the profile
                row_id = row.get('id')
                if not row_id:
                    logger.warning(f"Missing row ID for profile: {discord_id}")
                    error_profiles += 1
                    continue
                    
                # Prepare the update
                update_cells = [
                    {'column': key, 'value': value}
                    for key, value in updates.items()
                ]
                
                # Update the row
                response = await cog.coda_client.request(
                    'PUT',
                    f'docs/{DOC_ID}/tables/{TABLE_ID}/rows/{row_id}',
                    data={'row': {'cells': update_cells}}
                )
                
                if response:
                    logger.info(f"Successfully updated profile for {discord_id}")
                    updated_profiles += 1
                    
                    # Invalidate cache
                    try:
                        await cog.cache.invalidate(str(discord_id))
                    except Exception as cache_err:
                        logger.warning(f"Cache invalidation warning: {cache_err}")
                        
                    # Update nickname if member is in guild
                    if member:
                        try:
                            # Get the updated profile data
                            member_row = await cog.get_member_row(member.id)
                            if member_row:
                                # Validate and update the profile
                                was_fixed, changes = await cog.validate_member_profile(member, member_row)
                                if was_fixed:
                                    logger.info(f"Additional profile fixes for {discord_id}: {changes}")
                        except Exception as profile_err:
                            logger.warning(f"Error validating profile for {discord_id}: {profile_err}")
                else:
                    logger.error(f"Failed to update row for member {discord_id}")
                    error_profiles += 1
                
            except Exception as e:
                logger.error(f"Error processing profile: {e}", exc_info=True)
                error_profiles += 1
        
        # Log results
        logger.info(f"Migration complete: {updated_profiles} updated, {skipped_profiles} skipped, {error_profiles} errors")
        logger.info(f"Total profiles processed: {total_profiles}")
        
        # Return success if no errors
        return error_profiles == 0
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False