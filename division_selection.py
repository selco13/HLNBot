# cogs/fleet_selection.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import os
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger('fleet_selection')

class FleetSelectionUI(discord.ui.View):
    """UI for selecting a fleet component upon promotion to Crewman."""
    
    def __init__(self, cog, member: discord.Member):
        super().__init__(timeout=1800)  # 30 minute timeout
        self.cog = cog
        self.member = member
        self.add_fleet_select()
        
    def add_fleet_select(self):
        """Add the fleet component selection dropdown."""
        # Get available fleet components
        fleet_components = [
            "Command Staff",
            "Navy Fleet",
            "Marine Expeditionary Force",
            "Industrial & Logistics Wing",
            "Support & Medical Fleet",
            "Exploration & Intelligence Wing",
            "Non-Fleet"  # Include this as an option for those who want to stay unaffiliated
        ]
        
        # Create select menu
        select = discord.ui.Select(
            placeholder="Choose your fleet component",
            options=[
                discord.SelectOption(
                    label=fleet,
                    value=fleet,
                    description=f"Join the {fleet}"
                ) for fleet in fleet_components
            ]
        )
        
        # Set callback
        select.callback = self.fleet_callback
        self.add_item(select)
        
    async def fleet_callback(self, interaction: discord.Interaction):
        """Handle fleet component selection."""
        # Security check
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(
                "This selection is not for you.",
                ephemeral=True
            )
            return
            
        selected_fleet = interaction.data["values"][0]
        
        # Update fleet component selection
        success, error = await self.cog.assign_fleet(
            self.member,
            selected_fleet
        )
        
        if success:
            embed = discord.Embed(
                title="Fleet Assignment",
                description=f"You have been assigned to the {selected_fleet}!",
                color=discord.Color.green()
            )
            
            if selected_fleet != "Non-Fleet":
                embed.add_field(
                    name="Next Steps",
                    value=(
                        "1. Introduce yourself in your fleet component's channel\n"
                        "2. Review fleet requirements and training materials\n"
                        "3. Connect with your fleet leadership about role specialization options"
                    ),
                    inline=False
                )
                
                # Add specialization information
                embed.add_field(
                    name="Role Specialization",
                    value=(
                        "Speak with your fleet leadership about specialization options "
                        "available within your fleet component. Each fleet has different "
                        "specialized roles you can pursue."
                    ),
                    inline=False
                )
            
            await interaction.response.edit_message(
                content=None,
                embed=embed,
                view=None
            )
            
            # Send announcement
            announcement_channel = self.cog.bot.get_channel(int(os.getenv('ANNOUNCEMENT_CHANNEL_ID', 0)))
            if announcement_channel:
                await announcement_channel.send(
                    f"🎉 {self.member.mention} has joined the {selected_fleet}!"
                )
                
        else:
            await interaction.response.send_message(
                f"❌ Error assigning fleet component: {error}",
                ephemeral=True
            )
            self.stop()
    
    async def on_timeout(self):
        """Handle view timeout."""
        try:
            # Try to edit the original message
            original_message = await self.message.edit(
                content="Fleet selection timed out. Use `/select_fleet` to try again.",
                view=None
            )
        except:
            # If we can't find the original message, try to DM the user
            try:
                await self.member.send(
                    "Your fleet selection has timed out. Use `/select_fleet` in the server to try again."
                )
            except:
                pass

