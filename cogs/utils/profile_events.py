# cogs/utils/profile_events.py

import discord 
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from enum import Enum, auto


class ProfileEventType(Enum):
    """Types of profile-related events."""
    ONBOARDING_COMPLETE = "onboarding_complete"
    MISSION_COMPLETE = "mission_complete"
    EVALUATION_COMPLETE = "evaluation_complete"
    CERTIFICATION_GRANTED = "certification_granted"
    CERTIFICATION_REVOKED = "certification_revoked"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REMOVED = "role_removed"
    RANK_UPDATED = "rank_updated"
    DIVISION_UPDATED = "division_updated"
    SPECIALIZATION_UPDATED = "specialization_updated"
    AWARD_GRANTED = "award_granted"
    FLIGHT_HOURS_UPDATED = "flight_hours_updated"
    SECURITY_CLEARANCE_UPDATED = "security_clearance_updated"

@dataclass
class ProfileEvent:
    """Event data for profile updates."""
    event_type: ProfileEventType
    member_id: int
    timestamp: datetime
    data: Dict[str, Any]
    actor_id: Optional[int] = None
    reason: Optional[str] = None

@dataclass
class ProfileUpdateBatch:
    """Batch of profile updates to be processed."""
    member_id: int
    updates: Dict[str, Any]
    events: List[ProfileEvent] = field(default_factory=list)
    requires_role_sync: bool = False

class RatingSystem:
    """Handles calculation of various ratings."""
    
    @staticmethod
    def calculate_combat_rating(metrics: Dict[str, Any]) -> str:
        """Calculate combat rating based on metrics."""
        total_combat_missions = metrics.get('combat_missions', 0)
        success_rate = metrics.get('combat_success_rate', 0)
        
        if total_combat_missions < 5:
            return "Rookie"
        elif total_combat_missions < 15:
            return "Experienced" if success_rate > 70 else "Novice"
        elif total_combat_missions < 30:
            return "Veteran" if success_rate > 80 else "Experienced"
        else:
            return "Elite" if success_rate > 90 else "Veteran"

    @staticmethod
    def calculate_trade_rating(metrics: Dict[str, Any]) -> str:
        """Calculate trade rating based on metrics."""
        total_profit = metrics.get('total_trade_profit', 0)
        successful_runs = metrics.get('successful_trade_runs', 0)
        
        if successful_runs < 5:
            return "Rookie"
        elif successful_runs < 20:
            return "Merchant" if total_profit > 1000000 else "Trader"
        elif successful_runs < 50:
            return "Magnate" if total_profit > 5000000 else "Merchant"
        else:
            return "Tycoon" if total_profit > 20000000 else "Magnate"

    @staticmethod
    def calculate_mining_rating(metrics: Dict[str, Any]) -> str:
        """Calculate mining rating based on metrics."""
        total_ore = metrics.get('total_ore_mined', 0)
        rare_finds = metrics.get('rare_mineral_finds', 0)
        
        if total_ore < 100000:
            return "Rookie"
        elif total_ore < 500000:
            return "Miner" if rare_finds > 5 else "Prospector"
        elif total_ore < 2000000:
            return "Expert" if rare_finds > 15 else "Miner"
        else:
            return "Master" if rare_finds > 30 else "Expert"

    @staticmethod
    def calculate_exploration_rating(metrics: Dict[str, Any]) -> str:
        """Calculate exploration rating based on metrics."""
        systems_visited = metrics.get('systems_visited', 0)
        discoveries = metrics.get('new_discoveries', 0)
        
        if systems_visited < 10:
            return "Rookie"
        elif systems_visited < 30:
            return "Scout" if discoveries > 5 else "Explorer"
        elif systems_visited < 100:
            return "Pathfinder" if discoveries > 15 else "Scout"
        else:
            return "Pioneer" if discoveries > 30 else "Pathfinder"

@dataclass
class CertificationRequirements:
    """Requirements for ship certifications."""
    ship_type: str
    level: str
    required_flight_hours: int
    required_missions: int
    required_specializations: List[str]
    combat_rating_required: Optional[str] = None
    trade_rating_required: Optional[str] = None
    mining_rating_required: Optional[str] = None
    exploration_rating_required: Optional[str] = None
    
    def meets_requirements(self, profile: Any) -> Tuple[bool, List[str]]:
        """Check if profile meets certification requirements."""
        missing = []
        
        # Check flight hours
        ship_hours = profile.flight_hours.get(self.ship_type, 0)
        if ship_hours < self.required_flight_hours:
            missing.append(f"Needs {self.required_flight_hours - ship_hours} more flight hours")
            
        # Check missions
        if profile.mission_count < self.required_missions:
            missing.append(f"Needs {self.required_missions - profile.mission_count} more missions")
            
        # Check specializations
        for spec in self.required_specializations:
            if spec not in profile.specializations:
                missing.append(f"Missing specialization: {spec}")
                
        # Check ratings
        if self.combat_rating_required and profile.combat_rating != self.combat_rating_required:
            missing.append(f"Requires {self.combat_rating_required} combat rating")
            
        if self.trade_rating_required and profile.trade_rating != self.trade_rating_required:
            missing.append(f"Requires {self.trade_rating_required} trade rating")
            
        if self.mining_rating_required and profile.mining_rating != self.mining_rating_required:
            missing.append(f"Requires {self.mining_rating_required} mining rating")
            
        if self.exploration_rating_required and profile.exploration_rating != self.exploration_rating_required:
            missing.append(f"Requires {self.exploration_rating_required} exploration rating")
            
        return len(missing) == 0, missing

class SecurityClearance:
    """Handles security clearance calculations."""
    
    LEVELS = {
        "Standard": 0,
        "Restricted": 1,
        "Confidential": 2,
        "Secret": 3,
        "Top Secret": 4
    }
    
    @staticmethod
    def calculate_clearance(profile: Any) -> str:
        """Calculate security clearance level based on profile metrics."""
        points = 0
        
        # Time in org
        join_date = datetime.fromisoformat(profile.join_date)
        months_active = (datetime.now() - join_date).days / 30
        points += min(months_active / 3, 10)  # Up to 10 points for longevity
        
        # Mission participation
        points += min(profile.mission_count / 10, 10)  # Up to 10 points
        
        # Rank consideration
        rank_value = RANK_NUMBERS.get(profile.rank, 0)
        points += rank_value * 2  # Up to 20 points
        
        # Special certifications
        points += len(profile.certifications)  # Points for each cert
        
        # Determine level
        if points >= 45:
            return "Top Secret"
        elif points >= 35:
            return "Secret"
        elif points >= 25:
            return "Confidential"
        elif points >= 15:
            return "Restricted"
        else:
            return "Standard"
