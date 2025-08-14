"""UI components for profile system with fleet-based structure."""

import discord
import logging
from typing import Dict, List, Optional, Any, Callable, Union
from datetime import datetime, timezone
import asyncio
from .constants import DIVISION_TO_FLEET_WING

logger = logging.getLogger('profile.ui')

class ProfileView(discord.ui.View):
    """Interactive profile view with dropdown for page selection."""
    
    def __init__(self, cog, member: discord.Member, member_data: dict, viewer: discord.Member, is_mobile: bool = False):
        super().__init__(timeout=180)
        self.cog = cog
        self.member = member
        self.member_data = member_data
        self.viewer = viewer
        self.is_mobile = is_mobile
        self.current_embed = None
        
    @discord.ui.select(
        placeholder="Select profile page",
        options=[
            discord.SelectOption(label="Main Profile", value="main", 
                               emoji="📋", description="Overview of profile"),
            discord.SelectOption(label="Service Record", value="service", 
                               emoji="📜", description="Detailed service history"),
            discord.SelectOption(label="Combat Log", value="combat", 
                               emoji="⚔️", description="Combat operations record"),
            discord.SelectOption(label="Qualifications", value="qualifications", 
                               emoji="🏅", description="Training and certifications"),
            discord.SelectOption(label="Mission Log", value="missions", 
                               emoji="🚀", description="Mission history"),
            discord.SelectOption(label="Classified Info", value="classified", 
                               emoji="🔒", description="Classified information")
        ]
    )
    async def profile_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle profile page selection."""
        option = select.values[0]
        
        if option == "main":
            embed = await self.cog.create_profile_embed(self.member, self.member_data, self.viewer, self.is_mobile)
        elif option == "service":
            embed = await self.cog.create_service_record_embed(self.member, self.member_data, self.viewer, self.is_mobile)
        elif option == "combat":
            embed = await self.cog.create_combat_log_embed(self.member, self.member_data, self.viewer, self.is_mobile)
        elif option == "qualifications":
            embed = await self.cog.create_qualifications_embed(self.member, self.member_data, self.viewer, self.is_mobile)
        elif option == "missions":
            embed = await self.cog.create_mission_log_embed(self.member, self.member_data, self.viewer, self.is_mobile)
        elif option == "classified":
            embed = await self.cog.create_classified_info_embed(self.member, self.member_data, self.viewer, self.is_mobile)
            if not embed:
                await interaction.response.send_message("You don't have sufficient clearance to view this information.", ephemeral=True)
                return
        
        self.current_embed = embed
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Dispatch profile_page_viewed event
        if hasattr(self.cog, 'dispatch_event'):
            await self.cog.dispatch_event(
                'profile_page_viewed',
                member_id=self.member.id,
                viewer_id=self.viewer.id,
                page_type=option
            )
        
    @discord.ui.button(label="Share Profile", style=discord.ButtonStyle.green, emoji="📤", row=1)
    async def share_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Generate a shareable version of the profile."""
        embed = await self.cog.create_profile_embed(self.member, self.member_data, self.viewer, False)
        
        # Create a new basic embed for sharing
        share_embed = discord.Embed(
            title=f"Shared Profile: {self.member.display_name}",
            color=discord.Color.blue()
        )
        
        # Add basic info
        values = self.member_data.get('values', {})
        share_embed.add_field(
            name="Basic Information",
            value=self.cog.formatter.format_basic_info(values),
            inline=False
        )
        
        # Add quick stats
        share_embed.add_field(
            name="Statistics",
            value=self.cog.formatter.format_quick_stats(values),
            inline=False
        )
        
        # Add certifications
        share_embed.add_field(
            name="Certifications",
            value=self.cog.formatter.format_grouped_certifications(values),
            inline=False
        )
        
        share_embed.set_thumbnail(url=self.member.display_avatar.url)
        share_embed.set_footer(text=f"Profile shared by {interaction.user.display_name}")
        
        # Send as a new message
        await interaction.response.send_message(
            content=f"Shared profile for {self.member.mention}:",
            embed=share_embed
        )
        
        # Dispatch profile_shared event
        if hasattr(self.cog, 'dispatch_event'):
            await self.cog.dispatch_event(
                'profile_shared',
                member_id=self.member.id,
                shared_by=interaction.user.id
            )

    @discord.ui.button(label="Export PDF", style=discord.ButtonStyle.grey, emoji="📄", row=1)
    async def export_pdf(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Export profile as PDF."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            pdf_bytes = await self.cog.generate_profile_pdf(self.member)
            file = discord.File(
                fp=pdf_bytes,
                filename=f"{self.member.name}_profile.pdf"
            )
            await interaction.followup.send("Here's the exported profile PDF:", file=file, ephemeral=True)
            
            # Dispatch profile_exported event
            if hasattr(self.cog, 'dispatch_event'):
                await self.cog.dispatch_event(
                    'profile_exported',
                    member_id=self.member.id,
                    export_type="pdf",
                    exported_by=interaction.user.id
                )
        except Exception as e:
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to generate PDF. Please try again later.", ephemeral=True)

    @discord.ui.button(label="Visualize Stats", style=discord.ButtonStyle.blurple, emoji="📊", row=1)
    async def visualize_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the stats visualization for the profile."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.cog.send_profile_visualization(interaction, self.member)
        except Exception as e:
            logger.error(f"Error visualizing stats: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to generate visualization.", ephemeral=True)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.green, emoji="🔄", row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Refresh the profile data."""
        await interaction.response.defer()
        logger.debug(f"Refreshing profile for {self.member.name} (ID: {self.member.id})")
        
        try:
            member_row = await self.cog.get_member_row(self.member.id)
            if not member_row:
                await interaction.followup.send("❌ No service record found.", ephemeral=True)
                return

            validated_data = self.cog.map_and_validate_profile(member_row, self.member.id)
            if not validated_data:
                await interaction.followup.send("❌ Invalid service record data.", ephemeral=True)
                return

            self.member_data = member_row
            
            # Refresh current page
            if not self.current_embed:
                embed = await self.cog.create_profile_embed(self.member, self.member_data, self.viewer, self.is_mobile)
            else:
                # Use the current embed type
                embed = self.current_embed
                # Update the embed's creation method (this is a simplified approach)
                embed = await self.cog.create_profile_embed(self.member, self.member_data, self.viewer, self.is_mobile)
            
            self.current_embed = embed
            await interaction.edit_original_response(embed=embed, view=self)
            await interaction.followup.send("✅ Profile refreshed successfully.", ephemeral=True)
            
            # Dispatch profile_refreshed event
            if hasattr(self.cog, 'dispatch_event'):
                await self.cog.dispatch_event(
                    'profile_refreshed',
                    member_id=self.member.id,
                    refreshed_by=interaction.user.id
                )
            
        except Exception as e:
            logger.error(f"Error refreshing profile: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred while refreshing.", ephemeral=True)
            
            
    @discord.ui.button(label="Ship Assignment", style=discord.ButtonStyle.grey, emoji="🚢", row=2)
    async def view_ship_assignment(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View the member's ship assignment details."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get ship assignment from profile data
            values = self.member_data.get('values', {})
            ship_assignment = values.get('Ship Assignment', '')
            flight_group = values.get('Flight Group', '')
            squadron = values.get('Squadron', '')
            
            if not ship_assignment or ship_assignment == 'Unassigned':
                await interaction.followup.send(
                    f"{self.member.display_name} is not currently assigned to any ship.",
                    ephemeral=True
                )
                return
                
            # Create embed with ship details
            embed = discord.Embed(
                title=f"Ship Assignment: {self.member.display_name}",
                description=f"Current assignment details for {self.member.mention}",
                color=discord.Color.blue()
            )
            
            # Extract position if available
            position = None
            base_ship = ship_assignment
            if '(' in ship_assignment and ')' in ship_assignment:
                base_ship = ship_assignment.split('(')[0].strip()
                position = ship_assignment.split('(')[1].split(')')[0].strip()
            
            # Basic assignment info
            assignment_info = [f"**Ship**: {base_ship}"]
            if position:
                assignment_info.append(f"**Position**: {position}")
            if flight_group:
                assignment_info.append(f"**Flight Group**: {flight_group}")
            if squadron:
                assignment_info.append(f"**Squadron**: {squadron}")
                
            embed.add_field(
                name="Assignment Details",
                value="\n".join(assignment_info),
                inline=False
            )
            
            # Check if ships cog is available for more details
            ships_cog = self.cog.bot.get_cog('Ships')
            registry_info = None
            
            if ships_cog and hasattr(ships_cog, 'registry'):
                try:
                    registry_info = await ships_cog.registry.get_ship_registry_info(base_ship)
                    
                    if registry_info:
                        registry_details = [
                            f"**Registry Number**: {registry_info.get('Registry Number', 'Unknown')}",
                            f"**Ship Model**: {registry_info.get('Ship Model', 'Unknown')}",
                            f"**Division**: {registry_info.get('Division', 'Unknown')}",
                            f"**Primary Use**: {registry_info.get('Primary Use', 'Unknown')}"
                        ]
                        
                        embed.add_field(
                            name="Ship Registry Information",
                            value="\n".join(registry_details),
                            inline=False
                        )
                except Exception as e:
                    logger.error(f"Error getting ship registry info: {e}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error viewing ship assignment: {e}")
            await interaction.followup.send(
                "An error occurred while retrieving ship assignment details.",
                ephemeral=True
            )

class ComparisonView(discord.ui.View):
    """View for comparing two profiles side by side."""
    
    def __init__(self, cog, member1: discord.Member, member2: discord.Member, 
                 data1: dict, data2: dict, viewer: discord.Member):
        super().__init__(timeout=180)
        self.cog = cog
        self.member1 = member1
        self.member2 = member2
        self.data1 = data1
        self.data2 = data2
        self.viewer = viewer
        self.current_category = "basic"
        
    async def create_comparison_embed(self) -> discord.Embed:
        """Create an embed comparing two members based on selected category."""
        embed = discord.Embed(
            title=f"Profile Comparison",
            description=f"Comparing {self.member1.display_name} and {self.member2.display_name}",
            color=discord.Color.blue()
        )
        
        values1 = self.data1.get('values', {})
        values2 = self.data2.get('values', {})
        
        if self.current_category == "basic":
            # Basic info comparison
            embed.add_field(
                name=f"{self.member1.display_name}",
                value=self.cog.formatter.format_basic_info(values1),
                inline=True
            )
            embed.add_field(
                name=f"{self.member2.display_name}",
                value=self.cog.formatter.format_basic_info(values2),
                inline=True
            )
            
        elif self.current_category == "stats":
            # Stats comparison
            embed.add_field(
                name=f"{self.member1.display_name}",
                value=self.cog.formatter.format_quick_stats(values1),
                inline=True
            )
            embed.add_field(
                name=f"{self.member2.display_name}",
                value=self.cog.formatter.format_quick_stats(values2),
                inline=True
            )
            
        elif self.current_category == "service":
            # Service record comparison
            embed.add_field(
                name=f"{self.member1.display_name}",
                value=self.cog.formatter.format_service_record(values1),
                inline=True
            )
            embed.add_field(
                name=f"{self.member2.display_name}",
                value=self.cog.formatter.format_service_record(values2),
                inline=True
            )
            
        elif self.current_category == "awards":
            # Awards comparison
            embed.add_field(
                name=f"{self.member1.display_name}",
                value=self.cog.formatter.format_awards(values1),
                inline=True
            )
            embed.add_field(
                name=f"{self.member2.display_name}",
                value=self.cog.formatter.format_awards(values2),
                inline=True
            )
        
        # Add thumbnails for both members
        # Discord embeds don't support multiple thumbnails, so we'll use images
        embed.set_thumbnail(url=self.member1.display_avatar.url)
        embed.set_image(url=self.member2.display_avatar.url)
        
        # Add a footer
        timestamp = datetime.now(timezone.utc).strftime('%Y.%m.%d-%H%M')
        embed.set_footer(text=f"Comparison generated: {timestamp} UTC")
        
        return embed
        
    @discord.ui.select(
        placeholder="Select comparison category",
        options=[
            discord.SelectOption(label="Basic Information", value="basic", 
                                emoji="📋", description="Compare basic profile data"),
            discord.SelectOption(label="Statistics", value="stats", 
                                emoji="📊", description="Compare performance statistics"),
            discord.SelectOption(label="Service Record", value="service", 
                                emoji="📜", description="Compare service histories"),
            discord.SelectOption(label="Awards", value="awards", 
                                emoji="🏅", description="Compare awards and decorations")
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle category selection."""
        self.current_category = select.values[0]
        embed = await self.create_comparison_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Dispatch profile_comparison_viewed event
        if hasattr(self.cog, 'dispatch_event'):
            await self.cog.dispatch_event(
                'profile_comparison_category_selected',
                member1_id=self.member1.id,
                member2_id=self.member2.id,
                viewer_id=interaction.user.id,
                category=self.current_category
            )

class AchievementUnlockModal(discord.ui.Modal):
    """Modal for configuring achievement unlock notifications."""
    
    def __init__(self, title: str, cog, member: discord.Member):
        super().__init__(title=title)
        self.cog = cog
        self.member = member
        
        self.achievement_name = discord.ui.TextInput(
            label="Achievement Name",
            placeholder="Enter achievement name",
            required=True,
            max_length=100
        )
        self.add_item(self.achievement_name)
        
        self.achievement_description = discord.ui.TextInput(
            label="Achievement Description",
            placeholder="Enter achievement description",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000
        )
        self.add_item(self.achievement_description)
        
        self.award = discord.ui.TextInput(
            label="Related Award (Optional)",
            placeholder="Enter related award name if applicable",
            required=False,
            max_length=100
        )
        self.add_item(self.award)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            # Send achievement unlock notification
            success = await self.cog.send_achievement_unlock(
                self.member,
                str(self.achievement_name),
                str(self.achievement_description),
                str(self.award) if self.award.value else None
            )
            
            if success:
                await interaction.followup.send(f"✅ Achievement notification sent to {self.member.mention}!")
                
                # Log the achievement
                if hasattr(self.cog, 'audit_logger'):
                    await self.cog.audit_logger.log_action(
                        'achievement_sent',
                        interaction.user,
                        self.member,
                        f"Achievement: {self.achievement_name.value}"
                    )
            else:
                await interaction.followup.send("⚠️ Could not send DM to user. Achievement may not have been delivered.")
        except Exception as e:
            logger.error(f"Error sending achievement: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to send achievement notification.")

class PaginatedContentView(discord.ui.View):
    """View for paginating long content like mission logs."""
    
    def __init__(self, all_entries: List[str], entries_per_page: int = 5):
        super().__init__(timeout=180)
        self.all_entries = all_entries
        self.entries_per_page = entries_per_page
        self.current_page = 0
        self.max_pages = max(1, (len(all_entries) + entries_per_page - 1) // entries_per_page)
        
    def get_current_page_content(self) -> str:
        """Get content for the current page."""
        start_idx = self.current_page * self.entries_per_page
        end_idx = min(start_idx + self.entries_per_page, len(self.all_entries))
        
        entries = self.all_entries[start_idx:end_idx]
        content = "\n".join([f"• {entry}" for entry in entries])
        
        if not content:
            return "No entries to display"
        
        footer = f"Page {self.current_page + 1}/{self.max_pages}"
        return f"```yaml\n{content}\n\n{footer}\n```"
    
    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        self.current_page = max(0, self.current_page - 1)
        
        # Update button states
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.max_pages - 1)
        
        # Update content
        await interaction.response.edit_message(
            content=self.get_current_page_content(),
            view=self
        )
        
    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        self.current_page = min(self.max_pages - 1, self.current_page + 1)
        
        # Update button states
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.max_pages - 1)
        
        # Update content
        await interaction.response.edit_message(
            content=self.get_current_page_content(),
            view=self
        )