class FleetSelectionCog(commands.Cog):
    """Cog for handling fleet component selection when a member is promoted to Crewman."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("FleetSelectionCog initialized")
        
    @app_commands.command(
        name="select_fleet",
        description="Select your fleet component as a Crewman or higher."
    )
    async def select_fleet(self, interaction: discord.Interaction):
        """Command to select or change fleet component."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check if user has the required rank
            has_member_role = discord.utils.get(interaction.user.roles, name="Member")
            has_crewman_rank = any(discord.utils.get(interaction.user.roles, name=rank) for rank in [
                "Crewman", "Crewman Apprentice", "Senior Crewman", "Master Crewman",
                "Petty Officer 3rd Class", "Petty Officer 2nd Class", "Petty Officer 1st Class",
                "Chief Petty Officer", "Ensign", "Lieutenant Junior Grade", "Lieutenant",
                "Lieutenant Commander", "Commander", "Captain", "Fleet Captain",
                "Commodore", "Rear Admiral", "Vice Admiral", "Admiral"
            ])
            
            if not has_member_role or not has_crewman_rank:
                await interaction.followup.send(
                    "❌ You must be a Member with Crewman rank or higher to select a fleet component.",
                    ephemeral=True
                )
                return
                
            # Show fleet selection
            view = FleetSelectionUI(self, interaction.user)
            embed = discord.Embed(
                title="Fleet Selection",
                description=(
                    "Select which fleet component you would like to join. Each fleet has its own "
                    "focus areas, ships, and responsibilities within the HLN organization."
                ),
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Command Staff",
                value="Leadership, strategic planning, and fleet coordination.",
                inline=False
            )
            
            embed.add_field(
                name="Navy Fleet",
                value="Space combat, escort duties, fleet security, and force projection operations.",
                inline=False
            )
            
            embed.add_field(
                name="Marine Expeditionary Force",
                value="Boarding operations, ground combat, station security, and planetary operations.",
                inline=False
            )
            
            embed.add_field(
                name="Industrial & Logistics Wing",
                value="Resource acquisition, supply chain management, transport, salvage, and engineering.",
                inline=False
            )
            
            embed.add_field(
                name="Support & Medical Fleet",
                value="Medical assistance, operations support, fleet repairs, and support services.",
                inline=False
            )
            
            embed.add_field(
                name="Exploration & Intelligence Wing",
                value="Reconnaissance, intelligence gathering, science, research, and communications.",
                inline=False
            )
            
            embed.add_field(
                name="Non-Fleet",
                value="Remain unaffiliated with any specific fleet component.",
                inline=False
            )
            
            message = await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True
            )
            view.message = message
                
        except Exception as e:
            logger.error(f"Error in select_fleet: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your request.",
                ephemeral=True
            )
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Listen for role changes to detect promotion to Crewman."""
        try:
            # Check if Member role was added
            before_member = discord.utils.get(before.roles, name="Member")
            after_member = discord.utils.get(after.roles, name="Member")
            
            if not before_member and after_member:
                # Member role was added
                logger.info(f"Member role added to {after.id}")
                # No immediate action needed - they'll be CR rank
                return
                
            # Look for rank change to Crewman from Crewman Recruit
            before_rank = discord.utils.get(before.roles, name="Crewman Recruit")
            after_rank = discord.utils.get(after.roles, name="Crewman")
            
            if before_rank and after_rank:
                # Promoted from CR to Crewman - offer fleet selection
                logger.info(f"User {after.id} promoted to Crewman - sending fleet selection")
                
                # Check if they already have a fleet component other than Non-Fleet
                has_other_fleet = False
                for role in after.roles:
                    if role.name in ["Command Staff", "Navy Fleet", "Marine Expeditionary Force", 
                                     "Industrial & Logistics Wing", "Support & Medical Fleet", 
                                     "Exploration & Intelligence Wing"]:
                        has_other_fleet = True
                        break
                        
                if not has_other_fleet:
                    # Send fleet selection DM
                    try:
                        embed = discord.Embed(
                            title="Fleet Selection Available",
                            description=(
                                "Congratulations on your promotion to Crewman! You are now eligible "
                                "to select a fleet component to join."
                            ),
                            color=discord.Color.green()
                        )
                        
                        embed.add_field(
                            name="Select Your Fleet",
                            value=(
                                "Use the `/select_fleet` command in the server to choose your fleet component. "
                                "This will determine your career path and role specialization opportunities."
                            ),
                            inline=False
                        )
                        
                        embed.add_field(
                            name="Available Fleet Components",
                            value=(
                                "• Command Staff - Leadership and strategic coordination\n"
                                "• Navy Fleet - Combat and fleet security\n"
                                "• Marine Expeditionary Force - Boarding and ground operations\n"
                                "• Industrial & Logistics Wing - Resources and supply chain\n"
                                "• Support & Medical Fleet - Medical and support services\n"
                                "• Exploration & Intelligence Wing - Science and intelligence"
                            ),
                            inline=False
                        )
                        
                        await after.send(embed=embed)
                        logger.info(f"Sent fleet selection DM to {after.id}")
                    except discord.Forbidden:
                        logger.warning(f"Could not send fleet selection DM to {after.id}")
                        
                        # Try sending in a public channel
                        fleet_channel = self.bot.get_channel(int(os.getenv('FLEET_CHANNEL_ID', 0)))
                        if fleet_channel:
                            await fleet_channel.send(
                                f"{after.mention} Congratulations on your promotion to Crewman! "
                                "You can now select a fleet component using the `/select_fleet` command."
                            )
                
        except Exception as e:
            logger.error(f"Error in on_member_update: {e}")
    
    async def assign_fleet(self, member: discord.Member, fleet_component: str) -> tuple[bool, Optional[str]]:
        """Assign a user to a fleet component."""
        try:
            # Get the fleet component role
            fleet_role = discord.utils.get(member.guild.roles, name=fleet_component)
            if not fleet_role:
                return False, f"Could not find the {fleet_component} role"
                
            # Remove other fleet component roles
            other_fleet_roles = [
                role for role in member.roles
                if role.name in ["Command Staff", "Navy Fleet", "Marine Expeditionary Force", 
                                "Industrial & Logistics Wing", "Support & Medical Fleet", 
                                "Exploration & Intelligence Wing", "Non-Fleet"]
                and role.name != fleet_component
            ]
            
            if other_fleet_roles:
                await member.remove_roles(*other_fleet_roles, reason="Fleet component change")
                
            # Add new fleet component role
            await member.add_roles(fleet_role, reason="Fleet component assignment")
            
            # Update database record - Now with improved error handling
            db_success = await self.update_fleet_in_database(member.id, fleet_component)
            if not db_success:
                # Just log the warning, don't fail the whole operation
                logger.warning(f"Failed to update fleet component in database for {member.id} - continuing with Discord role assignment")
                
            # Import fleet codes from constants
            try:
                from .constants import FLEET_COMPONENTS
                fleet_code = FLEET_COMPONENTS.get(fleet_component, 'ND')
                
                # Don't actually modify nickname here - let it be handled by NicknameManager
                # This is just for verification
                logger.info(f"Fleet assignment complete for {member.id}: {fleet_component} ({fleet_code})")
                
            except ImportError as e:
                logger.error(f"Error importing fleet constants: {e}")
                # Continue anyway since this is just for logging
                logger.info(f"Fleet assignment complete for {member.id}: {fleet_component}")
                
            return True, None
            
        except discord.Forbidden:
            return False, "Bot lacks permission to manage roles"
        except Exception as e:
            logger.error(f"Error assigning fleet component: {e}")
            return False, str(e)
    
    async def update_fleet_in_database(self, user_id: int, fleet_component: str) -> bool:
        """Update the member's fleet component in the database."""
        try:
            # Log all parameters for debugging
            logger.debug(f"Updating fleet in database for user ID: {user_id}, Fleet: {fleet_component}")
            logger.debug(f"DOC_ID: {os.getenv('DOC_ID')}, TABLE_ID: {os.getenv('TABLE_ID')}")
            
            # -------------------------------------------------------------------------------
            # APPROACH 1: Try to get the row directly using the row listing endpoint
            # This avoids issues with the query syntax by getting all rows and filtering manually
            # -------------------------------------------------------------------------------
            
            # Get all rows (with a reasonable limit)
            all_rows_response = await self.bot.coda_client.request(
                'GET',
                f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                params={
                    'useColumnNames': 'true',
                    'limit': 200  # Adjust as needed based on your table size
                }
            )
            
            row_id = None
            
            if all_rows_response and 'items' in all_rows_response:
                logger.debug(f"Retrieved {len(all_rows_response['items'])} rows from database")
                
                # Try to find the user's row by Discord ID
                for row in all_rows_response['items']:
                    if 'values' in row and 'Discord User ID' in row['values']:
                        db_user_id = row['values']['Discord User ID']
                        
                        # Try both string and int comparison
                        if str(db_user_id) == str(user_id):
                            row_id = row['id']
                            logger.info(f"Found user {user_id} with row ID {row_id}")
                            break
            
            # -------------------------------------------------------------------------------
            # APPROACH 2: If we still don't have a row ID, try multiple query formats
            # -------------------------------------------------------------------------------
            if not row_id:
                logger.warning(f"Could not find user by browsing rows, trying direct queries")
                
                # Try multiple query formats to find the user
                queries = [
                    f'"Discord User ID":{user_id}',         # As number
                    f'"Discord User ID":"{user_id}"',       # As string
                    f'Discord User ID:{user_id}',           # Without quotes in column name
                    f'Discord User ID:"{user_id}"',         # Without quotes in column name, string value
                    f'"Discord User ID" = {user_id}',       # Using equals operator
                    f'"Discord User ID" = "{user_id}"'      # Using equals operator with string
                ]
                
                # Try each query format until we find a match
                for query in queries:
                    logger.debug(f"Trying query: {query}")
                    
                    response = await self.bot.coda_client.request(
                        'GET',
                        f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                        params={
                            'query': query,
                            'useColumnNames': 'true',
                            'limit': 1
                        }
                    )
                    
                    if response and 'items' in response and len(response['items']) > 0:
                        row_id = response['items'][0].get('id')
                        logger.info(f"Found user {user_id} with row ID {row_id} using query: {query}")
                        break
            
            # -------------------------------------------------------------------------------
            # APPROACH 3: If we still can't find the user, try to create a new record
            # -------------------------------------------------------------------------------
            if not row_id:
                logger.warning(f"Could not find user {user_id} in database - creating new record")
                
                try:
                    # Create a new user record
                    create_response = await self.bot.coda_client.request(
                        'POST',
                        f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows',
                        data={
                            'rows': [
                                {
                                    'cells': [
                                        {'column': 'Discord User ID', 'value': str(user_id)},
                                        {'column': 'Fleet Component', 'value': fleet_component},
                                        {'column': 'Division', 'value': fleet_component}, # For backward compatibility
                                        {'column': 'Fleet Updated', 'value': datetime.now(timezone.utc).isoformat()},
                                        {'column': 'Join Date', 'value': datetime.now(timezone.utc).isoformat()},
                                        {'column': 'Status', 'value': 'Active'}
                                    ]
                                }
                            ]
                        }
                    )
                    
                    if create_response and 'items' in create_response and len(create_response['items']) > 0:
                        logger.info(f"Created new user record for {user_id} with fleet {fleet_component}")
                        return True
                    else:
                        logger.error(f"Failed to create user record for {user_id}")
                        return False
                        
                except Exception as e:
                    logger.error(f"Error creating user record: {e}")
                    return False
            
            # -------------------------------------------------------------------------------
            # Update the user's fleet component
            # -------------------------------------------------------------------------------
            if row_id:
                # Update fleet component (and Division for backward compatibility)
                update_response = await self.bot.coda_client.request(
                    'PUT',
                    f'docs/{os.getenv("DOC_ID")}/tables/{os.getenv("TABLE_ID")}/rows/{row_id}',
                    data={
                        'row': {
                            'cells': [
                                {'column': 'Fleet Component', 'value': fleet_component},
                                {'column': 'Division', 'value': fleet_component}, # For backward compatibility
                                {'column': 'Fleet Updated', 'value': datetime.now(timezone.utc).isoformat()}
                            ]
                        }
                    }
                )
                
                if update_response is not None:
                    logger.info(f"Successfully updated fleet to {fleet_component} for user {user_id}")
                    return True
                else:
                    logger.error(f"Failed to update fleet for user {user_id} - null response")
                    return False
            else:
                logger.error(f"Could not find or create record for user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating fleet in database: {e}")
            return False

async def setup(bot: commands.Bot):
    await bot.add_cog(FleetSelectionCog(bot))
    logger.info("FleetSelectionCog loaded")