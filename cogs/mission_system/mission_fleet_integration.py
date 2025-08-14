"""
Mission Fleet Integration Module

This module provides integration between the mission system and the fleet management system.
It enables assigning flight groups, squadrons, and registered ships to missions.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Dict, Optional, Any, Tuple, Set
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger('mission_fleet')
logger.setLevel(logging.INFO)

class FleetAssignment:
    """Tracks assignment of fleet assets to a mission."""
    
    def __init__(self):
        self.assigned_ships: Set[str] = set()  # Registry numbers
        self.assigned_flight_groups: Set[str] = set()  # Flight group IDs/names
        self.assigned_squadrons: Set[str] = set()  # Squadron IDs/names
        
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'assigned_ships': list(self.assigned_ships),
            'assigned_flight_groups': list(self.assigned_flight_groups),
            'assigned_squadrons': list(self.assigned_squadrons)
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'FleetAssignment':
        """Create from dictionary data."""
        instance = cls()
        instance.assigned_ships = set(data.get('assigned_ships', []))
        instance.assigned_flight_groups = set(data.get('assigned_flight_groups', []))
        instance.assigned_squadrons = set(data.get('assigned_squadrons', []))
        return instance

class FleetAssignmentView(discord.ui.View):
    """View for assigning fleet assets to a mission."""
    
    def __init__(self, mission_cog, ship_cog, mission, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.mission_cog = mission_cog
        self.ship_cog = ship_cog
        self.mission = mission
        self.fleet_assignment = getattr(mission, 'fleet_assignment', FleetAssignment())
        
        # Ensure mission has fleet_assignment attribute
        if not hasattr(mission, 'fleet_assignment'):
            mission.fleet_assignment = self.fleet_assignment
    
    @discord.ui.select(
        placeholder="Select ships to assign...",
        min_values=0,
        max_values=25,
        options=[
            discord.SelectOption(label="Loading ships...", value="loading")
        ]
    )
    async def ship_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle ship selection."""
        # This will be populated with real options when the view is created
        await interaction.response.defer()
        
        # Update assigned ships
        self.fleet_assignment.assigned_ships = set(select.values)
        
        # Save mission data
        self.mission_cog.save_missions()
        
        # Acknowledge
        await interaction.followup.send(f"Updated assigned ships for mission '{self.mission.name}'", ephemeral=True)
    
    @discord.ui.select(
        placeholder="Select flight groups to assign...",
        min_values=0,
        max_values=25,
        options=[
            discord.SelectOption(label="Loading flight groups...", value="loading")
        ]
    )
    async def flight_group_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle flight group selection."""
        # This will be populated with real options when the view is created
        await interaction.response.defer()
        
        # Update assigned flight groups
        self.fleet_assignment.assigned_flight_groups = set(select.values)
        
        # Save mission data
        self.mission_cog.save_missions()
        
        # Acknowledge
        await interaction.followup.send(f"Updated assigned flight groups for mission '{self.mission.name}'", ephemeral=True)
    
    @discord.ui.select(
        placeholder="Select squadrons to assign...",
        min_values=0,
        max_values=25,
        options=[
            discord.SelectOption(label="Loading squadrons...", value="loading")
        ]
    )
    async def squadron_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle squadron selection."""
        # This will be populated with real options when the view is created
        await interaction.response.defer()
        
        # Update assigned squadrons
        self.fleet_assignment.assigned_squadrons = set(select.values)
        
        # Save mission data
        self.mission_cog.save_missions()
        
        # Acknowledge
        await interaction.followup.send(f"Updated assigned squadrons for mission '{self.mission.name}'", ephemeral=True)
    
    @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Complete the assignment process."""
        await interaction.response.defer()
        
        # Update mission embed
        await self.mission_cog.update_mission_view(self.mission)
        
        # Summary message
        embed = discord.Embed(
            title=f"Fleet Assignments for {self.mission.name}",
            color=discord.Color.green()
        )
        
        # Add ships
        if self.fleet_assignment.assigned_ships:
            ship_str = "\n".join([f"• {ship}" for ship in self.fleet_assignment.assigned_ships])
            embed.add_field(name="Assigned Ships", value=ship_str, inline=False)
        else:
            embed.add_field(name="Assigned Ships", value="No ships assigned", inline=False)
            
        # Add flight groups
        if self.fleet_assignment.assigned_flight_groups:
            fg_str = "\n".join([f"• {fg}" for fg in self.fleet_assignment.assigned_flight_groups])
            embed.add_field(name="Assigned Flight Groups", value=fg_str, inline=False)
        else:
            embed.add_field(name="Assigned Flight Groups", value="No flight groups assigned", inline=False)
            
        # Add squadrons
        if self.fleet_assignment.assigned_squadrons:
            sq_str = "\n".join([f"• {sq}" for sq in self.fleet_assignment.assigned_squadrons])
            embed.add_field(name="Assigned Squadrons", value=sq_str, inline=False)
        else:
            embed.add_field(name="Assigned Squadrons", value="No squadrons assigned", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
        # Close view
        self.stop()

async def setup_fleet_assignment_view(mission_cog, mission) -> FleetAssignmentView:
    """Create and setup a fleet assignment view."""
    # Get ship cog reference
    ship_cog = mission_cog.bot.get_cog("ShipsCog")
    if not ship_cog:
        logger.error("ShipsCog not found, cannot setup fleet assignment view")
        return None
    
    # Create view
    view = FleetAssignmentView(mission_cog, ship_cog, mission)
    
    # Setup ship select options
    ship_options = []
    try:
        # Get registered ships
        commissioned_ships = []
        for ship_name in ship_cog.registry._ships_cache.keys():
            registry_info = await ship_cog.registry.get_ship_registry_info(ship_name)
            if registry_info and registry_info.get('Registry Number'):
                # Add ship to options
                display_name = f"{ship_name} ({registry_info['Registry Number']})"
                registry_id = registry_info['Registry Number']
                ship_options.append(discord.SelectOption(
                    label=display_name[:100],  # 100 char limit
                    value=registry_id,
                    default=registry_id in mission.fleet_assignment.assigned_ships
                ))
    except Exception as e:
        logger.error(f"Error setting up ship options: {e}")
    
    # Replace placeholder options
    ship_select = [item for item in view.children if isinstance(item, discord.ui.Select) 
                   and item.placeholder == "Select ships to assign..."][0]
    ship_select.options = ship_options[:25]  # 25 options max
    
    # Setup flight group select options
    flight_group_options = []
    try:
        # Get flight groups
        flight_groups = await ship_cog.registry.list_flight_groups()
        for fg in flight_groups:
            fg_name = fg['name']
            flight_group_options.append(discord.SelectOption(
                label=fg_name[:100],  # 100 char limit
                value=fg_name,
                default=fg_name in mission.fleet_assignment.assigned_flight_groups
            ))
    except Exception as e:
        logger.error(f"Error setting up flight group options: {e}")
    
    # Replace placeholder options
    flight_group_select = [item for item in view.children if isinstance(item, discord.ui.Select) 
                          and item.placeholder == "Select flight groups to assign..."][0]
    flight_group_select.options = flight_group_options[:25]
    
    # Setup squadron select options
    squadron_options = []
    try:
        # Get squadrons
        squadrons = await ship_cog.registry.list_squadrons()
        for sq in squadrons:
            sq_name = sq['name']
            squadron_options.append(discord.SelectOption(
                label=sq_name[:100],  # 100 char limit
                value=sq_name,
                default=sq_name in mission.fleet_assignment.assigned_squadrons
            ))
    except Exception as e:
        logger.error(f"Error setting up squadron options: {e}")
    
    # Replace placeholder options
    squadron_select = [item for item in view.children if isinstance(item, discord.ui.Select) 
                      and item.placeholder == "Select squadrons to assign..."][0]
    squadron_select.options = squadron_options[:25]
    
    return view

async def flight_group_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provide autocomplete for flight groups."""
    choices = []
    
    # Get ship cog
    ship_cog = interaction.client.get_cog("ShipsCog")
    if not ship_cog:
        return choices
        
    try:
        # Get flight groups from registry
        flight_groups = await ship_cog.registry.list_flight_groups()
        
        # Filter by current input
        for fg in flight_groups:
            fg_name = fg['name']
            if current.lower() in fg_name.lower():
                choices.append(app_commands.Choice(name=fg_name, value=fg_name))
                
        return choices[:25]  # 25 choices max
    except Exception as e:
        logger.error(f"Error in flight group autocomplete: {e}")
        return choices

