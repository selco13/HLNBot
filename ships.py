import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import List, Optional, Dict, Any, Union
import os
from datetime import datetime
import asyncio

from .mission_system.ship_data import Ship
from .managers.ships_registry_manager import ShipsRegistryManager
import config

logger = logging.getLogger('ships')
logger.setLevel(logging.DEBUG)

# Constants for pagination
SHIPS_PER_PAGE = 8
MANUFACTURERS_PER_PAGE = 5

# Environment variables - use config module
GUILD_ID = config.GUILD_ID
DOC_ID = config.DOC_ID
SHIPS_TABLE_ID = config.SHIPS_TABLE_ID
USERS_TABLE_ID = config.USERS_TABLE_ID

def get_ship_role_emoji(role: str) -> str:
    """Get emoji for ship role."""
    role_emojis = {
        "Combat": "⚔️",
        "Transport": "🚢",
        "Exploration": "🧭",
        "Mining": "⛏️",
        "Cargo": "📦",
        "Medical": "🏥",
        "Interdiction": "🛡️",
        "Support": "🔧",
        "Racing": "🏁",
        "Salvage": "🔍",
    }
    return role_emojis.get(role, "🚀")


class PaginatedView(discord.ui.View):
    """Paginated view for discord embeds."""
    
    def __init__(self, pages: List[discord.Embed], timeout: int = 180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.total_pages = len(pages)
        
        # Update button states based on initial page
        self._update_button_states()
        
    def _update_button_states(self):
        """Update button states based on current page."""
        # Disable previous button if on first page
        self.previous_page.disabled = (self.current_page == 0)
        
        # Disable next button if on last page
        self.next_page.disabled = (self.current_page == len(self.pages) - 1)
        
        # Update page counter
        self.page_counter.label = f"{self.current_page + 1}/{self.total_pages}"
        
    @discord.ui.button(label="◀", style=discord.ButtonStyle.gray)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_button_states()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
            
    @discord.ui.button(label="1/1", style=discord.ButtonStyle.gray, disabled=True)
    async def page_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Page counter (disabled button)."""
        # This button is just a page counter and doesn't do anything when clicked
        pass
            
    @discord.ui.button(label="▶", style=discord.ButtonStyle.gray)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_button_states()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)


class ShipActionView(discord.ui.View):
    """View with ship action buttons."""
    
    def __init__(self, registry: ShipsRegistryManager, ship_name: str, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.registry = registry
        self.ship_name = ship_name
        
    @discord.ui.button(label="Assign to Flight Group", style=discord.ButtonStyle.primary)
    async def assign_to_flight_group(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a modal to assign ship to a flight group."""
        modal = ShipAssignmentModal(self.registry, self.ship_name)
        await interaction.response.send_modal(modal)


class ShipAssignmentModal(discord.ui.Modal, title="Assign Ship to Flight Group"):
    """Modal for assigning a ship to a flight group."""
    
    flight_group = discord.ui.TextInput(
        label="Flight Group Name",
        placeholder="Enter flight group name",
        required=True,
        max_length=100
    )
    
    def __init__(self, registry: ShipsRegistryManager, ship_name: str):
        super().__init__()
        self.registry = registry
        self.ship_name = ship_name
        
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission."""
        flight_group_name = self.flight_group.value
        
        # Get flight group to verify it exists
        flight_group = await self.registry.get_flight_group(flight_group_name)
        if not flight_group:
            await interaction.response.send_message(f"Flight group '{flight_group_name}' not found.", ephemeral=True)
            return
            
        # Assign ship to flight group
        success = await self.registry.assign_ship_to_flight_group(self.ship_name, flight_group_name)
        
        if success:
            # Create success embed
            embed = discord.Embed(
                title="Ship Assignment",
                description=f"**{self.ship_name}** has been assigned to flight group **{flight_group_name}**",
                color=discord.Color.green()
            )
            
            # Include squadron info if available
            squadron = flight_group.get('squadron')
            if squadron:
                embed.add_field(name="Squadron", value=squadron, inline=False)
                
            await interaction.response.send_message(embed=embed)
            
            # Log to audit channel if available
            if hasattr(interaction.client, 'audit_logger'):
                audit_message = (
                    f"**Ship Assigned to Flight Group**\n"
                    f"Ship: {self.ship_name}\n"
                    f"Flight Group: {flight_group_name}\n"
                    f"By: {interaction.user.mention} ({interaction.user.display_name})"
                )
                await interaction.client.audit_logger.log(audit_message)
        else:
            await interaction.response.send_message("Failed to assign ship to flight group.", ephemeral=True)

class ShipIntegrationMethods:
    """Methods for integrating profile system with ship registry."""
    
    async def get_flight_group_members(self, flight_group_name: str) -> List[discord.Member]:
        """
        Get all members assigned to a flight group.
        
        This method is called by the ships cog to display member information.
        
        Args:
            flight_group_name: Name of the flight group
            
        Returns:
            List of discord.Member objects
        """
        try:
            # Import needed constants
            import os
            DOC_ID = os.getenv("DOC_ID")
            TABLE_ID = os.getenv("TABLE_ID") or os.getenv("PROFILE_TABLE_ID")
            FIELD_FLIGHT_GROUP = "Flight Group"  # Use column name instead of ID for flexibility
            
            # Query for members assigned to this flight group
            query = f'"{FIELD_FLIGHT_GROUP}":"{flight_group_name}"'
            
            rows = await self.coda_client.get_rows(
                DOC_ID,
                TABLE_ID,
                query=query
            )
            
            # Extract member IDs and get member objects
            members = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = self.bot.get_guild(int(self.GUILD_ID)).get_member(int(discord_id))
                        if member:
                            members.append(member)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            return members
            
        except Exception as e:
            logger.error(f"Error getting flight group members: {e}")
            return []
            
    async def get_squadron_members(self, squadron_name: str) -> List[discord.Member]:
        """
        Get all members assigned to a squadron.
        
        This method is called by the ships cog to display member information.
        
        Args:
            squadron_name: Name of the squadron
            
        Returns:
            List of discord.Member objects
        """
        try:
            # Import needed constants
            import os
            DOC_ID = os.getenv("DOC_ID")
            TABLE_ID = os.getenv("TABLE_ID") or os.getenv("PROFILE_TABLE_ID")
            FIELD_SQUADRON = "Squadron"  # Use column name instead of ID for flexibility
            
            # Query for members assigned to this squadron
            query = f'"{FIELD_SQUADRON}":"{squadron_name}"'
            
            rows = await self.coda_client.get_rows(
                DOC_ID,
                TABLE_ID,
                query=query
            )
            
            # Extract member IDs and get member objects
            members = []
            for row in rows:
                discord_id = row.get('values', {}).get('Discord User ID')
                if discord_id:
                    try:
                        member = self.bot.get_guild(int(self.GUILD_ID)).get_member(int(discord_id))
                        if member:
                            members.append(member)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid Discord ID: {discord_id}")
            
            return members
            
        except Exception as e:
            logger.error(f"Error getting squadron members: {e}")
            return []
            
    async def update_member_assignment(
        self,
        member: discord.Member,
        flight_group: Optional[str] = None,
        squadron: Optional[str] = None,
        position: Optional[str] = None
    ) -> bool:
        """
        Update a member's flight group and squadron assignment.
        
        Args:
            member: Discord member
            flight_group: Flight group name (None to remove)
            squadron: Squadron name (None to remove)
            position: Position in flight group (None to remove)
            
        Returns:
            bool: Success or failure
        """
        try:
            updates = {}
            
            # Add flight group if provided
            if flight_group is not None:
                updates['Flight Group'] = flight_group
                
            # Add squadron if provided
            if squadron is not None:
                updates['Squadron'] = squadron
                
            # Add position to ship assignment if provided
            if position is not None:
                # Get current ship assignment
                member_row = await self.get_member_row(member.id)
                if member_row:
                    ship_assignment = member_row.get('values', {}).get('Ship Assignment', '')
                    
                    # Add position in parentheses if there's a ship assignment
                    if ship_assignment and ship_assignment != 'Unassigned':
                        # Remove any existing position
                        if '(' in ship_assignment:
                            ship_assignment = ship_assignment.split('(')[0].strip()
                            
                        # Add new position
                        updates['Ship Assignment'] = f"{ship_assignment} ({position})"
            
            # Only proceed if there are updates to make
            if not updates:
                return True
                
            # Update the profile
            success = await self.update_profile(
                member,
                updates,
                f"Updated flight assignment"
            )
            
            return success
            
        except Exception as e:
            logger.error(f"Error updating member assignment: {e}")
            return False


class ShipsCog(commands.Cog, name="Ships"):
    """Enhanced ship management cog."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Get the CodaAPIClient from the bot
        self.coda_client = bot.coda_client
        
        # Create ships registry manager
        self.registry = ShipsRegistryManager(
            self.coda_client,
            DOC_ID,
            SHIPS_TABLE_ID,
            USERS_TABLE_ID
        )
        
        # Load ship data
        if not Ship._ships_cache:
            ship_file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'ships.csv')
            success = Ship.load_ships(ship_file_path)
            if success:
                logger.info(f"Loaded {len(Ship._ships_cache)} ships into cache")
            else:
                logger.error(f"Failed to load ships from {ship_file_path}")
            
        # Background task to initialize registry
        self.init_task = asyncio.create_task(self._initialize_registry())
        
    async def _initialize_registry(self):
        """Initialize the registry manager."""
        try:
            success = await self.registry.initialize()
            if success:
                logger.info("Ship registry initialized successfully")
            else:
                logger.error("Failed to initialize ship registry")
        except Exception as e:
            logger.error(f"Error initializing ship registry: {e}")
            
    @staticmethod
    def safe_float_convert(value):
        """Convert a value to float, returning None if it's an empty string."""
        if value == '' or value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
            
    async def cog_unload(self):
        """Clean up when cog is unloaded."""
        # Cancel any pending tasks
        if hasattr(self, 'init_task') and not self.init_task.done():
            self.init_task.cancel()
            
    def get_app_commands(self):
        """Return a list of app commands for logging and reference."""
        return [
            self.ship_info,
            self.commission_ship,
            self.list_ships,
            self.manufacturers,
            self.decommission_ship,
            self.ship_lookup,
            self.transfer_ship,
            self.fleet_stats,
            # Flight group and squadron commands
            self.create_flight_group,
            self.create_squadron,
            self.flight_group_info,
            self.squadron_info,
            self.list_flight_groups,
            self.list_squadrons,
            self.assign_flight_group_to_squadron,
            self.assign_ship_to_flight_group,
            # New commands
            self.registry_report,
            self.refresh_registry_cache
        ]
            
    @app_commands.command(name="ship_info", description="View detailed information about a ship")
    @app_commands.describe(name="Name of the ship")
    async def ship_info(self, interaction: discord.Interaction, name: str):
        """View detailed ship information and registry status."""
        await interaction.response.defer()
        
        # Get ship data
        ship = Ship.get_ship(name)
        if not ship:
            await interaction.followup.send("🚫 Ship not found in database.", ephemeral=True)
            return
            
        # Get registry information if available
        registry_info = await self.registry.get_ship_registry_info(name)
        
        # Create embed
        embed = discord.Embed(
            title=f"HLN Ship Database: {ship.name}",
            description=f"*{ship.manufacturer} Design Bureau*",
            color=discord.Color.from_rgb(47, 49, 54)
        )
        
        # Registry Status Block
        if registry_info and registry_info.get('Registry Number'):
            registry = (
                f"```yaml\n"
                f"Registry Number: {registry_info['Registry Number']}\n"
                f"Status: {registry_info.get('Status', 'Commissioned')}\n"
                f"Commission Date: {registry_info.get('Commission Date', 'Unknown')}\n"
                f"```"
            )
            embed.add_field(name="📟 Registry Information", value=registry, inline=False)
            
            # Add service information
            service_info = (
                f"```yaml\n"
                f"Division: {registry_info.get('Division', 'Unknown')}\n"
                f"Primary Use: {registry_info.get('Primary Use', 'Unknown')}\n"
                f"```"
            )
            embed.add_field(name="🏢 Service Information", value=service_info, inline=False)
            
            # Add flight group information if available
            flight_group = registry_info.get('Flight Group')
            if flight_group:
                flight_info = (
                    f"```yaml\n"
                    f"Flight Group: {flight_group}\n"
                )
                
                squadron = registry_info.get('Squadron')
                if squadron:
                    flight_info += f"Squadron: {squadron}\n"
                    
                flight_info += "```"
                
                embed.add_field(name="🛩️ Flight Assignment", value=flight_info, inline=False)
        else:
            registry = "```yaml\nStatus: Not Commissioned\n```"
            embed.add_field(name="📟 Registry Information", value=registry, inline=False)
        
        # Technical Specifications
        specs = (
            f"```yaml\n"
            f"Primary Role: {ship.role}\n"
            f"Size Class: {ship.size}\n"
            f"Crew Complement: {ship.min_crew} - {ship.max_crew}\n"
            f"Cargo Capacity: {ship.cargo}\n"
            f"```"
        )
        embed.add_field(name="📊 Technical Specifications", value=specs, inline=False)
        
        # Dimensions Block
        dimensions = (
            f"```yaml\n"
            f"Length: {ship.length}\n"
            f"Width: {ship.width}\n"
            f"Height: {ship.height}\n"
            f"Mass: {ship.weight}\n"
            f"```"
        )
        embed.add_field(name="📐 Dimensional Data", value=dimensions, inline=True)
        
        # Performance Metrics
        performance = (
            f"```yaml\n"
            f"SCM Speed: {ship.scm_speed}\n"
            f"Max Speed: {ship.max_speed}\n"
            f"Roll Rate: {ship.roll}\n"
            f"Pitch Rate: {ship.pitch}\n"
            f"Yaw Rate: {ship.yaw}\n"
            f"```"
        )
        embed.add_field(name="⚡ Performance Metrics", value=performance, inline=True)
        
        # Footer
        timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"HLN Fleet Registry • Generated: {timestamp} UTC")
        
        # Create view with action buttons if ship is commissioned
        if registry_info and registry_info.get('Registry Number') and registry_info.get('Status') == 'Active':
            view = ShipActionView(self.registry, name)
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)
        
    @app_commands.command(name="commission_ship", description="Commission a ship into the HLN fleet")
    @app_commands.describe(
        ship_name="Name of the ship to commission",
        division="Division assignment",
        primary_use="Primary use/role of the ship"
    )
    async def commission_ship(self, interaction: discord.Interaction, ship_name: str, division: str, primary_use: str):
        """Commission a ship into the HLN fleet."""
        await interaction.response.defer()
        
        # Verify ship exists in database
        ship = Ship.get_ship(ship_name)
        if not ship:
            await interaction.followup.send("🚫 Ship not found in database.", ephemeral=True)
            return
            
        # Commission the ship
        result = await self.registry.commission_ship(
            ship_name=ship_name,
            ship_model=ship.role,
            division=division,
            primary_use=primary_use,
            discord_user_id=str(interaction.user.id)
        )
        
        if result:
            embed = discord.Embed(
                title="Ship Commission Confirmation",
                description=f"**{ship_name}** has been commissioned into the HLN Fleet",
                color=discord.Color.green()
            )
            
            commission_details = (
                f"```yaml\n"
                f"Registry Number: {result['registry_number']}\n"
                f"Division: {division}\n"
                f"Primary Use: {primary_use}\n"
                f"Commission Date: {result['commission_date']}\n"
                f"Status: Active\n"
                f"```"
            )
            embed.add_field(name="📋 Commission Details", value=commission_details, inline=False)
            
            # Log to audit channel if available
            if hasattr(self.bot, 'audit_logger'):
                audit_message = (
                    f"**Ship Commissioned**\n"
                    f"Ship: {ship_name}\n"
                    f"Registry: {result['registry_number']}\n"
                    f"By: {interaction.user.mention} ({interaction.user.display_name})\n"
                    f"Division: {division}\n"
                    f"Primary Use: {primary_use}"
                )
                await self.bot.audit_logger.log(audit_message)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Failed to commission ship. It may already be commissioned or there was a database error.", ephemeral=True)
            
    @app_commands.command(name="list_ships", description="List ships with optional filters")
    @app_commands.describe(
        manufacturer="Filter by manufacturer",
        role="Filter by role",
        size="Filter by size class",
        commissioned_only="Show only commissioned ships",
        flight_group="Filter by flight group",
        squadron="Filter by squadron"
    )
    async def list_ships(
        self,
        interaction: discord.Interaction,
        manufacturer: Optional[str] = None,
        role: Optional[str] = None,
        size: Optional[str] = None,
        commissioned_only: bool = False,
        flight_group: Optional[str] = None,
        squadron: Optional[str] = None
    ):
        """List ships with optional filters."""
        await interaction.response.defer()
        
        # Filter ships based on basic criteria
        ships = Ship.filter_ships(
            manufacturer=manufacturer,
            role=role,
            size=size
        )
        
        # Build a list to store tuples of (ship, registry_info)
        filtered_ships = []
        
        # Get registry info for all ships
        for ship in ships:
            registry_info = await self.registry.get_ship_registry_info(ship.name)
            
            # Apply commissioned_only filter
            if commissioned_only and (not registry_info or not registry_info.get('Registry Number')):
                continue
                
            # Apply flight_group filter
            if flight_group and (not registry_info or registry_info.get('Flight Group') != flight_group):
                continue
                
            # Apply squadron filter
            if squadron and (not registry_info or registry_info.get('Squadron') != squadron):
                continue
                
            # Add to filtered list
            filtered_ships.append((ship, registry_info))
            
        if not filtered_ships:
            await interaction.followup.send("🚫 No ships found matching criteria", ephemeral=True)
            return
            
        # Create paginated embeds
        pages = []
        
        for i in range(0, len(filtered_ships), SHIPS_PER_PAGE):
            page_ships = filtered_ships[i:i + SHIPS_PER_PAGE]
            
            embed = discord.Embed(
                title="HLN Fleet Registry Database",
                description=f"Displaying {len(page_ships)} of {len(filtered_ships)} ships",
                color=discord.Color.from_rgb(47, 49, 54)
            )
            
            # Add filter information
            filters_applied = []
            if manufacturer:
                filters_applied.append(f"Manufacturer: {manufacturer}")
            if role:
                filters_applied.append(f"Role: {role}")
            if size:
                filters_applied.append(f"Size: {size}")
            if flight_group:
                filters_applied.append(f"Flight Group: {flight_group}")
            if squadron:
                filters_applied.append(f"Squadron: {squadron}")
            if commissioned_only:
                filters_applied.append("Status: Commissioned only")
                
            if filters_applied:
                embed.add_field(name="Filters Applied", value="\n".join(filters_applied), inline=False)
                
            # Add ship entries
            for ship, registry_info in page_ships:
                role_emoji = get_ship_role_emoji(ship.role)
                
                # Base information all ships have
                value = f"```yaml\n"
                value += f"Class: {ship.size}\n"
                value += f"Role: {ship.role}\n"
                
                # Only show registry info for commissioned ships
                if registry_info and registry_info.get('Registry Number'):
                    status = registry_info.get('Status', 'Active')
                    status_emoji = "🟢" if status == 'Active' else "🔴"
                    value += f"Status: {status_emoji} {status}\n"
                    value += f"Registry: {registry_info['Registry Number']}\n"
                    value += f"Division: {registry_info.get('Division', 'Unknown')}\n"
                    
                    # Add flight group info if available
                    flight_group = registry_info.get('Flight Group')
                    if flight_group:
                        value += f"Flight Group: {flight_group}\n"
                        
                        # Add squadron info if available
                        squadron = registry_info.get('Squadron')
                        if squadron:
                            value += f"Squadron: {squadron}\n"
                else:
                    value += f"Status: ⚪ Not Commissioned\n"
                    
                value += "```"
                
                embed.add_field(
                    name=f"{role_emoji} {ship.name}",
                    value=value,
                    inline=True
                )
                
            timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
            embed.set_footer(text=f"HLN Fleet Registry • Page {len(pages) + 1}/{(len(filtered_ships) + SHIPS_PER_PAGE - 1) // SHIPS_PER_PAGE} • Generated: {timestamp} UTC")
            pages.append(embed)
            
        if len(pages) > 1:
            view = PaginatedView(pages)
            await interaction.followup.send(embed=pages[0], view=view)
        else:
            await interaction.followup.send(embed=pages[0])
            
    @app_commands.command(name="manufacturers", description="List ship manufacturers and their fleet contributions")
    async def manufacturers(self, interaction: discord.Interaction):
        """List ship manufacturers and their fleet contributions."""
        await interaction.response.defer()
        
        manufacturers = Ship.get_all_manufacturers()
        pages = []
        
        for i in range(0, len(manufacturers), MANUFACTURERS_PER_PAGE):
            embed = discord.Embed(
                title="HLN Approved Manufacturers",
                description="Official Registry of Ship Manufacturers",
                color=discord.Color.from_rgb(47, 49, 54)
            )
            
            page_manufacturers = sorted(manufacturers)[i:i + MANUFACTURERS_PER_PAGE]
            for mfr in page_manufacturers:
                ships = Ship.get_ships_by_manufacturer(mfr)
                
                # Count commissioned vs total ships
                commissioned_count = 0
                role_counts = {}
                
                for ship in ships:
                    registry_info = await self.registry.get_ship_registry_info(ship.name)
                    if registry_info and registry_info.get('Registry Number'):
                        commissioned_count += 1
                    role_counts[ship.role] = role_counts.get(ship.role, 0) + 1
                    
                # Create manufacturer summary
                ship_summary = "\n".join([
                    f"{get_ship_role_emoji(role)} {role}: {count} ships"
                    for role, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True)
                ])
                
                latest_models = ", ".join(s.name for s in ships[:3])
                if len(ships) > 3:
                    latest_models += f" and {len(ships) - 3} more"
                    
                value = (
                    f"```yaml\n"
                    f"Total Models: {len(ships)}\n"
                    f"Commissioned: {commissioned_count}\n"
                    f"Latest Models: {latest_models}\n"
                    f"```\n"
                    f"{ship_summary}"
                )
                
                embed.add_field(
                    name=f"🏭 {mfr}",
                    value=value,
                    inline=False
                )
                
            timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
            embed.set_footer(text=f"HLN Fleet Registry • Page {len(pages) + 1}/{(len(manufacturers) + MANUFACTURERS_PER_PAGE - 1) // MANUFACTURERS_PER_PAGE} • Generated: {timestamp} UTC")
            pages.append(embed)
            
        view = PaginatedView(pages)
        await interaction.followup.send(embed=pages[0], view=view)
        
    @app_commands.command(name="decommission_ship", description="Decommission a ship from active service")
    @app_commands.describe(
        ship_name="Name of the ship to decommission",
        reason="Reason for decommissioning"
    )
    @app_commands.default_permissions(administrator=True)
    async def decommission_ship(self, interaction: discord.Interaction, ship_name: str, reason: str):
        """Decommission a ship from active service."""
        await interaction.response.defer()
        
        # Decommission the ship
        result = await self.registry.decommission_ship(
            ship_name=ship_name,
            reason=reason,
            discord_user_id=str(interaction.user.id)
        )
        
        if result:
            embed = discord.Embed(
                title="Ship Decommissioned",
                description=f"**{ship_name}** has been decommissioned from active service",
                color=discord.Color.red()
            )
            
            decommission_info = (
                f"```yaml\n"
                f"Date: {result['decommission_date']}\n"
                f"Reason: {reason}\n"
                f"Authorized By: {interaction.user.display_name}\n"
                f"```"
            )
            embed.add_field(name="📋 Decommission Details", value=decommission_info, inline=False)
            
            # Log to audit channel if available
            if hasattr(self.bot, 'audit_logger'):
                audit_message = (
                    f"**Ship Decommissioned**\n"
                    f"Ship: {ship_name}\n"
                    f"Registry: {result['registry_number']}\n"
                    f"By: {interaction.user.mention} ({interaction.user.display_name})\n"
                    f"Reason: {reason}"
                )
                await self.bot.audit_logger.log(audit_message)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Failed to decommission ship. It may not be commissioned or there was a database error.", ephemeral=True)
            
    @app_commands.command(name="ship_lookup", description="Look up a ship by registry number")
    @app_commands.describe(registry_number="Registry number to search for")
    async def ship_lookup(self, interaction: discord.Interaction, registry_number: str):
        """Look up a ship by registry number."""
        await interaction.response.defer()
        
        try:
            # Search the registry using the fixed search method
            results = await self.registry.search_registry(registry_number)
            
            if not results:
                await interaction.followup.send(f"🚫 No ships found with registry number **{registry_number}**", ephemeral=True)
                return
                
            # Create embed for the ship
            ship_info = results[0]  # Take the first match
            
            embed = discord.Embed(
                title=f"Ship Registry: {registry_number}",
                description=f"Registry information for {ship_info.get('Ship Name', 'Unknown Ship')}",
                color=discord.Color.blue()
            )
            
            # Add registry details
            registry_details = (
                f"```yaml\n"
                f"Registry Number: {ship_info.get('Registry Number', 'Unknown')}\n"
                f"Ship Model: {ship_info.get('Ship Model', 'Unknown')}\n"
                f"Status: {ship_info.get('Status', 'Unknown')}\n"
                f"Commission Date: {ship_info.get('Commission Date', 'Unknown')}\n"
                f"Division: {ship_info.get('Division', 'Unknown')}\n"
                f"Primary Use: {ship_info.get('Primary Use', 'Unknown')}\n"
                f"```"
            )
            embed.add_field(name="📋 Registry Details", value=registry_details, inline=False)
            
            # Add flight group info if available
            flight_group = ship_info.get('Flight Group')
            if flight_group:
                flight_info = (
                    f"```yaml\n"
                    f"Flight Group: {flight_group}\n"
                )
                
                squadron = ship_info.get('Squadron')
                if squadron:
                    flight_info += f"Squadron: {squadron}\n"
                    
                flight_info += "```"
                
                embed.add_field(name="🛩️ Flight Assignment", value=flight_info, inline=False)
            
            # Get registered by info (ID Number)
            registered_by = ship_info.get('Registered By', '')
            if registered_by:
                try:
                    id_number = await self.registry.get_user_id_number(registered_by)
                    # Try to get member object
                    member = interaction.guild.get_member(int(registered_by))
                    if member:
                        embed.add_field(
                            name="👤 Registered By", 
                            value=f"{member.mention} (ID: {id_number})", 
                            inline=False
                        )
                    else:
                        embed.add_field(name="👤 Registered By", value=f"ID: {id_number}", inline=False)
                except:
                    embed.add_field(name="👤 Registered By", value=f"Discord ID: {registered_by}", inline=False)
                
            timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
            embed.set_footer(text=f"HLN Fleet Registry • Generated: {timestamp} UTC")
            
            # Create view with action buttons if ship is active
            if ship_info.get('Status') == 'Active':
                ship_name = ship_info.get('Ship Name', '')
                if ship_name:
                    view = ShipActionView(self.registry, ship_name)
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error looking up ship by registry number: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while looking up this registry number.", ephemeral=True)

    @app_commands.command(name="transfer_ship", description="Transfer ship ownership to another member")
    @app_commands.describe(
        ship_name="Name of the ship to transfer",
        new_owner_id="Discord ID of the new owner",
        reason="Reason for the transfer"
    )
    @app_commands.default_permissions(administrator=True)
    async def transfer_ship(self, interaction: discord.Interaction, ship_name: str, new_owner_id: str, reason: str):
        """Transfer ownership of a ship to another member."""
        await interaction.response.defer()
        
        # Verify the ship exists and is commissioned
        registry_info = await self.registry.get_ship_registry_info(ship_name)
        if not registry_info or not registry_info.get('Registry Number'):
            await interaction.followup.send("🚫 Ship not found or not commissioned.", ephemeral=True)
            return
            
        # Verify the new owner ID format
        if not new_owner_id.isdigit():
            await interaction.followup.send("❌ New owner ID must be a valid Discord user ID.", ephemeral=True)
            return
            
        # Transfer the ship
        success = await self.registry.transfer_ship_ownership(
            ship_name=ship_name,
            new_owner_id=new_owner_id,
            transfer_reason=reason
        )
        
        if success:
            embed = discord.Embed(
                title="Ship Ownership Transferred",
                description=f"**{ship_name}** has been transferred to a new owner",
                color=discord.Color.gold()
            )
            
            # Get new owner ID number
            id_number = await self.registry.get_user_id_number(new_owner_id)
            
            # Try to get member object for new owner
            new_owner_name = "Unknown"
            try:
                new_owner = interaction.guild.get_member(int(new_owner_id))
                if new_owner:
                    new_owner_name = new_owner.display_name
            except:
                pass
            
            transfer_info = (
                f"```yaml\n"
                f"Ship: {ship_name}\n"
                f"Registry: {registry_info['Registry Number']}\n"
                f"New Owner: {new_owner_name}\n"
                f"ID Number: {id_number if id_number != 'N/A' else 'Unknown'}\n"
                f"Reason: {reason}\n"
                f"Authorized By: {interaction.user.display_name}\n"
                f"```"
            )
            embed.add_field(name="📋 Transfer Details", value=transfer_info, inline=False)
            
            # Log to audit channel if available
            if hasattr(self.bot, 'audit_logger'):
                audit_message = (
                    f"**Ship Ownership Transferred**\n"
                    f"Ship: {ship_name}\n"
                    f"Registry: {registry_info['Registry Number']}\n"
                    f"New Owner: {new_owner_name} (ID: {new_owner_id})\n"
                    f"By: {interaction.user.mention} ({interaction.user.display_name})\n"
                    f"Reason: {reason}"
                )
                await self.bot.audit_logger.log(audit_message)
            
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Failed to transfer ship ownership. Please try again later.", ephemeral=True)
            
    @app_commands.command(name="fleet_stats", description="View statistics about the fleet")
    async def fleet_stats(self, interaction: discord.Interaction):
        """View statistics about the HLN fleet."""
        await interaction.response.defer()
        
        # Get fleet statistics
        stats = await self.registry.get_fleet_statistics()
        
        if not stats:
            await interaction.followup.send("❌ Failed to retrieve fleet statistics.", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="HLN Fleet Statistics",
            description="Current status of the HLN fleet registry",
            color=discord.Color.blue()
        )
        
        # Overall statistics
        overall_stats = (
            f"```yaml\n"
            f"Total Ships: {stats['total_ships']}\n"
            f"Active Ships: {stats['active_ships']}\n"
            f"Decommissioned Ships: {stats['decommissioned_ships']}\n"
            f"```"
        )
        embed.add_field(name="📊 Fleet Overview", value=overall_stats, inline=False)
        
        # Division breakdown
        if stats['divisions']:
            divisions_text = "```yaml\n"
            for division, count in sorted(stats['divisions'].items(), key=lambda x: x[1], reverse=True):
                if division:  # Skip empty division names
                    divisions_text += f"{division}: {count} ships\n"
            divisions_text += "```"
            embed.add_field(name="🏢 Ships by Division", value=divisions_text, inline=True)
            
        # Primary use breakdown
        if stats['primary_uses']:
            uses_text = "```yaml\n"
            for use, count in sorted(stats['primary_uses'].items(), key=lambda x: x[1], reverse=True):
                if use:  # Skip empty use names
                    uses_text += f"{use}: {count} ships\n"
            uses_text += "```"
            embed.add_field(name="🔧 Ships by Primary Use", value=uses_text, inline=True)
            
        # Latest commissions
        if stats['latest_commissions']:
            latest_text = ""
            for i, commission in enumerate(stats['latest_commissions'][:5], 1):
                ship_name = commission.get('ship_name', 'Unknown')
                commission_date = commission.get('commission_date', 'Unknown')
                latest_text += f"{i}. **{ship_name}** - {commission_date}\n"
                
            embed.add_field(name="🆕 Recent Commissions", value=latest_text, inline=False)
            
        timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"HLN Fleet Registry • Generated: {timestamp} UTC")
        
        await interaction.followup.send(embed=embed)

    # ============ FLIGHT GROUP AND SQUADRON COMMANDS ============
            
    @app_commands.command(name="create_flight_group", description="Create a new flight group")
    @app_commands.describe(
        name="Name of the flight group",
        description="Description of the flight group",
        fleet_wing="Fleet wing the flight group belongs to",
        commander="Commander of the flight group (optional)"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def create_flight_group(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        fleet_wing: str,
        commander: Optional[discord.Member] = None
    ):
        """Create a new flight group."""
        await interaction.response.defer()
        
        try:
            result = await self.registry.create_flight_group(
                name=name,
                description=description,
                fleet_wing=fleet_wing,
                commander_discord_id=str(commander.id) if commander else None
            )
            
            if result:
                embed = discord.Embed(
                    title="Flight Group Created",
                    description=f"**{name}** has been created",
                    color=discord.Color.green()
                )
                
                details = (
                    f"```yaml\n"
                    f"Name: {name}\n"
                    f"Description: {description}\n"
                    f"Fleet Wing: {fleet_wing}\n"
                    f"Commander: {commander.display_name if commander else 'None'}\n"
                    f"```"
                )
                embed.add_field(name="📋 Flight Group Details", value=details, inline=False)
                
                # Log to audit channel if available
                if hasattr(self.bot, 'audit_logger'):
                    audit_message = (
                        f"**Flight Group Created**\n"
                        f"Name: {name}\n"
                        f"By: {interaction.user.mention} ({interaction.user.display_name})\n"
                        f"Fleet Wing: {fleet_wing}"
                    )
                    await self.bot.audit_logger.log(audit_message)
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to create flight group. It may already exist or there was a database error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating flight group: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while creating the flight group.", ephemeral=True)

    @app_commands.command(name="create_squadron", description="Create a new squadron")
    @app_commands.describe(
        name="Name of the squadron",
        description="Description of the squadron",
        fleet_wing="Fleet wing the squadron belongs to",
        commander="Commander of the squadron (optional)"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def create_squadron(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        fleet_wing: str,
        commander: Optional[discord.Member] = None
    ):
        """Create a new squadron."""
        await interaction.response.defer()
        
        try:
            result = await self.registry.create_squadron(
                name=name,
                description=description,
                fleet_wing=fleet_wing,
                commander_discord_id=str(commander.id) if commander else None
            )
            
            if result:
                embed = discord.Embed(
                    title="Squadron Created",
                    description=f"**{name}** has been created",
                    color=discord.Color.green()
                )
                
                details = (
                    f"```yaml\n"
                    f"Name: {name}\n"
                    f"Description: {description}\n"
                    f"Fleet Wing: {fleet_wing}\n"
                    f"Commander: {commander.display_name if commander else 'None'}\n"
                    f"```"
                )
                embed.add_field(name="📋 Squadron Details", value=details, inline=False)
                
                # Log to audit channel if available
                if hasattr(self.bot, 'audit_logger'):
                    audit_message = (
                        f"**Squadron Created**\n"
                        f"Name: {name}\n"
                        f"By: {interaction.user.mention} ({interaction.user.display_name})\n"
                        f"Fleet Wing: {fleet_wing}"
                    )
                    await self.bot.audit_logger.log(audit_message)
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to create squadron. It may already exist or there was a database error.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating squadron: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while creating the squadron.", ephemeral=True)

    @app_commands.command(name="flight_group_info", description="View information about a flight group")
    @app_commands.describe(
        name="Name of the flight group"
    )
    async def flight_group_info(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        """View information about a flight group."""
        await interaction.response.defer()
        
        try:
            flight_group = await self.registry.get_flight_group(name)
            
            if not flight_group:
                await interaction.followup.send(f"❌ Flight group '{name}' not found.", ephemeral=True)
                return
                
            embed = discord.Embed(
                title=f"Flight Group: {flight_group['name']}",
                description=flight_group['description'],
                color=discord.Color.blue()
            )
            
            # Basic info
            basic_info = (
                f"```yaml\n"
                f"Status: {flight_group.get('status', 'Unknown')}\n"
                f"Fleet Wing: {flight_group.get('fleet_wing', 'N/A')}\n"
                f"Squadron: {flight_group.get('squadron', 'None')}\n"
                f"```"
            )
            embed.add_field(name="📋 Basic Information", value=basic_info, inline=False)
            
            # Commander info
            commander_id = flight_group.get('commander_id')
            commander_info = "None assigned"
            if commander_id:
                try:
                    commander = interaction.guild.get_member(int(commander_id))
                    if commander:
                        commander_info = f"{commander.mention} ({commander.display_name})"
                except:
                    commander_info = f"ID: {commander_id}"
                    
            embed.add_field(name="👤 Commander", value=commander_info, inline=False)
            
            # Ships
            ships = flight_group.get('ships', [])
            if isinstance(ships, str):
                ships = [s.strip() for s in ships.split(',') if s.strip()]
                
            if ships:
                ship_list = "\n".join([f"• {ship}" for ship in ships])
                embed.add_field(name="🚀 Assigned Ships", value=f"```\n{ship_list}\n```", inline=False)
            else:
                embed.add_field(name="🚀 Assigned Ships", value="No ships assigned", inline=False)
            
            # Check if profile cog is available to list members
            profile_cog = self.bot.get_cog('Profile')
            if profile_cog and hasattr(profile_cog, 'get_flight_group_members'):
                try:
                    members = await profile_cog.get_flight_group_members(name)
                    if members:
                        member_list = "\n".join([f"• {member.mention} ({member.display_name})" for member in members])
                        embed.add_field(name="👥 Members", value=member_list, inline=False)
                    else:
                        embed.add_field(name="👥 Members", value="No members assigned", inline=False)
                except Exception as e:
                    logger.error(f"Error getting flight group members: {e}")
                    embed.add_field(name="👥 Members", value="Error retrieving members", inline=False)
                    
            timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
            embed.set_footer(text=f"HLN Fleet Registry • Generated: {timestamp} UTC")
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error retrieving flight group info: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while retrieving flight group information.", ephemeral=True)

    @app_commands.command(name="squadron_info", description="View information about a squadron")
    @app_commands.describe(
        name="Name of the squadron"
    )
    async def squadron_info(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        """View information about a squadron."""
        await interaction.response.defer()
        
        try:
            squadron = await self.registry.get_squadron(name)
            
            if not squadron:
                await interaction.followup.send(f"❌ Squadron '{name}' not found.", ephemeral=True)
                return
                
            embed = discord.Embed(
                title=f"Squadron: {squadron['name']}",
                description=squadron['description'],
                color=discord.Color.blue()
            )
            
            # Basic info
            basic_info = (
                f"```yaml\n"
                f"Status: {squadron.get('status', 'Unknown')}\n"
                f"Fleet Wing: {squadron.get('fleet_wing', 'N/A')}\n"
                f"```"
            )
            embed.add_field(name="📋 Basic Information", value=basic_info, inline=False)
            
            # Commander info
            commander_id = squadron.get('commander_id')
            commander_info = "None assigned"
            if commander_id:
                try:
                    commander = interaction.guild.get_member(int(commander_id))
                    if commander:
                        commander_info = f"{commander.mention} ({commander.display_name})"
                except:
                    commander_info = f"ID: {commander_id}"
                    
            embed.add_field(name="👤 Commander", value=commander_info, inline=False)
            
            # Flight Groups
            flight_groups = squadron.get('flight_groups', [])
            if isinstance(flight_groups, str):
                flight_groups = [fg.strip() for fg in flight_groups.split(',') if fg.strip()]
                
            if flight_groups:
                fg_list = "\n".join([f"• {fg}" for fg in flight_groups])
                embed.add_field(name="🛩️ Flight Groups", value=f"```\n{fg_list}\n```", inline=False)
            else:
                embed.add_field(name="🛩️ Flight Groups", value="No flight groups assigned", inline=False)
                
            # Check if profile cog is available to list members
            profile_cog = self.bot.get_cog('Profile')
            if profile_cog and hasattr(profile_cog, 'get_squadron_members'):
                try:
                    members = await profile_cog.get_squadron_members(name)
                    if members:
                        member_list = "\n".join([f"• {member.mention} ({member.display_name})" for member in members])
                        embed.add_field(name="👥 Members", value=member_list, inline=False)
                    else:
                        embed.add_field(name="👥 Members", value="No members assigned", inline=False)
                except Exception as e:
                    logger.error(f"Error getting squadron members: {e}")
                    embed.add_field(name="👥 Members", value="Error retrieving members", inline=False)
                    
            timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
            embed.set_footer(text=f"HLN Fleet Registry • Generated: {timestamp} UTC")
            
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error retrieving squadron info: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while retrieving squadron information.", ephemeral=True)

    @app_commands.command(name="list_flight_groups", description="List all flight groups")
    @app_commands.describe(
        squadron="Filter by squadron (optional)",
        fleet_wing="Filter by fleet wing (optional)"
    )
    async def list_flight_groups(
        self,
        interaction: discord.Interaction,
        squadron: Optional[str] = None,
        fleet_wing: Optional[str] = None
    ):
        """List all flight groups."""
        await interaction.response.defer()
        
        try:
            flight_groups = await self.registry.list_flight_groups(squadron, fleet_wing)
            
            if not flight_groups:
                await interaction.followup.send("No flight groups found matching the criteria.", ephemeral=True)
                return
                
            # Create paginated embeds
            pages = []
            for i in range(0, len(flight_groups), 5):
                page_flight_groups = flight_groups[i:i + 5]
                
                embed = discord.Embed(
                    title="HLN Flight Groups",
                    description=f"Displaying {len(page_flight_groups)} of {len(flight_groups)} flight groups",
                    color=discord.Color.blue()
                )
                
                # Add filter information
                filters_applied = []
                if squadron:
                    filters_applied.append(f"Squadron: {squadron}")
                if fleet_wing:
                    filters_applied.append(f"Fleet Wing: {fleet_wing}")
                    
                if filters_applied:
                    embed.add_field(name="Filters Applied", value="\n".join(filters_applied), inline=False)
                    
                for fg in page_flight_groups:
                    status_emoji = "🟢" if fg.get('status') == 'Active' else "🔴"
                    
                    # Count ships
                    ships = fg.get('ships', [])
                    if isinstance(ships, str):
                        ships = [s.strip() for s in ships.split(',') if s.strip()]
                        
                    # Get commander info
                    commander_info = "None"
                    if fg.get('commander_id'):
                        try:
                            commander = interaction.guild.get_member(int(fg['commander_id']))
                            if commander:
                                commander_info = commander.display_name
                        except:
                            commander_info = "Unknown"
                    
                    value = (
                        f"```yaml\n"
                        f"Status: {status_emoji} {fg.get('status', 'Unknown')}\n"
                        f"Fleet Wing: {fg.get('fleet_wing', 'N/A')}\n"
                        f"Squadron: {fg.get('squadron', 'N/A')}\n"
                        f"Commander: {commander_info}\n"
                        f"Ships: {len(ships)}\n"
                        f"```"
                    )
                    
                    embed.add_field(
                        name=f"🛩️ {fg['name']}",
                        value=value,
                        inline=False
                    )
                    
                timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
                embed.set_footer(text=f"HLN Fleet Registry • Page {len(pages) + 1}/{(len(flight_groups) + 5 - 1) // 5} • Generated: {timestamp} UTC")
                pages.append(embed)
                
            if len(pages) > 1:
                view = PaginatedView(pages)
                await interaction.followup.send(embed=pages[0], view=view)
            else:
                await interaction.followup.send(embed=pages[0])
        except Exception as e:
            logger.error(f"Error listing flight groups: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while listing flight groups.", ephemeral=True)

    @app_commands.command(name="list_squadrons", description="List all squadrons")
    @app_commands.describe(
        fleet_wing="Filter by fleet wing (optional)"
    )
    async def list_squadrons(
        self,
        interaction: discord.Interaction,
        fleet_wing: Optional[str] = None
    ):
        """List all squadrons."""
        await interaction.response.defer()
        
        try:
            squadrons = await self.registry.list_squadrons(fleet_wing)
            
            if not squadrons:
                await interaction.followup.send("No squadrons found matching the criteria.", ephemeral=True)
                return
                
            # Create paginated embeds
            pages = []
            for i in range(0, len(squadrons), 5):
                page_squadrons = squadrons[i:i + 5]
                
                embed = discord.Embed(
                    title="HLN Squadrons",
                    description=f"Displaying {len(page_squadrons)} of {len(squadrons)} squadrons",
                    color=discord.Color.blue()
                )
                
                if fleet_wing:
                    embed.add_field(name="Fleet Wing Filter", value=fleet_wing, inline=True)
                    
                for squadron in page_squadrons:
                    status_emoji = "🟢" if squadron.get('status') == 'Active' else "🔴"
                    
                    # Count flight groups
                    flight_groups = squadron.get('flight_groups', [])
                    if isinstance(flight_groups, str):
                        flight_groups = [fg.strip() for fg in flight_groups.split(',') if fg.strip()]
                        
                    # Get commander info
                    commander_info = "None"
                    if squadron.get('commander_id'):
                        try:
                            commander = interaction.guild.get_member(int(squadron['commander_id']))
                            if commander:
                                commander_info = commander.display_name
                        except:
                            commander_info = "Unknown"
                    
                    value = (
                        f"```yaml\n"
                        f"Status: {status_emoji} {squadron.get('status', 'Unknown')}\n"
                        f"Fleet Wing: {squadron.get('fleet_wing', 'N/A')}\n"
                        f"Commander: {commander_info}\n"
                        f"Flight Groups: {len(flight_groups)}\n"
                        f"```"
                    )
                    
                    embed.add_field(
                        name=f"🚀 {squadron['name']}",
                        value=value,
                        inline=False
                    )
                    
                timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
                embed.set_footer(text=f"HLN Fleet Registry • Page {len(pages) + 1}/{(len(squadrons) + 5 - 1) // 5} • Generated: {timestamp} UTC")
                pages.append(embed)
                
            if len(pages) > 1:
                view = PaginatedView(pages)
                await interaction.followup.send(embed=pages[0], view=view)
            else:
                await interaction.followup.send(embed=pages[0])
        except Exception as e:
            logger.error(f"Error listing squadrons: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while listing squadrons.", ephemeral=True)

    @app_commands.command(name="assign_flight_group_to_squadron", description="Assign a flight group to a squadron")
    @app_commands.describe(
        flight_group="Name of the flight group",
        squadron="Name of the squadron"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def assign_flight_group_to_squadron(
        self,
        interaction: discord.Interaction,
        flight_group: str,
        squadron: str
    ):
        """Assign a flight group to a squadron."""
        await interaction.response.defer()
        
        try:
            result = await self.registry.assign_flight_group_to_squadron(flight_group, squadron)
            
            if result:
                embed = discord.Embed(
                    title="Flight Group Assigned",
                    description=f"**{flight_group}** has been assigned to **{squadron}**",
                    color=discord.Color.green()
                )
                
                # Log to audit channel if available
                if hasattr(self.bot, 'audit_logger'):
                    audit_message = (
                        f"**Flight Group Assigned to Squadron**\n"
                        f"Flight Group: {flight_group}\n"
                        f"Squadron: {squadron}\n"
                        f"By: {interaction.user.mention} ({interaction.user.display_name})"
                    )
                    await self.bot.audit_logger.log(audit_message)
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to assign flight group to squadron. Please verify that both exist.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error assigning flight group to squadron: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while assigning the flight group to squadron.", ephemeral=True)

    @app_commands.command(name="assign_ship_to_flight_group", description="Assign a ship to a flight group")
    @app_commands.describe(
        ship_name="Name of the ship",
        flight_group="Name of the flight group"
    )
    @app_commands.checks.has_any_role('Admin', 'Command Staff', 'Fleet Command')
    async def assign_ship_to_flight_group(
        self,
        interaction: discord.Interaction,
        ship_name: str,
        flight_group: str
    ):
        """Assign a ship to a flight group."""
        await interaction.response.defer()
        
        try:
            result = await self.registry.assign_ship_to_flight_group(ship_name, flight_group)
            
            if result:
                embed = discord.Embed(
                    title="Ship Assigned",
                    description=f"**{ship_name}** has been assigned to **{flight_group}**",
                    color=discord.Color.green()
                )
                
                # Log to audit channel if available
                if hasattr(self.bot, 'audit_logger'):
                    audit_message = (
                        f"**Ship Assigned to Flight Group**\n"
                        f"Ship: {ship_name}\n"
                        f"Flight Group: {flight_group}\n"
                        f"By: {interaction.user.mention} ({interaction.user.display_name})"
                    )
                    await self.bot.audit_logger.log(audit_message)
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to assign ship to flight group. Please verify that both exist.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error assigning ship to flight group: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while assigning the ship to flight group.", ephemeral=True)

    # ============ NEW COMMANDS ============
    
    @app_commands.command(name="registry_report", description="Generate a comprehensive registry report")
    @app_commands.describe(
        report_type="Type of report to generate",
        filter_value="Optional filter value (e.g. division name or user ID)"
    )
    @app_commands.choices(report_type=[
        app_commands.Choice(name="Division Ships", value="division"),
        app_commands.Choice(name="User Ships", value="user"),
        app_commands.Choice(name="Flight Group Ships", value="flight_group"),
        app_commands.Choice(name="Squadron Ships", value="squadron"),
        app_commands.Choice(name="Unassigned Ships", value="unassigned")
    ])
    async def registry_report(
        self,
        interaction: discord.Interaction,
        report_type: str,
        filter_value: Optional[str] = None
    ):
        """Generate a comprehensive registry report."""
        await interaction.response.defer()
        
        try:
            if report_type == "division":
                # Get ships by division
                if not filter_value:
                    await interaction.followup.send("❌ Division name is required for this report type.", ephemeral=True)
                    return
                
                ships = await self.registry.get_ships_by_division(filter_value)
                title = f"Division Ships Report: {filter_value}"
                description = f"Ships assigned to division: {filter_value}"
                
            elif report_type == "user":
                # Get ships by user
                if not filter_value:
                    # Use interaction user's ID if no filter value provided
                    filter_value = str(interaction.user.id)
                    
                ships = await self.registry.get_ships_by_user(filter_value)
                
                # Try to get user info
                user_name = "Unknown"
                try:
                    user = interaction.guild.get_member(int(filter_value))
                    if user:
                        user_name = user.display_name
                except:
                    pass
                    
                title = f"User Ships Report: {user_name}"
                description = f"Ships registered to user: {user_name}"
                
            elif report_type == "flight_group":
                # Get ships by flight group
                if not filter_value:
                    await interaction.followup.send("❌ Flight group name is required for this report type.", ephemeral=True)
                    return
                    
                # Get flight group first to check if it exists
                flight_group = await self.registry.get_flight_group(filter_value)
                if not flight_group:
                    await interaction.followup.send(f"❌ Flight group '{filter_value}' not found.", ephemeral=True)
                    return
                    
                # Get all ships
                all_ships = await self.registry.get_ships_by_status('Active')
                ships = [ship for ship in all_ships if ship.get('Flight Group') == filter_value]
                
                title = f"Flight Group Ships Report: {filter_value}"
                description = f"Ships assigned to flight group: {filter_value}"
                
            elif report_type == "squadron":
                # Get ships by squadron
                if not filter_value:
                    await interaction.followup.send("❌ Squadron name is required for this report type.", ephemeral=True)
                    return
                    
                # Get squadron first to check if it exists
                squadron = await self.registry.get_squadron(filter_value)
                if not squadron:
                    await interaction.followup.send(f"❌ Squadron '{filter_value}' not found.", ephemeral=True)
                    return
                    
                # Get all ships
                all_ships = await self.registry.get_ships_by_status('Active')
                ships = [ship for ship in all_ships if ship.get('Squadron') == filter_value]
                
                title = f"Squadron Ships Report: {filter_value}"
                description = f"Ships assigned to squadron: {filter_value}"
                
            elif report_type == "unassigned":
                # Get all active ships
                all_ships = await self.registry.get_ships_by_status('Active')
                
                # Filter to only include ships not assigned to a flight group
                ships = [ship for ship in all_ships if not ship.get('Flight Group')]
                
                title = "Unassigned Ships Report"
                description = "Ships not assigned to any flight group"
                
            else:
                await interaction.followup.send("❌ Invalid report type.", ephemeral=True)
                return
                
            if not ships:
                await interaction.followup.send(f"No ships found for this {report_type} report.", ephemeral=True)
                return
                
            # Create paginated embeds
            pages = []
            for i in range(0, len(ships), SHIPS_PER_PAGE):
                page_ships = ships[i:i + SHIPS_PER_PAGE]
                
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=discord.Color.blue()
                )
                
                for ship in page_ships:
                    ship_name = ship.get('Ship Name', 'Unknown')
                    registry_number = ship.get('Registry Number', 'N/A')
                    status = ship.get('Status', 'Unknown')
                    status_emoji = "🟢" if status == 'Active' else "🔴"
                    division = ship.get('Division', 'Unknown')
                    primary_use = ship.get('Primary Use', 'Unknown')
                    
                    value = (
                        f"```yaml\n"
                        f"Registry: {registry_number}\n"
                        f"Status: {status_emoji} {status}\n"
                        f"Division: {division}\n"
                        f"Primary Use: {primary_use}\n"
                    )
                    
                    # Add flight assignment info if available
                    flight_group = ship.get('Flight Group')
                    if flight_group:
                        value += f"Flight Group: {flight_group}\n"
                        
                        squadron = ship.get('Squadron')
                        if squadron:
                            value += f"Squadron: {squadron}\n"
                            
                    value += "```"
                    
                    embed.add_field(
                        name=f"🚀 {ship_name}",
                        value=value,
                        inline=False
                    )
                    
                timestamp = datetime.utcnow().strftime('%Y.%m.%d-%H%M')
                embed.set_footer(text=f"HLN Fleet Registry • Page {len(pages) + 1}/{(len(ships) + SHIPS_PER_PAGE - 1) // SHIPS_PER_PAGE} • Generated: {timestamp} UTC")
                pages.append(embed)
                
            if len(pages) > 1:
                view = PaginatedView(pages)
                await interaction.followup.send(embed=pages[0], view=view)
            else:
                await interaction.followup.send(embed=pages[0])
                
        except Exception as e:
            logger.error(f"Error generating registry report: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while generating the registry report.", ephemeral=True)
    
    @app_commands.command(name="refresh_registry_cache", description="Refresh the registry cache")
    @app_commands.default_permissions(administrator=True)
    async def refresh_registry_cache(self, interaction: discord.Interaction):
        """Refresh the registry cache."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.registry.clear_cache()
            await interaction.followup.send("✅ Registry cache cleared successfully.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error refreshing registry cache: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while refreshing the registry cache.", ephemeral=True)

    # Autocomplete handlers
    @ship_info.autocomplete('name')
    async def ship_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        ships = Ship.search_ships(current)
        return [
            app_commands.Choice(name=f"{s.name} ({s.manufacturer})", value=s.name)
            for s in ships
        ][:25]
        
    @commission_ship.autocomplete('ship_name')
    async def commission_ship_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        ships = Ship.search_ships(current)
        # Filter out already commissioned ships
        non_commissioned = []
        for ship in ships:
            registry_info = await self.registry.get_ship_registry_info(ship.name)
            if not registry_info or not registry_info.get('Registry Number'):
                non_commissioned.append(ship)
        return [
            app_commands.Choice(name=f"{s.name} ({s.manufacturer})", value=s.name)
            for s in non_commissioned
        ][:25]
        
    @list_ships.autocomplete('manufacturer')
    async def manufacturer_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        manufacturers = Ship.get_all_manufacturers()
        return [
            app_commands.Choice(name=m, value=m)
            for m in manufacturers
            if current.lower() in m.lower()
        ][:25]
        
    @list_ships.autocomplete('role')
    async def role_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        roles = Ship.get_all_roles()
        return [
            app_commands.Choice(name=r, value=r)
            for r in roles
            if current.lower() in r.lower()
        ][:25]
        
    @list_ships.autocomplete('size')
    async def size_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        sizes = Ship.get_all_sizes()
        return [
            app_commands.Choice(name=s, value=s)
            for s in sizes
            if current.lower() in s.lower()
        ][:25]
        
    @commission_ship.autocomplete('division')
    async def division_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        divisions = ['Command', 'Operations', 'Tactical', 'Support', 'Medical', 'Engineering', 'Science', 'Security', 'Non-Division']
        return [
            app_commands.Choice(name=d, value=d)
            for d in divisions
            if current.lower() in d.lower()
        ][:25]
        
    @commission_ship.autocomplete('primary_use')
    async def primary_use_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        uses = [
            'Combat', 'Exploration', 'Transport', 'Mining', 'Refueling',
            'Medical', 'Research', 'Trading', 'Salvage', 'Support',
            'Flagship', 'Navy Multirole Platform', 'Reconnaissance',
            'Search and Rescue', 'Command and Control'
        ]
        return [
            app_commands.Choice(name=u, value=u)
            for u in uses
            if current.lower() in u.lower()
        ][:25]
        
    @decommission_ship.autocomplete('ship_name')
    @transfer_ship.autocomplete('ship_name')
    async def commissioned_ship_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        ships = Ship.search_ships(current)
        # Filter to only show commissioned ships
        commissioned_ships = []
        for ship in ships:
            registry_info = await self.registry.get_ship_registry_info(ship.name)
            if registry_info and registry_info.get('Registry Number') and registry_info.get('Status', '') != 'Decommissioned':
                commissioned_ships.append((ship, registry_info['Registry Number']))
        return [
            app_commands.Choice(name=f"{s[0].name} ({s[1]})", value=s[0].name)
            for s in commissioned_ships
        ][:25]

    # Flight group and squadron autocomplete methods
    @flight_group_info.autocomplete('name')
    @assign_flight_group_to_squadron.autocomplete('flight_group')
    @assign_ship_to_flight_group.autocomplete('flight_group')
    @list_ships.autocomplete('flight_group')
    @registry_report.autocomplete('filter_value')
    async def flight_group_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for flight group names."""
        # Only process flight group autocomplete for registry_report if report_type is flight_group
        if interaction.command.name == "registry_report":
            options = interaction.namespace.to_dict()
            if options.get("report_type") != "flight_group":
                return []
                
        try:
            flight_groups = await self.registry.list_flight_groups()
            return [
                app_commands.Choice(name=fg['name'], value=fg['name'])
                for fg in flight_groups
                if current.lower() in fg['name'].lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in flight group autocomplete: {e}")
            return []

    @squadron_info.autocomplete('name')
    @assign_flight_group_to_squadron.autocomplete('squadron')
    @list_ships.autocomplete('squadron')
    @registry_report.autocomplete('filter_value')
    async def squadron_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for squadron names."""
        # Only process squadron autocomplete for registry_report if report_type is squadron
        if interaction.command.name == "registry_report":
            options = interaction.namespace.to_dict()
            if options.get("report_type") != "squadron":
                return []
                
        try:
            squadrons = await self.registry.list_squadrons()
            return [
                app_commands.Choice(name=squadron['name'], value=squadron['name'])
                for squadron in squadrons
                if current.lower() in squadron['name'].lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in squadron autocomplete: {e}")
            return []

    # Division autocomplete for registry report
    @registry_report.autocomplete('filter_value')
    async def division_report_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for division names in registry report."""
        # Only process if report_type is division
        options = interaction.namespace.to_dict()
        if options.get("report_type") != "division":
            return []
            
        divisions = ['Command', 'Operations', 'Tactical', 'Support', 'Medical', 'Engineering', 'Science', 'Security', 'Non-Division']
        return [
            app_commands.Choice(name=d, value=d)
            for d in divisions
            if current.lower() in d.lower()
        ][:25]

    # Ship autocomplete for flight group assignment
    @assign_ship_to_flight_group.autocomplete('ship_name')
    async def ship_for_flight_group_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for ship names."""
        ships = Ship.search_ships(current)
        
        # Filter only commissioned ships
        commissioned_ships = []
        for ship in ships:
            registry_info = await self.registry.get_ship_registry_info(ship.name)
            if registry_info and registry_info.get('Registry Number') and registry_info.get('Status', '') != 'Decommissioned':
                commissioned_ships.append((ship, registry_info.get('Registry Number', '')))
        
        return [
            app_commands.Choice(name=f"{s[0].name} ({s[1]})", value=s[0].name)
            for s in commissioned_ships
        ][:25]


async def setup(bot: commands.Bot):
    """Set up the ships cog."""
    cog = ShipsCog(bot)
    await bot.add_cog(cog)
    logger.info("ShipsCog loaded successfully")