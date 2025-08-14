# cogs/fixer.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import aiohttp
import asyncio
from typing import Optional, Dict, Any
from urllib.parse import quote
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# ------------------------------ Logging Setup ------------------------------
logger = logging.getLogger('fixer')
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(
    filename='fixer.log',
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=5,
    encoding='utf-8',
    mode='a'
)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# Setup Duplicate Logger for tracking multiple entries
class DuplicateLogHandler:
    def __init__(self, log_file: str = "duplicate_records.log"):
        self.logger = logging.getLogger('duplicate_handler')
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            filename=log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8',
            mode='a'
        )
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        if not self.logger.handlers:
            self.logger.addHandler(handler)

    def log_duplicate(self, discord_user_id: str, discord_username: str, rows: list):
        self.logger.info(f"\nDuplicate Records Found for User ID: {discord_user_id}, Username: {discord_username}")
        for idx, row in enumerate(rows, 1):
            values = row.get('values', {})
            self.logger.info(
                f"Record {idx}:\n"
                f"  Row ID: {row.get('id')}\n"
                f"  Discord User ID: {values.get('Discord User ID', 'N/A')}\n"
                f"  Discord Username: {values.get('Discord Username', 'N/A')}\n"
                f"  ID Number: {values.get('ID Number', 'N/A')}\n"
                f"  Division: {values.get('Division', 'N/A')}\n"
                f"  Rank: {values.get('Rank', 'N/A')}\n"
                f"  Join Date: {values.get('Join Date', 'N/A')}"
            )

duplicate_logger = DuplicateLogHandler()

# ------------------------------ Load Environment Variables ------------------------------
load_dotenv()

