from enum import Enum
from typing import Dict, Any
from .shared import MissionType

class MissionDifficulty(Enum):
    EASY = "Easy"
    NORMAL = "Normal"
    HARD = "Hard"
    EXPERT = "Expert"
    TRAINING = "Training"

MISSION_TEMPLATES = {
    'combat_patrol': {
        'name': "Combat Patrol",
        'type': MissionType.COMBAT,
        'description': (
            "Standard combat patrol mission\n"
            "Objectives:\n"
            "• Patrol designated sector\n"
            "• Respond to distress calls\n"
            "• Eliminate hostile targets"
        ),
        'min_participants': 2,
        'max_participants': 4,
        'required_ships': ["Gladius", "Vanguard"],
        'duration': 60,
        'difficulty': MissionDifficulty.NORMAL,
        'tags': ["combat", "patrol", "security"]
    },
    'mining_operation': {
        'name': "Mining Operation",
        'type': MissionType.MINING,
        'description': (
            "Organized mining operation\n"
            "Objectives:\n"
            "• Extract valuable minerals\n"
            "• Maintain safety protocols\n"
            "• Transport resources"
        ),
        'min_participants': 3,
        'max_participants': 6,
        'required_ships': ["MISC Prospector", "Argo MOLE"],
        'duration': 120,
        'difficulty': MissionDifficulty.NORMAL,
        'tags': ["mining", "industrial", "resources"]
    },
    'trade_convoy': {
        'name': "Trade Convoy",
        'type': MissionType.TRADING,
        'description': (
            "Protected trade convoy operation\n"
            "Objectives:\n"
            "• Transport cargo safely\n"
            "• Maintain convoy formation\n"
            "• Protect cargo ships"
        ),
        'min_participants': 4,
        'max_participants': 8,
        'required_ships': ["Caterpillar", "Freelancer", "Cutlass Black"],
        'duration': 90,
        'difficulty': MissionDifficulty.NORMAL,
        'tags': ["trading", "convoy", "escort"]
    }
}

# Add more templates as needed

def get_template(template_id: str) -> Dict[str, Any]:
    """Get a mission template by ID."""
    return MISSION_TEMPLATES.get(template_id, {})

def list_templates() -> Dict[str, Dict[str, Any]]:
    """Get all available templates."""
    return MISSION_TEMPLATES