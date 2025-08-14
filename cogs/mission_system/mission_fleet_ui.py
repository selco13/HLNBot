"""
Mission Fleet UI Components

This module provides UI components for mission fleet integration,
including modals and views for assigning fleet assets to missions.
"""

import discord
from discord.ext import commands
from typing import List, Dict, Optional, Any, Tuple, Set
import logging
import asyncio
from datetime import datetime, timezone

logger = logging.getLogger('mission_fleet_ui')

class FleetAssetSelectionView(discord.ui.View):
    """View for selecting fleet assets during mission creation or editing."""
    
    def __init__(self, cog, mission_id: str, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.mission_id = mission_id
        self.selected_ships = set()
        self.selected_flight_groups = set()
        self.selected_squadrons = set()
        
    @discord.ui.button(label="Select Ships", style=discord.ButtonStyle.primary, row=0)
    async def select_ships_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the ship selection interface."""
        mission = self.cog.missions.get(self.mission_id)
        if not mission:
            await interaction.response.send_message("Mission not found.", ephemeral=True)
            return
        
        # Create a ship selection modal
        modal = RegisteredShipSelectionModal(self.cog, mission)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Select Flight Groups", style=discord.ButtonStyle.primary, row=0)
    async def select_flight_groups_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the flight group selection interface."""
        mission = self.cog.missions.get(self.mission_id)
        if not mission:
            await interaction.response.send_message("Mission not found.", ephemeral=True)
            return
        
        # Create a flight group selection modal
        modal = FlightGroupSelectionModal(self.cog, mission)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Select Squadrons", style=discord.ButtonStyle.primary, row=0)
    async def select_squadrons_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the squadron selection interface."""
        mission = self.cog.missions.get(self.mission_id)
        if not mission:
            await interaction.response.send_message("Mission not found.", ephemeral=True)
            return
        
        # Create a squadron selection modal
        modal = SquadronSelectionModal(self.cog, mission)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Done", style=discord.ButtonStyle.success, row=1)
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Complete the fleet asset selection process."""
        mission = self.cog.missions.get(self.mission_id)
        if not mission:
            await interaction.response.send_message("Mission not found.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Fleet Assets Selected",
            description=f"The following assets have been assigned to mission '{mission.name}':",
            color=discord.Color.green()
        )
        
        # Check if mission has fleet_assignment attribute
        if hasattr(mission, 'fleet_assignment'):
            fleet_assignments = mission.fleet_assignment
            
            # Add ships
            if fleet_assignments.assigned_ships:
                ship_str = "\n".join([f"• {ship}" for ship in fleet_assignments.assigned_ships])
                embed.add_field(name="Assigned Ships", value=ship_str, inline=False)
            else:
                embed.add_field(name="Assigned Ships", value="No ships assigned", inline=False)
                
            # Add flight groups
            if fleet_assignments.assigned_flight_groups:
                fg_str = "\n".join([f"• {fg}" for fg in fleet_assignments.assigned_flight_groups])
                embed.add_field(name="Assigned Flight Groups", value=fg_str, inline=False)
            else:
                embed.add_field(name="Assigned Flight Groups", value="No flight groups assigned", inline=False)
                
            # Add squadrons
            if fleet_assignments.assigned_squadrons:
                sq_str = "\n".join([f"• {sq}" for sq in fleet_assignments.assigned_squadrons])
                embed.add_field(name="Assigned Squadrons", value=sq_str, inline=False)
            else:
                embed.add_field(name="Assigned Squadrons", value="No squadrons assigned", inline=False)
        else:
            embed.description = "No fleet assets have been assigned to this mission."
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()


class RegisteredShipSelectionModal(discord.ui.Modal):
    """Modal for selecting registered ships."""
    
    def __init__(self, cog, mission):
        super().__init__(title=f"Select Ships for {mission.name}")
        self.cog = cog
        self.mission = mission
        
        # Create a text input for entering ship registry numbers
        self.ships_input = discord.ui.TextInput(
            label="Enter Ship Registry Numbers (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="HLN-123-4567\nHLN-890-1234",
            required=False,
            default="\n".join(getattr(mission, 'fleet_assignment', {}).get('assigned_ships', []))
        )
        self.add_item(self.ships_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted ship selections."""
        await interaction.response.defer(ephemeral=True)
        
        # Parse the ships input
        ships = self.ships_input.value.strip().split('\n')
        ships = [s.strip() for s in ships if s.strip()]
        
        # Validate the ship registry numbers
        ship_cog = interaction.client.get_cog("ShipsCog")
        if ship_cog:
            valid_ships = []
            invalid_ships = []
            
            for registry_number in ships:
                try:
                    # Search for ship by registry number
                    results = await ship_cog.registry.search_registry(registry_number)
                    if results:
                        valid_ships.append(registry_number)
                    else:
                        invalid_ships.append(registry_number)
                except Exception as e:
                    logger.error(f"Error validating ship registry: {e}")
                    invalid_ships.append(registry_number)
            
            # Update the mission's fleet assignment
            from mission_fleet_integration import FleetAssignment
            if not hasattr(self.mission, 'fleet_assignment'):
                self.mission.fleet_assignment = FleetAssignment()
            
            self.mission.fleet_assignment.assigned_ships = set(valid_ships)
            
            # Save the mission data
            self.cog.save_missions()
            
            # Create response message
            if invalid_ships:
                await interaction.followup.send(
                    f"✅ Assigned {len(valid_ships)} ships to the mission.\n"
                    f"⚠️ {len(invalid_ships)} invalid registry numbers were ignored: {', '.join(invalid_ships)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Successfully assigned {len(valid_ships)} ships to the mission.",
                    ephemeral=True
                )
            
            # Update the mission view
            await self.cog.update_mission_view(self.mission)
        else:
            await interaction.followup.send(
                "❌ Error: Ship registry system not available.",
                ephemeral=True
            )


class FlightGroupSelectionModal(discord.ui.Modal):
    """Modal for selecting flight groups."""
    
    def __init__(self, cog, mission):
        super().__init__(title=f"Select Flight Groups for {mission.name}")
        self.cog = cog
        self.mission = mission
        
        # Create a text input for entering flight group names
        self.flight_groups_input = discord.ui.TextInput(
            label="Enter Flight Group Names (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="Alpha Flight\nBravo Flight",
            required=False,
            default="\n".join(getattr(mission, 'fleet_assignment', {}).get('assigned_flight_groups', []))
        )
        self.add_item(self.flight_groups_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted flight group selections."""
        await interaction.response.defer(ephemeral=True)
        
        # Parse the flight groups input
        flight_groups = self.flight_groups_input.value.strip().split('\n')
        flight_groups = [fg.strip() for fg in flight_groups if fg.strip()]
        
        # Validate the flight group names
        ship_cog = interaction.client.get_cog("ShipsCog")
        if ship_cog:
            valid_flight_groups = []
            invalid_flight_groups = []
            
            for fg_name in flight_groups:
                try:
                    # Get flight group info
                    fg = await ship_cog.registry.get_flight_group(fg_name)
                    if fg:
                        valid_flight_groups.append(fg_name)
                    else:
                        invalid_flight_groups.append(fg_name)
                except Exception as e:
                    logger.error(f"Error validating flight group: {e}")
                    invalid_flight_groups.append(fg_name)
            
            # Update the mission's fleet assignment
            from mission_fleet_integration import FleetAssignment
            if not hasattr(self.mission, 'fleet_assignment'):
                self.mission.fleet_assignment = FleetAssignment()
            
            self.mission.fleet_assignment.assigned_flight_groups = set(valid_flight_groups)
            
            # Save the mission data
            self.cog.save_missions()
            
            # Create response message
            if invalid_flight_groups:
                await interaction.followup.send(
                    f"✅ Assigned {len(valid_flight_groups)} flight groups to the mission.\n"
                    f"⚠️ {len(invalid_flight_groups)} invalid flight groups were ignored: {', '.join(invalid_flight_groups)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Successfully assigned {len(valid_flight_groups)} flight groups to the mission.",
                    ephemeral=True
                )
            
            # Update the mission view
            await self.cog.update_mission_view(self.mission)
        else:
            await interaction.followup.send(
                "❌ Error: Flight group system not available.",
                ephemeral=True
            )


class SquadronSelectionModal(discord.ui.Modal):
    """Modal for selecting squadrons."""
    
    def __init__(self, cog, mission):
        super().__init__(title=f"Select Squadrons for {mission.name}")
        self.cog = cog
        self.mission = mission
        
        # Create a text input for entering squadron names
        self.squadrons_input = discord.ui.TextInput(
            label="Enter Squadron Names (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="1st Squadron\n2nd Squadron",
            required=False,
            default="\n".join(getattr(mission, 'fleet_assignment', {}).get('assigned_squadrons', []))
        )
        self.add_item(self.squadrons_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process the submitted squadron selections."""
        await interaction.response.defer(ephemeral=True)
        
        # Parse the squadrons input
        squadrons = self.squadrons_input.value.strip().split('\n')
        squadrons = [sq.strip() for sq in squadrons if sq.strip()]
        
        # Validate the squadron names
        ship_cog = interaction.client.get_cog("ShipsCog")
        if ship_cog:
            valid_squadrons = []
            invalid_squadrons = []
            
            for sq_name in squadrons:
                try:
                    # Get squadron info
                    sq = await ship_cog.registry.get_squadron(sq_name)
                    if sq:
                        valid_squadrons.append(sq_name)
                    else:
                        invalid_squadrons.append(sq_name)
                except Exception as e:
                    logger.error(f"Error validating squadron: {e}")
                    invalid_squadrons.append(sq_name)
            
            # Update the mission's fleet assignment
            from mission_fleet_integration import FleetAssignment
            if not hasattr(self.mission, 'fleet_assignment'):
                self.mission.fleet_assignment = FleetAssignment()
            
            self.mission.fleet_assignment.assigned_squadrons = set(valid_squadrons)
            
            # Save the mission data
            self.cog.save_missions()
            
            # Create response message
            if invalid_squadrons:
                await interaction.followup.send(
                    f"✅ Assigned {len(valid_squadrons)} squadrons to the mission.\n"
                    f"⚠️ {len(invalid_squadrons)} invalid squadrons were ignored: {', '.join(invalid_squadrons)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Successfully assigned {len(valid_squadrons)} squadrons to the mission.",
                    ephemeral=True
                )
            
            # Update the mission view
            await self.cog.update_mission_view(self.mission)
        else:
            await interaction.followup.send(
                "❌ Error: Squadron system not available.",
                ephemeral=True
            )


class JoinAsCommanderModal(discord.ui.Modal):
    """Modal for commander to join and bring their flight group/squadron/ship."""
    
    def __init__(self, cog, mission, commander):
        super().__init__(title=f"Join Mission as Commander")
        self.cog = cog
        self.mission = mission
        self.commander = commander
        
        # Create a select dropdown for role
        self.role_input = discord.ui.TextInput(
            label="Your Role",
            placeholder="Your role in the mission (e.g., Squadron Commander)",
            required=True,
            max_length=100
        )
        self.add_item(self.role_input)
        
        # Create a select for asset type
        self.asset_type = discord.ui.TextInput(
            label="Asset Type",
            placeholder="Flight Group, Squadron, or Ship",
            required=True,
            max_length=20
        )
        self.add_item(self.asset_type)
        
        # Create a select for asset name
        self.asset_name = discord.ui.TextInput(
            label="Asset Name/ID",
            placeholder="Enter the name of your flight group, squadron, or ship registry",
            required=True,
            max_length=100
        )
        self.add_item(self.asset_name)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process the commander's join request."""
        await interaction.response.defer(ephemeral=True)
        
        role = self.role_input.value.strip()
        asset_type = self.asset_type.value.lower().strip()
        asset_name = self.asset_name.value.strip()
        
        # Validate asset type
        if asset_type not in ['flight group', 'squadron', 'ship']:
            await interaction.followup.send(
                "❌ Invalid asset type. Please enter 'Flight Group', 'Squadron', or 'Ship'.",
                ephemeral=True
            )
            return
        
        # Validate command authority
        ship_cog = interaction.client.get_cog("ShipsCog")
        if not ship_cog:
            await interaction.followup.send(
                "❌ Error: Fleet system not available.",
                ephemeral=True
            )
            return
        
        # Import checking functions
        from mission_fleet_integration import (
            check_flight_group_command,
            check_squadron_command,
            check_ship_command
        )
        
        has_command = False
        if asset_type == 'flight group':
            has_command = await check_flight_group_command(interaction.user, asset_name)
            if has_command:
                # Add flight group to mission
                if not hasattr(self.mission, 'fleet_assignment'):
                    from mission_fleet_integration import FleetAssignment
                    self.mission.fleet_assignment = FleetAssignment()
                self.mission.fleet_assignment.assigned_flight_groups.add(asset_name)
                
                # Add commander as participant
                success = self.mission.add_participant(
                    interaction.user.id,
                    f"Flight Group Commander: {asset_name}",
                    role
                )
                
                if success:
                    await interaction.followup.send(
                        f"✅ You have joined the mission as {role} with your flight group '{asset_name}'.",
                        ephemeral=True
                    )
                    
                    # Add history entry
                    self.mission.add_history_entry(
                        "join_as_commander",
                        interaction.user.id,
                        f"Joined as {role} with flight group {asset_name}"
                    )
                    
                    # Save mission data
                    self.cog.save_missions()
                    
                    # Update mission view
                    await self.cog.update_mission_view(self.mission)
                else:
                    await interaction.followup.send(
                        "❌ Failed to join the mission. The mission may be full.",
                        ephemeral=True
                    )
            
        elif asset_type == 'squadron':
            has_command = await check_squadron_command(interaction.user, asset_name)
            if has_command:
                # Add squadron to mission
                if not hasattr(self.mission, 'fleet_assignment'):
                    from mission_fleet_integration import FleetAssignment
                    self.mission.fleet_assignment = FleetAssignment()
                self.mission.fleet_assignment.assigned_squadrons.add(asset_name)
                
                # Add commander as participant
                success = self.mission.add_participant(
                    interaction.user.id,
                    f"Squadron Commander: {asset_name}",
                    role
                )
                
                if success:
                    await interaction.followup.send(
                        f"✅ You have joined the mission as {role} with your squadron '{asset_name}'.",
                        ephemeral=True
                    )
                    
                    # Add history entry
                    self.mission.add_history_entry(
                        "join_as_commander",
                        interaction.user.id,
                        f"Joined as {role} with squadron {asset_name}"
                    )
                    
                    # Save mission data
                    self.cog.save_missions()
                    
                    # Update mission view
                    await self.cog.update_mission_view(self.mission)
                else:
                    await interaction.followup.send(
                        "❌ Failed to join the mission. The mission may be full.",
                        ephemeral=True
                    )
        
        elif asset_type == 'ship':
            has_command = await check_ship_command(interaction.user, asset_name)
            if has_command:
                # Add ship to mission
                if not hasattr(self.mission, 'fleet_assignment'):
                    from mission_fleet_integration import FleetAssignment
                    self.mission.fleet_assignment = FleetAssignment()
                self.mission.fleet_assignment.assigned_ships.add(asset_name)
                
                # Look up ship name from registry
                ship_name = "Registered Ship"
                try:
                    results = await ship_cog.registry.search_registry(asset_name)
                    if results:
                        ship_info = results[0]
                        ship_name = ship_info.get('Ship Name', ship_name)
                except Exception:
                    pass
                
                # Add commander as participant
                success = self.mission.add_participant(
                    interaction.user.id,
                    ship_name,
                    role
                )
                
                if success:
                    await interaction.followup.send(
                        f"✅ You have joined the mission as {role} with your ship '{ship_name}' ({asset_name}).",
                        ephemeral=True
                    )
                    
                    # Add history entry
                    self.mission.add_history_entry(
                        "join_as_commander",
                        interaction.user.id,
                        f"Joined as {role} with ship {ship_name} ({asset_name})"
                    )
                    
                    # Save mission data
                    self.cog.save_missions()
                    
                    # Update mission view
                    await self.cog.update_mission_view(self.mission)
                else:
                    await interaction.followup.send(
                        "❌ Failed to join the mission. The mission may be full.",
                        ephemeral=True
                    )
        
        if not has_command:
            await interaction.followup.send(
                f"❌ You do not have command authority over the {asset_type} '{asset_name}'.",
                ephemeral=True
            )


class CommanderJoinView(discord.ui.View):
    """View for commander to join a mission with their assets."""
    
    def __init__(self, cog, mission):
        super().__init__(timeout=180)
        self.cog = cog
        self.mission = mission
    
    @discord.ui.button(label="Join as Flight Group Commander", style=discord.ButtonStyle.primary, row=0)
    async def join_as_flight_group_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join as a flight group commander."""
        # Check if user is a flight group commander
        ship_cog = interaction.client.get_cog("ShipsCog")
        if not ship_cog:
            await interaction.response.send_message(
                "❌ Error: Fleet system not available.",
                ephemeral=True
            )
            return
        
        # Show modal to select flight group and role
        modal = JoinAsCommanderModal(self.cog, self.mission, interaction.user)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Join as Squadron Commander", style=discord.ButtonStyle.primary, row=0)
    async def join_as_squadron_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join as a squadron commander."""
        # Check if user is a squadron commander
        ship_cog = interaction.client.get_cog("ShipsCog")
        if not ship_cog:
            await interaction.response.send_message(
                "❌ Error: Fleet system not available.",
                ephemeral=True
            )
            return
        
        # Show modal to select squadron and role
        modal = JoinAsCommanderModal(self.cog, self.mission, interaction.user)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Join as Ship Commander", style=discord.ButtonStyle.primary, row=0)
    async def join_as_ship_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Join as a ship commander."""
        # Check if user has any registered ships
        ship_cog = interaction.client.get_cog("ShipsCog")
        if not ship_cog:
            await interaction.response.send_message(
                "❌ Error: Fleet system not available.",
                ephemeral=True
            )
            return
        
        # Show modal to select ship and role
        modal = JoinAsCommanderModal(self.cog, self.mission, interaction.user)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel joining the mission."""
        await interaction.response.send_message("Commander join cancelled.", ephemeral=True)
        self.stop()