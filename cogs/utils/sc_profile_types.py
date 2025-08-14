# cogs/utils/sc_profile_types.py

import discord 
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from datetime import datetime
from enum import Enum

class ShipRole(Enum):
    """Star Citizen ship roles."""
    FIGHTER = "Fighter"
    BOMBER = "Bomber"
    GUNSHIP = "Gunship"
    CORVETTE = "Corvette"
    FRIGATE = "Frigate"
    DESTROYER = "Destroyer"
    CRUISER = "Cruiser"
    CARGO = "Cargo"
    MINING = "Mining"
    EXPLORATION = "Exploration"
    MEDICAL = "Medical"
    TRANSPORT = "Transport"
    MISC = "Miscellaneous"

class StationRole(Enum):
    """Ship station roles."""
    CAPTAIN = "Captain"
    XO = "Executive Officer"
    HELMSMAN = "Helmsman"
    WEAPONS = "Weapons Officer"
    ENGINEERING = "Engineering Officer"
    MEDICAL = "Medical Officer"
    SECURITY = "Security Officer"
    CARGO = "Cargo Master"
    MINING = "Mining Officer"
    SCIENCE = "Science Officer"

class CareerPath(Enum):
    """Star Citizen career paths."""
    COMBAT = "Combat"
    TRADE = "Trade"
    EXPLORATION = "Exploration"
    MINING = "Mining"
    SALVAGE = "Salvage"
    MEDICAL = "Medical"
    ENGINEERING = "Engineering"
    SECURITY = "Security"

class ExperienceLevel(Enum):
    """Experience levels for various activities."""
    ROOKIE = "Rookie"
    NOVICE = "Novice"
    EXPERIENCED = "Experienced"
    VETERAN = "Veteran"
    ELITE = "Elite"
    MASTER = "Master"

@dataclass
class ShipCertification:
    """Represents a ship certification."""
    ship_type: str
    cert_level: str
    granted_date: datetime
    granted_by: int  # Discord ID
    flight_hours: int = 0
    specializations: List[str] = field(default_factory=list)
    endorsements: List[str] = field(default_factory=list)
    expires: Optional[datetime] = None
    revoked: bool = False

@dataclass
class CareerProgress:
    """Tracks progress in a career path."""
    career: CareerPath
    level: ExperienceLevel
    experience_points: int = 0
    missions_completed: int = 0
    achievements: List[str] = field(default_factory=list)
    specializations: List[str] = field(default_factory=list)
    mentor: Optional[int] = None  # Discord ID of mentor

@dataclass
class StationAssignment:
    """Represents a station assignment on a ship."""
    ship_name: str
    role: StationRole
    assigned_date: datetime
    assigned_by: int  # Discord ID
    is_primary: bool = False
    performance_rating: Optional[float] = None
    notes: str = ""

