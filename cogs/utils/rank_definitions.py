import discord 
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from enum import Enum

@dataclass
class RankInfo:
    specialized_name: str
    standard_name: str 
    specialized_abbrev: str
    standard_abbrev: str
    division: str
    specialty: str
    level: int
    
    @property
    def display_name(self) -> str:
        return f"{self.specialized_name} ({self.standard_name})"
    
    @property 
    def display_abbrev(self) -> str:
        return f"{self.specialized_abbrev}/{self.standard_abbrev}"

# Division ranks imported from admin cog
DIVISION_RANKS = {
    # Operations Division
    'Operations': {
        'Engineering': [
            ('Engineering Apprentice', 'Crewman Recruit', 'EA', 'CWR'),
            ('Junior Technician', 'Crewman', 'JT', 'CWM'),
            ('Technician', 'Petty Officer 3rd Class', 'Tech', 'PO3'),
            ('Senior Technician', 'Petty Officer 2nd Class', 'ST', 'PO2'),
            ('Systems Operator', 'Petty Officer 1st Class', 'SO', 'PO1'),
            ('Engineering Supervisor', 'Chief Petty Officer', 'ES', 'CPO'),
            ('Chief Systems Officer', 'Ensign', 'CSO', 'ENS'),
            ('Deputy Chief Engineer', 'Lieutenant Junior Grade', 'DCE', 'Lt JG'),
            ('Assistant Chief Engineer', 'Lieutenant', 'ACE', 'Lt'),
            ('Chief Engineer', 'Lieutenant Commander', 'CE', 'Lt Cmdr'),
            ('Senior Chief Engineer', 'Commander', 'SCE', 'Cdr'),
            ('Master Chief Engineer', 'Captain', 'MCE', 'CAPT'),
            ('Engineering Director', 'Fleet Captain', 'ED', 'FCpt')
        ],
        'Haulers': [
            ('Cargo Apprentice', 'Crewman Recruit', 'CA', 'CWR'),
            ('Cargo Handler', 'Crewman', 'CH', 'CWM'),
            ('Cargo Specialist', 'Petty Officer 3rd Class', 'CS', 'PO3'),
            ('Senior Cargo Specialist', 'Petty Officer 2nd Class', 'SCS', 'PO2'),
            ('Transport Coordinator', 'Petty Officer 1st Class', 'TC', 'PO1'),
            ('Fleet Logistics Officer', 'Chief Petty Officer', 'FLO', 'CPO'),
            ('Senior Logistics Officer', 'Ensign', 'SLO', 'ENS'),
            ('Chief Logistics Officer', 'Lieutenant Junior Grade', 'CLO', 'Lt JG'),
            ('Assistant Haulmaster', 'Lieutenant', 'AHM', 'Lt'),
            ('Senior Haulmaster', 'Lieutenant Commander', 'SHM', 'Lt Cmdr'),
            ('Master Haulmaster', 'Commander', 'MHM', 'Cdr'),
            ('Logistics Commander', 'Captain', 'LC', 'CAPT'),
            ('Logistics Fleet Commander', 'Fleet Captain', 'LFC', 'FCpt')
        ],
        'Mining': [
            ('Mining Trainee', 'Crewman Recruit', 'MT', 'CWR'),
            ('Junior Miner', 'Crewman', 'JM', 'CWM'),
            ('Mining Specialist', 'Petty Officer 3rd Class', 'MS', 'PO3'),
            ('Senior Mining Specialist', 'Petty Officer 2nd Class', 'SMS', 'PO2'),
            ('Extraction Specialist', 'Petty Officer 1st Class', 'ES', 'PO1'),
            ('Mining Operations Chief', 'Chief Petty Officer', 'MOC', 'CPO'),
            ('Mining Team Leader', 'Ensign', 'MTL', 'ENS'),
            ('Mining Operations Officer', 'Lieutenant Junior Grade', 'MOO', 'Lt JG'),
            ('Senior Mining Officer', 'Lieutenant', 'SMO', 'Lt'),
            ('Chief Mining Officer', 'Lieutenant Commander', 'CMO', 'Lt Cmdr'),
            ('Mining Fleet Commander', 'Commander', 'MFC', 'Cdr'),
            ('Mining Director', 'Captain', 'MD', 'CAPT'),
            ('Mining Operations Director', 'Fleet Captain', 'MOD', 'FCpt')
        ],
        'Salvage': [
            ('Salvage Trainee', 'Crewman Recruit', 'ST', 'CWR'),
            ('Salvage Operator', 'Crewman', 'SO', 'CWM'),
            ('Salvage Specialist', 'Petty Officer 3rd Class', 'SS', 'PO3'),
            ('Senior Salvage Specialist', 'Petty Officer 2nd Class', 'SSS', 'PO2'),
            ('Recovery Specialist', 'Petty Officer 1st Class', 'RS', 'PO1'),
            ('Salvage Operations Chief', 'Chief Petty Officer', 'SOC', 'CPO'),
            ('Salvage Team Leader', 'Ensign', 'STL', 'ENS'),
            ('Salvage Operations Officer', 'Lieutenant Junior Grade', 'SOO', 'Lt JG'),
            ('Senior Salvage Officer', 'Lieutenant', 'SSO', 'Lt'),
            ('Chief Salvage Officer', 'Lieutenant Commander', 'CSO', 'Lt Cmdr'),
            ('Salvage Fleet Commander', 'Commander', 'SFC', 'Cdr'),
            ('Salvage Director', 'Captain', 'SD', 'CAPT'),
            ('Salvage Operations Director', 'Fleet Captain', 'SOD', 'FCpt')
        ]
    },
    # Support Division
    'Support': {
        'Medical': [
            ('Medical Trainee', 'Crewman Recruit', 'MT', 'CWR'),
            ('Medical Assistant', 'Crewman', 'MA', 'CWM'),
            ('Field Medic', 'Petty Officer 3rd Class', 'FM', 'PO3'),
            ('Senior Field Medic', 'Petty Officer 2nd Class', 'SFM', 'PO2'),
            ('Medical Specialist', 'Petty Officer 1st Class', 'MS', 'PO1'),
            ('Chief Medical Specialist', 'Chief Petty Officer', 'CMS', 'CPO'),
            ('Medical Officer', 'Ensign', 'MO', 'ENS'),
            ('Senior Medical Officer', 'Lieutenant Junior Grade', 'SMO', 'Lt JG'),
            ('Chief Medical Officer', 'Lieutenant', 'CMO', 'Lt'),
            ('Fleet Medical Officer', 'Lieutenant Commander', 'FMO', 'Lt Cmdr'),
            ('Medical Commander', 'Commander', 'MC', 'Cdr'),
            ('Medical Director', 'Captain', 'MD', 'CAPT'),
            ('Medical Fleet Director', 'Fleet Captain', 'MFD', 'FCpt')
        ],
        'Science': [
            ('Research Assistant', 'Crewman Recruit', 'RA', 'CWR'),
            ('Junior Researcher', 'Crewman', 'JR', 'CWM'),
            ('Field Researcher', 'Petty Officer 3rd Class', 'FR', 'PO3'),
            ('Senior Researcher', 'Petty Officer 2nd Class', 'SR', 'PO2'),
            ('Research Specialist', 'Petty Officer 1st Class', 'RS', 'PO1'),
            ('Chief Research Specialist', 'Chief Petty Officer', 'CRS', 'CPO'),
            ('Science Officer', 'Ensign', 'SO', 'ENS'),
            ('Senior Science Officer', 'Lieutenant Junior Grade', 'SSO', 'Lt JG'),
            ('Chief Science Officer', 'Lieutenant', 'CSO', 'Lt'),
            ('Research Director', 'Lieutenant Commander', 'RD', 'Lt Cmdr'),
            ('Science Commander', 'Commander', 'SC', 'Cdr'),
            ('Science Director', 'Captain', 'SD', 'CAPT'),
            ('Science Fleet Director', 'Fleet Captain', 'SFD', 'FCpt')
        ],
        'Logistics': [
            ('Logistics Trainee', 'Crewman Recruit', 'LT', 'CWR'),
            ('Logistics Assistant', 'Crewman', 'LA', 'CWM'),
            ('Logistics Specialist', 'Petty Officer 3rd Class', 'LS', 'PO3'),
            ('Senior Logistics Specialist', 'Petty Officer 2nd Class', 'SLS', 'PO2'),
            ('Supply Officer', 'Petty Officer 1st Class', 'SO', 'PO1'),
            ('Chief Supply Officer', 'Chief Petty Officer', 'CSO', 'CPO'),
            ('Logistics Officer', 'Ensign', 'LO', 'ENS'),
            ('Senior Logistics Officer', 'Lieutenant Junior Grade', 'SLO', 'Lt JG'),
            ('Chief Logistics Officer', 'Lieutenant', 'CLO', 'Lt'),
            ('Fleet Supply Officer', 'Lieutenant Commander', 'FSO', 'Lt Cmdr'),
            ('Logistics Commander', 'Commander', 'LC', 'Cdr'),
            ('Supply Director', 'Captain', 'SD', 'CAPT'),
            ('Logistics Fleet Director', 'Fleet Captain', 'LFD', 'FCpt')
        ]
    },
    # Tactical Division
    'Tactical': {
        'Marines': [
            ('Recruit', 'Crewman Recruit', 'Rct', 'CWR'),
            ('Private', 'Crewman', 'Pvt', 'CWM'),
            ('Private First Class', 'Petty Officer 3rd Class', 'PFC', 'PO3'),
            ('Lance Corporal', 'Petty Officer 2nd Class', 'LCpl', 'PO2'),
            ('Corporal', 'Petty Officer 1st Class', 'Cpl', 'PO1'),
            ('Sergeant', 'Chief Petty Officer', 'Sgt', 'CPO'),
            ('Staff Sergeant', 'Ensign', 'SSgt', 'ENS'),
            ('Gunnery Sergeant', 'Lieutenant Junior Grade', 'GySgt', 'Lt JG'),
            ('Master Sergeant', 'Lieutenant', 'MSgt', 'Lt'),
            ('First Sergeant', 'Lieutenant Commander', '1stSgt', 'Lt Cmdr'),
            ('Master Gunnery Sergeant', 'Commander', 'MGySgt', 'Cdr'),
            ('Sergeant Major', 'Captain', 'SgtMaj', 'CAPT'),
            ('Second Lieutenant', 'Fleet Captain', '2ndLt', 'FCpt'),
            ('First Lieutenant', 'Commodore', '1stLt', 'CDRE'),
            ('Captain', 'Rear Admiral', 'Capt', 'RADM')
        ],
        'Special Operations': [
            ('Special Operations Trainee', 'Crewman Recruit', 'SOT', 'CWR'),
            ('Special Operator', 'Crewman', 'SO', 'CWM'),
            ('Senior Operator', 'Petty Officer 3rd Class', 'SrO', 'PO3'),
            ('Lead Operator', 'Petty Officer 2nd Class', 'LO', 'PO2'),
            ('Chief Operator', 'Petty Officer 1st Class', 'CO', 'PO1'),
            ('Operations Chief', 'Chief Petty Officer', 'OC', 'CPO'),
            ('Special Operations Officer', 'Ensign', 'SOO', 'ENS'),
            ('Senior Operations Officer', 'Lieutenant Junior Grade', 'SrOO', 'Lt JG'),
            ('Operations Commander', 'Lieutenant', 'OpsCdr', 'Lt'),
            ('Special Operations Commander', 'Lieutenant Commander', 'SOC', 'Lt Cmdr'),
            ('Task Force Commander', 'Commander', 'TFC', 'Cdr'),
            ('Special Operations Director', 'Captain', 'SOD', 'CAPT'),
            ('Special Operations Force Commander', 'Fleet Captain', 'SOFC', 'FCpt')
        ]
    }
}

def get_rank_info_by_standard_name(
    division: str, 
    specialty: str, 
    standard_rank: str
) -> Optional[RankInfo]:
    """Find the specialized rank entry for a given standard rank, without needing rank_index."""
    if division not in DIVISION_RANKS or specialty not in DIVISION_RANKS[division]:
        return None

    rank_list = DIVISION_RANKS[division][specialty]
    standard_rank_lower = standard_rank.lower()

    for i, (spec_name, std_name, spec_abbrev, std_abbrev) in enumerate(rank_list):
        if std_name.lower() == standard_rank_lower:
            return RankInfo(
                specialized_name=spec_name,
                standard_name=std_name,
                specialized_abbrev=spec_abbrev,
                standard_abbrev=std_abbrev,
                division=division,
                specialty=specialty,
                level=i
            )
    return None
