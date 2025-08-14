"""Constants for the profile cog with AAR integration."""

import os
from dotenv import load_dotenv
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Union

# Import main constants as needed
from cogs.constants import (
    FLEET_COMPONENTS, DIVISION_CODES, RANKS, RANK_CODE_MAPPING, RANK_NUMBERS,
    RANK_ABBREVIATIONS, STANDARD_RANK_ABBREVIATIONS, MEMBER_ROLE_THRESHOLD,
    REQUIRED_STANDARD_RANKS, HIGH_RANKS, ROLE_SPECIALIZATIONS, DIVISION_RANKS,
    DIVISION_TO_STANDARD_RANK, STANDARD_TO_DIVISION_RANK, FLEET_TO_STANDARD_RANK,
    STANDARD_ABBREVS, DIVISION_ABBREVS, ALL_RANK_ABBREVIATIONS
)

# Setup logger
logger = logging.getLogger('profile.constants')


# Load environment variables
load_dotenv()

# Get configuration from environment variables
DOC_ID = os.getenv("DOC_ID", "iTSZEM9OQo")
TABLE_ID = os.getenv("TABLE_ID") or os.getenv("PROFILE_TABLE_ID", "grid--ABwp3mJVA")
GUILD_ID = int(os.getenv("GUILD_ID", "1058522038945460327"))
PROMOTIONS_CHANNEL_ID = int(os.getenv("PROMOTIONS_CHANNEL_ID", "1071114194906251415"))
AUDIT_LOG_CHANNEL_ID = int(os.getenv("AUDIT_LOG_CHANNEL_ID", "1093754008813973565"))
ADMIN_NOTIFICATIONS_CHANNEL_ID = int(os.getenv("ADMIN_NOTIFICATIONS_CHANNEL_ID", "1093754008813973565"))
AAR_CHANNEL_ID = int(os.getenv("AAR_CHANNEL_ID", "1322652798378315776"))  # For AAR integration
STAFF_NOTIFICATION_CHANNEL_ID = int(os.getenv("STAFF_NOTIFICATION_CHANNEL_ID", "1093754008813973565"))

# Coda column IDs based on your provided mapping
FIELD_ID_NUMBER = "c-bgJ5QegMDm"
FIELD_SC_HANDLE = "c-9Z1okPugmt"
FIELD_PHOTO = "c-5sRF_w-DFf"
FIELD_DISCORD_USERNAME = "c-z8KBXfHzU3"
FIELD_DIVISION = "c-bQisz-FLUQ"
FIELD_FLEET_WING = "c-aMCkZwSMw9"
FIELD_SHIP_ASSIGNMENT = "c-1dfLBItEI1"
FIELD_RANK = "c-1EY3awJx4r"
FIELD_REGISTRATION_TOKEN = "c-rYfZufmMWt"
FIELD_STATUS = "c-QOeut2ZZHY"
FIELD_DISCORD_USER_ID = "c-QgM-J6GI3o"
FIELD_AWARDS = "c-iB1E96e68D"
FIELD_CERTIFICATIONS = "c-VUj3sz6llh"
FIELD_SPECIALIZATION = "c-ClTj_yaH0y"
FIELD_TYPE = "c-W65Lild9o8"
FIELD_JOIN_DATE = "c-LJhvTGxeOy"
FIELD_PREFERRED_GAMEPLAY = "c-X1vTclwJfZ"
FIELD_OTHER_INTERESTS = "c-cdq71TofKm"
FIELD_REASON_FOR_ASSOCIATION = "c-aT8lYxgL-V"
FIELD_STARTED_AT = "c-h24jEPuttn"
FIELD_LAST_REMINDER_SENT = "c-h8JZ9JlpKW"
FIELD_SECURITY_CLEARANCE = "c-Pz9QaIjbo5"
FIELD_CLASSIFIED_INFO = "c-3gAHLS-7xw"
FIELD_PREVIOUS_ASSIGNMENTS = "c-S51FTsljNZ"
FIELD_SPECIAL_OPERATIONS = "c-Uu2e-QyVlv"
FIELD_STRATEGIC_PLANNING = "c-6XeKWuGmXT"
FIELD_COMMAND_HISTORY = "c-B2JZq3kFdF"
FIELD_COMBAT_MISSIONS = "c-ANbijAO8b7"
FIELD_MISSION_OUTCOMES = "c-XmBL_n-H8b"
FIELD_STRATEGIC_IMPACT = "c-zgAOC7rxDJ"
FIELD_CLASSIFIED_OPERATIONS = "c-SY4ffI_7Eu"
FIELD_STRATEGIC_ASSESSMENT = "c-eGm9A-KF2n"
FIELD_COMMAND_EVALUATION = "c-cVrcHtLQ0x"
FIELD_FLEET_OPERATIONS = "c-X6fhHRb4hE"
FIELD_EVAL_PERIOD = "c-Ja6zxXBPAa"
FIELD_COMPLETED_MISSIONS = "c-Vc3tkEziRV"
FIELD_MISSION_COUNT = "c-X2I9ekFWBS"
FIELD_MISSION_TYPES = "c-YibfzMn78G"
FIELD_PROPOSED_RANK = "c-zGGLyRBbje"
FIELD_RECOMMENDATION_SOURCE = "c-l_5a9naOmn"
FIELD_RECOMMENDATION_REASON = "c-6m2HSlC_fu"
FIELD_STATUSPRO = "c-R5tms-P582"
FIELD_REQUEST_DATE = "c-dgQac9uJ4Q"
FIELD_RANK_DATE = "c-iJIKRoLWd0"

