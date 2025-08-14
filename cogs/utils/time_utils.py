# cogs/utils/time_utils.py

from datetime import datetime
import pytz
from typing import Dict, List, Optional, Any, Union, Tuple, Set
import re

class TimeParsingError(Exception):
    """Custom exception for time parsing errors."""
    pass

class TimeConverter:
    # Regular expressions for different time formats
    ZULU_PATTERN = re.compile(r'^(\d{4})\s*(?:Z|ZULU|UTC)?$')  # 1500Z, 1500 ZULU, 1500 UTC
    MILITARY_PATTERN = re.compile(r'^(\d{4})$')  # 1500
    STANDARD_PATTERN = re.compile(r'^(\d{1,2}):?(\d{2})\s*(?:AM|PM)?$', re.IGNORECASE)  # 3:00PM, 1500, 15:00

    @staticmethod
    def parse_time(time_str: str, timezone_str: Optional[str] = None, date_str: Optional[str] = None) -> datetime:
        """
        Parse time string and convert to UTC.
        
        Args:
            time_str: Time in various formats (1500Z, 1500 ZULU, 3:00 PM, etc.)
            timezone_str: Timezone identifier (e.g., 'America/New_York', 'EST', 'UTC+2')
            date_str: Optional date in YYYY-MM-DD format. If not provided, uses current date.
        
        Returns:
            datetime object in UTC
        """
        try:
            # Clean up input
            time_str = time_str.strip().upper()
            
            # Handle date
            if date_str:
                try:
                    base_date = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    raise TimeParsingError("Date must be in YYYY-MM-DD format")
            else:
                base_date = datetime.now()

            # Try parsing as Zulu/UTC time
            zulu_match = TimeConverter.ZULU_PATTERN.match(time_str)
            if zulu_match:
                time_str = zulu_match.group(1)
                try:
                    hours = int(time_str[:2])
                    minutes = int(time_str[2:])
                    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                        raise TimeParsingError("Invalid hours or minutes")
                    dt = datetime(base_date.year, base_date.month, base_date.day, 
                                hours, minutes, tzinfo=pytz.UTC)
                    return dt
                except ValueError:
                    raise TimeParsingError("Invalid time format")

            # If timezone provided, parse as local time
            if timezone_str:
                try:
                    # Handle common timezone abbreviations
                    timezone_map = {
                        'EST': 'America/New_York',
                        'CST': 'America/Chicago',
                        'MST': 'America/Denver',
                        'PST': 'America/Los_Angeles',
                        'EDT': 'America/New_York',
                        'CDT': 'America/Chicago',
                        'MDT': 'America/Denver',
                        'PDT': 'America/Los_Angeles',
                    }
                    
                    # Convert common abbreviations to proper timezone names
                    if timezone_str in timezone_map:
                        timezone_str = timezone_map[timezone_str]
                    
                    # Get timezone object
                    tz = pytz.timezone(timezone_str)
                    
                    # Parse the time
                    hours, minutes = TimeConverter._parse_time_components(time_str)
                    
                    # Create localized time
                    local_dt = tz.localize(datetime(base_date.year, base_date.month, 
                                                  base_date.day, hours, minutes))
                    
                    # Convert to UTC
                    return local_dt.astimezone(pytz.UTC)
                    
                except pytz.exceptions.UnknownTimeZoneError:
                    raise TimeParsingError(f"Unknown timezone: {timezone_str}")

            raise TimeParsingError("Timezone is required for non-Zulu times")

        except TimeParsingError:
            raise
        except Exception as e:
            raise TimeParsingError(f"Error parsing time: {str(e)}")

    @staticmethod
    def _parse_time_components(time_str: str) -> Tuple[int, int]:
        """Parse time string into hours and minutes."""
        # Try military time format first (1500)
        military_match = TimeConverter.MILITARY_PATTERN.match(time_str)
        if military_match:
            time_str = military_match.group(1)
            hours = int(time_str[:2])
            minutes = int(time_str[2:])
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise TimeParsingError("Invalid hours or minutes")
            return hours, minutes

        # Try standard time format (3:00 PM)
        standard_match = TimeConverter.STANDARD_PATTERN.match(time_str)
        if standard_match:
            hours = int(standard_match.group(1))
            minutes = int(standard_match.group(2))
            
            # Check if PM is specified
            if 'PM' in time_str.upper() and hours < 12:
                hours += 12
            elif 'AM' in time_str.upper() and hours == 12:
                hours = 0
                
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise TimeParsingError("Invalid hours or minutes")
            return hours, minutes

        raise TimeParsingError("Invalid time format")

    @staticmethod
    def format_time(dt: datetime, include_date: bool = True) -> str:
        """Format datetime object into standard Zulu time string."""
        if include_date:
            return dt.strftime('%Y-%m-%d %H%MZ')
        return dt.strftime('%H%MZ')

    @staticmethod
    def get_available_timezones() -> list:
        """Get list of common timezone names."""
        common_timezones = [
            'UTC', 'America/New_York', 'America/Chicago', 
            'America/Denver', 'America/Los_Angeles',
            'Europe/London', 'Europe/Paris', 'Australia/Sydney'
        ]
        return sorted(common_timezones)
