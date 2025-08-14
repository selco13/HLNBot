import logging
import random
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger('onboarding')

# Original Division Codes for ID Generation
DIVISION_CODES = {
    "Tactical": "TC",
    "Operations": "OP",
    "Support": "SP",
    "Command Staff": "HQ",
    "Non-Division": "ND",
    "Ambassador": "AMB",
    "Associate": "AS",
    "Reserve": "RS"
}

# Fleet Wing to Division mapping (for backward compatibility)
FLEET_TO_DIVISION_MAPPING = {
    "Navy Fleet": "Tactical",
    "Marine Expeditionary Force": "Tactical",  # Marine forces fall under Tactical
    "Industrial & Logistics Wing": "Operations",
    "Support & Medical Fleet": "Support",
    "Exploration & Intelligence Wing": "Operations",  # Exploration falls under Operations
    "Fleet Command": "Command Staff",
    "Command Staff": "Command Staff",
    "Non-Fleet": "Non-Division",
    "Ambassador": "Ambassador",
    "Associate": "Associate"
}

# Rank Codes - Numbers padded with leading zeros (01-21)
RANK_CODES = {
    # Officers (ascending order)
    "Admiral": "01",
    "Vice Admiral": "02",
    "Rear Admiral": "03",
    "Commodore": "04",
    "Fleet Captain": "05",
    "Captain": "06",
    "Commander": "07",
    "Lieutenant Commander": "08",
    "Lieutenant": "09",
    "Lieutenant Junior Grade": "10",
    "Ensign": "11",
    # Enlisted (ascending order)
    "Chief Petty Officer": "12",
    "Petty Officer 1st Class": "13",
    "Petty Officer 2nd Class": "14",
    "Petty Officer 3rd Class": "15",
    "Master Crewman": "16",
    "Senior Crewman": "17",
    "Crewman": "18",
    "Crewman Apprentice": "19",
    "Crewman Recruit": "20",
    # Special ranks
    "Ambassador": "AMB",
    "Associate": "AS"
}

# Standard Rank Abbreviations (for reference)
RANK_ABBREVIATIONS = {
    "Admiral": "ADM",
    "Vice Admiral": "VADM",
    "Rear Admiral": "RADM", 
    "Commodore": "CDRE",
    "Fleet Captain": "FCPT",
    "Captain": "CAPT",
    "Commander": "CDR",
    "Lieutenant Commander": "LCDR",
    "Lieutenant": "LT",
    "Lieutenant Junior Grade": "LTJG",
    "Ensign": "ENS",
    "Chief Petty Officer": "CPO",
    "Petty Officer 1st Class": "PO1",
    "Petty Officer 2nd Class": "PO2",
    "Petty Officer 3rd Class": "PO3",
    "Master Crewman": "MCWM",
    "Senior Crewman": "SCWM",
    "Crewman": "CWM",
    "Crewman Apprentice": "CWA",
    "Crewman Recruit": "CWR",
    "Ambassador": "AMB",
    "Associate": "AS"
}

async def generate_member_id(coda_client, member_type: str, fleet_wing: str = None, division: str = None) -> str:
    """
    Generate a unique member ID following the HLN format:
    [Division Code]-[Rank Code]-[Personal Sequence Number]
    
    Args:
        coda_client: The Coda API client
        member_type: The type of membership (Member or Associate)
        fleet_wing: The fleet wing the member belongs to
        division: The division the member belongs to (older system)
        
    Returns:
        A formatted member ID string
    """
    try:
        # Step 1: Determine division code
        # First check if division is directly provided
        if division and division in DIVISION_CODES:
            division_code = DIVISION_CODES[division]
        # If not, try to map from fleet wing to division
        elif fleet_wing and fleet_wing in FLEET_TO_DIVISION_MAPPING:
            mapped_division = FLEET_TO_DIVISION_MAPPING[fleet_wing]
            division_code = DIVISION_CODES[mapped_division]
        else:
            # Default to Non-Division if we can't determine
            division_code = DIVISION_CODES["Non-Division"]
        
        # Step 2: Determine rank code based on member type
        if member_type == "Associate":
            rank_code = RANK_CODES["Associate"]
        elif member_type == "Ambassador":
            rank_code = RANK_CODES["Ambassador"]
        else:  # Regular member - start at Crewman Recruit
            rank_code = RANK_CODES["Crewman Recruit"]
            
        # Step 3: Generate a unique sequence number
        sequence_number = await generate_unique_sequence_number(coda_client)
        
        # Step 4: Format the ID
        member_id = f"{division_code}-{rank_code}-{sequence_number}"
        logger.info(f"Generated member ID: {member_id}")
        
        return member_id
        
    except Exception as e:
        logger.error(f"Error generating member ID: {e}")
        # Return a fallback ID if there's an error
        return f"ND-{RANK_CODES['Crewman Recruit']}-0000"
        
