# cogs/views/promotion_views.py

import discord
from typing import Dict, Any, Optional
import logging
from ..constants import HIGH_RANKS

logger = logging.getLogger('promotion_views')

class PromotionReviewView(discord.ui.View):
    """View for command staff to review promotion recommendations."""
    
    def __init__(self, cog, user_id: int, proposed_rank: str, eligibility_details: Dict[str, Dict[str, Any]]):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.proposed_rank = proposed_rank
        self.eligibility_details = eligibility_details
        self.override_active = False
        self.override_reason = None

    @discord.ui.button(label="View Eligibility", style=discord.ButtonStyle.secondary)
    async def view_eligibility(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show detailed eligibility information and override options."""
        if not self.cog.has_required_rank(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to view eligibility details.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Promotion Eligibility Details",
            description="Review the eligibility requirements and status below.",
            color=discord.Color.blue()
        )

        for req, status in self.eligibility_details.items():
            embed.add_field(
                name=req,
                value=f"{'✅' if status['met'] else '❌'} {status['details']}",
                inline=False
            )

        can_override = any(not status['met'] for status in self.eligibility_details.values())
        view = None
        if can_override and any(role.name in HIGH_RANKS for role in interaction.user.roles):
            view = PromotionOverrideView(self)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle promotion approval."""
        try:
            if not self.cog.has_required_rank(interaction.user):
                await interaction.response.send_message(
                    "❌ You do not have permission to approve promotions.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            member = interaction.guild.get_member(self.user_id)
            if not member:
                await interaction.followup.send("❌ Member not found in the guild.", ephemeral=True)
                return

            success = await self.cog.promotion_manager.promote_member(
                interaction,
                member,
                "Non-Division",  # Default division
                self.proposed_rank,
                override_time=self.override_active
            )

            if success:
                await interaction.followup.send(
                    f"✅ Promotion to **{self.proposed_rank}** approved for {member.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ Failed to execute promotion.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in promotion approval: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle promotion denial."""
        if not self.cog.has_required_rank(interaction.user):
            await interaction.response.send_message(
                "❌ You do not have permission to deny promotions.",
                ephemeral=True
            )
            return

        modal = PromotionDenialModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)


class PromotionOverrideView(discord.ui.View):
    """View for handling requirement overrides."""
    
    def __init__(self, parent_view: PromotionReviewView):
        super().__init__(timeout=None)
        self.parent_view = parent_view

    @discord.ui.button(label="Override Requirements", style=discord.ButtonStyle.danger)
    async def override_requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.name in HIGH_RANKS for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You do not have permission to override requirements.",
                ephemeral=True
            )
            return

        modal = OverrideConfirmationModal(self.parent_view)
        await interaction.response.send_modal(modal)


class PromotionDenialModal(discord.ui.Modal, title="Promotion Denial Reason"):
    """Modal for providing reason when denying a promotion."""
    
    def __init__(self, cog, user_id: int):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        
        self.reason = discord.ui.TextInput(
            label="Denial Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Please provide the reason for denying this promotion...",
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.cog.coda_manager.update_promotion_request_status(
                str(self.user_id),
                'Denied',
                self.reason.value
            )

            member = interaction.guild.get_member(self.user_id)
            if member:
                try:
                    await member.send(
                        f"Your promotion recommendation has been denied.\nReason: {self.reason.value}"
                    )
                except discord.Forbidden:
                    logger.warning(f"Could not DM user {self.user_id} about promotion denial")

            await interaction.response.send_message(
                "✅ Promotion denied and member notified.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in denial submission: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing the denial.",
                ephemeral=True
            )


class OverrideConfirmationModal(discord.ui.Modal, title="Confirm Requirements Override"):
    """Modal for confirming requirement overrides."""
    
    def __init__(self, parent_view: PromotionReviewView):
        super().__init__()
        self.parent_view = parent_view
        
        self.reason = discord.ui.TextInput(
            label="Override Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Please provide the reason for overriding requirements...",
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.override_active = True
        self.parent_view.override_reason = self.reason.value

        await interaction.response.send_message(
            "✅ Requirements override confirmed. You may now proceed with the promotion approval.",
            ephemeral=True
        )