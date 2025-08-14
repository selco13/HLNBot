"""Command extensions for the profile cog."""

import discord
from discord.ext import commands
from discord import app_commands
import csv
import io
import logging
import os
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime, timezone

logger = logging.getLogger('profile.commands')

# Import constants directly instead of from cog to avoid circular import
from .constants import DOC_ID, TABLE_ID

class ProfileCommandExtensions:
    """Command extension methods for the ProfileCog."""
    
    async def generate_profile_pdf(self, member: discord.Member) -> io.BytesIO:
        """Generate a PDF of a member's profile."""
        try:
            from .pdf_utils import generate_profile_pdf
            
            member_row = await self.get_member_row(member.id)
            if not member_row:
                raise ValueError("No profile data found")
            
            # Return the PDF bytes buffer
            return await generate_profile_pdf(member, member_row, self.formatter)
            
        except ImportError:
            logger.error("ReportLab library not installed - PDF generation not available")
            raise ImportError("ReportLab library is required for PDF generation")
        except Exception as e:
            logger.error(f"Error generating PDF: {e}", exc_info=True)
            raise

    async def send_profile_visualization(self, interaction: discord.Interaction, member: discord.Member):
        """Send a visualization of a profile."""
        try:
            from .visualizations import generate_stats_chart, generate_award_chart, generate_career_timeline
            
            member_row = await self.get_member_row(member.id)
            if not member_row:
                await interaction.followup.send("No profile data found for this member.", ephemeral=True)
                return
                
            values = member_row.get('values', {})
            
            # Prepare data for the visualization
            from .utils import parse_list_field
            profile_data = {
                'Mission Count': values.get('Mission Count', 0),
                'Join Date': values.get('Join Date'),
                'Awards': parse_list_field(values.get('Awards', [])),
                'Mission Types': parse_list_field(values.get('Mission Types', [])),
                'Certifications': parse_list_field(values.get('Certifications', [])),
                'Combat Missions': parse_list_field(values.get('Combat Missions', [])),
                'Completed Missions': parse_list_field(values.get('Completed Missions', []))
            }
            
            # Create stats chart
            stats_file = await generate_stats_chart(profile_data)
            
            # Create awards chart if there are awards
            awards_file = None
            if profile_data['Awards']:
                awards_file = await generate_award_chart(profile_data['Awards'])
                
            # Create career timeline
            timeline_file = await generate_career_timeline(profile_data)
            
            # Create embed for the stats
            embed = discord.Embed(
                title=f"Profile Statistics for {member.display_name}",
                description="Visual representation of service record statistics.",
                color=discord.Color.blue()
            )
            
            embed.set_thumbnail(url=member.display_avatar.url)
            
            # Add some numeric stats to the embed
            embed.add_field(
                name="Service Summary",
                value=(
                    f"**Missions:** {profile_data['Mission Count']}\n"
                    f"**Combat Missions:** {len(profile_data['Combat Missions'])}\n"
                    f"**Awards:** {len(profile_data['Awards'])}\n"
                    f"**Certifications:** {len(profile_data['Certifications'])}"
                ),
                inline=False
            )
            
            files = [stats_file]
            if awards_file:
                files.append(awards_file)
            if timeline_file:
                files.append(timeline_file)
                
            # Send the visualization
            await interaction.followup.send(
                embed=embed,
                files=files,
                ephemeral=True
            )
            
            # Dispatch visualization_generated event
            if hasattr(self, 'dispatch_event'):
                await self.dispatch_event(
                    'profile_visualization_generated',
                    member_id=member.id,
                    chart_types=["stats"] + 
                              (["awards"] if awards_file else []) + 
                              (["timeline"] if timeline_file else [])
                )
            
        except Exception as e:
            logger.error(f"Error generating visualization: {e}", exc_info=True)
            await interaction.followup.send("Error generating visualization.", ephemeral=True)

    async def send_achievement_unlock(
        self, 
        member: discord.Member, 
        achievement_name: str, 
        description: str, 
        award: Optional[str] = None
    ) -> bool:
        """Send an achievement unlock notification to a member."""
        try:
            # Create embed for the achievement unlock
            embed = discord.Embed(
                title=f"🏆 Achievement Unlocked: {achievement_name}",
                description=description,
                color=discord.Color.gold()
            )
            
            # Add additional fields if an award is associated
            if award:
                embed.add_field(
                    name="Award Earned",
                    value=f"You have been awarded the **{award}**!",
                    inline=False
                )
            
            # Add timestamp and footer
            embed.timestamp = datetime.now()
            embed.set_footer(text="HLN Starward Fleet Achievements")
            
            # Try to DM the member
            try:
                await member.send(embed=embed)
                logger.info(f"Sent achievement notification to {member.name}: {achievement_name}")
                
                # Dispatch achievement_unlocked event
                if hasattr(self, 'dispatch_event'):
                    await self.dispatch_event(
                        'achievement_unlocked',
                        member_id=member.id,
                        achievement_name=achievement_name,
                        description=description,
                        award=award
                    )
                    
                return True
            except discord.Forbidden:
                logger.warning(f"Could not DM achievement to {member.name} - permissions")
                # Fall back to a channel mention if configured
                achievement_channel_id = os.getenv("ACHIEVEMENT_CHANNEL_ID")
                if achievement_channel_id:
                    try:
                        channel = self.bot.get_channel(int(achievement_channel_id))
                        if channel:
                            await channel.send(
                                content=f"Congratulations {member.mention}!",
                                embed=embed
                            )
                            return True
                    except Exception as channel_err:
                        logger.error(f"Error sending achievement to channel: {channel_err}")
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending achievement: {e}", exc_info=True)
            return False

    async def update_member_status(self, member: discord.Member, new_status: str, reason: str) -> bool:
        """Update a member's status and handle associated actions."""
        try:
            member_row = await self.get_member_row(member.id)
            if not member_row:
                logger.error(f"No profile found for member {member.id}")
                return False
                
            current_status = member_row.get('values', {}).get('Status', "Unknown")
            
            # Don't update if the status hasn't changed
            if current_status == new_status:
                logger.info(f"Status for {member.name} already set to {new_status}")
                return True
                
            # Update the profile
            success = await self.update_profile(
                member,
                {'Status': new_status},
                f"Status changed from {current_status} to {new_status}: {reason}"
            )
            
            if not success:
                logger.error(f"Failed to update status for {member.id}")
                return False
                
            # Handle additional actions based on the new status
            if new_status == "Inactive":
                # Look for an Inactive role to assign
                inactive_role = discord.utils.get(member.guild.roles, name="Inactive")
                if inactive_role and inactive_role not in member.roles:
                    await member.add_roles(inactive_role, reason=f"Status changed to Inactive: {reason}")
                    
                # Remove Active role if present
                active_role = discord.utils.get(member.guild.roles, name="Active")
                if active_role and active_role in member.roles:
                    await member.remove_roles(active_role, reason=f"Status changed to Inactive: {reason}")
                    
            elif new_status == "Active":
                # Add Active role
                active_role = discord.utils.get(member.guild.roles, name="Active")
                if active_role and active_role not in member.roles:
                    await member.add_roles(active_role, reason=f"Status changed to Active: {reason}")
                    
                # Remove Inactive role if present
                inactive_role = discord.utils.get(member.guild.roles, name="Inactive")
                if inactive_role and inactive_role in member.roles:
                    await member.remove_roles(inactive_role, reason=f"Status changed to Active: {reason}")
            
            # Log the status change
            if hasattr(self, 'audit_logger'):
                await self.audit_logger.log_action(
                    'status_change',
                    self.bot.user,
                    member,
                    f"Status changed from {current_status} to {new_status}: {reason}"
                )
                
            # Dispatch status_changed event
            if hasattr(self, 'dispatch_event'):
                await self.dispatch_event(
                    'status_changed',
                    member_id=member.id,
                    old_status=current_status,
                    new_status=new_status,
                    reason=reason
                )
                
            # Notify the member of the status change
            try:
                embed = discord.Embed(
                    title="Status Update",
                    description=f"Your status has been updated to **{new_status}**.",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.set_footer(text="HLN Starward Fleet")
                
                await member.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Could not DM status change to {member.name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating member status: {e}", exc_info=True)
            return False

    async def export_division_to_csv(self, division: str, members_data: List[tuple]) -> str:
        """Export division members to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow([
            "Name", "Discord ID", "Rank", "Specialization", "Status", 
            "ID Number", "Join Date", "Service Time", "Mission Count", 
            "Certifications", "Awards"
        ])
        
        # Write data rows
        for member, data in members_data:
            values = data.get('values', {})
            
            from .utils import parse_list_field, calculate_service_time
            certifications = ', '.join(parse_list_field(values.get('Certifications', [])))
            awards = ', '.join(parse_list_field(values.get('Awards', [])))
            join_date = values.get('Join Date', 'Unknown')
            service_time = calculate_service_time(join_date)
            
            writer.writerow([
                member.display_name,
                member.id,
                values.get('Rank', 'N/A'),
                values.get('Specialization', 'N/A'),
                values.get('Status', 'Unknown'),
                values.get('ID Number', 'N/A'),
                join_date,
                service_time,
                values.get('Mission Count', 0),
                certifications,
                awards
            ])
        
        return output.getvalue()

    async def export_search_to_csv(self, search_type: str, query: str, members_data: List[tuple]) -> str:
        """Export search results to CSV format."""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        writer.writerow([
            "Name", "Discord ID", "Division", "Rank", "Status", 
            "Specialization", "Matching Field", "Match Value"
        ])
        
        # Write data rows
        for member, data in members_data:
            values = data.get('values', {})
            
            # Determine what matched
            match_field = "N/A"
            match_value = "N/A"
            from .utils import parse_list_field
            
            if search_type == "certification":
                certifications = parse_list_field(values.get('Certifications', []))
                for cert in certifications:
                    if query.lower() in cert.lower():
                        match_field = "Certification"
                        match_value = cert
                        break
            elif search_type == "award":
                awards = parse_list_field(values.get('Awards', []))
                for award in awards:
                    if query.lower() in award.lower():
                        match_field = "Award"
                        match_value = award
                        break
            
            writer.writerow([
                member.display_name,
                member.id,
                values.get('Division', 'N/A'),
                values.get('Rank', 'N/A'),
                values.get('Status', 'Unknown'),
                values.get('Specialization', 'N/A'),
                match_field,
                match_value
            ])
        
        return output.getvalue()

    # Commands section moved to cog.py to avoid circular imports