# Status indicators for UI
STATUS_INDICATORS = {
    "Active": "🟢",
    "Inactive": "🔴",
    "On Leave": "🟡", 
    "Training": "🔵",
    "Deployed": "🟣",
    "Unknown": "⚪"
}

# Security level indicators
SECURITY_LEVELS = {
    "TOP_SECRET": "🔴",
    "SECRET": "🟡",
    "CONFIDENTIAL": "🟢",
    "RESTRICTED": "⚪"
}

# Division and Fleet Wing icons
DIVISION_ICONS = {
    "Command Staff": "[HQ]",
    "Tactical": "[TC]",
    "Operations": "[OP]",
    "Support": "[SP]",
    "Non-Division": "[ND]",
    "Ambassador": "[AMB]",
    "Associate": "[AS]"
}

# Updated Fleet Wing icons
FLEET_WING_ICONS = {
    "Navy Fleet": "[NF]",
    "Marine Expeditionary Force": "[MEF]",
    "Industrial & Logistics Wing": "[ILW]",
    "Support & Medical Fleet": "[SMF]",
    "Exploration & Intelligence Wing": "[EIW]",
    "Fleet Command": "[FC]",
    "Command Staff": "[HQ]",
    "Non-Fleet": "[NFL]",
    "Ambassador": "[AMB]",
    "Associate": "[AS]"
}

# Updated mapping from old divisions to new fleet wings
DIVISION_TO_FLEET_WING = {
    "Command Staff": "Command Staff",
    "HQ": "Fleet Command",
    "Tactical": "Navy Fleet",
    "Operations": "Industrial & Logistics Wing",
    "Support": "Support & Medical Fleet",
    "Non-Division": "Non-Fleet",
    "Ambassador": "Ambassador", 
    "Associate": "Associate"
}