@dataclass
class StarCitizenMetrics:
    """Tracks various Star Citizen gameplay metrics."""
    total_flight_hours: int = 0
    combat_missions: int = 0
    trade_missions: int = 0
    mining_operations: int = 0
    exploration_missions: int = 0
    medical_missions: int = 0
    salvage_operations: int = 0
    
    # Combat metrics
    combat_victories: int = 0
    ships_destroyed: int = 0
    assist_kills: int = 0
    deaths: int = 0
    
    # Trade metrics
    cargo_delivered: int = 0
    total_profit: int = 0
    successful_runs: int = 0
    cargo_lost: int = 0
    
    # Mining metrics
    ore_extracted: int = 0
    rare_minerals_found: int = 0
    mining_accidents: int = 0
    
    # Exploration metrics
    systems_visited: int = 0
    jump_points_discovered: int = 0
    anomalies_found: int = 0
    
    # Medical metrics
    patients_treated: int = 0
    successful_rescues: int = 0
    medical_research: int = 0
    
    def calculate_combat_rating(self) -> ExperienceLevel:
        """Calculate combat experience level."""
        if self.combat_missions < 10:
            return ExperienceLevel.ROOKIE
        
        kd_ratio = self.ships_destroyed / max(self.deaths, 1)
        victory_rate = self.combat_victories / max(self.combat_missions, 1)
        
        if kd_ratio >= 3.0 and victory_rate >= 0.9:
            return ExperienceLevel.ELITE
        elif kd_ratio >= 2.0 and victory_rate >= 0.8:
            return ExperienceLevel.VETERAN
        elif kd_ratio >= 1.5 and victory_rate >= 0.7:
            return ExperienceLevel.EXPERIENCED
        elif kd_ratio >= 1.0 and victory_rate >= 0.6:
            return ExperienceLevel.NOVICE
        else:
            return ExperienceLevel.ROOKIE

    def calculate_trade_rating(self) -> ExperienceLevel:
        """Calculate trade experience level."""
        if self.trade_missions < 10:
            return ExperienceLevel.ROOKIE
        
        success_rate = self.successful_runs / max(self.trade_missions, 1)
        profit_per_run = self.total_profit / max(self.successful_runs, 1)
        
        if success_rate >= 0.95 and profit_per_run >= 100000:
            return ExperienceLevel.ELITE
        elif success_rate >= 0.85 and profit_per_run >= 75000:
            return ExperienceLevel.VETERAN
        elif success_rate >= 0.75 and profit_per_run >= 50000:
            return ExperienceLevel.EXPERIENCED
        elif success_rate >= 0.65 and profit_per_run >= 25000:
            return ExperienceLevel.NOVICE
        else:
            return ExperienceLevel.ROOKIE

    def calculate_mining_rating(self) -> ExperienceLevel:
        """Calculate mining experience level."""
        if self.mining_operations < 10:
            return ExperienceLevel.ROOKIE
            
        ore_per_op = self.ore_extracted / max(self.mining_operations, 1)
        rare_find_rate = self.rare_minerals_found / max(self.mining_operations, 1)
        safety_rating = 1 - (self.mining_accidents / max(self.mining_operations, 1))
        
        if ore_per_op >= 10000 and rare_find_rate >= 0.1 and safety_rating >= 0.95:
            return ExperienceLevel.ELITE
        elif ore_per_op >= 7500 and rare_find_rate >= 0.05 and safety_rating >= 0.9:
            return ExperienceLevel.VETERAN
        elif ore_per_op >= 5000 and rare_find_rate >= 0.02 and safety_rating >= 0.85:
            return ExperienceLevel.EXPERIENCED
        elif ore_per_op >= 2500 and safety_rating >= 0.8:
            return ExperienceLevel.NOVICE
        else:
            return ExperienceLevel.ROOKIE