# Environment variables with validation
def load_env_variable(var_name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    value = os.getenv(var_name, default)
    if required and not value:
        raise EnvironmentError(f"Missing required environment variable: {var_name}")
    return value

DISCORD_BOT_TOKEN = load_env_variable('DISCORD_BOT_TOKEN', required=True)
CODA_API_TOKEN = load_env_variable('CODA_API_TOKEN', required=True)
DOC_ID = load_env_variable('DOC_ID', required=True)
TABLE_ID = load_env_variable('TABLE_ID', required=True)
GUILD_ID = load_env_variable('GUILD_ID', required=True)
ERROR_CHANNEL_ID = load_env_variable('ERROR_CHANNEL_ID')
FIXER_BATCH_SIZE = load_env_variable('FIXER_BATCH_SIZE', '3')
FIXER_BATCH_DELAY = load_env_variable('FIXER_BATCH_DELAY', '20')

# Convert environment variables to integers with validation
def convert_to_int(value: Optional[str], var_name: str, default: Optional[int] = None, min_value: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        int_value = int(value)
        if min_value is not None and int_value < min_value:
            raise ValueError(f"{var_name} must be at least {min_value}.")
        return int_value
    except ValueError as e:
        logger.warning(f"Invalid value for {var_name}: {value}. Using default: {default}. Error: {e}")
        return default

GUILD_ID_INT = convert_to_int(GUILD_ID, 'GUILD_ID', default=None, min_value=1)
if GUILD_ID_INT is None:
    raise EnvironmentError("Invalid GUILD_ID: must be a positive integer.")

ERROR_CHANNEL_ID_INT = convert_to_int(ERROR_CHANNEL_ID, 'ERROR_CHANNEL_ID') if ERROR_CHANNEL_ID else None
FIXER_BATCH_SIZE_INT = convert_to_int(FIXER_BATCH_SIZE, 'FIXER_BATCH_SIZE', default=3, min_value=1)
FIXER_BATCH_DELAY_INT = convert_to_int(FIXER_BATCH_DELAY, 'FIXER_BATCH_DELAY', default=20, min_value=0)

# ------------------------------ Constants ------------------------------
# Coda.io Column Names
DISCORD_USER_ID_COLUMN = 'Discord User ID'
DISCORD_USERNAME_COLUMN = 'Discord Username'
ID_NUMBER_COLUMN = 'ID Number'
DIVISION_COLUMN = 'Division'
RANK_COLUMN = 'Rank'
JOIN_DATE_COLUMN = 'Join Date'
SPECIALIZATION_COLUMN = 'Specialization'
TYPE_COLUMN = 'Type'

DIVISION_CODES = {
    'Command Staff': 'HQ',
    'Tactical': 'TC',
    'Operations': 'OP',
    'Support': 'SP',
    'Non-Division': 'ND',
    'Ambassador': 'AMB',
    'Associate': 'AS',
}

STANDARD_RANKS = [
    ('Admiral', 'ADM'),
    ('Vice Admiral', 'VADM'),
    ('Rear Admiral', 'RADM'),
    ('Commodore', 'CDRE'),
    ('Fleet Captain', 'FCPT'),
    ('Captain', 'CAPT'),
    ('Commander', 'Cdr'),
    ('Lieutenant Commander', 'Lt Cdr'),
    ('Lieutenant', 'Lt'),
    ('Lieutenant Junior Grade', 'Lt JG'),
    ('Ensign', 'ENS'),
    ('Chief Petty Officer', 'CPO'),
    ('Petty Officer 1st Class', 'PO1'),
    ('Petty Officer 2nd Class', 'PO2'),
    ('Petty Officer 3rd Class', 'PO3'),
    ('Master Crewman', 'MCWM'),
    ('Senior Crewman', 'SCWM'),
    ('Crewman', 'CWM'),
    ('Crewman Apprentice', 'CWA'),
    ('Crewman Recruit', 'CWR'),
    ('Ambassador', 'AMB'),
    ('Associate', 'ASC'),
]

# ------------------------------ Cog Definition ------------------------------
class FixerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.batch_size = FIXER_BATCH_SIZE_INT
        self.batch_delay = FIXER_BATCH_DELAY_INT
        self.max_retries = 5
        self.backoff_factor = 2
        self.semaphore = asyncio.Semaphore(5)
        self.duplicate_logger = duplicate_logger

        # Create mappings for roles and ranks
        self.role_to_rank = {rank_name.lower(): rank_name for rank_name, _ in STANDARD_RANKS}
        self.rank_hierarchy = [rank_name for rank_name, _ in STANDARD_RANKS]

        # Discord role mappings
        self.CODA_TO_DISCORD_RANK_ROLE = {rank[0].lower(): rank[0] for rank in STANDARD_RANKS}
        self.CODA_TO_DISCORD_DIVISION_ROLE = {k.lower(): k.title() for k in DIVISION_CODES.keys()}

    async def coda_api_request(self, session: aiohttp.ClientSession, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make a request to the Coda API with retry logic."""
        url = f'https://coda.io/apis/v1/{endpoint.strip()}'
        headers = {
            'Authorization': f'Bearer {CODA_API_TOKEN}',
            'Content-Type': 'application/json'
        }

        retries = 0
        wait_time = 1

        while retries <= self.max_retries:
            try:
                async with session.request(method, url, headers=headers, json=data) as response:
                    if response.status == 429:
                        retries += 1
                        retry_after = int(response.headers.get('Retry-After', wait_time))
                        await asyncio.sleep(retry_after)
                        wait_time *= self.backoff_factor
                        continue

                    if 200 <= response.status < 300:
                        return await response.json() if response.content_type == 'application/json' else {}

                    logger.error(f"HTTP error {response.status} for {method} request to {url}")
                    return None

            except Exception as err:
                logger.error(f"Request error occurred: {err} - URL: {url}")
                return None

        logger.error(f"Failed after {self.max_retries} retries")
        return None

    async def get_member_row(self, session: aiohttp.ClientSession, discord_user_id: str) -> Optional[Dict[str, Any]]:
        """Get a member's row from Coda based on Discord ID."""
        endpoint = f'docs/{DOC_ID}/tables/{quote(TABLE_ID)}/rows?useColumnNames=true'
        matched_rows = []

        while endpoint:
            response = await self.coda_api_request(session, 'GET', endpoint)
            if response is not None:
                for row in response.get('items', []):
                    values = row.get('values', {})
                    coda_discord_user_id = str(values.get(DISCORD_USER_ID_COLUMN, '')).strip()
                    if coda_discord_user_id == discord_user_id:
                        matched_rows.append(row)
                endpoint = response.get('nextPageLink')
            else:
                break

        if not matched_rows:
            return None
        elif len(matched_rows) == 1:
            return matched_rows[0]
        else:
            self.duplicate_logger.log_duplicate(discord_user_id, '', matched_rows)
            return matched_rows[0]

    async def update_join_date(self, session: aiohttp.ClientSession, member: discord.Member, member_row: Dict[str, Any]) -> bool:
        """Update only the join date in Coda, using standard YYYY-MM-DD format."""
        if not member.joined_at:
            return False

        values = member_row.get('values', {})
        existing_join_date = values.get(JOIN_DATE_COLUMN, '')

        # Format the join date in YYYY-MM-DD format without stellar conversion
        new_join_date = member.joined_at.strftime("%Y-%m-%d")

        if existing_join_date != new_join_date:
            try:
                update_endpoint = f'docs/{DOC_ID}/tables/{quote(TABLE_ID)}/rows/{member_row["id"]}'
                data = {
                    'row': {
                        'cells': [{'column': JOIN_DATE_COLUMN, 'value': new_join_date}]
                    }
                }
                update_response = await self.coda_api_request(session, 'PUT', update_endpoint, data)
                if update_response is not None:
                    logger.info(f"Updated join date for {member.display_name} to {new_join_date}")
                    return True
                else:
                    logger.error(f"Failed to update join date for {member.display_name}")
                    return False
            except Exception as e:
                logger.error(f"Failed to update join date for {member.display_name}: {e}")
                return False
        return False

    async def update_discord_roles_based_on_coda(self, guild: discord.Guild, member_row: Dict[str, Any], member: discord.Member):
        """Update Discord roles to match Coda data."""
        values = member_row.get('values', {})
        coda_rank = values.get(RANK_COLUMN, '').lower()
        coda_division = values.get(DIVISION_COLUMN, '').lower()
        coda_specialization = values.get(SPECIALIZATION_COLUMN, '').lower()

        roles_to_add = []
        roles_to_remove = []

        # Get current roles
        current_role_names = [role.name.lower() for role in member.roles]

        # Process rank roles
        if coda_rank:
            desired_rank_role = self.CODA_TO_DISCORD_RANK_ROLE.get(coda_rank)
            if desired_rank_role:
                if desired_rank_role.lower() not in current_role_names:
                    roles_to_add.append(desired_rank_role)
                # Remove other rank roles
                for rank_role in self.CODA_TO_DISCORD_RANK_ROLE.values():
                    if rank_role.lower() != desired_rank_role.lower() and rank_role.lower() in current_role_names:
                        roles_to_remove.append(rank_role)

        # Process division roles
        if coda_division:
            desired_division_role = self.CODA_TO_DISCORD_DIVISION_ROLE.get(coda_division)
            if desired_division_role:
                if desired_division_role.lower() not in current_role_names:
                    roles_to_add.append(desired_division_role)
                # Remove other division roles
                for division_role in self.CODA_TO_DISCORD_DIVISION_ROLE.values():
                    if division_role.lower() != desired_division_role.lower() and division_role.lower() in current_role_names:
                        roles_to_remove.append(division_role)

        # Add roles
        for role_name in roles_to_add:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                try:
                    await member.add_roles(role, reason="Syncing with Coda data")
                    logger.info(f"Added role {role_name} to {member.display_name}")
                except Exception as e:
                    logger.error(f"Failed to add role {role_name} to {member.display_name}: {e}")

        # Remove roles
        for role_name in roles_to_remove:
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                try:
                    await member.remove_roles(role, reason="Syncing with Coda data")
                    logger.info(f"Removed role {role_name} from {member.display_name}")
                except Exception as e:
                    logger.error(f"Failed to remove role {role_name} from {member.display_name}: {e}")

    async def process_member(self, session: aiohttp.ClientSession, member: discord.Member, counters: Dict[str, int]) -> None:
        """Process a single member, syncing their Discord roles with Coda data and updating join date."""
        try:
            async with self.semaphore:
                logger.info(f"Processing member: {member.display_name} (ID: {member.id})")

                # Find member's data in Coda
                member_row = await self.get_member_row(session, str(member.id))

                if not member_row:
                    logger.warning(f"No Coda entry found for member {member.display_name}")
                    counters['errors'] += 1
                    return

                # Update join date in Coda
                join_date_updated = await self.update_join_date(session, member, member_row)

                # Sync Discord roles with Coda data
                guild = self.bot.get_guild(GUILD_ID_INT)
                if guild:
                    await self.update_discord_roles_based_on_coda(guild, member_row, member)
                    if join_date_updated:
                        counters['updated'] += 1
                else:
                    logger.error(f"Guild with ID {GUILD_ID_INT} not found.")
                    counters['errors'] += 1

                counters['processed'] += 1

        except Exception as e:
            logger.error(f"Error processing member {member.display_name}: {str(e)}")
            counters['errors'] += 1

    @app_commands.command(
        name='fixer',
        description='Synchronize Discord roles with Coda data for all members.'
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guilds(discord.Object(id=GUILD_ID_INT))
    async def fixer_command(self, interaction: discord.Interaction):
        """Command to synchronize all member roles with Coda data."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            logger.error("Guild not found.")
            return

        counters = {'processed': 0, 'updated': 0, 'errors': 0}

        # Ensure all members are loaded
        if not guild.chunked:
            await guild.chunk()

        members = guild.members
        batch = []

        async with aiohttp.ClientSession() as session:
            for member in members:
                if member.bot:  # Skip bot accounts
                    continue

                if not member.display_name or member.display_name.strip() == "":
                    logger.warning(f"Member with ID {member.id} has a blank username. Skipping.")
                    continue

                batch.append(member)
                if len(batch) == self.batch_size:
                    tasks = [self.process_member(session, m, counters) for m in batch]
                    try:
                        await asyncio.gather(*tasks)
                    except Exception as e:
                        logger.error(f"Error processing batch: {e}")
                        if ERROR_CHANNEL_ID_INT:
                            error_channel = self.bot.get_channel(ERROR_CHANNEL_ID_INT)
                            if error_channel:
                                await error_channel.send(f"Error processing batch: {e}")

                    await asyncio.sleep(self.batch_delay)
                    batch = []

            # Process remaining members
            if batch:
                tasks = [self.process_member(session, m, counters) for m in batch]
                try:
                    await asyncio.gather(*tasks)
                except Exception as e:
                    logger.error(f"Error processing final batch: {e}")
                    if ERROR_CHANNEL_ID_INT:
                        error_channel = self.bot.get_channel(ERROR_CHANNEL_ID_INT)
                        if error_channel:
                            await error_channel.send(f"Error processing final batch: {e}")

        # Send completion message
        await interaction.followup.send(
            f"✅ Synchronization completed.\n"
            f"Total Members Processed: {counters['processed']}\n"
            f"Total Updated: {counters['updated']}\n"
            f"Total Errors: {counters['errors']}",
            ephemeral=True
        )
        logger.info(f"Fixer completed. Processed: {counters['processed']}, Updated: {counters['updated']}, Errors: {counters['errors']}")

    @app_commands.command(
        name='fixer_test',
        description='Test synchronization with a single member.'
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guilds(discord.Object(id=GUILD_ID_INT))
    @app_commands.describe(member='The member to test synchronization with.')
    async def fixer_test_command(self, interaction: discord.Interaction, member: discord.Member):
        """Command to test synchronization with a single member."""
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            logger.error("Guild not found.")
            return

        counters = {'processed': 0, 'updated': 0, 'errors': 0}

        async with aiohttp.ClientSession() as session:
            await self.process_member(session, member, counters)

        await interaction.followup.send(
            f"✅ Test synchronization completed for {member.display_name}.\n"
            f"Total Members Processed: {counters['processed']}\n"
            f"Total Updated: {counters['updated']}\n"
            f"Total Errors: {counters['errors']}",
            ephemeral=True
        )
        logger.info(
            f"Fixer test completed for {member.display_name}. "
            f"Processed: {counters['processed']}, Updated: {counters['updated']}, "
            f"Errors: {counters['errors']}"
        )

# Cog setup
async def setup(bot: commands.Bot):
    await bot.add_cog(FixerCog(bot))
    logger.info("FixerCog has been added to the bot.")