# Available awards for autocomplete - synchronized with AAR system medals
AVAILABLE_AWARDS = [
    # Standard medals
    "Fleet Service Medal - For dedicated service to the fleet",
    "Combat Action Ribbon - For participation in combat operations",
    "Medal of Valor - For exceptional courage in the face of danger",
    "Distinguished Service Medal - For distinguished service in key positions",
    "Achievement Medal - For meritorious service in non-combat roles",
    "Commendation Medal - For distinguished service in any capacity",
    "Good Conduct Medal - For exemplary behavior and performance",
    "Expeditionary Medal - For service in expedition operations",
    "Campaign Medal - For service in specific campaigns",
    "Exploration Medal - For contributions to exploration efforts",
    "Scientific Service Medal - For contributions to scientific discovery",
    "Engineering Excellence Medal - For exceptional engineering work",
    "Medical Service Medal - For outstanding medical service",
    "Humanitarian Service Medal - For humanitarian operations",
    "Combat Medic Medal - For medical service in combat conditions",
    "Long Service Medal - For extended time in service",
    "Special Operations Medal - For service in special operations",
    "Intelligence Service Medal - For intelligence gathering operations",
    "Fleet Captain Commendation - Direct recognition from Fleet Captain",
    "Admiral's Distinction - Personal commendation from an Admiral",
    
    # AAR System specific medals (sync with AARMedal enum)
    "Service Medal - For dedicated service in fleet operations",
    "Combat Medal - For excellence in combat operations",
    "Explorer's Medal - For outstanding exploration achievements",
    "Leadership Medal - For exemplary leadership in missions",
    "Training Excellence - For excellence in training operations",
    "Teamwork Medal - For exceptional teamwork during missions",
    "HLN Starward Medal - Highest honor for extraordinary service",
    "Galactic Service Ribbon in Gold - Gold level service recognition",
    "Galactic Service Ribbon in Silver - Silver level service recognition",
    "Galactic Service Ribbon - Recognition of galactic service",
    "Innovator's Crest of Excellence - Excellence in innovation",
    "Innovator's Crest of Distinction - Distinguished innovation",
    "Innovator's Crest - Recognition of innovative solutions",
    "Divisional Excellence Trophy - Excellence within division",
    "Unit Citation Ribbon - Recognition of outstanding unit performance"
]

# Security clearance levels
CLEARANCE_LEVELS = {
    "Admiral": {"level": 5, "code": "ALPHA"},
    "Vice Admiral": {"level": 5, "code": "BRAVO"},
    "Rear Admiral": {"level": 4, "code": "CHARLIE"},
    "Commodore": {"level": 4, "code": "DELTA"},
    "Fleet Captain": {"level": 3, "code": "ECHO"},
    "Captain": {"level": 3, "code": "FOXTROT"},
    "Commander": {"level": 3, "code": "GOLF"},
    "Lieutenant Commander": {"level": 2, "code": "HOTEL"},
    "Lieutenant": {"level": 2, "code": "INDIA"},
    "Lieutenant Junior Grade": {"level": 1, "code": "JULIET"},
    "Ensign": {"level": 1, "code": "KILO"},
    "Chief Petty Officer": {"level": 1, "code": "LIMA"},
    "Petty Officer 1st Class": {"level": 1, "code": "MIKE"},
    "Petty Officer 2nd Class": {"level": 1, "code": "NOVEMBER"},
    "Petty Officer 3rd Class": {"level": 1, "code": "OSCAR"},
    "Master Crewman": {"level": 1, "code": "PAPA"},
    "Senior Crewman": {"level": 1, "code": "QUEBEC"},
    "Crewman": {"level": 1, "code": "ROMEO"},
    "Crewman Apprentice": {"level": 1, "code": "SIERRA"},
    "Crewman Recruit": {"level": 1, "code": "TANGO"},
    "Ambassador": {"level": 3, "code": "UNIFORM"},
    "Associate": {"level": 1, "code": "VICTOR"}
}

# Auth codes for security classifications
AUTH_CODES = {
    "TOP_SECRET": "TS",
    "SECRET": "SC",
    "CONFIDENTIAL": "CO",
    "RESTRICTED": "RE"
}

# Security classification class
class SecurityClassification:
    def __init__(self, classification, auth_code):
        self.classification = classification
        self.auth_code = auth_code