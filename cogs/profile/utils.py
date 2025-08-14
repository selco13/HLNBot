"""Utility functions for profile system."""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from .constants import RANKS, STANDARD_TO_DIVISION_RANK, RANK_ABBREVIATIONS

logger = logging.getLogger('profile.utils')

class RankInfo:
    """Information about a rank."""
    def __init__(self, specialized_name, standard_name, specialized_abbrev, 
                 standard_abbrev, division, specialty, level):
        self.specialized_name = specialized_name
        self.standard_name = standard_name
        self.specialized_abbrev = specialized_abbrev
        self.standard_abbrev = standard_abbrev
        self.division = division
        self.specialty = specialty
        self.level = level
        
    @property
    def display_name(self) -> str:
        """Get display name for the rank."""
        return f"{self.specialized_name} ({self.standard_name})"
    
    @property 
    def display_abbrev(self) -> str:
        """Get display abbreviation for the rank."""
        return f"{self.specialized_abbrev}/{self.standard_abbrev}"

def parse_list_field(field: Any) -> List[str]:
    """Parse a field that might be a list or comma-separated string."""
    try:
        if field is None:
            return []
            
        if isinstance(field, str):
            # Handle comma-separated string
            return [item.strip() for item in field.split(',') if item.strip()]
        elif isinstance(field, list):
            # Handle list format
            return [str(cert).strip() for cert in field if cert]
        else:
            # Handle unexpected types
            return [str(field).strip()]
    except Exception as e:
        logger.error(f"Error parsing list field: {e}")
        return []

def get_rank_info(division: str, specialty: str, rank_index: int) -> Optional[RankInfo]:
    """
    Get rank information by division, specialty and rank index.
    
    Args:
        division: Member's division
        specialty: Member's specialization
        rank_index: Index of rank in the RANKS list
        
    Returns:
        RankInfo object or None if not found
    """
    try:
        # Guard against invalid indices
        if rank_index < 0 or rank_index >= len(RANKS):
            return None
            
        # Get standard rank info
        standard_rank_name, standard_abbrev = RANKS[rank_index]
        
        # Check for division-specific rank
        if division and specialty:
            div_key = (division.lower(), specialty.lower(), standard_rank_name.lower())
            if div_key in STANDARD_TO_DIVISION_RANK:
                div_name, div_abbrev = STANDARD_TO_DIVISION_RANK[div_key]
                return RankInfo(
                    specialized_name=div_name,
                    standard_name=standard_rank_name,
                    specialized_abbrev=div_abbrev,
                    standard_abbrev=standard_abbrev,
                    division=division,
                    specialty=specialty,
                    level=rank_index
                )
        
        # Return standard rank info if no specialized rank found
        return RankInfo(
            specialized_name=standard_rank_name,
            standard_name=standard_rank_name,
            specialized_abbrev=standard_abbrev,
            standard_abbrev=standard_abbrev,
            division=division,
            specialty=specialty,
            level=rank_index
        )
    except Exception as e:
        logger.error(f"Error in get_rank_info: {e}")
        return None

def calculate_service_time(join_date: str) -> str:
    """Compute how long a member has served."""
    try:
        dt_join = datetime.strptime(join_date, "%Y-%m-%d")
        now = datetime.now()
        total_months = (now.year - dt_join.year) * 12 + (now.month - dt_join.month)
        years = total_months // 12
        months = total_months % 12
        if years > 0:
            if months > 0:
                return f"{years} year{'s' if years != 1 else ''}, {months} month{'s' if months != 1 else ''}"
            return f"{years} year{'s' if years != 1 else ''}"
        elif months > 0:
            return f"{months} month{'s' if months != 1 else ''}"
        else:
            return "Less than 1 month"
    except (ValueError, TypeError):
        return "Unknown"

def format_stellar_date(date_str: str) -> str:
    """Format Earth date as Stellar Date (SD)."""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        stellar_year = date_obj.year + 930
        return f"SD {stellar_year}.{date_obj.month:02d}.{date_obj.day:02d}"
    except (ValueError, TypeError):
        return "SD UNKNOWN"