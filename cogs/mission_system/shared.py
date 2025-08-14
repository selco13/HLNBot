# cogs/mission_system/shared.py

import discord
from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

class MissionType(Enum):
    """Types of missions available."""
    COMBAT = "Combat Operation"
    MINING = "Mining Operation"
    TRADING = "Trading Run"
    EXPLORATION = "Exploration Mission"
    ESCORT = "Escort Mission"
    SALVAGE = "Salvage Operation"
    MEDICAL = "Medical Operation"
    LOGISTICS = "Logistics Run"
    FLEET = "Fleet Operation"
    CUSTOM = "Custom Operation"

    def __str__(self):
        return self.value

class MissionStatus(Enum):
    """Mission states."""
    PLANNING = "Planning"
    RECRUITING = "Recruiting"
    READY = "Ready"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    DELAYED = "Delayed"

    def __str__(self):
        return self.value

class AARType(Enum):
    """Types of After Action Reports."""
    COMBAT = "Combat Operation"
    MINING = "Mining Operation"
    TRADING = "Trading Run"
    EXPLORATION = "Exploration Mission"
    ESCORT = "Escort Mission"
    SALVAGE = "Salvage Operation"
    MEDICAL = "Medical Operation"
    LOGISTICS = "Logistics Run"
    FLEET = "Fleet Operation"
    TRAINING = "Training Exercise"
    OTHER = "Other Operation"

    def __str__(self):
        return self.value

class AAROutcome(Enum):
    """Possible mission outcomes."""
    SUCCESS = "Success"
    PARTIAL = "Partial Success"
    FAILURE = "Failure"
    CANCELLED = "Cancelled"
    INCOMPLETE = "Incomplete"

    def __str__(self):
        return self.value

class AARMedal(Enum):
    """Types of medals that can be awarded."""
    COMBAT = "Combat Excellence Medal"
    LEADERSHIP = "Leadership Medal"
    SERVICE = "Meritorious Service Medal"
    VALOR = "Medal of Valor"
    ACHIEVEMENT = "Achievement Medal"
    TEAMWORK = "Teamwork Medal"
    TECHNICAL = "Technical Excellence Medal"
    EXPLORATION = "Explorer's Medal"
    DEDICATION = "Dedication Medal"

    def __str__(self):
        return self.value
        
class MissionDifficulty(Enum):
    """Mission difficulty levels."""
    EASY = "Easy"
    NORMAL = "Normal"
    HARD = "Hard"
    EXPERT = "Expert"
    TRAINING = "Training"
    BEGINNER = "Beginner-Friendly"
    ADVANCED = "Advanced"
    ELITE = "Elite"
    CASUAL = "Casual"

    def __str__(self):
        return self.value

@dataclass
class Participant:
    """Represents a mission participant (used by both Missions & AARs)."""
    user_id: int
    ship_name: str
    role: str
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Fields below are extra for AAR usage, but do not harm Missions usage
    contribution: Optional[str] = None
    medals: List[AARMedal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'user_id': self.user_id,
            'ship_name': self.ship_name,
            'role': self.role,
            'joined_at': self.joined_at.isoformat(),
            'contribution': self.contribution,
            'medals': [medal.name for medal in self.medals]
        }

    @classmethod
    def from_dict(cls, data: Any) -> 'Participant':
        """
        Create from dictionary data. If data is a list/tuple
        (legacy format), handle that gracefully.
        """
        if isinstance(data, (list, tuple)):
            # Old format: e.g., [user_id, ship_name, role]
            user_id = data[0] if isinstance(data[0], int) else int(data[0])
            return cls(
                user_id=user_id,
                ship_name=data[1],
                role=data[2]
            )

        # If data is a dict, parse carefully
        data = data.copy()
        if 'joined_at' in data and isinstance(data['joined_at'], str):
            data['joined_at'] = datetime.fromisoformat(data['joined_at'])
        if 'medals' in data:
            data['medals'] = [AARMedal[m] for m in data['medals']]
        return cls(**data)

class MissionSystemUtilities:
    """Shared utilities for the mission system (used by Missions & AARs)."""

    @staticmethod
    def get_status_color(status: MissionStatus) -> discord.Color:
        """Get an appropriate color based on mission status (requires discord)."""
        colors = {
            MissionStatus.PLANNING: discord.Color.blue(),
            MissionStatus.RECRUITING: discord.Color.green(),
            MissionStatus.READY: discord.Color.gold(),
            MissionStatus.IN_PROGRESS: discord.Color.purple(),
            MissionStatus.COMPLETED: discord.Color.dark_green(),
            MissionStatus.CANCELLED: discord.Color.red(),
            MissionStatus.DELAYED: discord.Color.orange()
        }
        return colors.get(status, discord.Color.default())

    @staticmethod
    def parse_objectives(description: str) -> List[str]:
        """Extract objectives from a multi-line description."""
        objectives = []
        if description:
            lines = description.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Identify lines that begin with bullet or digit
                if line.startswith('•') or line.startswith('-') or line[0].isdigit():
                    objectives.append(line.lstrip('•-123456789. ').strip())
        return objectives

    @staticmethod
    def format_time_until(target_time: datetime) -> str:
        """Return a string representing how long until target_time."""
        now = datetime.now(timezone.utc)
        delta = target_time - now

        if delta.total_seconds() <= 0:
            return "In Progress"

        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "Now"

