# cogs/constants.py

# Core fleet component codes
FLEET_COMPONENTS = {
    'Navy Fleet': 'NF',  # Combat & Security
    'Marine Expeditionary Force': 'MEF',  # Ground Combat & Boarding
    'Industrial & Logistics Wing': 'ILW',  # Mining, Salvage, Hauling, etc.
    'Support & Medical Fleet': 'SMF',  # Medical, technical support, repairs
    'Exploration & Intelligence Wing': 'EIW',  # Scouting, intelligence, charting
    'Fleet Command': 'FC',  # High Command & Admiralty
    'Command Staff': 'HQ',  # Command positions - no special progression
    'Non-Fleet': 'NFL',  # For those not in the fleet structure
    'Ambassador': 'AMB',  # Special diplomatic position
    'Associate': 'AS',  # Temporary or affiliate members
}

# For backward compatibility - mapping old divisions to new fleet components
DIVISION_CODES = {
    'Tactical': 'NF',  # Maps to Navy Fleet
    'Operations': 'ILW',  # Maps to Industrial & Logistics Wing
    'Support': 'SMF',  # Maps to Support & Medical Fleet
    'Command Staff': 'HQ',  # Same as before
    'HQ': 'FC',  # Maps to Fleet Command
    'Non-Division': 'NF',  # Maps to Non-Fleet
    'Ambassador': 'AMB',  # Same as before
    'Associate': 'AS',  # Same as before
}

# Mapping old divisions to new fleet wings (for transition)
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

# Standard Military Ranks - Unified progression path
RANKS = [
    ('Admiral', 'ADM'),
    ('Vice Admiral', 'VADM'),
    ('Rear Admiral', 'RADM'),
    ('Commodore', 'CDRE'),
    ('Fleet Captain', 'FCPT'),
    ('Captain', 'CAPT'),
    ('Commander', 'CDR'),
    ('Lieutenant Commander', 'LCDR'),
    ('Lieutenant', 'LT'),
    ('Lieutenant Junior Grade', 'LTJG'),
    ('Ensign', 'ENS'),
    ('Chief Petty Officer', 'CPO'),
    ('Petty Officer 1st Class', 'PO1'),
    ('Petty Officer 2nd Class', 'PO2'),
    ('Petty Officer 3rd Class', 'PO3'),
    ('Master Crewman', 'MCWM'),
    ('Senior Crewman', 'SCWM'),
    ('Crewman', 'CWM'),
    ('Crewman Apprentice', 'CWA'),
    ('Crewman Recruit', 'CWR'),
    ('Ambassador', 'AMB'),
    ('Associate', 'AS'),
]

RANK_CODE_MAPPING = {
    rank[0].lower(): str(idx + 1).zfill(2)
    for idx, rank in enumerate(RANKS)
}

RANK_NUMBERS = {name: idx + 1 for idx, (name, _) in enumerate(RANKS)}
RANK_ABBREVIATIONS = {name: abbrev for name, abbrev in RANKS}
STANDARD_RANK_ABBREVIATIONS = {name.lower(): abbrev for name, abbrev in RANKS}

MEMBER_ROLE_THRESHOLD = 14  # Ranks 1 through 14 are above Crewman

# Ranks required for administrative actions
REQUIRED_STANDARD_RANKS = [
    'Captain',
    'Commodore',
    'Rear Admiral',
    'Vice Admiral',
    'Admiral'
]

# High ranks that can override promotion requirements
HIGH_RANKS = [
    'Rear Admiral',
    'Vice Admiral',
    'Admiral'
]

