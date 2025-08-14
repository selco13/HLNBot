# cogs/role_sync.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import config  # Ensure this imports your configuration variables

class RoleSyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Define the slash command
    @app_commands.command(
        name="sync_associate_non_division",
        description="Assigns the 'Non-Division' role to all members with the 'Associate' role who lack it."
    )
    @app_commands.default_permissions(administrator=True)  # Restrict to administrators
    @app_commands.guilds(discord.Object(id=config.GUILD_ID))  # Specify your guild/server ID
    async def sync_associate_non_division(self, interaction: discord.Interaction):
        """Synchronizes roles by assigning 'Non-Division' to members with 'Associate'."""
        await interaction.response.defer(ephemeral=True)  # Acknowledge the command and defer the response

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ This command can only be used within a server.", ephemeral=True)
            logging.error("Command invoked outside of a guild.")
            return

        associate_role = discord.utils.get(guild.roles, name="Associate")
        non_division_role = discord.utils.get(guild.roles, name="Non-Division")

        if associate_role is None:
            await interaction.followup.send("❌ The role 'Associate' does not exist in this server.", ephemeral=True)
            logging.error("Role 'Associate' not found.")
            return

        if non_division_role is None:
            await interaction.followup.send("❌ The role 'Non-Division' does not exist in this server.", ephemeral=True)
            logging.error("Role 'Non-Division' not found.")
            return

        # Fetch all members with the 'Associate' role
        members_with_associate = [member for member in guild.members if associate_role in member.roles]

        if not members_with_associate:
            await interaction.followup.send("ℹ️ No members with the 'Associate' role were found.", ephemeral=True)
            logging.info("No members with 'Associate' role to process.")
            return

        # Initialize counters
        total_processed = 0
        roles_assigned = 0
        failed_assignments = 0

        # Iterate through members and assign 'Non-Division' role if they don't have it
        for member in members_with_associate:
            total_processed += 1
            if non_division_role not in member.roles:
                try:
                    await member.add_roles(non_division_role, reason="Role synchronization: Associate requires Non-Division role.")
                    roles_assigned += 1
                    logging.info(f"Assigned 'Non-Division' role to {member.display_name} (ID: {member.id}).")
                except discord.Forbidden:
                    failed_assignments += 1
                    logging.error(f"Permission denied when assigning 'Non-Division' role to {member.display_name} (ID: {member.id}).")
                except Exception as e:
                    failed_assignments += 1
                    logging.error(f"Unexpected error when assigning 'Non-Division' role to {member.display_name} (ID: {member.id}): {e}")

        # Prepare the result message
        embed = discord.Embed(
            title="Role Synchronization Complete",
            color=0x00ff00
        )
        embed.add_field(name="Total Members Processed", value=str(total_processed), inline=False)
        embed.add_field(name="Roles Assigned", value=str(roles_assigned), inline=False)
        if failed_assignments > 0:
            embed.add_field(name="Failed Assignments", value=str(failed_assignments), inline=False)

        # Send the result as a follow-up message
        await interaction.followup.send(embed=embed, ephemeral=True)

    # Error handler for app_commands in this cog
    @sync_associate_non_division.error
    async def sync_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You do not have the necessary permissions to use this command.",
                ephemeral=True
            )
            logging.warning(f"User {interaction.user} attempted to use a command without sufficient permissions.")
        else:
            await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
            logging.error(f"An unexpected error occurred in 'sync_associate_non_division' command: {error}")

async def setup(bot):
    await bot.add_cog(RoleSyncCog(bot))

