# cogs/fleet_application.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import logging
import logging.handlers
import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# ------------------------------ Logging Setup ------------------------------
logger = logging.getLogger('fleet_application')
logger.setLevel(logging.DEBUG)  # Set to DEBUG for comprehensive logging

handler = logging.handlers.RotatingFileHandler(
    filename='fleet_application.log',
    encoding='utf-8',
    mode='a',
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=5
)
handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# ------------------------------ Load Environment Variables ------------------------------
load_dotenv()

CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
DOC_ID = os.getenv('DOC_ID')
FLEET_APPLICATION_TABLE_ID = os.getenv('FLEET_APPLICATION_TABLE_ID')
GUILD_ID = os.getenv('GUILD_ID')
STAFF_NOTIFICATION_CHANNEL_ID = os.getenv('STAFF_NOTIFICATION_CHANNEL_ID')

logger.info(f"Loaded environment variables:")
logger.info(f"  CODA_API_TOKEN: {'Set' if CODA_API_TOKEN else 'Not Set'}")
logger.info(f"  DOC_ID: {DOC_ID}")
logger.info(f"  FLEET_APPLICATION_TABLE_ID: {FLEET_APPLICATION_TABLE_ID}")
logger.info(f"  GUILD_ID: {GUILD_ID}")
logger.info(f"  STAFF_NOTIFICATION_CHANNEL_ID: {STAFF_NOTIFICATION_CHANNEL_ID}")

missing_vars = []
if not CODA_API_TOKEN:
    missing_vars.append('CODA_API_TOKEN')
if not DOC_ID:
    missing_vars.append('DOC_ID')
if not FLEET_APPLICATION_TABLE_ID:
    missing_vars.append('FLEET_APPLICATION_TABLE_ID')
if not GUILD_ID:
    missing_vars.append('GUILD_ID')
if not STAFF_NOTIFICATION_CHANNEL_ID:
    missing_vars.append('STAFF_NOTIFICATION_CHANNEL_ID')

if missing_vars:
    logger.critical(f"Missing environment variables: {', '.join(missing_vars)}. Please set them in your .env file.")
    exit(1)

try:
    GUILD_ID = int(GUILD_ID)
except ValueError:
    logger.critical("GUILD_ID must be an integer representing your Discord Guild ID.")
    exit(1)

try:
    STAFF_NOTIFICATION_CHANNEL_ID = int(STAFF_NOTIFICATION_CHANNEL_ID)
except ValueError:
    logger.critical("STAFF_NOTIFICATION_CHANNEL_ID must be an integer representing a Discord Channel ID.")
    exit(1)