# Role Specializations - Based exactly on RevisedStructure.txt
ROLE_SPECIALIZATIONS = {
    # Navy Fleet - The primary military progression path
    'Navy Fleet': {
        'Command': [
            # General ranks until MCWM - Unified starting experience
            ('Crewman Recruit', 'Crewman Recruit', 'CWR', 'CWR'),
            ('Crewman Apprentice', 'Crewman Apprentice', 'CWA', 'CWA'),
            ('Crewman', 'Crewman', 'CWM', 'CWM'),
            ('Senior Crewman', 'Senior Crewman', 'SCWM', 'SCWM'),
            ('Master Crewman', 'Master Crewman', 'MCWM', 'MCWM'),
            # Specialization begins
            ('Tactical Officer', 'Petty Officer 3rd Class', 'TO', 'PO3'),
            ('Senior Tactical Officer', 'Petty Officer 2nd Class', 'STO', 'PO2'),
            ('Bridge Officer', 'Petty Officer 1st Class', 'BO', 'PO1'),
            ('Assistant Chief Tactical Officer', 'Chief Petty Officer', 'ACTO', 'CPO'),
            ('Ensign', 'Ensign', 'ENS', 'ENS'),
            ('Lieutenant Junior Grade', 'Lieutenant Junior Grade', 'LTJG', 'LTJG'),
            ('Lieutenant', 'Lieutenant', 'LT', 'LT'),
            ('Lieutenant Commander', 'Lieutenant Commander', 'LCDR', 'LCDR'),
            ('Commander', 'Commander', 'CDR', 'CDR'),
            ('Captain', 'Captain', 'CAPT', 'CAPT'),
            ('Fleet Captain', 'Fleet Captain', 'FCPT', 'FCPT'),
            ('Commodore', 'Commodore', 'CDRE', 'CDRE')
        ],
        'Flight Operations': [
            # General ranks until MCWM - Unified starting experience
            ('Crewman Recruit', 'Crewman Recruit', 'CWR', 'CWR'),
            ('Crewman Apprentice', 'Crewman Apprentice', 'CWA', 'CWA'),
            ('Crewman', 'Crewman', 'CWM', 'CWM'),
            ('Senior Crewman', 'Senior Crewman', 'SCWM', 'SCWM'),
            ('Master Crewman', 'Master Crewman', 'MCWM', 'MCWM'),
            # Specialization begins
            ('Combat Pilot Recruit', 'Petty Officer 3rd Class', 'CPR', 'PO3'),
            ('Combat Pilot 1', 'Petty Officer 2nd Class', 'CP1', 'PO2'),
            ('Combat Pilot 2', 'Petty Officer 1st Class', 'CP2', 'PO1'),
            ('Combat Pilot 3', 'Chief Petty Officer', 'CP3', 'CPO'),
            ('Combat Flight Lead 1', 'Ensign', 'CFL1', 'ENS'),
            ('Combat Flight Lead 2', 'Lieutenant Junior Grade', 'CFL2', 'LTJG'),
            ('Gunship Operations', 'Lieutenant', 'GSO', 'LT'),
            ('Wing Commander', 'Lieutenant Commander', 'WC', 'LCDR')
            # Capped at Lieutenant Commander - Must transition to Command track for higher ranks
        ],
        'Naval Strategic Operations': [
            # General ranks until MCWM - Unified starting experience
            ('Crewman Recruit', 'Crewman Recruit', 'CWR', 'CWR'),
            ('Crewman Apprentice', 'Crewman Apprentice', 'CWA', 'CWA'),
            ('Crewman', 'Crewman', 'CWM', 'CWM'),
            ('Senior Crewman', 'Senior Crewman', 'SCWM', 'SCWM'),
            ('Master Crewman', 'Master Crewman', 'MCWM', 'MCWM'),
            # Specialization begins
            ('Ensign', 'Ship Junior Officer', 'SJO', 'ENS'),
            ('Lieutenant Junior Grade', 'Ship Officer', 'SO', 'LTJG'),
            ('Lieutenant', 'Ship Senior Officer', 'SSO', 'LT'),
            ('Lieutenant Commander', 'Ship Department Head', 'SDH', 'LCDR'),
            ('Commander', 'Commander', 'CDR', 'CDR'),
            ('Captain', 'Captain', 'CAPT', 'CAPT'),
            ('Rear Admiral', 'Rear Admiral', 'RADM', 'RADM')
        ]
    },
    
    # Marine Expeditionary Force - Secondary military progression path
    'Marine Expeditionary Force': {
        'Ground Forces': [
            # General ranks until MCWM - Unified starting experience
            ('Crewman Recruit', 'Crewman Recruit', 'CWR', 'CWR'),
            ('Crewman Apprentice', 'Crewman Apprentice', 'CWA', 'CWA'),
            ('Crewman', 'Crewman', 'CWM', 'CWM'),
            ('Senior Crewman', 'Senior Crewman', 'SCWM', 'SCWM'),
            ('Master Crewman', 'Master Crewman', 'MCWM', 'MCWM'),
            # Specialization begins with Marine ranks
            ('Corporal', 'Petty Officer 3rd Class', 'CPL', 'PO3'),
            ('Sergeant', 'Petty Officer 2nd Class', 'SGT', 'PO2'),
            ('Staff Sergeant', 'Petty Officer 1st Class', 'SSGT', 'PO1'),
            ('Gunnery Sergeant', 'Chief Petty Officer', 'GSGT', 'CPO'),
            ('Marine Ensign', 'Ensign', 'MENS', 'ENS'),
            ('Marine Lieutenant', 'Lieutenant Junior Grade', 'MLT', 'LTJG'),
            ('Marine Captain', 'Lieutenant', 'MCPT', 'LT'),
            ('Major', 'Lieutenant Commander', 'MAJ', 'LCDR'),
            ('Lieutenant Colonel', 'Commander', 'LTCOL', 'CDR'),
            ('Colonel', 'Captain', 'COL', 'CAPT'),
            ('Force Colonel', 'Fleet Captain', 'FCOL', 'FCPT'),
            ('Brigadier', 'Commodore', 'BRIG', 'CDRE')
        ]
    },
    
    # Industrial & Logistics Wing - Secondary military progression path
    'Industrial & Logistics Wing': {
        'Naval Operations': [
            # General ranks until MCWM - Unified starting experience
            ('Crewman Recruit', 'Crewman Recruit', 'CWR', 'CWR'),
            ('Crewman Apprentice', 'Crewman Apprentice', 'CWA', 'CWA'),
            ('Crewman', 'Crewman', 'CWM', 'CWM'),
            ('Senior Crewman', 'Senior Crewman', 'SCWM', 'SCWM'),
            ('Master Crewman', 'Master Crewman', 'MCWM', 'MCWM'),
            # Specialization begins
            ('Ops Specialist', 'Petty Officer 3rd Class', 'OS', 'PO3'),
            ('Senior Ops Specialist', 'Petty Officer 2nd Class', 'SOS', 'PO2'),
            ('Operations Officer', 'Petty Officer 1st Class', 'OO', 'PO1'),
            ('Operations Chief', 'Chief Petty Officer', 'OC', 'CPO'),
            ('Ops Ensign', 'Ensign', 'OE', 'ENS'),
            ('Ops Lieutenant', 'Lieutenant Junior Grade', 'OL', 'LTJG'),
            ('Ops Division Officer', 'Lieutenant', 'ODO', 'LT'),
            ('Chief of Operations', 'Lieutenant Commander', 'COO', 'LCDR')
            # Capped at Lieutenant Commander - Must transition to Command track for higher ranks
        ],
        'Support Operations': [
            # General ranks until MCWM - Unified starting experience
            ('Crewman Recruit', 'Crewman Recruit', 'CWR', 'CWR'),
            ('Crewman Apprentice', 'Crewman Apprentice', 'CWA', 'CWA'),
            ('Crewman', 'Crewman', 'CWM', 'CWM'),
            ('Senior Crewman', 'Senior Crewman', 'SCWM', 'SCWM'),
            ('Master Crewman', 'Master Crewman', 'MCWM', 'MCWM'),
            # Specialization begins
            ('Ops Specialist', 'Petty Officer 3rd Class', 'OS', 'PO3'),
            ('Senior Ops Specialist', 'Petty Officer 2nd Class', 'SOS', 'PO2'),
            ('Operations Officer', 'Petty Officer 1st Class', 'OO', 'PO1'),
            ('Operations Chief', 'Chief Petty Officer', 'OC', 'CPO')
            # Capped at Chief Petty Officer - Must transition to Command track for higher ranks
        ]
    },
    
    # Fleet Command - Command structure
    'Fleet Command': {
        'Command': [
            # High command uses standard ranks
            ('Admiral', 'Admiral', 'ADM', 'ADM'),
            ('Vice Admiral', 'Vice Admiral', 'VADM', 'VADM'),
            ('Rear Admiral', 'Rear Admiral', 'RADM', 'RADM'),
            ('Commodore', 'Commodore', 'CDRE', 'CDRE'),
            ('Fleet Captain', 'Fleet Captain', 'FCPT', 'FCPT'),
            ('Captain', 'Captain', 'CAPT', 'CAPT')
        ]
    },
    
    # Basic placeholders for other wings (not fully specified in RevisedStructure.txt)
    'Support & Medical Fleet': {},
    'Exploration & Intelligence Wing': {},
    'Non-Fleet': {},
    'Ambassador': {},
    'Associate': {}
}

