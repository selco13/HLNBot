# cogs/managers/coda_manager.py

import logging
import asyncio
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime, timezone, timedelta
import os
import json

logger = logging.getLogger('coda_manager')

class CodaManager:
    """
    Handles all Coda.io API interactions with enhanced caching and service integration.
    """
    
    def __init__(self, coda_client, doc_id: str = None, profile_table_id: str = None, promotion_requests_table_id: str = None):
        self.coda = coda_client
        
        # Accept parameters directly or get from environment variables
        self.doc_id = doc_id or os.getenv('DOC_ID')
        self.profile_table_id = profile_table_id or os.getenv('TABLE_ID')
        self.promotion_requests_table_id = promotion_requests_table_id or os.getenv('PROMOTION_REQUESTS_TABLE_ID')
        
        # Additional table IDs
        self.ships_table_id = os.getenv('SHIPS_TABLE_ID')
        self.accounts_table_id = os.getenv('ACCOUNTS_TABLE_ID')
        self.transactions_table_id = os.getenv('TRANSACTIONS_TABLE_ID')
        
        # Cache settings
        self._cache = {}
        self._cache_lock = asyncio.Lock()
        self._cache_expiry = 300  # 5 minutes
        
        # Column mappings
        self.columns = {}  # Will be populated by initialize_columns
        
        # Backup settings
        self._backup_dir = "coda_backups"
        self._backup_interval = 24 * 60 * 60  # 24 hours
        self._last_backup = None
        
        logger.info("CodaManager initialized")

    async def get_member_data(self, member_id: int) -> Optional[Dict[str, Any]]:
        """Get member data from Coda with caching."""
        try:
            # Check cache first
            cache_key = f"member_{member_id}"
            async with self._cache_lock:
                cached_data = self._cache.get(cache_key)
                if cached_data:
                    cache_time = cached_data.get('_cache_time', 0)
                    if datetime.now().timestamp() - cache_time < self._cache_expiry:
                        logger.debug(f"Returning cached data for member {member_id}")
                        return cached_data['data']

            # Query Coda using standardized client
            rows = await self.coda.get_rows(
                self.doc_id,
                self.profile_table_id,
                query=f'"Discord User ID":"{member_id}"',
                use_column_names=True,
                limit=1
            )
            
            if rows and len(rows) > 0:
                # Clean and store the data
                member_data = self._clean_coda_data(rows[0].get('values', {}))
                member_data['id'] = rows[0]['id']  # Include row ID
                
                # Update cache
                async with self._cache_lock:
                    self._cache[cache_key] = {
                        'data': member_data,
                        '_cache_time': datetime.now().timestamp()
                    }
                
                return member_data

            logger.warning(f"No data found for member {member_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting member data: {e}", exc_info=True)
            return None

    def _clean_coda_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean data received from Coda."""
        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                cleaned[key] = value.strip('`').strip()
            elif isinstance(value, list):
                cleaned[key] = [item.strip('`').strip() if isinstance(item, str) else item for item in value]
            else:
                cleaned[key] = value
        return cleaned

    async def update_member_info(self, row_id: str, updates: Dict[str, Any]) -> bool:
        """Update member information in profile table."""
        try:
            # Map internal field names to Coda table field names
            field_mapping = {
                'rank': 'Rank',
                'rank_date': 'Rank Date',
                'division': 'Division',
                'specialization': 'Specialization',
                'proposed_rank': 'Proposed Rank',
                'recommendation_source': 'Recommendation Source',
                'recommendation_reason': 'Recommendation Reason',
                'statuspro': 'Statuspro',
                'id_number': 'ID Number',
                'certifications': 'Certifications'
            }
            
            cells = []
            for key, value in updates.items():
                coda_field = field_mapping.get(key, key)
                cells.append({'column': coda_field, 'value': value})

            # Check if we're updating ID Number (which might need row name update)
            id_update = updates.get('id_number') or updates.get('ID Number')
            if id_update:
                # Update row with new name
                response = await self.coda.update_row_with_name(
                    self.doc_id,
                    self.profile_table_id,
                    row_id,
                    cells,
                    id_update
                )
            else:
                # Normal update
                response = await self.coda.update_row(
                    self.doc_id,
                    self.profile_table_id,
                    row_id,
                    cells
                )
            
            success = response is not None
            
            if success:
                logger.info(f"Successfully updated member info for row ID: {row_id}")
                # Invalidate cache for this member
                await self._invalidate_member_cache(row_id)
            else:
                logger.error(f"Failed to update member info for row ID: {row_id}")
                
            return success

        except Exception as e:
            logger.error(f"Error updating member info: {e}", exc_info=True)
            return False

    async def _generate_new_id(
        self,
        member_data: Dict[str, Any],
        new_rank: str,
        division: str
    ) -> Optional[str]:
        """Generate new ID number based on rank changes while preserving division."""
        try:
            current_id = member_data.get('ID Number', '')
            if not current_id:
                logger.error("No current ID number found")
                return None

            # Parse current ID (format: XX-YY-ZZZZ)
            parts = current_id.split('-')
            if len(parts) != 3:
                logger.error(f"Invalid ID format: {current_id}")
                return None

            # Keep existing division code from current ID
            division_code = parts[0]  # Preserve existing division code
            
            # Get new rank number
            from ..constants import RANK_CODE_MAPPING
            rank_number = RANK_CODE_MAPPING.get(new_rank.lower())
            unique_number = parts[2]  # Preserve the unique number

            if not rank_number:
                logger.error(f"Invalid rank: {new_rank}")
                return None

            # Generate new ID while preserving division code
            new_id = f"{division_code}-{rank_number}-{unique_number}"
            logger.info(f"Generated new ID: {current_id} -> {new_id}")
            return new_id

        except Exception as e:
            logger.error(f"Error generating new ID: {e}", exc_info=True)
            return None

    async def create_promotion_request(
        self,
        member_id: int,
        current_rank: str,
        new_rank: str,
        reason: str,
        source: Optional[str] = None
    ) -> bool:
        """Create a new promotion request record."""
        try:
            cells = [
                {'column': 'Discord User ID', 'value': str(member_id)},
                {'column': 'Current Rank', 'value': current_rank},
                {'column': 'Proposed Rank', 'value': new_rank},
                {'column': 'Recommendation Reason', 'value': reason},
                {'column': 'Statuspro', 'value': 'Pending'},
                {'column': 'Request Date', 'value': datetime.now(timezone.utc).isoformat()}
            ]
            
            if source:
                cells.append({
                    'column': 'Recommendation Source',
                    'value': source
                })

            # Use the standardized client
            response = await self.coda.request(
                'POST',
                f'docs/{self.doc_id}/tables/{self.promotion_requests_table_id}/rows',
                data={'rows': [{'cells': cells}]}
            )
            
            success = response is not None

            if success:
                logger.info(f"Created promotion request for member {member_id}")
            else:
                logger.error(f"Failed to create promotion request for member {member_id}")

            return success

        except Exception as e:
            logger.error(f"Error creating promotion request: {e}", exc_info=True)
            return False

    async def update_promotion_request_status(
        self,
        request_id: str,
        status: str,
        reason: Optional[str] = None
    ) -> bool:
        """Update the status of a promotion request."""
        try:
            cells = [{'column': 'Statuspro', 'value': status}]
            
            if reason:
                cells.append({
                    'column': 'Recommendation Reason',
                    'value': reason
                })

            # Use the standardized client
            response = await self.coda.update_row(
                self.doc_id,
                self.promotion_requests_table_id,
                request_id,
                cells
            )
            
            success = response is not None

            if success:
                logger.info(f"Updated promotion request {request_id} status to {status}")
            else:
                logger.error(f"Failed to update promotion request {request_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating promotion request status: {e}", exc_info=True)
            return False

    async def update_promotion_records(
        self,
        member_id: int,
        new_rank: str,
        division: str,
        specialization: Optional[str] = None
    ) -> bool:
        """Update member records in profile table after promotion."""
        try:
            # Get current member data
            member_data = await self.get_member_data(member_id)
            if not member_data:
                logger.error(f"No Coda record found for member {member_id}")
                return False

            # Keep existing division if present, only use parameter as fallback
            existing_division = member_data.get('Division')
            update_division = existing_division if existing_division else division

            # Prepare updates
            updates = {
                'Rank': new_rank,
                'Rank Date': datetime.now(timezone.utc).isoformat(),
                'Division': update_division
            }

            if specialization:
                updates['Specialization'] = specialization

            # Update ID number while preserving division
            new_id = await self._generate_new_id(member_data, new_rank, update_division)
            if new_id:
                updates['ID Number'] = new_id

            # Log the update details
            logger.info(f"Sending updates to Coda for member {member_id}: {updates}")
            
            # Use the row ID from member_data
            row_id = member_data.get('id')
            if not row_id:
                logger.error(f"No row ID found for member {member_id}")
                return False
                
            # Special handling for ID Number which might be used as row name
            if 'ID Number' in updates:
                # Update with new name
                cells = [{'column': k, 'value': v} for k, v in updates.items()]
                response = await self.coda.update_row_with_name(
                    self.doc_id,
                    self.profile_table_id,
                    row_id,
                    cells,
                    updates['ID Number']
                )
            else:
                # Normal update
                cells = [{'column': k, 'value': v} for k, v in updates.items()]
                response = await self.coda.update_row(
                    self.doc_id,
                    self.profile_table_id,
                    row_id,
                    cells
                )
                
            success = response is not None

            if success:
                logger.info(f"Successfully updated Coda records for member {member_id}")
                # Invalidate cache
                async with self._cache_lock:
                    self._cache.pop(f"member_{member_id}", None)
                return True
            else:
                logger.error(f"Failed to update Coda records for member {member_id}")
                return False

        except Exception as e:
            logger.error(f"Error updating promotion records: {e}", exc_info=True)
            return False

    async def initialize_columns(self) -> bool:
        """Initialize and validate Coda columns."""
        try:
            # Get columns for both tables
            profile_columns = await self._get_table_columns(self.profile_table_id)
            promotion_columns = await self._get_table_columns(self.promotion_requests_table_id)
            
            # Merge column mappings
            self.columns = {**profile_columns, **promotion_columns}
            
            # Verify required columns
            required_columns = [
                'Discord User ID',
                'Rank',
                'Division',
                'ID Number',
                'Certifications',
                'Rank Date',
                'Completed Missions'
            ]
            
            missing = [col for col in required_columns if col not in self.columns]
            if missing:
                logger.error(f"Missing required columns: {missing}")
                return False
                
            logger.info("Successfully initialized Coda columns")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize columns: {e}", exc_info=True)
            return False

    async def _get_table_columns(self, table_id: str) -> Dict[str, str]:
        """Get column mappings for a table."""
        columns = await self.coda.get_columns(self.doc_id, table_id)
        if not columns:
            raise ValueError(f"Failed to fetch columns for table {table_id}")
            
        return {item['name']: item['id'] for item in columns}

    async def _normalize_certifications(self, certs) -> List[str]:
        """
        Normalize certifications to a list of strings.
        Handles different data formats that might come from Coda.
        """
        if not certs:
            return []
            
        if isinstance(certs, str):
            # Handle comma-separated string
            return [cert.strip() for cert in certs.split(',') if cert.strip()]
        elif isinstance(certs, list):
            # Handle list format
            return [str(cert).strip() for cert in certs if cert]
        else:
            # Handle unexpected types
            return [str(certs).strip()]

    async def check_certification(self, user_id: int, certification: str) -> bool:
        """
        Check if a member has a specific certification.
        
        Args:
            user_id: Discord ID of the member
            certification: ID of the certification to check
            
        Returns:
            bool: True if the member has the certification, False otherwise
        """
        try:
            member_data = await self.get_member_data(user_id)
            if not member_data:
                logger.warning(f"No member data found for user ID {user_id}")
                return False
                
            certifications = member_data.get('Certifications', '')
            cert_list = await self._normalize_certifications(certifications)
            
            return certification in cert_list
        except Exception as e:
            logger.error(f"Error checking certification: {e}", exc_info=True)
            return False

    async def get_member_certifications(self, user_id: int) -> List[str]:
        """
        Get all certifications a member has.
        
        Args:
            user_id: Discord ID of the member
            
        Returns:
            List[str]: List of certification IDs the member has
        """
        try:
            member_data = await self.get_member_data(user_id)
            if not member_data:
                logger.warning(f"No member data found for user ID {user_id}")
                return []
                
            certifications = member_data.get('Certifications', '')
            return await self._normalize_certifications(certifications)
        except Exception as e:
            logger.error(f"Error getting member certifications: {e}", exc_info=True)
            return []

    async def add_certification(self, user_id: int, certification: str) -> bool:
        """
        Add a certification to a member's record.
        
        Args:
            user_id: Discord ID of the member
            certification: ID of the certification to add
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if member already has this certification
            if await self.check_certification(user_id, certification):
                logger.info(f"Member {user_id} already has certification {certification}")
                return True  # Already has it, consider it a success
                
            member_data = await self.get_member_data(user_id)
            if not member_data:
                logger.error(f"No member data found for user ID {user_id}")
                return False
                
            # Get current certifications
            current_certs = member_data.get('Certifications', '')
            cert_list = await self._normalize_certifications(current_certs)
            
            # Add new certification
            cert_list.append(certification)
            
            # Format as comma-separated string for storage
            formatted_certs = ', '.join(cert_list)
            
            # Update in Coda
            success = await self.update_member_info(
                member_data['id'],
                {'Certifications': formatted_certs}
            )
            
            if success:
                logger.info(f"Added certification {certification} to member {user_id}")
            else:
                logger.error(f"Failed to add certification {certification} to member {user_id}")
                
            return success
        except Exception as e:
            logger.error(f"Error adding certification: {e}", exc_info=True)
            return False

    async def remove_certification(self, user_id: int, certification: str) -> bool:
        """
        Remove a certification from a member.
        
        Args:
            user_id: Discord ID of the member
            certification: ID of the certification to remove
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if member has this certification
            if not await self.check_certification(user_id, certification):
                logger.info(f"Member {user_id} doesn't have certification {certification} - nothing to remove")
                return True  # Already doesn't have it, consider it a success
                
            member_data = await self.get_member_data(user_id)
            if not member_data:
                logger.error(f"No member data found for user ID {user_id}")
                return False
                
            # Get current certifications
            current_certs = member_data.get('Certifications', '')
            cert_list = await self._normalize_certifications(current_certs)
            
            # Remove certification
            if certification in cert_list:
                cert_list.remove(certification)
            
            # Format as comma-separated string for storage
            formatted_certs = ', '.join(cert_list)
            
            # Update in Coda
            success = await self.update_member_info(
                member_data['id'],
                {'Certifications': formatted_certs}
            )
            
            if success:
                logger.info(f"Removed certification {certification} from member {user_id}")
            else:
                logger.error(f"Failed to remove certification {certification} from member {user_id}")
                
            return success
        except Exception as e:
            logger.error(f"Error removing certification: {e}", exc_info=True)
            return False

    async def log_certification_change(
        self, 
        user_id: int, 
        certification: str, 
        action: str,
        authorizer_id: int
    ) -> bool:
        """
        Log a certification change in history.
        
        Args:
            user_id: Discord ID of the member
            certification: ID of the certification
            action: 'granted' or 'revoked'
            authorizer_id: Discord ID of the user who authorized the change
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Log the certification change
            from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
            
            # Try to get certification name if available
            cert_name = certification
            if 'CERTIFICATIONS' in globals() and certification in CERTIFICATIONS:
                cert_name = CERTIFICATIONS[certification].get('name', certification)
            elif 'SHIP_CERTIFICATIONS' in globals() and certification in SHIP_CERTIFICATIONS:
                cert_name = SHIP_CERTIFICATIONS[certification].get('name', certification)
            
            # Log the change
            logger.info(
                f"Certification change: {action} {cert_name} ({certification}) "
                f"for user {user_id} by {authorizer_id} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # TODO: If you have an audit log table in Coda, you could store the change there
            
            return True
        except Exception as e:
            logger.error(f"Error logging certification change: {e}", exc_info=True)
            return False

    async def get_certification_report(self) -> Dict[str, Any]:
        """
        Generate a report of certification statistics.
        
        Returns:
            Dict[str, Any]: Dictionary containing certification statistics
        """
        try:
            # Get all members
            members = await self.get_all_members()
            
            # Initialize counters
            cert_counts = {}
            members_with_certs = 0
            total_certs_granted = 0
            
            # Count certifications
            for member in members:
                if not member:
                    continue
                    
                certifications = member.get('Certifications', '')
                cert_list = await self._normalize_certifications(certifications)
                
                if cert_list:
                    members_with_certs += 1
                    total_certs_granted += len(cert_list)
                    
                    for cert in cert_list:
                        cert_counts[cert] = cert_counts.get(cert, 0) + 1
            
            # Calculate statistics
            return {
                'total_members': len([m for m in members if m]),
                'members_with_certs': members_with_certs,
                'total_certs_granted': total_certs_granted,
                'cert_counts': cert_counts,
                'most_common_certs': sorted(cert_counts.items(), key=lambda x: x[1], reverse=True)[:10],
                'least_common_certs': sorted(cert_counts.items(), key=lambda x: x[1])[:10] if cert_counts else []
            }
        except Exception as e:
            logger.error(f"Error generating certification report: {e}", exc_info=True)
            return {}

    async def get_all_members(self) -> List[Dict[str, Any]]:
        """
        Get all members from the Coda table.
        
        Returns:
            List[Dict[str, Any]]: List of member data dictionaries
        """
        try:
            # Get all rows from the member profile table
            response = await self.coda.get_rows(
                self.doc_id,
                self.profile_table_id,
                limit=1000,  # Set a reasonable limit
                use_column_names=True
            )
            
            if not response:
                logger.error("Failed to fetch members from Coda")
                return []
                
            members = []
            for row in response:
                # Clean and store the data
                member_data = self._clean_coda_data(row.get('values', {}))
                member_data['id'] = row['id']  # Include row ID
                members.append(member_data)
                
            logger.info(f"Retrieved {len(members)} members from Coda")
            return members
            
        except Exception as e:
            logger.error(f"Error getting all members: {e}", exc_info=True)
            return []

    async def update_member_field(self, user_id: int, field: str, value: Any) -> bool:
        """
        Update a single field for a member.
        
        Args:
            user_id: Discord ID of the member
            field: Field name to update
            value: New value for the field
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            member_data = await self.get_member_data(user_id)
            if not member_data:
                logger.error(f"No member data found for user ID {user_id}")
                return False
                
            row_id = member_data.get('id')
            if not row_id:
                logger.error(f"No row ID found for member {user_id}")
                return False
                
            return await self.update_member_info(row_id, {field: value})
            
        except Exception as e:
            logger.error(f"Error updating member field: {e}", exc_info=True)
            return False
            
    async def _invalidate_member_cache(self, row_id: str) -> None:
        """Invalidate cache for a specific member row."""
        try:
            async with self._cache_lock:
                # Find all cache entries for this member
                related_keys = []
                for key, cached in self._cache.items():
                    if key.startswith('member_') and 'data' in cached:
                        if cached['data'].get('id') == row_id:
                            related_keys.append(key)
                            
                # Remove all related entries
                for key in related_keys:
                    logger.debug(f"Invalidating cache for {key}")
                    self._cache.pop(key, None)
        except Exception as e:
            logger.error(f"Error invalidating member cache: {e}")
            
    # New method for backup functionality
    async def backup_data(self) -> bool:
        """Create a backup of Coda data."""
        try:
            # Ensure backup directory exists
            os.makedirs(self._backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self._backup_dir, f"coda_backup_{timestamp}.json")
            
            # Get all members
            members = await self.get_all_members()
            
            # Write to file
            with open(backup_file, 'w') as f:
                json.dump(members, f, indent=2)
                
            logger.info(f"Created backup with {len(members)} members at {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return False
    
    # New method for getting promotion requests
    async def get_pending_promotions(self) -> List[Dict[str, Any]]:
        """Get all pending promotion requests."""
        try:
            # Check if we have the promotion requests table ID
            if not self.promotion_requests_table_id:
                logger.error("No promotion_requests_table_id configured")
                return []
                
            # Query Coda for pending requests
            response = await self.coda.get_rows(
                self.doc_id,
                self.promotion_requests_table_id,
                query='"Statuspro":"Pending"',
                use_column_names=True
            )
            
            if not response:
                return []
                
            # Process results
            requests = []
            for row in response:
                # Clean and store the data
                request_data = self._clean_coda_data(row.get('values', {}))
                request_data['id'] = row['id']  # Include row ID
                requests.append(request_data)
                
            logger.info(f"Retrieved {len(requests)} pending promotion requests")
            return requests
            
        except Exception as e:
            logger.error(f"Error getting pending promotions: {e}")
            return []
            
    # New method for finding member by name/handle
    async def find_member_by_name(self, name: str) -> List[Dict[str, Any]]:
        """
        Find members by name or handle.
        
        Args:
            name: Partial name or handle to search for
            
        Returns:
            List[Dict[str, Any]]: List of matching members
        """
        try:
            # Build query using OR conditions
            # This searches across Discord Username, Preferred Name, and In-Game Handle
            query_parts = [
                f'"Discord Username" ~* "{name}"',
                f'"Preferred Name" ~* "{name}"',
                f'"In-Game Handle" ~* "{name}"'
            ]
            query = " OR ".join(query_parts)
            
            # Query Coda
            response = await self.coda.get_rows(
                self.doc_id,
                self.profile_table_id,
                query=query,
                use_column_names=True,
                limit=10  # Reasonable limit for name search
            )
            
            if not response:
                return []
                
            # Process results
            results = []
            for row in response:
                # Clean and store the data
                member_data = self._clean_coda_data(row.get('values', {}))
                member_data['id'] = row['id']  # Include row ID
                results.append(member_data)
                
            logger.info(f"Found {len(results)} members matching '{name}'")
            return results
            
        except Exception as e:
            logger.error(f"Error finding member by name: {e}")
            return []