"""Mission Fleet Setup Module

This module integrates fleet functionality with the mission system.
It hooks into the MissionCog to add fleet-related commands and features without
registering duplicate commands.
"""

import logging
from typing import Optional, Dict, List, Any
import discord
from discord.ext import commands
import asyncio
import sys
import importlib

# Correct imports based on the actual directory structure
from .missions import create_interactive_mission_view
from .mission_system.mission_fleet_integration import FleetAssignment, setup_fleet_assignment_view
from .mission_system.mission_fleet_ui import FleetAssetSelectionView, CommanderJoinView

logger = logging.getLogger('mission_fleet_setup')
logger.setLevel(logging.INFO)

# Global flag to track if fleet integration is complete
FLEET_INTEGRATION_COMPLETE = False

async def integrate_fleet_functionality(mission_cog):
    """Integrate fleet functionality with the mission system."""
    try:
        logger.info("Integrating fleet functionality into mission system")
        
        # Store reference to the original update_mission_view method
        original_update_mission_view = mission_cog.update_mission_view
        
        # Create enhanced update_mission_view method
        async def enhanced_update_mission_view(mission):
            """Enhanced version that handles fleet assignments."""
            await original_update_mission_view(mission)
            logger.debug(f"Enhanced update_mission_view called for mission {mission.mission_id}")
            
        # Replace the update_mission_view method
        mission_cog.update_mission_view = enhanced_update_mission_view
        
        # Add fleet assignment methods to MissionCog
        from .mission_system.mission_cog_extensions import MissionCogExtensions
        mission_cog.assign_fleet_to_mission = lambda mission_id, fleet_assignment: MissionCogExtensions.assign_fleet_to_mission(mission_cog, mission_id, fleet_assignment)
        mission_cog.remove_fleet_from_mission = lambda mission_id, fleet_assignment: MissionCogExtensions.remove_fleet_from_mission(mission_cog, mission_id, fleet_assignment)
        mission_cog.get_missions_with_fleet_asset = lambda asset_type, asset_id: MissionCogExtensions.get_missions_with_fleet_asset(mission_cog, asset_type, asset_id)
        
        # ---------------------------------------------------------------
        # COMMANDS: Instead of registering new commands, add handlers to 
        # the MissionCog class that will be used by existing commands
        # ---------------------------------------------------------------
        
        # Add a method to handle fleet assignment
        async def handle_fleet_assignment(self, ctx_or_interaction, mission_id):
            """Handle fleet assignment for both prefix and slash commands."""
            is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
            if is_interaction:
                await ctx_or_interaction.response.defer(ephemeral=True)
                send_method = ctx_or_interaction.followup.send
            else:
                send_method = ctx_or_interaction.send
                
            mission = self.missions.get(mission_id)
            if not mission:
                await send_method("Mission not found.")
                return
                
            view = await setup_fleet_assignment_view(self, mission)
            if view:
                await send_method(
                    f"Select fleet assets to assign to mission '{mission.name}':",
                    view=view,
                    ephemeral=is_interaction
                )
            else:
                await send_method("Failed to create fleet assignment view. Check if ShipsCog is loaded.")
                
        # Add a method to handle commander join
        async def handle_commander_join(self, interaction, mission_id):
            """Handle commander join requests."""
            await interaction.response.defer(ephemeral=True)
            
            mission = self.missions.get(mission_id)
            if not mission:
                await interaction.followup.send("Mission not found.")
                return
                
            # Show commander join options
            view = CommanderJoinView(self, mission)
            await interaction.followup.send(
                f"Select how you want to join mission '{mission.name}' as a commander:",
                view=view,
                ephemeral=True
            )
        
        # Add the handler methods to the mission_cog
        mission_cog.handle_fleet_assignment = handle_fleet_assignment.__get__(mission_cog)
        mission_cog.handle_commander_join = handle_commander_join.__get__(mission_cog)
        
        # Add support for fleet assets button and callbacks by extending InteractiveMissionView
        from .missions import InteractiveMissionView
        
        # Save the original __init__ method - only if we haven't already monkey-patched it
        if not hasattr(InteractiveMissionView, "_original_init"):
            InteractiveMissionView._original_init = InteractiveMissionView.__init__
            
            # Create enhanced __init__ method that adds fleet buttons
            def enhanced_init(self, cog, mission):
                # Call the original __init__
                InteractiveMissionView._original_init(self, cog, mission)
                
                # Add fleet button if appropriate
                if mission.status not in [mission.status.COMPLETED, mission.status.CANCELLED]:
                    fleet_button = discord.ui.Button(
                        label="Fleet Assets", 
                        style=discord.ButtonStyle.secondary,
                        custom_id="fleet_assets",
                        row=1
                    )
                    fleet_button.callback = self.fleet_assets_callback
                    self.add_item(fleet_button)
                    
            # Add the fleet assets callback method if not already added
            if not hasattr(InteractiveMissionView, "fleet_assets_callback"):
                async def fleet_assets_callback(self, interaction: discord.Interaction):
                    """Callback for the fleet assets button"""
                    # Create a fleet asset selection view
                    view = FleetAssetSelectionView(self.cog, self.mission.mission_id)
                    await interaction.response.send_message(
                        f"Manage fleet assets for mission '{self.mission.name}':",
                        view=view,
                        ephemeral=True
                    )
                
                # Add the fleet assets callback
                InteractiveMissionView.fleet_assets_callback = fleet_assets_callback
                
            # Replace the __init__ method
            InteractiveMissionView.__init__ = enhanced_init
            logger.info("Enhanced InteractiveMissionView with fleet functionality")
        
        # Override update_mission_view to use our patched function
        async def update_mission_view_with_fleet(mission):
            """Update the mission view with fleet functionality"""
            channel = mission_cog.bot.get_channel(mission.channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(mission.message_id)
                    view = await create_interactive_mission_view(mission_cog, mission, mission.leader_id)
                    await message.edit(embed=mission.to_embed(mission_cog.bot), view=view)
                except Exception as e:
                    logger.error(f"Failed to update mission view: {e}")
        
        # Replace the update_mission_view method again with our fully integrated version
        mission_cog.update_mission_view = update_mission_view_with_fleet
        
        # -------------------------------------------------------------------
        # ADD COMMAND HOOKS: Add the fleet command callbacks to existing commands
        # -------------------------------------------------------------------
        
        # Find existing fleet commands or create them
        try:
            # Add fleet command callbacks
            @mission_cog.bot.command(name="fleet")
            @commands.has_permissions(administrator=True)
            async def fleet_command(ctx, subcommand: str = None, mission_id: str = None):
                """Manage fleet assets for missions.
                
                Subcommands:
                  assign: Assign fleet assets to a mission
                """
                if subcommand == "assign" and mission_id:
                    await mission_cog.handle_fleet_assignment(ctx, mission_id)
                else:
                    await ctx.send("Usage: !fleet assign <mission_id>")
            
            # Check if we already have the command
            existing_command = mission_cog.bot.get_command("fleet")
            if existing_command:
                # Remove our temporary command if it exists
                mission_cog.bot.remove_command("fleet")
                # Make sure the existing command has our callback
                existing_command.callback = fleet_command.callback
                logger.info("Updated existing fleet command with new functionality")
            else:
                # Our command was registered, so keep it
                logger.info("Registered new fleet command")
                
            # Set up a listener for the application command interaction
            @mission_cog.bot.listen('on_interaction')
            async def on_interaction(interaction):
                """Handle interactions for fleet commands"""
                if not interaction.type == discord.InteractionType.application_command:
                    return
                    
                # Check if this is a fleet-related command
                command_name = interaction.data.get('name', '')
                if command_name == 'fleet_assign':
                    # Get the mission_id from options
                    options = interaction.data.get('options', [])
                    mission_id = None
                    for option in options:
                        if option.get('name') == 'mission_id':
                            mission_id = option.get('value')
                    
                    if mission_id:
                        await mission_cog.handle_fleet_assignment(interaction, mission_id)
                    else:
                        await interaction.response.send_message("Mission ID is required", ephemeral=True)
                        
                elif command_name == 'join_as_commander':
                    # Get the mission_id from options
                    options = interaction.data.get('options', [])
                    mission_id = None
                    for option in options:
                        if option.get('name') == 'mission_id':
                            mission_id = option.get('value')
                    
                    if mission_id:
                        await mission_cog.handle_commander_join(interaction, mission_id)
                    else:
                        await interaction.response.send_message("Mission ID is required", ephemeral=True)
                        
            logger.info("Added interaction listener for fleet slash commands")
        except Exception as e:
            logger.error(f"Error setting up command hooks: {e}", exc_info=True)
        
        logger.info("Fleet functionality integrated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error integrating fleet functionality: {e}", exc_info=True)
        return False

async def setup(bot):
    """Setup the mission fleet integration."""
    global FLEET_INTEGRATION_COMPLETE
    
    # Don't wait for the bot to be ready, but check if MissionCog is available directly
    mission_cog = bot.get_cog('MissionCog')
    if not mission_cog:
        # If MissionCog isn't loaded yet, schedule this to run later when the cog is available
        logger.info("MissionCog not found yet, scheduling fleet integration for later")
        
        async def check_for_mission_cog():
            """Periodically check for the MissionCog"""
            tries = 0
            max_tries = 10
            while tries < max_tries:
                await asyncio.sleep(3)  # Wait 3 seconds between checks
                mission_cog = bot.get_cog('MissionCog')
                if mission_cog:
                    logger.info(f"MissionCog found after {tries+1} attempts, continuing with setup")
                    await complete_setup(bot, mission_cog)
                    return
                tries += 1
                
            logger.error(f"MissionCog not found after {max_tries} attempts, giving up")
            
        # Create a task to run the checker, but don't block the current setup
        bot.loop.create_task(check_for_mission_cog())
        
        # Allow this setup function to complete successfully so it doesn't block other extensions
        return
    
    # If MissionCog is already available, proceed with setup immediately
    await complete_setup(bot, mission_cog)

async def complete_setup(bot, mission_cog):
    """Complete the setup with a valid MissionCog instance."""
    global FLEET_INTEGRATION_COMPLETE
    
    if FLEET_INTEGRATION_COMPLETE:
        logger.info("Fleet integration already completed, skipping")
        return
        
    # Initialize the Ship class if it's not already initialized
    try:
        from .mission_system.ship_data import Ship
        if not hasattr(Ship, '_ships_cache') or not Ship._ships_cache:
            file_path = bot.config.get('ship_data_path', None)
            success = Ship.load_ships(file_path)
            if not success:
                logger.warning("Failed to load ship data, fleet functionality may be limited")
        
        # Integrate fleet functionality
        success = await integrate_fleet_functionality(mission_cog)
        if success:
            logger.info("Mission fleet setup complete")
            FLEET_INTEGRATION_COMPLETE = True
        else:
            logger.error("Mission fleet setup failed")
    except Exception as e:
        logger.error(f"Error in mission fleet setup: {e}", exc_info=True)