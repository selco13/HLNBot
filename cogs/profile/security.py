"""Security-related functionality for profile system."""

import discord
import logging
import random
import string
from enum import Enum
from typing import Optional, Tuple
from .constants import CLEARANCE_LEVELS, AUTH_CODES

logger = logging.getLogger('profile.security')

class SecurityClearance(Enum):
    """Security clearance levels with associated ranks."""
    TOP_SECRET = {"level": 4, "ranks": ["Admiral", "Vice Admiral"], "emoji": "🔴"}
    SECRET = {"level": 3, "ranks": ["Rear Admiral", "Commodore"], "emoji": "🟡"}
    CONFIDENTIAL = {"level": 2, "ranks": ["Fleet Captain", "Captain", "Commander"], "emoji": "🟢"}
    RESTRICTED = {"level": 1, "ranks": [], "emoji": "⚪"}  # Default level

    @classmethod
    def get_clearance_from_member(cls, member: discord.Member) -> 'SecurityClearance':
        """Get clearance level based on member's roles."""
        member_roles = [role.name for role in member.roles]
        
        for clearance in cls:
            if any(rank in member_roles for rank in clearance.value["ranks"]):
                return clearance
                
        return cls.RESTRICTED

    @classmethod
    def can_view_full_profile(cls, viewer_clearance: 'SecurityClearance', target_clearance: 'SecurityClearance') -> bool:
        """Determine if viewer can see full profile."""
        return viewer_clearance.value["level"] >= target_clearance.value["level"]
    
    @classmethod
    def get_clearance_by_level(cls, level: int) -> 'SecurityClearance':
        """Get clearance by numeric level."""
        for clearance in cls:
            if clearance.value["level"] == level:
                return clearance
        return cls.RESTRICTED

class SecurityClassification:
    """Security classification class with proper string representation."""
    def __init__(self, classification, auth_code):
        self.classification = classification
        self.auth_code = auth_code
        
    def __str__(self):
        """String representation for display and logging."""
        return self.classification
        
    def __repr__(self):
        """Formal representation for debugging."""
        return f"SecurityClassification('{self.classification}', '{self.auth_code}')"

def generate_auth_code() -> str:
    """Generate a random authentication code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def get_security_classification(rank: str) -> str:
    """Get security classification based on rank."""
    rank = rank or ""
    normalized_rank = rank.lower().strip()
    clearance_lookup = {k.lower(): v for k, v in CLEARANCE_LEVELS.items()}
    clearance = clearance_lookup.get(normalized_rank, {'level': 1, 'code': 'EPSILON'})
    level = clearance['level']

    if level >= 5:
        return "TOP_SECRET"
    elif level >= 4:
        return "SECRET" 
    elif level >= 3:
        return "CONFIDENTIAL"
    return "RESTRICTED"

def get_clearance_code(rank: str) -> str:
    """Generate a full clearance code for a rank."""
    # Map ranks to their clearance codes directly
    rank_to_clearance = {
        "Admiral": "TS-ALPHA",
        "Vice Admiral": "TS-BRAVO",
        "Rear Admiral": "SC-CHARLIE",
        "Commodore": "SC-DELTA",
        "Fleet Captain": "CO-ECHO",
        "Captain": "CO-FOXTROT",
        "Commander": "CO-GOLF",
        "Lieutenant Commander": "RE-HOTEL",
        "Lieutenant": "RE-INDIA",
        "Lieutenant Junior Grade": "RE-JULIET",
        "Ensign": "RE-KILO",
        "Chief Petty Officer": "RE-LIMA",
        "Petty Officer 1st Class": "RE-MIKE",
        "Petty Officer 2nd Class": "RE-NOVEMBER",
        "Petty Officer 3rd Class": "RE-OSCAR",
        "Master Crewman": "RE-PAPA",
        "Senior Crewman": "RE-QUEBEC",
        "Crewman": "RE-ROMEO",
        "Crewman Apprentice": "RE-SIERRA",
        "Crewman Recruit": "RE-TANGO",
        "Ambassador": "CO-UNIFORM",
        "Associate": "RE-VICTOR"
    }
    
    base_code = rank_to_clearance.get(rank, "RE-EPSILON")
    
    # Add a random suffix for uniqueness
    random_suffix = generate_auth_code()
    
    return f"{base_code}-{random_suffix}"

def validate_security_level(member: discord.Member, required_level: int) -> bool:
    """
    Validate if member has the required security clearance level.
    
    Args:
        member: Discord member to check
        required_level: Required security level (1-5)
        
    Returns:
        bool: True if member has required level, False otherwise
    """
    clearance = SecurityClearance.get_clearance_from_member(member)
    return clearance.value["level"] >= required_level

def get_emoji_for_clearance(clearance: SecurityClearance) -> str:
    """Get emoji representing security clearance level."""
    return clearance.value["emoji"]

def get_security_banner(clearance: SecurityClearance) -> str:
    """
    Generate a security banner for a clearance level.
    
    For example:
    🔴 TOP SECRET 🔴 TOP SECRET 🔴
    """
    emoji = clearance.value["emoji"]
    security_text = clearance.name.replace('_', ' ')
    return f"{emoji} {security_text} {emoji}"