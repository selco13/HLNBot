#!/usr/bin/env python3
"""
Migration script to move ship data from the old ships registry to the new system.
This should be run once to migrate existing data.
"""

import sys
import os
import asyncio
import logging
import argparse
import json
import datetime
from typing import Dict, List, Any, Optional

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import required modules
from dotenv import load_dotenv
load_dotenv()

import config
from cogs.utils.coda_api import CodaAPIClient
from cogs.managers.ships_registry_manager import ShipsRegistryManager
from cogs.mission_system.ship_data import Ship

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/ships_migration_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)

logger = logging.getLogger('ships_migration')

# Create backup directory
BACKUP_DIR = "backups/ships_migration"
os.makedirs(BACKUP_DIR, exist_ok=True)

async def backup_data(coda_client, old_table_id: str):
    """Backup the old ship registry data."""
    logger.info(f"Backing up data from table {old_table_id}")
    
    try:
        # Get rows from the old table
        rows = await coda_client.get_rows(
            config.DOC_ID,
            old_table_id,
            limit=1000,
            use_column_names=True
        )
        
        if not rows:
            logger.error("Failed to retrieve data from old table")
            return False
            
        logger.info(f"Retrieved {len(rows)} rows from old table")
        
        # Save to backup file
        backup_file = os.path.join(BACKUP_DIR, f"ships_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2)
            
        logger.info(f"Backup saved to {backup_file}")
        return backup_file
        
    except Exception as e:
        logger.error(f"Error backing up data: {e}")
        return False

async def migrate_ship_data(args):
    """Migrate ship data from old to new format."""
    logger.info("Starting ship data migration")
    
    # Initialize CodaAPIClient
    coda_client = CodaAPIClient(config.CODA_API_TOKEN)
    
    # Create ShipsRegistryManager
    registry_manager = ShipsRegistryManager(
        coda_client,
        config.DOC_ID,
        config.SHIPS_TABLE_ID,
        config.USERS_TABLE_ID
    )
    
    # Initialize the registry manager
    logger.info("Initializing ShipsRegistryManager")
    success = await registry_manager.initialize()
    if not success:
        logger.error("Failed to initialize ShipsRegistryManager")
        return False
    
    # Backup old data
    backup_file = await backup_data(coda_client, args.old_table_id)
    if not backup_file:
        logger.error("Failed to backup old data, aborting migration")
        return False
        
    # Load Ship data
    ship_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ships.csv')
    ship_load_success = Ship.load_ships(ship_file_path)
    if not ship_load_success:
        logger.error(f"Failed to load ship data from {ship_file_path}")
        return False
        
    logger.info(f"Loaded {len(Ship._ships_cache)} ships from {ship_file_path}")
    
    # Check if we're just doing a dry run
    if args.dry_run:
        logger.info("Running in dry run mode - no changes will be made")
        
    # Get existing ships from new registry
    existing_ships = {}
    for ship_name in Ship._ships_cache:
        registry_info = await registry_manager.get_ship_registry_info(ship_name)
        if registry_info:
            existing_ships[ship_name] = registry_info
            
    logger.info(f"Found {len(existing_ships)} ships already in new registry")
    
    # Get all ships from old registry
    old_ships = []
    try:
        with open(backup_file, 'r', encoding='utf-8') as f:
            old_ships = json.load(f)
    except Exception as e:
        logger.error(f"Error loading backup file: {e}")
        return False
        
    logger.info(f"Loaded {len(old_ships)} ships from old registry")
    
    # Map old column names to new names (adjust based on your specific column names)
    column_mapping = {
        'Ship Name': 'Ship Name',
        'Registry Number': 'Registry Number',
        'Ship Model': 'Ship Model',
        'Commission Date': 'Commission Date',
        'Primary Use': 'Primary Use',
        'Division': 'Division',
        'Registered By': 'Registered By',
        'Status': 'Status'
    }
    
    # Process each ship in the old registry
    success_count = 0
    skipped_count = 0
    error_count = 0
    
    for old_ship in old_ships:
        try:
            old_values = old_ship.get('values', {})
            
            # Extract ship name
            ship_name = old_values.get('Ship Name', '')
            if not ship_name:
                logger.warning(f"Skipping entry without ship name: {old_values}")
                skipped_count += 1
                continue
                
            # Check if ship is already in the new registry
            if ship_name in existing_ships:
                logger.info(f"Ship {ship_name} already exists in new registry - skipping")
                skipped_count += 1
                continue
                
            # Check if ship exists in the Ship database
            ship = Ship.get_ship(ship_name)
            if not ship:
                # This might be a custom entry that's not in the ships.csv
                logger.warning(f"Ship {ship_name} not found in ships database")
                # We'll still try to migrate it
                
            # Get registry number
            registry_number = old_values.get('Registry Number', '')
            if not registry_number:
                logger.warning(f"Ship {ship_name} missing registry number - generating one")
                ship_model = old_values.get('Ship Model', ship.role if ship else "Unknown")
                registry_number = registry_manager.generate_registry_number(ship_model)
                
            # Map other fields
            new_ship_data = {}
            for new_key, old_key in column_mapping.items():
                if old_key in old_values:
                    new_ship_data[new_key] = old_values[old_key]
                    
            # Set defaults for missing fields
            if 'Ship Model' not in new_ship_data:
                new_ship_data['Ship Model'] = ship.role if ship else "Unknown"
                
            if 'Commission Date' not in new_ship_data:
                new_ship_data['Commission Date'] = datetime.datetime.now().strftime('%Y-%m-%d')
                
            if 'Status' not in new_ship_data:
                new_ship_data['Status'] = 'Active'
                
            # Prepare data for new registry
            cells = []
            for key, value in new_ship_data.items():
                if key in registry_manager.ship_column_ids:
                    cells.append({
                        'column': registry_manager.ship_column_ids[key],
                        'value': value
                    })
                    
            # Create the ship in the new registry (unless dry run)
            if not args.dry_run:
                response = await coda_client.request(
                    'POST',
                    f'docs/{config.DOC_ID}/tables/{config.SHIPS_TABLE_ID}/rows',
                    data={'rows': [{'cells': cells}]}
                )
                
                if response:
                    logger.info(f"Successfully migrated ship {ship_name}")
                    success_count += 1
                else:
                    logger.error(f"Failed to migrate ship {ship_name}")
                    error_count += 1
            else:
                # In dry run mode, just log what would be done
                logger.info(f"Would migrate ship {ship_name} with data: {new_ship_data}")
                success_count += 1
                
        except Exception as e:
            logger.error(f"Error processing ship: {e}")
            error_count += 1
            
    # Log summary
    logger.info("Migration complete!")
    logger.info(f"Processed {len(old_ships)} ships:")
    logger.info(f"  - {success_count} successfully migrated")
    logger.info(f"  - {skipped_count} skipped (already exist)")
    logger.info(f"  - {error_count} errors")
    
    return True

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Migrate ship data from old to new registry")
    
    parser.add_argument(
        "--old-table-id",
        default=config.SHIPS_TABLE_ID,  # Default to current table ID
        help="Table ID of the old ships registry"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without making any changes"
    )
    
    return parser.parse_args()

async def main():
    """Main entry point."""
    args = parse_args()
    
    try:
        success = await migrate_ship_data(args)
        logger.info("Migration " + ("successful" if success else "failed"))
        return success
    except Exception as e:
        logger.error(f"Unhandled error in migration: {e}")
        return False

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    success = loop.run_until_complete(main())
    sys.exit(0 if success else 1)