# For backward compatibility - just reference the new structure
DIVISION_RANKS = ROLE_SPECIALIZATIONS

# Mapping of fleet wings to visual icons
FLEET_WING_ICONS = {
    "Navy Fleet": "[NF]",
    "Marine Expeditionary Force": "[MEF]",
    "Industrial & Logistics Wing": "[ILW]",
    "Support & Medical Fleet": "[SMF]",
    "Exploration & Intelligence Wing": "[EIW]",
    "Fleet Command": "[FC]",
    "Command Staff": "[HQ]",
    "Non-Fleet": "[NF]",
    "Ambassador": "[AMB]",
    "Associate": "[AS]"
}

# Core certification categories
CERTIFICATION_CATEGORIES = [
    "combat",       # Combat operations
    "technical",    # Engineering and technical skills
    "medical",      # Medical skills
    "operations",   # Ship operations
    "science",      # Scientific knowledge
    "command",      # Command and leadership
    "comms",        # Communications
    "exploration"   # Added exploration category
]

# Time in grade requirements - simplified
TIME_IN_GRADE = {
    'Crewman Recruit': {'days': 7, 'missions': 2},
    'Crewman Apprentice': {'days': 10, 'missions': 3},
    'Crewman': {'days': 14, 'missions': 4},
    'Senior Crewman': {'days': 21, 'missions': 5},
    'Master Crewman': {'days': 28, 'missions': 6},
    'Petty Officer 3rd Class': {'days': 35, 'missions': 7},
    'Petty Officer 2nd Class': {'days': 45, 'missions': 9},
    'Petty Officer 1st Class': {'days': 60, 'missions': 11},
    'Chief Petty Officer': {'days': 90, 'missions': 13},
    'Ensign': {'days': 120, 'missions': 15},
    'Lieutenant Junior Grade': {'days': 150, 'missions': 20},
    'Lieutenant': {'days': 180, 'missions': 25},
    'Lieutenant Commander': {'days': 210, 'missions': 30},
    'Commander': {'days': 240, 'missions': 35},
    'Captain': {'days': 270, 'missions': 40},
    'Fleet Captain': {'days': 300, 'missions': 45},
    'Commodore': {'days': 330, 'missions': 50},
    'Rear Admiral': {'days': 360, 'missions': 55},
    'Vice Admiral': {'days': 390, 'missions': 60},
    'Admiral': {'days': 420, 'missions': 65}
}

