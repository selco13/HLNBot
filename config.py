# config.py

import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Star Citizen API Configuration
STAR_CITIZEN_API_KEY = os.getenv('STAR_CITIZEN_API_KEY')  # Ensure this key is set in .env

# Discord Bot Token
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set.")

# Guild (Server) ID - if multiple IDs are provided, take the first one
GUILD_ID_STR = os.getenv('GUILD_ID')
if GUILD_ID_STR is None:
    raise ValueError("GUILD_ID environment variable is not set.")
try:
    if ',' in GUILD_ID_STR:
        GUILD_ID = int(GUILD_ID_STR.split(',')[0].strip())
    else:
        GUILD_ID = int(GUILD_ID_STR.strip())
except ValueError:
    raise ValueError("GUILD_ID must be an integer.")

# Add to config.py validation section
if not os.getenv('USERS_TABLE_ID'):
    raise ValueError("USERS_TABLE_ID environment variable is not set.")

# Feedback Channel ID
FEEDBACK_CHANNEL_ID_STR = os.getenv('FEEDBACK_CHANNEL_ID')
if FEEDBACK_CHANNEL_ID_STR is None:
    raise ValueError("FEEDBACK_CHANNEL_ID environment variable is not set.")

try:
    FEEDBACK_CHANNEL_ID = int(FEEDBACK_CHANNEL_ID_STR)
except ValueError:
    raise ValueError("FEEDBACK_CHANNEL_ID must be an integer.")

# Coda.io Configuration
CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
DOC_ID = os.getenv('DOC_ID')  # Your Coda.io doc ID
TABLE_ID = os.getenv('TABLE_ID')  # Your Coda.io table ID

if CODA_API_TOKEN is None:
    raise ValueError("CODA_API_TOKEN environment variable is not set.")
if DOC_ID is None:
    raise ValueError("DOC_ID environment variable is not set.")
if TABLE_ID is None:
    raise ValueError("TABLE_ID environment variable is not set.")

# Banking Table IDs
ACCOUNTS_TABLE_ID = 'grid--KJPwOfQpY'
TRANSACTIONS_TABLE_ID = 'grid-ZEnSNOlK7r'

# Resource Management Table IDs
INVENTORIES_TABLE_ID = 'grid-qu2cj2RuuV'
RESOURCE_LOGS_TABLE_ID = 'grid-ZoUGgazgA1'

SHIPS_TABLE_ID = 'grid--AN5-WNrfv'
USERS_TABLE_ID = os.getenv('USERS_TABLE_ID')

PROMOTION_REQUESTS_TABLE_ID = os.getenv('PROMOTION_REQUESTS_TABLE_ID')
if PROMOTION_REQUESTS_TABLE_ID is None:
    raise ValueError("PROMOTION_REQUESTS_TABLE_ID environment variable is not set.")

# Channel IDs with Error Handling
def get_channel_id(var_name):
    value_str = os.getenv(var_name)
    if value_str is None:
        raise ValueError(f"{var_name} environment variable is not set.")
    try:
        return int(value_str)
    except ValueError:
        raise ValueError(f"{var_name} must be an integer.")

GAME_NEWS_CHANNEL_ID = get_channel_id('GAME_NEWS_CHANNEL_ID')
ADMIN_NOTIFICATIONS_CHANNEL_ID = get_channel_id('ADMIN_NOTIFICATIONS_CHANNEL_ID')

# Fetch Interval
FETCH_INTERVAL_MINUTES_STR = os.getenv('FETCH_INTERVAL_MINUTES', '10')  # Default to 10 minutes if not set
try:
    FETCH_INTERVAL_MINUTES = int(FETCH_INTERVAL_MINUTES_STR)
except ValueError:
    raise ValueError("FETCH_INTERVAL_MINUTES must be an integer.")

# Authorized Roles for Manual Fetch
AUTHORIZED_ROLE_IDS = set()
authorized_roles = os.getenv('AUTHORIZED_ROLE_IDS')
if authorized_roles:
    try:
        AUTHORIZED_ROLE_IDS = set(int(role_id.strip()) for role_id in authorized_roles.split(',') if role_id.strip())
    except ValueError:
        raise ValueError("AUTHORIZED_ROLE_IDS must be a comma-separated list of integers.")

