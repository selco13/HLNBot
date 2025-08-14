from __future__ import annotations

from typing import List, Optional, Dict, Any, Union, Type, TYPE_CHECKING, cast, Tuple, Set, Callable, Coroutine
import discord
from discord import SelectOption
from discord.ext import commands
from discord import app_commands
import logging
import os
import math
import time
import inspect
import importlib
import asyncio
from datetime import datetime
from decimal import Decimal

if TYPE_CHECKING:
    from discord import Interaction, Member, ButtonStyle, Color
    from discord.ui import Button, Select
    from .banking import TransactionType, TransactionData, BankingCog

logger = logging.getLogger('command_hub')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='command_hub.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Guild ID for commands
GUILD_ID = int(os.getenv('GUILD_ID', 0))

# Command Staff roles - users with these roles can access admin commands
COMMAND_STAFF_ROLES = [
    'Admiral',
    'Vice Admiral', 
    'Rear Admiral',
    'Commodore',
    'Fleet Captain',
    'Captain'
]

# Command categories with their emoji identifiers
COMMAND_CATEGORIES = {
    "General": {
        "emoji": "👤",
        "description": "General-purpose commands",
        "commands": ["profile", "help", "onboarding_status"]
    },
    "Banking": {
        "emoji": "💰",
        "description": "Banking and economy commands",
        "commands": ["banking", "balance", "deposit", "withdraw", "transfer", "vc_payout", "trade_profit", "mining_profit"]
    },
    "Ships": {
        "emoji": "🚀",
        "description": "Ship management and information",
        "commands": ["ship_info", "list_ships", "commission_ship", "manufacturers", "fleet_stats", "ship_lookup"]
    },
    "Missions": {
        "emoji": "🎯",
        "description": "Mission and operation management",
        "commands": ["create_mission", "join_mission", "leave_mission", "list_missions", "update_mission_status", "edit_mission"]
    },
    "Radio": {
        "emoji": "📻",
        "description": "Radio and audio controls",
        "commands": ["play", "stop", "stations", "volume", "nowplaying"]
    },
    "Organization": {
        "emoji": "🏢",
        "description": "Organization-related commands",
        "commands": ["alert_level", "alert_history", "select_division", "view_awards", "applyfleet"]
    },
    "Communications": {
        "emoji": "📡",
        "description": "Communication systems",
        "commands": ["setup_mission_comms", "mission_comms"]
    }
}

# Admin command categories
ADMIN_CATEGORIES = {
    "Administration": {
        "emoji": "⚙️",
        "description": "Core administrative commands",
        "commands": ["admin", "promote", "sync_commands", "sync_status", "eval"]
    },
    "Member Management": {
        "emoji": "👥",
        "description": "Member and profile management",
        "commands": ["add_award", "remove_award", "bulk_award", "division_report", "compare_profiles", "export_profile", "search_members"]
    },
    "Certification": {
        "emoji": "🏆",
        "description": "Certification management",
        "commands": ["my_certifications", "admin_certification", "certification", "certification_report"]
    },
    "Finance": {
        "emoji": "💵",
        "description": "Financial administration",
        "commands": ["admin_loan", "admin_budget", "evaluate_orders"]
    },
    "Ship Management": {
        "emoji": "🛥️",
        "description": "Fleet and ship administration",
        "commands": ["decommission_ship", "transfer_ship"]
    },
    "Orders": {
        "emoji": "📋",
        "description": "Order system management",
        "commands": ["order_system_start", "order_system_pause", "order_system_stop", "create_mission_order", 
                     "create_division_order", "create_major_order", "complete_order", "cancel_order", 
                     "add_objectives", "refresh_order_messages", "change_order_status", "set_order_due_date"]
    },
    "Security": {
        "emoji": "🔒",
        "description": "Security and protection",
        "commands": ["configure_raid_protection", "toggle_raid_protection", "toggle_join_notifications"]
    }
}

# Parameter types for autocomplete and selection
PARAM_TYPES = {
    "string": {"type": "text", "autocomplete": False},
    "number": {"type": "text", "autocomplete": False},
    "user": {"type": "text", "autocomplete": True},
    "ship": {"type": "text", "autocomplete": True},
    "mission": {"type": "text", "autocomplete": True},
    "mission_type": {"type": "select", "options": [
        "Combat", "Mining", "Trading", "Exploration", "Salvage", "Medical", "Transport", "Patrol", "Training", "Other"
    ]},
    "rank": {"type": "select", "options": [
        "Recruit", "Specialist", "Corporal", "Sergeant", "Lieutenant", "Captain", "Major", "Commander", "Admiral"
    ]},
    "division": {"type": "select", "options": [
        "Command", "Security", "Medical", "Engineering", "Science", "Operations", "Logistics"
    ]},
    "timezone": {"type": "select", "options": [
        "UTC-12", "UTC-11", "UTC-10", "UTC-9", "UTC-8", "UTC-7", "UTC-6", "UTC-5", 
        "UTC-4", "UTC-3", "UTC-2", "UTC-1", "UTC+0", "UTC+1", "UTC+2", "UTC+3", 
        "UTC+4", "UTC+5", "UTC+6", "UTC+7", "UTC+8", "UTC+9", "UTC+10", "UTC+11", "UTC+12"
    ]},
    "station": {"type": "select", "autocomplete": True},
    "order_type": {"type": "select", "options": [
        "Mission", "Division", "Major"
    ]},
    "alert_level": {"type": "select", "options": [
        "Green", "Yellow", "Orange", "Red", "Black"
    ]},
    "order_status": {"type": "select", "options": [
        "Planning", "Active", "Complete", "Failed", "Cancelled"
    ]}
}