async def generate_unique_sequence_number(coda_client) -> str:
    """
    Generate a unique 4-digit sequence number that doesn't exist in the database.
    
    Args:
        coda_client: The Coda API client
        
    Returns:
        A 4-digit sequence number as a string
    """
    import os
    
    try:
        # Get all existing sequence numbers from the database
        doc_id = os.getenv("DOC_ID")
        table_id = os.getenv("TABLE_ID")
        
        if not doc_id or not table_id:
            logger.warning("Missing DOC_ID or TABLE_ID environment variables")
            return f"{random.randint(1000, 9999):04d}"
        
        response = await coda_client.request(
            'GET',
            f'docs/{doc_id}/tables/{table_id}/rows',
            params={
                'useColumnNames': 'true',
                'valueFormat': 'simple'
            }
        )
        
        existing_ids = []
        
        if response and 'items' in response:
            for item in response['items']:
                if 'values' in item and 'ID Number' in item['values']:
                    id_value = item['values']['ID Number']
                    if id_value and isinstance(id_value, str) and '-' in id_value:
                        # Extract the sequence number part
                        parts = id_value.split('-')
                        if len(parts) == 3:
                            try:
                                existing_ids.append(int(parts[2]))
                            except ValueError:
                                continue
        
        # Find the highest existing sequence number
        highest_seq = max(existing_ids) if existing_ids else 1000
        
        # Generate a new sequence number
        new_seq = highest_seq + 1
        
        # Ensure it's 4 digits
        return f"{new_seq:04d}"
        
    except Exception as e:
        logger.error(f"Error generating sequence number: {e}")
        # Generate a random number if we couldn't get existing ones
        random_seq = random.randint(5000, 9999)
        return f"{random_seq:04d}"

async def update_id_for_promotion(current_id: str, new_rank: str) -> str:
    """
    Update a member's ID when they are promoted to reflect their new rank.
    The division code and sequence number remain the same, only the rank code changes.
    
    Args:
        current_id: The member's current ID
        new_rank: The member's new rank
        
    Returns:
        Updated ID string
    """
    try:
        # Parse the current ID
        parts = current_id.split('-')
        if len(parts) != 3:
            logger.error(f"Invalid ID format: {current_id}")
            return current_id
            
        division_code, _, sequence_number = parts
        
        # Get the new rank code
        if new_rank not in RANK_CODES:
            logger.error(f"Unknown rank: {new_rank}")
            return current_id
            
        new_rank_code = RANK_CODES[new_rank]
        
        # Create the updated ID
        updated_id = f"{division_code}-{new_rank_code}-{sequence_number}"
        logger.info(f"Updated ID for promotion: {current_id} -> {updated_id}")
        
        return updated_id
        
    except Exception as e:
        logger.error(f"Error updating ID for promotion: {e}")
        return current_id

async def update_id_for_transfer(current_id: str, new_division: str = None, new_fleet_wing: str = None) -> str:
    """
    Update a member's ID when they transfer to a new division or fleet wing.
    The rank code and sequence number remain the same, only the division code changes.
    
    Args:
        current_id: The member's current ID
        new_division: The member's new division (old system)
        new_fleet_wing: The member's new fleet wing (new system)
        
    Returns:
        Updated ID string
    """
    try:
        # Parse the current ID
        parts = current_id.split('-')
        if len(parts) != 3:
            logger.error(f"Invalid ID format: {current_id}")
            return current_id
            
        _, rank_code, sequence_number = parts
        
        # Determine the new division code
        if new_division and new_division in DIVISION_CODES:
            new_division_code = DIVISION_CODES[new_division]
        elif new_fleet_wing and new_fleet_wing in FLEET_TO_DIVISION_MAPPING:
            mapped_division = FLEET_TO_DIVISION_MAPPING[new_fleet_wing]
            new_division_code = DIVISION_CODES[mapped_division]
        else:
            # If we can't determine, keep the original division code
            new_division_code = parts[0]
        
        # Create the updated ID
        updated_id = f"{new_division_code}-{rank_code}-{sequence_number}"
        logger.info(f"Updated ID for transfer: {current_id} -> {updated_id}")
        
        return updated_id
        
    except Exception as e:
        logger.error(f"Error updating ID for transfer: {e}")
        return current_id

def parse_id(id_string: str) -> Dict[str, str]:
    """
    Parse an ID string into its components.
    
    Args:
        id_string: The ID to parse
        
    Returns:
        Dictionary with division_code, rank_code, and sequence_number
    """
    try:
        parts = id_string.split('-')
        if len(parts) != 3:
            logger.error(f"Invalid ID format: {id_string}")
            return {
                "division_code": "Unknown",
                "rank_code": "Unknown",
                "sequence_number": "Unknown"
            }
            
        division_code, rank_code, sequence_number = parts
        
        return {
            "division_code": division_code,
            "rank_code": rank_code,
            "sequence_number": sequence_number
        }
        
    except Exception as e:
        logger.error(f"Error parsing ID: {e}")
        return {
            "division_code": "Error",
            "rank_code": "Error",
            "sequence_number": "Error"
        }