async def squadron_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provide autocomplete for squadrons."""
    choices = []
    
    # Get ship cog
    ship_cog = interaction.client.get_cog("ShipsCog")
    if not ship_cog:
        return choices
        
    try:
        # Get squadrons from registry
        squadrons = await ship_cog.registry.list_squadrons()
        
        # Filter by current input
        for sq in squadrons:
            sq_name = sq['name']
            if current.lower() in sq_name.lower():
                choices.append(app_commands.Choice(name=sq_name, value=sq_name))
                
        return choices[:25]  # 25 choices max
    except Exception as e:
        logger.error(f"Error in squadron autocomplete: {e}")
        return choices

async def registered_ship_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Provide autocomplete for registered ships."""
    choices = []
    
    # Get ship cog
    ship_cog = interaction.client.get_cog("ShipsCog")
    if not ship_cog:
        return choices
        
    try:
        # Search for ships by name or registry number
        if current:
            # Check if searching by registry number
            if current.startswith('HLN-'):
                # Search by registry number
                results = await ship_cog.registry.search_registry(current)
                for ship in results:
                    ship_name = ship.get('Ship Name', 'Unknown')
                    registry_number = ship.get('Registry Number', 'Unknown')
                    display_name = f"{ship_name} ({registry_number})"
                    choices.append(app_commands.Choice(name=display_name[:100], value=registry_number))
            else:
                # Search by ship name
                commissioned_ships = []
                for ship_name in ship_cog.registry._ships_cache.keys():
                    if current.lower() in ship_name.lower():
                        registry_info = await ship_cog.registry.get_ship_registry_info(ship_name)
                        if registry_info and registry_info.get('Registry Number'):
                            display_name = f"{ship_name} ({registry_info['Registry Number']})"
                            registry_id = registry_info['Registry Number']
                            choices.append(app_commands.Choice(name=display_name[:100], value=registry_id))
        else:
            # Show some commissioned ships without a filter
            ship_count = 0
            for ship_name in list(ship_cog.registry._ships_cache.keys())[:10]:  # Limit to first 10 for performance
                registry_info = await ship_cog.registry.get_ship_registry_info(ship_name)
                if registry_info and registry_info.get('Registry Number'):
                    display_name = f"{ship_name} ({registry_info['Registry Number']})"
                    registry_id = registry_info['Registry Number']
                    choices.append(app_commands.Choice(name=display_name[:100], value=registry_id))
                    ship_count += 1
                    if ship_count >= 25:
                        break
                    
        return choices[:25]  # 25 choices max
    except Exception as e:
        logger.error(f"Error in registered ship autocomplete: {e}")
        return choices