class CommandCategory(discord.ui.Select):
    """Select menu for choosing command categories"""
    def __init__(self, view: discord.ui.View, categories: Dict[str, Dict[str, Any]], 
                 placeholder: str = "Select a category"):
        # Store view as parent_view to avoid name conflict with discord.py internals
        self.parent_view = view
        self.categories = categories
        
        options = []
        for category, data in categories.items():
            options.append(
                discord.SelectOption(
                    label=category,
                    description=data["description"],
                    emoji=data["emoji"],
                    value=category
                )
            )
            
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options
        )
        
    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        await self.parent_view.show_category(interaction, category)


class Command(discord.ui.Button):
    """Button for executing a command"""
    def __init__(self, cog: 'CommandHubCog', command_name: str, style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        command_info = cog.get_command_info(command_name)
        
        # Get emoji and format label
        emoji = command_info.get('emoji', '🔹')
        label = command_name.replace('_', ' ').title()
        
        # Ensure the label doesn't exceed Discord's 80-character limit
        if len(label) > 25:
            label = label[:22] + "..."
            
        super().__init__(
            style=style,
            label=label,
            emoji=emoji,
            custom_id=f"cmd:{command_name}"
        )
        
        self.cog = cog
        self.command_name = command_name
        
    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_command_button(interaction, self.command_name)


class HomeView(discord.ui.View):
    """Main view for command categories"""
    def __init__(self, cog: 'CommandHubCog', is_admin: bool = False):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.is_admin = is_admin
        
        # Select the right categories based on if this is an admin view
        if is_admin:
            categories = ADMIN_CATEGORIES
            placeholder = "Select admin category"
        else:
            categories = COMMAND_CATEGORIES
            placeholder = "Select command category"
            
        # Add the category selector
        self.add_item(CommandCategory(self, categories, placeholder))
        
        # Add quick action buttons for common commands
        if not is_admin:
            self.add_quick_action_buttons()
        
    def add_quick_action_buttons(self):
        """Add quick access buttons for common commands"""
        # Row 1: Common actions
        self.add_item(Command(self.cog, "profile", discord.ButtonStyle.primary))
        self.add_item(Command(self.cog, "banking", discord.ButtonStyle.primary))
        
        # Row 2: More actions
        self.add_item(Command(self.cog, "ship_info", discord.ButtonStyle.secondary))
        self.add_item(Command(self.cog, "list_missions", discord.ButtonStyle.secondary))
        
    async def show_category(self, interaction: discord.Interaction, category: str):
        """Show commands in the selected category"""
        view = CategoryView(self.cog, category, self.is_admin)
        
        if self.is_admin:
            title = f"⚙️ Admin: {category}"
            categories = ADMIN_CATEGORIES
        else:
            title = f"{COMMAND_CATEGORIES.get(category, {}).get('emoji', '📋')} {category} Commands"
            categories = COMMAND_CATEGORIES
            
        embed = discord.Embed(
            title=title,
            description=categories.get(category, {}).get('description', 'Select a command to execute'),
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryView(discord.ui.View):
    """View displaying commands in a category"""
    def __init__(self, cog: 'CommandHubCog', category: str, is_admin: bool = False):
        super().__init__(timeout=300)
        self.cog = cog
        self.category = category
        self.is_admin = is_admin
        
        # Get commands for this category
        if is_admin:
            commands_list = ADMIN_CATEGORIES.get(category, {}).get('commands', [])
            parent_categories = ADMIN_CATEGORIES
        else:
            commands_list = COMMAND_CATEGORIES.get(category, {}).get('commands', [])
            parent_categories = COMMAND_CATEGORIES
            
        # Add buttons for commands
        for cmd_name in commands_list:
            self.add_item(Command(cog, cmd_name))
            
        # Add category selector for easy navigation between categories
        self.add_item(CommandCategory(self, parent_categories, f"Current: {category}"))
        
        # Add back button
        self.add_item(BackToHomeButton(cog, is_admin))
        
    async def show_category(self, interaction: discord.Interaction, category: str):
        """Show a different category"""
        view = CategoryView(self.cog, category, self.is_admin)
        
        if self.is_admin:
            title = f"⚙️ Admin: {category}"
            categories = ADMIN_CATEGORIES
        else:
            title = f"{COMMAND_CATEGORIES.get(category, {}).get('emoji', '📋')} {category} Commands"
            categories = COMMAND_CATEGORIES
            
        embed = discord.Embed(
            title=title,
            description=categories.get(category, {}).get('description', 'Select a command to execute'),
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)


class BackToHomeButton(discord.ui.Button):
    """Button to return to the home view"""
    def __init__(self, cog: 'CommandHubCog', is_admin: bool = False):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="Back to Main Menu",
            emoji="🏠",
            row=4  # Always place at the bottom
        )
        self.cog = cog
        self.is_admin = is_admin
        
    async def callback(self, interaction: discord.Interaction):
        view = HomeView(self.cog, self.is_admin)
        
        if self.is_admin:
            title = "⚙️ Admin Command Hub"
            description = "Access administrative commands and functions"
        else:
            title = "🏟️ Command Hub"
            description = "Welcome to the organization command hub. Select a category or use quick actions below."
            
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)