TOKEN_EXPIRY_HOURS = 24

# Basic certifications for all personnel
CERTIFICATIONS = {
    # Basic Combat Certifications
    "basic_combat": {
        "name": "Basic Combat Training", 
        "category": "combat", 
        "level": "basic",
        "color": "red",
        "fleet_components": ["Navy Fleet", "Marine Expeditionary Force"]
    },
    "weapons_qualification": {
        "name": "Weapons Qualification", 
        "category": "combat", 
        "level": "basic",
        "color": "red",
        "fleet_components": ["Navy Fleet", "Marine Expeditionary Force"]
    },
    "basic_flight": {
        "name": "Basic Flight", 
        "category": "combat", 
        "level": "basic",
        "color": "red",
        "fleet_components": ["Navy Fleet"]
    },
    
    # Advanced Combat Certifications
    "advanced_combat": {
        "name": "Advanced Combat Training", 
        "category": "combat", 
        "level": "advanced",
        "color": "blue",
        "prerequisites": ["basic_combat"],
        "fleet_components": ["Navy Fleet", "Marine Expeditionary Force"]
    },
    "fighter_combat": {
        "name": "Fighter Combat", 
        "category": "combat", 
        "level": "advanced",
        "color": "blue",
        "prerequisites": ["basic_flight"],
        "fleet_components": ["Navy Fleet"]
    },
    "tactical_systems": {
        "name": "Tactical Systems", 
        "category": "combat", 
        "level": "advanced",
        "color": "blue",
        "prerequisites": ["weapons_qualification"],
        "fleet_components": ["Navy Fleet"]
    },
    
    # Basic Technical Certifications
    "basic_engineering": {
        "name": "Basic Engineering", 
        "category": "technical", 
        "level": "basic",
        "color": "gold",
        "fleet_components": ["Industrial & Logistics Wing", "Support & Medical Fleet"]
    },
    "systems_maintenance": {
        "name": "Systems Maintenance", 
        "category": "technical", 
        "level": "basic",
        "color": "gold",
        "fleet_components": ["Industrial & Logistics Wing", "Support & Medical Fleet"]
    },
    "resource_extraction": {
        "name": "Resource Extraction", 
        "category": "technical", 
        "level": "basic",
        "color": "gold",
        "fleet_components": ["Industrial & Logistics Wing"]
    },
    
    # Advanced Technical Certifications
    "advanced_engineering": {
        "name": "Advanced Engineering", 
        "category": "technical", 
        "level": "advanced",
        "color": "orange",
        "prerequisites": ["basic_engineering"],
        "fleet_components": ["Industrial & Logistics Wing", "Support & Medical Fleet"]
    },
    "propulsion_systems": {
        "name": "Propulsion Systems", 
        "category": "technical", 
        "level": "advanced",
        "color": "orange",
        "prerequisites": ["basic_engineering"],
        "fleet_components": ["Industrial & Logistics Wing", "Support & Medical Fleet"]
    },
    "advanced_resource_ops": {
        "name": "Advanced Resource Operations", 
        "category": "technical", 
        "level": "advanced",
        "color": "orange",
        "prerequisites": ["resource_extraction"],
        "fleet_components": ["Industrial & Logistics Wing"]
    },
    
    # Medical Certifications
    "basic_medical": {
        "name": "Basic Medical Training", 
        "category": "medical", 
        "level": "basic",
        "color": "green",
        "fleet_components": ["Support & Medical Fleet"]
    },
    "field_medicine": {
        "name": "Field Medicine", 
        "category": "medical", 
        "level": "basic",
        "color": "green",
        "fleet_components": ["Support & Medical Fleet", "Marine Expeditionary Force"]
    },
    "advanced_medical": {
        "name": "Advanced Medical Training", 
        "category": "medical", 
        "level": "advanced",
        "color": "teal",
        "prerequisites": ["basic_medical"],
        "fleet_components": ["Support & Medical Fleet"]
    },
    "trauma_medicine": {
        "name": "Trauma Medicine", 
        "category": "medical", 
        "level": "advanced",
        "color": "teal",
        "prerequisites": ["field_medicine"],
        "fleet_components": ["Support & Medical Fleet", "Marine Expeditionary Force"]
    },
    
    # Ship Operations Certifications
    "basic_ship_operations": {
        "name": "Basic Ship Operations", 
        "category": "operations", 
        "level": "basic",
        "color": "purple",
        "fleet_components": ["Navy Fleet", "Industrial & Logistics Wing"]
    },
    "helm_control": {
        "name": "Helm Control", 
        "category": "operations", 
        "level": "basic",
        "color": "purple",
        "fleet_components": ["Navy Fleet"]
    },
    "navigation": {
        "name": "Navigation", 
        "category": "operations", 
        "level": "basic",
        "color": "purple",
        "fleet_components": ["Navy Fleet", "Exploration & Intelligence Wing"]
    },
    "ship_systems": {
        "name": "Ship Systems Operation", 
        "category": "operations", 
        "level": "advanced",
        "color": "indigo",
        "prerequisites": ["basic_ship_operations"],
        "fleet_components": ["Navy Fleet", "Industrial & Logistics Wing"]
    },
    "advanced_helm": {
        "name": "Advanced Helm Operations", 
        "category": "operations", 
        "level": "advanced",
        "color": "indigo",
        "prerequisites": ["helm_control"],
        "fleet_components": ["Navy Fleet"]
    },
    
    # Science & Exploration Certifications
    "basic_science": {
        "name": "Basic Science Training", 
        "category": "science", 
        "level": "basic",
        "color": "cyan",
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    "stellar_cartography": {
        "name": "Stellar Cartography", 
        "category": "science", 
        "level": "basic",
        "color": "cyan",
        "fleet_components": ["Exploration & Intelligence Wing", "Navy Fleet"]
    },
    "xenoscience": {
        "name": "Xenoscience", 
        "category": "science", 
        "level": "advanced",
        "color": "teal",
        "prerequisites": ["basic_science"],
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    "advanced_astronomy": {
        "name": "Advanced Astronomy", 
        "category": "science", 
        "level": "advanced",
        "color": "teal",
        "prerequisites": ["stellar_cartography"],
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    
    # Exploration Certifications
    "basic_exploration": {
        "name": "Basic Exploration", 
        "category": "exploration", 
        "level": "basic",
        "color": "cyan",
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    "jump_point_charting": {
        "name": "Jump Point Charting", 
        "category": "exploration", 
        "level": "basic",
        "color": "cyan",
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    "advanced_exploration": {
        "name": "Advanced Exploration", 
        "category": "exploration", 
        "level": "advanced",
        "color": "teal",
        "prerequisites": ["basic_exploration"],
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    "frontier_reconnaissance": {
        "name": "Frontier Reconnaissance", 
        "category": "exploration", 
        "level": "advanced",
        "color": "teal",
        "prerequisites": ["jump_point_charting"],
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    
    # Command Certifications
    "basic_leadership": {
        "name": "Basic Leadership", 
        "category": "command", 
        "level": "basic",
        "color": "yellow",
        "fleet_components": ["Navy Fleet", "Marine Expeditionary Force", "Industrial & Logistics Wing", "Support & Medical Fleet", "Exploration & Intelligence Wing"]
    },
    "tactical_command": {
        "name": "Tactical Command", 
        "category": "command", 
        "level": "advanced",
        "color": "gold",
        "prerequisites": ["basic_leadership"],
        "fleet_components": ["Navy Fleet", "Marine Expeditionary Force"]
    },
    "bridge_command": {
        "name": "Bridge Command", 
        "category": "command", 
        "level": "advanced",
        "color": "gold",
        "prerequisites": ["basic_leadership", "ship_systems"],
        "fleet_components": ["Navy Fleet"]
    },
    "captaincy": {
        "name": "Captaincy Certification", 
        "category": "command", 
        "level": "advanced",
        "color": "gold",
        "prerequisites": ["bridge_command"],
        "fleet_components": ["Navy Fleet"]
    },
    
    # Communications Certifications
    "basic_comms": {
        "name": "Basic Communications", 
        "category": "comms", 
        "level": "basic",
        "color": "blue",
        "fleet_components": ["Navy Fleet", "Exploration & Intelligence Wing"]
    },
    "fleet_communications": {
        "name": "Fleet Communications", 
        "category": "comms", 
        "level": "advanced",
        "color": "purple",
        "prerequisites": ["basic_comms"],
        "fleet_components": ["Navy Fleet", "Exploration & Intelligence Wing"]
    },
    "signals_intelligence": {
        "name": "Signals Intelligence", 
        "category": "comms", 
        "level": "advanced",
        "color": "purple",
        "prerequisites": ["basic_comms"],
        "fleet_components": ["Exploration & Intelligence Wing"]
    },
    "signals_operations": {
        "name": "Signals Operations", 
        "category": "comms", 
        "level": "advanced",
        "color": "purple",
        "prerequisites": ["signals_intelligence"],
        "fleet_components": ["Exploration & Intelligence Wing"]
    }
}

# Required certifications for various roles
CERTIFICATION_REQUIREMENTS = {
    "ship_command": ["helm_control", "navigation", "basic_leadership", "bridge_command", "captaincy"],
    "pilot": ["basic_flight", "basic_comms"],
    "tactical_officer": ["tactical_systems", "weapons_qualification"],
    "marine": ["basic_combat", "weapons_qualification"],
    "engineer": ["basic_engineering", "systems_maintenance"],
    "medic": ["basic_medical", "field_medicine"],
    "science_officer": ["basic_science", "stellar_cartography"],
    "intelligence_officer": ["basic_comms", "signals_intelligence"],
    "resource_specialist": ["resource_extraction"],
    "communications_officer": ["basic_comms", "fleet_communications"],
    "explorer": ["basic_exploration", "jump_point_charting"],
    "signals_specialist": ["signals_operations", "signals_intelligence"]
}

# Rank advancement requirements for military progression path
MILITARY_RANK_REQUIREMENTS = {
    "Captain": {
        "certifications": ["captaincy", "bridge_command", "tactical_command"],
        "service_time_days": 180,
        "missions": 20
    },
    "Fleet Captain": {
        "certifications": ["captaincy", "bridge_command", "tactical_command"],
        "service_time_days": 240,
        "missions": 30,
        "command_time_days": 60  # Time served as Captain
    },
    "Commodore": {
        "certifications": ["captaincy", "bridge_command", "tactical_command"],
        "service_time_days": 300, 
        "missions": 40,
        "command_time_days": 120  # Time served as Captain or higher
    }
}

# Ship certification requirements
SHIP_CERTIFICATIONS = {
    'SMALL_CRAFT': {
        'name': 'Small Craft Certification',
        'description': 'Qualified to pilot small utility craft and shuttles',
        'prerequisite_hours': 5,
        'required_missions': 3
    },
    'LIGHT_FIGHTER': {
        'name': 'Light Fighter Certification',
        'description': 'Qualified to pilot light fighters',
        'prerequisite_hours': 10,
        'required_missions': 5,
        'prerequisites': ['SMALL_CRAFT']
    },
    'MEDIUM_FIGHTER': {
        'name': 'Medium Fighter Certification',
        'description': 'Qualified to pilot medium fighters',
        'prerequisite_hours': 20,
        'required_missions': 10,
        'prerequisites': ['LIGHT_FIGHTER']
    },
    'HEAVY_FIGHTER': {
        'name': 'Heavy Fighter Certification', 
        'description': 'Qualified to pilot heavy fighters',
        'prerequisite_hours': 30,
        'required_missions': 15,
        'prerequisites': ['MEDIUM_FIGHTER']
    },
    'SMALL_VESSEL': {
        'name': 'Small Vessel Certification',
        'description': 'Qualified to captain ships up to corvette size',
        'prerequisite_hours': 15,
        'required_missions': 5,
        'prerequisites': ['SMALL_CRAFT']
    },
    'MEDIUM_VESSEL': {
        'name': 'Medium Vessel Certification',
        'description': 'Qualified to captain medium ships up to frigate size',
        'prerequisite_hours': 25,
        'required_missions': 15,
        'prerequisites': ['SMALL_VESSEL']
    },
    'LARGE_VESSEL': {
        'name': 'Large Vessel Certification',
        'description': 'Qualified to captain large ships up to destroyer size',
        'prerequisite_hours': 40,
        'required_missions': 25,
        'prerequisites': ['MEDIUM_VESSEL']
    },
    'CAPITAL_SHIP': {
        'name': 'Capital Ship Certification',
        'description': 'Qualified to captain capital ships',
        'prerequisite_hours': 60,
        'required_missions': 35,
        'prerequisites': ['LARGE_VESSEL', 'captaincy']
    },
    # Specialized ship certifications for different fleet components
    'MINING_VESSEL': {
        'name': 'Mining Vessel Certification',
        'description': 'Qualified to operate specialized mining vessels',
        'prerequisite_hours': 20,
        'required_missions': 8,
        'prerequisites': ['SMALL_VESSEL', 'resource_extraction']
    },
    'SALVAGE_VESSEL': {
        'name': 'Salvage Vessel Certification',
        'description': 'Qualified to operate specialized salvage vessels',
        'prerequisite_hours': 20,
        'required_missions': 8,
        'prerequisites': ['SMALL_VESSEL', 'resource_extraction']
    },
    'MEDICAL_TRANSPORT': {
        'name': 'Medical Transport Certification',
        'description': 'Qualified to operate medical ships and evacuation transports',
        'prerequisite_hours': 15,
        'required_missions': 6,
        'prerequisites': ['SMALL_VESSEL', 'basic_medical']
    },
    'EXPLORATION_VESSEL': {
        'name': 'Exploration Vessel Certification',
        'description': 'Qualified to operate long-range exploration ships',
        'prerequisite_hours': 25,
        'required_missions': 10,
        'prerequisites': ['SMALL_VESSEL', 'basic_exploration']
    }
}

# Create mappings for fleet wing and specialization-specific ranks
DIVISION_RANK_ABBREVIATIONS = {}
STANDARD_TO_DIVISION_RANK = {}

for fleet_wing, specializations in ROLE_SPECIALIZATIONS.items():
    for specialization, ranks in specializations.items():
        for div_rank_name, std_rank_name, div_abbr, std_abbr in ranks:
            key = (fleet_wing.lower(), specialization.lower(), std_rank_name.lower())
            STANDARD_TO_DIVISION_RANK[key] = (div_rank_name, div_abbr)
            DIVISION_RANK_ABBREVIATIONS[div_rank_name.lower()] = div_abbr

# Create reverse mapping for looking up standard ranks from division-specific ranks
DIVISION_TO_STANDARD_RANK = {}
for key, (div_name, div_abbr) in STANDARD_TO_DIVISION_RANK.items():
    fleet_wing, specialization, std_rank_name = key
    # Find the standard rank info
    for idx, (name, abbrev) in enumerate(RANKS):
        if name.lower() == std_rank_name.lower():
            DIVISION_TO_STANDARD_RANK[(fleet_wing, specialization, div_name.lower())] = (name, abbrev, idx)
            break

# For backward compatibility
FLEET_RANK_ABBREVIATIONS = DIVISION_RANK_ABBREVIATIONS
STANDARD_TO_FLEET_RANK = STANDARD_TO_DIVISION_RANK
FLEET_TO_STANDARD_RANK = DIVISION_TO_STANDARD_RANK

# Combine all abbreviations
STANDARD_ABBREVS = list(RANK_ABBREVIATIONS.values())
DIVISION_ABBREVS = list(DIVISION_RANK_ABBREVIATIONS.values())
ALL_RANK_ABBREVIATIONS = list(set(STANDARD_ABBREVS + DIVISION_ABBREVS))
ALL_RANK_ABBREVIATIONS = sorted(ALL_RANK_ABBREVIATIONS, key=len, reverse=True)