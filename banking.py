# cogs/banking.py
from __future__ import annotations

from discord import Interaction as DiscordInteraction
from typing import Dict, List, Optional, Any, Set, Tuple, TYPE_CHECKING, Union, Literal, cast
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass, field
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import aiohttp
import logging
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import io
import json
import random
import uuid
import time

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

if TYPE_CHECKING:
    from .utils.profile_events import ProfileEvent, ProfileEventType
    from .utils.sc_profile_types import CareerPath, ExperienceLevel
    from discord import Interaction as DiscordInteraction

# Constants
CODA_API_TOKEN = os.getenv('CODA_API_TOKEN')
DOC_ID = os.getenv('DOC_ID')
ACCOUNTS_TABLE_ID = os.getenv('ACCOUNTS_TABLE_ID')
TRANSACTIONS_TABLE_ID = os.getenv('TRANSACTIONS_TABLE_ID')
SESSIONS_TABLE_ID = os.getenv('SESSIONS_TABLE_ID')
GOALS_TABLE_ID = os.getenv('GOALS_TABLE_ID')
NOTES_TABLE_ID = os.getenv('NOTES_TABLE_ID')
LOANS_TABLE_ID = os.getenv('LOANS_TABLE_ID', '')
ORG_BUDGET_TABLE_ID = os.getenv('ORG_BUDGET_TABLE_ID', '')
PROJECTS_TABLE_ID = os.getenv('PROJECTS_TABLE_ID', '')
DISCORD_USER_ID_COLUMN = "c-MxtkQv7d7g"  # Discord User ID column ID
USERNAME_COLUMN = None  # This will be detected automatically
BALANCE_COLUMN = None  # This will be detected automatically

# Constants for table column IDs
# Accounts table
DISCORD_USER_ID_COLUMN = "c-MxtkQv7d7g"  # Discord User ID column ID
BALANCE_COLUMN = "c-x9ZuuMiOys"  # Balance column ID
USERNAME_COLUMN = "c-SSQMLIh7h7"  # Username column ID
CREATED_AT_COLUMN = "c-iInPfYYPbN"  # Created At column ID
LAST_UPDATED_COLUMN = "c-Nod2z6q9Zb"  # Last Updated column ID

# Transactions table
TRANS_USER_ID_COLUMN = "c-KtwjQt1i-M"  # Discord User ID column ID
TRANS_TYPE_COLUMN = "c-Yb4fg1XrcT"  # Type column ID
TRANS_AMOUNT_COLUMN = "c-liq7c9R7TT"  # Amount column ID
TRANS_TARGET_USER_COLUMN = "c-woON-syD7p"  # Target Discord User ID column ID
TRANS_DESC_COLUMN = "c-RVmqfG1luc"  # Description column ID
TRANS_STATUS_COLUMN = "c-nQRz2cKN-R"  # Status column ID
TRANS_CATEGORY_COLUMN = "c-pCoccLJCUS"  # Category column ID
TRANS_SESSION_ID_COLUMN = "c-z-IKIJ9m_U"  # Session ID column ID
TRANS_GOAL_ID_COLUMN = "c-jifTZOcXR2"  # Goal ID column ID
TRANS_CREATED_AT_COLUMN = "c-8o-fVv4jCX"  # Created At column ID
TRANS_BALANCE_AFTER_COLUMN = "c-dOsEboOJUQ"  # Account Balance After column ID
TRANS_ID_COLUMN = "c-3Wmjl9OkhM"  # Transaction ID column ID

# Sessions table
SESSION_ID_COLUMN = "c-Py-uFk9wVL"  # Session ID column ID
SESSION_USER_ID_COLUMN = "c-cvtRJe7kUh"  # Discord User ID column ID
SESSION_START_TIME_COLUMN = "c-RSlbYvp7mL"  # Start Time column ID
SESSION_END_TIME_COLUMN = "c-8UeP3-FSg1"  # End Time column ID
SESSION_INITIAL_BAL_COLUMN = "c-WauhhaqNNh"  # Initial Balance column ID
SESSION_FINAL_BAL_COLUMN = "c-8dVp8Mrsjv"  # Final Balance column ID
SESSION_EARNINGS_COLUMN = "c-jO_WqC-PR3"  # Total Earnings column ID
SESSION_NOTES_COLUMN = "c-Vmwkz6gwWf"  # Notes column ID
SESSION_CREATED_AT_COLUMN = "c-gxS2ab-jdp"  # Created Time column ID
SESSION_UPDATED_AT_COLUMN = "c-6aL15Quc0k"  # Last Updated column ID

# Goals table
GOAL_ID_COLUMN = "c-RkOO61RSU0"  # Goal ID column ID
GOAL_USER_ID_COLUMN = "c-aDUAG8pyUF"  # Discord User ID column ID
GOAL_TARGET_AMOUNT_COLUMN = "c-j9b1Di-fJ3"  # Target Amount column ID
GOAL_CURRENT_AMOUNT_COLUMN = "c-QfI_YuQK4-"  # Current Amount column ID
GOAL_DESCRIPTION_COLUMN = "c-qRRxmSaLpH"  # Description column ID
GOAL_STATUS_COLUMN = "c-yerNh3MW0B"  # Status column ID
GOAL_CREATED_AT_COLUMN = "c-p-Cyjh6Nu5"  # Created Time column ID
GOAL_UPDATED_AT_COLUMN = "c-lNKgGXGjtx"  # Last Updated column ID

# Transaction Notes table
NOTE_ID_COLUMN = "c-5USbrJ7Ze9"  # Note ID column ID
NOTE_TRANS_ID_COLUMN = "c-Mbl48rl4kO"  # Transaction ID column ID
NOTE_USER_ID_COLUMN = "c-YqknscaZaR"  # Discord User ID column ID
NOTE_CONTENT_COLUMN = "c-KPGGCjn1zx"  # Note Content column ID
NOTE_CREATED_AT_COLUMN = "c-HL3K-uG43B"  # Created Time column ID
NOTE_UPDATED_AT_COLUMN = "c-wxha_c37cY"  # Last Updated column ID

# Setup Logging
logger = logging.getLogger('banking')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='banking.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class TransactionType(Enum):
    """Enumeration of transaction types for better type safety."""
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    TRADE_PROFIT = "trade_profit"
    MINING_PROFIT = "mining_profit"
    MISSION_REWARD = "mission_reward"
    BOUNTY_REWARD = "bounty_reward"
    REFINERY_PROFIT = "refinery_profit"
    TRANSPORT_PROFIT = "transport_profit"
    VC_PAYOUT = "vc_payout"
    LOAN_DISBURSEMENT = "loan_disbursement"
    LOAN_REPAYMENT = "loan_repayment"
    SECURITY_PAYOUT = "security_payout"
    ORG_DONATION = "org_donation"
    PROJECT_FUNDING = "project_funding"

class TransactionCategory(Enum):
    """Categories for better transaction organization"""
    TRADE = "trade"
    MINING = "mining"
    MISSION = "mission"
    TRANSPORT = "transport"
    BOUNTY = "bounty"
    REFINERY = "refinery"
    PERSONAL = "personal"
    PAYOUT = "payout"
    LOAN = "loan"
    SECURITY = "security"
    DONATION = "donation" 
    PROJECT = "project"
    OTHER = "other"

class TransactionStatus(Enum):
    """Enumeration of transaction statuses."""
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"

