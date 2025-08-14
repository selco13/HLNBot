import discord
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import string
import secrets
from ..constants import DIVISION_CODES, RANK_NUMBERS

logger = logging.getLogger('onboarding')

class CodaHandler:
    def __init__(self, bot_cog):
        self.cog = bot_cog
        self.lock = asyncio.Lock()
        self.columns = {}

    async def initialize(self) -> bool:
        """Initialize handler and validate Coda setup."""
        try:
            # Verify all required columns exist
            required_columns = {
                'ID Number': 'Member ID',
                'Star Citizen Handle': 'Game handle',
                'Discord Username': 'Discord name',
                'Division': 'Current division',
                'Rank': 'Current rank',
                'Token': 'Registration token',
                'Status': 'Current status',
                'Discord User ID': 'Discord ID',
                'Type': 'Member type',
                'Preferred Gameplay': 'Gameplay preferences',
                'Other Interests': 'Other interests',
                'Started At': 'Start timestamp',
                'Join Date': 'Join timestamp',
                'Last Reminder Sent': 'Last reminder timestamp'
            }

            response = await self.cog.coda_api_request(
                'GET',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/columns'
            )

            if not response or 'items' not in response:
                logger.error("Failed to fetch Coda columns")
                return False

            # Map column names to IDs
            self.columns = {col['name']: col['id'] for col in response['items']}

            # Verify required columns
            missing = [name for name in required_columns if name not in self.columns]
            if missing:
                logger.error(f"Missing required columns: {', '.join(missing)}")
                return False

            logger.info("Successfully initialized Coda handler")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Coda handler: {e}")
            return False

    async def create_initial_record(self, member: discord.Member, member_type: str) -> Optional[str]:
        """Create initial record for new member."""
        async with self.lock:
            try:
                # Generate new ID and token
                division_code = DIVISION_CODES['Non-Division']
                rank_name = 'Crewman Recruit' if member_type == 'Member' else 'Associate'
                rank_number = RANK_NUMBERS.get(rank_name, 21 if member_type == 'Member' else 50)
                
                id_number = await self.generate_unique_id(division_code, rank_number)
                if not id_number:
                    return None

                token = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
                now = datetime.now(timezone.utc).isoformat()

                # Create initial record
                data = {
                    'rows': [{
                        'cells': [
                            {'column': self.columns['ID Number'], 'value': id_number},
                            {'column': self.columns['Discord User ID'], 'value': str(member.id)},
                            {'column': self.columns['Discord Username'], 'value': str(member)},
                            {'column': self.columns['Division'], 'value': 'Non-Division'},
                            {'column': self.columns['Rank'], 'value': rank_name},
                            {'column': self.columns['Token'], 'value': token},
                            {'column': self.columns['Status'], 'value': 'Started'},
                            {'column': self.columns['Type'], 'value': member_type},
                            {'column': self.columns['Started At'], 'value': now},
                            {'column': self.columns['Join Date'], 'value': now}
                        ]
                    }]
                }

                response = await self.cog.coda_api_request(
                    'POST',
                    f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows',
                    data=data
                )

                if response and 'id' in response:
                    logger.info(f"Created initial record for {member}")
                    return response['id']
                else:
                    logger.error(f"Failed to create record for {member}")
                    return None

            except Exception as e:
                logger.error(f"Error creating initial record: {e}")
                return None

    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate token and return member data if valid."""
        try:
            response = await self.cog.coda_api_request(
                'GET',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows',
                params={
                    'query': f'Token="{token}" and Status in ["Started","Unused"]',
                    'useColumnNames': 'true'
                }
            )

            if response and 'items' in response and response['items']:
                return {
                    'row_id': response['items'][0]['id'],
                    'values': response['items'][0].get('values', {}),
                    'Type': response['items'][0].get('values', {}).get('Type', 'Member')
                }
            return None

        except Exception as e:
            logger.error(f"Error validating token: {e}")
            return None

    async def is_token_expired(self, member_data: Dict[str, Any]) -> bool:
        """Check if token has expired."""
        try:
            started_at = member_data['values'].get('Started At')
            if not started_at:
                return True

            started_datetime = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            hours_since_start = (datetime.now(timezone.utc) - started_datetime).total_seconds() / 3600
            return hours_since_start > self.cog.TOKEN_EXPIRY_HOURS

        except Exception as e:
            logger.error(f"Error checking token expiry: {e}")
            return True

    async def complete_registration(self, row_id: str) -> bool:
        """Complete registration in Coda."""
        try:
            updates = {
                'Status': 'Active',
                'Join Date': datetime.now(timezone.utc).isoformat()
            }

            data = {
                'row': {
                    'cells': [
                        {'column': self.columns[key], 'value': value}
                        for key, value in updates.items()
                    ]
                }
            }

            response = await self.cog.coda_api_request(
                'PUT',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows/{row_id}',
                data=data
            )

            return bool(response)

        except Exception as e:
            logger.error(f"Error completing registration: {e}")
            return False

    async def generate_unique_id(self, division_code: str, rank_number: int) -> Optional[str]:
        """Generate unique member ID."""
        try:
            existing_ids = set()
            response = await self.cog.coda_api_request(
                'GET',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows',
                params={'useColumnNames': 'true'}
            )

            if response and 'items' in response:
                for item in response['items']:
                    id_number = item.get('values', {}).get('ID Number')
                    if id_number:
                        existing_ids.add(id_number)

            max_attempts = 100
            for _ in range(max_attempts):
                random_part = ''.join(secrets.choice(string.digits) for _ in range(4))
                id_number = f"{division_code}-{rank_number:02d}-{random_part}"
                
                if id_number not in existing_ids:
                    return id_number

            logger.error(f"Failed to generate unique ID after {max_attempts} attempts")
            return None

        except Exception as e:
            logger.error(f"Error generating unique ID: {e}")
            return None

    async def update_survey_data(self, row_id: str, updates: Dict[str, Any]) -> bool:
        """Update survey data in Coda."""
        try:
            data = {
                'row': {
                    'cells': [
                        {'column': self.columns[key], 'value': value}
                        for key, value in updates.items()
                        if key in self.columns
                    ]
                }
            }

            response = await self.cog.coda_api_request(
                'PUT',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows/{row_id}',
                data=data
            )

            return bool(response)

        except Exception as e:
            logger.error(f"Error updating survey data: {e}")
            return False

    async def get_member_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get member data from Coda."""
        try:
            response = await self.cog.coda_api_request(
                'GET',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows',
                params={
                    'query': f'Discord User ID="{user_id}"',
                    'useColumnNames': 'true'
                }
            )

            if response and 'items' in response and response['items']:
                return response['items'][0].get('values', {})
            return None

        except Exception as e:
            logger.error(f"Error getting member data: {e}")
            return None

    async def get_pending_onboardings(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending onboardings."""
        try:
            response = await self.cog.coda_api_request(
                'GET',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows',
                params={
                    'query': 'Status="Started"',
                    'useColumnNames': 'true'
                }
            )

            pending = {}
            if response and 'items' in response:
                for item in response['items']:
                    values = item.get('values', {})
                    user_id = values.get('Discord User ID')
                    if user_id:
                        started_at = datetime.fromisoformat(values.get('Started At', '').replace('Z', '+00:00'))
                        last_reminder = None
                        if values.get('Last Reminder Sent'):
                            last_reminder = datetime.fromisoformat(values['Last Reminder Sent'].replace('Z', '+00:00'))
                        
                        pending[user_id] = {
                            'Row ID': item['id'],
                            'Started At': started_at,
                            'Last Reminder Sent': last_reminder
                        }

            return pending

        except Exception as e:
            logger.error(f"Error getting pending onboardings: {e}")
            return {}

    async def update_reminder_sent(self, row_id: str) -> bool:
        """Update last reminder timestamp."""
        try:
            data = {
                'row': {
                    'cells': [
                        {
                            'column': self.columns['Last Reminder Sent'],
                            'value': datetime.now(timezone.utc).isoformat()
                        }
                    ]
                }
            }

            response = await self.cog.coda_api_request(
                'PUT',
                f'docs/{self.cog.DOC_ID}/tables/{self.cog.TABLE_ID}/rows/{row_id}',
                data=data
            )

            return bool(response)

        except Exception as e:
            logger.error(f"Error updating reminder timestamp: {e}")
            return False