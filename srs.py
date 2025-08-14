import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import aiohttp
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime
from enum import Enum
import pytz
import json
import re

# ----------------------------------------------------------------------------
# Logging setup
# ----------------------------------------------------------------------------
logger = logging.getLogger('srs')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='srs.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# ----------------------------------------------------------------------------
# Environment validation
# ----------------------------------------------------------------------------
def validate_srs_env_vars():
    """Validate required environment variables for SRS functionality."""
    required_vars = {
        'GUILD_ID': os.getenv('GUILD_ID'),
        'CODA_API_TOKEN': os.getenv('CODA_API_TOKEN'),
        'DOC_ID': os.getenv('DOC_ID'),

        # Based on your previous coda references:
        'SHIP_CARD_TABLE_ID': 'grid-MmO5D2OUTr',
        'SRS_FREQ_DESC_TABLE_ID': 'grid-55ggdrA-w2',
        'GENERIC_SRS_TABLE_ID': 'grid-SmgV3peI4L'
    }

    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        global GUILD_ID
        global SHIP_CARD_TABLE_ID
        global SRS_FREQ_DESC_TABLE_ID
        global GENERIC_SRS_TABLE_ID
        global DOC_ID
        global CODA_API_TOKEN

        GUILD_ID = int(required_vars['GUILD_ID'])
        SHIP_CARD_TABLE_ID = required_vars['SHIP_CARD_TABLE_ID']
        SRS_FREQ_DESC_TABLE_ID = required_vars['SRS_FREQ_DESC_TABLE_ID']
        GENERIC_SRS_TABLE_ID = required_vars['GENERIC_SRS_TABLE_ID']
        DOC_ID = required_vars['DOC_ID']
        CODA_API_TOKEN = required_vars['CODA_API_TOKEN']

    except ValueError as e:
        error_msg = f"Invalid environment variable format: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg)

# Validate on import
validate_srs_env_vars()

# ----------------------------------------------------------------------------
# StationType / FrequencyType enums
# ----------------------------------------------------------------------------
class StationType(Enum):
    """Ship station types for Star Citizen usage."""
    CAPTAIN = "Captain"
    EXECUTIVE_OFFICER = "Executive Officer"
    HELMSMAN = "Helmsman"
    LEAD_GUNNERY = "Lead Gunnery Officer"
    CHIEF_ENGINEER = "Chief Engineer"
    SECURITY_CHIEF = "Security Chief"
    LOGISTICS = "Logistics Officer"
    MEDICAL = "Chief Medical Officer"
    PORT_GUN = "Port Gun Lead"
    PORT_SECONDARY = "Port Secondary Gun"
    STARBOARD_GUN = "Starboard Gun Lead"
    STARBOARD_SECONDARY = "Starboard Secondary Gun"
    PORT_GUN_LEAD = "Port Gun Lead"
    STARBOARD_GUN_LEAD = "Starboard Gun Lead"
    MARINE_FLEX = "Marine Flex"
    MISC_OPERATIONAL_ASSET = "Misc Operational Asset"

class FrequencyType(Enum):
    """Types of communication frequencies (DCS + Star Citizen)."""
    SATCOM = "SATCOM"
    SUB_COMMAND = "Sub Command"
    FLEET_COORDINATION = "FleetCoordination"
    COMMON_OPS = "Common Ops"
    SPC = "SPC"  # Ship Primary Comms
    SSC = "SSC"  # Ship Secondary Comms
    MARINE_OPS = "Marine Ops"
    DIV_COMMS = "Div Comms"
    EMERGENCY = "Emergency"
    GENERAL_AM = "General AM"
    
    @classmethod
    def from_name(cls, name: str) -> Optional['FrequencyType']:
        """Get FrequencyType from radio name."""
        name = name.strip().upper().replace(' ', '_')
        for freq_type in cls:
            if freq_type.name == name:
                return freq_type
        return None

class RadioChannel:
    """Represents a radio communication channel with frequency details."""
    def __init__(self, name: str, freq: float, description: str = "", encrypted: bool = False, key: int = 0):
        self.name = name
        self.freq = freq
        self.description = description
        self.encrypted = encrypted
        self.key = key
        self.type = self._determine_type()
        
    def _determine_type(self) -> FrequencyType:
        """Determine the type of frequency based on name."""
        if "SATCOM" in self.name:
            return FrequencyType.SATCOM
        elif "C&C" in self.name:
            return FrequencyType.COMMON_OPS
        elif "Marine" in self.name:
            return FrequencyType.MARINE_OPS
        elif "Primary Comms" in self.name or "FG Comms" in self.name:
            return FrequencyType.SPC
        elif "Turret" in self.name or "Engineering" in self.name:
            return FrequencyType.SSC
        elif "Support" in self.name or "Operations" in self.name or "Tactical" in self.name:
            return FrequencyType.DIV_COMMS
        elif "Emergency" in self.name:
            return FrequencyType.EMERGENCY
        else:
            return FrequencyType.GENERAL_AM
    
    def get_formatted_name(self) -> str:
        """Get formatted channel name with frequency."""
        if self.encrypted:
            return f"{self.name} ({self.freq:.3f} 🔒)"
        else:
            return f"{self.name} ({self.freq:.3f})"

