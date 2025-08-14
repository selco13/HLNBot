"""Data models for profile system."""

from pydantic import BaseModel, validator, Field
from typing import Optional, List, Dict, Any

class ProfileData(BaseModel):
    """Validation model for profile data including all Coda fields."""
    id_number: Optional[str] = None
    discord_username: str
    discord_user_id: str
    division: Optional[str] = None
    rank: Optional[str] = None
    awards: Optional[List[str]] = Field(default_factory=list)
    certifications: Optional[List[str]] = Field(default_factory=list) 
    specialization: Optional[str] = None
    join_date: Optional[str] = None
    status: Optional[str] = None
    security_clearance: Optional[str] = None
    classified_information: Optional[str] = None
    completed_missions: Optional[List[str]] = Field(default_factory=list)
    mission_count: Optional[int] = 0  # Set default to 0
    mission_type: Optional[List[str]] = Field(default_factory=list)
    special_operations: Optional[List[str]] = Field(default_factory=list)
    strategic_planning: Optional[str] = None
    combat_missions: Optional[List[str]] = Field(default_factory=list)
    strategic_assessment: Optional[str] = None
    command_evaluation: Optional[str] = None
    fleet_operations: Optional[str] = None
    rank_index: Optional[int] = 0
    
    @validator('mission_count', pre=True)
    def validate_mission_count(cls, v):
        """Convert empty string or None to 0 for mission count."""
        if v is None or v == '':
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @validator('id_number')
    def validate_id_number(cls, v):
        """Validate the ID number format."""
        if not v:
            return v  # Allow None/empty
            
        parts = v.split('-')
        if len(parts) != 3:
            raise ValueError('ID number must be in format DIV-RANK-XXXX')
    
        div_code, rank_code_str, seq_num = parts
        valid_div_codes = {'HQ', 'TC', 'OP', 'SP', 'ND'}
        
        if div_code not in valid_div_codes:
            raise ValueError(f'Invalid division code "{div_code}". Must be one of: {", ".join(valid_div_codes)}')
    
        try:
            rank_code_int = int(rank_code_str)
            if not (1 <= rank_code_int <= 21):
                raise ValueError('Rank code must be between 1 and 21')
        except ValueError:
            raise ValueError('Rank code must be numeric')
    
        if not (len(seq_num) == 4 and seq_num.isdigit()):
            raise ValueError('Sequence number must be 4 digits')
    
        return v

    @validator('discord_user_id')
    def validate_discord_id(cls, v):
        """Validate Discord user ID."""
        if not v or not v.isdigit():
            raise ValueError('Discord User ID must be numeric')
        return v

    class Config:
        """Configuration for the ProfileData model."""
        extra = "ignore"  # Allow extra fields