class BulkAwardModal(discord.ui.Modal):
    """Modal for selecting multiple members for bulk awards."""
    
    def __init__(self, cog, award: str, citation: str):
        super().__init__(title="Bulk Award Members")
        self.cog = cog
        self.award = award
        self.citation = citation
        
        self.members_input = discord.ui.TextInput(
            label="Member IDs or @mentions (one per line)",
            style=discord.TextStyle.paragraph,
            placeholder="Enter member IDs or @mentions, one per line",
            required=True
        )
        self.add_item(self.members_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Parse member IDs
        member_lines = self.members_input.value.split('\n')
        member_ids = []
        
        for line in member_lines:
            line = line.strip()
            if not line:
                continue
                
            # Try to extract ID from @mention format
            if line.startswith('<@') and line.endswith('>'):
                try:
                    member_id = int(line[2:-1].replace('!', ''))
                    member_ids.append(member_id)
                except ValueError:
                    pass
            # Try to parse as direct ID
            elif line.isdigit():
                member_ids.append(int(line))
        
        if not member_ids:
            await interaction.followup.send("❌ No valid member IDs provided.", ephemeral=True)
            return
            
        # Get guild members
        guild = interaction.guild
        valid_members = []
        invalid_ids = []
        
        for member_id in member_ids:
            member = guild.get_member(member_id)
            if member:
                valid_members.append(member)
            else:
                invalid_ids.append(member_id)
        
        if not valid_members:
            await interaction.followup.send("❌ None of the provided IDs matched active server members.", ephemeral=True)
            return
            
        # Create confirmation view
        embed = discord.Embed(
            title="Confirm Bulk Award",
            description=f"You are about to award the **{self.award}** to {len(valid_members)} members.",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Citation", value=self.citation, inline=False)
        
        # List members (up to 10)
        member_list = "\n".join([f"• {m.mention} ({m.display_name})" for m in valid_members[:10]])
        if len(valid_members) > 10:
            member_list += f"\n• ...and {len(valid_members) - 10} more"
            
        embed.add_field(name="Recipients", value=member_list, inline=False)
        
        if invalid_ids:
            embed.add_field(
                name="Invalid IDs",
                value=f"{len(invalid_ids)} ID(s) could not be found in the server.",
                inline=False
            )
        
        # Create confirmation view
        view = discord.ui.View(timeout=60)
        
        async def confirm_callback(confirm_interaction: discord.Interaction):
            if confirm_interaction.user.id != interaction.user.id:
                await confirm_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                return
                
            await confirm_interaction.response.defer()
            
            # Process the awards
            results = await self.cog.process_bulk_awards(valid_members, self.award, self.citation)
            
            # Create results embed
            results_embed = discord.Embed(
                title="Bulk Award Results",
                description=f"Processed {len(valid_members)} award(s).",
                color=discord.Color.green()
            )
            
            success_count = sum(1 for r in results if r[1])
            results_embed.add_field(
                name="Summary",
                value=f"✅ {success_count} successful\n❌ {len(results) - success_count} failed",
                inline=False
            )
            
            if len(results) - success_count > 0:
                failures = [f"• {r[0].mention}: {r[2]}" for r in results if not r[1]]
                results_embed.add_field(
                    name="Failures",
                    value="\n".join(failures[:10]) + (
                        f"\n...and {len(failures) - 10} more" if len(failures) > 10 else ""
                    ),
                    inline=False
                )
            
            await confirm_interaction.edit_original_response(
                content="Award processing complete.",
                embed=results_embed,
                view=None
            )
            
            # Dispatch bulk_awards_processed event
            if hasattr(self.cog, 'dispatch_event'):
                await self.cog.dispatch_event(
                    'bulk_awards_processed',
                    member_ids=[m.id for m in valid_members],
                    award=self.award,
                    citation=self.citation,
                    success_count=success_count,
                    total_count=len(valid_members),
                    processed_by=interaction.user.id
                )
            
        async def cancel_callback(cancel_interaction: discord.Interaction):
            if cancel_interaction.user.id != interaction.user.id:
                await cancel_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                return
                
            await cancel_interaction.response.edit_message(
                content="Bulk award cancelled.",
                embed=None,
                view=None
            )
            
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.success)
        confirm_button.callback = confirm_callback
        
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger)
        cancel_button.callback = cancel_callback
        
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        await interaction.followup.send(embed=embed, view=view)