async def check_flight_group_command(member: discord.Member, flight_group: str) -> bool:
    """Check if member is commander of a flight group."""
    try:
        # Get the ShipsCog
        ship_cog = member.guild.bot.get_cog("ShipsCog")
        if not ship_cog:
            return False
        
        # Get flight group info
        fg = await ship_cog.registry.get_flight_group(flight_group)
        if not fg:
            return False
            
        # Check if member is commander
        commander_id = fg.get('commander_id')
        if commander_id and int(commander_id) == member.id:
            return True
            
        # Also allow administrators to command any flight group
        if member.guild_permissions.administrator:
            return True
            
        return False
    except Exception as e:
        logger.error(f"Error checking flight group command: {e}")
        return False

async def check_squadron_command(member: discord.Member, squadron: str) -> bool:
    """Check if member is commander of a squadron."""
    try:
        # Get the ShipsCog
        ship_cog = member.guild.bot.get_cog("ShipsCog")
        if not ship_cog:
            return False
        
        # Get squadron info
        sq = await ship_cog.registry.get_squadron(squadron)
        if not sq:
            return False
            
        # Check if member is commander
        commander_id = sq.get('commander_id')
        if commander_id and int(commander_id) == member.id:
            return True
            
        # Also allow administrators to command any squadron
        if member.guild_permissions.administrator:
            return True
            
        return False
    except Exception as e:
        logger.error(f"Error checking squadron command: {e}")
        return False

async def check_ship_command(member: discord.Member, registry_number: str) -> bool:
    """Check if member can command a registered ship."""
    try:
        # Get the ShipsCog
        ship_cog = member.guild.bot.get_cog("ShipsCog")
        if not ship_cog:
            return False
        
        # Search for ship by registry number
        results = await ship_cog.registry.search_registry(registry_number)
        if not results:
            return False
            
        ship_info = results[0]
        
        # Check if member is registered owner
        registered_by = ship_info.get('Registered By')
        if registered_by and registered_by == str(member.id):
            return True
            
        # Also allow administrators to command any ship
        if member.guild_permissions.administrator:
            return True
            
        return False
    except Exception as e:
        logger.error(f"Error checking ship command: {e}")
        return False

def format_fleet_assignments_for_embed(mission):
    """Format fleet assignments for display in mission embed."""
    if not hasattr(mission, 'fleet_assignment'):
        return None
        
    fleet_assignment = mission.fleet_assignment
    
    # Return None if no assignments
    if not (fleet_assignment.assigned_ships or 
            fleet_assignment.assigned_flight_groups or 
            fleet_assignment.assigned_squadrons):
        return None
    
    # Format assignment text
    assignment_lines = []
    
    # Add squadrons
    if fleet_assignment.assigned_squadrons:
        assignment_lines.append("**Squadrons:**")
        for squadron in fleet_assignment.assigned_squadrons:
            assignment_lines.append(f"• {squadron}")
    
    # Add flight groups
    if fleet_assignment.assigned_flight_groups:
        assignment_lines.append("**Flight Groups:**")
        for flight_group in fleet_assignment.assigned_flight_groups:
            assignment_lines.append(f"• {flight_group}")
    
    # Add ships
    if fleet_assignment.assigned_ships:
        assignment_lines.append("**Ships:**")
        for ship in fleet_assignment.assigned_ships:
            assignment_lines.append(f"• {ship}")
    
    if assignment_lines:
        return "\n".join(assignment_lines)
    else:
        return None