class GoalStatus(Enum):
    """Enumeration of goal statuses."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

class LoanStatus(Enum):
    """Enumeration of loan statuses."""
    PENDING = "pending"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    DEFAULTED = "defaulted"
    REJECTED = "rejected"

class MemberRank(Enum):
    """Enumeration of org member ranks."""
    RECRUIT = "recruit"
    MEMBER = "member"
    VETERAN = "veteran"
    OFFICER = "officer"
    ADMIN = "admin"

class IncidentStatus(Enum):
    """Enumeration of cargo incident statuses."""
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"

class ProjectStatus(Enum):
    """Enumeration of project statuses."""
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"

@dataclass
class TransactionData:
    """Data class for structured transaction information."""
    user_id: int
    trans_type: TransactionType
    amount: Decimal
    target_user_id: Optional[int] = None
    description: Optional[str] = None
    status: TransactionStatus = TransactionStatus.COMPLETED
    category: Optional[TransactionCategory] = None
    balance_after: Optional[Decimal] = None
    transaction_id: Optional[str] = None
    session_id: Optional[str] = None
    goal_id: Optional[str] = None
    loan_id: Optional[str] = None
    project_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class SessionData:
    """Data class for gaming session information."""
    session_id: str
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    initial_balance: Optional[Decimal] = None
    final_balance: Optional[Decimal] = None
    total_earnings: Optional[Decimal] = None
    notes: Optional[str] = None

@dataclass
class GoalData:
    """Data class for savings goal information."""
    goal_id: str
    user_id: int
    target_amount: Decimal
    current_amount: Decimal
    description: str
    status: GoalStatus = GoalStatus.ACTIVE

@dataclass
class LoanData:
    """Data class for cargo investment loan information."""
    loan_id: str
    user_id: int
    amount: Decimal
    purpose: str
    status: LoanStatus
    disbursement_date: Optional[datetime] = None
    repayment_due_date: Optional[datetime] = None
    repaid_amount: Decimal = Decimal('0')
    interest_rate: Decimal = Decimal('0.10')  # 10% default
    security_team: List[int] = field(default_factory=list)
    security_payout_percentage: Decimal = Decimal('0.10')  # 10% default
    tax_waived: bool = False
    security_fee_waived: bool = False  # New field for security fee waiver
    approved_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class CargoIncidentData:
    """Data class for cargo incident reports."""
    incident_id: str
    loan_id: str
    user_id: int
    report_date: datetime
    description: str
    amount_lost: Decimal
    location: str
    status: IncidentStatus = IncidentStatus.PENDING_REVIEW
    reviewed_by: Optional[int] = None
    review_date: Optional[datetime] = None
    review_notes: Optional[str] = None

@dataclass
class OrgBudgetData:
    """Data class for organization budget tracking."""
    total_funds: Decimal
    allocated_funds: Decimal
    available_funds: Decimal
    last_updated: datetime

@dataclass
class ProjectData:
    """Data class for organization projects."""
    project_id: str
    name: str
    description: str
    budget: Decimal
    funds_used: Decimal
    status: ProjectStatus
    start_date: datetime
    end_date: Optional[datetime] = None
    manager_id: Optional[int] = None
    contributors: List[int] = field(default_factory=list)
    notes: Optional[str] = None

class BankingCache:
    """Cache manager for banking operations."""
    def __init__(self, ttl: int = 300):  # 5 minutes default TTL
        self.balance_cache = {}
        self.lock = asyncio.Lock()
        self.ttl = ttl
        self._cleanup_task = None
        self.last_rate_limit = 0

    def check_rate_limit(self) -> bool:
        """Check if we're currently rate limited by Coda API."""
        current_time = time.time()
        
        # Check if we've made a rate limit request in the last 60 seconds
        if current_time - self.last_rate_limit < 60:
            return True
        
        return False

    async def get_balance(self, user_id: int) -> Optional[Decimal]:
        """Get user's balance from cache if available."""
        async with self.lock:
            cached_data = self.balance_cache.get(user_id)
            if cached_data:
                timestamp, balance = cached_data
                current_time = datetime.now().timestamp()
                if current_time - timestamp < self.ttl:
                    return balance
        return None

    async def set_balance(self, user_id: int, balance: Decimal):
        """Cache a user's balance."""
        async with self.lock:
            self.balance_cache[user_id] = (datetime.now().timestamp(), balance)

    async def invalidate(self, user_id: int):
        """Invalidate cached balance for a user."""
        async with self.lock:
            self.balance_cache.pop(user_id, None)

    async def start_cleanup(self):
        """Start the cache cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """Periodically clean up expired cache entries."""
        while True:
            await asyncio.sleep(self.ttl)
            current_time = datetime.now().timestamp()
            async with self.lock:
                for user_id, (timestamp, _) in list(self.balance_cache.items()):
                    if current_time - timestamp >= self.ttl:
                        del self.balance_cache[user_id]

class BankingHomeView(discord.ui.View):
    """Main UI view for banking system navigation."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
    
    @discord.ui.button(label="💰 Account", style=discord.ButtonStyle.primary)
    async def account_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show account options."""
        view = AccountOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Account Options",
            description="Select an option to manage your account:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📊 Transactions", style=discord.ButtonStyle.primary)
    async def transactions_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show transaction options."""
        view = TransactionOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Transaction Options",
            description="Select an option to view or manage your transactions:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🎯 Goals", style=discord.ButtonStyle.primary)
    async def goals_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show goals options."""
        view = GoalsOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Savings Goals",
            description="Set and track progress towards your financial goals:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🚢 Cargo Loans", style=discord.ButtonStyle.primary)
    async def loans_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show cargo investment loan options."""
        view = LoanOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Cargo Investment Loans",
            description="Apply for and manage cargo investment loans:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚡ Quick Actions", style=discord.ButtonStyle.success)
    async def quick_actions_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show quick action options."""
        view = QuickActionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Quick Actions",
            description="Common banking actions:",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class AccountOptionsView(discord.ui.View):
    """View for account-related options."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="View Balance", style=discord.ButtonStyle.primary)
    async def view_balance_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """View account balance."""
        await interaction.response.defer(thinking=True)
        
        try:
            balance = await self.cog.get_balance(interaction.user.id)
            embed = self.cog.create_balance_embed(interaction.user, balance)
            
            # Add back button to return to main menu
            view = discord.ui.View(timeout=180)
            view.add_item(BackToMainMenuButton(self.cog))
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            await interaction.followup.send(
                "An error occurred while checking your balance.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Deposit Funds", style=discord.ButtonStyle.primary)
    async def deposit_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open deposit modal."""
        modal = DepositModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Withdraw Funds", style=discord.ButtonStyle.primary)
    async def withdraw_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open withdraw modal."""
        modal = WithdrawModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Transfer Funds", style=discord.ButtonStyle.primary)
    async def transfer_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open transfer modal."""
        modal = TransferStartModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Back to Main Menu", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to main menu."""
        view = BankingHomeView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Welcome to the organization banking system. Select an option below:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class TransactionOptionsView(discord.ui.View):
    """View for transaction-related options."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="Transaction History", style=discord.ButtonStyle.primary)
    async def history_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show transaction history."""
        await interaction.response.defer(thinking=True)
        
        # Get initial transactions (last week by default)
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(weeks=1)

        transactions = await self.cog.get_transactions(
            interaction.user.id,
            start_date=start_date
        )

        if not transactions:
            embed = discord.Embed(
                title="Transaction History",
                description="No transactions found for the past week.",
                color=discord.Color.blue()
            )
            view = discord.ui.View()
            view.add_item(BackToMainMenuButton(self.cog))
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            return

        # Create transaction history view
        view = self.cog.TransactionHistoryView(
            self.cog,
            interaction.user.id,
            timeframe="week",
            view_type="detailed"
        )
        
        embed = await view.create_transaction_list_embed(
            transactions,
            detailed=True
        )

        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
    
    @discord.ui.button(label="Category Summary", style=discord.ButtonStyle.primary)
    async def category_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show category selector for summary."""
        view = CategorySummaryView(self.cog)
        embed = discord.Embed(
            title="Category Summary",
            description="Select a timeframe and optional category:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Export Transactions", style=discord.ButtonStyle.primary)
    async def export_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show export options."""
        view = ExportOptionsView(self.cog)
        embed = discord.Embed(
            title="Export Transactions",
            description="Select format and timeframe for export:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Add Note to Transaction", style=discord.ButtonStyle.primary)
    async def note_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open add note modal."""
        modal = AddNoteModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Back to Main Menu", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to main menu."""
        view = BankingHomeView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Welcome to the organization banking system. Select an option below:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class GoalsOptionsView(discord.ui.View):
    """View for savings goals options."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="View Goals", style=discord.ButtonStyle.primary)
    async def view_goals_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """View savings goals."""
        await interaction.response.defer(thinking=True)
        
        try:
            goals = await self.cog.get_user_goals(interaction.user.id)
            
            if not goals:
                embed = discord.Embed(
                    title="Savings Goals",
                    description="You don't have any savings goals set up yet.",
                    color=discord.Color.blue()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            # Create goal navigation view
            view = GoalNavigationView(self.cog, goals)
            embed = view.create_goal_embed(goals[0], interaction.user)
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error viewing goals: {e}")
            await interaction.followup.send(
                "An error occurred while retrieving your savings goals.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Create New Goal", style=discord.ButtonStyle.primary)
    async def create_goal_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open create goal modal."""
        modal = CreateGoalModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Contribute to Goal", style=discord.ButtonStyle.primary)
    async def contribute_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show goal selection for contribution."""
        await interaction.response.defer(thinking=True)
        
        try:
            goals = await self.cog.get_user_goals(interaction.user.id, status=GoalStatus.ACTIVE)
            
            if not goals:
                embed = discord.Embed(
                    title="Contribute to Goal",
                    description="You don't have any active savings goals.",
                    color=discord.Color.blue()
                )
                view = discord.ui.View()
                view.add_item(BackToGoalsButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            view = GoalSelectionView(self.cog, goals, "contribute")
            embed = discord.Embed(
                title="Contribute to Goal",
                description="Select a goal to contribute to:",
                color=discord.Color.blue()
            )
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error loading goals for contribution: {e}")
            await interaction.followup.send(
                "An error occurred while loading your goals.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Modify Goal", style=discord.ButtonStyle.primary)
    async def modify_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show goal selection for modification."""
        await interaction.response.defer(thinking=True)
        
        try:
            goals = await self.cog.get_user_goals(interaction.user.id)
            
            if not goals:
                embed = discord.Embed(
                    title="Modify Goal",
                    description="You don't have any savings goals.",
                    color=discord.Color.blue()
                )
                view = discord.ui.View()
                view.add_item(BackToGoalsButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            view = GoalSelectionView(self.cog, goals, "modify")
            embed = discord.Embed(
                title="Modify Goal",
                description="Select a goal to modify:",
                color=discord.Color.blue()
            )
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error loading goals for modification: {e}")
            await interaction.followup.send(
                "An error occurred while loading your goals.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Back to Main Menu", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to main menu."""
        view = BankingHomeView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Welcome to the organization banking system. Select an option below:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class LoanOptionsView(discord.ui.View):
    """View for cargo investment loan options."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="View My Loans", style=discord.ButtonStyle.primary)
    async def view_loans_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """View user loans."""
        await interaction.response.defer(thinking=True)
        
        try:
            loans = await self.cog.get_user_loans(interaction.user.id)
            
            if not loans:
                embed = discord.Embed(
                    title="Cargo Investment Loans",
                    description="You don't have any cargo investment loans.",
                    color=discord.Color.blue()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            # Create loan navigation view
            view = LoanNavigationView(self.cog, loans)
            embed = view.create_loan_embed(loans[0])
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error viewing loans: {e}")
            await interaction.followup.send(
                "An error occurred while retrieving your loans.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Apply for Loan", style=discord.ButtonStyle.primary)
    async def apply_loan_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open loan application modal."""
        modal = LoanApplicationModal(self.cog)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Repay Loan", style=discord.ButtonStyle.primary)
    async def repay_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show loan selection for repayment."""
        await interaction.response.defer(thinking=True)
        
        try:
            loans = await self.cog.get_user_loans(
                interaction.user.id,
                status=[LoanStatus.ACTIVE, LoanStatus.APPROVED]
            )
            
            if not loans:
                embed = discord.Embed(
                    title="Repay Loan",
                    description="You don't have any active loans that need repayment.",
                    color=discord.Color.blue()
                )
                view = discord.ui.View()
                view.add_item(BackToLoansButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            view = LoanSelectionView(self.cog, loans, "repay")
            embed = discord.Embed(
                title="Repay Loan",
                description="Select a loan to repay:",
                color=discord.Color.blue()
            )
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error loading loans for repayment: {e}")
            await interaction.followup.send(
                "An error occurred while loading your loans.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Report Incident", style=discord.ButtonStyle.danger)
    async def incident_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show loan selection for incident report."""
        await interaction.response.defer(thinking=True)
        
        try:
            loans = await self.cog.get_user_loans(
                interaction.user.id,
                status=[LoanStatus.ACTIVE, LoanStatus.APPROVED]
            )
            
            if not loans:
                embed = discord.Embed(
                    title="Report Cargo Incident",
                    description="You don't have any active loans to report incidents for.",
                    color=discord.Color.blue()
                )
                view = discord.ui.View()
                view.add_item(BackToLoansButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            view = LoanSelectionView(self.cog, loans, "incident")
            embed = discord.Embed(
                title="Report Cargo Incident",
                description="Select a loan to report an incident for:",
                color=discord.Color.red()
            )
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error loading loans for incident report: {e}")
            await interaction.followup.send(
                "An error occurred while loading your loans.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Back to Main Menu", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to main menu."""
        view = BankingHomeView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Welcome to the organization banking system. Select an option below:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class QuickActionsView(discord.ui.View):
    """View for quick banking actions."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
    
    @discord.ui.button(label="Check Balance", style=discord.ButtonStyle.success)
    async def check_balance_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Quick balance check."""
        await interaction.response.defer(thinking=True)
        
        try:
            balance = await self.cog.get_balance(interaction.user.id)
            
            embed = discord.Embed(
                title="Your Balance",
                description=f"Current balance: **{balance:,.2f} aUEC**",
                color=discord.Color.green()
            )
            
            view = discord.ui.View()
            view.add_item(BackToMainMenuButton(self.cog))
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error in quick balance check: {e}")
            await interaction.followup.send(
                "An error occurred while checking your balance.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Quick Deposit", style=discord.ButtonStyle.success)
    async def quick_deposit_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open quick deposit modal."""
        modal = DepositModal(self.cog, quick=True)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Start Session", style=discord.ButtonStyle.success)
    async def start_session_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Start gaming session."""
        await interaction.response.defer(thinking=True)
        
        try:
            # Check if there's already an active session
            existing_session = await self.cog.get_active_session(interaction.user.id)
            if existing_session:
                embed = discord.Embed(
                    title="Session Already Active",
                    description="You already have an active gaming session.",
                    color=discord.Color.orange()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            session = await self.cog.start_gaming_session(interaction.user.id)
            
            if session:
                embed = discord.Embed(
                    title="Gaming Session Started",
                    description="Your gaming session has been started successfully.",
                    color=discord.Color.green(),
                    timestamp=session.start_time
                )
                
                embed.add_field(
                    name="Initial Balance",
                    value=f"{session.initial_balance:,.2f} aUEC",
                    inline=False
                )
                
                embed.add_field(
                    name="Session ID",
                    value=session.session_id,
                    inline=False
                )
                
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                view.add_item(EndSessionButton(self.cog))
                
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                embed = discord.Embed(
                    title="Session Start Failed",
                    description="Failed to start gaming session.",
                    color=discord.Color.red()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            await interaction.followup.send(
                "An error occurred while starting the gaming session.",
                ephemeral=True
            )
    
    @discord.ui.button(label="End Session", style=discord.ButtonStyle.success)
    async def end_session_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """End gaming session."""
        await interaction.response.defer(thinking=True)
        
        try:
            session = await self.cog.get_active_session(interaction.user.id)
            if not session:
                embed = discord.Embed(
                    title="No Active Session",
                    description="You don't have an active gaming session to end.",
                    color=discord.Color.orange()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return
                
            ended_session = await self.cog.end_gaming_session(interaction.user.id)
            
            if ended_session:
                embed = self.cog.create_session_summary_embed(ended_session, interaction.user)
                
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                embed = discord.Embed(
                    title="Session End Failed",
                    description="Failed to end gaming session.",
                    color=discord.Color.red()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                
        except Exception as e:
            logger.error(f"Error ending session: {e}")
            await interaction.followup.send(
                "An error occurred while ending the gaming session.",
                ephemeral=True
            )
    
    @discord.ui.button(label="Back to Main Menu", style=discord.ButtonStyle.secondary, row=4)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to main menu."""
        view = BankingHomeView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Welcome to the organization banking system. Select an option below:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class BackToMainMenuButton(discord.ui.Button):
    """Button to return to main menu."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(style=discord.ButtonStyle.secondary, label="Back to Main Menu")
        self.cog = cog
        
    async def callback(self, interaction: DiscordInteraction):
        view = BankingHomeView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking System",
            description="Welcome to the organization banking system. Select an option below:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class BackToGoalsButton(discord.ui.Button):
    """Button to return to goals menu."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(style=discord.ButtonStyle.secondary, label="Back to Goals Menu")
        self.cog = cog
        
    async def callback(self, interaction: DiscordInteraction):
        view = GoalsOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Savings Goals",
            description="Set and track progress towards your financial goals:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class BackToLoansButton(discord.ui.Button):
    """Button to return to loans menu."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(style=discord.ButtonStyle.secondary, label="Back to Loans Menu")
        self.cog = cog
        
    async def callback(self, interaction: DiscordInteraction):
        view = LoanOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Cargo Investment Loans",
            description="Apply for and manage cargo investment loans:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class EndSessionButton(discord.ui.Button):
    """Button to end gaming session."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(style=discord.ButtonStyle.danger, label="End Session")
        self.cog = cog
        
    async def callback(self, interaction: DiscordInteraction):
        await interaction.response.defer(thinking=True)
        
        try:
            ended_session = await self.cog.end_gaming_session(interaction.user.id)
            
            if ended_session:
                embed = self.cog.create_session_summary_embed(ended_session, interaction.user)
                
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                embed = discord.Embed(
                    title="Session End Failed",
                    description="Failed to end gaming session.",
                    color=discord.Color.red()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                
        except Exception as e:
            logger.error(f"Error ending session: {e}")
            await interaction.followup.send(
                "An error occurred while ending the gaming session.",
                ephemeral=True
            )

class GoalNavigationView(discord.ui.View):
    """View for navigating through savings goals."""
    def __init__(self, cog: 'BankingCog', goals: List[GoalData]):
        super().__init__(timeout=300)
        self.cog = cog
        self.goals = goals
        self.current_index = 0
        self.update_button_states()
        
    def update_button_states(self):
        """Update button states based on current index."""
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.goals) - 1
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def prev_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show previous goal."""
        self.current_index = max(0, self.current_index - 1)
        self.update_button_states()
        
        embed = self.create_goal_embed(self.goals[self.current_index], interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show next goal."""
        self.current_index = min(len(self.goals) - 1, self.current_index + 1)
        self.update_button_states()
        
        embed = self.create_goal_embed(self.goals[self.current_index], interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Contribute", style=discord.ButtonStyle.green)
    async def contribute_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Contribute to current goal."""
        current_goal = self.goals[self.current_index]
        
        # Only allow contributions to active goals
        if current_goal.status != GoalStatus.ACTIVE:
            await interaction.response.send_message(
                "You can only contribute to active goals.",
                ephemeral=True
            )
            return
            
        modal = ContributeGoalModal(self.cog, current_goal)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Back to Goals Menu", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to goals menu."""
        view = GoalsOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Savings Goals",
            description="Set and track progress towards your financial goals:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
        
    def create_goal_embed(self, goal: GoalData, user: discord.User) -> discord.Embed:
        """Create an embed for a goal."""
        progress = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount else 0
        progress_bar = self.cog.create_progress_bar(progress)
        
        status_colors = {
            GoalStatus.ACTIVE: discord.Color.blue(),
            GoalStatus.COMPLETED: discord.Color.green(),
            GoalStatus.ABANDONED: discord.Color.red()
        }
        
        embed = discord.Embed(
            title="🎯 Savings Goal",
            description=goal.description,
            color=status_colors.get(goal.status, discord.Color.blue()),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Target Amount",
            value=f"{goal.target_amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Current Amount",
            value=f"{goal.current_amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value=goal.status.value.title(),
            inline=True
        )
        
        embed.add_field(
            name="Progress",
            value=f"{progress:.1f}%\n{progress_bar}",
            inline=False
        )
        
        embed.set_footer(text=f"Goal ID: {goal.goal_id}")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        return embed

class LoanNavigationView(discord.ui.View):
    """View for navigating through loans."""
    def __init__(self, cog: 'BankingCog', loans: List[LoanData]):
        super().__init__(timeout=300)
        self.cog = cog
        self.loans = loans
        self.current_index = 0
        self.update_button_states()
        
    def update_button_states(self):
        """Update button states based on current index."""
        self.prev_button.disabled = self.current_index == 0
        self.next_button.disabled = self.current_index >= len(self.loans) - 1
        
        # Only enable repay button for active loans
        current_loan = self.loans[self.current_index]
        self.repay_button.disabled = current_loan.status not in [LoanStatus.ACTIVE, LoanStatus.APPROVED]
        
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def prev_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show previous loan."""
        self.current_index = max(0, self.current_index - 1)
        self.update_button_states()
        
        embed = self.create_loan_embed(self.loans[self.current_index])
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Show next loan."""
        self.current_index = min(len(self.loans) - 1, self.current_index + 1)
        self.update_button_states()
        
        embed = self.create_loan_embed(self.loans[self.current_index])
        await interaction.response.edit_message(embed=embed, view=self)
        
    @discord.ui.button(label="Repay", style=discord.ButtonStyle.green)
    async def repay_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Repay current loan."""
        current_loan = self.loans[self.current_index]
        
        # Only allow repayment for active loans
        if current_loan.status not in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
            await interaction.response.send_message(
                "You can only repay active loans.",
                ephemeral=True
            )
            return
            
        modal = RepayLoanModal(self.cog, current_loan)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Back to Loans Menu", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to loans menu."""
        view = LoanOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Cargo Investment Loans",
            description="Apply for and manage cargo investment loans:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
        
    def create_loan_embed(self, loan: LoanData) -> discord.Embed:
        """Create a standardized loan embed."""
        status_colors = {
            LoanStatus.PENDING: discord.Color.light_grey(),
            LoanStatus.APPROVED: discord.Color.green(),
            LoanStatus.ACTIVE: discord.Color.blue(),
            LoanStatus.COMPLETED: discord.Color.green(),
            LoanStatus.DEFAULTED: discord.Color.red(),
            LoanStatus.REJECTED: discord.Color.red()
        }
        
        status_emojis = {
            LoanStatus.PENDING: "⏳",
            LoanStatus.APPROVED: "✅",
            LoanStatus.ACTIVE: "💼",
            LoanStatus.COMPLETED: "🎉",
            LoanStatus.DEFAULTED: "❌",
            LoanStatus.REJECTED: "🚫"
        }
        
        try:
            color = status_colors.get(loan.status, discord.Color.blue())
        except:
            color = discord.Color.blue()
            
        emoji = status_emojis.get(loan.status, "📋")
        
        embed = discord.Embed(
            title=f"🚢 Cargo Investment Loan",
            description=loan.purpose,
            color=color,
            timestamp=loan.created_at
        )
        
        embed.add_field(
            name="Amount",
            value=f"{loan.amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value=f"{emoji} {loan.status.value.title()}",
            inline=True
        )
        
        if loan.repaid_amount > 0:
            # Calculate total due based on waivers
            total_due = loan.amount
            if not loan.tax_waived:
                total_due += loan.amount * loan.interest_rate
            if not loan.security_fee_waived:
                total_due += loan.amount * loan.security_payout_percentage
                
            repayment_progress = (loan.repaid_amount / total_due) * 100
            progress_bar = self.create_progress_bar(repayment_progress)
            
            embed.add_field(
                name="Repaid",
                value=f"{loan.repaid_amount:,.2f} aUEC ({repayment_progress:.1f}%)",
                inline=True
            )
            
            embed.add_field(
                name="Repayment Progress",
                value=progress_bar,
                inline=False
            )
        
        if loan.disbursement_date:
            embed.add_field(
                name="Disbursement Date",
                value=loan.disbursement_date.strftime("%Y-%m-%d %H:%M"),
                inline=True
            )
            
        if loan.repayment_due_date:
            embed.add_field(
                name="Due Date",
                value=loan.repayment_due_date.strftime("%Y-%m-%d %H:%M"),
                inline=True
            )
        
        # Fee information section
        if loan.status in [LoanStatus.APPROVED, LoanStatus.ACTIVE]:
            fee_fields = []
            
            # Interest information
            if loan.tax_waived:
                fee_fields.append({
                    "name": "Interest",
                    "value": "Waived",
                    "inline": True
                })
            else:
                interest_amount = loan.amount * loan.interest_rate
                fee_fields.append({
                    "name": "Interest (10%)",
                    "value": f"{interest_amount:,.2f} aUEC",
                    "inline": True
                })
            
            # Security fee information
            if loan.security_fee_waived:
                fee_fields.append({
                    "name": "Security Fee",
                    "value": "Waived",
                    "inline": True
                })
            else:
                security_fee = loan.amount * loan.security_payout_percentage
                fee_fields.append({
                    "name": "Security Fee (10%)",
                    "value": f"{security_fee:,.2f} aUEC",
                    "inline": True
                })
            
            # Total repayment amount
            total_repayment = loan.amount
            if not loan.tax_waived:
                total_repayment += loan.amount * loan.interest_rate
            if not loan.security_fee_waived:
                total_repayment += loan.amount * loan.security_payout_percentage
                
            fee_fields.append({
                "name": "Total Repayment",
                "value": f"{total_repayment:,.2f} aUEC",
                "inline": False
            })
            
            for field in fee_fields:
                embed.add_field(**field)
                
        if loan.security_team and len(loan.security_team) > 0:
            security_team_str = ", ".join([f"<@{member_id}>" for member_id in loan.security_team])
            security_payout = loan.amount * loan.security_payout_percentage
            
            # Only show the security payout if the fee isn't waived
            if not loan.security_fee_waived:
                embed.add_field(
                    name="Security Team",
                    value=f"{security_team_str}\nPayout: {security_payout:,.2f} aUEC ({loan.security_payout_percentage*100:.0f}%)",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Security Team",
                    value=f"{security_team_str}\nPayout: Waived",
                    inline=False
                )
                
        if loan.notes:
            embed.add_field(
                name="Notes",
                value=loan.notes,
                inline=False
            )
            
        embed.set_footer(text=f"Loan ID: {loan.loan_id}")
        
        return embed

class GoalSelectionView(discord.ui.View):
    """View for selecting a goal from multiple options."""
    def __init__(self, cog: 'BankingCog', goals: List[GoalData], action_type: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.goals = goals
        self.action_type = action_type  # "contribute" or "modify"
        
        # Add select menu for goals
        options = []
        for goal in goals:
            progress = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount else 0
            option_description = f"{goal.description[:50]}... - {progress:.1f}%" if len(goal.description) > 50 else f"{goal.description} - {progress:.1f}%"
            
            options.append(
                discord.SelectOption(
                    label=f"Goal: {goal.target_amount:,.0f} aUEC",
                    description=option_description,
                    value=goal.goal_id
                )
            )
            
        self.add_item(GoalSelect(options, self.on_goal_selected))
        
    async def on_goal_selected(self, interaction: DiscordInteraction, goal_id: str):
        """Handle goal selection."""
        selected_goal = next((g for g in self.goals if g.goal_id == goal_id), None)
        
        if not selected_goal:
            await interaction.response.send_message("Goal not found.", ephemeral=True)
            return
            
        if self.action_type == "contribute":
            modal = ContributeGoalModal(self.cog, selected_goal)
            await interaction.response.send_modal(modal)
        elif self.action_type == "modify":
            modal = ModifyGoalModal(self.cog, selected_goal)
            await interaction.response.send_modal(modal)
            
    @discord.ui.button(label="Back to Goals Menu", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to goals menu."""
        view = GoalsOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Savings Goals",
            description="Set and track progress towards your financial goals:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class GoalSelect(discord.ui.Select):
    """Custom select menu for goals with callback."""
    def __init__(self, options: List[discord.SelectOption], callback_func):
        super().__init__(
            placeholder="Select a goal...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.callback_func = callback_func
        
    async def callback(self, interaction: DiscordInteraction):
        """Trigger the provided callback function."""
        await self.callback_func(interaction, self.values[0])

class LoanSelectionView(discord.ui.View):
    """View for selecting a loan from multiple options."""
    def __init__(self, cog: 'BankingCog', loans: List[LoanData], action_type: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.loans = loans
        self.action_type = action_type  # "repay" or "incident"
        
        # Add select menu for loans
        options = []
        for loan in loans:
            if loan.status in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
                option_description = f"{loan.purpose[:50]}..." if len(loan.purpose) > 50 else loan.purpose
                
                options.append(
                    discord.SelectOption(
                        label=f"Loan: {loan.amount:,.0f} aUEC",
                        description=option_description,
                        value=loan.loan_id
                    )
                )
                
        self.add_item(LoanSelect(options, self.on_loan_selected))
        
    async def on_loan_selected(self, interaction: DiscordInteraction, loan_id: str):
        """Handle loan selection."""
        selected_loan = next((l for l in self.loans if l.loan_id == loan_id), None)
        
        if not selected_loan:
            await interaction.response.send_message("Loan not found.", ephemeral=True)
            return
            
        if self.action_type == "repay":
            modal = RepayLoanModal(self.cog, selected_loan)
            await interaction.response.send_modal(modal)
        elif self.action_type == "incident":
            modal = IncidentReportModal(self.cog, selected_loan)
            await interaction.response.send_modal(modal)
            
    @discord.ui.button(label="Back to Loans Menu", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to loans menu."""
        view = LoanOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Cargo Investment Loans",
            description="Apply for and manage cargo investment loans:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class LoanSelect(discord.ui.Select):
    """Custom select menu for loans with callback."""
    def __init__(self, options: List[discord.SelectOption], callback_func):
        super().__init__(
            placeholder="Select a loan...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.callback_func = callback_func
        
    async def callback(self, interaction: DiscordInteraction):
        """Trigger the provided callback function."""
        await self.callback_func(interaction, self.values[0])

class CategorySummaryView(discord.ui.View):
    """View for category summary options."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
        self.timeframe = "month"
        self.category = None
        
        # Add timeframe and category selects
        self.add_item(self.create_timeframe_select())
        self.add_item(self.create_category_select())
        
    def create_timeframe_select(self):
        """Create timeframe select menu."""
        options = [
            discord.SelectOption(label="Day", value="day", description="Transactions from the past 24 hours"),
            discord.SelectOption(label="Week", value="week", description="Transactions from the past 7 days"),
            discord.SelectOption(label="Month", value="month", description="Transactions from the past 30 days", default=True),
            discord.SelectOption(label="Year", value="year", description="Transactions from the past 365 days")
        ]
        
        select = discord.ui.Select(
            placeholder="Select timeframe...",
            options=options
        )
        
        async def callback(interaction: DiscordInteraction):
            self.timeframe = select.values[0]
            await interaction.response.defer()
            
        select.callback = callback
        return select
        
    def create_category_select(self):
        """Create category select menu."""
        options = [
            discord.SelectOption(label="All Categories", value="all", description="View all transaction categories", default=True)
        ]
        
        for category in TransactionCategory:
            options.append(
                discord.SelectOption(
                    label=category.value.title(),
                    value=category.value,
                    description=f"View only {category.value} transactions"
                )
            )
            
        select = discord.ui.Select(
            placeholder="Select category...",
            options=options
        )
        
        async def callback(interaction: DiscordInteraction):
            if select.values[0] == "all":
                self.category = None
            else:
                self.category = TransactionCategory(select.values[0])
            await interaction.response.defer()
            
        select.callback = callback
        return select
        
    @discord.ui.button(label="Generate Summary", style=discord.ButtonStyle.primary)
    async def generate_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Generate category summary."""
        await interaction.response.defer(thinking=True)
        
        try:
            # Get date range
            now = datetime.now(timezone.utc)
            if self.timeframe == "day":
                start_date = now - timedelta(days=1)
            elif self.timeframe == "week":
                start_date = now - timedelta(weeks=1)
            elif self.timeframe == "month":
                start_date = now - timedelta(days=30)
            else:  # year
                start_date = now - timedelta(days=365)

            transactions = await self.cog.get_transactions(
                interaction.user.id,
                start_date=start_date
            )

            if not transactions:
                embed = discord.Embed(
                    title="No Transactions Found",
                    description=f"No transactions found for the selected timeframe ({self.timeframe}).",
                    color=discord.Color.orange()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return

            # Filter by category if specified
            if self.category:
                filtered_transactions = [t for t in transactions if t.category == self.category]
                if not filtered_transactions:
                    embed = discord.Embed(
                        title="No Transactions Found",
                        description=f"No transactions found for category {self.category.value} in the selected timeframe ({self.timeframe}).",
                        color=discord.Color.orange()
                    )
                    view = discord.ui.View()
                    view.add_item(BackToMainMenuButton(self.cog))
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                    return
                transactions = filtered_transactions

            embed = discord.Embed(
                title=f"Category Summary ({self.timeframe})",
                color=discord.Color.blue(),
                timestamp=now
            )

            if self.category:
                # Detailed view of single category
                total_amount = sum(t.amount for t in transactions)
                avg_amount = total_amount / len(transactions) if transactions else Decimal('0')
                largest_transaction = max(transactions, key=lambda t: abs(t.amount))
                
                emoji = self.cog.get_category_emoji(self.category)
                embed.add_field(
                    name=f"{emoji} {self.category.value.title()} Summary",
                    value=(
                        f"Total Amount: {total_amount:,.2f} aUEC\n"
                        f"Transaction Count: {len(transactions)}\n"
                        f"Average Amount: {avg_amount:,.2f} aUEC\n"
                        f"Largest Transaction: {largest_transaction.amount:,.2f} aUEC"
                    ),
                    inline=False
                )

                # Show recent transactions
                recent_transactions = sorted(
                    transactions,
                    key=lambda t: datetime.fromisoformat(t.metadata['created_at'].replace('Z', '+00:00')),
                    reverse=True
                )[:5]

                for transaction in recent_transactions:
                    trans_time = datetime.fromisoformat(
                        transaction.metadata['created_at'].replace('Z', '+00:00')
                    )
                    embed.add_field(
                        name=f"{trans_time.strftime('%Y-%m-%d %H:%M')}",
                        value=(
                            f"Amount: {transaction.amount:,.2f} aUEC\n"
                            f"Description: {transaction.description or 'N/A'}"
                        ),
                        inline=False
                    )

            else:
                # Overall category summary
                category_data = defaultdict(list)
                for trans in transactions:
                    if trans.category:
                        category_data[trans.category].append(trans)

                for cat, cat_transactions in sorted(
                    category_data.items(),
                    key=lambda x: sum(abs(t.amount) for t in x[1]),
                    reverse=True
                ):
                    emoji = self.cog.get_category_emoji(cat)
                    total = sum(t.amount for t in cat_transactions)
                    avg = total / len(cat_transactions)
                    
                    embed.add_field(
                        name=f"{emoji} {cat.value.title()}",
                        value=(
                            f"Total: {total:,.2f} aUEC\n"
                            f"Count: {len(cat_transactions)}\n"
                            f"Average: {avg:,.2f} aUEC"
                        ),
                        inline=True
                    )

            # Add overall statistics
            total_amount = sum(t.amount for t in transactions)
            embed.add_field(
                name="📊 Overall Statistics",
                value=(
                    f"Total Transactions: {len(transactions)}\n"
                    f"Total Amount: {total_amount:,.2f} aUEC\n"
                    f"Period: {self.timeframe}"
                ),
                inline=False
            )

            view = discord.ui.View()
            view.add_item(BackToMainMenuButton(self.cog))
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error generating category summary: {e}")
            await interaction.followup.send(
                "An error occurred while generating the category summary.",
                ephemeral=True
            )
            
    @discord.ui.button(label="Back to Transaction Options", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to transaction options."""
        view = TransactionOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Transaction Options",
            description="Select an option to view or manage your transactions:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class ExportOptionsView(discord.ui.View):
    """View for export options."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(timeout=300)
        self.cog = cog
        self.timeframe = "month"
        self.format = "csv"
        
        # Add timeframe and format selects
        self.add_item(self.create_timeframe_select())
        self.add_item(self.create_format_select())
        
    def create_timeframe_select(self):
        """Create timeframe select menu."""
        options = [
            discord.SelectOption(label="Week", value="week", description="Transactions from the past 7 days"),
            discord.SelectOption(label="Month", value="month", description="Transactions from the past 30 days", default=True),
            discord.SelectOption(label="Year", value="year", description="Transactions from the past 365 days")
        ]
        
        select = discord.ui.Select(
            placeholder="Select timeframe...",
            options=options
        )
        
        async def callback(interaction: DiscordInteraction):
            self.timeframe = select.values[0]
            await interaction.response.defer()
            
        select.callback = callback
        return select
        
    def create_format_select(self):
        """Create format select menu."""
        options = [
            discord.SelectOption(label="CSV", value="csv", description="Export as comma-separated values file", default=True),
            discord.SelectOption(label="JSON", value="json", description="Export as JSON file")
        ]
        
        select = discord.ui.Select(
            placeholder="Select format...",
            options=options
        )
        
        async def callback(interaction: DiscordInteraction):
            self.format = select.values[0]
            await interaction.response.defer()
            
        select.callback = callback
        return select
        
    @discord.ui.button(label="Export", style=discord.ButtonStyle.primary)
    async def export_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Export transactions."""
        await interaction.response.defer(thinking=True)
        
        try:
            # Get date range
            now = datetime.now(timezone.utc)
            if self.timeframe == "week":
                start_date = now - timedelta(weeks=1)
            elif self.timeframe == "month":
                start_date = now - timedelta(days=30)
            else:  # year
                start_date = now - timedelta(days=365)

            transactions = await self.cog.get_transactions(
                interaction.user.id,
                start_date=start_date
            )

            if not transactions:
                embed = discord.Embed(
                    title="No Transactions Found",
                    description=f"No transactions found for the selected timeframe ({self.timeframe}).",
                    color=discord.Color.orange()
                )
                view = discord.ui.View()
                view.add_item(BackToMainMenuButton(self.cog))
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                return

            if self.format == "csv":
                # Create CSV string
                headers = [
                    "Date", "Type", "Category", "Amount", "Description",
                    "Status", "Transaction ID"
                ]
                rows = []
                rows.append(",".join(headers))
                
                for trans in transactions:
                    created_at = datetime.fromisoformat(
                        trans.metadata['created_at'].replace('Z', '+00:00')
                    )
                    
                    # Handle possible None values
                    category = trans.category.value if trans.category else ""
                    description = trans.description or ""
                    # Escape quotes in description
                    desc_escaped = description.replace('"', '""')
                    description = '"' + desc_escaped + '"'
                    
                    row = [
                        created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        trans.trans_type.value,
                        category,
                        str(trans.amount),
                        description,
                        trans.status.value,
                        trans.transaction_id or ""
                    ]
                    rows.append(",".join(row))
                
                content = "\n".join(rows)
                
            else:  # json
                # Create JSON structure
                json_data = []
                for trans in transactions:
                    created_at = datetime.fromisoformat(
                        trans.metadata['created_at'].replace('Z', '+00:00')
                    )
                    json_data.append({
                        "date": created_at.isoformat(),
                        "type": trans.trans_type.value,
                        "category": trans.category.value if trans.category else None,
                        "amount": str(trans.amount),
                        "description": trans.description,
                        "status": trans.status.value,
                        "transaction_id": trans.transaction_id
                    })
                
                content = json.dumps(json_data, indent=2)

            # Create a discord.File with the content
            filename = f"transactions_{self.timeframe}_{self.format}.{self.format}"
            file = discord.File(
                io.StringIO(content),
                filename=filename
            )
            
            embed = discord.Embed(
                title="Transaction Export",
                description=f"Your transaction history for the last {self.timeframe}",
                color=discord.Color.blue(),
                timestamp=now
            )
            
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            
            # Keep the export menu open
            view = ExportOptionsView(self.cog)
            view.timeframe = self.timeframe
            view.format = self.format
            
            embed = discord.Embed(
                title="Export Transactions",
                description="Select format and timeframe for export:",
                color=discord.Color.blue()
            )
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)

        except Exception as e:
            logger.error(f"Error exporting transactions: {e}")
            await interaction.followup.send(
                "An error occurred while exporting your transactions.",
                ephemeral=True
            )
            
    @discord.ui.button(label="Back to Transaction Options", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Return to transaction options."""
        view = TransactionOptionsView(self.cog)
        embed = discord.Embed(
            title="🏦 Banking - Transaction Options",
            description="Select an option to view or manage your transactions:",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

# Modal forms for various banking operations
class DepositModal(discord.ui.Modal):
    """Modal for deposit operation."""
    def __init__(self, cog: 'BankingCog', quick: bool = False):
        super().__init__(title="Deposit Funds")
        self.cog = cog
        self.quick = quick
        
        self.amount_input = discord.ui.TextInput(
            label="Amount to Deposit",
            placeholder="Enter amount...",
            required=True
        )
        self.add_item(self.amount_input)
        
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Purpose of deposit...",
            required=False,
            max_length=100
        )
        self.add_item(self.description_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle deposit form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            description = self.description_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
                
            # Process deposit
            success = await self.cog.update_balance(interaction.user.id, amount)
            
            if success:
                # Record transaction
                await self.cog.add_transaction(
                    interaction.user.id,
                    TransactionType.DEPOSIT.value,
                    amount,
                    None,
                    description
                )
                
                # Get new balance
                new_balance = await self.cog.get_balance(interaction.user.id)
                
                # Create response embed
                embed = discord.Embed(
                    title="Deposit Successful",
                    description=f"Successfully deposited {amount:,.2f} aUEC to your account.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="New Balance",
                    value=f"{new_balance:,.2f} aUEC",
                    inline=True
                )
                
                if description:
                    embed.add_field(
                        name="Description",
                        value=description,
                        inline=False
                    )
                
                # Show different views based on context
                if self.quick:
                    view = QuickActionsView(self.cog)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    
                    # Update original message
                    embed = discord.Embed(
                        title="🏦 Banking - Quick Actions",
                        description="Common banking actions:",
                        color=discord.Color.green()
                    )
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                else:
                    view = AccountOptionsView(self.cog)
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                await interaction.followup.send(
                    "Failed to process deposit. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error processing deposit: {e}")
            await interaction.followup.send(
                "An error occurred while processing your deposit.",
                ephemeral=True
            )

class WithdrawModal(discord.ui.Modal):
    """Modal for withdrawal operation."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(title="Withdraw Funds")
        self.cog = cog
        
        self.amount_input = discord.ui.TextInput(
            label="Amount to Withdraw",
            placeholder="Enter amount...",
            required=True
        )
        self.add_item(self.amount_input)
        
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Purpose of withdrawal...",
            required=False,
            max_length=100
        )
        self.add_item(self.description_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle withdrawal form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            description = self.description_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
                
            # Check balance
            current_balance = await self.cog.get_balance(interaction.user.id)
            if current_balance < amount:
                await interaction.followup.send(
                    f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                    ephemeral=True
                )
                return
                
            # Process withdrawal
            success = await self.cog.update_balance(interaction.user.id, -amount)
            
            if success:
                # Record transaction
                await self.cog.add_transaction(
                    interaction.user.id,
                    TransactionType.WITHDRAW.value,
                    -amount,
                    None,
                    description
                )
                
                # Get new balance
                new_balance = await self.cog.get_balance(interaction.user.id)
                
                # Create response embed
                embed = discord.Embed(
                    title="Withdrawal Successful",
                    description=f"Successfully withdrew {amount:,.2f} aUEC from your account.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="New Balance",
                    value=f"{new_balance:,.2f} aUEC",
                    inline=True
                )
                
                if description:
                    embed.add_field(
                        name="Description",
                        value=description,
                        inline=False
                    )
                
                view = AccountOptionsView(self.cog)
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                await interaction.followup.send(
                    "Failed to process withdrawal. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error processing withdrawal: {e}")
            await interaction.followup.send(
                "An error occurred while processing your withdrawal.",
                ephemeral=True
            )

class TransferStartModal(discord.ui.Modal):
    """Modal for first step of transfer operation."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(title="Transfer Funds - Step 1")
        self.cog = cog
        
        self.user_input = discord.ui.TextInput(
            label="Recipient's User ID or @mention",
            placeholder="Enter user ID or paste @mention...",
            required=True
        )
        self.add_item(self.user_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle initial transfer form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            user_input = self.user_input.value.strip()
            
            # Parse user ID from input (handle both raw ID and @mention)
            user_id = None
            if user_input.isdigit():
                user_id = int(user_input)
            elif user_input.startswith('<@') and user_input.endswith('>'):
                # Extract ID from mention format <@123456789>
                id_str = user_input[2:-1]
                if id_str.isdigit():
                    user_id = int(id_str)
                    
            if not user_id:
                await interaction.followup.send(
                    "Invalid user ID or mention format. Please enter a valid user ID or mention.",
                    ephemeral=True
                )
                return
                
            if user_id == interaction.user.id:
                await interaction.followup.send(
                    "You cannot transfer funds to yourself.",
                    ephemeral=True
                )
                return
                
            # Try to fetch user to verify they exist
            try:
                target_user = await interaction.client.fetch_user(user_id)
                
                # If successful, show the transfer amount modal
                modal = TransferAmountModal(self.cog, target_user)
                await interaction.followup.send_modal(modal)
                
            except discord.NotFound:
                await interaction.followup.send(
                    "User not found. Please check the ID and try again.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in transfer user selection: {e}")
            await interaction.followup.send(
                "An error occurred while processing your transfer.",
                ephemeral=True
            )

class TransferAmountModal(discord.ui.Modal):
    """Modal for second step of transfer operation."""
    def __init__(self, cog: 'BankingCog', target_user: discord.User):
        super().__init__(title=f"Transfer to {target_user.display_name}")
        self.cog = cog
        self.target_user = target_user
        
        self.amount_input = discord.ui.TextInput(
            label="Amount to Transfer",
            placeholder="Enter amount...",
            required=True
        )
        self.add_item(self.amount_input)
        
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Purpose of transfer...",
            required=False,
            max_length=100
        )
        self.add_item(self.description_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle transfer amount form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            description = self.description_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
                
            # Check balance
            current_balance = await self.cog.get_balance(interaction.user.id)
            if current_balance < amount:
                await interaction.followup.send(
                    f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                    ephemeral=True
                )
                return
                
            # Process transfer - sender side
            sender_success = await self.cog.update_balance(interaction.user.id, -amount)
            if not sender_success:
                await interaction.followup.send(
                    "Failed to process transfer. Please try again later.",
                    ephemeral=True
                )
                return
                
            # Process transfer - recipient side
            recipient_success = await self.cog.update_balance(self.target_user.id, amount)
            if not recipient_success:
                # Rollback sender transaction if recipient fails
                await self.cog.update_balance(interaction.user.id, amount)
                await interaction.followup.send(
                    "Failed to complete transfer to recipient. Your account has not been charged.",
                    ephemeral=True
                )
                return
                
            # Record transactions
            await self.cog.add_transaction(
                interaction.user.id,
                TransactionType.TRANSFER_OUT.value,
                -amount,
                self.target_user.id,
                description
            )
            
            await self.cog.add_transaction(
                self.target_user.id,
                TransactionType.TRANSFER_IN.value,
                amount,
                interaction.user.id,
                description
            )
            
            # Get new balance
            new_balance = await self.cog.get_balance(interaction.user.id)
            
            # Create response embed
            embed = discord.Embed(
                title="Transfer Successful",
                description=f"Successfully transferred {amount:,.2f} aUEC to {self.target_user.display_name}.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Recipient",
                value=f"{self.target_user.mention} ({self.target_user.id})",
                inline=True
            )
            
            embed.add_field(
                name="New Balance",
                value=f"{new_balance:,.2f} aUEC",
                inline=True
            )
            
            if description:
                embed.add_field(
                    name="Description",
                    value=description,
                    inline=False
                )
            
            view = AccountOptionsView(self.cog)
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            
            # Notify recipient
            try:
                recipient_embed = discord.Embed(
                    title="Transfer Received",
                    description=f"You have received {amount:,.2f} aUEC from {interaction.user.display_name}.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                recipient_embed.add_field(
                    name="Sender",
                    value=f"{interaction.user.mention} ({interaction.user.id})",
                    inline=True
                )
                
                recipient_balance = await self.cog.get_balance(self.target_user.id)
                recipient_embed.add_field(
                    name="New Balance",
                    value=f"{recipient_balance:,.2f} aUEC",
                    inline=True
                )
                
                if description:
                    recipient_embed.add_field(
                        name="Description",
                        value=description,
                        inline=False
                    )
                    
                await self.target_user.send(embed=recipient_embed)
            except:
                logger.warning(f"Could not send transfer notification to user {self.target_user.id}")
                
        except Exception as e:
            logger.error(f"Error processing transfer: {e}")
            await interaction.followup.send(
                "An error occurred while processing your transfer.",
                ephemeral=True
            )

class AddNoteModal(discord.ui.Modal):
    """Modal for adding note to transaction."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(title="Add Note to Transaction")
        self.cog = cog
        
        self.transaction_id_input = discord.ui.TextInput(
            label="Transaction ID",
            placeholder="Enter transaction ID...",
            required=True
        )
        self.add_item(self.transaction_id_input)
        
        self.note_input = discord.ui.TextInput(
            label="Note",
            placeholder="Enter your note...",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.note_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle note form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            transaction_id = self.transaction_id_input.value.strip()
            note = self.note_input.value.strip()
            
            success = await self.cog.add_transaction_note(
                transaction_id,
                interaction.user.id,
                note
            )
            
            if success:
                embed = discord.Embed(
                    title="Note Added",
                    description="Successfully added note to transaction.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="Transaction ID",
                    value=transaction_id,
                    inline=True
                )
                
                embed.add_field(
                    name="Note",
                    value=note,
                    inline=False
                )
                
                view = TransactionOptionsView(self.cog)
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                await interaction.followup.send(
                    "Failed to add note. Please check the transaction ID and try again.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error adding note: {e}")
            await interaction.followup.send(
                "An error occurred while adding the note.",
                ephemeral=True
            )

class CreateGoalModal(discord.ui.Modal):
    """Modal for creating savings goal."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(title="Create Savings Goal")
        self.cog = cog
        
        self.amount_input = discord.ui.TextInput(
            label="Target Amount",
            placeholder="Enter target amount...",
            required=True
        )
        self.add_item(self.amount_input)
        
        self.description_input = discord.ui.TextInput(
            label="Goal Description",
            placeholder="What are you saving for?",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.description_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle goal creation form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            description = self.description_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Target amount must be positive.",
                    ephemeral=True
                )
                return
                
            # Create the goal
            goal = await self.cog.set_savings_goal(
                interaction.user.id,
                amount,
                description
            )
            
            if goal:
                embed = self.cog.create_goal_embed(goal, interaction.user)
                
                view = GoalsOptionsView(self.cog)
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                await interaction.followup.send(
                    "Failed to create savings goal. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error creating goal: {e}")
            await interaction.followup.send(
                "An error occurred while creating your savings goal.",
                ephemeral=True
            )

class ContributeGoalModal(discord.ui.Modal):
    """Modal for contributing to savings goal."""
    def __init__(self, cog: 'BankingCog', goal: GoalData):
        super().__init__(title="Contribute to Goal")
        self.cog = cog
        self.goal = goal
        
        self.amount_input = discord.ui.TextInput(
            label="Contribution Amount",
            placeholder="Enter amount...",
            required=True
        )
        self.add_item(self.amount_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle goal contribution form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Contribution amount must be positive.",
                    ephemeral=True
                )
                return
                
            # Check balance
            current_balance = await self.cog.get_balance(interaction.user.id)
            if current_balance < amount:
                await interaction.followup.send(
                    f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                    ephemeral=True
                )
                return
                
            # Deduct from balance
            balance_update = await self.cog.update_balance(interaction.user.id, -amount)
            if not balance_update:
                await interaction.followup.send(
                    "Failed to update balance. Please try again later.",
                    ephemeral=True
                )
                return
                
            # Update goal progress
            updated_goal = await self.cog.update_goal_progress(
                self.goal.goal_id,
                amount
            )
            
            if updated_goal:
                # Record transaction
                await self.cog.add_transaction(
                    interaction.user.id,
                    TransactionType.WITHDRAW.value,
                    -amount,
                    None,
                    f"Contribution to goal: {self.goal.description}"
                )
                
                # Create response embed
                embed = self.cog.create_goal_embed(updated_goal, interaction.user)
                
                embed.title = "Goal Contribution Successful"
                
                view = GoalsOptionsView(self.cog)
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
            else:
                # Rollback balance update
                await self.cog.update_balance(interaction.user.id, amount)
                await interaction.followup.send(
                    "Failed to update goal progress. Your account has not been charged.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error contributing to goal: {e}")
            await interaction.followup.send(
                "An error occurred while processing your contribution.",
                ephemeral=True
            )

class ModifyGoalModal(discord.ui.Modal):
    """Modal for modifying savings goal."""
    def __init__(self, cog: 'BankingCog', goal: GoalData):
        super().__init__(title="Modify Goal")
        self.cog = cog
        self.goal = goal
        
        self.description_input = discord.ui.TextInput(
            label="New Description",
            placeholder="Update goal description...",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph,
            default=goal.description
        )
        self.add_item(self.description_input)
        
        self.status_input = discord.ui.TextInput(
            label="Status (active/completed/abandoned)",
            placeholder="Enter new status...",
            required=True,
            default=goal.status.value
        )
        self.add_item(self.status_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle goal modification form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            description = self.description_input.value.strip()
            status_str = self.status_input.value.strip().lower()
            
            # Validate status
            try:
                status = GoalStatus(status_str)
            except:
                await interaction.followup.send(
                    "Invalid status. Must be one of: active, completed, abandoned.",
                    ephemeral=True
                )
                return
                
            # Update the goal
            success = await self.cog.modify_goal(
                self.goal.goal_id,
                description,
                status
            )
            
            if success:
                # Get updated goal
                updated_goal = await self.cog.get_goal(self.goal.goal_id)
                
                if updated_goal:
                    embed = self.cog.create_goal_embed(updated_goal, interaction.user)
                    
                    embed.title = "Goal Modified Successfully"
                    
                    view = GoalsOptionsView(self.cog)
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.send(
                        "Goal was modified, but couldn't retrieve updated information.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "Failed to modify goal. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error modifying goal: {e}")
            await interaction.followup.send(
                "An error occurred while modifying your savings goal.",
                ephemeral=True
            )

class LoanApplicationModal(discord.ui.Modal):
    """Modal for cargo investment loan application."""
    def __init__(self, cog: 'BankingCog'):
        super().__init__(title="Cargo Investment Loan Application")
        self.cog = cog
        
        self.amount_input = discord.ui.TextInput(
            label="Loan Amount",
            placeholder="Enter requested amount...",
            required=True
        )
        self.add_item(self.amount_input)
        
        self.purpose_input = discord.ui.TextInput(
            label="Purpose",
            placeholder="Describe your cargo plans...",
            required=True,
            max_length=300,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.purpose_input)
        
        self.security_input = discord.ui.TextInput(
            label="Security Team (Member IDs)",
            placeholder="List security team member IDs, separated by commas...",
            required=True
        )
        self.add_item(self.security_input)
        
        self.repayment_input = discord.ui.TextInput(
            label="Estimated Repayment Date",
            placeholder="YYYY-MM-DD",
            required=True
        )
        self.add_item(self.repayment_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle loan application form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            purpose = self.purpose_input.value.strip()
            security_team_str = self.security_input.value.strip()
            repayment_date_str = self.repayment_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Loan amount must be positive.",
                    ephemeral=True
                )
                return
                
            # Parse security team
            security_team = []
            try:
                for member_id in security_team_str.split(','):
                    member_id = member_id.strip()
                    if member_id:
                        if member_id.isdigit():
                            security_team.append(int(member_id))
                        elif member_id.startswith('<@') and member_id.endswith('>'):
                            id_str = member_id[2:-1]
                            if id_str.isdigit():
                                security_team.append(int(id_str))
            except:
                pass
                
            if not security_team:
                await interaction.followup.send(
                    "You must provide at least one security team member.",
                    ephemeral=True
                )
                return
                
            # Parse repayment date
            try:
                repayment_date = datetime.strptime(repayment_date_str, "%Y-%m-%d")
                repayment_date = repayment_date.replace(tzinfo=timezone.utc)
                
                # Ensure date is in the future
                if repayment_date <= datetime.now(timezone.utc):
                    await interaction.followup.send(
                        "Repayment date must be in the future.",
                        ephemeral=True
                    )
                    return
            except:
                await interaction.followup.send(
                    "Invalid date format. Please use YYYY-MM-DD.",
                    ephemeral=True
                )
                return
                
            # Create the loan application
            loan = await self.cog.create_loan_application(
                interaction.user.id,
                amount,
                purpose,
                security_team,
                repayment_date
            )
            
            if loan:
                embed = discord.Embed(
                    title="Loan Application Submitted",
                    description="Your cargo investment loan application has been submitted for review.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="Amount",
                    value=f"{amount:,.2f} aUEC",
                    inline=True
                )
                
                embed.add_field(
                    name="Status",
                    value="⏳ Pending",
                    inline=True
                )
                
                embed.add_field(
                    name="Repayment Due",
                    value=repayment_date.strftime("%Y-%m-%d"),
                    inline=True
                )
                
                embed.add_field(
                    name="Purpose",
                    value=purpose,
                    inline=False
                )
                
                security_team_mentions = []
                for member_id in security_team:
                    try:
                        member = await interaction.client.fetch_user(member_id)
                        security_team_mentions.append(f"{member.mention} ({member.display_name})")
                    except:
                        security_team_mentions.append(f"<@{member_id}>")
                
                if security_team_mentions:
                    embed.add_field(
                        name="Security Team",
                        value="\n".join(security_team_mentions),
                        inline=False
                    )
                
                embed.set_footer(text=f"Loan ID: {loan.loan_id}")
                
                view = LoanOptionsView(self.cog)
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                
                # Notify admins for approval
                await self.cog.notify_loan_application(loan, interaction.user)
            else:
                await interaction.followup.send(
                    "Failed to submit loan application. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error submitting loan application: {e}")
            await interaction.followup.send(
                "An error occurred while submitting your loan application.",
                ephemeral=True
            )

class RepayLoanModal(discord.ui.Modal):
    """Modal for loan repayment."""
    def __init__(self, cog: 'BankingCog', loan: LoanData):
        super().__init__(title="Repay Loan")
        self.cog = cog
        self.loan = loan
        
        # Calculate remaining amount
        self.remaining = self.loan.amount - self.loan.repaid_amount
        
        # Add interest if not waived
        if not self.loan.tax_waived:
            self.interest = self.loan.amount * self.loan.interest_rate
        else:
            self.interest = Decimal('0')
            
        # Add security fee if not waived
        if not self.loan.security_fee_waived:
            self.security_fee = self.loan.amount * self.loan.security_payout_percentage
        else:
            self.security_fee = Decimal('0')
            
        self.total_remaining = self.remaining + self.interest + self.security_fee
        
        self.amount_input = discord.ui.TextInput(
            label=f"Amount to Repay (Total: {self.total_remaining:,.2f})",
            placeholder=f"Enter amount (up to {self.total_remaining:,.2f})...",
            required=True
        )
        self.add_item(self.amount_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle loan repayment form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            amount_str = self.amount_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Repayment amount must be positive.",
                    ephemeral=True
                )
                return
                
            if amount > self.total_remaining:
                await interaction.followup.send(
                    f"Repayment amount exceeds the remaining balance ({self.total_remaining:,.2f} aUEC).",
                    ephemeral=True
                )
                return
                
            # Check user balance
            current_balance = await self.cog.get_balance(interaction.user.id)
            if current_balance < amount:
                await interaction.followup.send(
                    f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                    ephemeral=True
                )
                return
                
            # Process repayment
            success = await self.cog.repay_loan(
                self.loan.loan_id,
                amount
            )
            
            if success:
                # Deduct from user balance
                await self.cog.update_balance(interaction.user.id, -amount)
                
                # Record transaction
                await self.cog.add_transaction(
                    interaction.user.id,
                    TransactionType.LOAN_REPAYMENT.value,
                    -amount,
                    None,
                    f"Loan repayment for cargo investment: {self.loan.loan_id}",
                    TransactionStatus.COMPLETED,
                    TransactionCategory.LOAN
                )
                
                # Get updated loan
                updated_loan = await self.cog.get_loan(self.loan.loan_id)
                
                if updated_loan:
                    embed = self.cog.create_loan_embed(updated_loan)
                    
                    embed.title = "Loan Repayment Successful"
                    
                    new_balance = await self.cog.get_balance(interaction.user.id)
                    embed.add_field(
                        name="Your New Balance",
                        value=f"{new_balance:,.2f} aUEC",
                        inline=True
                    )
                    
                    view = LoanOptionsView(self.cog)
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.send(
                        "Repayment processed, but couldn't retrieve updated loan information.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "Failed to process loan repayment. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error processing loan repayment: {e}")
            await interaction.followup.send(
                "An error occurred while processing your loan repayment.",
                ephemeral=True
            )

class IncidentReportModal(discord.ui.Modal):
    """Modal for cargo incident report."""
    def __init__(self, cog: 'BankingCog', loan: LoanData):
        super().__init__(title="Cargo Incident Report")
        self.cog = cog
        self.loan = loan
        
        self.description_input = discord.ui.TextInput(
            label="Incident Description",
            placeholder="Describe what happened...",
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.description_input)
        
        self.location_input = discord.ui.TextInput(
            label="Location",
            placeholder="Where did the incident occur?",
            required=True
        )
        self.add_item(self.location_input)
        
        self.amount_input = discord.ui.TextInput(
            label="Amount Lost (aUEC)",
            placeholder="Estimated cargo value lost...",
            required=True
        )
        self.add_item(self.amount_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle incident report form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            description = self.description_input.value.strip()
            location = self.location_input.value.strip()
            amount_str = self.amount_input.value.strip()
            
            # Parse and validate amount
            try:
                amount = Decimal(amount_str)
            except:
                await interaction.followup.send(
                    "Invalid amount format. Please enter a valid number.",
                    ephemeral=True
                )
                return
                
            if amount <= 0:
                await interaction.followup.send(
                    "Amount lost must be positive.",
                    ephemeral=True
                )
                return
                
            if amount > self.loan.amount:
                await interaction.followup.send(
                    f"Amount lost cannot exceed the loan amount ({self.loan.amount:,.2f} aUEC).",
                    ephemeral=True
                )
                return
                
            # Create the incident report
            incident = await self.cog.create_cargo_incident(
                self.loan.loan_id,
                interaction.user.id,
                description,
                amount,
                location
            )
            
            if incident:
                embed = discord.Embed(
                    title="Cargo Incident Report Submitted",
                    description="Your cargo incident report has been submitted for review.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="Loan ID",
                    value=self.loan.loan_id,
                    inline=True
                )
                
                embed.add_field(
                    name="Status",
                    value="⏳ Pending Review",
                    inline=True
                )
                
                embed.add_field(
                    name="Amount Lost",
                    value=f"{amount:,.2f} aUEC",
                    inline=True
                )
                
                embed.add_field(
                    name="Location",
                    value=location,
                    inline=True
                )
                
                embed.add_field(
                    name="Description",
                    value=description,
                    inline=False
                )
                
                embed.set_footer(text=f"Incident ID: {incident.incident_id}")
                
                view = LoanOptionsView(self.cog)
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
                
                # Notify admins for review
                await self.cog.notify_incident_report(incident, self.loan, interaction.user)
            else:
                await interaction.followup.send(
                    "Failed to submit incident report. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error submitting incident report: {e}")
            await interaction.followup.send(
                "An error occurred while submitting your incident report.",
                ephemeral=True
            )
class LoanRepaymentReminderView(discord.ui.View):
    """View for loan repayment buttons in reminder DMs."""
    def __init__(self, cog: 'BankingCog', loan: LoanData):
        super().__init__(timeout=None)  # No timeout for DM buttons
        self.cog = cog
        self.loan = loan
        
    @discord.ui.button(label="Repay Loan", style=discord.ButtonStyle.primary)
    async def repay_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Open repayment modal."""
        modal = RepayLoanModal(self.cog, self.loan)
        await interaction.response.send_modal(modal)
        
class LoanReviewView(discord.ui.View):
    """View for admin loan review."""
    def __init__(self, cog: 'BankingCog', loan_id: str):
        super().__init__(timeout=None)  # No timeout for admin actions
        self.cog = cog
        self.loan_id = loan_id
        
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Approve loan application."""
        if not await self.check_admin_permissions(interaction):
            return
            
        modal = LoanApprovalModal(self.cog, self.loan_id)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_button(self, interaction: DiscordInteraction, button: discord.ui.Button):
        """Reject loan application."""
        if not await self.check_admin_permissions(interaction):
            return
            
        modal = LoanRejectionModal(self.cog, self.loan_id)
        await interaction.response.send_modal(modal)
        
    async def check_admin_permissions(self, interaction: DiscordInteraction) -> bool:
        """Check if user has admin permissions."""
        # TODO: Replace with your actual permission check
        # Example:
        # admin_role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
        # if admin_role not in interaction.user.roles:
        #     await interaction.response.send_message("You don't have permission to review loans.", ephemeral=True)
        #     return False
        return True
        
class LoanApprovalModal(discord.ui.Modal):
    """Modal for approving a loan."""
    def __init__(self, cog: 'BankingCog', loan_id: str):
        super().__init__(title="Approve Loan Application")
        self.cog = cog
        self.loan_id = loan_id
        
        self.disburse_input = discord.ui.TextInput(
            label="Disburse funds now? (yes/no)",
            placeholder="Type 'yes' to disburse immediately",
            required=True,
            default="yes"
        )
        self.add_item(self.disburse_input)
        
        self.tax_waiver_input = discord.ui.TextInput(
            label="Waive interest tax? (yes/no)",
            placeholder="Type 'yes' to waive interest",
            required=True,
            default="no"
        )
        self.add_item(self.tax_waiver_input)
        
        self.security_fee_waiver_input = discord.ui.TextInput(
            label="Waive security fee? (yes/no)",
            placeholder="Type 'yes' to waive security fee",
            required=True,
            default="no"
        )
        self.add_item(self.security_fee_waiver_input)
        
        self.notes_input = discord.ui.TextInput(
            label="Notes (Optional)",
            placeholder="Add any notes to the approval...",
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.notes_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle loan approval form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            disburse_now = self.disburse_input.value.strip().lower() == "yes"
            tax_waived = self.tax_waiver_input.value.strip().lower() == "yes"
            security_fee_waived = self.security_fee_waiver_input.value.strip().lower() == "yes"
            notes = self.notes_input.value.strip()
            
            success = await self.cog.approve_loan(
                self.loan_id,
                interaction.user.id,
                disburse_now,
                tax_waived,
                security_fee_waived,
                notes
            )
            
            if success:
                # Get updated loan
                loan = await self.cog.get_loan(self.loan_id)
                
                if loan:
                    status_text = "approved and funds disbursed" if disburse_now else "approved"
                    
                    embed = discord.Embed(
                        title="Loan Application Approved",
                        description=f"The loan application has been {status_text}.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    embed.add_field(
                        name="Loan ID",
                        value=self.loan_id,
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Amount",
                        value=f"{loan.amount:,.2f} aUEC",
                        inline=True
                    )
                    
                    fee_status = []
                    if loan.tax_waived:
                        fee_status.append("Interest waived")
                    if loan.security_fee_waived:
                        fee_status.append("Security fee waived")
                    
                    if fee_status:
                        embed.add_field(
                            name="Fee Status",
                            value=", ".join(fee_status),
                            inline=True
                        )
                    
                    if notes:
                        embed.add_field(
                            name="Notes",
                            value=notes,
                            inline=False
                        )
                        
                    await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
                else:
                    await interaction.followup.edit_message(
                        interaction.message.id,
                        content="Loan approved, but couldn't retrieve updated loan information.",
                        view=None
                    )
            else:
                await interaction.followup.send(
                    "Failed to approve loan. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error approving loan: {e}")
            await interaction.followup.send(
                "An error occurred while approving the loan.",
                ephemeral=True
            )
            
class LoanRejectionModal(discord.ui.Modal):
    """Modal for rejecting a loan."""
    def __init__(self, cog: 'BankingCog', loan_id: str):
        super().__init__(title="Reject Loan Application")
        self.cog = cog
        self.loan_id = loan_id
        
        self.reason_input = discord.ui.TextInput(
            label="Rejection Reason",
            placeholder="Explain why the loan is being rejected...",
            required=True,
            max_length=300,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.reason_input)
        
    async def on_submit(self, interaction: DiscordInteraction):
        """Handle loan rejection form submission."""
        await interaction.response.defer(thinking=True)
        
        try:
            reason = self.reason_input.value.strip()
            
            success = await self.cog.reject_loan(
                self.loan_id,
                interaction.user.id,
                reason
            )
            
            if success:
                embed = discord.Embed(
                    title="Loan Application Rejected",
                    description="The loan application has been rejected.",
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="Loan ID",
                    value=self.loan_id,
                    inline=True
                )
                
                embed.add_field(
                    name="Reason",
                    value=reason,
                    inline=False
                )
                        
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
            else:
                await interaction.followup.send(
                    "Failed to reject loan. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error rejecting loan: {e}")
            await interaction.followup.send(
                "An error occurred while rejecting the loan.",
                ephemeral=True
            )

class BankingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._profile_cog = None
        self.cache = BankingCache()
        self.rate_limits = defaultdict(lambda: {"last_update": 0, "count": 0})
        self.RATE_LIMIT_WINDOW = 60  # 1 minute
        self.MAX_OPERATIONS = 10  # Max operations per minute
        
        # Loan limits by rank
        self.loan_limits = {
            MemberRank.RECRUIT: Decimal('50000'),
            MemberRank.MEMBER: Decimal('200000'),
            MemberRank.VETERAN: Decimal('500000'),
            MemberRank.OFFICER: Decimal('1000000'),
            MemberRank.ADMIN: Decimal('2500000')
        }
        
        # Organization budget cache
        self.org_budget_cache = None
        self.org_budget_cache_time = 0
        self.ORG_BUDGET_CACHE_TTL = 300  # 5 minutes
        
        # Start cache cleanup
        asyncio.create_task(self.cache.start_cleanup())
        
        # Start the sync usernames task
        self.sync_usernames.start()
        
        # Start the loan due date check task
        self.check_loan_due_dates.start()
        

    # ====================== CORE API METHODS ======================
    
    async def setup_column_ids(self):
        """Set up column IDs for database tables using predefined values."""
        global USERNAME_COLUMN, BALANCE_COLUMN
        
        # Use predefined column IDs
        # These are defined at the top of the file
        logger.info(f"Setting up column IDs using predefined values")
        logger.info(f"Discord User ID column: {DISCORD_USER_ID_COLUMN}")
        logger.info(f"Balance column: {BALANCE_COLUMN}")
        logger.info(f"Username column: {USERNAME_COLUMN}")
        
        # Verify that the column IDs are valid by attempting to access the accounts table
        try:
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
            params = {
                'limit': 1
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if response and 'items' in response and len(response['items']) > 0:
                logger.info("Successfully verified column IDs with accounts table")
            else:
                logger.warning("Could not verify column IDs. Accounts table may be empty.")
        
        except Exception as e:
            logger.error(f"Error verifying column IDs: {e}")
            # We'll continue using the predefined IDs even if verification fails
        
    async def coda_api_request(self, method, endpoint, params=None, data=None):
        """Make a request to the Coda API with improved error handling and rate limiting."""
        if not CODA_API_TOKEN:
            logger.error("Coda API token not found")
            return None
            
        headers = {
            'Authorization': f'Bearer {CODA_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        url = f'https://coda.io/apis/v1/{endpoint}'
        
        # Add exponential backoff and retry for rate limits
        max_retries = 3
        base_sleep_time = 1  # Start with 1 second
        
        for retry_count in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    if method == 'GET':
                        async with session.get(url, headers=headers, params=params) as response:
                            if response.status == 200:
                                return await response.json()
                            elif response.status == 429:  # Rate limited
                                # Store the last rate limit time
                                self.cache.last_rate_limit = time.time()
                                
                                # Get retry-after header if available
                                retry_after = int(response.headers.get('Retry-After', 60))
                                
                                logger.warning(f"Rate limited by Coda API. Retry after {retry_after} seconds.")
                                
                                # If this is not the final retry, wait and try again
                                if retry_count < max_retries - 1:
                                    await asyncio.sleep(retry_after)
                                    continue
                                else:
                                    logger.error(f"API request failed after {max_retries} retries: {response.status} - {await response.text()}")
                                    return None
                            else:
                                logger.error(f"API request failed: {response.status} - {await response.text()}")
                                return None
                    elif method == 'POST':
                        async with session.post(url, headers=headers, json=data) as response:
                            if response.status in [200, 201, 202]:
                                return await response.json()
                            elif response.status == 429:  # Rate limited
                                # Store the last rate limit time
                                self.cache.last_rate_limit = time.time()
                                
                                # Get retry-after header if available
                                retry_after = int(response.headers.get('Retry-After', 60))
                                
                                logger.warning(f"Rate limited by Coda API. Retry after {retry_after} seconds.")
                                
                                # If this is not the final retry, wait and try again
                                if retry_count < max_retries - 1:
                                    await asyncio.sleep(retry_after)
                                    continue
                                else:
                                    logger.error(f"API request failed after {max_retries} retries: {response.status} - {await response.text()}")
                                    return None
                            else:
                                error_text = await response.text()
                                logger.error(f"API request failed: {response.status} - {error_text}")
                                
                                # Try to parse the response as JSON to get more detailed error
                                try:
                                    error_json = json.loads(error_text)
                                    if 'message' in error_json:
                                        logger.error(f"Error message: {error_json['message']}")
                                except:
                                    pass
                                    
                                return None
                    elif method == 'PUT':
                        async with session.put(url, headers=headers, json=data) as response:
                            if response.status in [200, 201, 202]:
                                return await response.json()
                            elif response.status == 429:  # Rate limited
                                self.cache.last_rate_limit = time.time()
                                retry_after = int(response.headers.get('Retry-After', 60))
                                if retry_count < max_retries - 1:
                                    await asyncio.sleep(retry_after)
                                    continue
                                else:
                                    logger.error(f"API request failed after {max_retries} retries: {response.status} - {await response.text()}")
                                    return None
                            else:
                                logger.error(f"API request failed: {response.status} - {await response.text()}")
                                return None
                    elif method == 'DELETE':
                        async with session.delete(url, headers=headers) as response:
                            if response.status in [200, 204]:
                                return True
                            elif response.status == 429:  # Rate limited
                                self.cache.last_rate_limit = time.time()
                                retry_after = int(response.headers.get('Retry-After', 60))
                                if retry_count < max_retries - 1:
                                    await asyncio.sleep(retry_after)
                                    continue
                                else:
                                    logger.error(f"API request failed after {max_retries} retries: {response.status} - {await response.text()}")
                                    return None
                            else:
                                logger.error(f"API request failed: {response.status} - {await response.text()}")
                                return None
                                
                # If we got here without a continue, the request was successful or failed for reasons other than rate limiting
                break
                    
            except Exception as e:
                logger.error(f"Error making API request: {e}")
                
                # Exponential backoff if we should retry
                if retry_count < max_retries - 1:
                    sleep_time = base_sleep_time * (2 ** retry_count)  # Exponential backoff
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    await asyncio.sleep(sleep_time)
                else:
                    return None
                    
        # If we exhausted all retries
        return None
    
    # ====================== BALANCE METHODS ======================
    
    async def get_balance(self, user_id: int) -> Decimal:
        """Get user's current balance from database or cache."""
        # Try cache first
        cached_balance = await self.cache.get_balance(user_id)
        if cached_balance is not None:
            return cached_balance
            
        # Fetch from Coda if not in cache
        try:
            # Query accounts table for the user
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
            params = {
                'query': f'Discord User ID = {user_id}',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                # User not found, create new account with 0 balance
                return await self.create_account(user_id)
                
            # Extract balance from response
            balance_str = response['items'][0]['values'].get('Balance', '0')
            balance = Decimal(balance_str)
            
            # Cache the balance
            await self.cache.set_balance(user_id, balance)
            
            return balance
        except Exception as e:
            logger.error(f"Error getting balance for user {user_id}: {e}")
            return Decimal('0')
    
    async def create_account(self, user_id: int) -> Decimal:
        """Create a new account for user with 0 balance."""
        try:
            # Check for rate limiting
            if self.check_rate_limit():
                logger.warning(f"Rate limited while creating account for user {user_id}")
                return Decimal('0')  # Return 0 balance for now to avoid further requests
            
            # Fetch user info from Discord
            user = await self.bot.fetch_user(user_id)
            username = user.name if user else f"User-{user_id}"
            
            # Create row in accounts table
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
            
            # Prepare cells based on known column IDs
            cells = [
                {'column': DISCORD_USER_ID_COLUMN, 'value': str(user_id)}
            ]
            
            if USERNAME_COLUMN:
                cells.append({'column': USERNAME_COLUMN, 'value': username})
            
            if BALANCE_COLUMN:
                cells.append({'column': BALANCE_COLUMN, 'value': '0'})
            
            data = {
                'rows': [{
                    'cells': cells
                }]
            }
            
            logger.info(f"Creating account for user {user_id}")
            
            response = await self.coda_api_request('POST', endpoint, data=data)
            
            if response and 'items' in response and len(response['items']) > 0:
                logger.info(f"Successfully created account for user {user_id}")
                
                # Cache the new balance
                await self.cache.set_balance(user_id, Decimal('0'))
                
                return Decimal('0')
            else:
                logger.error(f"Failed to create account for user {user_id}")
                # Check for error details in response
                if response and 'message' in response:
                    logger.error(f"Error message: {response['message']}")
                return Decimal('0')
        except Exception as e:
            logger.error(f"Error creating account for user {user_id}: {e}")
            return Decimal('0')

    
    async def update_balance(self, user_id: int, amount: Decimal) -> bool:
        """Update user's balance by adding the specified amount (can be negative)."""
        try:
            # Get current balance
            current_balance = await self.get_balance(user_id)
            new_balance = current_balance + amount
            
            # Prevent negative balance
            if new_balance < 0:
                logger.warning(f"Attempted to set negative balance for user {user_id}")
                return False
                
            # Query accounts table for the user to get row ID
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
            params = {
                'query': f'Discord User ID = {user_id}',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                # User not found, create new account
                if amount >= 0:
                    await self.create_account(user_id)
                    await self.update_balance(user_id, amount)
                    return True
                else:
                    return False
                    
            row_id = response['items'][0]['id']
            
            # Update balance in the table
            update_endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows/{row_id}'
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Balance', 'value': str(new_balance)}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Update the cache
                await self.cache.set_balance(user_id, new_balance)
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error updating balance for user {user_id}: {e}")
            return False
    
    # ====================== TRANSACTION METHODS ======================
    
    async def add_transaction(self, user_id: int, trans_type: str, amount: Decimal, 
                          target_user_id: Optional[int] = None, description: Optional[str] = None,
                          status: Optional[TransactionStatus] = TransactionStatus.COMPLETED,
                          category: Optional[TransactionCategory] = None,
                          session_id: Optional[str] = None,
                          goal_id: Optional[str] = None,
                          loan_id: Optional[str] = None) -> Optional[str]:
        """Record a transaction in the database."""
        try:
            # Generate transaction ID
            transaction_id = str(uuid.uuid4())
            
            # Generate timestamp
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Determine category if not provided
            if category is None:
                category = self.get_default_category(trans_type)
                
            # Create transaction data
            endpoint = f'docs/{DOC_ID}/tables/{TRANSACTIONS_TABLE_ID}/rows'
            
            data = {
                'rows': [{
                    'cells': [
                        {'column': 'Transaction ID', 'value': transaction_id},
                        {'column': 'Discord User ID', 'value': str(user_id)},
                        {'column': 'Type', 'value': trans_type},
                        {'column': 'Amount', 'value': str(amount)},
                        {'column': 'Status', 'value': status.value},
                        {'column': 'Created At', 'value': timestamp}
                    ]
                }]
            }
            
            # Add optional fields if provided
            if target_user_id:
                data['rows'][0]['cells'].append({'column': 'Target User ID', 'value': str(target_user_id)})
                
            if description:
                data['rows'][0]['cells'].append({'column': 'Description', 'value': description})
                
            if category:
                data['rows'][0]['cells'].append({'column': 'Category', 'value': category.value})
                
            if session_id:
                data['rows'][0]['cells'].append({'column': 'Session ID', 'value': session_id})
                
            if goal_id:
                data['rows'][0]['cells'].append({'column': 'Goal ID', 'value': goal_id})
                
            if loan_id:
                data['rows'][0]['cells'].append({'column': 'Loan ID', 'value': loan_id})
                
            response = await self.coda_api_request('POST', endpoint, data=data)
            
            if response and 'items' in response and len(response['items']) > 0:
                return transaction_id
            else:
                logger.error(f"Failed to record transaction for user {user_id}")
                return None
        except Exception as e:
            logger.error(f"Error recording transaction for user {user_id}: {e}")
            return None
    
    def get_default_category(self, trans_type: str) -> Optional[TransactionCategory]:
        """Determine the default category based on transaction type."""
        type_to_category = {
            TransactionType.DEPOSIT.value: TransactionCategory.PERSONAL,
            TransactionType.WITHDRAW.value: TransactionCategory.PERSONAL,
            TransactionType.TRANSFER_OUT.value: TransactionCategory.PERSONAL,
            TransactionType.TRANSFER_IN.value: TransactionCategory.PERSONAL,
            TransactionType.TRADE_PROFIT.value: TransactionCategory.TRADE,
            TransactionType.MINING_PROFIT.value: TransactionCategory.MINING,
            TransactionType.MISSION_REWARD.value: TransactionCategory.MISSION,
            TransactionType.BOUNTY_REWARD.value: TransactionCategory.BOUNTY,
            TransactionType.REFINERY_PROFIT.value: TransactionCategory.REFINERY,
            TransactionType.TRANSPORT_PROFIT.value: TransactionCategory.TRANSPORT,
            TransactionType.VC_PAYOUT.value: TransactionCategory.PAYOUT,
            TransactionType.LOAN_DISBURSEMENT.value: TransactionCategory.LOAN,
            TransactionType.LOAN_REPAYMENT.value: TransactionCategory.LOAN,
            TransactionType.SECURITY_PAYOUT.value: TransactionCategory.SECURITY,
            TransactionType.ORG_DONATION.value: TransactionCategory.DONATION,
            TransactionType.PROJECT_FUNDING.value: TransactionCategory.PROJECT
        }
        
        return type_to_category.get(trans_type, TransactionCategory.OTHER)
    
    async def get_transactions(self, user_id: int, start_date: Optional[datetime] = None, 
                              end_date: Optional[datetime] = None, 
                              trans_type: Optional[str] = None,
                              category: Optional[TransactionCategory] = None,
                              limit: int = 100) -> List[TransactionData]:
        """Get user transactions with optional filters."""
        try:
            # Build query
            query_parts = [f'Discord User ID = {user_id}']
            
            if start_date:
                query_parts.append(f'Created At >= "{start_date.isoformat()}"')
                
            if end_date:
                query_parts.append(f'Created At <= "{end_date.isoformat()}"')
                
            if trans_type:
                query_parts.append(f'Type = "{trans_type}"')
                
            if category:
                query_parts.append(f'Category = "{category.value}"')
                
            query = ' AND '.join(query_parts)
            
            # Query transactions table
            endpoint = f'docs/{DOC_ID}/tables/{TRANSACTIONS_TABLE_ID}/rows'
            params = {
                'query': query,
                'useColumnNames': 'true',
                'limit': limit,
                'sortBy': 'Created At',
                'sortDirection': 'desc'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response:
                return []
                
            # Convert response to TransactionData objects
            transactions = []
            for item in response['items']:
                values = item['values']
                
                # Parse transaction type
                try:
                    trans_type_value = values.get('Type')
                    trans_type_enum = TransactionType(trans_type_value) if trans_type_value else None
                except ValueError:
                    trans_type_enum = None
                    
                # Parse category
                try:
                    category_value = values.get('Category')
                    category_enum = TransactionCategory(category_value) if category_value else None
                except ValueError:
                    category_enum = None
                    
                # Parse status
                try:
                    status_value = values.get('Status', 'completed')
                    status_enum = TransactionStatus(status_value)
                except ValueError:
                    status_enum = TransactionStatus.COMPLETED
                    
                # Build metadata
                metadata = {
                    'created_at': values.get('Created At', ''),
                    'row_id': item.get('id', '')
                }
                
                # Create TransactionData object
                transaction = TransactionData(
                    user_id=int(values.get('Discord User ID', '0')),
                    trans_type=trans_type_enum,
                    amount=Decimal(values.get('Amount', '0')),
                    target_user_id=int(values.get('Target User ID', '0')) if values.get('Target User ID') else None,
                    description=values.get('Description'),
                    status=status_enum,
                    category=category_enum,
                    transaction_id=values.get('Transaction ID'),
                    session_id=values.get('Session ID'),
                    goal_id=values.get('Goal ID'),
                    loan_id=values.get('Loan ID'),
                    metadata=metadata
                )
                
                transactions.append(transaction)
                
            return transactions
        except Exception as e:
            logger.error(f"Error getting transactions for user {user_id}: {e}")
            return []
    
    async def add_transaction_note(self, transaction_id: str, user_id: int, note: str) -> bool:
        """Add a note to a transaction."""
        try:
            # Check if transaction exists and belongs to user
            endpoint = f'docs/{DOC_ID}/tables/{TRANSACTIONS_TABLE_ID}/rows'
            params = {
                'query': f'Transaction ID = "{transaction_id}" AND Discord User ID = {user_id}',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                logger.warning(f"Transaction {transaction_id} not found or doesn't belong to user {user_id}")
                return False
                
            # Generate note ID and timestamp
            note_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Create note in notes table
            notes_endpoint = f'docs/{DOC_ID}/tables/{NOTES_TABLE_ID}/rows'
            
            data = {
                'rows': [{
                    'cells': [
                        {'column': 'Note ID', 'value': note_id},
                        {'column': 'Transaction ID', 'value': transaction_id},
                        {'column': 'Discord User ID', 'value': str(user_id)},
                        {'column': 'Note', 'value': note},
                        {'column': 'Created At', 'value': timestamp}
                    ]
                }]
            }
            
            note_response = await self.coda_api_request('POST', notes_endpoint, data=data)
            
            return bool(note_response and 'items' in note_response)
            
        except Exception as e:
            logger.error(f"Error adding note to transaction {transaction_id}: {e}")
            return False
            
    async def get_transaction_stats(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get detailed transaction statistics for a user.
        
        Args:
            user_id: Discord user ID
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            
        Returns:
            Dictionary with various statistics about transactions
        """
        try:
            transactions = await self.get_transactions(user_id, start_date, end_date)
            
            if not transactions:
                return {
                    "transaction_count": 0,
                    "total_in": Decimal('0'),
                    "total_out": Decimal('0'),
                    "net_change": Decimal('0'),
                    "categories": {},
                    "types": {}
                }
            
            stats = {
                "transaction_count": len(transactions),
                "total_in": Decimal('0'),
                "total_out": Decimal('0'),
                "net_change": Decimal('0'),
                "categories": defaultdict(lambda: {"count": 0, "total": Decimal('0')}),
                "types": defaultdict(lambda: {"count": 0, "total": Decimal('0')}),
                "largest_transaction": None,
                "smallest_transaction": None,
                "average_transaction": Decimal('0'),
                "first_transaction_date": None,
                "last_transaction_date": None
            }
            
            # Process each transaction
            for trans in transactions:
                # Skip transactions with no amount
                if trans.amount is None:
                    continue
                    
                # Track incoming vs outgoing
                if trans.amount > 0:
                    stats["total_in"] += trans.amount
                else:
                    stats["total_out"] += abs(trans.amount)
                    
                # Net change
                stats["net_change"] += trans.amount
                
                # Track by category
                if trans.category:
                    cat_key = trans.category.value
                    stats["categories"][cat_key]["count"] += 1
                    stats["categories"][cat_key]["total"] += trans.amount
                
                # Track by type
                if trans.trans_type:
                    type_key = trans.trans_type.value
                    stats["types"][type_key]["count"] += 1
                    stats["types"][type_key]["total"] += trans.amount
                
                # Largest and smallest transactions
                if (stats["largest_transaction"] is None or 
                    abs(trans.amount) > abs(stats["largest_transaction"].amount)):
                    stats["largest_transaction"] = trans
                    
                if (stats["smallest_transaction"] is None or 
                    abs(trans.amount) < abs(stats["smallest_transaction"].amount)):
                    stats["smallest_transaction"] = trans
                    
                # Track dates
                created_at = None
                if trans.metadata and 'created_at' in trans.metadata:
                    try:
                        created_at = datetime.fromisoformat(
                            trans.metadata['created_at'].replace('Z', '+00:00')
                        )
                    except (ValueError, TypeError):
                        pass
                        
                if created_at:
                    if stats["first_transaction_date"] is None or created_at < stats["first_transaction_date"]:
                        stats["first_transaction_date"] = created_at
                        
                    if stats["last_transaction_date"] is None or created_at > stats["last_transaction_date"]:
                        stats["last_transaction_date"] = created_at
            
            # Calculate averages
            if stats["transaction_count"] > 0:
                stats["average_transaction"] = stats["net_change"] / stats["transaction_count"]
            
            # Find most common category and type
            if stats["categories"]:
                most_common_cat = max(stats["categories"].items(), key=lambda x: x[1]["count"])
                stats["most_common_category"] = {
                    "name": most_common_cat[0],
                    "count": most_common_cat[1]["count"],
                    "total": most_common_cat[1]["total"]
                }
            
            if stats["types"]:
                most_common_type = max(stats["types"].items(), key=lambda x: x[1]["count"])
                stats["most_common_type"] = {
                    "name": most_common_type[0],
                    "count": most_common_type[1]["count"],
                    "total": most_common_type[1]["total"]
                }
            
            # Convert defaultdicts to regular dicts for easier serialization
            stats["categories"] = dict(stats["categories"])
            stats["types"] = dict(stats["types"])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting transaction stats for user {user_id}: {e}")
            return {
                "error": str(e),
                "transaction_count": 0
            }
    
    async def search_transactions(
        self,
        user_id: int,
        search_term: str,
        search_fields: List[str] = ['description'],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[TransactionData]:
        """Search for transactions matching the given criteria.
        
        Args:
            user_id: Discord user ID
            search_term: Text to search for
            search_fields: Fields to search in (description, type, category, etc.)
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            limit: Maximum number of results to return
            
        Returns:
            List of matching transactions
        """
        try:
            # Get transactions for the user with specified date range
            transactions = await self.get_transactions(user_id, start_date, end_date, limit=limit)
            
            if not transactions:
                return []
            
            search_term = search_term.lower()
            matching_transactions = []
            
            # Function to check if a transaction field matches the search term
            def field_matches(trans, field):
                value = None
                
                if field == 'description':
                    value = trans.description
                elif field == 'type' and trans.trans_type:
                    value = trans.trans_type.value
                elif field == 'category' and trans.category:
                    value = trans.category.value
                elif field == 'transaction_id':
                    value = trans.transaction_id
                elif field == 'amount':
                    value = str(trans.amount)
                elif field == 'target_user_id':
                    value = str(trans.target_user_id) if trans.target_user_id else None
                elif field == 'session_id':
                    value = trans.session_id
                elif field == 'goal_id':
                    value = trans.goal_id
                
                if value is not None and search_term in str(value).lower():
                    return True
                
                return False
            
            # Check each transaction for matches
            for trans in transactions:
                if any(field_matches(trans, field) for field in search_fields):
                    matching_transactions.append(trans)
                    
                    # Respect the limit
                    if len(matching_transactions) >= limit:
                        break
            
            return matching_transactions
            
        except Exception as e:
            logger.error(f"Error searching transactions for user {user_id}: {e}")
            return []
            
    async def add_batch_transactions(
        self, 
        transactions: List[Tuple[int, str, Decimal, Optional[int], Optional[str], Optional[TransactionCategory], Optional[str]]]
    ) -> List[Optional[str]]:
        """Record multiple transactions in batch.
        
        Args:
            transactions: List of tuples (user_id, trans_type, amount, target_user_id, description, category, session_id)
        
        Returns:
            List of transaction IDs or None for failed transactions.
        """
        try:
            # Prepare batch data for Coda API
            batch_rows = []
            transaction_ids = []
            
            for transaction in transactions:
                user_id, trans_type, amount, target_user_id, description, category, session_id = transaction
                
                # Generate transaction ID
                transaction_id = str(uuid.uuid4())
                transaction_ids.append(transaction_id)
                
                # Generate timestamp
                timestamp = datetime.now(timezone.utc).isoformat()
                
                # Determine category if not provided
                if category is None:
                    category = self.get_default_category(trans_type)
                    
                # Prepare cells for this transaction
                cells = [
                    {'column': TRANS_ID_COLUMN, 'value': transaction_id},
                    {'column': TRANS_USER_ID_COLUMN, 'value': str(user_id)},
                    {'column': TRANS_TYPE_COLUMN, 'value': trans_type},
                    {'column': TRANS_AMOUNT_COLUMN, 'value': str(amount)},
                    {'column': TRANS_STATUS_COLUMN, 'value': TransactionStatus.COMPLETED.value},
                    {'column': TRANS_CREATED_AT_COLUMN, 'value': timestamp}
                ]
                
                # Add optional fields if provided
                if target_user_id:
                    cells.append({'column': TRANS_TARGET_USER_COLUMN, 'value': str(target_user_id)})
                    
                if description:
                    cells.append({'column': TRANS_DESC_COLUMN, 'value': description})
                    
                if category:
                    cells.append({'column': TRANS_CATEGORY_COLUMN, 'value': category.value})
                    
                if session_id:
                    cells.append({'column': TRANS_SESSION_ID_COLUMN, 'value': session_id})
                    
                # Add this row to the batch
                batch_rows.append({'cells': cells})
                
            # Send batch request to Coda API
            if batch_rows:
                endpoint = f'docs/{DOC_ID}/tables/{TRANSACTIONS_TABLE_ID}/rows'
                
                data = {
                    'rows': batch_rows
                }
                
                response = await self.coda_api_request('POST', endpoint, data=data)
                
                if not response or 'items' not in response:
                    # If batch request failed, fall back to individual requests
                    logger.warning("Batch transaction add failed, falling back to individual requests")
                    result_ids = []
                    for i, transaction in enumerate(transactions):
                        user_id, trans_type, amount, target_user_id, description, category, session_id = transaction
                        trans_id = await self.add_transaction(
                            user_id, trans_type, amount, target_user_id, description, TransactionStatus.COMPLETED, category, session_id
                        )
                        result_ids.append(trans_id)
                    return result_ids
                
                return transaction_ids
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error adding batch transactions: {e}")
            return [None] * len(transactions)
    
    async def process_payouts(
        self,
        payouts: List[Tuple[int, Decimal, str, Optional[TransactionCategory]]],
        batch_size: int = 10
    ) -> List[bool]:
        """Process multiple payouts efficiently in batches.
        
        Args:
            payouts: List of tuples (user_id, amount, description, category)
            batch_size: Number of payouts to process in each batch
            
        Returns:
            List of success flags for each payout
        """
        results = []
        
        # Process in batches to avoid overloading the API
        for i in range(0, len(payouts), batch_size):
            batch = payouts[i:i+batch_size]
            batch_results = []
            
            # First update all balances in this batch
            for user_id, amount, _, _ in batch:
                success = await self.update_balance(user_id, amount)
                batch_results.append(success)
            
            # Then record transactions for successful balance updates
            transaction_batch = []
            for j, (user_id, amount, description, category) in enumerate(batch):
                if batch_results[j]:
                    transaction_batch.append((
                        user_id, 
                        TransactionType.VC_PAYOUT.value, 
                        amount, 
                        None, 
                        description,
                        category or TransactionCategory.PAYOUT,
                        None
                    ))
            
            # Add transactions in batch
            if transaction_batch:
                await self.add_batch_transactions(transaction_batch)
            
            results.extend(batch_results)
            
            # Add a small delay between batches to avoid rate limiting
            if i + batch_size < len(payouts):
                await asyncio.sleep(1)
        
        return results
    
    # ====================== SESSION METHODS ======================
    
    async def get_active_session(self, user_id: int) -> Optional[SessionData]:
        """Get user's active gaming session if any."""
        try:
            # Query sessions table for active sessions
            endpoint = f'docs/{DOC_ID}/tables/{SESSIONS_TABLE_ID}/rows'
            params = {
                'query': f'Discord User ID = {user_id} AND End Time IS BLANK',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return None
                
            # Parse the active session
            session_data = response['items'][0]['values']
            
            session = SessionData(
                session_id=session_data.get('Session ID', ''),
                user_id=int(session_data.get('Discord User ID', '0')),
                start_time=datetime.fromisoformat(session_data.get('Start Time', '').replace('Z', '+00:00')),
                initial_balance=Decimal(session_data.get('Initial Balance', '0'))
            )
            
            return session
        except Exception as e:
            logger.error(f"Error getting active session for user {user_id}: {e}")
            return None
    
    async def start_gaming_session(self, user_id: int) -> Optional[SessionData]:
        """Start a new gaming session for user."""
        try:
            # Check if there's already an active session
            existing_session = await self.get_active_session(user_id)
            if existing_session:
                return existing_session
                
            # Get current balance as initial balance
            initial_balance = await self.get_balance(user_id)
            
            # Generate session ID and timestamp
            session_id = str(uuid.uuid4())
            start_time = datetime.now(timezone.utc)
            
            # Create session in database
            endpoint = f'docs/{DOC_ID}/tables/{SESSIONS_TABLE_ID}/rows'
            
            data = {
                'rows': [{
                    'cells': [
                        {'column': 'Session ID', 'value': session_id},
                        {'column': 'Discord User ID', 'value': str(user_id)},
                        {'column': 'Start Time', 'value': start_time.isoformat()},
                        {'column': 'Initial Balance', 'value': str(initial_balance)}
                    ]
                }]
            }
            
            response = await self.coda_api_request('POST', endpoint, data=data)
            
            if response and 'items' in response and len(response['items']) > 0:
                # Return session data
                return SessionData(
                    session_id=session_id,
                    user_id=user_id,
                    start_time=start_time,
                    initial_balance=initial_balance
                )
            else:
                logger.error(f"Failed to create gaming session for user {user_id}")
                return None
        except Exception as e:
            logger.error(f"Error starting gaming session for user {user_id}: {e}")
            return None
    
    async def end_gaming_session(self, user_id: int) -> Optional[SessionData]:
        """End user's active gaming session."""
        try:
            # Get active session
            session = await self.get_active_session(user_id)
            if not session:
                return None
                
            # Get current balance for final balance
            final_balance = await self.get_balance(user_id)
            
            # Calculate earnings
            total_earnings = final_balance - session.initial_balance
            
            # Set end time
            end_time = datetime.now(timezone.utc)
            
            # Update session in database
            endpoint = f'docs/{DOC_ID}/tables/{SESSIONS_TABLE_ID}/rows'
            params = {
                'query': f'Session ID = "{session.session_id}"',
                'useColumnNames': 'true'
            }
            
            session_response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not session_response or 'items' not in session_response or len(session_response['items']) == 0:
                logger.error(f"Session {session.session_id} not found in database")
                return None
                
            row_id = session_response['items'][0]['id']
            
            # Update session row
            update_endpoint = f'docs/{DOC_ID}/tables/{SESSIONS_TABLE_ID}/rows/{row_id}'
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'End Time', 'value': end_time.isoformat()},
                        {'column': 'Final Balance', 'value': str(final_balance)},
                        {'column': 'Total Earnings', 'value': str(total_earnings)}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Return updated session data
                session.end_time = end_time
                session.final_balance = final_balance
                session.total_earnings = total_earnings
                return session
            else:
                logger.error(f"Failed to update session {session.session_id}")
                return None
        except Exception as e:
            logger.error(f"Error ending gaming session for user {user_id}: {e}")
            return None
    
    # ====================== GOALS METHODS ======================
    
    async def set_savings_goal(self, user_id: int, target_amount: Decimal, description: str) -> Optional[GoalData]:
        """Create a new savings goal for user."""
        try:
            # Generate goal ID
            goal_id = str(uuid.uuid4())
            
            # Create goal in database
            endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows'
            
            data = {
                'rows': [{
                    'cells': [
                        {'column': 'Goal ID', 'value': goal_id},
                        {'column': 'Discord User ID', 'value': str(user_id)},
                        {'column': 'Target Amount', 'value': str(target_amount)},
                        {'column': 'Current Amount', 'value': '0'},
                        {'column': 'Description', 'value': description},
                        {'column': 'Status', 'value': GoalStatus.ACTIVE.value},
                        {'column': 'Created At', 'value': datetime.now(timezone.utc).isoformat()}
                    ]
                }]
            }
            
            response = await self.coda_api_request('POST', endpoint, data=data)
            
            if response and 'items' in response and len(response['items']) > 0:
                # Return goal data
                return GoalData(
                    goal_id=goal_id,
                    user_id=user_id,
                    target_amount=target_amount,
                    current_amount=Decimal('0'),
                    description=description,
                    status=GoalStatus.ACTIVE
                )
            else:
                logger.error(f"Failed to create savings goal for user {user_id}")
                return None
        except Exception as e:
            logger.error(f"Error creating savings goal for user {user_id}: {e}")
            return None
    
    async def get_user_goals(self, user_id: int, status: Optional[GoalStatus] = None) -> List[GoalData]:
        """Get user's savings goals with optional status filter."""
        try:
            # Build query
            query_parts = [f'Discord User ID = {user_id}']
            
            if status:
                query_parts.append(f'Status = "{status.value}"')
                
            query = ' AND '.join(query_parts)
            
            # Query goals table
            endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows'
            params = {
                'query': query,
                'useColumnNames': 'true',
                'sortBy': 'Created At',
                'sortDirection': 'desc'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response:
                return []
                
            # Convert response to GoalData objects
            goals = []
            for item in response['items']:
                values = item['values']
                
                # Parse goal status
                try:
                    status_value = values.get('Status', 'active')
                    status_enum = GoalStatus(status_value)
                except ValueError:
                    status_enum = GoalStatus.ACTIVE
                    
                # Create GoalData object
                goal = GoalData(
                    goal_id=values.get('Goal ID', ''),
                    user_id=int(values.get('Discord User ID', '0')),
                    target_amount=Decimal(values.get('Target Amount', '0')),
                    current_amount=Decimal(values.get('Current Amount', '0')),
                    description=values.get('Description', ''),
                    status=status_enum
                )
                
                goals.append(goal)
                
            return goals
        except Exception as e:
            logger.error(f"Error getting goals for user {user_id}: {e}")
            return []
    
    async def get_goal(self, goal_id: str) -> Optional[GoalData]:
        """Get goal by ID."""
        try:
            # Query goals table for the specific goal
            endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows'
            params = {
                'query': f'Goal ID = "{goal_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return None
                
            # Parse goal data
            values = response['items'][0]['values']
            
            # Parse goal status
            try:
                status_value = values.get('Status', 'active')
                status_enum = GoalStatus(status_value)
            except ValueError:
                status_enum = GoalStatus.ACTIVE
                
            # Create GoalData object
            goal = GoalData(
                goal_id=values.get('Goal ID', ''),
                user_id=int(values.get('Discord User ID', '0')),
                target_amount=Decimal(values.get('Target Amount', '0')),
                current_amount=Decimal(values.get('Current Amount', '0')),
                description=values.get('Description', ''),
                status=status_enum
            )
            
            return goal
        except Exception as e:
            logger.error(f"Error getting goal {goal_id}: {e}")
            return None
    
    async def update_goal_progress(self, goal_id: str, amount: Decimal) -> Optional[GoalData]:
        """Update progress towards a savings goal."""
        try:
            # Get current goal
            goal = await self.get_goal(goal_id)
            if not goal:
                logger.error(f"Goal {goal_id} not found")
                return None
                
            # Calculate new amount
            new_amount = goal.current_amount + amount
            
            # Update goal in database
            endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows'
            params = {
                'query': f'Goal ID = "{goal_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return None
                
            row_id = response['items'][0]['id']
            
            # Update goal row
            update_endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows/{row_id}'
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Current Amount', 'value': str(new_amount)}
                    ]
                }
            }
            
            # If goal is reached, update status
            if new_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
                data['row']['cells'].append({'column': 'Status', 'value': GoalStatus.COMPLETED.value})
                
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Return updated goal data
                if new_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
                    goal.status = GoalStatus.COMPLETED
                goal.current_amount = new_amount
                return goal
            else:
                return None
        except Exception as e:
            logger.error(f"Error updating goal {goal_id}: {e}")
            return None
    
    async def modify_goal(self, goal_id: str, description: str, status: GoalStatus) -> bool:
        """Modify a savings goal."""
        try:
            # Update goal in database
            endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows'
            params = {
                'query': f'Goal ID = "{goal_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return False
                
            row_id = response['items'][0]['id']
            
            # Update goal row
            update_endpoint = f'docs/{DOC_ID}/tables/{GOALS_TABLE_ID}/rows/{row_id}'
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Description', 'value': description},
                        {'column': 'Status', 'value': status.value}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            return bool(update_response)
        except Exception as e:
            logger.error(f"Error modifying goal {goal_id}: {e}")
            return False
    
    # ====================== LOAN METHODS ======================
    
    async def create_loan_application(self, user_id: int, amount: Decimal, purpose: str, 
                                    security_team: List[int], repayment_date: datetime) -> Optional[LoanData]:
        """Create a new cargo investment loan application."""
        try:
            # Generate loan ID
            loan_id = str(uuid.uuid4())
            
            # Format security team as comma-separated string
            security_team_str = ",".join(str(member_id) for member_id in security_team)
            
            # Create loan in database
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            
            data = {
                'rows': [{
                    'cells': [
                        {'column': 'Loan ID', 'value': loan_id},
                        {'column': 'Discord User ID', 'value': str(user_id)},
                        {'column': 'Amount', 'value': str(amount)},
                        {'column': 'Purpose', 'value': purpose},
                        {'column': 'Status', 'value': LoanStatus.PENDING.value},
                        {'column': 'Repayment Due Date', 'value': repayment_date.isoformat()},
                        {'column': 'Security Team', 'value': security_team_str},
                        {'column': 'Created At', 'value': datetime.now(timezone.utc).isoformat()}
                    ]
                }]
            }
            
            response = await self.coda_api_request('POST', endpoint, data=data)
            
            if response and 'items' in response and len(response['items']) > 0:
                # Return loan data
                return LoanData(
                    loan_id=loan_id,
                    user_id=user_id,
                    amount=amount,
                    purpose=purpose,
                    status=LoanStatus.PENDING,
                    repayment_due_date=repayment_date,
                    security_team=security_team,
                    created_at=datetime.now(timezone.utc)
                )
            else:
                logger.error(f"Failed to create loan application for user {user_id}")
                return None
        except Exception as e:
            logger.error(f"Error creating loan application for user {user_id}: {e}")
            return None
    
    async def get_user_loans(self, user_id: int, status: Optional[List[LoanStatus]] = None) -> List[LoanData]:
        """Get user's loans with optional status filter."""
        try:
            # Build query
            query_parts = [f'Discord User ID = {user_id}']
            
            if status:
                status_values = [f'"{s.value}"' for s in status]
                status_query = f'Status IN [{", ".join(status_values)}]'
                query_parts.append(status_query)
                
            query = ' AND '.join(query_parts)
            
            # Query loans table
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': query,
                'useColumnNames': 'true',
                'sortBy': 'Created At',
                'sortDirection': 'desc'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response:
                return []
                
            # Convert response to LoanData objects
            loans = []
            for item in response['items']:
                values = item['values']
                
                # Parse loan status
                try:
                    status_value = values.get('Status', 'pending')
                    status_enum = LoanStatus(status_value)
                except ValueError:
                    status_enum = LoanStatus.PENDING
                    
                # Parse security team
                security_team = []
                security_team_str = values.get('Security Team', '')
                if security_team_str:
                    for member_id in security_team_str.split(','):
                        member_id = member_id.strip()
                        if member_id and member_id.isdigit():
                            security_team.append(int(member_id))
                    
                # Parse dates
                created_at = datetime.fromisoformat(values.get('Created At', '').replace('Z', '+00:00')) if values.get('Created At') else datetime.now(timezone.utc)
                
                disbursement_date = None
                if values.get('Disbursement Date'):
                    disbursement_date = datetime.fromisoformat(values.get('Disbursement Date', '').replace('Z', '+00:00'))
                    
                repayment_due_date = None
                if values.get('Repayment Due Date'):
                    repayment_due_date = datetime.fromisoformat(values.get('Repayment Due Date', '').replace('Z', '+00:00'))
                    
                # Create LoanData object
                loan = LoanData(
                    loan_id=values.get('Loan ID', ''),
                    user_id=int(values.get('Discord User ID', '0')),
                    amount=Decimal(values.get('Amount', '0')),
                    purpose=values.get('Purpose', ''),
                    status=status_enum,
                    disbursement_date=disbursement_date,
                    repayment_due_date=repayment_due_date,
                    repaid_amount=Decimal(values.get('Repaid Amount', '0')),
                    interest_rate=Decimal(values.get('Interest Rate', '0.10')),
                    security_team=security_team,
                    security_payout_percentage=Decimal(values.get('Security Payout Percentage', '0.10')),
                    tax_waived=values.get('Tax Waived', 'false').lower() == 'true',
                    approved_by=int(values.get('Approved By', '0')) if values.get('Approved By') else None,
                    notes=values.get('Notes'),
                    created_at=created_at
                )
                
                loans.append(loan)
                
            return loans
        except Exception as e:
            logger.error(f"Error getting loans for user {user_id}: {e}")
            return []
    
    async def get_loan(self, loan_id: str) -> Optional[LoanData]:
        """Get loan by ID."""
        try:
            # Query loan table for the specific loan
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Loan ID = "{loan_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return None
                
            # Parse loan data
            values = response['items'][0]['values']
            
            # Parse loan status
            try:
                status_value = values.get('Status', 'pending')
                status_enum = LoanStatus(status_value)
            except ValueError:
                status_enum = LoanStatus.PENDING
                
            # Parse security team
            security_team = []
            security_team_str = values.get('Security Team', '')
            if security_team_str:
                for member_id in security_team_str.split(','):
                    member_id = member_id.strip()
                    if member_id and member_id.isdigit():
                        security_team.append(int(member_id))
                
            # Parse dates
            created_at = datetime.fromisoformat(values.get('Created At', '').replace('Z', '+00:00')) if values.get('Created At') else datetime.now(timezone.utc)
            
            disbursement_date = None
            if values.get('Disbursement Date'):
                disbursement_date = datetime.fromisoformat(values.get('Disbursement Date', '').replace('Z', '+00:00'))
                
            repayment_due_date = None
            if values.get('Repayment Due Date'):
                repayment_due_date = datetime.fromisoformat(values.get('Repayment Due Date', '').replace('Z', '+00:00'))
                
            # Create LoanData object
            loan = LoanData(
                loan_id=values.get('Loan ID', ''),
                user_id=int(values.get('Discord User ID', '0')),
                amount=Decimal(values.get('Amount', '0')),
                purpose=values.get('Purpose', ''),
                status=status_enum,
                disbursement_date=disbursement_date,
                repayment_due_date=repayment_due_date,
                repaid_amount=Decimal(values.get('Repaid Amount', '0')),
                interest_rate=Decimal(values.get('Interest Rate', '0.10')),
                security_team=security_team,
                security_payout_percentage=Decimal(values.get('Security Payout Percentage', '0.10')),
                tax_waived=values.get('Tax Waived', 'false').lower() == 'true',
                approved_by=int(values.get('Approved By', '0')) if values.get('Approved By') else None,
                notes=values.get('Notes'),
                created_at=created_at
            )
            
            return loan
        except Exception as e:
            logger.error(f"Error getting loan {loan_id}: {e}")
            return None
    
    async def repay_loan(self, loan_id: str, amount: Decimal) -> bool:
        """Repay part or all of a loan."""
        try:
            # Get loan
            loan = await self.get_loan(loan_id)
            if not loan:
                return False
                
            # Calculate new repaid amount
            new_repaid_amount = loan.repaid_amount + amount
            
            # Update loan in database
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Loan ID = "{loan_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return False
                
            row_id = response['items'][0]['id']
            
            # Prepare update data
            data = {
                'row': {
                    'cells': [
                        {'column': 'Repaid Amount', 'value': str(new_repaid_amount)}
                    ]
                }
            }
            
            # Calculate total due based on waivers
            total_due = loan.amount
            if not loan.tax_waived:
                total_due += loan.amount * loan.interest_rate  # Add interest
            if not loan.security_fee_waived:
                total_due += loan.amount * loan.security_payout_percentage  # Add security fee
                
            # If fully repaid, update status
            if new_repaid_amount >= total_due and loan.status in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
                data['row']['cells'].append({'column': 'Status', 'value': LoanStatus.COMPLETED.value})
                
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Process security team payouts if loan is fully repaid
                if new_repaid_amount >= total_due and loan.status in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
                    await self.process_security_team_payouts(loan)
                    
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Error repaying loan {loan_id}: {e}")
            return False
    
    async def process_security_team_payouts(self, loan: LoanData) -> bool:
        """Process payouts to security team for completed loan."""
        try:
            # If security fee is waived or there's no security team, skip payouts
            if loan.security_fee_waived or not loan.security_team:
                return True
                
            security_payout_total = loan.amount * loan.security_payout_percentage
            payout_per_member = security_payout_total / len(loan.security_team)
            
            for member_id in loan.security_team:
                # Update security member balance
                success = await self.update_balance(member_id, payout_per_member)
                
                if success:
                    # Add transaction record
                    await self.add_transaction(
                        member_id,
                        TransactionType.SECURITY_PAYOUT.value,
                        payout_per_member,
                        None,
                        f"Security team payout for cargo loan #{loan.loan_id}",
                        TransactionStatus.COMPLETED,
                        TransactionCategory.SECURITY,
                        None,
                        None,
                        loan.loan_id
                    )
                    
            return True
        except Exception as e:
            logger.error(f"Error processing security team payouts for loan {loan.loan_id}: {e}")
            return False
    
    async def approve_loan(self, loan_id: str, admin_id: int, disburse_now: bool, 
                          tax_waived: bool = False, security_fee_waived: bool = False,
                          notes: Optional[str] = None) -> bool:
        """Approve a loan application."""
        try:
            # Get loan
            loan = await self.get_loan(loan_id)
            if not loan or loan.status != LoanStatus.PENDING:
                return False
                
            # Update loan in database
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Loan ID = "{loan_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return False
                
            row_id = response['items'][0]['id']
            
            # Prepare update data
            current_time = datetime.now(timezone.utc)
            cells = [
                {'column': 'Status', 'value': LoanStatus.APPROVED.value},
                {'column': 'Approved By', 'value': str(admin_id)},
                {'column': 'Tax Waived', 'value': str(tax_waived).lower()},
                {'column': 'Security Fee Waived', 'value': str(security_fee_waived).lower()}
            ]
            
            if notes:
                cells.append({'column': 'Notes', 'value': notes})
            
            # If immediate disbursement
            if disburse_now:
                cells.append({'column': 'Status', 'value': LoanStatus.ACTIVE.value})
                cells.append({'column': 'Disbursement Date', 'value': current_time.isoformat()})
                
            data = {'row': {'cells': cells}}
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response and disburse_now:
                # Process loan disbursement
                await self.update_balance(loan.user_id, loan.amount)
                
                # Add transaction record
                await self.add_transaction(
                    loan.user_id,
                    TransactionType.LOAN_DISBURSEMENT.value,
                    loan.amount,
                    None,
                    f"Cargo investment loan: {loan.purpose}",
                    TransactionStatus.COMPLETED,
                    TransactionCategory.LOAN,
                    None,
                    None,
                    loan_id
                )
                
                # Notify user
                await self.notify_loan_disbursement(loan, tax_waived, security_fee_waived)
                
            return bool(update_response)
        except Exception as e:
            logger.error(f"Error approving loan {loan_id}: {e}")
            return False

    
    async def reject_loan(self, loan_id: str, admin_id: int, reason: str) -> bool:
        """Reject a loan application."""
        try:
            # Get loan
            loan = await self.get_loan(loan_id)
            if not loan or loan.status != LoanStatus.PENDING:
                return False
                
            # Update loan in database
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Loan ID = "{loan_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return False
                
            row_id = response['items'][0]['id']
            
            # Prepare update data
            data = {
                'row': {
                    'cells': [
                        {'column': 'Status', 'value': LoanStatus.REJECTED.value},
                        {'column': 'Notes', 'value': f"Rejected by admin: {reason}"}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Notify user
                await self.notify_loan_rejection(loan, reason)
                
            return bool(update_response)
        except Exception as e:
            logger.error(f"Error rejecting loan {loan_id}: {e}")
            return False
    
    async def create_cargo_incident(self, loan_id: str, user_id: int, description: str, 
                                  amount_lost: Decimal, location: str) -> Optional[CargoIncidentData]:
        """Create a cargo incident report."""
        try:
            # Generate incident ID
            incident_id = str(uuid.uuid4())
            
            # Create incident record (you'll need to create the incidents table in Coda)
            # For now, we'll just update the loan with notes
            loan = await self.get_loan(loan_id)
            if not loan:
                return None
                
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Loan ID = "{loan_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return None
                
            row_id = response['items'][0]['id']
            
            current_notes = loan.notes or ""
            updated_notes = f"{current_notes}\n\nINCIDENT REPORT ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): {description}\nLocation: {location}\nAmount Lost: {amount_lost} aUEC\nStatus: Under Review"
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Notes', 'value': updated_notes}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Create incident data object
                incident = CargoIncidentData(
                    incident_id=incident_id,
                    loan_id=loan_id,
                    user_id=user_id,
                    report_date=datetime.now(timezone.utc),
                    description=description,
                    amount_lost=amount_lost,
                    location=location
                )
                
                # Notify admins
                await self.notify_incident_report(incident, loan, await self.bot.fetch_user(user_id))
                
                return incident
            else:
                return None
        except Exception as e:
            logger.error(f"Error creating cargo incident for loan {loan_id}: {e}")
            return None
    
    # ====================== NOTIFICATION METHODS ======================
    
    async def notify_loan_application(self, loan: LoanData, user: discord.User) -> None:
        """Notify admins of a new loan application."""
        try:
            # Create notification embed
            embed = discord.Embed(
                title="New Cargo Investment Loan Application",
                description=f"User {user.display_name} has applied for a cargo investment loan.",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Amount",
                value=f"{loan.amount:,.2f} aUEC",
                inline=True
            )
            
            if loan.repayment_due_date:
                embed.add_field(
                    name="Repayment Due",
                    value=loan.repayment_due_date.strftime("%Y-%m-%d"),
                    inline=True
                )
                
            embed.add_field(
                name="Purpose",
                value=loan.purpose,
                inline=False
            )
            
            embed.set_footer(text=f"Loan ID: {loan.loan_id}")
            
            if user.avatar:
                embed.set_thumbnail(url=user.avatar.url)
                
            # Create review buttons
            view = LoanReviewView(self, loan.loan_id)
            
            # Determine the admin notification channel
            # TODO: Replace with your actual admin channel
            # admin_channel = self.bot.get_channel(ADMIN_CHANNEL_ID)
            # if admin_channel:
            #     await admin_channel.send(embed=embed, view=view)
            
            # For now, just log it
            logger.info(f"New loan application from {user.id}: {loan.amount} aUEC")
            
        except Exception as e:
            logger.error(f"Error sending loan application notification: {e}")
    
    async def notify_loan_disbursement(self, loan: LoanData, tax_waived: bool, security_fee_waived: bool) -> None:
        """Notify user when their loan is disbursed."""
        try:
            user = await self.bot.fetch_user(loan.user_id)
            if not user:
                return
                
            embed = discord.Embed(
                title="Cargo Investment Loan Approved",
                description="Your cargo investment loan has been approved and funds have been disbursed to your account.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Amount",
                value=f"{loan.amount:,.2f} aUEC",
                inline=True
            )
            
            if loan.repayment_due_date:
                embed.add_field(
                    name="Repayment Due",
                    value=loan.repayment_due_date.strftime("%Y-%m-%d"),
                    inline=True
                )
            
            # Calculate repayment amount based on waivers
            repayment_amount = loan.amount
            if not tax_waived:
                interest_amount = loan.amount * loan.interest_rate
                embed.add_field(
                    name="Interest (10%)",
                    value=f"{interest_amount:,.2f} aUEC",
                    inline=True
                )
                repayment_amount += interest_amount
                
            if not security_fee_waived:
                security_fee = loan.amount * loan.security_payout_percentage
                embed.add_field(
                    name="Security Fee (10%)",
                    value=f"{security_fee:,.2f} aUEC",
                    inline=True
                )
                repayment_amount += security_fee
                
            embed.add_field(
                name="Total Repayment Amount",
                value=f"{repayment_amount:,.2f} aUEC",
                inline=False
            )
            
            embed.add_field(
                name="Purpose",
                value=loan.purpose,
                inline=False
            )
            
            # Add fee waiver information
            fee_status = []
            if tax_waived:
                fee_status.append("Interest Waived")
            if security_fee_waived:
                fee_status.append("Security Fee Waived")
                
            if fee_status:
                embed.add_field(
                    name="Fee Status",
                    value=", ".join(fee_status),
                    inline=False
                )
            
            embed.set_footer(text=f"Loan ID: {loan.loan_id}")
            
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Cannot send DM to user {loan.user_id}")
                
        except Exception as e:
            logger.error(f"Error sending loan disbursement notification: {e}")
    
    async def notify_loan_rejection(self, loan: LoanData, reason: str) -> None:
        """Notify user when their loan is rejected."""
        try:
            user = await self.bot.fetch_user(loan.user_id)
            if not user:
                return
                
            embed = discord.Embed(
                title="Cargo Investment Loan Rejected",
                description="We regret to inform you that your cargo investment loan application has been rejected.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Amount Requested",
                value=f"{loan.amount:,.2f} aUEC",
                inline=True
            )
            
            embed.add_field(
                name="Reason for Rejection",
                value=reason,
                inline=False
            )
            
            embed.set_footer(text=f"Loan ID: {loan.loan_id}")
            
            try:
                await user.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Cannot send DM to user {loan.user_id}")
                
        except Exception as e:
            logger.error(f"Error sending loan rejection notification: {e}")
    
    async def notify_incident_report(self, incident: CargoIncidentData, loan: LoanData, user: discord.User) -> None:
        """Notify admins of a new incident report."""
        try:
            # Create notification embed
            embed = discord.Embed(
                title="New Cargo Incident Report",
                description=f"User {user.display_name} has reported a cargo incident.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Loan ID",
                value=loan.loan_id,
                inline=True
            )
            
            embed.add_field(
                name="Amount Lost",
                value=f"{incident.amount_lost:,.2f} aUEC",
                inline=True
            )
            
            embed.add_field(
                name="Location",
                value=incident.location,
                inline=True
            )
            
            embed.add_field(
                name="Description",
                value=incident.description,
                inline=False
            )
            
            embed.set_footer(text=f"Incident ID: {incident.incident_id}")
            
            if user.avatar:
                embed.set_thumbnail(url=user.avatar.url)
                
            # Determine the admin notification channel
            # TODO: Replace with your actual admin channel
            # admin_channel = self.bot.get_channel(ADMIN_CHANNEL_ID)
            # if admin_channel:
            #     await admin_channel.send(embed=embed)
            
            # For now, just log it
            logger.info(f"New incident report from {user.id} for loan {loan.loan_id}: {incident.amount_lost} aUEC lost")
            
        except Exception as e:
            logger.error(f"Error sending incident report notification: {e}")
    
    # ====================== ORGANIZATION BUDGET METHODS ======================
    
    async def get_org_budget(self) -> OrgBudgetData:
        """Get current organization budget."""
        # Check cache first
        current_time = time.time()
        if self.org_budget_cache and current_time - self.org_budget_cache_time < self.ORG_BUDGET_CACHE_TTL:
            return self.org_budget_cache
            
        try:
            # Query budget table
            endpoint = f'docs/{DOC_ID}/tables/{ORG_BUDGET_TABLE_ID}/rows'
            
            response = await self.coda_api_request('GET', endpoint)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                # Create default budget if not exists
                return await self.create_default_org_budget()
                
            # Parse budget data
            values = response['items'][0]['values']
            
            total_funds = Decimal(values.get('Total Funds', '0'))
            allocated_funds = Decimal(values.get('Allocated Funds', '0'))
            available_funds = total_funds - allocated_funds
            
            try:
                last_updated = datetime.fromisoformat(values.get('Last Updated', '').replace('Z', '+00:00'))
            except:
                last_updated = datetime.now(timezone.utc)
                
            budget = OrgBudgetData(
                total_funds=total_funds,
                allocated_funds=allocated_funds,
                available_funds=available_funds,
                last_updated=last_updated
            )
            
            # Update cache
            self.org_budget_cache = budget
            self.org_budget_cache_time = current_time
            
            return budget
            
        except Exception as e:
            logger.error(f"Error getting org budget: {e}")
            # Return default budget as fallback
            return OrgBudgetData(
                total_funds=Decimal('0'),
                allocated_funds=Decimal('0'),
                available_funds=Decimal('0'),
                last_updated=datetime.now(timezone.utc)
            )
    
    async def create_default_org_budget(self) -> OrgBudgetData:
        """Create a default organization budget if none exists."""
        try:
            current_time = datetime.now(timezone.utc)
            
            # Create budget row
            endpoint = f'docs/{DOC_ID}/tables/{ORG_BUDGET_TABLE_ID}/rows'
            
            data = {
                'rows': [{
                    'cells': [
                        {'column': 'Total Funds', 'value': '0'},
                        {'column': 'Allocated Funds', 'value': '0'},
                        {'column': 'Last Updated', 'value': current_time.isoformat()}
                    ]
                }]
            }
            
            await self.coda_api_request('POST', endpoint, data=data)
            
            # Return default budget
            budget = OrgBudgetData(
                total_funds=Decimal('0'),
                allocated_funds=Decimal('0'),
                available_funds=Decimal('0'),
                last_updated=current_time
            )
            
            # Update cache
            self.org_budget_cache = budget
            self.org_budget_cache_time = time.time()
            
            return budget
            
        except Exception as e:
            logger.error(f"Error creating default org budget: {e}")
            return OrgBudgetData(
                total_funds=Decimal('0'),
                allocated_funds=Decimal('0'),
                available_funds=Decimal('0'),
                last_updated=datetime.now(timezone.utc)
            )
    
    async def update_org_budget(self, total_funds_delta: Decimal = Decimal('0'), 
                              allocated_funds_delta: Decimal = Decimal('0')) -> bool:
        """Update organization budget."""
        try:
            # Get current budget
            current_budget = await self.get_org_budget()
            
            # Calculate new values
            new_total_funds = current_budget.total_funds + total_funds_delta
            new_allocated_funds = current_budget.allocated_funds + allocated_funds_delta
            
            # Validate new values
            if new_total_funds < 0 or new_allocated_funds < 0:
                logger.error("Invalid budget update: negative values not allowed")
                return False
                
            if new_allocated_funds > new_total_funds:
                logger.error("Invalid budget update: allocated funds cannot exceed total funds")
                return False
                
            # Query budget table to get row ID
            endpoint = f'docs/{DOC_ID}/tables/{ORG_BUDGET_TABLE_ID}/rows'
            
            response = await self.coda_api_request('GET', endpoint)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                # Create budget if not exists
                await self.create_default_org_budget()
                return await self.update_org_budget(total_funds_delta, allocated_funds_delta)
                
            row_id = response['items'][0]['id']
            
            # Update budget row
            update_endpoint = f'docs/{DOC_ID}/tables/{ORG_BUDGET_TABLE_ID}/rows/{row_id}'
            
            current_time = datetime.now(timezone.utc)
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Total Funds', 'value': str(new_total_funds)},
                        {'column': 'Allocated Funds', 'value': str(new_allocated_funds)},
                        {'column': 'Last Updated', 'value': current_time.isoformat()}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if update_response:
                # Update cache
                new_budget = OrgBudgetData(
                    total_funds=new_total_funds,
                    allocated_funds=new_allocated_funds,
                    available_funds=new_total_funds - new_allocated_funds,
                    last_updated=current_time
                )
                
                self.org_budget_cache = new_budget
                self.org_budget_cache_time = time.time()
                
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error updating org budget: {e}")
            return False
    
    async def process_org_donation(self, user_id: int, amount: Decimal, tax_waiver: bool) -> bool:
        """Process donation to organization."""
        try:
            # Deduct from user balance
            success = await self.update_balance(user_id, -amount)
            if not success:
                return False
                
            # Add transaction record
            await self.add_transaction(
                user_id,
                TransactionType.ORG_DONATION.value,
                -amount,
                None,
                "Donation to organization",
                TransactionStatus.COMPLETED,
                TransactionCategory.DONATION
            )
            
            # Add to org budget
            await self.update_org_budget(total_funds_delta=amount)
            
            # If tax waiver requested and amount sufficient, update user's tax status
            if tax_waiver and amount >= Decimal('5000000'):
                await self.update_user_tax_status(user_id, True)
                
            return True
            
        except Exception as e:
            logger.error(f"Error processing org donation from user {user_id}: {e}")
            return False
    
    async def update_user_tax_status(self, user_id: int, tax_waived: bool) -> bool:
        """Update user's tax waiver status for loans."""
        try:
            # This would typically be stored in your user preferences table
            # For now, we'll just log it
            logger.info(f"Updated tax status for user {user_id}: waived={tax_waived}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating tax status for user {user_id}: {e}")
            return False
            
    # ====================== SCHEDULED TASKS ======================
    
    @tasks.loop(hours=24)
    async def sync_usernames(self):
        """Sync Discord usernames with account records daily."""
        try:
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
            response = await self.coda_api_request('GET', endpoint)
            
            if response and 'items' in response:
                for item in response['items']:
                    user_id = int(item['values'].get('Discord User ID', '0'))
                    if user_id:
                        await self.sync_username(user_id)
                    await asyncio.sleep(1)  # Rate limiting
        except Exception as e:
            logger.error(f"Error in username sync task: {e}")

    @sync_usernames.before_loop
    async def before_sync_usernames(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()
        
    @tasks.loop(hours=12)
    async def check_loan_due_dates(self):
        """Check for overdue loans and send reminders."""
        try:
            # Get all active loans
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Status = "active"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response:
                return
                
            now = datetime.now(timezone.utc)
            
            for item in response['items']:
                try:
                    values = item.get('values', {})
                    loan_id = item['id']
                    user_id = int(values.get('Discord User ID', '0'))
                    due_date_str = values.get('Repayment Due Date')
                    
                    if not user_id or not due_date_str:
                        continue
                        
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
                    
                    # Calculate days remaining
                    days_remaining = (due_date - now).days
                    
                    # Send reminder for loans due soon or overdue
                    if days_remaining <= 3:
                        await self.send_loan_reminder(loan_id, user_id, days_remaining)
                        
                    # Mark loans as defaulted if significantly overdue
                    if days_remaining < -7:
                        await self.mark_loan_defaulted(loan_id, user_id)
                        
                except Exception as e:
                    logger.error(f"Error processing loan {item.get('id')}: {e}")
                    
                # Sleep briefly to avoid rate limits
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in loan due date check task: {e}")
            
    @check_loan_due_dates.before_loop
    async def before_check_loan_due_dates(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()
    
    # ====================== UTILITY METHODS ======================
    
    async def is_rate_limited(self, user_id: int) -> bool:
        """Check if user is rate limited."""
        current_time = datetime.now().timestamp()
        user_limits = self.rate_limits[user_id]
        
        # Reset counter if window has passed
        if current_time - user_limits["last_update"] > self.RATE_LIMIT_WINDOW:
            user_limits["count"] = 0
            user_limits["last_update"] = current_time
            
        user_limits["count"] += 1
        return user_limits["count"] > self.MAX_OPERATIONS

    async def sync_username(self, user_id: int) -> bool:
        """Sync Discord username to account record."""
        try:
            # Fetch user info from Discord
            user = await self.bot.fetch_user(user_id)
            if not user:
                return False
                
            # Query accounts table for the user
            endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows'
            params = {
                'query': f'Discord User ID = {user_id}',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                # User not found, skip update
                return False
                
            row_id = response['items'][0]['id']
            
            # Update username in the table
            update_endpoint = f'docs/{DOC_ID}/tables/{ACCOUNTS_TABLE_ID}/rows/{row_id}'
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Username', 'value': user.name}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            return bool(update_response)
        except Exception as e:
            logger.error(f"Error syncing username for user {user_id}: {e}")
            return False
    
    async def send_loan_reminder(self, loan_id: str, user_id: int, days_remaining: int) -> bool:
        """Send loan repayment reminder to user."""
        try:
            # Get loan details
            loan = await self.get_loan(loan_id)
            if not loan:
                return False
                
            # Try to fetch user
            user = await self.bot.fetch_user(user_id)
            if not user:
                logger.error(f"Could not fetch user {user_id} for loan reminder")
                return False
                
            # Create reminder embed
            if days_remaining > 0:
                title = f"🚢 Loan Repayment Due Soon"
                description = f"Your cargo investment loan repayment is due in {days_remaining} day(s)."
                color = discord.Color.gold()
            else:
                title = f"⚠️ Loan Repayment OVERDUE"
                description = f"Your cargo investment loan repayment is {abs(days_remaining)} day(s) overdue!"
                color = discord.Color.red()
                
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.now(timezone.utc)
            )
            
            embed.add_field(
                name="Amount Due",
                value=f"{(loan.amount - loan.repaid_amount):,.2f} aUEC",
                inline=True
            )
            
            if not loan.tax_waived:
                interest_amount = loan.amount * loan.interest_rate
                embed.add_field(
                    name="Interest (10%)",
                    value=f"{interest_amount:,.2f} aUEC",
                    inline=True
                )
            
            if loan.repayment_due_date:
                embed.add_field(
                    name="Due Date",
                    value=loan.repayment_due_date.strftime("%Y-%m-%d"),
                    inline=True
                )
                
            embed.add_field(
                name="Purpose",
                value=loan.purpose,
                inline=False
            )
            
            embed.set_footer(text=f"Loan ID: {loan.loan_id}")
            
            # Create button view for quick repayment
            view = LoanRepaymentReminderView(self, loan)
            
            # Send reminder DM
            try:
                await user.send(embed=embed, view=view)
                return True
            except discord.Forbidden:
                logger.warning(f"Cannot send DM to user {user_id}")
                return False
        except Exception as e:
            logger.error(f"Error sending loan reminder for loan {loan_id}: {e}")
            return False
    
    async def mark_loan_defaulted(self, loan_id: str, user_id: int) -> bool:
        """Mark loan as defaulted after grace period."""
        try:
            # Get loan details
            loan = await self.get_loan(loan_id)
            if not loan or loan.status != LoanStatus.ACTIVE:
                return False
                
            # Update loan status to defaulted
            endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
            params = {
                'query': f'Loan ID = "{loan_id}"',
                'useColumnNames': 'true'
            }
            
            response = await self.coda_api_request('GET', endpoint, params=params)
            
            if not response or 'items' not in response or len(response['items']) == 0:
                return False
                
            row_id = response['items'][0]['id']
            
            # Update loan row
            update_endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows/{row_id}'
            
            data = {
                'row': {
                    'cells': [
                        {'column': 'Status', 'value': LoanStatus.DEFAULTED.value},
                        {'column': 'Notes', 'value': f"Automatically marked as defaulted on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"}
                    ]
                }
            }
            
            update_response = await self.coda_api_request('PUT', update_endpoint, data=data)
            
            if not update_response:
                return False
                
            # Try to notify user
            try:
                user = await self.bot.fetch_user(user_id)
                if user:
                    embed = discord.Embed(
                        title="⚠️ Loan Default Notice",
                        description="Your cargo investment loan has been marked as defaulted due to non-payment.",
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    embed.add_field(
                        name="Loan ID",
                        value=loan_id,
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Amount",
                        value=f"{loan.amount:,.2f} aUEC",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Repaid",
                        value=f"{loan.repaid_amount:,.2f} aUEC",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Next Steps",
                        value="Please contact an organization officer to discuss repayment options.",
                        inline=False
                    )
                    
                    await user.send(embed=embed)
            except:
                # Continue even if notification fails
                pass
                
            return True
        except Exception as e:
            logger.error(f"Error marking loan {loan_id} as defaulted: {e}")
            return False
    
    def get_transaction_emoji(self, trans_type: TransactionType) -> str:
        """Get appropriate emoji for transaction type."""
        emoji_map = {
            TransactionType.DEPOSIT: "💵",
            TransactionType.WITHDRAW: "💳",
            TransactionType.TRANSFER_OUT: "↗️",
            TransactionType.TRANSFER_IN: "↙️",
            TransactionType.TRADE_PROFIT: "📈",
            TransactionType.MINING_PROFIT: "⛏️",
            TransactionType.MISSION_REWARD: "✨",
            TransactionType.BOUNTY_REWARD: "🎯",
            TransactionType.REFINERY_PROFIT: "⚗️",
            TransactionType.TRANSPORT_PROFIT: "🚀",
            TransactionType.VC_PAYOUT: "💰",
            TransactionType.LOAN_DISBURSEMENT: "💸",
            TransactionType.LOAN_REPAYMENT: "🔄",
            TransactionType.SECURITY_PAYOUT: "🛡️",
            TransactionType.ORG_DONATION: "🎁",
            TransactionType.PROJECT_FUNDING: "🏗️"
        }
        return emoji_map.get(trans_type, "💠")

    def get_category_emoji(self, category: TransactionCategory) -> str:
        """Get appropriate emoji for transaction category."""
        emoji_map = {
            TransactionCategory.TRADE: "💹",
            TransactionCategory.MINING: "⛏️",
            TransactionCategory.MISSION: "📋",
            TransactionCategory.TRANSPORT: "🚀",
            TransactionCategory.BOUNTY: "🎯",
            TransactionCategory.REFINERY: "⚗️",
            TransactionCategory.PERSONAL: "👤",
            TransactionCategory.PAYOUT: "💰",
            TransactionCategory.LOAN: "💸",
            TransactionCategory.SECURITY: "🛡️",
            TransactionCategory.DONATION: "🎁",
            TransactionCategory.PROJECT: "🏗️",
            TransactionCategory.OTHER: "📎"
        }
        return emoji_map.get(category, "📎")

    def get_status_emoji(self, status: TransactionStatus) -> str:
        """Get appropriate emoji for transaction status."""
        emoji_map = {
            TransactionStatus.COMPLETED: "✅",
            TransactionStatus.PENDING: "⏳",
            TransactionStatus.FAILED: "❌"
        }
        return emoji_map.get(status, "❔")

    def format_currency(self, amount: Decimal) -> str:
        """Format currency with color coding based on value."""
        if amount > 0:
            return f"```diff\n+{amount:,.2f} aUEC\n```"
        elif amount < 0:
            return f"```diff\n{amount:,.2f} aUEC\n```"
        return f"```{amount:,.2f} aUEC```"

    def create_balance_embed(self, user: discord.User, balance: Decimal) -> discord.Embed:
        """Create a standardized balance embed."""
        embed = discord.Embed(
            title=f"{user.display_name}'s Account Balance",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name="Current Balance",
            value=f"{balance:,.2f} aUEC",
            inline=False
        )
        embed.set_footer(text=f"Account ID: {user.id}")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        return embed

    def create_transaction_embed(
        self,
        transaction: TransactionData,
        user: discord.User,
        new_balance: Decimal
    ) -> discord.Embed:
        """Create a standardized transaction embed."""
        transaction_type = transaction.trans_type
        
        # Determine title and color based on transaction type
        if transaction_type == TransactionType.DEPOSIT:
            title = "Deposit Successful"
            color = discord.Color.green()
        elif transaction_type == TransactionType.WITHDRAW:
            title = "Withdrawal Successful"
            color = discord.Color.green()
        elif transaction_type == TransactionType.TRANSFER_OUT:
            title = "Transfer Successful"
            color = discord.Color.green()
        elif transaction_type == TransactionType.TRANSFER_IN:
            title = "Transfer Received"
            color = discord.Color.green()
        elif transaction_type == TransactionType.LOAN_DISBURSEMENT:
            title = "Loan Disbursed"
            color = discord.Color.blue()
        elif transaction_type == TransactionType.LOAN_REPAYMENT:
            title = "Loan Repayment"
            color = discord.Color.blue()
        else:
            title = f"{transaction_type.value.replace('_', ' ').title()}"
            color = discord.Color.green() if transaction.amount > 0 else discord.Color.red()
            
        status_emoji = self.get_status_emoji(transaction.status)
        
        embed = discord.Embed(
            title=f"{title}",
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Transaction Details
        embed.add_field(
            name="Amount",
            value=f"{transaction.amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value=f"{status_emoji} {transaction.status.value.title()}",
            inline=True
        )
        
        # Category if available
        if transaction.category:
            category_emoji = self.get_category_emoji(transaction.category)
            embed.add_field(
                name="Category",
                value=f"{category_emoji} {transaction.category.value.title()}",
                inline=True
            )
        
        # Description if available
        if transaction.description:
            embed.add_field(
                name="Description",
                value=transaction.description,
                inline=False
            )
        
        # New Balance
        embed.add_field(
            name="New Balance",
            value=f"{new_balance:,.2f} aUEC",
            inline=False
        )
        
        # Footer with transaction ID
        embed.set_footer(text=f"Transaction ID: {transaction.transaction_id}")
        
        # Set user avatar if available
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        return embed

    def create_session_summary_embed(self, session: SessionData, user: discord.User) -> discord.Embed:
        """Create a standardized session summary embed."""
        duration = session.end_time - session.start_time if session.end_time else None
        
        embed = discord.Embed(
            title="🎮 Gaming Session Summary",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Duration",
            value=str(duration).split('.')[0] if duration else "Session Active",
            inline=True
        )
        
        embed.add_field(
            name="Initial Balance",
            value=f"{session.initial_balance:,.2f} aUEC",
            inline=True
        )
        
        if session.final_balance is not None:
            embed.add_field(
                name="Final Balance",
                value=f"{session.final_balance:,.2f} aUEC",
                inline=True
            )
            
            embed.add_field(
                name="Total Earnings",
                value=f"{session.total_earnings:,.2f} aUEC",
                inline=True
            )
        
        if session.notes:
            embed.add_field(
                name="Session Notes",
                value=session.notes,
                inline=False
            )
        
        embed.set_footer(text=f"Session ID: {session.session_id}")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        return embed

    def create_goal_embed(self, goal: GoalData, user: discord.User) -> discord.Embed:
        """Create a standardized savings goal embed."""
        progress = (goal.current_amount / goal.target_amount) * 100 if goal.target_amount else 0
        progress_bar = self.create_progress_bar(progress)
        
        embed = discord.Embed(
            title="🎯 Savings Goal",
            description=goal.description,
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Target Amount",
            value=f"{goal.target_amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Current Amount",
            value=f"{goal.current_amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Progress",
            value=f"{progress:.1f}%\n{progress_bar}",
            inline=False
        )
        
        embed.set_footer(text=f"Goal ID: {goal.goal_id}")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        return embed

    def create_loan_embed(self, loan: LoanData) -> discord.Embed:
        """Create a standardized loan embed."""
        status_colors = {
            LoanStatus.PENDING: discord.Color.light_grey(),
            LoanStatus.APPROVED: discord.Color.green(),
            LoanStatus.ACTIVE: discord.Color.blue(),
            LoanStatus.COMPLETED: discord.Color.green(),
            LoanStatus.DEFAULTED: discord.Color.red(),
            LoanStatus.REJECTED: discord.Color.red()
        }
        
        status_emojis = {
            LoanStatus.PENDING: "⏳",
            LoanStatus.APPROVED: "✅",
            LoanStatus.ACTIVE: "💼",
            LoanStatus.COMPLETED: "🎉",
            LoanStatus.DEFAULTED: "❌",
            LoanStatus.REJECTED: "🚫"
        }
        
        try:
            color = status_colors.get(loan.status, discord.Color.blue())
        except:
            color = discord.Color.blue()
            
        emoji = status_emojis.get(loan.status, "📋")
        
        embed = discord.Embed(
            title=f"🚢 Cargo Investment Loan",
            description=loan.purpose,
            color=color,
            timestamp=loan.created_at
        )
        
        embed.add_field(
            name="Amount",
            value=f"{loan.amount:,.2f} aUEC",
            inline=True
        )
        
        embed.add_field(
            name="Status",
            value=f"{emoji} {loan.status.value.title()}",
            inline=True
        )
        
        if loan.repaid_amount > 0:
            repayment_progress = (loan.repaid_amount / loan.amount) * 100
            progress_bar = self.create_progress_bar(repayment_progress)
            
            embed.add_field(
                name="Repaid",
                value=f"{loan.repaid_amount:,.2f} aUEC ({repayment_progress:.1f}%)",
                inline=True
            )
            
            embed.add_field(
                name="Repayment Progress",
                value=progress_bar,
                inline=False
            )
        
        if loan.disbursement_date:
            embed.add_field(
                name="Disbursement Date",
                value=loan.disbursement_date.strftime("%Y-%m-%d %H:%M"),
                inline=True
            )
            
        if loan.repayment_due_date:
            embed.add_field(
                name="Due Date",
                value=loan.repayment_due_date.strftime("%Y-%m-%d %H:%M"),
                inline=True
            )
            
        if loan.tax_waived:
            embed.add_field(
                name="Tax Status",
                value="Waived",
                inline=True
            )
        elif loan.status in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
            interest_amount = loan.amount * loan.interest_rate
            embed.add_field(
                name="Interest (10%)",
                value=f"{interest_amount:,.2f} aUEC",
                inline=True
            )
            
        if loan.security_team and len(loan.security_team) > 0:
            security_team_str = ", ".join([f"<@{member_id}>" for member_id in loan.security_team])
            security_payout = loan.amount * loan.security_payout_percentage
            
            embed.add_field(
                name="Security Team",
                value=f"{security_team_str}\nPayout: {security_payout:,.2f} aUEC ({loan.security_payout_percentage*100:.0f}%)",
                inline=False
            )
            
        if loan.notes:
            embed.add_field(
                name="Notes",
                value=loan.notes,
                inline=False
            )
            
        embed.set_footer(text=f"Loan ID: {loan.loan_id}")
        
        return embed

    def create_progress_bar(self, percentage: float, length: int = 20) -> str:
        """Create a text-based progress bar."""
        filled = int((percentage / 100.0) * length)
        return f"[{'=' * filled}{'-' * (length - filled)}]"
    
    # ====================== COMMANDS ======================
    
    # Main Banking UI Command
    @app_commands.command(
        name='banking',
        description='Open the banking system interface'
    )
    async def banking(self, interaction: DiscordInteraction):
        """Open the main banking system UI."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            if await self.is_rate_limited(interaction.user.id):
                await interaction.followup.send(
                    "You are making too many requests. Please wait a moment.",
                    ephemeral=True
                )
                return
                
            # Create main banking view
            view = BankingHomeView(self)
            
            embed = discord.Embed(
                title="🏦 Banking System",
                description="Welcome to the organization banking system. Select an option below:",
                color=discord.Color.blue()
            )
            
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error opening banking UI: {e}")
            
            # Admin Commands
    @app_commands.command(
        name='admin_loan',
        description='Admin loan management'
    )
    @app_commands.describe(
        action='Admin action to perform',
        loan_id='ID of the loan',
        user_id='Target user ID (for some actions)',
        amount='Amount (for some actions)',
        note='Note or reason (for some actions)'
    )
    async def admin_loan(
        self, 
        interaction: DiscordInteraction, 
        action: Literal["approve", "reject", "extend", "default", "waive_interest", "waive_security_fee"], 
        loan_id: str,
        user_id: Optional[str] = None,
        amount: Optional[float] = None,
        note: Optional[str] = None
    ):
        """Admin loan management command."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check admin permissions
            # TODO: Replace with your actual permission check
            # is_admin = admin_role in interaction.user.roles
            is_admin = True
            
            if not is_admin:
                await interaction.followup.send(
                    "You don't have permission to use admin commands.",
                    ephemeral=True
                )
                return
                
            # Get the loan
            loan = await self.get_loan(loan_id)
            if not loan:
                await interaction.followup.send(
                    f"Loan with ID {loan_id} not found.",
                    ephemeral=True
                )
                return
                
            if action == "approve":
                if loan.status != LoanStatus.PENDING:
                    await interaction.followup.send(
                        "Only pending loans can be approved.",
                        ephemeral=True
                    )
                    return
                    
                # Default to immediate disbursement
                disburse_now = True
                tax_waived = False
                security_fee_waived = False
                
                if note:
                    note_lower = note.lower()
                    if "hold" in note_lower:
                        disburse_now = False
                    if "waive interest" in note_lower or "interest waive" in note_lower:
                        tax_waived = True
                    if "waive security" in note_lower or "security waive" in note_lower:
                        security_fee_waived = True
                        
                success = await self.approve_loan(
                    loan_id,
                    interaction.user.id,
                    disburse_now,
                    tax_waived,
                    security_fee_waived,
                    note
                )
                
                if success:
                    status_text = "approved and funds disbursed" if disburse_now else "approved (funds on hold)"
                    waivers = []
                    if tax_waived:
                        waivers.append("interest waived")
                    if security_fee_waived:
                        waivers.append("security fee waived")
                        
                    waiver_text = f" with {' and '.join(waivers)}" if waivers else ""
                    
                    await interaction.followup.send(
                        f"Loan {loan_id} has been {status_text}{waiver_text}.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Failed to approve loan. Please check the loan ID and try again.",
                        ephemeral=True
                    )
                        
            elif action == "reject":
                if loan.status != LoanStatus.PENDING:
                    await interaction.followup.send(
                        "Only pending loans can be rejected.",
                        ephemeral=True
                    )
                    return
                    
                if not note:
                    await interaction.followup.send(
                        "A rejection reason is required.",
                        ephemeral=True
                    )
                    return
                    
                success = await self.reject_loan(
                    loan_id,
                    interaction.user.id,
                    note
                )
                
                if success:
                    await interaction.followup.send(
                        f"Loan {loan_id} has been rejected.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Failed to reject loan. Please check the loan ID and try again.",
                        ephemeral=True
                    )
                        
            elif action == "extend":
                if loan.status not in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
                    await interaction.followup.send(
                        "Only active loans can be extended.",
                        ephemeral=True
                    )
                    return
                    
                if not amount:
                    await interaction.followup.send(
                        "Extension days amount is required.",
                        ephemeral=True
                    )
                    return
                    
                # Calculate new due date
                days_extension = int(amount)
                if days_extension <= 0:
                    await interaction.followup.send(
                        "Extension days must be positive.",
                        ephemeral=True
                    )
                    return
                    
                if not loan.repayment_due_date:
                    await interaction.followup.send(
                        "Loan does not have a due date to extend.",
                        ephemeral=True
                    )
                    return
                    
                new_due_date = loan.repayment_due_date + timedelta(days=days_extension)
                
                # Update loan due date
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
                params = {
                    'query': f'Loan ID = "{loan_id}"',
                    'useColumnNames': 'true'
                }
                
                response = await self.coda_api_request('GET', endpoint, params=params)
                
                if not response or 'items' not in response or len(response['items']) == 0:
                    await interaction.followup.send(
                        "Failed to find loan. Please check the loan ID.",
                        ephemeral=True
                    )
                    return
                    
                row_id = response['items'][0]['id']
                
                data = {
                    'row': {
                        'cells': [
                            {'column': 'Repayment Due Date', 'value': new_due_date.isoformat()}
                        ]
                    }
                }
                
                if note:
                    data['row']['cells'].append({
                        'column': 'Notes', 
                        'value': f"{loan.notes or ''}\n\nExtended by {days_extension} days: {note}"
                    })
                    
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows/{row_id}'
                response = await self.coda_api_request('PUT', endpoint, data=data)
                
                if response:
                    await interaction.followup.send(
                        f"Loan {loan_id} due date extended by {days_extension} days to {new_due_date.strftime('%Y-%m-%d')}.",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "Failed to extend loan due date. Please try again later.",
                        ephemeral=True
                    )
                        
            elif action == "default":
                if loan.status not in [LoanStatus.ACTIVE, LoanStatus.APPROVED]:
                    await interaction.followup.send(
                        "Only active loans can be marked as defaulted.",
                        ephemeral=True
                    )
                    return
                    
                # Mark loan as defaulted
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
                params = {
                    'query': f'Loan ID = "{loan_id}"',
                    'useColumnNames': 'true'
                }
                
                response = await self.coda_api_request('GET', endpoint, params=params)
                
                if not response or 'items' not in response or len(response['items']) == 0:
                    await interaction.followup.send(
                        "Failed to find loan. Please check the loan ID.",
                        ephemeral=True
                    )
                    return
                    
                row_id = response['items'][0]['id']
                
                data = {
                    'row': {
                        'cells': [
                            {'column': 'Status', 'value': LoanStatus.DEFAULTED.value}
                        ]
                    }
                }
                
                if note:
                    data['row']['cells'].append({
                        'column': 'Notes', 
                        'value': f"{loan.notes or ''}\n\nMarked as defaulted by admin: {note}"
                    })
                    
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows/{row_id}'
                response = await self.coda_api_request('PUT', endpoint, data=data)
                
                if response:
                    await interaction.followup.send(
                        f"Loan {loan_id} has been marked as defaulted.",
                        ephemeral=True
                    )
                    
                    # Notify user
                    try:
                        user = await self.bot.fetch_user(loan.user_id)
                        if user:
                            embed = discord.Embed(
                                title="⚠️ Loan Default Notice",
                                description="Your cargo investment loan has been marked as defaulted.",
                                color=discord.Color.red(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            
                            embed.add_field(
                                name="Loan ID",
                                value=loan_id,
                                inline=True
                            )
                            
                            embed.add_field(
                                name="Next Steps",
                                value="Please contact an organization officer to discuss this matter.",
                                inline=False
                            )
                            
                            if note:
                                embed.add_field(
                                    name="Reason",
                                    value=note,
                                    inline=False
                                )
                                
                            await user.send(embed=embed)
                    except:
                        # Continue even if notification fails
                        pass
                else:
                    await interaction.followup.send(
                        "Failed to mark loan as defaulted. Please try again later.",
                        ephemeral=True
                    )
                    
            elif action == "waive_interest":
                if loan.status not in [LoanStatus.APPROVED, LoanStatus.ACTIVE]:
                    await interaction.followup.send(
                        "Can only waive interest for approved or active loans.",
                        ephemeral=True
                    )
                    return
                    
                # Update loan tax_waived field
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
                params = {
                    'query': f'Loan ID = "{loan_id}"',
                    'useColumnNames': 'true'
                }
                
                response = await self.coda_api_request('GET', endpoint, params=params)
                
                if not response or 'items' not in response or len(response['items']) == 0:
                    await interaction.followup.send(
                        "Failed to find loan. Please check the loan ID.",
                        ephemeral=True
                    )
                    return
                    
                row_id = response['items'][0]['id']
                
                data = {
                    'row': {
                        'cells': [
                            {'column': 'Tax Waived', 'value': 'true'}
                        ]
                    }
                }
                
                if note:
                    data['row']['cells'].append({
                        'column': 'Notes', 
                        'value': f"{loan.notes or ''}\n\nInterest waived: {note}"
                    })
                    
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows/{row_id}'
                response = await self.coda_api_request('PUT', endpoint, data=data)
                
                if response:
                    await interaction.followup.send(
                        f"Interest has been waived for loan {loan_id}.",
                        ephemeral=True
                    )
                    
                    # Notify user
                    try:
                        user = await self.bot.fetch_user(loan.user_id)
                        if user:
                            embed = discord.Embed(
                                title="Loan Interest Waived",
                                description="The interest on your cargo investment loan has been waived!",
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            
                            embed.add_field(
                                name="Loan ID",
                                value=loan_id,
                                inline=True
                            )
                            
                            embed.add_field(
                                name="Amount Saved",
                                value=f"{(loan.amount * loan.interest_rate):,.2f} aUEC",
                                inline=True
                            )
                            
                            if note:
                                embed.add_field(
                                    name="Note",
                                    value=note,
                                    inline=False
                                )
                                
                            await user.send(embed=embed)
                    except:
                        # Continue even if notification fails
                        pass
                else:
                    await interaction.followup.send(
                        "Failed to waive interest. Please try again later.",
                        ephemeral=True
                    )
                    
            elif action == "waive_security_fee":
                if loan.status not in [LoanStatus.APPROVED, LoanStatus.ACTIVE]:
                    await interaction.followup.send(
                        "Can only waive security fee for approved or active loans.",
                        ephemeral=True
                    )
                    return
                    
                # Update loan security_fee_waived field
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows'
                params = {
                    'query': f'Loan ID = "{loan_id}"',
                    'useColumnNames': 'true'
                }
                
                response = await self.coda_api_request('GET', endpoint, params=params)
                
                if not response or 'items' not in response or len(response['items']) == 0:
                    await interaction.followup.send(
                        "Failed to find loan. Please check the loan ID.",
                        ephemeral=True
                    )
                    return
                    
                row_id = response['items'][0]['id']
                
                data = {
                    'row': {
                        'cells': [
                            {'column': 'Security Fee Waived', 'value': 'true'}
                        ]
                    }
                }
                
                if note:
                    data['row']['cells'].append({
                        'column': 'Notes', 
                        'value': f"{loan.notes or ''}\n\nSecurity fee waived: {note}"
                    })
                    
                endpoint = f'docs/{DOC_ID}/tables/{LOANS_TABLE_ID}/rows/{row_id}'
                response = await self.coda_api_request('PUT', endpoint, data=data)
                
                if response:
                    await interaction.followup.send(
                        f"Security fee has been waived for loan {loan_id}.",
                        ephemeral=True
                    )
                    
                    # Notify user
                    try:
                        user = await self.bot.fetch_user(loan.user_id)
                        if user:
                            embed = discord.Embed(
                                title="Loan Security Fee Waived",
                                description="The security fee on your cargo investment loan has been waived!",
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            
                            embed.add_field(
                                name="Loan ID",
                                value=loan_id,
                                inline=True
                            )
                            
                            embed.add_field(
                                name="Amount Saved",
                                value=f"{(loan.amount * loan.security_payout_percentage):,.2f} aUEC",
                                inline=True
                            )
                            
                            if note:
                                embed.add_field(
                                    name="Note",
                                    value=note,
                                    inline=False
                                )
                                
                            await user.send(embed=embed)
                    except:
                        # Continue even if notification fails
                        pass
                else:
                    await interaction.followup.send(
                        "Failed to waive security fee. Please try again later.",
                        ephemeral=True
                    )
                    
            else:
                await interaction.followup.send(
                    f"Unknown action: {action}",
                    ephemeral=True
                )
                    
        except Exception as e:
            logger.error(f"Error in admin loan command: {e}")
            await interaction.followup.send(
                "An error occurred while processing the admin loan command.",
                ephemeral=True
            )
    
    @app_commands.command(
        name='admin_budget',
        description='Manage organization budget'
    )
    @app_commands.describe(
        action='Budget action to perform',
        amount='Amount for adjustment',
        reason='Reason for budget change'
    )
    async def admin_budget(
        self,
        interaction: DiscordInteraction,
        action: Literal["view", "add_funds", "allocate", "deallocate"],
        amount: Optional[float] = None,
        reason: Optional[str] = None
    ):
        """Admin organization budget command."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Check admin permissions
            # TODO: Replace with your actual permission check
            # is_admin = admin_role in interaction.user.roles
            is_admin = True
            
            if not is_admin:
                await interaction.followup.send(
                    "You don't have permission to use admin commands.",
                    ephemeral=True
                )
                return
                
            if action == "view":
                # Get current budget
                budget = await self.get_org_budget()
                
                embed = discord.Embed(
                    title="Organization Budget",
                    color=discord.Color.blue(),
                    timestamp=budget.last_updated
                )
                
                embed.add_field(
                    name="Total Funds",
                    value=f"{budget.total_funds:,.2f} aUEC",
                    inline=True
                )
                
                embed.add_field(
                    name="Allocated Funds",
                    value=f"{budget.allocated_funds:,.2f} aUEC",
                    inline=True
                )
                
                embed.add_field(
                    name="Available Funds",
                    value=f"{budget.available_funds:,.2f} aUEC",
                    inline=True
                )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
            elif action in ["add_funds", "allocate", "deallocate"]:
                if amount is None:
                    await interaction.followup.send(
                        "Amount is required for budget adjustments.",
                        ephemeral=True
                    )
                    return
                    
                amount_decimal = Decimal(str(amount))
                if amount_decimal <= 0:
                    await interaction.followup.send(
                        "Amount must be positive.",
                        ephemeral=True
                    )
                    return
                    
                success = False
                if action == "add_funds":
                    # Add to total funds
                    success = await self.update_org_budget(total_funds_delta=amount_decimal)
                    description = f"Added {amount_decimal:,.2f} aUEC to organization funds"
                elif action == "allocate":
                    # Increase allocated funds
                    success = await self.update_org_budget(allocated_funds_delta=amount_decimal)
                    description = f"Allocated {amount_decimal:,.2f} aUEC from available funds"
                else:  # deallocate
                    # Decrease allocated funds
                    success = await self.update_org_budget(allocated_funds_delta=-amount_decimal)
                    description = f"Deallocated {amount_decimal:,.2f} aUEC back to available funds"
                    
                if success:
                    # Get updated budget
                    budget = await self.get_org_budget()
                    
                    embed = discord.Embed(
                        title="Budget Updated",
                        description=description,
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    embed.add_field(
                        name="Total Funds",
                        value=f"{budget.total_funds:,.2f} aUEC",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Allocated Funds",
                        value=f"{budget.allocated_funds:,.2f} aUEC",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="Available Funds",
                        value=f"{budget.available_funds:,.2f} aUEC",
                        inline=True
                    )
                    
                    if reason:
                        embed.add_field(
                            name="Reason",
                            value=reason,
                            inline=False
                        )
                        
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "Failed to update budget. Ensure there are sufficient funds for the operation.",
                        ephemeral=True
                    )
                    
            else:
                await interaction.followup.send(
                    f"Unknown action: {action}",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in admin budget command: {e}")
            await interaction.followup.send(
                "An error occurred while processing the admin budget command.",
                ephemeral=True
            )
            
    @app_commands.command(
        name='donate',
        description='Donate to the organization'
    )
    @app_commands.describe(
        amount='Amount to donate',
        tax_waiver='Request tax waiver for future loans (requires 5M+ donation)'
    )
    async def donate(
        self,
        interaction: DiscordInteraction,
        amount: float,
        tax_waiver: bool = False
    ):
        """Donate to organization command."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                await interaction.followup.send(
                    "Donation amount must be positive.",
                    ephemeral=True
                )
                return
                
            # If requesting tax waiver, check minimum amount
            if tax_waiver and amount_decimal < Decimal('5000000'):
                await interaction.followup.send(
                    "Tax waiver requires a minimum donation of 5,000,000 aUEC.",
                    ephemeral=True
                )
                return
                
            # Check balance
            current_balance = await self.get_balance(interaction.user.id)
            if current_balance < amount_decimal:
                await interaction.followup.send(
                    f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                    ephemeral=True
                )
                return
                
            # Process donation
            success = await self.process_org_donation(
                interaction.user.id,
                amount_decimal,
                tax_waiver
            )
            
            if success:
                new_balance = await self.get_balance(interaction.user.id)
                
                embed = discord.Embed(
                    title="Donation Successful",
                    description=f"Thank you for your donation of {amount_decimal:,.2f} aUEC to the organization!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="New Balance",
                    value=f"{new_balance:,.2f} aUEC",
                    inline=True
                )
                
                if tax_waiver and amount_decimal >= Decimal('5000000'):
                    embed.add_field(
                        name="Tax Status",
                        value="Your donations have qualified you for tax-free cargo loans!",
                        inline=False
                    )
                    
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Notify admins of large donations
                if amount_decimal >= Decimal('1000000'):
                    # TODO: Implement admin notification
                    pass
                    
            else:
                await interaction.followup.send(
                    "Failed to process donation. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error processing donation: {e}")
            await interaction.followup.send(
                "An error occurred while processing your donation.",
                ephemeral=True
            )
            
    @app_commands.command(
        name='transaction',
        description='Perform banking transactions'
    )
    @app_commands.describe(
        action='Type of transaction to perform',
        amount='Amount to process',
        description='Optional description',
        user='User to transfer funds to (for transfers only)'
    )
    @app_commands.choices(action=[
        app_commands.Choice(name='Deposit', value='deposit'),
        app_commands.Choice(name='Withdraw', value='withdraw'),
        app_commands.Choice(name='Transfer', value='transfer')
    ])
    async def banking_transaction(
        self, 
        interaction: DiscordInteraction,
        action: str,
        amount: float,
        description: Optional[str] = None,
        user: Optional[discord.User] = None
    ):
        """Perform banking transactions directly."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                await interaction.followup.send(
                    "Amount must be positive.",
                    ephemeral=True
                )
                return
                
            if action == 'deposit':
                # Process deposit
                success = await self.update_balance(interaction.user.id, amount_decimal)
                
                if success:
                    # Record transaction
                    await self.add_transaction(
                        interaction.user.id,
                        TransactionType.DEPOSIT.value,
                        amount_decimal,
                        None,
                        description
                    )
                    
                    # Get new balance
                    new_balance = await self.get_balance(interaction.user.id)
                    
                    # Create response embed
                    embed = discord.Embed(
                        title="Deposit Successful",
                        description=f"Successfully deposited {amount_decimal:,.2f} aUEC to your account.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    embed.add_field(
                        name="New Balance",
                        value=f"{new_balance:,.2f} aUEC",
                        inline=True
                    )
                    
                    if description:
                        embed.add_field(
                            name="Description",
                            value=description,
                            inline=False
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "Failed to process deposit. Please try again later.",
                        ephemeral=True
                    )
                    
            elif action == 'withdraw':
                # Check balance
                current_balance = await self.get_balance(interaction.user.id)
                if current_balance < amount_decimal:
                    await interaction.followup.send(
                        f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                        ephemeral=True
                    )
                    return
                    
                # Process withdrawal
                success = await self.update_balance(interaction.user.id, -amount_decimal)
                
                if success:
                    # Record transaction
                    await self.add_transaction(
                        interaction.user.id,
                        TransactionType.WITHDRAW.value,
                        -amount_decimal,
                        None,
                        description
                    )
                    
                    # Get new balance
                    new_balance = await self.get_balance(interaction.user.id)
                    
                    # Create response embed
                    embed = discord.Embed(
                        title="Withdrawal Successful",
                        description=f"Successfully withdrew {amount_decimal:,.2f} aUEC from your account.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    embed.add_field(
                        name="New Balance",
                        value=f"{new_balance:,.2f} aUEC",
                        inline=True
                    )
                    
                    if description:
                        embed.add_field(
                            name="Description",
                            value=description,
                            inline=False
                        )
                    
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send(
                        "Failed to process withdrawal. Please try again later.",
                        ephemeral=True
                    )
                    
            elif action == 'transfer':
                if not user:
                    await interaction.followup.send(
                        "You must specify a user to transfer funds to.",
                        ephemeral=True
                    )
                    return
                    
                if user.id == interaction.user.id:
                    await interaction.followup.send(
                        "You cannot transfer funds to yourself.",
                        ephemeral=True
                    )
                    return
                    
                # Check balance
                current_balance = await self.get_balance(interaction.user.id)
                if current_balance < amount_decimal:
                    await interaction.followup.send(
                        f"Insufficient funds. Your current balance is {current_balance:,.2f} aUEC",
                        ephemeral=True
                    )
                    return
                    
                # Process transfer - sender side
                sender_success = await self.update_balance(interaction.user.id, -amount_decimal)
                if not sender_success:
                    await interaction.followup.send(
                        "Failed to process transfer. Please try again later.",
                        ephemeral=True
                    )
                    return
                    
                # Process transfer - recipient side
                recipient_success = await self.update_balance(user.id, amount_decimal)
                if not recipient_success:
                    # Rollback sender transaction if recipient fails
                    await self.update_balance(interaction.user.id, amount_decimal)
                    await interaction.followup.send(
                        "Failed to complete transfer to recipient. Your account has not been charged.",
                        ephemeral=True
                    )
                    return
                    
                # Record transactions
                await self.add_transaction(
                    interaction.user.id,
                    TransactionType.TRANSFER_OUT.value,
                    -amount_decimal,
                    user.id,
                    description
                )
                
                await self.add_transaction(
                    user.id,
                    TransactionType.TRANSFER_IN.value,
                    amount_decimal,
                    interaction.user.id,
                    description
                )
                
                # Get new balance
                new_balance = await self.get_balance(interaction.user.id)
                
                # Create response embed
                embed = discord.Embed(
                    title="Transfer Successful",
                    description=f"Successfully transferred {amount_decimal:,.2f} aUEC to {user.display_name}.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="Recipient",
                    value=f"{user.mention} ({user.id})",
                    inline=True
                )
                
                embed.add_field(
                    name="New Balance",
                    value=f"{new_balance:,.2f} aUEC",
                    inline=True
                )
                
                if description:
                    embed.add_field(
                        name="Description",
                        value=description,
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Notify recipient
                try:
                    recipient_embed = discord.Embed(
                        title="Transfer Received",
                        description=f"You have received {amount_decimal:,.2f} aUEC from {interaction.user.display_name}.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    recipient_embed.add_field(
                        name="Sender",
                        value=f"{interaction.user.mention} ({interaction.user.id})",
                        inline=True
                    )
                    
                    recipient_balance = await self.get_balance(user.id)
                    recipient_embed.add_field(
                        name="New Balance",
                        value=f"{recipient_balance:,.2f} aUEC",
                        inline=True
                    )
                    
                    if description:
                        recipient_embed.add_field(
                            name="Description",
                            value=description,
                            inline=False
                        )
                        
                    await user.send(embed=recipient_embed)
                except:
                    logger.warning(f"Could not send transfer notification to user {user.id}")
        
        except Exception as e:
            logger.error(f"Error processing transaction: {e}")
            await interaction.followup.send(
                "An error occurred while processing your transaction.",
                ephemeral=True
            )
            
    @app_commands.command(
        name='record-profit',
        description='Record profits from various activities'
    )
    @app_commands.describe(
        type='Type of profit to record',
        amount='Amount of profit',
        description='Description of the profit source'
    )
    @app_commands.choices(type=[
        app_commands.Choice(name='Trade', value='trade'),
        app_commands.Choice(name='Mining', value='mining'),
        app_commands.Choice(name='Mission', value='mission'),
        app_commands.Choice(name='Bounty', value='bounty'),
        app_commands.Choice(name='Refinery', value='refinery'),
        app_commands.Choice(name='Transport', value='transport')
    ])
    async def record_profit(
        self,
        interaction: DiscordInteraction,
        type: str,
        amount: float,
        description: Optional[str] = None
    ):
        """Record profits from various activities."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                await interaction.followup.send(
                    "Profit amount must be positive.",
                    ephemeral=True
                )
                return
            
            # Map profit type to transaction type and category
            type_mapping = {
                'trade': (TransactionType.TRADE_PROFIT, TransactionCategory.TRADE),
                'mining': (TransactionType.MINING_PROFIT, TransactionCategory.MINING),
                'mission': (TransactionType.MISSION_REWARD, TransactionCategory.MISSION),
                'bounty': (TransactionType.BOUNTY_REWARD, TransactionCategory.BOUNTY),
                'refinery': (TransactionType.REFINERY_PROFIT, TransactionCategory.REFINERY),
                'transport': (TransactionType.TRANSPORT_PROFIT, TransactionCategory.TRANSPORT)
            }
            
            trans_type, category = type_mapping.get(type, (TransactionType.DEPOSIT, TransactionCategory.OTHER))
            
            # Get active session if any
            session = await self.get_active_session(interaction.user.id)
            session_id = session.session_id if session else None
            
            # Add to balance
            success = await self.update_balance(interaction.user.id, amount_decimal)
            
            if success:
                # Record transaction
                await self.add_transaction(
                    interaction.user.id,
                    trans_type.value,
                    amount_decimal,
                    None,
                    description,
                    TransactionStatus.COMPLETED,
                    category,
                    session_id
                )
                
                # Get new balance
                new_balance = await self.get_balance(interaction.user.id)
                
                # Create response embed
                category_emoji = self.get_category_emoji(category)
                
                embed = discord.Embed(
                    title=f"{category_emoji} {type.title()} Profit Recorded",
                    description=f"Successfully recorded {amount_decimal:,.2f} aUEC profit from {type}.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                embed.add_field(
                    name="New Balance",
                    value=f"{new_balance:,.2f} aUEC",
                    inline=True
                )
                
                if session:
                    embed.add_field(
                        name="Session",
                        value=f"Recorded to active session",
                        inline=True
                    )
                
                if description:
                    embed.add_field(
                        name="Description",
                        value=description,
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    "Failed to record profit. Please try again later.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error recording profit: {e}")
            await interaction.followup.send(
                "An error occurred while recording your profit.",
                ephemeral=True
            )
            
    async def cog_unload(self):
        """Cleanup when cog is unloaded."""
        # Cancel the username sync task if it's running
        if self.sync_usernames.is_running():
            self.sync_usernames.cancel()
            
        # Cancel the loan due date check task if it's running
        if self.check_loan_due_dates.is_running():
            self.check_loan_due_dates.cancel()
        
        logger.info("BankingCog has been unloaded.")

async def setup(bot):
    await bot.add_cog(BankingCog(bot))
    logger.info("BankingCog has been added to the bot.")