class FleetReportView(discord.ui.View):
    """View for displaying fleet wing reports."""
    
    def __init__(self, cog, fleet_wing: str, members_data: List[tuple]):
        super().__init__(timeout=180)
        self.cog = cog
        self.fleet_wing = fleet_wing
        self.members_data = members_data  # List of (member, member_data) tuples
        self.current_page = 0
        self.members_per_page = 5
        self.max_pages = max(1, (len(members_data) + self.members_per_page - 1) // self.members_per_page)
        self.sort_by = "rank"  # Default sort
        
    def sort_members(self):
        """Sort members based on current sort criteria."""
        if self.sort_by == "rank":
            # Sort by rank (higher ranks first)
            self.members_data.sort(key=lambda x: x[1].get('values', {}).get('rank_index', 0), reverse=True)
        elif self.sort_by == "name":
            # Sort by name
            self.members_data.sort(key=lambda x: x[0].display_name.lower())
        elif self.sort_by == "service":
            # Sort by time in service (longest first)
            self.members_data.sort(
                key=lambda x: x[1].get('values', {}).get('Join Date', '2099-01-01')
            )
        elif self.sort_by == "missions":
            # Sort by mission count (highest first)
            self.members_data.sort(
                key=lambda x: int(x[1].get('values', {}).get('Mission Count', 0)), 
                reverse=True
            )
        elif self.sort_by == "status":
            # Sort by status (active first)
            status_order = {"Active": 0, "Deployed": 1, "Training": 2, "On Leave": 3, "Inactive": 4}
            self.members_data.sort(
                key=lambda x: status_order.get(x[1].get('values', {}).get('Status', 'Unknown'), 999)
            )
        elif self.sort_by == "ship":
            # Sort by ship assignment
            self.members_data.sort(
                key=lambda x: x[1].get('values', {}).get('Ship Assignment', 'Unassigned').lower()
            )
    
    async def get_current_page_embed(self):
        """Get embed for current page."""
        self.sort_members()
        
        start_idx = self.current_page * self.members_per_page
        end_idx = min(start_idx + self.members_per_page, len(self.members_data))
        
        current_members = self.members_data[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"{self.fleet_wing} Report",
            description=f"Showing members {start_idx+1}-{end_idx} of {len(self.members_data)}",
            color=discord.Color.blue()
        )
        
        # Add summary stats
        active_count = sum(1 for _, data in self.members_data 
                        if data.get('values', {}).get('Status') == 'Active')
        
        embed.add_field(
            name="Wing Stats",
            value=f"Total Members: {len(self.members_data)}\nActive Members: {active_count}",
            inline=False
        )
        
        # Add member entries
        for member, data in current_members:
            values = data.get('values', {})
            
            # Create a compact member entry
            rank = values.get('Rank', 'N/A')
            status = values.get('Status', 'Unknown')
            status_emoji = {
                'Active': '🟢', 'Inactive': '🔴', 'On Leave': '🟡', 
                'Training': '🔵', 'Deployed': '🟣'
            }.get(status, '⚪')
            
            spec = values.get('Specialization', 'N/A')
            join_date = values.get('Join Date', 'Unknown')
            from .utils import calculate_service_time
            service_time = calculate_service_time(join_date)
            mission_count = values.get('Mission Count', 0)
            ship_assignment = values.get('Ship Assignment', 'Unassigned')
            
            value = (
                f"**Rank:** {rank}\n"
                f"**Status:** {status_emoji} {status}\n"
                f"**Specialization:** {spec}\n"
                f"**Ship:** {ship_assignment}\n"
                f"**Service:** {service_time}\n"
                f"**Missions:** {mission_count}"
            )
            
            embed.add_field(
                name=member.display_name,
                value=value,
                inline=True
            )
        
        # Add footer with page info
        embed.set_footer(text=f"Page {self.current_page+1}/{self.max_pages} • Sorted by: {self.sort_by}")
        
        return embed
        
    @discord.ui.select(
        placeholder="Sort by...",
        options=[
            discord.SelectOption(label="Sort by Rank", value="rank", emoji="⭐"),
            discord.SelectOption(label="Sort by Name", value="name", emoji="📋"),
            discord.SelectOption(label="Sort by Service Time", value="service", emoji="⏱️"),
            discord.SelectOption(label="Sort by Mission Count", value="missions", emoji="🚀"),
            discord.SelectOption(label="Sort by Status", value="status", emoji="🔵"),
            discord.SelectOption(label="Sort by Ship", value="ship", emoji="🚢")
        ]
    )
    async def sort_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Handle sort selection."""
        self.sort_by = select.values[0]
        self.current_page = 0  # Reset to first page
        embed = await self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Previous Page", style=discord.ButtonStyle.grey)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on the first page!", ephemeral=True)
            
    @discord.ui.button(label="Next Page", style=discord.ButtonStyle.grey)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on the last page!", ephemeral=True)
            
    @discord.ui.button(label="Export All", style=discord.ButtonStyle.green, emoji="📄")
    async def export_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Export all wing members to CSV."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            csv_data = await self.cog.export_fleet_to_csv(self.fleet_wing, self.members_data)
            import io
            file = discord.File(
                io.StringIO(csv_data),
                filename=f"{self.fleet_wing.replace(' ', '_')}_fleet.csv"
            )
            await interaction.followup.send(
                f"Here's the export of all {len(self.members_data)} members in {self.fleet_wing}:",
                file=file,
                ephemeral=True
            )
            
            # Dispatch wing_exported event
            if hasattr(self.cog, 'dispatch_event'):
                await self.cog.dispatch_event(
                    'fleet_wing_exported',
                    fleet_wing=self.fleet_wing,
                    export_format="csv",
                    exported_by=interaction.user.id,
                    member_count=len(self.members_data)
                )
        except Exception as e:
            logger.error(f"Error exporting fleet wing: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to export fleet wing data.", ephemeral=True)

# Add a backward compatibility class that extends FleetReportView
class DivisionReportView(FleetReportView):
    """Backward compatibility class for division reports."""
    
    def __init__(self, cog, division: str, members_data: List[tuple]):
        # Map division to fleet wing if needed
        fleet_wing = DIVISION_TO_FLEET_WING.get(division, division)
        super().__init__(cog, fleet_wing, members_data)
        self.division = division  # Keep original division name
        
    async def get_current_page_embed(self):
        """Get embed for current page with division title for backward compatibility."""
        embed = await super().get_current_page_embed()
        embed.title = f"{self.division} Division Report"
        return embed

class StatusChangeModal(discord.ui.Modal):
    """Modal for changing a member's status."""
    
    def __init__(self, cog, member: discord.Member, current_status: str):
        super().__init__(title=f"Change Status for {member.display_name}")
        self.cog = cog
        self.member = member
        self.current_status = current_status
        
        self.status = discord.ui.TextInput(
            label="New Status",
            placeholder="Enter new status (Active, Inactive, On Leave, etc.)",
            required=True,
            default=current_status
        )
        self.add_item(self.status)
        
        self.reason = discord.ui.TextInput(
            label="Reason for Status Change",
            placeholder="Enter reason for the status change",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.reason)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            success = await self.cog.update_member_status(
                self.member, 
                str(self.status), 
                str(self.reason)
            )
            
            if success:
                await interaction.followup.send(
                    f"✅ Status for {self.member.mention} changed to {self.status}."
                )
                
                # Log the status change
                if hasattr(self.cog, 'audit_logger'):
                    await self.cog.audit_logger.log_action(
                        'status_change',
                        interaction.user,
                        self.member,
                        f"Status changed to {self.status}: {self.reason}"
                    )
            else:
                await interaction.followup.send(
                    "❌ Failed to update status. Please try again.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error updating status: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while updating the status.",
                ephemeral=True
            )

class MemberSearchView(discord.ui.View):
    """View for searching and filtering members."""
    
    def __init__(self, cog, members_data: List[tuple], search_type: str, query: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.all_members_data = members_data  # Original data
        self.filtered_members = members_data.copy()  # Filtered data
        self.search_type = search_type
        self.query = query
        self.current_page = 0
        self.members_per_page = 5
        self.max_pages = max(1, (len(self.filtered_members) + self.members_per_page - 1) // self.members_per_page)
        
    async def get_current_page_embed(self):
        """Get embed for current page."""
        start_idx = self.current_page * self.members_per_page
        end_idx = min(start_idx + self.members_per_page, len(self.filtered_members))
        
        current_members = self.filtered_members[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"Member Search Results",
            description=f"Search type: {self.search_type} | Query: '{self.query}'\n"
                       f"Found {len(self.filtered_members)} matches. Showing {start_idx+1}-{end_idx}",
            color=discord.Color.blue()
        )
        
        # Add member entries
        for member, data in current_members:
            values = data.get('values', {})
            
            # Get fleet wing (with backward compatibility)
            fleet_wing = values.get('Fleet Wing')
            if not fleet_wing:
                division = values.get('Division', 'N/A')
                fleet_wing = DIVISION_TO_FLEET_WING.get(division, division)
            
            # Create a compact member entry
            rank = values.get('Rank', 'N/A')
            status = values.get('Status', 'Unknown')
            status_emoji = {
                'Active': '🟢', 'Inactive': '🔴', 'On Leave': '🟡', 
                'Training': '🔵', 'Deployed': '🟣'
            }.get(status, '⚪')
            
            spec = values.get('Specialization', 'N/A')
            ship_assignment = values.get('Ship Assignment', 'Unassigned')
            
            # Highlight what matched the search
            highlighted_value = ""
            if self.search_type == "certification":
                certifications = data.get('values', {}).get('Certifications', '')
                from .utils import parse_list_field
                certs_list = parse_list_field(certifications)
                matching_certs = [f"**{cert}**" for cert in certs_list if self.query.lower() in cert.lower()]
                if matching_certs:
                    highlighted_value = f"Matching certifications:\n" + "\n".join(matching_certs)
            elif self.search_type == "award":
                awards = data.get('values', {}).get('Awards', '')
                from .utils import parse_list_field
                awards_list = parse_list_field(awards)
                matching_awards = [f"**{award}**" for award in awards_list if self.query.lower() in award.lower()]
                if matching_awards:
                    highlighted_value = f"Matching awards:\n" + "\n".join(matching_awards)
            
            value = (
                f"**Fleet Wing:** {fleet_wing}\n"
                f"**Rank:** {rank}\n"
                f"**Status:** {status_emoji} {status}\n"
                f"**Specialization:** {spec}\n"
                f"**Ship:** {ship_assignment}\n"
            )
            
            if highlighted_value:
                value += f"\n{highlighted_value}"
            
            embed.add_field(
                name=member.display_name,
                value=value,
                inline=False
            )
        
        # Add footer with page info
        embed.set_footer(text=f"Page {self.current_page+1}/{self.max_pages}")
        
        return embed
        
    @discord.ui.button(label="Previous Page", style=discord.ButtonStyle.grey)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on the first page!", ephemeral=True)
            
    @discord.ui.button(label="Next Page", style=discord.ButtonStyle.grey)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on the last page!", ephemeral=True)
            
    @discord.ui.button(label="Filter Active Only", style=discord.ButtonStyle.green)
    async def filter_active(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Filter to show only active members."""
        if button.label == "Filter Active Only":
            self.filtered_members = [
                (member, data) for member, data in self.all_members_data 
                if data.get('values', {}).get('Status') == 'Active'
            ]
            button.label = "Show All Statuses"
            button.style = discord.ButtonStyle.grey
        else:
            self.filtered_members = self.all_members_data.copy()
            button.label = "Filter Active Only"
            button.style = discord.ButtonStyle.green
            
        self.current_page = 0
        self.max_pages = max(1, (len(self.filtered_members) + self.members_per_page - 1) // self.members_per_page)
        
        embed = await self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Export Results", style=discord.ButtonStyle.blurple)
    async def export_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Export search results to CSV."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            csv_data = await self.cog.export_search_to_csv(self.search_type, self.query, self.filtered_members)
            import io
            file = discord.File(
                io.StringIO(csv_data),
                filename=f"search_results_{self.search_type}_{self.query}.csv"
            )
            await interaction.followup.send(
                f"Here's the export of {len(self.filtered_members)} search results:",
                file=file,
                ephemeral=True
            )
            
            # Dispatch search_results_exported event
            if hasattr(self.cog, 'dispatch_event'):
                await self.cog.dispatch_event(
                    'search_results_exported',
                    search_type=self.search_type,
                    query=self.query,
                    exported_by=interaction.user.id,
                    result_count=len(self.filtered_members)
                )
        except Exception as e:
            logger.error(f"Error exporting search results: {e}", exc_info=True)
            await interaction.followup.send("❌ Failed to export search results.", ephemeral=True)

class AwardGalleryView(discord.ui.View):
    """Paginated view for awards gallery."""
    
    def __init__(self, awards: List[str], timeout: int = 180):
        super().__init__(timeout=timeout)
        self.awards = awards
        self.current_page = 0
        self.awards_per_page = 3
        self.max_pages = max(1, (len(awards) + self.awards_per_page - 1) // self.awards_per_page)
        
    def get_current_embed(self) -> discord.Embed:
        """Get embed for current page."""
        start_idx = self.current_page * self.awards_per_page
        end_idx = min(start_idx + self.awards_per_page, len(self.awards))
        
        current_awards = self.awards[start_idx:end_idx]
        
        embed = discord.Embed(
            title="Awards Gallery",
            description=f"Showing awards {start_idx+1}-{end_idx} of {len(self.awards)}",
            color=discord.Color.gold()
        )
        
        for award in current_awards:
            parts = award.split(' - ')
            name = parts[0]
            citation = parts[1] if len(parts) > 1 else "No citation provided"
            date = parts[2] if len(parts) > 2 else "Unknown date"
            
            embed.add_field(
                name=name,
                value=f"Citation: {citation}\nAwarded: {date}",
                inline=False
            )
            
        embed.set_footer(text=f"Page {self.current_page+1}/{self.max_pages}")
        return embed
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            embed = self.get_current_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on the first page!", ephemeral=True)
            
    @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            embed = self.get_current_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on the last page!", ephemeral=True)