# ----------------------------------------------------------------------------
# Main SRS Cog
# ----------------------------------------------------------------------------
class SRSCog(commands.Cog):
    """Cog for Ship Registration System (SRS) + advanced station-based logic and mission comms setup."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

        # Data structures for frequency info
        # e.g., ship_frequencies["ShipDesignation"]["StationName"] = {...station data...}
        self.ship_frequencies: Dict[str, Dict[str, Dict]] = {}
        self.generic_frequencies: Dict[str, Dict] = {}
        self.frequency_descriptors: Dict[str, str] = {}
        
        # Radio system configuration
        self.dcs_radio_config: Dict = {}
        self.radio_channels: Dict[FrequencyType, List[RadioChannel]] = {freq_type: [] for freq_type in FrequencyType}
        
        # Ship database - maps ship names to prefixes used in radio channels
        self.ship_prefixes: Dict[str, str] = {
            "Providence": "Providence",
            "Kestrel": "Kestrel",
            "Pella": "Pella",
            "BirdDog": "BirdDog",
            "Venture": "Venture"
        }

        # Store user-friendly mission-level comms data for /setup_mission_comms
        # Key = mission.mission_id, Value = dict with readiness/freq/notes
        self.mission_comms_data: Dict[str, Dict[str, Any]] = {}

        logger.info("Initializing SRS Cog...")
        
    async def cog_load(self):
        """Called when the cog is loaded."""
        await self.load_frequency_tables()
        await self.load_radio_config()
        logger.info("SRS Cog loaded successfully")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        await self.session.close()
        logger.info("SRS Cog unloaded")
        
    # ------------------------------------------------------------------------
    # Radio configuration loading
    # ------------------------------------------------------------------------
    async def load_radio_config(self):
        """Load DCS radio configurations and frequencies from files."""
        try:
            # Load main radio configuration
            radio_config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'awacs-radios-custom.json')
            if os.path.exists(radio_config_path):
                with open(radio_config_path, 'r') as f:
                    self.dcs_radio_config = json.load(f)
                logger.info(f"Loaded DCS radio configuration from {radio_config_path}")
            else:
                logger.warning(f"DCS radio configuration file not found at {radio_config_path}")
            
            # Load frequency files
            await self.load_frequency_file('commonops.txt', FrequencyType.COMMON_OPS)
            await self.load_frequency_file('divcomms.txt', FrequencyType.DIV_COMMS)
            await self.load_frequency_file('fleetcoordination.txt', FrequencyType.FLEET_COORDINATION)
            await self.load_frequency_file('marineops.txt', FrequencyType.MARINE_OPS)
            await self.load_frequency_file('spc.txt', FrequencyType.SPC)
            await self.load_frequency_file('ssc.txt', FrequencyType.SSC)
            
            # Process radio config to create channels
            for radio in self.dcs_radio_config:
                freq_type = FrequencyType.from_name(radio.get('name', ''))
                if freq_type and radio.get('freq'):
                    channel = RadioChannel(
                        name=radio.get('name', 'Unknown'),
                        freq=radio.get('freq', 0) / 1000000.0,  # Convert to MHz
                        encrypted=radio.get('enc', False),
                        key=radio.get('encKey', 0)
                    )
                    if freq_type not in self.radio_channels:
                        self.radio_channels[freq_type] = []
                    self.radio_channels[freq_type].append(channel)
            
            # Log the loaded frequencies
            total_channels = sum(len(channels) for channels in self.radio_channels.values())
            logger.info(f"Loaded {total_channels} radio channels across {len(self.radio_channels)} frequency types")
            
        except Exception as e:
            logger.error(f"Error loading radio configuration: {e}", exc_info=True)
    
    async def load_frequency_file(self, filename: str, freq_type: FrequencyType):
        """Load frequency definitions from a text file."""
        try:
            file_path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
            if not os.path.exists(file_path):
                logger.warning(f"Frequency file not found: {file_path}")
                return
                
            with open(file_path, 'r') as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if line and '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        try:
                            freq = float(parts[1].strip())
                            channel = RadioChannel(
                                name=name,
                                freq=freq,
                                encrypted=self._should_encrypt_channel(freq_type),
                                key=self._get_encryption_key(freq_type)
                            )
                            if freq_type not in self.radio_channels:
                                self.radio_channels[freq_type] = []
                            self.radio_channels[freq_type].append(channel)
                        except ValueError:
                            logger.warning(f"Invalid frequency in line: {line}")
            
            logger.info(f"Loaded {len(self.radio_channels.get(freq_type, []))} frequencies from {filename}")
        except Exception as e:
            logger.error(f"Error loading frequency file {filename}: {e}")
    
    def _should_encrypt_channel(self, freq_type: FrequencyType) -> bool:
        """Determine if a channel type should be encrypted based on DCS config."""
        for radio in self.dcs_radio_config:
            if radio.get('name', '') == freq_type.value:
                return radio.get('enc', False)
        # Default encryption settings
        return freq_type in (
            FrequencyType.SPC, 
            FrequencyType.FLEET_COORDINATION, 
            FrequencyType.SUB_COMMAND,
            FrequencyType.DIV_COMMS,
            FrequencyType.MARINE_OPS
        )
    
    def _get_encryption_key(self, freq_type: FrequencyType) -> int:
        """Get encryption key for a frequency type based on DCS config."""
        for radio in self.dcs_radio_config:
            if radio.get('name', '') == freq_type.value:
                return radio.get('encKey', 1)
        return 1  # Default key

    # ------------------------------------------------------------------------
    # Load data from Coda
    # ------------------------------------------------------------------------
    async def load_frequency_tables(self):
        """
        Load frequency-related data from your Coda doc/tables.
        This fully implements logic from your earlier code.
        """
        try:
            logger.info("Loading frequency tables from Coda...")

            # 1) Load ship card table
            ship_data = await self.fetch_coda_table(SHIP_CARD_TABLE_ID)
            if not ship_data:
                logger.error(f"Failed to load ship card table: {SHIP_CARD_TABLE_ID}")
                return
                
            for row in ship_data:
                values = row['values']
                vessel_info_str = values.get('Vessel Information', '')
                station_name = values.get('Ship Station', '')

                designation = None
                sn = None
                ship_class = None

                # Parse lines from 'Vessel Information'
                for line in vessel_info_str.split('\n'):
                    line = line.strip()
                    if line.startswith("Designation:"):
                        designation = line.replace("Designation:", "").strip()
                    elif line.startswith("S/N:"):
                        sn = line.replace("S/N:", "").strip()
                    elif line.startswith("Class:"):
                        ship_class = line.replace("Class:", "").strip()

                if not designation:
                    designation = values.get('Designation')
                if not designation:
                    # If we still don't have a designation, skip
                    continue

                if designation not in self.ship_frequencies:
                    self.ship_frequencies[designation] = {}

                # Store or update class/SN
                if ship_class and "_ship_class" not in self.ship_frequencies[designation]:
                    self.ship_frequencies[designation]["_ship_class"] = ship_class
                if sn and "_ship_sn" not in self.ship_frequencies[designation]:
                    self.ship_frequencies[designation]["_ship_sn"] = sn

                # Station data
                station_data = {
                    'Vessel Information': vessel_info_str,
                    'Ship Station': station_name,
                    'Station Role': values.get('Station Role', ''),
                    'Station Controlled By Channels': self.parse_frequency_list(values.get('Station Controlled By Channels', [])),
                    'Station Controlled Channels': self.parse_frequency_list(values.get('Station Controlled Channels', [])),
                    'Monitored Only Channels': self.parse_frequency_list(values.get('Monitored Only Channels', [])),
                    'SRS Freq Table': self.parse_frequency_list(values.get('SRS Freq Table', [])),
                    'Class': ship_class or "Unknown",
                    'S/N': sn or "Unknown",
                    'Designation': designation
                }

                # Insert into structure
                self.ship_frequencies[designation][station_name] = station_data

            # 2) Load generic frequencies
            generic_data = await self.fetch_coda_table(GENERIC_SRS_TABLE_ID)
            if not generic_data:
                logger.error(f"Failed to load generic SRS table: {GENERIC_SRS_TABLE_ID}")
                return
                
            self.generic_frequencies = {
                row['values'].get('Channel Type'): row
                for row in generic_data
                if row['values'].get('Channel Type')
            }

            # 3) Load frequency descriptors
            freq_desc_data = await self.fetch_coda_table(SRS_FREQ_DESC_TABLE_ID)
            if not freq_desc_data:
                logger.error(f"Failed to load frequency descriptors table: {SRS_FREQ_DESC_TABLE_ID}")
                return
                
            self.frequency_descriptors = {
                row['values'].get('Channel Name / Freq'): row['values'].get('Usage Description')
                for row in freq_desc_data
                if row['values'].get('Channel Name / Freq')
            }

            # 4) Update each station's data with the discovered class/SN
            for ship_name, ship_data in self.ship_frequencies.items():
                ship_class = ship_data.get("_ship_class", "Unknown")
                ship_sn = ship_data.get("_ship_sn", "Unknown")
                for st_name, st_data in ship_data.items():
                    if st_name.startswith('_'):
                        continue
                    st_data["Class"] = ship_class
                    st_data["S/N"] = ship_sn
                
                # 5) Augment with DCS frequency data
                self.augment_ship_with_frequencies(ship_name)

            logger.info(
                f"Loaded {len(self.ship_frequencies)} ships, "
                f"{len(self.generic_frequencies)} generic freq definitions, "
                f"and {len(self.frequency_descriptors)} freq descriptors."
            )

        except Exception as e:
            logger.error(f"Error loading frequency tables: {e}", exc_info=True)
            
    def augment_ship_with_frequencies(self, ship_name: str):
        """Add DCS frequencies to a ship based on its name or designation."""
        if ship_name not in self.ship_frequencies:
            return
            
        # Find matching ship prefix
        matching_prefix = None
        for prefix in self.ship_prefixes:
            if prefix in ship_name:
                matching_prefix = prefix
                break
                
        if not matching_prefix:
            return
            
        # Find relevant frequencies for this ship
        ship_freqs = []
        
        # Add C&C frequency
        for channel in self.radio_channels.get(FrequencyType.COMMON_OPS, []):
            if matching_prefix in channel.name:
                ship_freqs.append(f"C&C: {channel.get_formatted_name()}")
                
        # Add SPC frequencies
        for channel in self.radio_channels.get(FrequencyType.SPC, []):
            if matching_prefix in channel.name:
                ship_freqs.append(f"Primary: {channel.get_formatted_name()}")
                
        # Add SSC frequencies
        for channel in self.radio_channels.get(FrequencyType.SSC, []):
            if matching_prefix in channel.name:
                ship_freqs.append(f"Secondary: {channel.get_formatted_name()}")
                
        # Add Marine frequencies
        for channel in self.radio_channels.get(FrequencyType.MARINE_OPS, []):
            if matching_prefix in channel.name:
                ship_freqs.append(f"Marine: {channel.get_formatted_name()}")
        
        # Store in ship data
        if ship_freqs:
            self.ship_frequencies[ship_name]["_dcs_frequencies"] = ship_freqs

    async def fetch_coda_table(self, table_id: str) -> List[Dict]:
        """Fetch all rows from a Coda table, returning a list of row data."""
        try:
            endpoint = f'docs/{DOC_ID}/tables/{table_id}/rows'
            headers = {
                'Authorization': f'Bearer {CODA_API_TOKEN}',
                'Content-Type': 'application/json'
            }
            params = {'useColumnNames': 'true', 'limit': 100}

            async with self.session.get(
                f'https://coda.io/apis/v1/{endpoint}',
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('items', [])
                else:
                    logger.error(f"Failed to fetch table {table_id}: status={response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error fetching table {table_id}: {e}")
            return []

    def parse_frequency_list(self, frequencies: Any) -> List[str]:
        """Convert frequency data to a list format (handles str or list)."""
        if isinstance(frequencies, str):
            return [freq.strip() for freq in frequencies.split(',') if freq.strip()]
        elif isinstance(frequencies, list):
            return frequencies
        return []
        
    def get_all_ship_frequencies(self) -> Dict[str, List[str]]:
        """Get comprehensive list of frequencies for all ships."""
        all_freqs = {}
        for ship_name, ship_data in self.ship_frequencies.items():
            ship_freqs = ship_data.get("_dcs_frequencies", [])
            if ship_freqs:
                all_freqs[ship_name] = ship_freqs
        return all_freqs
        
    def get_channels_for_station(self, ship_name: str, station_type: StationType) -> Dict[str, List[str]]:
        """Get all relevant DCS channels for a specific station."""
        result = {
            "controlled_by": [],
            "controls": [],
            "monitors": []
        }
        
        # Find the matching prefix for this ship
        matching_prefix = None
        for prefix in self.ship_prefixes:
            if prefix in ship_name:
                matching_prefix = prefix
                break
                
        if not matching_prefix:
            return result
            
        # Based on station type, assign channels
        # For Captain
        if station_type == StationType.CAPTAIN:
            # Controls C&C and Primary Comms
            for channel in self.radio_channels.get(FrequencyType.COMMON_OPS, []):
                if matching_prefix in channel.name:
                    result["controls"].append(channel.get_formatted_name())
                    
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "Primary" in channel.name:
                    result["controls"].append(channel.get_formatted_name())
                    
            # Monitors Fleet and Division comms
            for channel in self.radio_channels.get(FrequencyType.FLEET_COORDINATION, []):
                result["monitors"].append(channel.get_formatted_name())
                
            for channel in self.radio_channels.get(FrequencyType.DIV_COMMS, []):
                result["monitors"].append(channel.get_formatted_name())
                
        # For Executive Officer
        elif station_type == StationType.EXECUTIVE_OFFICER:
            # Controls FG Comms
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "FG" in channel.name:
                    result["controls"].append(channel.get_formatted_name())
                    
            # Controlled by Captain
            for channel in self.radio_channels.get(FrequencyType.COMMON_OPS, []):
                if matching_prefix in channel.name:
                    result["controlled_by"].append(channel.get_formatted_name())
                    
            # Monitors Division and Emergency
            for channel in self.radio_channels.get(FrequencyType.DIV_COMMS, []):
                result["monitors"].append(channel.get_formatted_name())
                
            for channel in self.radio_channels.get(FrequencyType.EMERGENCY, []):
                result["monitors"].append(channel.get_formatted_name())
                
        # For Helmsman
        elif station_type == StationType.HELMSMAN:
            # Controlled by Captain
            for channel in self.radio_channels.get(FrequencyType.COMMON_OPS, []):
                if matching_prefix in channel.name:
                    result["controlled_by"].append(channel.get_formatted_name())
                    
            # Monitors Primary and Emergency
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "Primary" in channel.name:
                    result["monitors"].append(channel.get_formatted_name())
                    
            for channel in self.radio_channels.get(FrequencyType.EMERGENCY, []):
                result["monitors"].append(channel.get_formatted_name())
                
        # For Lead Gunnery
        elif station_type in (StationType.LEAD_GUNNERY, StationType.PORT_GUN_LEAD, StationType.STARBOARD_GUN_LEAD):
            # Controls Turret channels
            for channel in self.radio_channels.get(FrequencyType.SSC, []):
                if matching_prefix in channel.name and "Turret" in channel.name:
                    result["controls"].append(channel.get_formatted_name())
                    
            # Controlled by Captain
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "Primary" in channel.name:
                    result["controlled_by"].append(channel.get_formatted_name())
                    
            # Monitors Combat
            for channel in self.radio_channels.get(FrequencyType.MARINE_OPS, []):
                if "Air Support" in channel.name:
                    result["monitors"].append(channel.get_formatted_name())
                    
        # For Chief Engineer
        elif station_type == StationType.CHIEF_ENGINEER:
            # Controls Engineering channel
            for channel in self.radio_channels.get(FrequencyType.SSC, []):
                if matching_prefix in channel.name and "Engineering" in channel.name:
                    result["controls"].append(channel.get_formatted_name())
                    
            # Controlled by Captain
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "Primary" in channel.name:
                    result["controlled_by"].append(channel.get_formatted_name())
                    
            # Monitors Support
            for channel in self.radio_channels.get(FrequencyType.DIV_COMMS, []):
                if "Support" in channel.name:
                    result["monitors"].append(channel.get_formatted_name())
                    
        # For Marine roles
        elif station_type in (StationType.SECURITY_CHIEF, StationType.MARINE_FLEX):
            # Controls Marine channel
            for channel in self.radio_channels.get(FrequencyType.MARINE_OPS, []):
                if matching_prefix in channel.name:
                    result["controls"].append(channel.get_formatted_name())
                    
            # Controlled by Captain
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "Primary" in channel.name:
                    result["controlled_by"].append(channel.get_formatted_name())
                    
        # For Medical
        elif station_type == StationType.MEDICAL:
            # Monitors Support and Emergency
            for channel in self.radio_channels.get(FrequencyType.DIV_COMMS, []):
                if "Support" in channel.name:
                    result["monitors"].append(channel.get_formatted_name())
                    
            for channel in self.radio_channels.get(FrequencyType.EMERGENCY, []):
                result["monitors"].append(channel.get_formatted_name())
                
            # Controlled by Captain
            for channel in self.radio_channels.get(FrequencyType.SPC, []):
                if matching_prefix in channel.name and "Primary" in channel.name:
                    result["controlled_by"].append(channel.get_formatted_name())
            
        # Add common emergency channel to all stations
        for channel in self.radio_channels.get(FrequencyType.EMERGENCY, []):
            if channel.get_formatted_name() not in result["monitors"]:
                result["monitors"].append(channel.get_formatted_name())
                
        return result

    # ------------------------------------------------------------------------
    # Advanced station-based methods for Star Citizen + Star Trek readiness
    # ------------------------------------------------------------------------
    async def get_ship_frequencies(self, ship_name: str, station_type: StationType) -> Dict:
        """Get frequencies for a specific ship station, or fallback to generic freq for that station."""
        try:
            station_data = self.get_station_data(ship_name, station_type)
            if station_data:
                # Augment with DCS radio data
                station_channels = self.get_channels_for_station(ship_name, station_type)
                if station_channels["controlled_by"]:
                    station_data["Station Controlled By Channels"] = station_channels["controlled_by"]
                if station_channels["controls"]:
                    station_data["Station Controlled Channels"] = station_channels["controls"]
                if station_channels["monitors"]:
                    station_data["Monitored Only Channels"] = station_channels["monitors"]
                
                return station_data
                
            # fallback
            logger.info(f"No specific station data found for {ship_name} - {station_type.value}, using generic fallback")
            generic_data = self.get_generic_frequencies(station_type)
            
            # Augment generic data with DCS radio data
            station_channels = self.get_channels_for_station(ship_name, station_type)
            if station_channels["controlled_by"]:
                generic_data["Station Controlled By Channels"] = station_channels["controlled_by"]
            if station_channels["controls"]:
                generic_data["Station Controlled Channels"] = station_channels["controls"]
            if station_channels["monitors"]:
                generic_data["Monitored Only Channels"] = station_channels["monitors"]
                
            return generic_data
        except Exception as e:
            logger.error(f"Error getting ship frequencies for {ship_name} - {station_type.value}: {e}", exc_info=True)
            return {}  # Return empty dict as fallback

    def get_station_data(self, ship_name: str, station_type: StationType) -> Optional[Dict]:
        """Get station data for a specific station on a named ship."""
        if ship_name not in self.ship_frequencies:
            return None
        return self.ship_frequencies[ship_name].get(station_type.value)

    def get_generic_frequencies(self, station_type: StationType) -> Dict:
        """Get generic fallback frequencies for a station type."""
        generic_data = self.generic_frequencies.get(station_type.value, {})
        values = generic_data.get('values', {})

        return {
            'Station Role': self.get_default_station_role(station_type),
            'Station Controlled By Channels': self.parse_frequency_list(values.get('Station Controlled By Channels', [])),
            'Station Controlled Channels': self.parse_frequency_list(values.get('Station Controlled Channels', [])),
            'Monitored Only Channels': self.parse_frequency_list(values.get('Monitored Only Channels', [])),
            'SRS Freq Table': self.parse_frequency_list(values.get('SRS Freq Table', [])),
            'Designation': "Unknown",
            'Class': "Unknown",
            'S/N': "Unknown"
        }

    def get_default_station_role(self, station_type: StationType) -> str:
        """Default role if station data not in coda."""
        roles = {
            StationType.CAPTAIN: "Ship / Fleet C&C",
            StationType.EXECUTIVE_OFFICER: "Task force / second-in-command",
            StationType.HELMSMAN: "Navigation / primary pilot",
            StationType.LEAD_GUNNERY: "Operates main guns, coordinates turret arcs",
            StationType.CHIEF_ENGINEER: "Ship systems maintenance and power management",
            StationType.SECURITY_CHIEF: "Internal security and boarding defense",
            StationType.LOGISTICS: "Resource management and resupply coordination",
            StationType.MEDICAL: "Medical emergencies and crew health",
            StationType.PORT_GUN_LEAD: "Primary port side weapon systems",
            StationType.STARBOARD_GUN_LEAD: "Primary starboard side weapon systems",
            StationType.MARINE_FLEX: "Boarding operations and ship defense",
        }
        return roles.get(station_type, "No description available")

    async def create_mission_station_embed(
        self,
        mission: Any,
        ship_name: str,
        station: StationType
    ) -> discord.Embed:
        """
        Show station frequencies for a given ship + station, referencing the 
        mission object. Includes Star Citizen references & Condition states.
        """
        station_data = await self.get_ship_frequencies(ship_name, station)
        if not station_data:
            return discord.Embed(
                title="Error",
                description=f"No station data found for {ship_name} - {station.value}.",
                color=discord.Color.red()
            )

        embed = discord.Embed(
            title=f"Mission Station: {mission.name}",
            description=(
                f"**Ship:** {ship_name}\n"
                f"**Station:** {station.value}\n"
                f"**Condition:** Green (Default)\n"  # can be changed dynamically if desired
                f"**Mission Status:** {mission.status.value}\n"
                f"**Mission Start:** <t:{int(mission.start_time.timestamp())}:f>"
            ),
            color=discord.Color.dark_blue()
        )

        # Example: station duties in Star Citizen
        embed.add_field(
            name="📋 Station Duties",
            value=(
                "• Manage turret arcs & ballistic ammo.\n"
                "• Monitor for quantum interdiction attempts.\n"
                "• Oversee power distribution for pilot/gunners.\n"
                f"• {station_data.get('Station Role', 'No specific role defined.')}\n"
            ),
            inline=False
        )

        # Controlled By
        controlled_by = station_data.get("Station Controlled By Channels", [])
        embed.add_field(
            name="📡 Receives Orders From",
            value="\n".join([f"• {channel}" for channel in controlled_by]) or "None",
            inline=False
        )
        
        # Controlled Channels
        controlled = station_data.get("Station Controlled Channels", [])
        embed.add_field(
            name="🎮 Controls Channels",
            value="\n".join([f"• {channel}" for channel in controlled]) or "None",
            inline=False
        )
        
        # Monitored Channels
        monitored = station_data.get("Monitored Only Channels", [])
        embed.add_field(
            name="👂 Monitors Channels",
            value="\n".join([f"• {channel}" for channel in monitored]) or "None",
            inline=False
        )

        # Frequency table with descriptions if available
        freq_table = station_data.get("SRS Freq Table", [])
        if freq_table:
            freq_display = []
            for freq in freq_table:
                description = self.frequency_descriptors.get(freq, "")
                if description:
                    freq_display.append(f"• **{freq}**: {description}")
                else:
                    freq_display.append(f"• **{freq}**")
                    
            embed.add_field(
                name="📻 SRS Frequency Table",
                value="\n".join(freq_display),
                inline=False
            )

        # Condition clarifications with emojis
        embed.add_field(
            name="⚠️ Condition Readiness States",
            value=(
                "🟢 **Green:** Normal operations\n"
                "🟡 **Yellow:** Elevated alert, prepare for action\n"
                "🔴 **Red:** Combat alert, weapons free\n"
            ),
            inline=False
        )

        # Add footer with ship info
        embed.set_footer(text=f"{ship_name} • {station_data.get('Class', 'Unknown Class')} • S/N: {station_data.get('S/N', 'Unknown')}")

        return embed

    async def create_mission_ship_embed(
        self,
        mission: Any,
        ship_name: str
    ) -> discord.Embed:
        """
        Show relevant frequencies/comm info for an entire ship, referencing
        the mission object. Star Citizen + Star Trek readiness usage.
        """
        ship_stations = self.ship_frequencies.get(ship_name, {})
        if not ship_stations:
            return discord.Embed(
                title="Error",
                description=f"No stations found for this ship: {ship_name}",
                color=discord.Color.red()
            )

        # Grab first station for basic info
        first_station_data = next(
            (st_data for key, st_data in ship_stations.items() if not key.startswith('_')),
            None
        )
        if not first_station_data:
            return discord.Embed(
                title="Error",
                description="No station data found for this ship.",
                color=discord.Color.red()
            )

        embed = discord.Embed(
            title=f"Ship Communications: {ship_name}",
            description=(
                f"**Mission:** {mission.name}\n"
                f"**Current Status:** {mission.status.value}\n"
                f"**Start Time:** <t:{int(mission.start_time.timestamp())}:f>\n"
                f"**Difficulty:** {mission.difficulty}\n\n"
                "**Current Readiness:** 🟢 **Condition Green** (Default)\n"
            ),
            color=discord.Color.dark_blue()
        )

        # Get DCS frequencies for this ship
        dcs_frequencies = ship_stations.get("_dcs_frequencies", [])

        # Ship overview with more formatting
        embed.add_field(
            name="🚀 Ship Overview",
            value=(
                f"**Class:** {first_station_data.get('Class', 'Unknown')}\n"
                f"**S/N:** {first_station_data.get('S/N', 'Unknown')}\n"
                "**Commanding Officer:** [TBD]\n"
                "**Home Port:** ARC-L1, Stanton\n"
                "---------------------------------------"
            ),
            inline=False
        )
        
        # DCS Ship Frequencies
        if dcs_frequencies:
            embed.add_field(
                name="📻 Ship Frequencies",
                value="\n".join([f"• {freq}" for freq in dcs_frequencies]),
                inline=False
            )

        # For each station - more compact formatting for better readability
        for station_name, st_data in ship_stations.items():
            if station_name.startswith("_"):
                continue

            # Format channels more cleanly
            channels_text = []
            
            cb_channels = st_data.get("Station Controlled By Channels", [])
            if cb_channels:
                channels_text.append(f"**Reports to:** {', '.join(cb_channels)}")
                
            c_channels = st_data.get("Station Controlled Channels", [])
            if c_channels:
                channels_text.append(f"**Controls:** {', '.join(c_channels)}")
                
            m_channels = st_data.get("Monitored Only Channels", [])
            if m_channels:
                channels_text.append(f"**Monitors:** {', '.join(m_channels)}")
                
            freq_table = st_data.get("SRS Freq Table", [])
            if freq_table:
                channels_text.append(f"**Frequencies:** {', '.join(freq_table)}")

            station_text = (
                f"**Role:** {st_data.get('Station Role', 'No description')}\n"
                f"{chr(10).join(channels_text)}"
            )

            embed.add_field(
                name=f"👩‍🚀 Station: {station_name}",
                value=station_text.strip(),
                inline=False
            )

        # Standing orders with emojis for better readability
        embed.add_field(
            name="📋 Standing Orders",
            value=(
                "• 🔍 Maintain quantum interdiction watch.\n"
                "• ⚔️ Engage hostiles if Condition Red is declared.\n"
                "• 📡 Communicate critical intel if Condition Yellow.\n"
                "• 🛑 No weapons discharge unless Condition Red or authorized.\n"
            ),
            inline=False
        )
        
        # Add communication protocols
        embed.add_field(
            name="📱 Comm Protocols",
            value=(
                "• Use callsigns on all channels.\n"
                "• Maintain communication discipline.\n"
                "• Monitor your assigned frequencies at all times.\n"
                "• Report any unusual contacts immediately.\n"
            ),
            inline=False
        )

        return embed

    async def create_mission_comms_embed(self, mission: Any) -> discord.Embed:
        """
        A general embed showing mission-wide communications info
        (Star Citizen + Star Trek–style readiness states).
        """
        embed = discord.Embed(
            title=f"📡 Mission Comms Overview: {mission.name}",
            description=(
                f"**Start Time:** <t:{int(mission.start_time.timestamp())}:f>\n"
                f"**Mission Type:** {mission.mission_type.value}\n"
                f"**Status:** {mission.status.value}\n"
                f"**Difficulty:** {mission.difficulty}"
            ),
            color=discord.Color.dark_blue()
        )

        # Chain of command with improved formatting
        embed.add_field(
            name="👑 Chain of Command",
            value=(
                f"**Mission Commander:** <@{mission.leader_id}>\n"
                "**XO:** [TBD]\n"
                "**Flight Lead:** [TBD]"
            ),
            inline=False
        )

        # Format primary frequencies from DCS data
        common_freqs = []
        fleet_freqs = []
        
        # Common operation frequencies
        for channel in self.radio_channels.get(FrequencyType.COMMON_OPS, []):
            common_freqs.append(f"• **{channel.name}** - {channel.freq:.3f}" + (" 🔒" if channel.encrypted else ""))
            
        # Fleet coordination frequencies
        for channel in self.radio_channels.get(FrequencyType.FLEET_COORDINATION, []):
            fleet_freqs.append(f"• **{channel.name}** - {channel.freq:.3f}" + (" 🔒" if channel.encrypted else ""))
            
        # Display primary frequencies
        embed.add_field(
            name="🔊 Primary Frequencies",
            value=(
                (f"**Fleet Coordination**\n" + "\n".join(fleet_freqs) + "\n\n" if fleet_freqs else "") +
                (f"**Common Operations**\n" + "\n".join(common_freqs) if common_freqs else "None configured")
            ) or "No primary frequencies configured.",
            inline=True
        )
        
        # Format support frequencies
        support_freqs = []
        marine_freqs = []
        emergency_freqs = []
        
        # Support division frequencies
        for channel in self.radio_channels.get(FrequencyType.DIV_COMMS, []):
            support_freqs.append(f"• **{channel.name}** - {channel.freq:.3f}" + (" 🔒" if channel.encrypted else ""))
            
        # Marine frequencies
        for channel in self.radio_channels.get(FrequencyType.MARINE_OPS, []):
            if "Air Support" in channel.name:
                marine_freqs.append(f"• **{channel.name}** - {channel.freq:.3f}" + (" 🔒" if channel.encrypted else ""))
                
        # Emergency frequency
        for channel in self.radio_channels.get(FrequencyType.EMERGENCY, []):
            emergency_freqs.append(f"• **{channel.name}** - {channel.freq:.3f}" + (" 🔒" if channel.encrypted else ""))
        
        # Display support frequencies
        embed.add_field(
            name="📻 Support Frequencies",
            value=(
                (f"**Division Support**\n" + "\n".join(support_freqs) + "\n\n" if support_freqs else "") +
                (f"**Marine Operations**\n" + "\n".join(marine_freqs) + "\n\n" if marine_freqs else "") +
                (f"**Emergency**\n" + "\n".join(emergency_freqs) if emergency_freqs else "")
            ) or "No support frequencies configured.",
            inline=True
        )

        # Condition states with emoji
        embed.add_field(
            name="⚠️ Alert Conditions",
            value=(
                "🟢 **Condition Green:** Normal operations\n"
                "🟡 **Condition Yellow:** Elevated alert, tactical readiness\n"
                "🔴 **Condition Red:** Combat alert, weapons free\n"
            ),
            inline=False
        )

        # Add a field for special instructions
        embed.add_field(
            name="📋 Comm Protocols",
            value=(
                "• Use callsigns on all channels\n"
                "• Maintain communication discipline\n"
                "• Report all unusual contacts immediately\n"
                "• Emergency channel is for true emergencies only\n"
                "• Maintain comms silence when directed\n"
            ),
            inline=False
        )

        # Add a footer with the mission ID
        embed.set_footer(text=f"Mission ID: {mission.mission_id[:8]} • Comms Plan")
        
        return embed

    # ------------------------------------------------------------------------
    # /setup_mission_comms with a user-friendly modal (limited to 5 inputs)
    # ------------------------------------------------------------------------
    @app_commands.command(
        name="setup_mission_comms",
        description="Set or update communications for a mission (user-friendly modal)."
    )
    @app_commands.describe(mission_name="Name of the mission to set up comms for")
    async def setup_mission_comms(self, interaction: discord.Interaction, mission_name: str):
        """
        Interactive approach to gather frequencies, readiness, etc. for a mission
        via a modal. Saves the data so that /mission_comms can display it.
        """
        missions_cog = self.bot.get_cog("MissionCog")
        if not missions_cog:
            await interaction.response.send_message("MissionCog not found. Make sure it's loaded properly.", ephemeral=True)
            return

        # Find mission by name
        mission_obj = None
        for mid, m in missions_cog.missions.items():
            if m.name.lower() == mission_name.lower():
                mission_obj = m
                break

        if not mission_obj:
            await interaction.response.send_message("Mission not found. Check the mission name or create one using `/create_mission`.", ephemeral=True)
            return

        # Launch the modal, limited to 5 inputs total
        modal = MissionCommsSetupModal(self, mission_obj)
        await interaction.response.send_modal(modal)

    @setup_mission_comms.autocomplete("mission_name")
    async def setup_mission_comms_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete mission names by mission.name (from MissionCog)."""
        missions_cog = self.bot.get_cog("MissionCog")
        if not missions_cog:
            return []
        result = []
        for mid, mission in missions_cog.missions.items():
            if current.lower() in mission.name.lower():
                result.append(app_commands.Choice(name=mission.name, value=mission.name))
        return result[:25]

    # ------------------------------------------------------------------------
    # /mission_comms - show the user-friendly data, and optionally advanced data
    # ------------------------------------------------------------------------
    @app_commands.command(
        name="mission_comms",
        description="View mission communications info for a given mission."
    )
    @app_commands.describe(
        mission_name="Name of the mission to view comms for",
        ship_name="Name of your ship (optional)",
        station="Station name/type (optional, e.g. CAPTAIN, HELMSMAN, etc.)",
        advanced="If True, display advanced station/ship info."
    )
    async def mission_comms(self, interaction: discord.Interaction, mission_name: str, ship_name: Optional[str] = None, station: Optional[str] = None, advanced: bool = False):
        """
        Displays the mission-level comms info set by /setup_mission_comms.
        If 'advanced' is True, can also display station-based or entire-ship-based 
        logic (depending on user input).
        """
        await interaction.response.defer()

        missions_cog = self.bot.get_cog("MissionCog")
        if not missions_cog:
            await interaction.followup.send("MissionCog not found. Make sure it's loaded properly.", ephemeral=True)
            return

        # Find the mission by name
        mission_obj = None
        for mid, m in missions_cog.missions.items():
            if m.name.lower() == mission_name.lower():
                mission_obj = m
                break

        if not mission_obj:
            await interaction.followup.send("Mission not found. Check the mission name or create one using `/create_mission`.", ephemeral=True)
            return

        # 1) Show user-friendly mission comms if present
        mission_id = mission_obj.mission_id
        comms_data = self.mission_comms_data.get(mission_id)
        if comms_data:
            embed = discord.Embed(
                title=f"Mission Comms: {mission_obj.name}",
                description=(
                    f"**Status:** {mission_obj.status.value}\n"
                    f"**Difficulty:** {mission_obj.difficulty}\n"
                    f"**Start Time:** <t:{int(mission_obj.start_time.timestamp())}:f>\n"
                ),
                color=discord.Color.dark_blue()
            )
            
            # Get readiness state emoji
            readiness = comms_data.get("readiness_state", "Condition Green")
            readiness_emoji = "🟢"
            if "yellow" in readiness.lower():
                readiness_emoji = "🟡"
            elif "red" in readiness.lower():
                readiness_emoji = "🔴"
                
            # readiness with emoji
            embed.add_field(
                name="⚠️ Readiness State",
                value=f"{readiness_emoji} {readiness}",
                inline=False
            )
            
            # frequencies with better formatting
            embed.add_field(
                name="📡 Primary Frequencies",
                value=(
                    f"**Fleet:** {comms_data.get('fleet_freq', 'N/A')}\n"
                    f"**Combat:** {comms_data.get('combat_freq', 'N/A')}\n"
                    f"**Support:** {comms_data.get('support_freq', 'N/A')}"
                ),
                inline=False
            )
            
            # notes
            notes = comms_data.get("notes", "No additional notes.")
            if notes:
                embed.add_field(
                    name="📋 Additional Notes",
                    value=notes,
                    inline=False
                )
                
            # Add command info
            embed.add_field(
                name="🎮 Command Usage",
                value=(
                    "• View ship-specific comms with `/mission_comms mission_name:\"" + mission_obj.name + "\" ship_name:\"YourShip\" advanced:True`\n"
                    "• View station-specific comms by adding `station:CAPTAIN` (or other station type)\n"
                    "• Update this comms plan with `/setup_mission_comms mission_name:\"" + mission_obj.name + "\"`"
                ),
                inline=False
            )
            
            # Footer with mission ID
            embed.set_footer(text=f"Mission ID: {mission_obj.mission_id[:8]} • Set up by: {interaction.guild.get_member(mission_obj.leader_id).display_name if interaction.guild.get_member(mission_obj.leader_id) else 'Unknown'}")
            
            await interaction.followup.send(embed=embed, ephemeral=False)
        else:
            # No user-friendly data found, don't show ephemeral error - instead show common frequencies
            embed = await self.create_mission_comms_embed(mission_obj)
            await interaction.followup.send(embed=embed)

        # 2) If advanced = True, show advanced logic
        if advanced:
            if ship_name and station:
                # Convert station string to enum if needed
                station_enum = None
                for st in StationType:
                    if st.name == station.upper() or st.value == station:
                        station_enum = st
                        break
                
                if not station_enum:
                    await interaction.followup.send(f"Invalid station type: {station}. Use one of the autocomplete suggestions.", ephemeral=True)
                    return
                    
                adv_embed = await self.create_mission_station_embed(mission_obj, ship_name, station_enum)
                await interaction.followup.send(embed=adv_embed)
            elif ship_name:
                adv_embed = await self.create_mission_ship_embed(mission_obj, ship_name)
                await interaction.followup.send(embed=adv_embed)

    @mission_comms.autocomplete("mission_name")
    async def mission_comms_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete mission names by mission.name from the MissionCog."""
        missions_cog = self.bot.get_cog('MissionCog')
        if not missions_cog:
            return []
        result = []
        for mid, mission in missions_cog.missions.items():
            if current.lower() in mission.name.lower():
                result.append(app_commands.Choice(name=mission.name, value=mission.name))
        return result[:25]
        
    @mission_comms.autocomplete("ship_name")
    async def ship_name_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete ship names from available ships in frequencies."""
        if not self.ship_frequencies:
            return []
        ships = list(self.ship_frequencies.keys())
        return [
            app_commands.Choice(name=ship, value=ship)
            for ship in ships
            if current.lower() in ship.lower()
        ][:25]
        
    @mission_comms.autocomplete("station")
    async def station_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for station types."""
        choices = []
        for st in StationType:
            if current.upper() in st.name or current.lower() in st.value.lower():
                choices.append(app_commands.Choice(name=st.value, value=st.name))
        return choices[:25]  # Discord limits to 25 choices
        
    # ------------------------------------------------------------------------
    # /list_frequencies - show available frequencies
    # ------------------------------------------------------------------------
    @app_commands.command(
        name="list_frequencies",
        description="List available frequencies for ships or general operations."
    )
    @app_commands.describe(
        category="Category of frequencies to list",
        ship_name="Name of ship (only used with 'Ship' category)"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="Ship Primary", value="SPC"),
        app_commands.Choice(name="Ship Secondary", value="SSC"),
        app_commands.Choice(name="Common Operations", value="COMMON_OPS"),
        app_commands.Choice(name="Fleet Coordination", value="FLEET_COORDINATION"),
        app_commands.Choice(name="Marine Operations", value="MARINE_OPS"),
        app_commands.Choice(name="Division Communications", value="DIV_COMMS"),
        app_commands.Choice(name="Emergency", value="EMERGENCY"),
        app_commands.Choice(name="All", value="ALL")
    ])
    async def list_frequencies(self, interaction: discord.Interaction, category: str, ship_name: Optional[str] = None):
        """List available frequencies by category."""
        await interaction.response.defer()
        
        # Get frequencies for the selected category
        freqs = []
        
        if category == "ALL":
            # Get all frequencies
            title = "All Communication Frequencies"
            for freq_type in FrequencyType:
                for channel in self.radio_channels.get(freq_type, []):
                    if ship_name and ship_name not in channel.name:
                        continue
                    freqs.append((freq_type.value, channel))
        else:
            # Get specific category
            try:
                freq_type = FrequencyType[category]
                title = f"{freq_type.value} Frequencies"
                
                for channel in self.radio_channels.get(freq_type, []):
                    if ship_name and ship_name not in channel.name:
                        continue
                    freqs.append((freq_type.value, channel))
            except KeyError:
                await interaction.followup.send(f"Invalid frequency category: {category}", ephemeral=True)
                return
        
        if not freqs:
            if ship_name:
                await interaction.followup.send(f"No {category} frequencies found for ship {ship_name}.", ephemeral=True)
            else:
                await interaction.followup.send(f"No frequencies found for category {category}.", ephemeral=True)
            return
        
        # Create embed to display frequencies
        embed = discord.Embed(
            title=title,
            description=f"Displaying {len(freqs)} frequencies" + (f" for {ship_name}" if ship_name else ""),
            color=discord.Color.blue()
        )
        
        # Group by category
        by_category = {}
        for category, channel in freqs:
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(channel)
            
        # Add fields for each category
        for category, channels in by_category.items():
            field_value = []
            for channel in channels:
                field_value.append(f"• **{channel.name}**: {channel.freq:.3f}" + (" 🔒" if channel.encrypted else ""))
                
            embed.add_field(
                name=f"📻 {category}",
                value="\n".join(field_value),
                inline=False
            )
            
        # Add footer with timestamp
        embed.set_footer(text=f"Frequency data current as of {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC")
        
        await interaction.followup.send(embed=embed)
        
    @list_frequencies.autocomplete("ship_name")
    async def list_frequencies_ship_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for ship names used in frequency listing."""
        ships = set()
        
        # Extract ship names from channels
        for freq_type in self.radio_channels:
            for channel in self.radio_channels.get(freq_type, []):
                # Try to extract ship name from channel name
                for ship_name in self.ship_prefixes:
                    if ship_name in channel.name:
                        ships.add(ship_name)
                        
        return [
            app_commands.Choice(name=ship, value=ship)
            for ship in ships
            if current.lower() in ship.lower()
        ][:25]