# ------------------------------ Cog Definition ------------------------------
class FleetApplicationCog(commands.Cog):
    """Cog to handle fleet applications."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.lock = asyncio.Lock()
        self.CODA_COLUMNS = {}  # To store column names and IDs
        self.pending_applicants = {}  # To track users who have started applications
        self.application_status_check.start()  # Start the background task

    async def cog_load(self):
        logger.info("FleetApplicationCog is loading. Fetching Coda.io column IDs.")
        logger.info(f"Using FLEET_APPLICATION_TABLE_ID: {FLEET_APPLICATION_TABLE_ID}")
        await self.fetch_columns_from_coda()
        if not self.validate_columns():
            logger.critical("Required columns are missing in Coda.io table/view. Disabling FleetApplicationCog.")
            await self.bot.remove_cog(self.__class__.__name__)
        else:
            logger.info("FleetApplicationCog loaded successfully with all required columns.")
            rows = await self.list_all_rows()
            if rows is not None:
                logger.info(f"Successfully fetched {len(rows)} rows from the table.")
            else:
                logger.error("Could not fetch rows from the table.")

    def cog_unload(self):
        self.application_status_check.cancel()
        asyncio.create_task(self.session.close())
        logger.info("FleetApplicationCog has been unloaded and aiohttp session closed.")

    # ------------------------------ Coda.io API Methods ------------------------------
    async def coda_api_request(self, method: str, endpoint: str, data: dict = None) -> Optional[Dict[str, Any]]:
        url = f'https://coda.io/apis/v1/{endpoint}'
        headers = {
            'Authorization': f'Bearer {CODA_API_TOKEN}',
            'Content-Type': 'application/json'
        }

        retries = 0
        max_retries = 5
        backoff_factor = 2
        retry_delay = 1

        while retries < max_retries:
            try:
                if method.upper() in ['POST', 'PUT']:
                    logger.debug(f"Request Data: {data}")
                async with self.session.request(method, url, headers=headers, json=data) as response:
                    response_text = await response.text()
                    logger.debug(f"Request URL: {url}")
                    logger.debug(f"Response Status: {response.status}")
                    logger.debug(f"Response Text: {response_text}")

                    if response.status in [200, 202]:
                        logger.debug(f"Coda.io {method} request to {url} successful.")
                        return await response.json()
                    elif response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', retry_delay))
                        logger.warning(f"Rate limited by Coda.io. Retrying after {retry_after} seconds...")
                        await asyncio.sleep(retry_after)
                        retries += 1
                        retry_delay *= backoff_factor
                    else:
                        logger.error(f"Coda.io {method} request to {url} failed with status {response.status}. Response: {response_text}")
                        return None
            except Exception as e:
                logger.error(f"An error occurred during Coda API request to {url}: {e}")
                await asyncio.sleep(retry_delay)
                retries += 1
                retry_delay *= backoff_factor
        logger.error(f"Failed to complete Coda.io {method} request to {url} after {max_retries} retries.")
        return None

    async def fetch_columns_from_coda(self):
        logger.info("Fetching all columns from Coda.io table.")
        endpoint = f'docs/{DOC_ID}/tables/{FLEET_APPLICATION_TABLE_ID}/columns'
        all_columns = {}
        next_page_token = None

        while True:
            current_endpoint = endpoint
            if next_page_token:
                current_endpoint += f'?pageToken={next_page_token}'

            response = await self.coda_api_request('GET', current_endpoint)
            if response and 'items' in response:
                for column in response['items']:
                    all_columns[column['name']] = column['id']
                logger.debug(f"Fetched {len(response['items'])} columns.")
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            else:
                logger.error("Failed to fetch columns from Coda.io.")
                break

        self.CODA_COLUMNS = all_columns
        logger.info(f"Fetched columns from Coda.io: {self.CODA_COLUMNS}")

    def validate_columns(self) -> bool:
        required_columns = [
            'Service ID', 'Availability', 'Roles', 'Commitment',
            'Application Status', 'Reasoning', 'Staff Notified', 'Applicant Notified', 'Discord User ID'
        ]
        missing_columns = [col for col in required_columns if col not in self.CODA_COLUMNS]
        if missing_columns:
            logger.critical(f"Missing required columns in Coda.io table/view: {', '.join(missing_columns)}")
            return False
        return True

    async def list_all_rows(self) -> Optional[list]:
        logger.info("Fetching all rows from Coda.io table.")
        endpoint = f'docs/{DOC_ID}/tables/{FLEET_APPLICATION_TABLE_ID}/rows'
        all_rows = []
        next_page_token = None

        while True:
            current_endpoint = endpoint
            if next_page_token:
                current_endpoint += f'?pageToken={next_page_token}'

            response = await self.coda_api_request('GET', current_endpoint)
            if response and 'items' in response:
                all_rows.extend(response['items'])
                logger.debug(f"Fetched {len(response['items'])} rows.")
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            else:
                logger.error("Failed to fetch rows from Coda.io.")
                break

        logger.info(f"Total rows fetched: {len(all_rows)}")
        return all_rows

    def normalize_value(self, value):
        if isinstance(value, list):
            if value:
                value = value[0]
            else:
                value = ''
        elif isinstance(value, dict):
            value = value.get('name', '')
        if value:
            return str(value).strip().lower()
        else:
            return ''

    async def get_application_by_user(self, user_id: int) -> Optional[dict]:
        logger.debug(f"Checking for existing pending application for user ID: {user_id}")
        all_rows = await self.list_all_rows()
        if all_rows is not None:
            discord_user_id_column = self.CODA_COLUMNS['Discord User ID']
            status_column = self.CODA_COLUMNS['Application Status']
            for row in all_rows:
                values = row.get('values', {})
                discord_user_id = values.get(discord_user_id_column)
                status = values.get(status_column)
                status = self.normalize_value(status)
                if discord_user_id == str(user_id) and status == 'pending':
                    logger.debug(f"Found pending application for user ID: {user_id}")
                    return row
        else:
            logger.error("Failed to fetch rows from Coda.io table.")
        logger.debug(f"No pending application found for user ID: {user_id}")
        return None

    async def get_processed_applications(self) -> list:
        logger.debug("Retrieving processed applications for notification.")
        all_rows = await self.list_all_rows()
        processed_applications = []
        if all_rows is not None:
            status_column = self.CODA_COLUMNS['Application Status']
            applicant_notified_column = self.CODA_COLUMNS['Applicant Notified']
            for row in all_rows:
                values = row.get('values', {})
                status = values.get(status_column)
                notified = values.get(applicant_notified_column)
                logger.debug(f"Row ID: {row.get('id')}, Status: {status!r}, Applicant Notified: {notified!r}")
                status = self.normalize_value(status)
                notified = self.normalize_value(notified)
                if status in ['approved', 'denied'] and notified != 'yes':
                    processed_applications.append(row)
            logger.debug(f"Found {len(processed_applications)} processed applications.")
        else:
            logger.error("Failed to fetch rows from Coda.io table.")
        return processed_applications

    async def get_pending_applications(self) -> list:
        logger.debug("Retrieving applications with status 'Pending'.")
        all_rows = await self.list_all_rows()
        pending_applications = []
        if all_rows is not None:
            status_column = self.CODA_COLUMNS['Application Status']
            staff_notified_column = self.CODA_COLUMNS['Staff Notified']
            for row in all_rows:
                values = row.get('values', {})
                logger.debug(f"Row ID: {row.get('id')}, Available Keys: {list(values.keys())}")
                status = values.get(status_column)
                notified = values.get(staff_notified_column)
                logger.debug(f"Row ID: {row.get('id')}, Status: {status!r}, Staff Notified: {notified!r}")
                status = self.normalize_value(status)
                notified = self.normalize_value(notified)
                if status == 'pending' and notified != 'yes':
                    pending_applications.append(row)
            logger.debug(f"Found {len(pending_applications)} pending applications.")
        else:
            logger.error("Failed to fetch rows from Coda.io table.")
        return pending_applications

    async def update_application_field(self, row_id: str, field_name: str, value: str):
        logger.debug(f"Updating application row ID: {row_id}, setting '{field_name}' to '{value}'.")
        data = {
            'row': {
                'cells': [
                    {'column': self.CODA_COLUMNS[field_name], 'value': value}
                ]
            }
        }
        endpoint = f'docs/{DOC_ID}/tables/{FLEET_APPLICATION_TABLE_ID}/rows/{row_id}'
        response = await self.coda_api_request('PUT', endpoint, data)
        if response:
            logger.info(f"Updated application row ID: {row_id}, set '{field_name}' to '{value}'.")
            return True
        else:
            logger.error(f"Failed to update application row ID: {row_id}, set '{field_name}' to '{value}'.")
            return False

    async def notify_staff_of_pending_applications(self, pending_applications: list):
        channel = self.bot.get_channel(STAFF_NOTIFICATION_CHANNEL_ID)
        if not channel:
            logger.error(f"Staff notification channel with ID {STAFF_NOTIFICATION_CHANNEL_ID} not found.")
            return

        for application in pending_applications:
            values = application.get('values', {})
            discord_user_id_column = self.CODA_COLUMNS['Discord User ID']
            service_id_column = self.CODA_COLUMNS['Service ID']
            roles_column = self.CODA_COLUMNS['Roles']
            availability_column = self.CODA_COLUMNS['Availability']
            commitment_column = self.CODA_COLUMNS['Commitment']
            reasoning_column = self.CODA_COLUMNS['Reasoning']

            applicant_id = values.get(discord_user_id_column, 'Unknown')
            service_id = values.get(service_id_column, 'Unknown')
            roles = values.get(roles_column, 'Unknown')
            availability = values.get(availability_column, 'Unknown')
            commitment = values.get(commitment_column, 'Unknown')
            reasoning = values.get(reasoning_column, 'No reasoning provided.')
            application_id = application.get('id', 'Unknown')

            message = (
                f"**New Pending Application**\n"
                f"**Applicant Discord ID:** {applicant_id}\n"
                f"**Service ID:** {service_id}\n"
                f"**Roles Applied For:** {roles}\n"
                f"**Availability:** {availability}\n"
                f"**Commitment:** {commitment}\n"
                f"**Reasoning:** {reasoning}\n"
                f"Please review the application in Coda.io.\n"
                f"Application ID: {application_id}"
            )

            try:
                await channel.send(message)
                logger.info(f"Notified staff about new pending application from Discord ID {applicant_id}.")
                await self.update_application_field(application_id, 'Staff Notified', 'Yes')
            except Exception as e:
                logger.error(f"Failed to send notification to staff: {e}")

    @app_commands.command(name="applyfleet", description="Apply to join the fleet.")
    # Removed @app_commands.guilds(discord.Object(id=GUILD_ID)) so this can sync globally
    async def applyfleet(self, interaction: discord.Interaction):
        logger.info(f"'/applyfleet' command invoked by {interaction.user}.")
        await interaction.response.defer(ephemeral=True)

        try:
            dm_channel = await interaction.user.create_dm()
            logger.info(f"Started fleet application DM with {interaction.user}")

            existing_application = await self.get_application_by_user(interaction.user.id)
            if existing_application:
                await dm_channel.send("You already have a pending application. Please wait for it to be reviewed.")
                await interaction.followup.send("You already have a pending application.", ephemeral=True)
                return

            form_link = "https://coda.io/form/Fleet-System-Application-Form_dZBuJhk5RE3"

            await dm_channel.send(
                f"Hello! To apply for the fleet, please fill out the following form:\n\n"
                f"{form_link}\n\n"
                f"Please make sure to enter your Discord User ID and HLN Service ID in the form so we can identify you.\n"
                f"Your Discord User ID is: **{interaction.user.id}**\n"
                f"You can find your HLN Service ID by running the `/profile` command.\n"
                f"Your Service ID is in the format `HQ-1-0001`."
            )
            await interaction.followup.send("I've sent you a DM with the application form link!", ephemeral=True)

            self.pending_applicants[interaction.user.id] = {
                'discord_user_id': str(interaction.user.id),
                'notified': False
            }

        except discord.Forbidden:
            await interaction.followup.send("I couldn't send you a DM. Please adjust your privacy settings.", ephemeral=True)
            logger.error(f"Failed to send DM to {interaction.user}")

    @tasks.loop(minutes=15)
    async def application_status_check(self):
        logger.info("Checking for application status updates...")

        await self.check_new_applications()

        processed_applications = await self.get_processed_applications()
        logger.info(f"Processing {len(processed_applications)} applications that were approved or denied.")

        for application in processed_applications:
            values = application.get('values', {})
            discord_user_id_column = self.CODA_COLUMNS['Discord User ID']
            status_column = self.CODA_COLUMNS['Application Status']
            reasoning_column = self.CODA_COLUMNS['Reasoning']
            applicant_notified_column = self.CODA_COLUMNS['Applicant Notified']

            discord_user_id = values.get(discord_user_id_column)
            application_status = values.get(status_column)
            reasoning = values.get(reasoning_column, '')
            notified = values.get(applicant_notified_column, 'No')

            application_status = self.normalize_value(application_status)
            notified = self.normalize_value(notified)

            logger.debug(f"Application ID: {application.get('id')}, Discord User ID: {discord_user_id}, Status: {application_status}, Applicant Notified: {notified}")

            if discord_user_id and application_status and notified != 'yes':
                try:
                    user = self.bot.get_user(int(discord_user_id))
                    if not user:
                        logger.warning(f"User with ID {discord_user_id} not found in bot's cache.")
                        user = await self.bot.fetch_user(int(discord_user_id))
                        if not user:
                            logger.error(f"User with ID {discord_user_id} could not be fetched.")
                            continue
                except Exception as e:
                    logger.error(f"Error fetching user with ID {discord_user_id}: {e}")
                    continue

                try:
                    dm_channel = await user.create_dm()
                    if application_status == 'approved':
                        await dm_channel.send(
                            "Congratulations! Your fleet application has been approved. Welcome aboard!\n"
                            "Please wait for further instructions."
                        )
                        logger.info(f"Sent approval message to {user}")
                    elif application_status == 'denied':
                        message = "Your fleet application has been denied."
                        if reasoning:
                            message += f"\nReason: {reasoning}"
                        await dm_channel.send(message)
                        logger.info(f"Sent denial message to {user}")
                    else:
                        logger.warning(f"Unknown application status '{application_status}' for user {user}")

                    await self.update_application_field(application['id'], 'Applicant Notified', 'Yes')
                except discord.Forbidden:
                    logger.error(f"Failed to send DM to {user}. The user may have DMs disabled.")
                except Exception as e:
                    logger.error(f"An error occurred while sending DM to {user}: {e}")
            else:
                logger.warning(f"Skipping application ID {application.get('id')} due to missing data.")

        logger.info(f"Processed {len(processed_applications)} applications that were approved or denied.")

        pending_applications = await self.get_pending_applications()
        if pending_applications:
            await self.notify_staff_of_pending_applications(pending_applications)
            logger.info(f"Notified staff about {len(pending_applications)} pending applications.")
        else:
            logger.info("No new pending applications to notify staff about.")

    async def check_new_applications(self):
        if not self.pending_applicants:
            return

        all_rows = await self.list_all_rows()
        if all_rows is not None:
            discord_user_id_column = self.CODA_COLUMNS['Discord User ID']
            for row in all_rows:
                values = row.get('values', {})
                discord_user_id = values.get(discord_user_id_column)
                if discord_user_id and int(discord_user_id) in self.pending_applicants:
                    user_id = int(discord_user_id)
                    if not self.pending_applicants[user_id]['notified']:
                        user = self.bot.get_user(user_id)
                        if user:
                            try:
                                dm_channel = await user.create_dm()
                                await dm_channel.send("Thank you! Your application has been received and is pending review.")
                                logger.info(f"Confirmed application submission with {user}")
                                self.pending_applicants[user_id]['notified'] = True
                            except discord.Forbidden:
                                logger.error(f"Failed to send DM to {user}")
            self.pending_applicants = {k: v for k, v in self.pending_applicants.items() if not v['notified']}
        else:
            logger.error("Failed to fetch rows from Coda.io table.")

    @application_status_check.before_loop
    async def before_application_status_check(self):
        await self.bot.wait_until_ready()
        logger.info("Application status check task is starting...")

async def setup(bot: commands.Bot):
    await bot.add_cog(FleetApplicationCog(bot))
    logger.info("FleetApplicationCog has been added to the bot.")
