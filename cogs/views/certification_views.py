# cogs/views/certification_views.py

import discord
from discord import ui
import logging
from typing import Optional, List, Dict, Any, TYPE_CHECKING, Callable
from datetime import datetime

if TYPE_CHECKING:
    from ..administration import AdministrationCog

logger = logging.getLogger('certification_views')

class CertificationGrantModal(ui.Modal, title="Grant Certification"):
    """Modal for providing additional details when granting certifications."""
    
    reason = ui.TextInput(
        label="Reason for granting certification",
        placeholder="Briefly explain why this certification is being granted...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )
    
    training_completed = ui.TextInput(
        label="Training/Qualifications Completed",
        placeholder="List training courses, exercises, or qualifications completed...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )
    
    assessment_date = ui.TextInput(
        label="Assessment Date (YYYY-MM-DD)",
        placeholder="When was the member assessed for this certification?",
        required=True,
        max_length=10
    )
    
    notes = ui.TextInput(
        label="Additional Notes",
        placeholder="Any additional information...",
        required=False,
        max_length=1000,
        style=discord.TextStyle.paragraph
    )
    
    def __init__(
        self, 
        cog: 'AdministrationCog', 
        member_id: int, 
        certification: str,
        callback: Callable
    ):
        super().__init__()
        self.cog = cog
        self.member_id = member_id
        self.certification = certification
        self.callback = callback
    
    async def on_submit(self, interaction: discord.Interaction):
        """Called when the user submits the modal."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Get the member
            guild = interaction.guild
            member = guild.get_member(self.member_id)
            if not member:
                await interaction.followup.send(
                    "❌ Member not found in the guild.",
                    ephemeral=True
                )
                return
                
            # Send the certification details to the callback
            await self.callback(
                interaction,
                member,
                self.certification,
                {
                    'reason': self.reason.value,
                    'training_completed': self.training_completed.value,
                    'assessment_date': self.assessment_date.value,
                    'notes': self.notes.value
                }
            )
        except Exception as e:
            logger.error(f"Error in CertificationGrantModal.on_submit: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing your request.",
                ephemeral=True
            )

class CertificationsView(ui.View):
    """View for displaying and managing member certifications."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.member = member
        self.embed = None
    
    async def create_embed(self) -> discord.Embed:
        """Create the certifications embed."""
        from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
        
        # Get member certifications
        member_certs = await self.cog.coda_manager.get_member_certifications(self.member.id)
        
        # Create categories
        categories = {
            "combat": {"basic": [], "advanced": []},
            "industrial": {"basic": [], "advanced": []},
            "technical": {"basic": [], "advanced": []},
            "medical": {"basic": [], "advanced": []},
            "specialized": {"basic": [], "advanced": []},
            "command": {"basic": [], "advanced": []},
            "ship": {"basic": [], "advanced": []},
            "other": {"basic": [], "advanced": []}
        }
        
        # Sort certifications by category and level
        for cert_id in member_certs:
            # Try CERTIFICATIONS first
            if cert_id in CERTIFICATIONS:
                info = CERTIFICATIONS[cert_id]
                category = info.get("category", "other")
                level = info.get("level", "basic")
                name = info.get("name", cert_id)
                
                if category in categories:
                    if level in categories[category]:
                        categories[category][level].append((cert_id, name))
            # Try SHIP_CERTIFICATIONS as fallback
            elif cert_id in SHIP_CERTIFICATIONS:
                info = SHIP_CERTIFICATIONS[cert_id]
                category = "ship"
                level = "advanced" if "HEAVY" in cert_id or "LARGE" in cert_id else "basic"
                name = info.get("name", cert_id)
                
                if "ship" in categories:
                    if level in categories["ship"]:
                        categories["ship"][level].append((cert_id, name))
            else:
                # Unknown certification
                if "other" in categories and "basic" in categories["other"]:
                    categories["other"]["basic"].append((cert_id, cert_id))
        
        # Create embed
        embed = discord.Embed(
            title=f"Certifications for {self.member.display_name}",
            description=f"Member has {len(member_certs)} certification(s)",
            color=discord.Color.blue()
        )
        
        # Add fields for each category
        for category, levels in categories.items():
            basic_certs = levels.get("basic", [])
            advanced_certs = levels.get("advanced", [])
            
            if basic_certs:
                embed.add_field(
                    name=f"Basic {category.title()}",
                    value="\n".join(f"• {name}" for _, name in basic_certs),
                    inline=False
                )
                
            if advanced_certs:
                embed.add_field(
                    name=f"Advanced {category.title()}",
                    value="\n".join(f"• {name}" for _, name in advanced_certs),
                    inline=False
                )
        
        embed.set_thumbnail(url=self.member.display_avatar.url)
        embed.set_footer(text=f"Last updated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        
        self.embed = embed
        return embed
    
    @ui.button(label="Grant Certification", style=discord.ButtonStyle.green, custom_id="grant_cert")
    async def grant_cert_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to grant a certification."""
        # Check if user has permission
        if not await self.cog.admin_command_permissions(interaction):
            return
        
        # Create a select menu for certification categories
        await interaction.response.send_message(
            "Select a certification category:",
            view=CertificationCategorySelectView(self.cog, self.member),
            ephemeral=True
        )
    
    @ui.button(label="Revoke Certification", style=discord.ButtonStyle.red, custom_id="revoke_cert")
    async def revoke_cert_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to revoke a certification."""
        # Check if user has permission
        if not await self.cog.admin_command_permissions(interaction):
            return
        
        # Get member certifications
        member_certs = await self.cog.coda_manager.get_member_certifications(self.member.id)
        if not member_certs:
            await interaction.response.send_message(
                f"{self.member.mention} has no certifications to revoke.",
                ephemeral=True
            )
            return
        
        # Create a select menu for revoking certifications
        await interaction.response.send_message(
            "Select a certification to revoke:",
            view=CertificationRevokeSelectView(self.cog, self.member, member_certs),
            ephemeral=True
        )
    
    @ui.button(label="Refresh", style=discord.ButtonStyle.blurple, custom_id="refresh")
    async def refresh_button(self, interaction: discord.Interaction, button: ui.Button):
        """Button to refresh the certifications view."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            embed = await self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
            await interaction.followup.send("✅ Refreshed certifications.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error refreshing certifications: {e}")
            await interaction.followup.send(
                "❌ Failed to refresh certifications.",
                ephemeral=True
            )

class CertificationCategorySelectView(ui.View):
    """View for selecting a certification category."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.member = member
        
        # Add select menu for categories
        self.add_item(CertificationCategorySelect(cog, member))

class CertificationCategorySelect(ui.Select):
    """Select menu for certification categories."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member):
        self.cog = cog
        self.member = member
        
        options = [
            discord.SelectOption(
                label="Combat",
                description="Combat-related certifications",
                value="combat"
            ),
            discord.SelectOption(
                label="Industrial",
                description="Industrial certifications",
                value="industrial"
            ),
            discord.SelectOption(
                label="Technical",
                description="Technical certifications",
                value="technical"
            ),
            discord.SelectOption(
                label="Medical",
                description="Medical certifications",
                value="medical"
            ),
            discord.SelectOption(
                label="Specialized",
                description="Specialized certifications",
                value="specialized"
            ),
            discord.SelectOption(
                label="Command",
                description="Command certifications",
                value="command"
            ),
            discord.SelectOption(
                label="Ship",
                description="Ship certifications",
                value="ship"
            )
        ]
        
        super().__init__(
            placeholder="Select a certification category",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Called when a category is selected."""
        await interaction.response.send_message(
            "Select a certification to grant:",
            view=CertificationSelectView(self.cog, self.member, self.values[0]),
            ephemeral=True
        )

class CertificationSelectView(ui.View):
    """View for selecting a certification to grant."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member, category: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.member = member
        self.category = category
        
        # Add select menu for certifications
        self.add_item(CertificationSelect(cog, member, category))

class CertificationSelect(ui.Select):
    """Select menu for certifications."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member, category: str):
        self.cog = cog
        self.member = member
        self.category = category
        
        from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
        
        # Filter certifications by category
        options = []
        
        if category != "ship":
            # Regular certifications
            category_certs = [
                (cert_id, info)
                for cert_id, info in CERTIFICATIONS.items()
                if info.get("category") == category
            ]
            
            # Sort by level (basic first, then advanced)
            category_certs.sort(key=lambda x: 0 if x[1].get("level") == "basic" else 1)
            
            # Create options
            for cert_id, info in category_certs:
                options.append(discord.SelectOption(
                    label=info.get("name", cert_id),
                    description=f"{info.get('level').title()} {category.title()} Certification",
                    value=cert_id
                ))
        else:
            # Ship certifications
            for cert_id, info in SHIP_CERTIFICATIONS.items():
                level = "advanced" if "HEAVY" in cert_id or "LARGE" in cert_id else "basic"
                options.append(discord.SelectOption(
                    label=info.get("name", cert_id),
                    description=f"{level.title()} Ship Certification",
                    value=cert_id
                ))
        
        # Limit to 25 options (Discord limit)
        options = options[:25]
        
        # If no options found
        if not options:
            options = [discord.SelectOption(
                label="No certifications found",
                description="No certifications found for this category",
                value="none"
            )]
        
        super().__init__(
            placeholder="Select a certification to grant",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Called when a certification is selected."""
        # Check if no certifications found
        if self.values[0] == "none":
            await interaction.response.send_message(
                "❌ No certifications found for this category.",
                ephemeral=True
            )
            return
            
        # Check if member already has this certification
        has_cert = await self.cog.coda_manager.check_certification(self.member.id, self.values[0])
        if has_cert:
            await interaction.response.send_message(
                f"⚠️ {self.member.mention} already has this certification.",
                ephemeral=True
            )
            return
        
        from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
        
        # Get certification name
        cert_id = self.values[0]
        cert_name = cert_id
        
        if cert_id in CERTIFICATIONS:
            cert_name = CERTIFICATIONS[cert_id].get("name", cert_id)
        elif cert_id in SHIP_CERTIFICATIONS:
            cert_name = SHIP_CERTIFICATIONS[cert_id].get("name", cert_id)
        
        # Show modal for additional details
        await interaction.response.send_modal(
            CertificationGrantModal(
                self.cog,
                self.member.id,
                self.values[0],
                self.process_certification_grant
            )
        )
    
    async def process_certification_grant(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        certification: str,
        details: Dict[str, str]
    ):
        """Process the certification grant after modal submission."""
        from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
        
        try:
            # Get certification name
            cert_name = certification
            if certification in CERTIFICATIONS:
                cert_name = CERTIFICATIONS[certification].get("name", certification)
            elif certification in SHIP_CERTIFICATIONS:
                cert_name = SHIP_CERTIFICATIONS[certification].get("name", certification)
            
            # Grant the certification
            success = await self.cog.coda_manager.add_certification(member.id, certification)
            
            if success:
                # Set certification expiry date if configured
                if hasattr(self.cog.config, 'CERT_EXPIRY_DAYS'):
                    from datetime import datetime, timedelta
                    expiry_date = datetime.now() + timedelta(days=self.cog.config['CERT_EXPIRY_DAYS'])
                    await self.cog.set_certification_expiry(member.id, certification, expiry_date)
                
                # Update certification roles
                await self.cog.update_certification_roles(member)
                
                # Log the certification grant
                await self.cog.coda_manager.log_certification_change(
                    member.id,
                    certification,
                    'granted',
                    interaction.user.id
                )
                
                # Send DM to member
                try:
                    dm_message = (
                        f"🏆 **Certification Granted** 🏆\n\n"
                        f"You have been granted the **{cert_name}** certification.\n\n"
                        f"Reason: {details['reason']}\n\n"
                        f"*Certification authorized by {interaction.user.display_name}*"
                    )
                    await member.send(dm_message)
                except discord.Forbidden:
                    logger.warning(f"Could not send certification DM to {member.name}")
                
                # Send announcement
                try:
                    cert_channel_id = self.cog.config.get('CERTIFICATION_CHANNEL_ID')
                    if cert_channel_id:
                        cert_channel = interaction.guild.get_channel(cert_channel_id)
                        if cert_channel:
                            embed = discord.Embed(
                                title="🏆 New Certification Granted",
                                description=f"{member.mention} has earned a new qualification!",
                                color=discord.Color.blue()
                            )
                            embed.add_field(name="Certification", value=cert_name, inline=True)
                            embed.add_field(name="Category", value=self.category.title(), inline=True)
                            embed.add_field(name="Assessment Date", value=details['assessment_date'], inline=True)
                            embed.add_field(name="Training Completed", value=details['training_completed'], inline=False)
                            if details['notes']:
                                embed.add_field(name="Notes", value=details['notes'], inline=False)
                            embed.set_thumbnail(url=member.display_avatar.url)
                            embed.set_footer(text=f"Granted by {interaction.user.display_name} • {datetime.now().strftime('%Y-%m-%d')}")
                            
                            await cert_channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error sending certification announcement: {e}")
                
                await interaction.followup.send(
                    f"✅ Successfully granted {cert_name} certification to {member.mention}.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to grant certification.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error granting certification: {e}")
            await interaction.followup.send(
                "❌ An error occurred while granting the certification.",
                ephemeral=True
            )

class CertificationRevokeSelectView(ui.View):
    """View for selecting a certification to revoke."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member, certifications: List[str]):
        super().__init__(timeout=120)
        self.cog = cog
        self.member = member
        
        # Add select menu for certifications
        self.add_item(CertificationRevokeSelect(cog, member, certifications))

class CertificationRevokeSelect(ui.Select):
    """Select menu for revoking certifications."""
    
    def __init__(self, cog: 'AdministrationCog', member: discord.Member, certifications: List[str]):
        self.cog = cog
        self.member = member
        
        from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
        
        # Create options
        options = []
        for cert_id in certifications:
            # Try CERTIFICATIONS first
            if cert_id in CERTIFICATIONS:
                info = CERTIFICATIONS[cert_id]
                category = info.get("category", "other").title()
                level = info.get("level", "basic").title()
                name = info.get("name", cert_id)
                
                options.append(discord.SelectOption(
                    label=name,
                    description=f"{level} {category} Certification",
                    value=cert_id
                ))
            # Try SHIP_CERTIFICATIONS as fallback
            elif cert_id in SHIP_CERTIFICATIONS:
                info = SHIP_CERTIFICATIONS[cert_id]
                level = "Advanced" if "HEAVY" in cert_id or "LARGE" in cert_id else "Basic"
                name = info.get("name", cert_id)
                
                options.append(discord.SelectOption(
                    label=name,
                    description=f"{level} Ship Certification",
                    value=cert_id
                ))
            else:
                # Unknown certification - just use ID
                options.append(discord.SelectOption(
                    label=cert_id,
                    description="Unknown Certification",
                    value=cert_id
                ))
        
        # Sort options by category and level
        options.sort(key=lambda x: (x.description, x.label))
        
        # Limit to 25 options (Discord limit)
        options = options[:25]
        
        # If no options found
        if not options:
            options = [discord.SelectOption(
                label="No certifications found",
                description="This member has no certifications",
                value="none"
            )]
        
        super().__init__(
            placeholder="Select a certification to revoke",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Called when a certification is selected."""
        # Check if no certifications found
        if self.values[0] == "none":
            await interaction.response.send_message(
                "❌ This member has no certifications to revoke.",
                ephemeral=True
            )
            return
            
        from ..constants import CERTIFICATIONS, SHIP_CERTIFICATIONS
        
        await interaction.response.defer(ephemeral=True)
        
        cert_id = self.values[0]
        
        # Get certification name
        cert_name = cert_id
        if cert_id in CERTIFICATIONS:
            cert_name = CERTIFICATIONS[cert_id].get("name", cert_id)
        elif cert_id in SHIP_CERTIFICATIONS:
            cert_name = SHIP_CERTIFICATIONS[cert_id].get("name", cert_id)
        
        # Create confirmation message
        embed = discord.Embed(
            title="Certification Revocation Confirmation",
            description=f"Are you sure you want to revoke the **{cert_name}** certification from {self.member.mention}?",
            color=discord.Color.red()
        )
        
        # Create confirmation buttons
        confirm_view = ui.View(timeout=60)
        
        confirm_button = ui.Button(label="Confirm", style=discord.ButtonStyle.red)
        cancel_button = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        
        async def confirm_callback(confirm_interaction: discord.Interaction):
            """Confirm button callback."""
            await confirm_interaction.response.defer(ephemeral=True)
            
            try:
                # Revoke the certification
                success = await self.cog.coda_manager.remove_certification(self.member.id, cert_id)
                
                if success:
                    # Remove certification expiry
                    await self.cog.remove_certification_expiry(self.member.id, cert_id)
                    
                    # Update certification roles
                    await self.cog.update_certification_roles(self.member)
                    
                    # Log the certification change
                    await self.cog.coda_manager.log_certification_change(
                        self.member.id,
                        cert_id,
                        'revoked',
                        interaction.user.id
                    )
                    
                    await confirm_interaction.followup.send(
                        f"✅ Successfully revoked {cert_name} certification from {self.member.mention}",
                        ephemeral=True
                    )
                else:
                    await confirm_interaction.followup.send(
                        "❌ Failed to revoke certification.",
                        ephemeral=True
                    )
            except Exception as e:
                logger.error(f"Error revoking certification: {e}")
                await confirm_interaction.followup.send(
                    "❌ An error occurred while revoking the certification.",
                    ephemeral=True
                )
                
        async def cancel_callback(cancel_interaction: discord.Interaction):
            """Cancel button callback."""
            await cancel_interaction.response.defer(ephemeral=True)
            await cancel_interaction.followup.send(
                "⚠️ Certification revocation cancelled.",
                ephemeral=True
            )
                
        # Add callbacks to buttons
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        # Add buttons to view
        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)
        
        # Send confirmation message
        await interaction.followup.send(embed=embed, view=confirm_view, ephemeral=True)