class ParameterInputModal(discord.ui.Modal):
    """Modal for inputting command parameters"""
    def __init__(self, cog: 'CommandHubCog', command_name: str, command_info: Dict[str, Any]):
        super().__init__(title=f"Enter parameters for /{command_name}")
        self.cog = cog
        self.command_name = command_name
        self.command_info = command_info
        self.selections = {}  # Store selections from selectors
        
        # Track which params are handled by selectors
        self.selector_params = []
        
        # Add input fields for each parameter
        params = command_info.get('parameters', [])
        for param in params:
            param_type = command_info.get('parameter_types', {}).get(param, 'string')
            help_text = command_info.get('parameter_help', {}).get(param, f"Enter {param}")
            placeholder = help_text if len(help_text) < 100 else help_text[:97] + "..."
            
            # For text input parameters
            if PARAM_TYPES.get(param_type, {}).get('type') == 'text':
                # Determine if this should be a paragraph input
                is_paragraph = param in ['description', 'notes', 'reason', 'briefing']
                style = discord.TextStyle.paragraph if is_paragraph else discord.TextStyle.short
                
                self.add_item(
                    discord.ui.TextInput(
                        label=param.replace('_', ' ').title(),
                        placeholder=placeholder,
                        required=True,
                        style=style,
                        max_length=4000 if is_paragraph else 100,
                        custom_id=f"param_{param}"
                    )
                )
            else:
                # For parameters that will be handled by selectors, we'll remember them
                # but not add them to the modal (they'll be handled in a follow-up view)
                self.selector_params.append(param)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Collect parameters from inputs
            kwargs = {}
            for child in self.children:
                if isinstance(child, discord.ui.TextInput):
                    param_name = child.custom_id.replace("param_", "")
                    kwargs[param_name] = child.value
            
            # If we have selector parameters, show the selection view
            if self.selector_params:
                await self.handle_selector_params(interaction, kwargs)
            else:
                # Otherwise, execute the command with parameters
                await self.cog.execute_command(interaction, self.command_name, **kwargs)
            
        except Exception as e:
            logger.error(f"Error processing parameter input for {self.command_name}: {e}")
            await interaction.response.send_message(
                f"An error occurred while processing your input: {str(e)}",
                ephemeral=True
            )
    
    async def handle_selector_params(self, interaction: discord.Interaction, current_kwargs: Dict[str, Any]):
        """Show a view for selecting additional parameters"""
        selector_view = ParameterSelectorView(
            self.cog, 
            self.command_name, 
            self.command_info,
            self.selector_params,
            current_kwargs
        )
        
        embed = discord.Embed(
            title=f"Additional Parameters for /{self.command_name}",
            description="Please select values for the following parameters:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=selector_view, ephemeral=True)


class ParameterSelectorView(discord.ui.View):
    """View for selecting parameters from dropdown/select menus"""
    def __init__(self, cog: 'CommandHubCog', command_name: str, command_info: Dict[str, Any], 
                 selector_params: List[str], current_kwargs: Dict[str, Any]):
        super().__init__(timeout=300)
        self.cog = cog
        self.command_name = command_name
        self.command_info = command_info
        self.selector_params = selector_params
        self.current_kwargs = current_kwargs
        self.selections = {}
        
        # Add a select menu for each parameter
        for i, param in enumerate(selector_params):
            param_type = command_info.get('parameter_types', {}).get(param, 'string')
            self.add_select_for_param(param, param_type, i)
            
        # Add submit button
        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Submit",
            custom_id="submit",
            row=min(4, len(selector_params))  # Place at the end
        ))
        
        # Get the button we just added and set its callback
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == "submit":
                item.callback = self.on_submit
                break
    
    def add_select_for_param(self, param: str, param_type: str, row: int):
        """Add a select menu for a parameter"""
        # Get parameter options based on type
        param_info = PARAM_TYPES.get(param_type, {'type': 'text'})
        
        if param_info.get('type') == 'select' and 'options' in param_info:
            # Create a select with fixed options
            options = [
                discord.SelectOption(label=option, value=option)
                for option in param_info['options']
            ]
            
            select = discord.ui.Select(
                placeholder=f"Select {param.replace('_', ' ')}",
                options=options,
                custom_id=f"select_{param}",
                row=min(row, 4)  # Max 5 rows (0-4)
            )
            
            # Set the select callback
            select.callback = self.make_select_callback(param)
            
            self.add_item(select)
    
    def make_select_callback(self, param_name: str):
        """Create a callback for a select menu"""
        async def select_callback(interaction: discord.Interaction):
            # Store the selection
            select = discord.utils.get(self.children, custom_id=f"select_{param_name}")
            if select and hasattr(select, 'values') and select.values:
                self.selections[param_name] = select.values[0]
            
            await interaction.response.defer()
            
        return select_callback
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle submit button click"""
        # Combine selections with current kwargs
        kwargs = {**self.current_kwargs, **self.selections}
        
        # Check if we've made all required selections
        missing_params = [param for param in self.selector_params if param not in self.selections]
        
        if missing_params:
            await interaction.response.send_message(
                f"Please select values for the following parameters: {', '.join(missing_params)}",
                ephemeral=True
            )
            return
        
        # Execute the command with all parameters
        await self.cog.execute_command(interaction, self.command_name, **kwargs)


class CommandConfirmView(discord.ui.View):
    """View for confirming command execution"""
    def __init__(self, cog: 'CommandHubCog', command_name: str, command_info: Dict[str, Any]):
        super().__init__(timeout=60)  # Short timeout for confirmation
        self.cog = cog
        self.command_name = command_name
        self.command_info = command_info
        
    @discord.ui.button(label="Execute", style=discord.ButtonStyle.success)
    async def execute_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # If command needs parameters, show the parameter modal
        if 'parameters' in self.command_info and self.command_info['parameters']:
            modal = ParameterInputModal(self.cog, self.command_name, self.command_info)
            await interaction.response.send_modal(modal)
        else:
            # Execute parameterless command
            await self.cog.execute_command(interaction, self.command_name)
            
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable buttons
        for item in self.children:
            item.disabled = True
            
        await interaction.response.edit_message(view=self)
        await interaction.followup.send("Command cancelled", ephemeral=True)


class BankingView(discord.ui.View):
    """Specialized view for banking operations"""
    def __init__(self, cog: 'CommandHubCog'):
        super().__init__(timeout=300)
        self.cog = cog
        
        # Add transaction type selector
        options = [
            discord.SelectOption(
                label="Check Balance",
                description="View your current balance",
                emoji="💰",
                value="balance"
            ),
            discord.SelectOption(
                label="Deposit",
                description="Add funds to your account",
                emoji="💵",
                value="deposit"
            ),
            discord.SelectOption(
                label="Withdraw",
                description="Remove funds from your account",
                emoji="💸",
                value="withdraw"
            ),
            discord.SelectOption(
                label="Transfer",
                description="Send funds to another user",
                emoji="📤",
                value="transfer"
            ),
            discord.SelectOption(
                label="Transaction History",
                description="View your recent transactions",
                emoji="📊",
                value="history"
            )
        ]
        
        self.add_item(discord.ui.Select(
            placeholder="Select Transaction Type",
            options=options,
            custom_id="bank_action"
        ))
        
        # Get the select we just added and set its callback
        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.custom_id == "bank_action":
                item.callback = self.handle_banking_selection
                break
                
        # Add back button
        self.add_item(BackToHomeButton(cog))
        
    async def handle_banking_selection(self, interaction: discord.Interaction):
        select = interaction.data.get("values", [None])[0]
        if not select:
            return
            
        # Handle different banking actions
        if select == "balance":
            await self.cog.execute_command(interaction, "balance")
        elif select == "deposit":
            await self.cog.show_deposit_modal(interaction)
        elif select == "withdraw":
            await self.cog.show_withdraw_modal(interaction)
        elif select == "transfer":
            await self.cog.show_transfer_modal(interaction)
        elif select == "history":
            await self.cog.execute_command(interaction, "transaction_history")


class DepositModal(discord.ui.Modal):
    """Modal for depositing funds"""
    def __init__(self):
        super().__init__(title="Deposit Funds")
        
        self.amount = discord.ui.TextInput(
            label="Amount",
            placeholder="Enter amount (e.g., 50,000)",
            required=True
        )
        self.add_item(self.amount)
        
        self.description = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Purpose of deposit...",
            required=False,
            max_length=100
        )
        self.add_item(self.description)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        cog = interaction.client.get_cog('CommandHubCog')
        if not cog:
            await interaction.followup.send("Command system unavailable", ephemeral=True)
            return
            
        await cog.execute_command(
            interaction,
            "deposit",
            amount=self.amount.value,
            description=self.description.value if self.description.value else None
        )


class WithdrawModal(discord.ui.Modal):
    """Modal for withdrawing funds"""
    def __init__(self):
        super().__init__(title="Withdraw Funds")
        
        self.amount = discord.ui.TextInput(
            label="Amount",
            placeholder="Enter amount (e.g., 50,000)",
            required=True
        )
        self.add_item(self.amount)
        
        self.description = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Purpose of withdrawal...",
            required=False,
            max_length=100
        )
        self.add_item(self.description)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        cog = interaction.client.get_cog('CommandHubCog')
        if not cog:
            await interaction.followup.send("Command system unavailable", ephemeral=True)
            return
            
        await cog.execute_command(
            interaction,
            "withdraw",
            amount=self.amount.value,
            description=self.description.value if self.description.value else None
        )


class TransferModal(discord.ui.Modal):
    """Modal for transferring funds"""
    def __init__(self):
        super().__init__(title="Transfer Funds")
        
        self.recipient = discord.ui.TextInput(
            label="Recipient",
            placeholder="Enter user ID or @mention",
            required=True
        )
        self.add_item(self.recipient)
        
        self.amount = discord.ui.TextInput(
            label="Amount",
            placeholder="Enter amount (e.g., 50,000)",
            required=True
        )
        self.add_item(self.amount)
        
        self.description = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Purpose of transfer...",
            required=False,
            max_length=100
        )
        self.add_item(self.description)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        cog = interaction.client.get_cog('CommandHubCog')
        if not cog:
            await interaction.followup.send("Command system unavailable", ephemeral=True)
            return
            
        await cog.execute_command(
            interaction,
            "transfer",
            user=self.recipient.value,
            amount=self.amount.value,
            description=self.description.value if self.description.value else None
        )


class CommandHubCog(commands.Cog):
    """Enhanced command hub for organizing and accessing all bot commands"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cogs_cache = {}
        self._command_info_cache = {}
        self._autocomplete_cache = {
            'ships': [],
            'users': [],
            'missions': [],
            'stations': []
        }
        self._register_commands()
        logger.info("CommandHub cog initialized")
        
    def _register_commands(self):
        """Register the main hub commands"""
        # Remove existing commands if any
        for command in self.bot.tree.get_commands():
            if command.name in ["command_hub", "admin_hub"]:
                self.bot.tree.remove_command(command.name)
                
        # Register the main command hub command (for members)
        command_hub = app_commands.Command(
            name="command_hub",
            description="Access all available commands in one place",
            callback=self._command_hub_callback,
            guild_ids=[GUILD_ID] if GUILD_ID else None
        )
        
        # Register the admin hub command
        admin_hub = app_commands.Command(
            name="admin_hub",
            description="Access administrative commands",
            callback=self._admin_hub_callback,
            guild_ids=[GUILD_ID] if GUILD_ID else None
        )
        
        # Add commands to the tree
        self.bot.tree.add_command(command_hub)
        self.bot.tree.add_command(admin_hub)
        
        logger.info("Registered main command hub commands")
        
    async def _command_hub_callback(self, interaction: discord.Interaction):
        """Callback for the command_hub command"""
        # Create the main home view
        view = HomeView(self, is_admin=False)
        
        embed = discord.Embed(
            title="🏟️ Command Hub",
            description="Welcome to the organization command hub. Select a category or use quick actions below.",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    async def _admin_hub_callback(self, interaction: discord.Interaction):
        """Callback for the admin_hub command"""
        # Check if user has admin permissions
        if not await self.has_admin_permissions(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to access the admin command hub.",
                ephemeral=True
            )
            return
            
        # Create the admin home view
        view = HomeView(self, is_admin=True)
        
        embed = discord.Embed(
            title="⚙️ Admin Command Hub",
            description="Access administrative commands and functions",
            color=discord.Color.dark_red()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def has_admin_permissions(self, user: discord.Member) -> bool:
        """Check if user has admin permissions"""
        if not hasattr(user, 'roles'):  # Ensure it's a Member, not a User
            return False
            
        # Check for command staff roles
        return any(role.name in COMMAND_STAFF_ROLES for role in user.roles)
    
    def get_command_info(self, command_name: str) -> Dict[str, Any]:
        """Get information about a command"""
        # Try to get from cache first
        if command_name in self._command_info_cache:
            return self._command_info_cache[command_name]
            
        # Default command info
        command_info = {
            'emoji': '🔹',
            'description': 'No description available',
            'parameters': [],
            'parameter_help': {},
            'parameter_types': {}
        }
        
        # Command-specific info overrides
        command_specific_info = {
            'profile': {'emoji': '👤', 'description': 'View your Star Citizen profile'},
            'balance': {'emoji': '💰', 'description': 'Check your aUEC balance'},
            'deposit': {
                'emoji': '💵', 
                'description': 'Deposit aUEC into your account',
                'parameters': ['amount', 'description'],
                'parameter_help': {
                    'amount': 'The amount to deposit (e.g., 50000)',
                    'description': 'Optional description for the transaction'
                },
                'parameter_types': {
                    'amount': 'number',
                    'description': 'string'
                }
            },
            'withdraw': {
                'emoji': '💸', 
                'description': 'Withdraw aUEC from your account',
                'parameters': ['amount', 'description'],
                'parameter_help': {
                    'amount': 'The amount to withdraw (e.g., 50000)',
                    'description': 'Optional description for the transaction'
                },
                'parameter_types': {
                    'amount': 'number',
                    'description': 'string'
                }
            },
            'transfer': {
                'emoji': '📤', 
                'description': 'Transfer aUEC to another member',
                'parameters': ['user', 'amount', 'description'],
                'parameter_help': {
                    'user': 'The member to transfer aUEC to (name, ID, or @mention)',
                    'amount': 'The amount to transfer (e.g., 50000)',
                    'description': 'Optional description for the transaction'
                },
                'parameter_types': {
                    'user': 'user',
                    'amount': 'number',
                    'description': 'string'
                }
            },
            'ship_info': {
                'emoji': '🚀', 
                'description': 'Get detailed information about a ship',
                'parameters': ['name'],
                'parameter_help': {
                    'name': 'The name of the ship to look up'
                },
                'parameter_types': {
                    'name': 'ship'
                }
            },
            'list_ships': {'emoji': '📋', 'description': 'List all available ships'},
            'create_mission': {
                'emoji': '🎯', 
                'description': 'Create a new mission',
                'parameters': ['name', 'mission_type', 'description', 'time', 'timezone', 'date'],
                'parameter_help': {
                    'name': 'Mission name (be descriptive)',
                    'mission_type': 'Type of mission (Combat, Mining, etc.)',
                    'description': 'Detailed mission description, objectives, and requirements',
                    'time': 'Start time (e.g., 15:00)',
                    'timezone': 'Your timezone (UTC offset)',
                    'date': 'Mission date (MM/DD/YYYY)'
                },
                'parameter_types': {
                    'name': 'string',
                    'mission_type': 'mission_type',
                    'description': 'string',
                    'time': 'string',
                    'timezone': 'timezone',
                    'date': 'string'
                }
            },
            'promote': {
                'emoji': '⭐', 
                'description': 'Promote a member',
                'parameters': ['member', 'new_rank'],
                'parameter_help': {
                    'member': 'The member to promote (name, ID, or @mention)',
                    'new_rank': 'The new rank to assign'
                },
                'parameter_types': {
                    'member': 'user',
                    'new_rank': 'rank'
                }
            },
            'banking': {'emoji': '🏦', 'description': 'Access banking features'},
            'play': {
                'emoji': '▶️', 
                'description': 'Play radio',
                'parameters': ['station'],
                'parameter_help': {
                    'station': 'The station to play'
                },
                'parameter_types': {
                    'station': 'station'
                }
            },
            'join_mission': {
                'emoji': '🚀',
                'description': 'Join an existing mission',
                'parameters': ['mission'],
                'parameter_help': {
                    'mission': 'Select the mission to join'
                },
                'parameter_types': {
                    'mission': 'mission'
                }
            },
            'leave_mission': {
                'emoji': '🚪',
                'description': 'Leave a mission you\'ve joined',
                'parameters': ['mission'],
                'parameter_help': {
                    'mission': 'Select the mission to leave'
                },
                'parameter_types': {
                    'mission': 'mission'
                }
            },
            'alert_level': {
                'emoji': '🚨',
                'description': 'Set or view organization alert level',
                'parameters': ['level'],
                'parameter_help': {
                    'level': 'Set the organization alert level'
                },
                'parameter_types': {
                    'level': 'alert_level'
                }
            },
            'select_division': {
                'emoji': '🏢',
                'description': 'Select your division',
                'parameters': ['division'],
                'parameter_help': {
                    'division': 'The division you want to join'
                },
                'parameter_types': {
                    'division': 'division'
                }
            }
        }
        
        # Update with command-specific info if available
        if command_name in command_specific_info:
            command_info.update(command_specific_info[command_name])
            
        # Cache and return
        self._command_info_cache[command_name] = command_info
        return command_info
    
    async def get_command_cog(self, command_name: str) -> Optional[commands.Cog]:
        """Get the cog that handles a specific command"""
        if command_name in self._cogs_cache:
            return self._cogs_cache[command_name]
            
        # Mapping of commands to cogs
        cog_mapping = {
            'profile': 'ProfileCog',
            'ship_info': 'IntegratedShipsCog',
            'list_ships': 'IntegratedShipsCog',
            'commission_ship': 'IntegratedShipsCog',
            'manufacturers': 'IntegratedShipsCog',
            'start': 'OnboardingCog',
            'balance': 'BankingCog',
            'deposit': 'BankingCog',
            'withdraw': 'BankingCog',
            'transfer': 'BankingCog',
            'trade_profit': 'BankingCog',
            'mining_profit': 'BankingCog',
            'career_stats': 'BankingCog',
            'vc_payout': 'BankingCog',
            'banking': 'BankingCog',
            'create_mission': 'MissionCog',
            'join_mission': 'MissionCog',
            'leave_mission': 'MissionCog',
            'update_mission_status': 'MissionCog',
            'edit_mission': 'MissionCog',
            'list_missions': 'MissionCog',
            'promote': 'AdministrationCog',
            'admin': 'AdministrationCog',
            'my_certifications': 'AdministrationCog',
            'play': 'RadioCog',
            'stop': 'RadioCog',
            'stations': 'RadioCog',
            'volume': 'RadioCog',
            'nowplaying': 'RadioCog',
            'addstation': 'RadioCog',
            'removestation': 'RadioCog',
            'sync_commands': 'SyncCommandsCog',
            'sync_status': 'SyncCommandsCog',
            'aar': 'AARCog',
            'admin_loan': 'BankingCog',
            'admin_budget': 'BankingCog',
            'donate': 'BankingCog',
            'add_award': 'ProfileCog',
            'remove_award': 'ProfileCog',
            'bulk_award': 'ProfileCog',
            'division_report': 'ProfileCog',
            'compare_profiles': 'ProfileCog',
            'export_profile': 'ProfileCog',
            'search_members': 'ProfileCog',
            'set_status': 'ProfileCog',
            'view_awards': 'ProfileCog',
            'applyfleet': 'FleetApplicationCog',
            'alert_level': 'AlertCog',
            'alert_history': 'AlertCog',
            'configure_raid_protection': 'RaidProtectionCog',
            'toggle_raid_protection': 'RaidProtectionCog',
            'toggle_join_notifications': 'RaidProtectionCog',
            'onboarding_status': 'OnboardingCog',
            'select_division': 'DivisionSelectionCog',
            'setup_mission_comms': 'SRSCog',
            'mission_comms': 'SRSCog',
            'decommission_ship': 'IntegratedShipsCog',
            'ship_lookup': 'IntegratedShipsCog',
            'transfer_ship': 'IntegratedShipsCog',
            'fleet_stats': 'IntegratedShipsCog',
            'order_system_start': 'OrdersCog',
            'order_system_pause': 'OrdersCog',
            'order_system_stop': 'OrdersCog',
            'create_mission_order': 'OrdersCog',
            'create_division_order': 'OrdersCog',
            'create_major_order': 'OrdersCog',
            'complete_order': 'OrdersCog',
            'view_order': 'OrdersCog',
            'add_objectives': 'OrdersCog',
            'evaluate_orders': 'OrdersCog',
            'refresh_order_messages': 'OrdersCog',
            'change_order_status': 'OrdersCog',
            'cancel_order': 'OrdersCog',
            'set_order_due_date': 'OrdersCog',
            'eval': 'EvalCog',
            'help': 'CommandHubCog'
        }
        
        # Try to get cog by name
        cog_name = cog_mapping.get(command_name)
        cog = None
        
        if cog_name:
            cog = self.bot.get_cog(cog_name)
            
        if not cog:
            # Fallback: search all cogs for the command
            for candidate in self.bot.cogs.values():
                # Check command tree
                for cmd in self.bot.tree.get_commands():
                    if cmd.name == command_name:
                        cog = candidate
                        break
                        
                # Check for app_commands in cog
                if hasattr(candidate, 'get_app_commands'):
                    for cmd in candidate.get_app_commands():
                        if cmd.name == command_name:
                            cog = candidate
                            break
                            
                if cog:
                    break
                    
        if cog:
            self._cogs_cache[command_name] = cog
            
        return cog
    
    async def handle_command_button(self, interaction: discord.Interaction, command_name: str):
        """Handle a command button press"""
        # Special handling for banking command
        if command_name == "banking":
            return await self.show_banking_interface(interaction)
            
        # Get command info
        command_info = self.get_command_info(command_name)
        
        # Create an embed with command info
        embed = discord.Embed(
            title=f"/{command_name}",
            description=command_info.get('description', 'No description available'),
            color=discord.Color.blue()
        )
        
        # Add parameter information if available
        if 'parameters' in command_info and command_info['parameters']:
            param_text = []
            for param in command_info['parameters']:
                help_text = command_info.get('parameter_help', {}).get(param, '')
                param_type = command_info.get('parameter_types', {}).get(param, 'string')
                type_info = ''
                
                if param_type in PARAM_TYPES:
                    if PARAM_TYPES[param_type].get('type') == 'select' and 'options' in PARAM_TYPES[param_type]:
                        type_info = f" (Select from: {', '.join(PARAM_TYPES[param_type]['options'][:3])}...)"
                    elif PARAM_TYPES[param_type].get('autocomplete', False):
                        type_info = " (Autocomplete available)"
                
                param_text.append(f"• **{param}**: {help_text}{type_info}")
                
            embed.add_field(
                name="Required Parameters",
                value="\n".join(param_text),
                inline=False
            )
            
        # Add help section for guidance
        embed.add_field(
            name="How to Fill Parameters",
            value=(
                "• For text fields, type directly into the input box\n"
                "• For selection fields, choose from the dropdown menu\n"
                "• Fields with autocomplete will show suggestions as you type\n"
                "• Required fields are marked with an asterisk (*)"
            ),
            inline=False
        )
            
        # Create confirmation view
        view = CommandConfirmView(self, command_name, command_info)
        
        # Check for direct command method
        cog = await self.get_command_cog(command_name)
        if cog and hasattr(cog, command_name) and not command_info.get('parameters'):
            # If it's a direct method with no parameters, we can execute it directly
            try:
                await interaction.response.defer(ephemeral=True)
                command_method = getattr(cog, command_name)
                await command_method(interaction)
                return
            except Exception as e:
                logger.error(f"Error calling direct method for {command_name}: {e}")
                # Fall back to the normal flow
        
        # Send the command info and confirmation view
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    async def execute_command(self, interaction: discord.Interaction, command_name: str, **kwargs):
        """Execute a command with parameters"""
        # Get the cog that handles this command
        cog = await self.get_command_cog(command_name)
        
        if not cog:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"Required system for command '{command_name}' is not available.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"Required system for command '{command_name}' is not available.",
                        ephemeral=True
                    )
            except Exception as e:
                logger.error(f"Error sending response: {e}")
            return
            
        try:
            # Find the command in the cog
            command = None
            
            # First check direct command attribute or method
            if hasattr(cog, command_name):
                command = getattr(cog, command_name)
                # If it's a method, we need to call it with self
                if callable(command):
                    try:
                        # Directly call the cog method
                        if not interaction.response.is_done():
                            await interaction.response.defer(ephemeral=True)
                        await command(interaction, **kwargs)
                        return
                    except Exception as e:
                        logger.error(f"Error calling method directly: {e}")
            
            # Check app_commands method if available
            if hasattr(cog, 'get_app_commands'):
                for cmd in cog.get_app_commands():
                    if cmd.name == command_name:
                        command = cmd
                        break
            
            # Also check for special command groups
            if not command and hasattr(cog, 'admin'):
                # Check for admin subcommands
                for subcmd in cog.admin.commands:
                    if subcmd.name == command_name:
                        command = subcmd
                        break
            
            # Check other possible groups 
            for group_name in ['ship_group', 'promotion', 'certification']:
                if not command and hasattr(cog, group_name):
                    group = getattr(cog, group_name)
                    for subcmd in group.commands:
                        if subcmd.name == command_name:
                            command = subcmd
                            break
            
            # If still not found, try the command tree
            if not command:
                for cmd in self.bot.tree.get_commands():
                    if cmd.name == command_name:
                        command = cmd
                        break
            
            if not command:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            f"Command '{command_name}' not found.",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            f"Command '{command_name}' not found.",
                            ephemeral=True
                        )
                except Exception as e:
                    logger.error(f"Error sending command not found: {e}")
                return
                
            # Execute the command
            try:
                if hasattr(command, 'callback'):
                    # Make sure we haven't already responded
                    if not interaction.response.is_done():
                        await interaction.response.defer(ephemeral=True)
                    
                    # For app commands, pass the interaction and kwargs
                    # Handle different cases depending on how the command is defined
                    if isinstance(command, app_commands.Command):
                        # Call the command directly
                        await command(interaction, **kwargs)
                    else:
                        # This is likely a method from a cog
                        await command(interaction, **kwargs)
                else:
                    try:
                        if not interaction.response.is_done():
                            await interaction.response.send_message(
                                f"Error: Command '{command_name}' doesn't have a valid callback.",
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                f"Error: Command '{command_name}' doesn't have a valid callback.",
                                ephemeral=True
                            )
                    except Exception as e:
                        logger.error(f"Error sending callback error: {e}")
            except Exception as e:
                logger.error(f"Error executing command {command_name}: {e}")
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(
                            f"Error executing command: {str(e)}",
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            f"Error executing command: {str(e)}",
                            ephemeral=True
                        )
                except Exception as follow_error:
                    logger.error(f"Error sending execution error: {follow_error}")
                
        except Exception as e:
            logger.error(f"Error in execute_command for {command_name}: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"An error occurred while executing the command: {str(e)}",
                        ephemeral=True
                    )
                else:
                    # Only try followup if we haven't already responded and the webhook is still valid
                    try:
                        await interaction.followup.send(
                            f"An error occurred while executing the command: {str(e)}",
                            ephemeral=True
                        )
                    except discord.errors.NotFound:
                        logger.error(f"Webhook expired for interaction when trying to send error")
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")
    
    async def show_banking_interface(self, interaction: discord.Interaction):
        """Show the banking interface"""
        view = BankingView(self)
        
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Select a banking operation from the menu below:",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    async def show_deposit_modal(self, interaction: discord.Interaction):
        """Show the deposit modal"""
        modal = DepositModal()
        await interaction.response.send_modal(modal)
        
    async def show_withdraw_modal(self, interaction: discord.Interaction):
        """Show the withdraw modal"""
        modal = WithdrawModal()
        await interaction.response.send_modal(modal)
        
    async def show_transfer_modal(self, interaction: discord.Interaction):
        """Show the transfer modal"""
        modal = TransferModal()
        await interaction.response.send_modal(modal)
    
    async def load_autocomplete_data(self):
        """Load autocomplete data from other cogs"""
        # Example: Load ship data from IntegratedShipsCog
        try:
            ships_cog = self.bot.get_cog('IntegratedShipsCog')
            if ships_cog and hasattr(ships_cog, 'get_ship_names'):
                self._autocomplete_cache['ships'] = await ships_cog.get_ship_names()
        except Exception as e:
            logger.error(f"Error loading ship autocomplete data: {e}")
            
        # Example: Load station data from RadioCog
        try:
            radio_cog = self.bot.get_cog('RadioCog')
            if radio_cog and hasattr(radio_cog, 'get_stations'):
                self._autocomplete_cache['stations'] = await radio_cog.get_stations()
        except Exception as e:
            logger.error(f"Error loading station autocomplete data: {e}")
            
        # Example: Load mission data from MissionCog
        try:
            mission_cog = self.bot.get_cog('MissionCog')
            if mission_cog and hasattr(mission_cog, 'get_active_missions'):
                self._autocomplete_cache['missions'] = await mission_cog.get_active_missions()
        except Exception as e:
            logger.error(f"Error loading mission autocomplete data: {e}")
    
    # Autocomplete handlers for different parameter types
    async def autocomplete_ship(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete handler for ship names"""
        # If cache is empty, try to load it
        if not self._autocomplete_cache['ships']:
            await self.load_autocomplete_data()
            
        ships = self._autocomplete_cache['ships']
        
        # Filter ships that match the current input
        matches = [ship for ship in ships if current.lower() in ship.lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=ship, value=ship)
            for ship in matches[:25]
        ]
    
    async def autocomplete_user(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete handler for user names"""
        # Get all members in the guild
        members = interaction.guild.members
        
        # Filter members that match the current input
        matches = []
        for member in members:
            if (current.lower() in member.name.lower() or 
                current.lower() in member.display_name.lower() or
                (member.nick and current.lower() in member.nick.lower())):
                matches.append(member)
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=f"{member.display_name} ({member.name})", value=str(member.id))
            for member in matches[:25]
        ]
    
    async def autocomplete_mission(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete handler for mission names"""
        # If cache is empty, try to load it
        if not self._autocomplete_cache['missions']:
            await self.load_autocomplete_data()
            
        missions = self._autocomplete_cache['missions']
        
        # Filter missions that match the current input
        matches = [mission for mission in missions if current.lower() in mission['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=mission['name'], value=str(mission['id']))
            for mission in matches[:25]
        ]
    
    async def autocomplete_station(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete handler for radio stations"""
        # If cache is empty, try to load it
        if not self._autocomplete_cache['stations']:
            await self.load_autocomplete_data()
            
        stations = self._autocomplete_cache['stations']
        
        # Filter stations that match the current input
        matches = [station for station in stations if current.lower() in station['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=station['name'], value=station['id'])
            for station in matches[:25]
        ]
    
    # Helper to get the appropriate autocomplete function for a parameter type
    def get_autocomplete_func(self, param_type: str) -> Callable:
        """Get the autocomplete function for a parameter type"""
        type_map = {
            'ship': self.autocomplete_ship,
            'user': self.autocomplete_user,
            'mission': self.autocomplete_mission,
            'station': self.autocomplete_station
        }
        
        return type_map.get(param_type)
    
    # Help command registered as a slash command  
    @app_commands.command(name="help", description="Get help with commands")
    @app_commands.describe(command="Get help for a specific command")
    async def help_command(self, interaction: discord.Interaction, command: Optional[str] = None):
        """Help command implementation"""
        if command:
            # Show help for a specific command
            command_info = self.get_command_info(command)
            
            embed = discord.Embed(
                title=f"Help: /{command}",
                description=command_info.get('description', 'No description available'),
                color=discord.Color.blue()
            )
            
            # Add parameters if available
            if 'parameters' in command_info and command_info['parameters']:
                param_text = []
                for param in command_info['parameters']:
                    help_text = command_info.get('parameter_help', {}).get(param, '')
                    param_type = command_info.get('parameter_types', {}).get(param, 'string')
                    type_info = ''
                    
                    if param_type in PARAM_TYPES:
                        if PARAM_TYPES[param_type].get('type') == 'select' and 'options' in PARAM_TYPES[param_type]:
                            type_info = f" (Select from: {', '.join(PARAM_TYPES[param_type]['options'][:3])}...)"
                        elif PARAM_TYPES[param_type].get('autocomplete', False):
                            type_info = " (Autocomplete available)"
                    
                    param_text.append(f"• **{param}**: {help_text}{type_info}")
                    
                embed.add_field(
                    name="Parameters",
                    value="\n".join(param_text),
                    inline=False
                )
                
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            # Show general help - direct to command hub
            embed = discord.Embed(
                title="Command Help",
                description=(
                    "Use `/command_hub` to access the interactive command menu with all available commands.\n\n"
                    "For administrative commands, use `/admin_hub` (requires Command Staff role)."
                ),
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Command Categories",
                value="\n".join([f"• {cat}" for cat in COMMAND_CATEGORIES.keys()]),
                inline=True
            )
            
            embed.add_field(
                name="Quick Commands",
                value=(
                    "• `/profile` - View your profile\n"
                    "• `/banking` - Access banking system\n"
                    "• `/ship_info` - Information about ships\n"
                    "• `/help [command]` - Get help for a specific command"
                ),
                inline=True
            )
            
            embed.add_field(
                name="Using Command Parameters",
                value=(
                    "• Commands may have required parameters you need to fill out\n"
                    "• Some parameters support autocomplete - start typing to see suggestions\n"
                    "• Some parameters use selection menus for choosing from options\n"
                    "• You can get detailed help for any command with `/help command_name`"
                ),
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandHubCog(bot))
    
    # Load autocomplete data when the cog is loaded
    command_hub = bot.get_cog('CommandHubCog')
    if command_hub:
        await command_hub.load_autocomplete_data()
        
    logger.info("CommandHub cog loaded successfully with autocomplete and selection features")