import csv
import logging
import os
from typing import Dict, List, Optional, Set, ClassVar
from dataclasses import dataclass
import re

logger = logging.getLogger('ship_data')
logger.setLevel(logging.DEBUG)

@dataclass
class Ship:
    """
    Ship data class to store information about ship models.
    """
    name: str
    manufacturer: str
    role: str
    size: str
    length: str
    width: str
    height: str
    weight: str
    min_crew: float
    max_crew: int
    cargo: str
    scm_speed: str
    max_speed: str
    roll: str
    pitch: str
    yaw: str
    
    # Class variables to store all loaded ships
    _ships_cache: ClassVar[Dict[str, 'Ship']] = {}
    _manufacturers: ClassVar[Set[str]] = set()
    _roles: ClassVar[Set[str]] = set()
    _sizes: ClassVar[Set[str]] = set()
    
    @classmethod
    def load_ships(cls, file_path: str = None) -> bool:
        """
        Load ships from CSV file.
        Returns True if successful, False otherwise.
        """
        if file_path is None:
            # Default to ships.csv in the expected location
            file_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'ships.csv')
        
        # Make sure we have a clean start
        cls._ships_cache.clear()
        cls._manufacturers.clear()
        cls._roles.clear()
        cls._sizes.clear()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    try:
                        ship = cls(
                            name=row['Name'],
                            manufacturer=row['Manufacturer'],
                            role=row['Role'],
                            size=row['Size'],
                            length=row['Length'],
                            width=row['Width'],
                            height=row['Height'],
                            weight=row['Weight'],
                            min_crew=float(row['Min Crew']),
                            max_crew=int(row['Max Crew']),
                            cargo=row['Cargo'],
                            scm_speed=row['SCM Speed'],
                            max_speed=row['Max Speed'],
                            roll=row['Roll'],
                            pitch=row['Pitch'],
                            yaw=row['Yaw']
                        )
                        cls._ships_cache[ship.name] = ship
                        cls._manufacturers.add(ship.manufacturer)
                        cls._roles.add(ship.role)
                        cls._sizes.add(ship.size)
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Error processing ship row: {e} - Row: {row}")
                
            logger.info(f"Loaded {len(cls._ships_cache)} ships from {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading ships from {file_path}: {e}")
            return False
    
    @classmethod
    def get_ship(cls, name: str) -> Optional['Ship']:
        """Get a ship by name."""
        return cls._ships_cache.get(name)
    
    @classmethod
    def search_ships(cls, search_term: str, limit: int = 25) -> List['Ship']:
        """
        Search for ships by name or manufacturer.
        Returns a list of matching ships, sorted by relevance.
        """
        if not search_term:
            # Return all ships if no search term, up to the limit
            return list(cls._ships_cache.values())[:limit]
        
        search_term = search_term.lower()
        exact_matches = []
        name_starts_with = []
        name_contains = []
        manufacturer_matches = []
        role_matches = []
        
        for ship in cls._ships_cache.values():
            ship_name_lower = ship.name.lower()
            
            # Exact match on name
            if ship_name_lower == search_term:
                exact_matches.append(ship)
                continue
                
            # Name starts with search term
            if ship_name_lower.startswith(search_term):
                name_starts_with.append(ship)
                continue
                
            # Name contains search term
            if search_term in ship_name_lower:
                name_contains.append(ship)
                continue
                
            # Manufacturer contains search term
            if search_term in ship.manufacturer.lower():
                manufacturer_matches.append(ship)
                continue
                
            # Role contains search term
            if search_term in ship.role.lower():
                role_matches.append(ship)
                continue
                
        # Combine results in order of relevance
        results = (
            exact_matches +
            name_starts_with +
            name_contains +
            manufacturer_matches +
            role_matches
        )
        
        return results[:limit]
    
    @classmethod
    def get_all_manufacturers(cls) -> List[str]:
        """Get a list of all manufacturers."""
        return sorted(cls._manufacturers)
    
    @classmethod
    def get_all_roles(cls) -> List[str]:
        """Get a list of all ship roles."""
        return sorted(cls._roles)
    
    @classmethod
    def get_all_sizes(cls) -> List[str]:
        """Get a list of all ship sizes."""
        return sorted(cls._sizes)
    
    @classmethod
    def get_ships_by_manufacturer(cls, manufacturer: str) -> List['Ship']:
        """Get all ships from a specific manufacturer."""
        return [
            ship for ship in cls._ships_cache.values()
            if ship.manufacturer == manufacturer
        ]
    
    @classmethod
    def get_ships_by_role(cls, role: str) -> List['Ship']:
        """Get all ships with a specific role."""
        return [
            ship for ship in cls._ships_cache.values()
            if ship.role == role
        ]
    
    @classmethod
    def get_ships_by_size(cls, size: str) -> List['Ship']:
        """Get all ships of a specific size."""
        return [
            ship for ship in cls._ships_cache.values()
            if ship.size == size
        ]
    
    @classmethod
    def filter_ships(
        cls,
        manufacturer: Optional[str] = None,
        role: Optional[str] = None,
        size: Optional[str] = None,
        min_crew: Optional[int] = None,
        max_crew: Optional[int] = None,
        search_term: Optional[str] = None
    ) -> List['Ship']:
        """
        Filter ships based on multiple criteria.
        Returns a list of ships that match all provided filters.
        """
        results = list(cls._ships_cache.values())
        
        # Apply filters
        if manufacturer:
            results = [s for s in results if manufacturer.lower() in s.manufacturer.lower()]
        
        if role:
            results = [s for s in results if role.lower() in s.role.lower()]
            
        if size:
            results = [s for s in results if size.lower() == s.size.lower()]
            
        if min_crew is not None:
            results = [s for s in results if s.min_crew >= min_crew]
            
        if max_crew is not None:
            results = [s for s in results if s.max_crew <= max_crew]
            
        if search_term:
            search_term = search_term.lower()
            results = [
                s for s in results
                if (search_term in s.name.lower() or
                    search_term in s.manufacturer.lower() or
                    search_term in s.role.lower())
            ]
            
        return results