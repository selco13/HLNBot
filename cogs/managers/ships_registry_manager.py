import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import re
import json

logger = logging.getLogger('ships_registry')
logger.setLevel(logging.DEBUG)

class ShipsRegistryManager:
    """Manager for ship registry operations using the existing CodaAPIClient."""
    
    def __init__(self, coda_client, doc_id: str, ships_table_id: str, users_table_id: str):
        """
        Initialize the ships registry manager.
        
        Args:
            coda_client: The CodaAPIClient instance
            doc_id: The Coda document ID
            ships_table_id: The ships table ID
            users_table_id: The users table ID
        """
        self.coda = coda_client
        self.doc_id = doc_id
        self.ships_table_id = ships_table_id
        self.users_table_id = users_table_id
        
        # Cache for registry data
        self._registry_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_expiry = 300  # 5 minutes
        self._cache_lock = asyncio.Lock()
        
        # Column IDs (will be populated by initialize)
        self.ship_column_ids: Dict[str, str] = {}
        self.user_column_ids: Dict[str, str] = {}
        
    async def initialize(self) -> bool:
        """Initialize the manager by loading column IDs."""
        try:
            # Get column IDs for ships table
            ships_columns = await self.coda.get_columns(self.doc_id, self.ships_table_id)
            if not ships_columns:
                logger.error(f"Failed to get columns for ships table {self.ships_table_id}")
                return False
                
            self.ship_column_ids = {col['name']: col['id'] for col in ships_columns}
            
            # Get column IDs for users table
            users_columns = await self.coda.get_columns(self.doc_id, self.users_table_id)
            if not users_columns:
                logger.error(f"Failed to get columns for users table {self.users_table_id}")
                return False
                
            self.user_column_ids = {col['name']: col['id'] for col in users_columns}
            
            # Verify required columns
            required_ship_columns = [
                'Ship Name', 'Registry Number', 'Ship Model',
                'Commission Date', 'Primary Use', 'Division',
                'Registered By', 'Status'
            ]
            
            missing_ship_columns = [col for col in required_ship_columns if col not in self.ship_column_ids]
            if missing_ship_columns:
                logger.error(f"Missing required ship columns: {missing_ship_columns}")
                return False
            
            logger.info("ShipsRegistryManager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing ShipsRegistryManager: {e}")
            return False
            
    def is_initialized(self) -> bool:
        """Check if the manager is properly initialized."""
        return bool(self.ship_column_ids)
        
    def generate_registry_number(self, ship_model: str) -> str:
        """Generate unique HLN registry number."""
        initials = ''.join(word[0] for word in ship_model.split() if word).upper()
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        registry_number = f"HLNS-{initials}-{timestamp[-5:]}"
        logger.debug(f"Generated registry number: {registry_number}")
        return registry_number
        
    async def get_ship_registry_info(self, ship_name: str) -> Optional[Dict[str, Any]]:
        """Get ship registry information from Coda."""
        # Check cache first
        async with self._cache_lock:
            cached_data = self._registry_cache.get(ship_name)
            if cached_data:
                cache_time = cached_data.get('_cache_time', 0)
                if datetime.now().timestamp() - cache_time < self._cache_expiry:
                    logger.debug(f"Using cached registry data for ship {ship_name}")
                    return cached_data['data']
        
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return None
            
        try:
            # Get all ships and filter in code - more reliable than complex API queries
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=200,  # Adjust based on expected total ships
                use_column_names=True
            )
            
            if not rows:
                logger.debug(f"No registry data found")
                return None
                
            # Find the ship by name
            ship_name_col_name = next((name for name, id in self.ship_column_ids.items() if name == 'Ship Name'), 'Ship Name')
            matching_row = None
            
            for row in rows:
                values = row.get('values', {})
                if values.get(ship_name_col_name) == ship_name:
                    matching_row = row
                    break
                    
            if not matching_row:
                logger.debug(f"No registry info found for ship {ship_name}")
                return None
                
            # Map row data to the expected format
            registry_info = {}
            values = matching_row.get('values', {})
            
            # Map values to column names
            for col_name in self.ship_column_ids.keys():
                registry_info[col_name] = values.get(col_name)
                
            # Include the row ID
            registry_info['id'] = matching_row.get('id')
            
            # Cache the result
            async with self._cache_lock:
                self._registry_cache[ship_name] = {
                    'data': registry_info,
                    '_cache_time': datetime.now().timestamp()
                }
                
            return registry_info
            
        except Exception as e:
            logger.error(f"Error getting registry info for ship {ship_name}: {e}")
            return None
            
    async def get_user_id_number(self, discord_user_id: str) -> str:
        """Get a user's ID number from their Discord ID."""
        try:
            user_id_col = self.user_column_ids.get('Discord User ID')
            id_number_col = self.user_column_ids.get('ID Number')
            
            if not user_id_col or not id_number_col:
                logger.error("Required user columns not found")
                return "N/A"
                
            # Use proper format for column queries
            query = f'`{user_id_col}` = "{discord_user_id}"'
            
            rows = await self.coda.get_rows(
                self.doc_id,
                self.users_table_id,
                query=query,
                use_column_names=False
            )
            
            if not rows or len(rows) == 0:
                logger.warning(f"No user found with Discord ID {discord_user_id}")
                return "N/A"
                
            values = rows[0].get('values', {})
            id_number = values.get(id_number_col, "N/A")
            
            return id_number
            
        except Exception as e:
            logger.error(f"Error getting user ID number: {e}")
            return "N/A"
            
    async def commission_ship(
        self,
        ship_name: str,
        ship_model: str,
        division: str,
        primary_use: str,
        discord_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Commission a new ship."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return None
            
        # Check if ship is already commissioned
        existing_ship = await self.get_ship_registry_info(ship_name)
        if existing_ship and existing_ship.get('Registry Number'):
            logger.warning(f"Ship {ship_name} is already commissioned")
            return None
            
        # Generate registry data
        registry_number = self.generate_registry_number(ship_model)
        commission_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Prepare data for Coda
        cells = [
            {'column': self.ship_column_ids['Ship Name'], 'value': ship_name},
            {'column': self.ship_column_ids['Registry Number'], 'value': registry_number},
            {'column': self.ship_column_ids['Ship Model'], 'value': ship_model},
            {'column': self.ship_column_ids['Commission Date'], 'value': commission_date},
            {'column': self.ship_column_ids['Primary Use'], 'value': primary_use},
            {'column': self.ship_column_ids['Division'], 'value': division},
            {'column': self.ship_column_ids['Registered By'], 'value': str(discord_user_id)},
            {'column': self.ship_column_ids['Status'], 'value': 'Active'}
        ]
        
        try:
            # Create the row in Coda
            response = await self.coda.request(
                'POST',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows',
                data={'rows': [{'cells': cells}]}
            )
            
            if not response:
                logger.error(f"Failed to commission ship {ship_name}")
                return None
                
            # Clear cache entry
            async with self._cache_lock:
                if ship_name in self._registry_cache:
                    del self._registry_cache[ship_name]
                    
            # Return commissioned ship info
            return {
                'ship_name': ship_name,
                'ship_model': ship_model,
                'registry_number': registry_number,
                'commission_date': commission_date,
                'primary_use': primary_use,
                'division': division,
                'status': 'Active'
            }
            
        except Exception as e:
            logger.error(f"Error commissioning ship {ship_name}: {e}")
            return None
            
    async def decommission_ship(
        self,
        ship_name: str,
        reason: str,
        discord_user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Decommission a ship."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return None
            
        # Check if ship is commissioned
        registry_info = await self.get_ship_registry_info(ship_name)
        if not registry_info or not registry_info.get('Registry Number'):
            logger.warning(f"Ship {ship_name} is not commissioned")
            return None
            
        decommission_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        try:
            # Prepare update cells
            cells = [
                {'column': self.ship_column_ids['Status'], 'value': 'Decommissioned'}
            ]
            
            # Add decommission reason if column exists
            if 'Decommission Reason' in self.ship_column_ids:
                cells.append({
                    'column': self.ship_column_ids['Decommission Reason'],
                    'value': reason
                })
            
            # Add decommission date if column exists  
            if 'Decommission Date' in self.ship_column_ids:
                cells.append({
                    'column': self.ship_column_ids['Decommission Date'],
                    'value': decommission_date
                })
                
            # Add decommissioned by if column exists
            if 'Decommissioned By' in self.ship_column_ids:
                cells.append({
                    'column': self.ship_column_ids['Decommissioned By'],
                    'value': str(discord_user_id)
                })
                
            # Update the row in Coda
            response = await self.coda.update_row(
                self.doc_id,
                self.ships_table_id,
                registry_info['id'],
                cells
            )
            
            if not response:
                logger.error(f"Failed to decommission ship {ship_name}")
                return None
                
            # Clear cache entry
            async with self._cache_lock:
                if ship_name in self._registry_cache:
                    del self._registry_cache[ship_name]
                    
            # Return decommissioned ship info
            return {
                'ship_name': ship_name,
                'registry_number': registry_info.get('Registry Number'),
                'decommission_date': decommission_date,
                'reason': reason,
                'status': 'Decommissioned'
            }
            
        except Exception as e:
            logger.error(f"Error decommissioning ship {ship_name}: {e}")
            return None
            
    async def get_ships_by_status(self, status: str = 'Active') -> List[Dict[str, Any]]:
        """Get all ships with a specific status."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return []
            
        try:
            # Get all ships and filter by status in code
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=200,
                use_column_names=True
            )
            
            if not rows:
                logger.info("No ships found in registry")
                return []
                
            # Filter by status
            status_col_name = next((name for name, id in self.ship_column_ids.items() if name == 'Status'), 'Status')
            ship_name_col_name = next((name for name, id in self.ship_column_ids.items() if name == 'Ship Name'), 'Ship Name')
            
            ships = []
            for row in rows:
                values = row.get('values', {})
                if values.get(status_col_name) == status:
                    registry_info = {}
                    
                    # Map values to column names
                    for col_name in self.ship_column_ids.keys():
                        registry_info[col_name] = values.get(col_name)
                        
                    # Include the row ID
                    registry_info['id'] = row.get('id')
                    ships.append(registry_info)
                    
                    # Update cache
                    ship_name = values.get(ship_name_col_name)
                    if ship_name:
                        async with self._cache_lock:
                            self._registry_cache[ship_name] = {
                                'data': registry_info,
                                '_cache_time': datetime.now().timestamp()
                            }
            
            return ships
            
        except Exception as e:
            logger.error(f"Error getting ships by status {status}: {e}")
            return []
            
    async def update_ship_info(
        self,
        ship_name: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update ship information."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return False
            
        # Get current ship info
        registry_info = await self.get_ship_registry_info(ship_name)
        if not registry_info:
            logger.error(f"Ship {ship_name} not found in registry")
            return False
            
        try:
            # Prepare update cells
            cells = []
            for key, value in updates.items():
                if key in self.ship_column_ids:
                    cells.append({
                        'column': self.ship_column_ids[key],
                        'value': value
                    })
                    
            if not cells:
                logger.warning(f"No valid updates specified for ship {ship_name}")
                return False
                
            # Update the row in Coda
            response = await self.coda.update_row(
                self.doc_id,
                self.ships_table_id,
                registry_info['id'],
                cells
            )
            
            if not response:
                logger.error(f"Failed to update ship {ship_name}")
                return False
                
            # Clear cache entry
            async with self._cache_lock:
                if ship_name in self._registry_cache:
                    del self._registry_cache[ship_name]
                    
            logger.info(f"Successfully updated ship {ship_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating ship {ship_name}: {e}")
            return False
            
    async def get_ships_by_division(self, division: str) -> List[Dict[str, Any]]:
        """Get all ships assigned to a specific division."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return []
            
        try:
            # Query for ships by division
            division_col_id = self.ship_column_ids['Division']
            # Use proper format for column queries
            query = f'`{division_col_id}` = "{division}"'
            
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                query=query,
                use_column_names=False
            )
            
            if not rows:
                logger.info(f"No ships found in division {division}")
                return []
                
            # Convert rows to ship registry info
            ships = []
            for row in rows:
                registry_info = {}
                
                # Map row data to column names
                values = row.get('values', {})
                for col_name, col_id in self.ship_column_ids.items():
                    registry_info[col_name] = values.get(col_id)
                    
                # Include the row ID
                registry_info['id'] = row.get('id')
                
                ships.append(registry_info)
                
                # Update cache for this ship
                if 'Ship Name' in registry_info and registry_info['Ship Name']:
                    ship_name = registry_info['Ship Name']
                    async with self._cache_lock:
                        self._registry_cache[ship_name] = {
                            'data': registry_info,
                            '_cache_time': datetime.now().timestamp()
                        }
            
            return ships
            
        except Exception as e:
            logger.error(f"Error getting ships by division {division}: {e}")
            return []
            
    async def get_fleet_statistics(self) -> Dict[str, Any]:
        """Get statistics about the fleet."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return {}
            
        try:
            # Get all ships
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=1000,
                use_column_names=False
            )
            
            if not rows:
                logger.info("No ships found in registry")
                return {
                    'total_ships': 0,
                    'active_ships': 0,
                    'decommissioned_ships': 0,
                    'divisions': {},
                    'primary_uses': {},
                    'latest_commissions': []
                }
                
            # Process statistics
            total_ships = len(rows)
            active_ships = 0
            decommissioned_ships = 0
            divisions = {}
            primary_uses = {}
            latest_commissions = []
            
            for row in rows:
                values = row.get('values', {})
                
                # Extract ship details
                ship_name = values.get(self.ship_column_ids.get('Ship Name', ''), '')
                status = values.get(self.ship_column_ids.get('Status', ''), '')
                division = values.get(self.ship_column_ids.get('Division', ''), '')
                primary_use = values.get(self.ship_column_ids.get('Primary Use', ''), '')
                commission_date = values.get(self.ship_column_ids.get('Commission Date', ''), '')
                
                # Count by status
                if status == 'Active':
                    active_ships += 1
                elif status == 'Decommissioned':
                    decommissioned_ships += 1
                    
                # Count by division
                if division:
                    divisions[division] = divisions.get(division, 0) + 1
                    
                # Count by primary use
                if primary_use:
                    primary_uses[primary_use] = primary_uses.get(primary_use, 0) + 1
                    
                # Track latest commissions
                if commission_date and ship_name:
                    latest_commissions.append({
                        'ship_name': ship_name,
                        'commission_date': commission_date,
                        'division': division,
                        'primary_use': primary_use
                    })
                    
            # Sort latest commissions by date (newest first)
            try:
                latest_commissions.sort(key=lambda x: x['commission_date'], reverse=True)
            except Exception:
                # In case of date parsing issues
                pass
                
            return {
                'total_ships': total_ships,
                'active_ships': active_ships,
                'decommissioned_ships': decommissioned_ships,
                'divisions': divisions,
                'primary_uses': primary_uses,
                'latest_commissions': latest_commissions[:10]  # Only return the 10 most recent
            }
            
        except Exception as e:
            logger.error(f"Error getting fleet statistics: {e}")
            return {
                'total_ships': 0,
                'active_ships': 0,
                'decommissioned_ships': 0,
                'divisions': {},
                'primary_uses': {},
                'latest_commissions': []
            }
            
    async def search_registry(self, search_term: str) -> List[Dict[str, Any]]:
        """Search the ship registry with a free-text search term."""
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return []
            
        if not search_term:
            logger.warning("Empty search term")
            return []
            
        try:
            # Sanitize the search term
            search_term = search_term.replace('"', '\\"')
            
            # Instead of complex queries, let's retrieve all registry records and filter in code
            # This is more reliable than dealing with API query syntax issues
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=200,  # Adjust as needed based on expected number of ships
                use_column_names=True  # Use column names instead of IDs
            )
            
            if not rows:
                logger.info("No ships found in registry")
                return []
                
            # Filter results in code to find matching ships
            results = []
            registry_col_name = next((name for name, id in self.ship_column_ids.items() if name == 'Registry Number'), 'Registry Number')
            ship_name_col_name = next((name for name, id in self.ship_column_ids.items() if name == 'Ship Name'), 'Ship Name')
            
            for row in rows:
                values = row.get('values', {})
                
                # Check for match in Registry Number (exact match)
                registry_number = values.get(registry_col_name, '')
                if registry_number and search_term.lower() in registry_number.lower():
                    # Found a match
                    registry_info = {}
                    
                    # Map values to column names
                    for col_name in self.ship_column_ids.keys():
                        registry_info[col_name] = values.get(col_name)
                        
                    # Include the row ID
                    registry_info['id'] = row.get('id')
                    results.append(registry_info)
                    
            # If no matches found by registry number, try ship name
            if not results:
                for row in rows:
                    values = row.get('values', {})
                    
                    # Check for match in Ship Name (partial match)
                    ship_name = values.get(ship_name_col_name, '')
                    if ship_name and search_term.lower() in ship_name.lower():
                        # Found a match
                        registry_info = {}
                        
                        # Map values to column names
                        for col_name in self.ship_column_ids.keys():
                            registry_info[col_name] = values.get(col_name)
                            
                        # Include the row ID
                        registry_info['id'] = row.get('id')
                        results.append(registry_info)
                        
            return results
                
        except Exception as e:
            logger.error(f"Error searching registry for '{search_term}': {e}", exc_info=True)
            return []
            
    async def bulk_update_ships(self, updates: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Perform bulk updates on multiple ships.
        
        Args:
            updates: List of dictionaries, each containing:
                - 'id': The Coda row ID
                - Updates to apply, with column names as keys
                
        Returns:
            Dict with success and failure counts
        """
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return {'success': 0, 'failure': len(updates)}
            
        if not updates:
            return {'success': 0, 'failure': 0}
            
        success_count = 0
        failure_count = 0
        
        for update in updates:
            row_id = update.get('id')
            if not row_id:
                logger.error("Missing row ID in bulk update")
                failure_count += 1
                continue
                
            # Extract updates, excluding 'id'
            ship_updates = {k: v for k, v in update.items() if k != 'id'}
            if not ship_updates:
                logger.warning(f"No updates specified for row {row_id}")
                failure_count += 1
                continue
                
            # Prepare cells for update
            cells = []
            for key, value in ship_updates.items():
                if key in self.ship_column_ids:
                    cells.append({
                        'column': self.ship_column_ids[key],
                        'value': value
                    })
                    
            if not cells:
                logger.warning(f"No valid updates specified for row {row_id}")
                failure_count += 1
                continue
                
            try:
                # Update the row in Coda
                response = await self.coda.update_row(
                    self.doc_id,
                    self.ships_table_id,
                    row_id,
                    cells
                )
                
                if response:
                    success_count += 1
                    
                    # Clear cache for this ship
                    ship_name = update.get('Ship Name')
                    if ship_name:
                        async with self._cache_lock:
                            if ship_name in self._registry_cache:
                                del self._registry_cache[ship_name]
                else:
                    logger.error(f"Failed to update row {row_id}")
                    failure_count += 1
                    
            except Exception as e:
                logger.error(f"Error updating row {row_id}: {e}")
                failure_count += 1
                
        logger.info(f"Bulk update completed: {success_count} successes, {failure_count} failures")
        return {'success': success_count, 'failure': failure_count}
            
    async def clear_cache(self):
        """Clear the registry cache."""
        async with self._cache_lock:
            self._registry_cache.clear()
        logger.info("Registry cache cleared")

    async def transfer_ship_ownership(
        self,
        ship_name: str,
        new_owner_id: str,
        transfer_reason: str
    ) -> bool:
        """
        Transfer ownership of a ship to a new owner.
        
        Args:
            ship_name: Name of the ship to transfer
            new_owner_id: Discord ID of the new owner
            transfer_reason: Reason for the transfer
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_initialized():
            logger.error("ShipsRegistryManager not initialized")
            return False
            
        # Get current ship info
        registry_info = await self.get_ship_registry_info(ship_name)
        if not registry_info:
            logger.error(f"Ship {ship_name} not found in registry")
            return False
            
        try:
            # Prepare update cells
            cells = [
                {'column': self.ship_column_ids['Registered By'], 'value': new_owner_id}
            ]
            
            # Add transfer reason if column exists
            if 'Transfer Reason' in self.ship_column_ids:
                cells.append({
                    'column': self.ship_column_ids['Transfer Reason'],
                    'value': transfer_reason
                })
            elif 'Notes' in self.ship_column_ids:
                # Use notes field as fallback
                cells.append({
                    'column': self.ship_column_ids['Notes'],
                    'value': f"Transferred: {transfer_reason}"
                })
                
            # Add transfer date if column exists
            if 'Transfer Date' in self.ship_column_ids:
                cells.append({
                    'column': self.ship_column_ids['Transfer Date'],
                    'value': datetime.utcnow().strftime('%Y-%m-%d')
                })
                
            # Update the row in Coda
            response = await self.coda.update_row(
                self.doc_id,
                self.ships_table_id,
                registry_info['id'],
                cells
            )
            
            if not response:
                logger.error(f"Failed to transfer ship {ship_name}")
                return False
                
            # Clear cache entry
            async with self._cache_lock:
                if ship_name in self._registry_cache:
                    del self._registry_cache[ship_name]
                    
            logger.info(f"Successfully transferred ship {ship_name} to user {new_owner_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error transferring ship {ship_name}: {e}")
            return False
            
    async def create_flight_group(
        self,
        name: str,
        description: str,
        fleet_wing: str,
        commander_discord_id: Optional[str] = None
    ):
        """Create a new flight group."""
        try:
            # Check if flight group already exists by getting all rows and filtering
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=100,
                use_column_names=True
            )
            
            # Check if a flight group with this name already exists
            for row in rows:
                values = row.get('values', {})
                row_type = values.get('Type', '')
                row_name = values.get('Name', '')
                
                if row_type == 'Flight Group' and row_name == name:
                    logger.warning(f"Flight group {name} already exists")
                    return None
            
            # Create the flight group
            cells = [
                {'column': 'Name', 'value': name},
                {'column': 'Type', 'value': 'Flight Group'},
                {'column': 'Description', 'value': description},
                {'column': 'Fleet Wing', 'value': fleet_wing},
                {'column': 'Status', 'value': 'Active'}
            ]
            
            # Add commander ID if provided
            if commander_discord_id:
                cells.append({'column': 'Commander ID', 'value': commander_discord_id})
                
            # Add creation date if the column exists
            cells.append({'column': 'Creation Date', 'value': datetime.utcnow().strftime('%Y-%m-%d')})
            
            response = await self.coda.request(
                'POST',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows',
                data={'rows': [{'cells': cells}]}
            )
            
            if response and 'id' in response:
                return {
                    'id': response['id'],
                    'name': name,
                    'description': description,
                    'fleet_wing': fleet_wing,
                    'commander_id': commander_discord_id
                }
            else:
                logger.error(f"Failed to create flight group: {response}")
                return None
        except Exception as e:
            logger.error(f"Error creating flight group: {e}")
            return None
    
    async def create_squadron(
        self,
        name: str,
        description: str,
        fleet_wing: str,
        commander_discord_id: Optional[str] = None
    ):
        """Create a new squadron."""
        try:
            # Check if squadron already exists by getting all rows and filtering
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=100,
                use_column_names=True
            )
            
            # Check if a squadron with this name already exists
            for row in rows:
                values = row.get('values', {})
                row_type = values.get('Type', '')
                row_name = values.get('Name', '')
                
                if row_type == 'Squadron' and row_name == name:
                    logger.warning(f"Squadron {name} already exists")
                    return None
            
            # Create the squadron
            cells = [
                {'column': 'Name', 'value': name},
                {'column': 'Type', 'value': 'Squadron'},
                {'column': 'Description', 'value': description},
                {'column': 'Fleet Wing', 'value': fleet_wing},
                {'column': 'Status', 'value': 'Active'}
            ]
            
            # Add commander ID if provided
            if commander_discord_id:
                cells.append({'column': 'Commander ID', 'value': commander_discord_id})
                
            # Add creation date if the column exists
            cells.append({'column': 'Creation Date', 'value': datetime.utcnow().strftime('%Y-%m-%d')})
            
            response = await self.coda.request(
                'POST',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows',
                data={'rows': [{'cells': cells}]}
            )
            
            if response and 'id' in response:
                return {
                    'id': response['id'],
                    'name': name,
                    'description': description,
                    'fleet_wing': fleet_wing,
                    'commander_id': commander_discord_id
                }
            else:
                logger.error(f"Failed to create squadron: {response}")
                return None
        except Exception as e:
            logger.error(f"Error creating squadron: {e}")
            return None
    
    async def get_flight_group(self, name: str):
        """Get a flight group by name."""
        try:
            # Get all rows and filter for flight groups
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=100,
                use_column_names=True
            )
            
            # Find the flight group with matching name
            for row in rows:
                values = row.get('values', {})
                row_type = values.get('Type', '')
                row_name = values.get('Name', '')
                
                if row_type == 'Flight Group' and row_name == name:
                    return {
                        'id': row.get('id'),
                        'name': row_name,
                        'description': values.get('Description', ''),
                        'fleet_wing': values.get('Fleet Wing', ''),
                        'commander_id': values.get('Commander ID', ''),
                        'squadron': values.get('Squadron', ''),
                        'ships': values.get('Ships', []),
                        'status': values.get('Status', '')
                    }
                    
            return None
        except Exception as e:
            logger.error(f"Error getting flight group: {e}")
            return None
    
    async def get_squadron(self, name: str):
        """Get a squadron by name."""
        try:
            # Get all rows and filter for squadrons
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=100,
                use_column_names=True
            )
            
            # Find the squadron with matching name
            for row in rows:
                values = row.get('values', {})
                row_type = values.get('Type', '')
                row_name = values.get('Name', '')
                
                if row_type == 'Squadron' and row_name == name:
                    return {
                        'id': row.get('id'),
                        'name': row_name,
                        'description': values.get('Description', ''),
                        'fleet_wing': values.get('Fleet Wing', ''),
                        'commander_id': values.get('Commander ID', ''),
                        'flight_groups': values.get('Flight Groups', []),
                        'status': values.get('Status', '')
                    }
                    
            return None
        except Exception as e:
            logger.error(f"Error getting squadron: {e}")
            return None
    
    async def assign_flight_group_to_squadron(self, flight_group_name: str, squadron_name: str):
        """Assign a flight group to a squadron."""
        try:
            # Get flight group and squadron
            flight_group = await self.get_flight_group(flight_group_name)
            squadron = await self.get_squadron(squadron_name)
            
            if not flight_group or not squadron:
                return False
                
            # Update flight group with squadron
            fg_row_id = flight_group['id']
            squadron_row_id = squadron['id']
            
            fg_update = await self.coda.request(
                'PUT',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows/{fg_row_id}',
                data={'row': {'cells': [{'column': 'Squadron', 'value': squadron_name}]}}
            )
            
            # Update squadron's flight groups list
            flight_groups = squadron.get('flight_groups', [])
            if isinstance(flight_groups, str):
                flight_groups = [fg.strip() for fg in flight_groups.split(',') if fg.strip()]
            elif flight_groups is None:
                flight_groups = []
                
            if flight_group_name not in flight_groups:
                flight_groups.append(flight_group_name)
                
            squadron_update = await self.coda.request(
                'PUT',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows/{squadron_row_id}',
                data={'row': {'cells': [{'column': 'Flight Groups', 'value': ','.join(flight_groups)}]}}
            )
            
            return fg_update and squadron_update
        except Exception as e:
            logger.error(f"Error assigning flight group to squadron: {e}")
            return False
    
    async def assign_ship_to_flight_group(self, ship_name: str, flight_group_name: str):
        """Assign a ship to a flight group."""
        try:
            # Get ship and flight group
            ship_info = await self.get_ship_registry_info(ship_name)
            flight_group = await self.get_flight_group(flight_group_name)
            
            if not ship_info or not flight_group:
                return False
                    
            # Get ship row ID from ship_info
            ship_row_id = ship_info.get('id')
            if not ship_row_id:
                logger.error(f"Missing row ID for ship {ship_name}")
                return False
            
            # Get squadron info from flight group if available
            squadron = flight_group.get('squadron')
            
            updates = [{'column': 'Flight Group', 'value': flight_group_name}]
            if squadron:
                updates.append({'column': 'Squadron', 'value': squadron})
            
            ship_update = await self.coda.request(
                'PUT',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows/{ship_row_id}',
                data={'row': {'cells': updates}}
            )
            
            # Update flight group's ships list
            fg_row_id = flight_group['id']
            ships = flight_group.get('ships', [])
            
            if isinstance(ships, str):
                ships = [s.strip() for s in ships.split(',') if s.strip()]
            elif ships is None:
                ships = []
                
            if ship_name not in ships:
                ships.append(ship_name)
                
            fg_update = await self.coda.request(
                'PUT',
                f'docs/{self.doc_id}/tables/{self.ships_table_id}/rows/{fg_row_id}',
                data={'row': {'cells': [{'column': 'Ships', 'value': ','.join(ships)}]}}
            )
            
            return ship_update and fg_update
        except Exception as e:
            logger.error(f"Error assigning ship to flight group: {e}")
            return False
    
    async def list_flight_groups(self, squadron: Optional[str] = None, fleet_wing: Optional[str] = None):
        """List flight groups, optionally filtered by squadron or fleet wing."""
        try:
            # Get all rows and filter for flight groups
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=100,
                use_column_names=True
            )
            
            flight_groups = []
            for row in rows:
                values = row.get('values', {})
                row_type = values.get('Type', '')
                
                # Check if the row is a flight group
                if row_type != 'Flight Group':
                    continue
                    
                # Apply filters if provided
                row_squadron = values.get('Squadron', '')
                row_fleet_wing = values.get('Fleet Wing', '')
                
                if squadron and row_squadron != squadron:
                    continue
                
                if fleet_wing and row_fleet_wing != fleet_wing:
                    continue
                    
                # Add flight group to results
                flight_groups.append({
                    'id': row.get('id'),
                    'name': values.get('Name', ''),
                    'description': values.get('Description', ''),
                    'fleet_wing': row_fleet_wing,
                    'commander_id': values.get('Commander ID', ''),
                    'squadron': row_squadron,
                    'ships': values.get('Ships', []),
                    'status': values.get('Status', '')
                })
                    
            return flight_groups
        except Exception as e:
            logger.error(f"Error listing flight groups: {e}")
            return []
    
    async def list_squadrons(self, fleet_wing: Optional[str] = None):
        """List squadrons, optionally filtered by fleet wing."""
        try:
            # Get all rows and filter for squadrons
            rows = await self.coda.get_rows(
                self.doc_id,
                self.ships_table_id,
                limit=100,
                use_column_names=True
            )
            
            squadrons = []
            for row in rows:
                values = row.get('values', {})
                row_type = values.get('Type', '')
                
                # Check if the row is a squadron
                if row_type != 'Squadron':
                    continue
                    
                # Apply fleet wing filter if provided
                row_fleet_wing = values.get('Fleet Wing', '')
                
                if fleet_wing and row_fleet_wing != fleet_wing:
                    continue
                    
                # Add squadron to results
                squadrons.append({
                    'id': row.get('id'),
                    'name': values.get('Name', ''),
                    'description': values.get('Description', ''),
                    'fleet_wing': row_fleet_wing,
                    'commander_id': values.get('Commander ID', ''),
                    'flight_groups': values.get('Flight Groups', []),
                    'status': values.get('Status', '')
                })
                    
            return squadrons
        except Exception as e:
            logger.error(f"Error listing squadrons: {e}")
            return []
    
    async def get_flight_group_members(self, flight_group_name: str):
        """Get members of a flight group."""
        try:
            # This is just a placeholder - the actual implementation will need to
            # be in the Profile cog as it has access to user profiles
            return []
        except Exception as e:
            logger.error(f"Error getting flight group members: {e}")
            return []
    
    async def assign_member_to_flight_group(self, member_id: str, flight_group_name: str):
        """Assign a member to a flight group."""
        try:
            # This is just a placeholder - the actual implementation will 
            # be in the Profile cog which manages member assignments
            return True
        except Exception as e:
            logger.error(f"Error assigning member to flight group: {e}")
            return False