# Raid Protection Configurations
RAID_PROTECTION_ENABLED = True
ANTI_SPAM_ENABLED = True
ANTI_RAID_ENABLED = True
ANTI_ADULT_SPAM_ENABLED = True  # Added for adult website spam protection

# Anti-Spam Settings
SPAM_MESSAGE_LIMIT = 5  # Number of messages
SPAM_TIMEFRAME = 10  # Seconds
SPAM_MUTE_DURATION = 300  # Seconds (5 minutes)

# Anti-Raid Settings
RAID_JOIN_LIMIT = 10  # Number of joins
RAID_TIMEFRAME = 60  # Seconds
RAID_ACTION = 'ban'  # Options: 'mute', 'ban', 'kick'

# Adult Spam Settings
ADULT_SPAM_ACTION = 'mute'  # Action to take: 'mute' or 'ban'

# Logging Channel with Error Handling
LOGGING_CHANNEL_ID = get_channel_id('LOGGING_CHANNEL_ID')  # Ensure this is set in .env

AUDIT_LOG_CHANNEL_ID = int(os.getenv('AUDIT_LOG_CHANNEL_ID', 0))
AAR_CHANNEL_ID = int(os.getenv('AAR_CHANNEL_ID', 0))
STAFF_NOTIFICATION_CHANNEL_ID = int(os.getenv('STAFF_NOTIFICATION_CHANNEL_ID', 0))

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
if LOG_LEVEL not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
    LOG_LEVEL = 'INFO'
    print(f"Invalid LOG_LEVEL specified, defaulting to {LOG_LEVEL}")

# Optional: Configure specific loggers
LOGGER_LEVELS = {
    'discord': 'WARNING',      # Less verbose discord.py logging
    'discord.http': 'WARNING', # Less verbose HTTP requests
    'aiohttp': 'WARNING',      # Less verbose HTTP client
    'websockets': 'WARNING',   # Less verbose websocket logging
}

# Standard Ranks with their abbreviations (Added for rank checking)
STANDARD_RANKS = [
    ('Admiral', 'ADM'),
    ('Vice Admiral', 'VADM'),
    ('Rear Admiral', 'RADM'),
    ('Commodore', 'CDRE'),
    ('Fleet Captain', 'FCpt'),
    ('Captain', 'CAPT'),
    ('Commander', 'Cdr'),
    ('Lieutenant Commander', 'Lt Cmdr'),
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
    ('Associate', 'ASC')
]

# List of regex patterns to detect adult websites (Added for spam detection)
ADULT_WEBSITE_PATTERNS = [
    r'\b(?:adult|porn|xxx|sex)\b',  # Simple keywords
    r'\b(?:escort)\b',
    r'(?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)?(?:adultsite|pornsite|sexchat)\.[a-z]{2,}',  # Example domains
    # Add more patterns as needed
]

# Test Function
if __name__ == "__main__":
    print("Configuration Loaded Successfully!")
    print(f"Star Citizen API Key: {STAR_CITIZEN_API_KEY}")
    print(f"Discord Bot Token: {DISCORD_BOT_TOKEN}")
    print(f"Guild ID: {GUILD_ID}")
    print(f"Feedback Channel ID: {FEEDBACK_CHANNEL_ID}")
    print(f"Coda.io API Token: {CODA_API_TOKEN}")
    print(f"Coda.io Doc ID: {DOC_ID}")
    print(f"Coda.io Table ID: {TABLE_ID}")
    print(f"Game News Channel ID: {GAME_NEWS_CHANNEL_ID}")
    print(f"Admin Notifications Channel ID: {ADMIN_NOTIFICATIONS_CHANNEL_ID}")
    print(f"Fetch Interval (Minutes): {FETCH_INTERVAL_MINUTES}")
    print(f"Authorized Role IDs: {AUTHORIZED_ROLE_IDS}")
    print(f"Logging Channel ID: {LOGGING_CHANNEL_ID}")

FORCE_SYNC_COMMANDS = False  # Set to True only when you want to force sync