# ----------------------------------------------------------------------------
# The Modal for user-friendly mission comms setup (limited to 5 total inputs)
# ----------------------------------------------------------------------------
class MissionCommsSetupModal(discord.ui.Modal, title="Mission Comms Setup"):
    """
    Collect readiness, up to 3 frequencies, and optional notes from user
    (5 total text fields to avoid 'no open space' error).
    """

    def __init__(self, cog: SRSCog, mission_obj: Any):
        super().__init__()
        self.cog = cog
        self.mission_obj = mission_obj
        
        # Get default frequencies for some common channels
        default_fleet_freq = "FLEET 30.000"
        default_combat_freq = "RED 29.500"
        default_support_freq = "LOG 27.000"
        
        # Check if we have real frequencies from DCS data
        for channel in self.cog.radio_channels.get(FrequencyType.FLEET_COORDINATION, []):
            if channel.freq > 0:
                default_fleet_freq = f"{channel.name} {channel.freq:.3f}"
                break
                
        for channel in self.cog.radio_channels.get(FrequencyType.COMMON_OPS, []):
            if "Providence" in channel.name and "C&C" in channel.name:
                default_combat_freq = f"{channel.name} {channel.freq:.3f}"
                break
                
        for channel in self.cog.radio_channels.get(FrequencyType.DIV_COMMS, []):
            if "Support" in channel.name:
                default_support_freq = f"{channel.name} {channel.freq:.3f}"
                break

        # We can only have 5 total items:
        self.readiness_state = discord.ui.TextInput(
            label="Readiness State",
            placeholder="Condition Green, Yellow, Red, or custom state",
            required=True,
            max_length=50,
            default="Condition Green"
        )
        self.fleet_freq = discord.ui.TextInput(
            label="Primary Fleet Frequency",
            placeholder=default_fleet_freq,
            required=True,
            max_length=50,
            default=default_fleet_freq
        )
        self.combat_freq = discord.ui.TextInput(
            label="Combat (Red) Frequency",
            placeholder=default_combat_freq,
            required=True,
            max_length=50,
            default=default_combat_freq
        )
        self.support_freq = discord.ui.TextInput(
            label="Support/Logistics Frequency",
            placeholder=default_support_freq,
            required=False,
            max_length=50,
            default=default_support_freq
        )
        # The 5th field is a multiline notes field
        self.notes = discord.ui.TextInput(
            label="Additional Notes",
            style=discord.TextStyle.paragraph,
            placeholder="Emergency procedures, ROE, comms discipline requirements, etc.",
            required=False,
            max_length=300
        )

        # Add them in order. We now have 5 total. This avoids the 'no open space' error.
        self.add_item(self.readiness_state)
        self.add_item(self.fleet_freq)
        self.add_item(self.combat_freq)
        self.add_item(self.support_freq)
        self.add_item(self.notes)

    async def on_submit(self, interaction: discord.Interaction):
        """
        Save user input in cog.mission_comms_data under mission_obj.mission_id.
        """
        comms_info = {
            "readiness_state": self.readiness_state.value.strip(),
            "fleet_freq": self.fleet_freq.value.strip(),
            "combat_freq": self.combat_freq.value.strip(),
            "support_freq": self.support_freq.value.strip() if self.support_freq.value else "N/A",
            "notes": self.notes.value.strip() if self.notes.value else "No notes provided."
        }

        mission_id = self.mission_obj.mission_id
        self.cog.mission_comms_data[mission_id] = comms_info

        # Create a mission setup message with a nice embed
        embed = discord.Embed(
            title=f"Mission Comms Setup: {self.mission_obj.name}",
            description="Communications plan has been configured successfully!",
            color=discord.Color.green()
        )
        
        # Get readiness state emoji
        readiness = self.readiness_state.value.strip()
        readiness_emoji = "🟢"
        if "yellow" in readiness.lower():
            readiness_emoji = "🟡"
        elif "red" in readiness.lower():
            readiness_emoji = "🔴"
            
        embed.add_field(
            name="⚠️ Readiness State",
            value=f"{readiness_emoji} {readiness}",
            inline=False
        )
        
        embed.add_field(
            name="📡 Frequencies",
            value=(
                f"**Fleet:** {self.fleet_freq.value.strip()}\n"
                f"**Combat:** {self.combat_freq.value.strip()}\n"
                f"**Support:** {self.support_freq.value.strip() if self.support_freq.value else 'N/A'}"
            ),
            inline=False
        )
        
        if self.notes.value:
            embed.add_field(
                name="📋 Additional Notes",
                value=self.notes.value.strip(),
                inline=False
            )
            
        embed.add_field(
            name="🎮 Next Steps",
            value=(
                "• View this comms plan with `/mission_comms mission_name:\"" + self.mission_obj.name + "\"`\n"
                "• View detailed ship comms by adding `ship_name:\"YourShip\" advanced:True`\n"
                "• View station-specific comms by adding `station:CAPTAIN` (or other station type)"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Set up by: {interaction.user.display_name} • Mission ID: {self.mission_obj.mission_id[:8]}")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

# ----------------------------------------------------------------------------
# The `setup` function to load the cog
# ----------------------------------------------------------------------------
async def setup(bot: commands.Bot):
    """Set up the SRS cog."""
    await bot.add_cog(SRSCog(bot))
    logger.info("SRSCog loaded successfully")