@dataclass
class SCProfile:
    """Complete Star Citizen profile for a member."""
    
    # Basic Info
    discord_id: int
    handle: str  # Star Citizen handle
    service_id: str  # HLN service ID (e.g., HQ-1-0001)
    join_date: datetime
    
    # Organizational Info
    division: str
    rank: str
    security_clearance: str = "Standard"
    active_status: bool = True
    last_active: Optional[datetime] = None
    
    # Certifications and Roles
    ship_certifications: List[ShipCertification] = field(default_factory=list)
    station_assignments: List[StationAssignment] = field(default_factory=list)
    career_tracks: Dict[CareerPath, CareerProgress] = field(default_factory=dict)
    
    # Performance Metrics
    metrics: StarCitizenMetrics = field(default_factory=StarCitizenMetrics)
    commendations: List[str] = field(default_factory=list)
    demerits: List[str] = field(default_factory=list)
    
    # Mission History
    total_missions: int = 0
    mission_success_rate: float = 0.0
    mission_history: List[str] = field(default_factory=list)
    preferred_roles: List[StationRole] = field(default_factory=list)
    
    # Equipment and Resources
    owned_ships: List[str] = field(default_factory=list)
    assigned_equipment: List[str] = field(default_factory=list)
    special_clearances: List[str] = field(default_factory=list)
    
    def calculate_experience_level(self) -> ExperienceLevel:
        """Calculate overall experience level."""
        points = 0
        
        # Time in org
        days_active = (datetime.now() - self.join_date).days
        points += min(days_active / 30, 24)  # Up to 24 points for 2 years
        
        # Missions and success rate
        points += min(self.total_missions / 10, 24)  # Up to 24 points
        points += self.mission_success_rate * 12  # Up to 12 points
        
        # Certifications
        points += len(self.ship_certifications) * 2  # 2 points per cert
        
        # Career progress
        for progress in self.career_tracks.values():
            points += progress.experience_points / 1000  # Normalized points
            
        # Calculate level
        if points >= 80:
            return ExperienceLevel.ELITE
        elif points >= 60:
            return ExperienceLevel.VETERAN
        elif points >= 40:
            return ExperienceLevel.EXPERIENCED
        elif points >= 20:
            return ExperienceLevel.NOVICE
        else:
            return ExperienceLevel.ROOKIE
            
    def can_certify_for_ship(self, ship_type: str) -> Tuple[bool, List[str]]:
        """Check if member can be certified for a ship."""
        requirements = []
        
        # Get ship data
        ships_cog = self.bot.get_cog('ShipsCog')
        if not ships_cog:
            return False, ["Ship data unavailable"]
            
        ship_data = ships_cog.get_ship(ship_type)
        if not ship_data:
            return False, ["Invalid ship type"]
            
        # Check current certifications
        has_prerequisites = False
        for cert in self.ship_certifications:
            if not cert.revoked and cert.ship_type == ship_type:
                return False, ["Already certified for this ship"]
                
        # Check role requirements
        role = ShipRole(ship_data.get('role', 'MISC'))
        if role == ShipRole.FIGHTER:
            if self.metrics.calculate_combat_rating() != ExperienceLevel.ELITE:
                requirements.append("Need Elite combat rating")
                
        elif role == ShipRole.MEDICAL:
            med_progress = self.career_tracks.get(CareerPath.MEDICAL)
            if not med_progress or med_progress.level != ExperienceLevel.VETERAN:
                requirements.append("Need Veteran medical rating")
                
        # Size-based requirements
        size = ship_data.get('size', 'SMALL')
        if size == 'CAPITAL':
            command_time = sum(
                1 for assign in self.station_assignments
                if assign.role == StationRole.CAPTAIN
            )
            if command_time < 100:
                requirements.append("Need 100 hours as Captain")
                
        # Clearance check for military ships
        is_military = ship_data.get('military', False)
        if is_military and self.security_clearance != "Top Secret":
            requirements.append("Need Top Secret clearance")
            
        return len(requirements) == 0, requirements
            
    def get_primary_station(self) -> Optional[StationAssignment]:
        """Get member's primary station assignment."""
        primary = [a for a in self.station_assignments if a.is_primary]
        return primary[0] if primary else None
            
    def add_mission_completion(
        self,
        mission_id: str,
        role: StationRole,
        ship: str,
        success: bool,
        duration: float
    ):
        """Record mission completion."""
        self.total_missions += 1
        self.mission_history.append(mission_id)
        
        # Update success rate
        total_success = self.mission_success_rate * (self.total_missions - 1)
        total_success += 1 if success else 0
        self.mission_success_rate = total_success / self.total_missions
        
        # Add flight hours
        relevant_cert = next(
            (c for c in self.ship_certifications if c.ship_type == ship),
            None
        )
        if relevant_cert:
            relevant_cert.flight_hours += duration
            
        # Update metrics based on role
        if role == StationRole.WEAPONS:
            self.metrics.combat_missions += 1
        elif role == StationRole.CARGO:
            self.metrics.trade_missions += 1
            
    def get_available_ships(self) -> List[str]:
        """Get list of ships member is certified to operate."""
        return [
            cert.ship_type for cert in self.ship_certifications
            if not cert.revoked and (
                not cert.expires or cert.expires > datetime.now()
            )
        ]
        
    def get_career_summary(self) -> Dict[str, Any]:
        """Get summary of career progress."""
        return {
            path.value: {
                'level': progress.level.value,
                'exp': progress.experience_points,
                'missions': progress.missions_completed,
                'specializations': progress.specializations
            }
            for path, progress in self.career_tracks.items()
        }
        
    def get_commendation_history(self) -> List[Dict[str, str]]:
        """Get formatted commendation history."""
        return [
            {
                'type': comm.split(' - ')[0],
                'reason': comm.split(' - ')[1],
                'date': comm.split(' - ')[2]
            }
            for comm in self.commendations
        ]
        
    def to_embed(self, detailed: bool = False) -> discord.Embed:
        """Convert profile to Discord embed."""
        embed = discord.Embed(
            title=f"Star Citizen Profile: {self.handle}",
            description=f"Service ID: {self.service_id}",
            color=discord.Color.blue()
        )
        
        # Basic Info
        embed.add_field(
            name="Basic Information",
            value=(
                f"**Division:** {self.division}\n"
                f"**Rank:** {self.rank}\n"
                f"**Clearance:** {self.security_clearance}\n"
                f"**Join Date:** {self.join_date.strftime('%Y-%m-%d')}\n"
                f"**Status:** {'Active' if self.active_status else 'Inactive'}"
            ),
            inline=False
        )
        
        # Current Assignment
        primary = self.get_primary_station()
        if primary:
            embed.add_field(
                name="Primary Assignment",
                value=(
                    f"**Ship:** {primary.ship_name}\n"
                    f"**Role:** {primary.role.value}\n"
                    f"**Since:** {primary.assigned_date.strftime('%Y-%m-%d')}"
                ),
                inline=False
            )
            
        # Experience Summary
        exp_level = self.calculate_experience_level()
        embed.add_field(
            name="Experience",
            value=(
                f"**Level:** {exp_level.value}\n"
                f"**Missions:** {self.total_missions}\n"
                f"**Success Rate:** {self.mission_success_rate*100:.1f}%"
            ),
            inline=True
        )
        
        if detailed:
            # Certifications
            if self.ship_certifications:
                cert_text = "\n".join(
                    f"• {cert.ship_type} ({cert.cert_level})"
                    for cert in self.ship_certifications
                    if not cert.revoked
                )
                embed.add_field(
                    name="Ship Certifications",
                    value=cert_text,
                    inline=False
                )
                
            # Career Progress
            career_summary = self.get_career_summary()
            for career, data in career_summary.items():
                embed.add_field(
                    name=f"{career} Progress",
                    value=(
                        f"**Level:** {data['level']}\n"
                        f"**Missions:** {data['missions']}\n"
                        f"**Specializations:** {', '.join(data['specializations'])}"
                    ),
                    inline=True
                )
                
        return embed

@dataclass
class SCMissionRole:
    """Role assignment for a Star Citizen mission."""
    member_id: int
    ship_name: str
    station: StationRole
    report_to: Optional[int] = None  # Discord ID of superior
    backup_for: Optional[int] = None  # Discord ID of primary
    special_instructions: str = ""
    
    def can_assign(self, profile: SCProfile) -> Tuple[bool, str]:
        """Check if member can be assigned this role."""
        # Verify ship certification
        if self.ship_name not in profile.get_available_ships():
            return False, "Not certified for this ship"
            
        # Check station requirements
        if self.station == StationRole.CAPTAIN:
            command_exp = sum(
                1 for r in profile.station_assignments
                if r.role == StationRole.CAPTAIN
            )
            if command_exp < 5:
                return False, "Insufficient command experience"
                
        elif self.station == StationRole.XO:
            if StationRole.CAPTAIN not in profile.preferred_roles:
                return False, "Must be trained for command"
                
        return True, "Eligible for assignment"

