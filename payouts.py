# cogs/payouts.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, List, Dict, Tuple
from decimal import Decimal
import asyncio
import config
from datetime import datetime
from .banking import BankingCog, TransactionType, TransactionCategory

# ------------------------------ Logging Setup ------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ------------------------------ PayoutsCog Definition ------------------------------
class PayoutsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._banking_cog = None
        self.batch_size = 10  # Process payouts in batches of 10
        logger.info("PayoutsCog initialized.")

    @property
    def banking_cog(self) -> Optional[BankingCog]:
        """Get the BankingCog instance, loading it if necessary."""
        if self._banking_cog is None:
            self._banking_cog = self.bot.get_cog('BankingCog')
        return self._banking_cog

    async def process_batch_payouts(
        self, 
        payouts: List[Tuple[discord.Member, Decimal, str]]
    ) -> List[str]:
        """Process payouts in batch for multiple members.
        
        Args:
            payouts: List of tuples (member, amount, description)
            
        Returns:
            List of failed member display names
        """
        if not self.banking_cog:
            logger.error("BankingCog not available")
            return [member.display_name for member, _, _ in payouts]
        
        # Organize data for batch processing
        batch_payouts = []
        for member, amount, description in payouts:
            batch_payouts.append((
                member.id,
                amount,
                description,
                TransactionCategory.PAYOUT
            ))
        
        # Process the batch using the banking_cog's optimized method
        if hasattr(self.banking_cog, 'process_payouts'):
            results = await self.banking_cog.process_payouts(batch_payouts, self.batch_size)
        else:
            # Fall back to individual processing if the optimized method is not available
            results = []
            for member_id, amount, description, category in batch_payouts:
                success = await self.banking_cog.update_balance(member_id, amount)
                if success:
                    await self.banking_cog.add_transaction(
                        member_id,
                        TransactionType.VC_PAYOUT.value,
                        amount,
                        description=description,
                        category=category
                    )
                    results.append(True)
                else:
                    results.append(False)
        
        # Collect failed members
        failed_members = [
            payouts[i][0].display_name
            for i, result in enumerate(results)
            if not result
        ]
        
        # Log success/failure
        success_count = len(results) - len(failed_members)
        logger.info(f"Processed {len(results)} payouts: {success_count} succeeded, {len(failed_members)} failed")
        
        return failed_members

    @app_commands.command(
        name='vc_payout',
        description='Calculate and display payouts for members in voice channels.'
    )
    @app_commands.describe(
        total_amount='Total payout amount in aUEC.',
        bonus_per_member='Additional bonus per member (optional).',
        commit='Commit payouts to member accounts (yes/no). Default is no.'
    )
    async def vc_payout(
        self,
        interaction: discord.Interaction,
        total_amount: float,
        bonus_per_member: float = 0.0,
        commit: str = 'no'
    ):
        """Calculates and optionally commits payouts for voice channel members."""
        try:
            await interaction.response.defer()
            logger.info(f"'vc_payout' command invoked by {interaction.user} with total_amount={total_amount}, bonus_per_member={bonus_per_member}, commit={commit}.")
            
            if total_amount <= 0:
                await interaction.followup.send("❌ Total amount must be positive.", ephemeral=True)
                return
            if not self.banking_cog:
                await interaction.followup.send("❌ Banking system is currently unavailable.", ephemeral=True)
                return

            # Get all members connected to voice channels in the guild
            guild = interaction.guild
            voice_members = set()

            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if not member.bot:
                        voice_members.add(member)

            if not voice_members:
                await interaction.followup.send("❌ No members are currently connected to any voice channels.", ephemeral=True)
                logger.warning("No voice channel members found for payout.")
                return

            member_count = len(voice_members)
            base_payout = Decimal(str(total_amount)) / member_count if member_count else Decimal('0')
            bonus = Decimal(str(bonus_per_member))

            # Create an embed using BankingCog's formatting
            embed = discord.Embed(
                title="Voice Channel Payout Report",
                description=f"**Total Amount:** {total_amount:,.2f} aUEC\n"
                            f"**Members:** {member_count}\n"
                            f"**Base Payout:** {base_payout:,.2f} aUEC\n"
                            f"**Bonus per Member:** {bonus:,.2f} aUEC",
                color=0x00ff00,
                timestamp=datetime.now()
            )

            # Prepare to commit payouts if requested
            commit = commit.lower()
            if commit not in ['yes', 'no']:
                await interaction.followup.send("❌ Invalid value for 'commit'. Please use 'yes' or 'no'.", ephemeral=True)
                return

            should_commit = (commit == 'yes')
            if should_commit:
                # Check if the user has the required rank
                allowed_ranks = [
                    'Captain', 'Fleet Captain', 'Commodore', 'Rear Admiral Lower Half',
                    'Rear Admiral Upper Half', 'Vice Admiral', 'Admiral'
                ]
                user_roles = [role.name for role in interaction.user.roles]
                if not any(role in allowed_ranks for role in user_roles):
                    await interaction.followup.send(
                        "❌ You do not have the required rank to commit payouts. Only members ranked Captain or above can commit payouts.",
                        ephemeral=True
                    )
                    return

            # Prepare member payouts
            payout_description = f"Voice channel participation payout - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            # Sort members by display name for consistent reporting
            sorted_members = sorted(voice_members, key=lambda m: m.display_name.lower())
            
            # Add member fields to embed
            total_payout = Decimal('0')
            
            for member in sorted_members:
                payout = base_payout + bonus
                total_payout += payout
                
                embed.add_field(
                    name=member.display_name,
                    value=f"{payout:,.2f} aUEC",
                    inline=True
                )

            embed.add_field(
                name="Total Payout",
                value=f"{total_payout:,.2f} aUEC",
                inline=False
            )
            
            embed.set_footer(text=f"Total Members: {member_count} | Requested by: {interaction.user.display_name}")

            # Process the payouts if requested
            if should_commit:
                # Create batch payout data
                payout_data = [
                    (member, base_payout + bonus, payout_description)
                    for member in sorted_members
                ]
                
                # Process in batch
                failed_commits = await self.process_batch_payouts(payout_data)
                
                if failed_commits:
                    failed_members = ', '.join(failed_commits)
                    await interaction.followup.send(
                        f"✅ Payouts committed, but failed for: {failed_members}",
                        embed=embed
                    )
                else:
                    await interaction.followup.send(
                        "✅ Payouts successfully committed to all members.",
                        embed=embed
                    )
            else:
                await interaction.followup.send(
                    "ℹ️ Payouts calculated (not committed). Use 'commit: yes' to commit.",
                    embed=embed
                )

            logger.info(f"Payout report sent to {interaction.user} for {member_count} members.")
        except Exception as e:
            await interaction.followup.send("❌ An error occurred while processing your request.", ephemeral=True)
            logger.error(f"Error in 'vc_payout' command: {e}")


# ------------------------------ Cog Setup ------------------------------
async def setup(bot):
    logger.info("Setting up PayoutsCog")
    try:
        await bot.add_cog(PayoutsCog(bot))
        logger.info("PayoutsCog successfully added.")
    except Exception as e:
        logger.error(f"Failed to load PayoutsCog: {e}")