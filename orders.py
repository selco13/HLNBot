import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
from datetime import datetime, timedelta, timezone
import random
from typing import Dict, List, Optional, Any, Tuple, Union, Set
import json
import os
import enum

# Import profile event types for integration
from cogs.utils.profile_events import ProfileEvent, ProfileEventType

logger = logging.getLogger('orders')
GUILD_ID = int(os.getenv("GUILD_ID", 0))
PERSONAL_ORDERS_CHANNEL = 1340090171642609704
MAJOR_ORDERS_CHANNEL = 1340090017544015892
DIVISION_ORDERS_CHANNEL = int(os.getenv("DIVISION_ORDERS_CHANNEL", PERSONAL_ORDERS_CHANNEL))

# ----------- Order Definitions ------------

class OrderType(enum.Enum):
    MISSION = "Mission"
    MAJOR = "Major"
    DIVISION = "Division"

class OrderStatus(enum.Enum):
    PENDING = "Pending"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    EXPIRED = "Expired"
    CANCELLED = "Cancelled"

class Order:
    def __init__(
        self,
        order_id: str,
        title: str,
        description: str,
        order_type: OrderType,
        start_date: datetime,
        end_date: datetime,
        author_id: int,
        priority: int = 0
    ):
        self.order_id = order_id
        self.title = title
        self.description = description
        self.order_type = order_type
        self.start_date = start_date
        self.end_date = end_date
        self.author_id = author_id
        self.priority = priority
        self.status = OrderStatus.PENDING
        self.created_at = datetime.now()
        self.modified_at = datetime.now()
        self.completion_data = {}
        self.participants: List[int] = []  # Track members who participated
        self.progress_updates: List[Dict[str, Any]] = []  # Track progress updates

    def to_dict(self) -> dict:
        return {
            'order_id': self.order_id,
            'title': self.title,
            'description': self.description,
            'order_type': self.order_type.value,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'author_id': self.author_id,
            'priority': self.priority,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'modified_at': self.modified_at.isoformat(),
            'completion_data': self.completion_data,
            'participants': self.participants,
            'progress_updates': self.progress_updates
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Order':
        order = cls(
            order_id=data['order_id'],
            title=data['title'],
            description=data['description'],
            order_type=OrderType(data['order_type']),
            start_date=datetime.fromisoformat(data['start_date']),
            end_date=datetime.fromisoformat(data['end_date']),
            author_id=data['author_id'],
            priority=data.get('priority', 0)
        )
        order.status = OrderStatus(data['status'])
        order.created_at = datetime.fromisoformat(data['created_at'])
        order.modified_at = datetime.fromisoformat(data['modified_at'])
        order.completion_data = data.get('completion_data', {})
        order.participants = data.get('participants', [])
        order.progress_updates = data.get('progress_updates', [])
        return order

    def add_progress_update(self, update_by: int, update_text: str):
        """Add a progress update to the order"""
        self.progress_updates.append({
            'timestamp': datetime.now().isoformat(),
            'update_by': update_by,
            'update_text': update_text
        })
        self.modified_at = datetime.now()

    def add_participant(self, member_id: int):
        """Add a participant to the order"""
        if member_id not in self.participants:
            self.participants.append(member_id)
            self.modified_at = datetime.now()
            return True
        return False

class MissionOrder(Order):
    def __init__(
        self,
        order_id: str,
        title: str,
        description: str,
        start_date: datetime,
        end_date: datetime,
        author_id: int,
        mission_type: str,
        required_roles: List[str],
        objectives: List[str]
    ):
        super().__init__(order_id, title, description, OrderType.MISSION, start_date, end_date, author_id)
        self.mission_type = mission_type
        self.required_roles = required_roles
        self.objectives = objectives

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            'mission_type': self.mission_type,
            'required_roles': self.required_roles,
            'objectives': self.objectives
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'MissionOrder':
        order = cls(
            order_id=data['order_id'],
            title=data['title'],
            description=data['description'],
            start_date=datetime.fromisoformat(data['start_date']),
            end_date=datetime.fromisoformat(data['end_date']),
            author_id=data['author_id'],
            mission_type=data['mission_type'],
            required_roles=data['required_roles'],
            objectives=data['objectives']
        )
        order.status = OrderStatus(data['status'])
        order.created_at = datetime.fromisoformat(data['created_at'])
        order.modified_at = datetime.fromisoformat(data['modified_at'])
        order.completion_data = data.get('completion_data', {})
        order.participants = data.get('participants', [])
        order.progress_updates = data.get('progress_updates', [])
        return order

class MajorOrder(Order):
    def __init__(
        self,
        order_id: str,
        title: str,
        description: str,
        start_date: datetime,
        end_date: datetime,
        author_id: int,
        strategic_objectives: List[str],
        resource_requirements: Dict[str, Any]
    ):
        super().__init__(order_id, title, description, OrderType.MAJOR, start_date, end_date, author_id)
        self.strategic_objectives = strategic_objectives
        self.resource_requirements = resource_requirements
        self.linked_division_orders: List[str] = []  # IDs of linked division orders

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            'strategic_objectives': self.strategic_objectives,
            'resource_requirements': self.resource_requirements,
            'linked_division_orders': self.linked_division_orders
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'MajorOrder':
        order = cls(
            order_id=data['order_id'],
            title=data['title'],
            description=data['description'],
            start_date=datetime.fromisoformat(data['start_date']),
            end_date=datetime.fromisoformat(data['end_date']),
            author_id=data['author_id'],
            strategic_objectives=data['strategic_objectives'],
            resource_requirements=data['resource_requirements']
        )
        order.status = OrderStatus(data['status'])
        order.created_at = datetime.fromisoformat(data['created_at'])
        order.modified_at = datetime.fromisoformat(data['modified_at'])
        order.completion_data = data.get('completion_data', {})
        order.linked_division_orders = data.get('linked_division_orders', [])
        order.participants = data.get('participants', [])
        order.progress_updates = data.get('progress_updates', [])
        return order

class DivisionOrder(Order):
    def __init__(
        self,
        order_id: str,
        title: str,
        description: str,
        start_date: datetime,
        end_date: datetime,
        author_id: int,
        division: str,
        objectives: List[str],
        required_personnel: int
    ):
        super().__init__(order_id, title, description, OrderType.DIVISION, start_date, end_date, author_id)
        self.division = division
        self.objectives = objectives
        self.required_personnel = required_personnel
        self.parent_major_order: Optional[str] = None  # ID of parent major order

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            'division': self.division,
            'objectives': self.objectives,
            'required_personnel': self.required_personnel,
            'parent_major_order': self.parent_major_order
        })
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'DivisionOrder':
        order = cls(
            order_id=data['order_id'],
            title=data['title'],
            description=data['description'],
            start_date=datetime.fromisoformat(data['start_date']),
            end_date=datetime.fromisoformat(data['end_date']),
            author_id=data['author_id'],
            division=data['division'],
            objectives=data['objectives'],
            required_personnel=data['required_personnel']
        )
        order.status = OrderStatus(data['status'])
        order.created_at = datetime.fromisoformat(data['created_at'])
        order.modified_at = datetime.fromisoformat(data['modified_at'])
        order.completion_data = data.get('completion_data', {})
        order.parent_major_order = data.get('parent_major_order')
        order.participants = data.get('participants', [])
        order.progress_updates = data.get('progress_updates', [])
        return order

# ---------- Monthly Cycle Management ----------

class MonthlyCycle:
    """Manages the 4-week cycle described in the M.E.S.S. document"""
    def __init__(self):
        self.current_week = 0  # 0-3 representing weeks of the month
        self.current_month = 0  # 0-11 representing months of the year
        self.major_order_id: Optional[str] = None 
        self.division_orders_phase1: List[str] = []  # First set (Week 1-2)
        self.division_orders_phase2: List[str] = []  # Second set (Week 3-4)
        self.weekly_mission_ids: List[str] = []      # Weekly missions for the month
        self.start_date = datetime.now()
        self.is_active = False
        
    def to_dict(self) -> dict:
        """Convert to serializable dictionary"""
        return {
            'current_week': self.current_week,
            'current_month': self.current_month,
            'major_order_id': self.major_order_id,
            'division_orders_phase1': self.division_orders_phase1,
            'division_orders_phase2': self.division_orders_phase2,
            'weekly_mission_ids': self.weekly_mission_ids,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'is_active': self.is_active
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'MonthlyCycle':
        """Create from serialized dictionary"""
        cycle = cls()
        cycle.current_week = data.get('current_week', 0)
        cycle.current_month = data.get('current_month', 0)
        cycle.major_order_id = data.get('major_order_id')
        cycle.division_orders_phase1 = data.get('division_orders_phase1', [])
        cycle.division_orders_phase2 = data.get('division_orders_phase2', [])
        cycle.weekly_mission_ids = data.get('weekly_mission_ids', [])
        if data.get('start_date'):
            cycle.start_date = datetime.fromisoformat(data['start_date'])
        cycle.is_active = data.get('is_active', False)
        return cycle
        
    def advance_week(self) -> bool:
        """Move to the next week in the cycle, return True if month completed"""
        self.current_week = (self.current_week + 1) % 4
        if self.current_week == 0:
            # New month
            self.current_month = (self.current_month + 1) % 12
            return True
        return False

# ---------- Order Scheduler ----------

class OrderScheduler:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mission_pool: List[MissionOrder] = []
        self._active_missions: Dict[str, MissionOrder] = {}
        self._major_orders: Dict[str, MajorOrder] = {}
        self._division_orders: Dict[str, DivisionOrder] = {}
        self.monthly_cycle = MonthlyCycle()
        self.weekly_mission_pool = WEEKLY_MISSION_TEMPLATES.copy()

    async def schedule_mission_distribution(self):
        if not self._mission_pool:
            logger.warning("No missions in pool to distribute")
            return
        start_date = datetime.now()
        week_duration = timedelta(days=7)
        random.shuffle(self._mission_pool)
        for mission in self._mission_pool:
            mission.start_date = start_date
            mission.end_date = start_date + week_duration
            self._active_missions[mission.order_id] = mission
            start_date += week_duration

    async def update_division_orders(self):
        current_orders = list(self._division_orders.values())
        expired_orders = [order for order in current_orders if order.end_date < datetime.now()]
        for order in expired_orders:
            order.status = OrderStatus.EXPIRED
            self._division_orders.pop(order.order_id)

    async def get_active_major_order(self) -> Optional[MajorOrder]:
        """Get the currently active major order"""
        for order_id, order in self._major_orders.items():
            if order.status == OrderStatus.ACTIVE:
                return order
        return None
    
    async def get_active_division_orders(self) -> List[DivisionOrder]:
        """Get all currently active division orders"""
        return [order for order in self._division_orders.values() 
                if order.status == OrderStatus.ACTIVE]
    
    async def get_active_mission(self) -> Optional[MissionOrder]:
        """Get the currently active weekly mission"""
        for order_id, order in self._active_missions.items():
            if order.status == OrderStatus.ACTIVE:
                return order
        return None
    
    async def get_all_mission_types(self) -> List[str]:
        """Get all unique mission types from the templates"""
        mission_types = set()
        for template in WEEKLY_MISSION_TEMPLATES:
            mission_types.add(template['mission_type'])
        return sorted(list(mission_types))
        
    async def evaluate_monthly_progress(self) -> Tuple[bool, float, dict]:
        """Evaluate the progress of the current monthly cycle
        
        Returns:
            Tuple containing:
            - bool: Whether monthly goals are met (4/6 division orders complete)
            - float: Completion percentage
            - dict: Detailed statistics
        """
        # Get active major order
        major_order = await self.get_active_major_order()
        if not major_order:
            return False, 0.0, {"error": "No active major order found"}
            
        # Count total and completed division orders
        total_div_orders = 0
        completed_div_orders = 0
        
        div_orders = await self.get_active_division_orders()
        total_div_orders = len(div_orders)
        completed_div_orders = len([o for o in div_orders if o.status == OrderStatus.COMPLETED])
        
        # Add historical division orders from this cycle
        if self.monthly_cycle.division_orders_phase1:
            for order_id in self.monthly_cycle.division_orders_phase1:
                # Check if order was completed but is now archived
                # This would need adjusting based on your archiving system
                if order_id not in self._division_orders:
                    # This means it was archived
                    total_div_orders += 1
                    completed_div_orders += 1
        
        if self.monthly_cycle.division_orders_phase2:
            for order_id in self.monthly_cycle.division_orders_phase2:
                if order_id not in self._division_orders:
                    total_div_orders += 1
                    completed_div_orders += 1
        
        # Calculate completion percentage
        completion_pct = (completed_div_orders / max(1, total_div_orders)) * 100
        
        # Check if monthly goal is met (4/6 division orders)
        monthly_goal_met = completed_div_orders >= 4
        
        return monthly_goal_met, completion_pct, {
            "total_division_orders": total_div_orders,
            "completed_division_orders": completed_div_orders,
            "major_order_title": major_order.title if major_order else "None",
            "current_week": self.monthly_cycle.current_week,
            "current_month": self.monthly_cycle.current_month
        }
        
    async def setup_new_monthly_cycle(self, major_order_template: str, author_id: int) -> Optional[MajorOrder]:
        """Set up a new monthly cycle with the given major order
        
        Returns:
            The created major order, or None if there was an error
        """
        try:
            # Create Major Order (lasts whole month)
            now = datetime.now()
            end_date = now + timedelta(days=30)
            
            # Generate unique ID
            order_id = f"major_{now.strftime('%Y%m%d')}_{random.randint(1000, 9999)}"
            
            # Create order
            major_order = MajorOrder(
                order_id=order_id,
                title=major_order_template,
                description=f"Strategic directive for {now.strftime('%B %Y')}",
                start_date=now,
                end_date=end_date,
                author_id=author_id,
                strategic_objectives=[major_order_template],
                resource_requirements={}
            )
            
            # Activate order
            major_order.status = OrderStatus.ACTIVE
            
            # Store in scheduler
            self._major_orders[order_id] = major_order
            
            # Update monthly cycle
            self.monthly_cycle.major_order_id = order_id
            self.monthly_cycle.current_week = 0
            self.monthly_cycle.start_date = now
            self.monthly_cycle.is_active = True
            
            # Create appropriate progress update
            major_order.add_progress_update(
                author_id,
                f"Monthly cycle initialized with Major Order: {major_order_template}"
            )
            
            return major_order
        except Exception as e:
            logger.error(f"Error setting up new monthly cycle: {e}")
            return None
    async def create_synchronized_division_orders(
        self, 
        major_order: MajorOrder,
        author_id: int,
        is_phase_two: bool = False
    ) -> List[DivisionOrder]:
        """Create synchronized division orders for the first or second phase of the month
        
        Args:
            major_order: The parent major order
            author_id: ID of the author creating these orders
            is_phase_two: Whether this is the second phase of division orders
            
        Returns:
            List of created division orders
        """
        created_orders = []
        phase_text = "Phase 2" if is_phase_two else "Phase 1"
        
        try:
            now = datetime.now()
            # Division orders last 2 weeks (14 days)
            end_date = now + timedelta(days=14)
            
            for division in DIVISION_ORDER_TEMPLATES:
                # Select a template based on suitable matches with major order
                suitable_templates = self.get_suitable_division_templates(division, major_order.title)
                if not suitable_templates:
                    suitable_templates = DIVISION_ORDER_TEMPLATES[division]
                
                template = random.choice(suitable_templates)
                
                # Generate unique ID
                order_id = f"div_{division.lower()}_{phase_text.lower()}_{now.strftime('%Y%m%d')}"
                
                # Create order
                division_order = DivisionOrder(
                    order_id=order_id,
                    title=template,
                    description=f"Supporting {major_order.title} - {phase_text}",
                    start_date=now,
                    end_date=end_date,
                    author_id=author_id,
                    division=division,
                    objectives=[f"Support {major_order.title}"],
                    required_personnel=3
                )
                
                # Link to major order
                division_order.parent_major_order = major_order.order_id
                if major_order.linked_division_orders is None:
                    major_order.linked_division_orders = []
                major_order.linked_division_orders.append(order_id)
                
                # Activate order
                division_order.status = OrderStatus.ACTIVE
                
                # Store in scheduler
                self._division_orders[order_id] = division_order
                created_orders.append(division_order)
                
                # Update monthly cycle
                if is_phase_two:
                    self.monthly_cycle.division_orders_phase2.append(order_id)
                else:
                    self.monthly_cycle.division_orders_phase1.append(order_id)
            
            # Create appropriate progress update
            major_order.add_progress_update(
                author_id,
                f"Created {len(created_orders)} division orders for {phase_text}"
            )
            
            return created_orders
        except Exception as e:
            logger.error(f"Error creating synchronized division orders: {e}")
            return []
    
    def get_suitable_division_templates(self, division: str, major_order_title: str) -> List[str]:
        """Get division order templates that align with the major order"""
        if division not in DIVISION_ORDER_TEMPLATES:
            return []
            
        all_templates = DIVISION_ORDER_TEMPLATES[division]
        
        # Define thematic alignment between major orders and division templates
        # This is a heuristic approach - you might want to define this mapping more explicitly
        if "Security" in major_order_title or "Piracy" in major_order_title:
            return [t for t in all_templates if any(keyword in t for keyword in 
                                                  ["Security", "Offensive", "Crackdown", "Training"])]
        
        elif "Economic" in major_order_title or "Trade" in major_order_title:
            return [t for t in all_templates if any(keyword in t for keyword in 
                                                  ["Trade", "Economic", "Cargo", "Mining", "Salvage"])]
        
        elif "Recruitment" in major_order_title or "Outreach" in major_order_title:
            return [t for t in all_templates if any(keyword in t for keyword in 
                                                  ["Outreach", "Training", "Focus"])]
        
        # Default case: return all templates
        return all_templates

    async def create_weekly_mission(self, author_id: int) -> Optional[MissionOrder]:
        """Create a weekly mission from the pool"""
        try:
            # Ensure we have templates available
            if not self.weekly_mission_pool:
                self.weekly_mission_pool = WEEKLY_MISSION_TEMPLATES.copy()
            
            # Select a random template
            template = random.choice(self.weekly_mission_pool)
            self.weekly_mission_pool.remove(template)
            
            now = datetime.now()
            # Weekly missions last 7 days
            end_date = now + timedelta(days=7)
            
            # Generate unique ID
            order_id = f"mission_{now.strftime('%Y%m%d')}_{random.randint(1000, 9999)}"
            
            # Create mission
            mission = MissionOrder(
                order_id=order_id,
                title=template["title"],
                description=template["description"],
                start_date=now,
                end_date=end_date,
                author_id=author_id,
                mission_type=template["mission_type"],
                required_roles=template["required_roles"],
                objectives=template["objectives"]
            )
            
            # Activate mission
            mission.status = OrderStatus.ACTIVE
            
            # Store in scheduler
            self._active_missions[order_id] = mission
            
            # Update monthly cycle
            self.monthly_cycle.weekly_mission_ids.append(order_id)
            
            return mission
        except Exception as e:
            logger.error(f"Error creating weekly mission: {e}")
            return None

# --------- Order Templates ---------

WEEKLY_MISSION_TEMPLATES = [
    {
        "title": "Contribute 500k to the Org bank",
        "description": "Deposit 500,000 aUEC into the org bank account.",
        "mission_type": "Financial",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Increase Reputation with Stanton Faction",
        "description": "Boost your reputation with one of Stanton's major factions.",
        "mission_type": "Reputation",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Increase Reputation with Pyro Faction",
        "description": "Improve your standing with one of Pyro's major factions.",
        "mission_type": "Reputation",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Collect Special Weapons for Org Use",
        "description": "Secure special weapons for organizational use.",
        "mission_type": "Combat",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Increase Cargo Reputation in Stanton",
        "description": "Enhance your cargo handling reputation in Stanton.",
        "mission_type": "Trade",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Increase Cargo Reputation in Pyro",
        "description": "Enhance your cargo handling reputation in Pyro.",
        "mission_type": "Trade",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Respond to a Distress Call",
        "description": "Answer a player distress call somewhere in the verse.",
        "mission_type": "Rescue",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Gain Your Next Certification",
        "description": "Work towards your next certification within your current track.",
        "mission_type": "Certification",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Participate in an Org Night",
        "description": "Join your org members for an evening of cooperative gameplay.",
        "mission_type": "Social",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Complete a Race on Stanton Tracks",
        "description": "Participate in an organized race on Stanton's tracks.",
        "mission_type": "Racing",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Hunt a Player Bounty",
        "description": "Locate and complete a player bounty mission.",
        "mission_type": "Bounty",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Explore a New Location",
        "description": "Venture to an unexplored or remote location and report back.",
        "mission_type": "Exploration",
        "required_roles": [],
        "objectives": []
    },
    {
        "title": "Report on a Remote Area",
        "description": "Discover a new area and provide a detailed report.",
        "mission_type": "Exploration",
        "required_roles": [],
        "objectives": []
    }
]

# Extract all available mission types for autocomplete
MISSION_TYPES = sorted(list(set(template["mission_type"] for template in WEEKLY_MISSION_TEMPLATES)))

# Preset date options for autocomplete
DATE_PRESETS = {
    "today": lambda: datetime.now(),
    "tomorrow": lambda: datetime.now() + timedelta(days=1),
    "next_week": lambda: datetime.now() + timedelta(days=7),
    "two_weeks": lambda: datetime.now() + timedelta(days=14),
    "one_month": lambda: datetime.now() + timedelta(days=30),
}

DIVISION_ORDER_TEMPLATES = {
    "Tactical": [
        "Security Crackdown",
        "Pilot Training",
        "Gunnery Training",
        "Marine Offensive",
        "Anti-Piracy Offensive",
        "Trade Security"
    ],
    "Operations": [
        "Salvage Surge",
        "Cargo Conglomerate",
        "Mining Training",
        "FOB Assertion",
        "Free Trade Focus",
        "Economic Boom"
    ],
    "Support": [
        "Medical Mandate",
        "Fuel Fiasco",
        "Logistic Focus",
        "Civilian Outreach"
    ]
}

MAJOR_ORDER_TEMPLATES = [
    "Pyro Security Crackdown",
    "Economic Focus in Stanton",
    "Recruitment Drive/Anti-Piracy",
    "Free Trade for Pyro",
    "HLN Civilian Outreach",
    "Anti-Piracy Crackdown",
    "Policing Stanton",
    "TBD Order 8",
    "TBD Order 9",
    "TBD Order 10",
    "TBD Order 11",
    "TBD Order 12"
]

# --- Standalone autocomplete callbacks ---
async def autocomplete_order_id_callback(interaction: discord.Interaction, current: str):
    cog = interaction.client.get_cog("OrdersCog")
    if cog is None:
        return []
    return await cog.autocomplete_order_id(interaction, current)

async def autocomplete_mission_type_callback(interaction: discord.Interaction, current: str):
    filtered_types = [
        app_commands.Choice(name=mission_type, value=mission_type)
        for mission_type in MISSION_TYPES
        if current.lower() in mission_type.lower()
    ]
    return filtered_types[:25]

async def autocomplete_date_callback(interaction: discord.Interaction, current: str):
    now = datetime.now()
    choices = []
    
    # Add preset choices
    for name, func in DATE_PRESETS.items():
        date_value = func().strftime('%Y-%m-%d')
        display_name = f"{name.replace('_', ' ').title()} ({date_value})"
        if current.lower() in name.lower() or current.lower() in date_value.lower():
            choices.append(app_commands.Choice(name=display_name, value=date_value))
    
    # Add manually typed date if it looks like a date format
    if current and len(current) >= 8:  # At least YYYY-MM-D
        try:
            # Try to parse as date
            parsed_date = datetime.strptime(current, '%Y-%m-%d')
            # If we get here, it's a valid date
            choices.append(app_commands.Choice(name=f"Custom: {current}", value=current))
        except ValueError:
            # Not a valid date, that's fine
            pass
    
    return choices[:25]

# New async autocomplete callbacks to replace lambda functions
async def autocomplete_division_callback(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=div, value=div)
        for div in DIVISION_ORDER_TEMPLATES.keys()
        if current.lower() in div.lower()
    ][:25]

async def autocomplete_template_callback(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=template, value=template)
        for template in MAJOR_ORDER_TEMPLATES
        if current.lower() in template.lower()
    ][:25]

class OrdersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduler = OrderScheduler(bot)
        self.orders_file = 'data/orders.json'
        self.cycle_file = 'data/order_cycle.json'
        self._mission_cog = None
        self._load_orders()
        self._load_cycle()
        self.autonomous_active = False
        self.autonomous_task: Optional[asyncio.Task] = None
        self.simulated_week = 0
        self.weekly_mission_pool = WEEKLY_MISSION_TEMPLATES.copy()
        self.last_personal_order_message = None
        self.last_major_order_message = None
        self.last_division_order_message = None

    def cog_unload(self):
        if self.autonomous_task:
            self.autonomous_task.cancel()
        self._save_orders()
        self._save_cycle()

    def _load_orders(self):
        try:
            if not os.path.exists(self.orders_file):
                return
            with open(self.orders_file, 'r') as f:
                data = json.load(f)
            self.scheduler._mission_pool = [
                MissionOrder.from_dict(m) for m in data.get('mission_pool', [])
            ]
            self.scheduler._active_missions = {
                m['order_id']: MissionOrder.from_dict(m)
                for m in data.get('active_missions', [])
            }
            self.scheduler._major_orders = {
                m['order_id']: MajorOrder.from_dict(m)
                for m in data.get('major_orders', [])
            }
            self.scheduler._division_orders = {
                m['order_id']: DivisionOrder.from_dict(m)
                for m in data.get('division_orders', [])
            }
        except Exception as e:
            logger.error(f"Error loading orders: {e}")

    def _save_orders(self):
        try:
            data = {
                'mission_pool': [m.to_dict() for m in self.scheduler._mission_pool],
                'active_missions': [m.to_dict() for m in self.scheduler._active_missions.values()],
                'major_orders': [m.to_dict() for m in self.scheduler._major_orders.values()],
                'division_orders': [m.to_dict() for m in self.scheduler._division_orders.values()]
            }
            os.makedirs(os.path.dirname(self.orders_file), exist_ok=True)
            with open(self.orders_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving orders: {e}")
    
    def _load_cycle(self):
        try:
            if not os.path.exists(self.cycle_file):
                return
            with open(self.cycle_file, 'r') as f:
                data = json.load(f)
            self.scheduler.monthly_cycle = MonthlyCycle.from_dict(data)
        except Exception as e:
            logger.error(f"Error loading monthly cycle: {e}")
    
    def _save_cycle(self):
        try:
            data = self.scheduler.monthly_cycle.to_dict()
            os.makedirs(os.path.dirname(self.cycle_file), exist_ok=True)
            with open(self.cycle_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving monthly cycle: {e}")

    async def update_channel_message(self, channel_id: int, embed: discord.Embed, current_message_ref: Optional[discord.Message] = None) -> Optional[discord.Message]:
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error(f"Could not find channel {channel_id}")
            return None
        try:
            if current_message_ref:
                try:
                    await current_message_ref.delete()
                except discord.NotFound:
                    pass
            new_message = await channel.send(embed=embed)
            return new_message
        except Exception as e:
            logger.error(f"Error updating channel message: {e}")
            return None

    async def create_order_embed(self, order: Order) -> discord.Embed:
        """Create a rich embed showing detailed order information with progress tracking"""
        # Basic embed setup
        embed = discord.Embed(
            title=f"{self.get_order_emoji(order)} {order.title}",
            description=order.description,
            color=self.get_status_color(order.status)
        )
        
        # Add progress bar if appropriate
        if order.status in [OrderStatus.ACTIVE, OrderStatus.PENDING]:
            progress_bar = await self.create_progress_bar(order)
            embed.add_field(name="Progress", value=progress_bar, inline=False)
        
        # Basic order information
        embed.add_field(name="Type", value=order.order_type.value)
        embed.add_field(name="Status", value=order.status.value)
        
        # Time information
        embed.add_field(name="Started", value=f"<t:{int(order.start_date.timestamp())}:R>", inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(order.end_date.timestamp())}:R>", inline=True)
        
        # Creator information
        try:
            creator = self.bot.get_user(order.author_id)
            creator_name = creator.name if creator else f"User ID: {order.author_id}"
        except:
            creator_name = f"User ID: {order.author_id}"
        
        embed.add_field(name="Created By", value=creator_name)
        
        # Order-specific fields
        if isinstance(order, MissionOrder):
            embed.add_field(name="Mission Type", value=order.mission_type, inline=True)
            if order.objectives:
                embed.add_field(name="Objectives", value="\n".join(f"• {obj}" for obj in order.objectives), inline=False)
                
        elif isinstance(order, MajorOrder):
            if order.strategic_objectives:
                embed.add_field(name="Strategic Objectives", value="\n".join(f"• {obj}" for obj in order.strategic_objectives), inline=False)
            
            # Show linked division orders if available
            if hasattr(order, 'linked_division_orders') and order.linked_division_orders:
                linked_orders = []
                for order_id in order.linked_division_orders:
                    if order_id in self.scheduler._division_orders:
                        div_order = self.scheduler._division_orders[order_id]
                        status_emoji = self.get_status_emoji(div_order.status)
                        linked_orders.append(f"{status_emoji} {div_order.division}: {div_order.title}")
                
                if linked_orders:
                    embed.add_field(name="Division Support", value="\n".join(linked_orders), inline=False)
                
        elif isinstance(order, DivisionOrder):
            embed.add_field(name="Division", value=order.division)
            if order.objectives:
                embed.add_field(name="Objectives", value="\n".join(f"• {obj}" for obj in order.objectives), inline=False)
            
            # Show parent major order if available
            if hasattr(order, 'parent_major_order') and order.parent_major_order:
                if order.parent_major_order in self.scheduler._major_orders:
                    major_order = self.scheduler._major_orders[order.parent_major_order]
                    embed.add_field(name="Supporting", value=f"{major_order.title}", inline=True)
        
        # Add participants count if any
        if hasattr(order, 'participants') and order.participants:
            embed.add_field(name="Participants", value=f"{len(order.participants)} members involved", inline=True)
        
        # Add completion information if completed
        if order.status == OrderStatus.COMPLETED and order.completion_data:
            completed_at = order.completion_data.get('completed_at', 'Unknown')
            if isinstance(completed_at, str) and completed_at != 'Unknown':
                try:
                    completed_dt = datetime.fromisoformat(completed_at)
                    completed_at = f"<t:{int(completed_dt.timestamp())}:R>"
                except:
                    pass
            
            embed.add_field(name="Completed", value=completed_at, inline=True)
            
            # Add completion notes if available
            notes = order.completion_data.get('notes')
            if notes:
                embed.add_field(name="Completion Notes", value=notes, inline=False)
        
        # Recent progress updates if available
        if hasattr(order, 'progress_updates') and order.progress_updates:
            recent_updates = order.progress_updates[-3:]  # Show last 3 updates
            updates_text = []
            
            for update in recent_updates:
                timestamp = update.get('timestamp', 'Unknown')
                if isinstance(timestamp, str) and timestamp != 'Unknown':
                    try:
                        update_dt = datetime.fromisoformat(timestamp)
                        timestamp = f"<t:{int(update_dt.timestamp())}:R>"
                    except:
                        pass
                
                update_by = update.get('update_by', 0)
                try:
                    user = self.bot.get_user(update_by)
                    user_name = user.name if user else f"User {update_by}"
                except:
                    user_name = f"User {update_by}"
                
                updates_text.append(f"**{timestamp}** by {user_name}: {update.get('update_text', 'No details')}")
            
            if updates_text:
                embed.add_field(name="Recent Updates", value="\n".join(updates_text), inline=False)
        
        # Add footer with order ID
        embed.set_footer(text=f"Order ID: {order.order_id}")
        
        return embed
    
    def get_order_emoji(self, order: Order) -> str:
        """Get appropriate emoji for order type"""
        if order.order_type == OrderType.MISSION:
            return "📋"
        elif order.order_type == OrderType.MAJOR:
            return "🔱"
        elif order.order_type == OrderType.DIVISION:
            return "🚩"
        return "📜"
    
    def get_status_emoji(self, status: OrderStatus) -> str:
        """Get appropriate emoji for order status"""
        if status == OrderStatus.ACTIVE:
            return "🟢"
        elif status == OrderStatus.PENDING:
            return "🟡"
        elif status == OrderStatus.COMPLETED:
            return "✅"
        elif status == OrderStatus.EXPIRED:
            return "⏱️"
        elif status == OrderStatus.CANCELLED:
            return "❌"
        return "⚪"
    
    def get_status_color(self, status: OrderStatus) -> discord.Color:
        """Get appropriate color for order status"""
        if status == OrderStatus.ACTIVE:
            return discord.Color.green()
        elif status == OrderStatus.PENDING:
            return discord.Color.gold()
        elif status == OrderStatus.COMPLETED:
            return discord.Color.blue()
        elif status == OrderStatus.EXPIRED:
            return discord.Color.dark_gray()
        elif status == OrderStatus.CANCELLED:
            return discord.Color.red()
        return discord.Color.light_gray()
    
    async def create_progress_bar(self, order: Order) -> str:
        """Create a visual progress bar for the order"""
        now = datetime.now()
        
        # Calculate progress percentage
        if now < order.start_date:
            progress_pct = 0
        elif now > order.end_date:
            progress_pct = 100
        else:
            total_seconds = (order.end_date - order.start_date).total_seconds()
            elapsed_seconds = (now - order.start_date).total_seconds()
            progress_pct = min(100, max(0, (elapsed_seconds / total_seconds) * 100))
        
        # Create visual bar
        bar_length = 20
        filled = int(bar_length * progress_pct / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        # Create text representation
        time_left = "Overdue" if now > order.end_date else f"<t:{int(order.end_date.timestamp())}:R>"
        
        return f"**{progress_pct:.1f}%** complete\n{bar}\nEnds: {time_left}"
    
    async def create_evaluation_embed(self) -> discord.Embed:
        """Create an embed evaluating current orders status"""
        monthly_goal_met, completion_pct, details = await self.scheduler.evaluate_monthly_progress()
        
        # Get active major order
        major_order = await self.scheduler.get_active_major_order()
        major_order_title = major_order.title if major_order else "No active major order"
        
        # Get active division orders
        div_orders = await self.scheduler.get_active_division_orders()
        
        # Get active mission
        mission = await self.scheduler.get_active_mission()
        
        # Create embed
        embed = discord.Embed(
            title="📊 Orders Evaluation Report",
            description=f"Monthly progress report for {datetime.now().strftime('%B %Y')}",
            color=discord.Color.blue()
        )
        
        # Create progress bar
        bar_length = 20
        filled = int(bar_length * completion_pct / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        # Add major order section
        if major_order:
            embed.add_field(
                name="Monthly Major Order",
                value=f"**{major_order_title}**\n"
                      f"Status: {major_order.status.value}\n"
                      f"Progress: **{completion_pct:.1f}%**\n"
                      f"{bar}\n"
                      f"Goal: 4/6 Division Orders complete\n"
                      f"Current: {details['completed_division_orders']}/{details['total_division_orders']}",
                inline=False
            )
        
        # Add division orders section
        if div_orders:
            div_text = []
            for order in div_orders:
                status_emoji = self.get_status_emoji(order.status)
                div_text.append(f"{status_emoji} **{order.division}**: {order.title}")
            
            embed.add_field(
                name="Active Division Orders",
                value="\n".join(div_text),
                inline=False
            )
        
        # Add current mission section
        if mission:
            embed.add_field(
                name="Current Weekly Mission",
                value=f"**{mission.title}**\n"
                      f"Type: {mission.mission_type}\n"
                      f"Status: {mission.status.value}\n"
                      f"Due: <t:{int(mission.end_date.timestamp())}:R>",
                inline=False
            )
        
        # Add cycle info
        cycle = self.scheduler.monthly_cycle
        embed.add_field(
            name="Cycle Information",
            value=f"Week: {cycle.current_week + 1}/4\n"
                  f"Month: {cycle.current_month + 1}/12\n"
                  f"Status: {'Active' if cycle.is_active else 'Inactive'}",
            inline=True
        )
        
        return embed

    @property
    def mission_cog(self):
        if self._mission_cog is None:
            self._mission_cog = self.bot.get_cog('MissionCog')
        return self._mission_cog

    # ------- UTILITY METHODS -------

    async def refresh_order_messages(self) -> Tuple[int, int, int]:
        """Refresh all order channel messages
        
        Returns:
            Tuple of (personal_refreshed, major_refreshed, division_refreshed) counts
        """
        personal_refreshed = 0
        major_refreshed = 0 
        division_refreshed = 0
        
        # Refresh active mission
        mission = await self.scheduler.get_active_mission()
        if mission:
            embed = await self.create_order_embed(mission)
            self.last_personal_order_message = await self.update_channel_message(
                PERSONAL_ORDERS_CHANNEL,
                embed,
                self.last_personal_order_message
            )
            if self.last_personal_order_message:
                personal_refreshed += 1
        
        # Refresh active major order
        major_order = await self.scheduler.get_active_major_order()
        if major_order:
            embed = await self.create_order_embed(major_order)
            self.last_major_order_message = await self.update_channel_message(
                MAJOR_ORDERS_CHANNEL,
                embed,
                self.last_major_order_message
            )
            if self.last_major_order_message:
                major_refreshed += 1
        
        # Refresh active division orders
        div_orders = await self.scheduler.get_active_division_orders()
        if div_orders:
            # Create combined embed
            embed = discord.Embed(
                title="🚩 Active Division Orders",
                description=f"Current division objectives",
                color=discord.Color.green()
            )
            
            for order in div_orders:
                embed.add_field(
                    name=f"{order.division}: {order.title}",
                    value=f"{order.description}\nStatus: {order.status.value}\nDue: <t:{int(order.end_date.timestamp())}:R>",
                    inline=False
                )
            
            self.last_division_order_message = await self.update_channel_message(
                DIVISION_ORDERS_CHANNEL,
                embed,
                self.last_division_order_message
            )
            if self.last_division_order_message:
                division_refreshed += 1
        
        return personal_refreshed, major_refreshed, division_refreshed

    async def get_active_order_counts(self) -> Tuple[int, int, int]:
        """Get counts of active orders by type
        
        Returns:
            Tuple of (missions, major_orders, division_orders) counts
        """
        mission_count = len([o for o in self.scheduler._active_missions.values() 
                           if o.status == OrderStatus.ACTIVE])
        
        major_count = len([o for o in self.scheduler._major_orders.values() 
                          if o.status == OrderStatus.ACTIVE])
        
        division_count = len([o for o in self.scheduler._division_orders.values() 
                             if o.status == OrderStatus.ACTIVE])
        
        return mission_count, major_count, division_count

    # ------- AUTONOMOUS SYSTEM METHODS -------
    
    async def autonomous_order_loop(self):
        logger.info("Autonomous order system started.")
        while self.autonomous_active:
            now = datetime.now()
            logger.info(f"Processing autonomous order loop at {now.isoformat()}")
            
            # Check if we need to advance the weekly cycle
            cycle = self.scheduler.monthly_cycle
            
            # If there's no active major order, create one
            major_order = await self.scheduler.get_active_major_order()
            if not major_order:
                # Start a new monthly cycle
                template = random.choice(MAJOR_ORDER_TEMPLATES)
                major_order = await self.scheduler.setup_new_monthly_cycle(template, self.bot.user.id)
                
                if major_order:
                    # Create embed and post to major orders channel
                    embed = await self.create_order_embed(major_order)
                    self.last_major_order_message = await self.update_channel_message(
                        MAJOR_ORDERS_CHANNEL,
                        embed,
                        self.last_major_order_message
                    )
                    logger.info(f"Created new major order: {major_order.title}")
                    
                    # Create first set of division orders
                    div_orders = await self.scheduler.create_synchronized_division_orders(
                        major_order, 
                        self.bot.user.id
                    )
                    
                    if div_orders:
                        # Create combined embed for division orders
                        embed = discord.Embed(
                            title="🚩 Division Orders - Phase 1",
                            description=f"Supporting Major Order: {major_order.title}",
                            color=discord.Color.green()
                        )
                        
                        for order in div_orders:
                            embed.add_field(
                                name=f"{order.division}: {order.title}",
                                value=f"{order.description}\nDue: <t:{int(order.end_date.timestamp())}:R>",
                                inline=False
                            )
                        
                        self.last_division_order_message = await self.update_channel_message(
                            DIVISION_ORDERS_CHANNEL,
                            embed,
                            self.last_division_order_message
                        )
                        logger.info(f"Created {len(div_orders)} division orders for Phase 1")
            
            # Check for division orders phase 2
            if cycle.current_week == 2 and not cycle.division_orders_phase2:
                # We're at week 3 and need Phase 2 division orders
                if major_order:
                    div_orders = await self.scheduler.create_synchronized_division_orders(
                        major_order, 
                        self.bot.user.id,
                        is_phase_two=True
                    )
                    
                    if div_orders:
                        # Create combined embed for division orders
                        embed = discord.Embed(
                            title="🚩 Division Orders - Phase 2",
                            description=f"Supporting Major Order: {major_order.title}",
                            color=discord.Color.green()
                        )
                        
                        for order in div_orders:
                            embed.add_field(
                                name=f"{order.division}: {order.title}",
                                value=f"{order.description}\nDue: <t:{int(order.end_date.timestamp())}:R>",
                                inline=False
                            )
                        
                        self.last_division_order_message = await self.update_channel_message(
                            DIVISION_ORDERS_CHANNEL,
                            embed,
                            self.last_division_order_message
                        )
                        logger.info(f"Created {len(div_orders)} division orders for Phase 2")
            
            # Check for weekly mission
            mission = await self.scheduler.get_active_mission()
            if not mission:
                # Create a new weekly mission
                mission = await self.scheduler.create_weekly_mission(self.bot.user.id)
                
                if mission:
                    embed = await self.create_order_embed(mission)
                    self.last_personal_order_message = await self.update_channel_message(
                        PERSONAL_ORDERS_CHANNEL,
                        embed,
                        self.last_personal_order_message
                    )
                    logger.info(f"Created weekly mission: {mission.title}")
                    
                    # If mission cog is available, create a mission
                    if self.mission_cog:
                        await self.mission_cog.create_mission_from_order(mission)
            
            # Evaluate monthly progress if at end of week
            if cycle.current_week == 3:
                # End of month, evaluate the monthly progress
                monthly_goal_met, completion_pct, details = await self.scheduler.evaluate_monthly_progress()
                
                # Log results
                logger.info(f"Monthly goal met: {monthly_goal_met}, Completion: {completion_pct:.1f}%")
                logger.info(f"Details: {details}")
                
                # If major order, update its status
                if major_order:
                    if monthly_goal_met:
                        major_order.status = OrderStatus.COMPLETED
                        major_order.completion_data = {
                            'completed_at': datetime.now().isoformat(),
                            'completed_by': self.bot.user.id,
                            'notes': f"Successfully completed with {completion_pct:.1f}% of division orders completed."
                        }
                    else:
                        # Not enough division orders completed
                        major_order.status = OrderStatus.EXPIRED
                        major_order.add_progress_update(
                            self.bot.user.id,
                            f"Failed to meet completion criteria. Only {completion_pct:.1f}% completed."
                        )
                    
                    # Update the message
                    embed = await self.create_order_embed(major_order)
                    self.last_major_order_message = await self.update_channel_message(
                        MAJOR_ORDERS_CHANNEL,
                        embed,
                        self.last_major_order_message
                    )
            
            # Advance the weekly cycle
            if cycle.is_active:
                month_completed = cycle.advance_week()
                if month_completed:
                    # Clear the previous month's data
                    cycle.division_orders_phase1 = []
                    cycle.division_orders_phase2 = []
                    cycle.weekly_mission_ids = []
                    cycle.major_order_id = None
                    
                    # Save changes
                    self._save_cycle()
            
            # Save the current state
            self._save_orders()
            self._save_cycle()
            
            # Wait for the next cycle (1 day in testing, 7 days in production)
            await asyncio.sleep(86400)  # 1 day for testing
            # await asyncio.sleep(604800)  # 7 days for production
            
        logger.info("Autonomous order system paused or stopped.")
    
    # ------- PROFILE SYSTEM INTEGRATION -------
    
    async def record_order_completion(self, member_id: int, order: Order, notes: str):
        """Record order completion in profile system"""
        try:
            if not hasattr(self.bot, "profile_sync"):
                logger.warning("Profile sync not available")
                return
                
            event_type = None
            if isinstance(order, MissionOrder):
                event_type = ProfileEventType.MISSION_COMPLETE
            elif isinstance(order, DivisionOrder):
                event_type = ProfileEventType.DIVISION_ORDER_COMPLETE
            elif isinstance(order, MajorOrder):
                event_type = ProfileEventType.MAJOR_ORDER_CONTRIBUTE
                
            if not event_type:
                return
                
            event = ProfileEvent(
                event_type=event_type,
                member_id=member_id,
                timestamp=datetime.now(timezone.utc),
                data={
                    "order_id": order.order_id,
                    "order_title": order.title,
                    "notes": notes,
                    "order_type": order.order_type.value
                }
            )
            await self.bot.profile_sync.queue_update(event)
        except Exception as e:
            logger.error(f"Error recording order completion: {e}")
            
            
    async def _create_mission_order_helper(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        mission_type: str,
        start_date: str,
        end_date: str
    ) -> bool:
        """Helper method to create a mission order"""
        try:
            # Validate mission type
            if mission_type not in MISSION_TYPES and mission_type:
                mission_type = MISSION_TYPES[0]  # Default to first type
                
            try:
                start_dt = datetime.fromisoformat(start_date)
            except ValueError:
                # Try alternate format
                start_dt = datetime.strptime(start_date, '%Y-%m-%d') 
                
            try:
                end_dt = datetime.fromisoformat(end_date)
            except ValueError:
                # Try alternate format
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                
            # Ensure end date is after start date
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(days=7)  # Default to 1 week
            
            order = MissionOrder(
                order_id=f"mission_{datetime.now().strftime('%Y%m%d')}_{random.randint(1000, 9999)}",
                title=title,
                description=description,
                start_date=start_dt,
                end_date=end_dt,
                author_id=interaction.user.id,
                mission_type=mission_type,
                required_roles=[],
                objectives=[]
            )
            order.status = OrderStatus.ACTIVE
            self.scheduler._active_missions[order.order_id] = order
            self._save_orders()
            embed = await self.create_order_embed(order)
            self.last_personal_order_message = await self.update_channel_message(
                PERSONAL_ORDERS_CHANNEL,
                embed,
                self.last_personal_order_message
            )
            if self.mission_cog:
                await self.mission_cog.create_mission_from_order(order)
            await interaction.followup.send(f"✅ Created mission order: {title}", embed=embed)
            return True
        except ValueError as ve:
            await interaction.followup.send(f"❌ Date format error: {ve}. Use YYYY-MM-DD format.", ephemeral=True)
            return False
        except Exception as e:
            logger.error(f"Error creating mission order: {e}")
            await interaction.followup.send(f"❌ An error occurred while creating the order: {str(e)}", ephemeral=True)
            return False
    
    async def _create_division_order_helper(
        self,
        interaction: discord.Interaction,
        division: str,
        template: str,
        description: str,
        duration_days: int = 14
    ) -> bool:
        """Helper method to create a division order"""
        try:
            if division not in DIVISION_ORDER_TEMPLATES:
                await interaction.followup.send(
                    f"❌ Invalid division. Available divisions: {', '.join(DIVISION_ORDER_TEMPLATES.keys())}",
                    ephemeral=True
                )
                return False
            if template not in DIVISION_ORDER_TEMPLATES[division]:
                await interaction.followup.send(
                    f"❌ Invalid template for division {division}",
                    ephemeral=True
                )
                return False
            now = datetime.now()
            order_id = f"div_{division.lower()}_{now.strftime('%Y%m%d')}_{random.randint(1000, 9999)}"
            order = DivisionOrder(
                order_id=order_id,
                title=template,
                description=description,
                start_date=now,
                end_date=now + timedelta(days=duration_days),
                author_id=interaction.user.id,
                division=division,
                objectives=[],
                required_personnel=0
            )
            order.status = OrderStatus.ACTIVE
            
            # Link to major order if one exists
            major_order = await self.scheduler.get_active_major_order()
            if major_order:
                order.parent_major_order = major_order.order_id
                if not hasattr(major_order, 'linked_division_orders'):
                    major_order.linked_division_orders = []
                major_order.linked_division_orders.append(order_id)
            
            self.scheduler._division_orders[order_id] = order
            self._save_orders()
            embed = await self.create_order_embed(order)
            await interaction.followup.send(embed=embed)
            
            # Update channel message
            self.last_division_order_message = await self.update_channel_message(
                DIVISION_ORDERS_CHANNEL,
                embed,
                self.last_division_order_message
            )
            return True
        except Exception as e:
            logger.error(f"Error creating division order: {e}")
            await interaction.followup.send(f"❌ An error occurred while creating the order: {str(e)}", ephemeral=True)
            return False
    
    async def _create_major_order_helper(
        self,
        interaction: discord.Interaction,
        template: str,
        description: str,
        duration_days: int = 30
    ) -> bool:
        """Helper method to create a major order"""
        try:
            if template not in MAJOR_ORDER_TEMPLATES:
                await interaction.followup.send("❌ Invalid template", ephemeral=True)
                return False
            now = datetime.now()
            order_id = f"major_{now.strftime('%Y%m%d')}_{random.randint(1000, 9999)}"
            order = MajorOrder(
                order_id=order_id,
                title=template,
                description=description,
                start_date=now,
                end_date=now + timedelta(days=duration_days),
                author_id=interaction.user.id,
                strategic_objectives=[template],
                resource_requirements={}
            )
            order.status = OrderStatus.ACTIVE
            self.scheduler._major_orders[order_id] = order
            self._save_orders()
            embed = await self.create_order_embed(order)
            self.last_major_order_message = await self.update_channel_message(
                MAJOR_ORDERS_CHANNEL,
                embed,
                self.last_major_order_message
            )
            await interaction.followup.send(embed=embed)
            return True
        except Exception as e:
            logger.error(f"Error creating major order: {e}")
            await interaction.followup.send(f"❌ An error occurred while creating the order: {str(e)}", ephemeral=True)
            return False
    
    # ------- COMMANDS SECTION -------
    
    @app_commands.command(name="order_system_start", description="Start the autonomous order system")
    @app_commands.default_permissions(administrator=True)
    async def order_system_start(self, interaction: discord.Interaction):
        if self.autonomous_active:
            await interaction.response.send_message("Autonomous order system is already running.", ephemeral=True)
            return
        self.autonomous_active = True
        self.scheduler.monthly_cycle.is_active = True
        self._save_cycle()
        self.autonomous_task = asyncio.create_task(self.autonomous_order_loop())
        await interaction.response.send_message("✅ Autonomous order system started.", ephemeral=True)

    @app_commands.command(name="order_system_pause", description="Pause the autonomous order system")
    @app_commands.default_permissions(administrator=True)
    async def order_system_pause(self, interaction: discord.Interaction):
        if not self.autonomous_active:
            await interaction.response.send_message("Autonomous order system is not running.", ephemeral=True)
            return
        self.autonomous_active = False
        self.scheduler.monthly_cycle.is_active = False
        self._save_cycle()
        await interaction.response.send_message("✅ Autonomous order system paused.", ephemeral=True)

    @app_commands.command(name="order_system_stop", description="Stop the autonomous order system completely")
    @app_commands.default_permissions(administrator=True)
    async def order_system_stop(self, interaction: discord.Interaction):
        if self.autonomous_task:
            self.autonomous_task.cancel()
            self.autonomous_task = None
        self.autonomous_active = False
        self.scheduler.monthly_cycle.is_active = False
        self._save_cycle()
        
        # Add confirmation dialog
        confirm_view = discord.ui.View(timeout=30)
        
        async def confirm_callback(confirm_interaction: discord.Interaction):
            if confirm_interaction.user.id != interaction.user.id:
                await confirm_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                return
            
            await confirm_interaction.response.send_message("✅ Autonomous order system stopped and cleared.", ephemeral=True)
        
        async def cancel_callback(cancel_interaction: discord.Interaction):
            if cancel_interaction.user.id != interaction.user.id:
                await cancel_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                return
            
            await cancel_interaction.response.send_message("Order system stopped but data preserved.", ephemeral=True)
        
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
        confirm_button.callback = confirm_callback
        
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel_button.callback = cancel_callback
        
        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)
        
        await interaction.response.send_message("Order system has been stopped. Would you like to also clear all current orders?", view=confirm_view, ephemeral=True)

    @app_commands.command(name="create_order", description="Create a new order of any type")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        type="The type of order to create",
        description="Description of the order",
        title="Title of the order (for mission orders)",
        mission_type="Type of mission (for mission orders)",
        division="Division for the order (for division orders)",
        template="Template for the order (for division and major orders)",
        start_date="Start date for the order (YYYY-MM-DD) (for mission orders)",
        end_date="End date for the order (YYYY-MM-DD) (for mission orders)",
        duration_days="Duration in days (for division and major orders)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Mission", value="mission"),
        app_commands.Choice(name="Division", value="division"),
        app_commands.Choice(name="Major", value="major")
    ])
    @app_commands.autocomplete(
        mission_type=autocomplete_mission_type_callback,
        division=autocomplete_division_callback,
        start_date=autocomplete_date_callback,
        end_date=autocomplete_date_callback
    )
    async def create_order(
        self,
        interaction: discord.Interaction,
        type: str,
        description: str,
        title: Optional[str] = None,
        mission_type: Optional[str] = None,
        division: Optional[str] = None,
        template: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        duration_days: Optional[int] = None
    ):
        """Create a new order of the specified type"""
        await interaction.response.defer()
        
        try:
            if type == "mission":
                # Validate mission parameters
                if not title:
                    await interaction.followup.send("❌ Mission orders require a title.", ephemeral=True)
                    return
                if not mission_type:
                    await interaction.followup.send("❌ Mission orders require a mission type.", ephemeral=True)
                    return
                if not start_date or not end_date:
                    await interaction.followup.send("❌ Mission orders require start and end dates.", ephemeral=True)
                    return
                    
                # Create mission order
                await self._create_mission_order_helper(
                    interaction, title, description, mission_type, start_date, end_date
                )
                
            elif type == "division":
                # Validate division parameters
                if not division:
                    await interaction.followup.send("❌ Division orders require a division.", ephemeral=True)
                    return
                if not template:
                    await interaction.followup.send("❌ Division orders require a template.", ephemeral=True)
                    return
                    
                # Create division order
                dur_days = duration_days if duration_days is not None else 14
                await self._create_division_order_helper(
                    interaction, division, template, description, dur_days
                )
                
            elif type == "major":
                # Validate major parameters
                if not template:
                    await interaction.followup.send("❌ Major orders require a template.", ephemeral=True)
                    return
                    
                # Create major order
                dur_days = duration_days if duration_days is not None else 30
                await self._create_major_order_helper(
                    interaction, template, description, dur_days
                )
                
            else:
                await interaction.followup.send(f"❌ Invalid order type: {type}", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            await interaction.followup.send(f"❌ An error occurred while creating the order: {str(e)}", ephemeral=True)
    
    @create_order.autocomplete('template')
    async def orders_template_autocomplete(self, interaction: discord.Interaction, current: str):
        """Dynamic autocomplete for templates based on order type and division"""
        order_type = interaction.namespace.type
        
        if order_type == "division":
            division = interaction.namespace.division
            if not division or division not in DIVISION_ORDER_TEMPLATES:
                return []
            return [
                app_commands.Choice(name=template, value=template)
                for template in DIVISION_ORDER_TEMPLATES[division]
                if current.lower() in template.lower()
            ][:25]
        elif order_type == "major":
            return [
                app_commands.Choice(name=template, value=template)
                for template in MAJOR_ORDER_TEMPLATES
                if current.lower() in template.lower()
            ][:25]
        else:
            return []

    @app_commands.command(name="complete_order", description="Mark an order as completed")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def complete_order(
        self,
        interaction: discord.Interaction,
        order_id: str,
        completion_notes: str
    ):
        await interaction.response.defer()
        try:
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            order.status = OrderStatus.COMPLETED
            order.completion_data = {
                'completed_by': interaction.user.id,
                'completed_at': datetime.now().isoformat(),
                'notes': completion_notes
            }
            self._save_orders()
            embed = await self.create_order_embed(order)
            
            # Update appropriate channel based on order type
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
                
            await interaction.followup.send(f"✅ Marked order as completed: {order.title}", embed=embed)
            
            # Record in profile system
            await self.record_order_completion(interaction.user.id, order, completion_notes)
            
        except Exception as e:
            logger.error(f"Error completing order: {e}")
            await interaction.followup.send(f"❌ An error occurred while completing the order: {str(e)}", ephemeral=True)

    async def autocomplete_order_id(self, interaction: discord.Interaction, current: str):
        order_ids = []
        
        # Add missions with status info
        for oid, order in self.scheduler._active_missions.items():
            status_emoji = self.get_status_emoji(order.status)
            display = f"{status_emoji} [Mission] {order.title}"
            if current.lower() in oid.lower() or current.lower() in order.title.lower():
                order_ids.append(app_commands.Choice(name=display, value=oid))
        
        # Add major orders with status info
        for oid, order in self.scheduler._major_orders.items():
            status_emoji = self.get_status_emoji(order.status)
            display = f"{status_emoji} [Major] {order.title}"
            if current.lower() in oid.lower() or current.lower() in order.title.lower():
                order_ids.append(app_commands.Choice(name=display, value=oid))
        
        # Add division orders with status info
        for oid, order in self.scheduler._division_orders.items():
            status_emoji = self.get_status_emoji(order.status)
            display = f"{status_emoji} [{order.division}] {order.title}"
            if current.lower() in oid.lower() or current.lower() in order.title.lower() or current.lower() in order.division.lower():
                order_ids.append(app_commands.Choice(name=display, value=oid))
            
        return order_ids[:25]

    @app_commands.command(name="view_order", description="View detailed information about a specific order")
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def view_order(
        self,
        interaction: discord.Interaction,
        order_id: str
    ):
        await interaction.response.defer()
        try:
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            embed = await self.create_order_embed(order)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error viewing order: {e}")
            await interaction.followup.send(f"❌ An error occurred while viewing the order: {str(e)}", ephemeral=True)

    @app_commands.command(name="add_objectives", description="Add objectives to an existing order")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def add_objectives(
        self,
        interaction: discord.Interaction,
        order_id: str,
        objectives: str
    ):
        await interaction.response.defer()
        try:
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            new_objectives = [obj.strip() for obj in objectives.split('\\n') if obj.strip()]
            if isinstance(order, (MissionOrder, DivisionOrder)):
                if not hasattr(order, 'objectives'):
                    order.objectives = []
                order.objectives.extend(new_objectives)
            elif isinstance(order, MajorOrder):
                if not hasattr(order, 'strategic_objectives'):
                    order.strategic_objectives = []
                order.strategic_objectives.extend(new_objectives)
            
            # Add progress update
            order.add_progress_update(
                interaction.user.id,
                f"Added {len(new_objectives)} new objectives"
            )
            
            self._save_orders()
            embed = await self.create_order_embed(order)
            
            # Update appropriate channel based on order type
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
                
            await interaction.followup.send(f"✅ Added {len(new_objectives)} objectives to order {order_id}", embed=embed)
        except Exception as e:
            logger.error(f"Error adding objectives: {e}")
            await interaction.followup.send(f"❌ An error occurred while adding objectives: {str(e)}", ephemeral=True)

    @app_commands.command(name="evaluate_orders", description="Evaluate completion status of all active orders")
    async def evaluate_orders(self, interaction: discord.Interaction):
        """Generate a report on order completion status"""
        await interaction.response.defer()
        
        try:
            embed = await self.create_evaluation_embed()
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error evaluating orders: {e}")
            await interaction.followup.send(f"❌ An error occurred while evaluating orders: {str(e)}", ephemeral=True)

    @app_commands.command(name="start_monthly_cycle", description="Start a new monthly cycle with coordinated orders")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(major_order_template=autocomplete_template_callback)
    async def start_monthly_cycle(
        self,
        interaction: discord.Interaction,
        major_order_template: str
    ):
        """Start a new monthly cycle with the specified major order"""
        await interaction.response.defer()
        
        try:
            # Check if there's already an active major order
            active_major_order = await self.scheduler.get_active_major_order()
            if active_major_order:
                confirm_view = discord.ui.View(timeout=60)
                
                async def confirm_callback(confirm_interaction: discord.Interaction):
                    if confirm_interaction.user.id != interaction.user.id:
                        await confirm_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                        return
                    
                    # Mark current active orders as expired
                    active_major_order.status = OrderStatus.EXPIRED
                    active_major_order.add_progress_update(
                        interaction.user.id,
                        "Expired early due to new monthly cycle"
                    )
                    
                    # Expire all active division orders
                    for order in self.scheduler._division_orders.values():
                        if order.status == OrderStatus.ACTIVE:
                            order.status = OrderStatus.EXPIRED
                    
                    # Now create the new cycle
                    await self.create_synchronized_monthly_orders(confirm_interaction, major_order_template)
                
                async def cancel_callback(cancel_interaction: discord.Interaction):
                    if cancel_interaction.user.id != interaction.user.id:
                        await cancel_interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
                        return
                    
                    await cancel_interaction.response.send_message("Monthly cycle creation cancelled.", ephemeral=True)
                
                confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
                confirm_button.callback = confirm_callback
                
                cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
                cancel_button.callback = cancel_callback
                
                confirm_view.add_item(confirm_button)
                confirm_view.add_item(cancel_button)
                
                await interaction.followup.send(
                    f"⚠️ There is already an active major order: **{active_major_order.title}**\n"
                    f"Starting a new cycle will expire all current orders. Continue?",
                    view=confirm_view,
                    ephemeral=True
                )
                return
            
            # If no active major order, create the new cycle
            await self.create_synchronized_monthly_orders(interaction, major_order_template)
            
        except Exception as e:
            logger.error(f"Error starting monthly cycle: {e}")
            await interaction.followup.send(f"❌ An error occurred while starting the monthly cycle: {str(e)}", ephemeral=True)
    
    async def create_synchronized_monthly_orders(self, interaction: discord.Interaction, major_order_template: str):
        """Create a synchronized set of orders for a new month (Major + Division orders)"""
        try:
            # Create Major Order first
            major_order = await self.scheduler.setup_new_monthly_cycle(
                major_order_template,
                interaction.user.id
            )
            
            if not major_order:
                await interaction.followup.send("❌ Failed to create major order.", ephemeral=True)
                return
            
            # Create matching Division Orders
            division_orders = await self.scheduler.create_synchronized_division_orders(
                major_order,
                interaction.user.id
            )
            
            # Create confirmation embed
            embed = discord.Embed(
                title=f"Monthly Plan: {major_order_template}",
                description=f"Created coordinated orders for the new month cycle",
                color=discord.Color.gold()
            )
            
            # Add major order details
            embed.add_field(
                name="Major Order",
                value=f"**{major_order.title}**\n{major_order.description}\nDue: <t:{int(major_order.end_date.timestamp())}:R>",
                inline=False
            )
            
            # Add division order details
            if division_orders:
                div_text = []
                for order in division_orders:
                    div_text.append(f"• **{order.division}**: {order.title}")
                
                embed.add_field(
                    name="Division Orders (Phase 1)",
                    value="\n".join(div_text),
                    inline=False
                )
            
            # Update channel messages
            major_embed = await self.create_order_embed(major_order)
            self.last_major_order_message = await self.update_channel_message(
                MAJOR_ORDERS_CHANNEL,
                major_embed,
                self.last_major_order_message
            )
            
            # Create combined division orders embed
            if division_orders:
                div_embed = discord.Embed(
                    title="🚩 Division Orders - Phase 1",
                    description=f"Supporting Major Order: {major_order.title}",
                    color=discord.Color.green()
                )
                
                for order in division_orders:
                    div_embed.add_field(
                        name=f"{order.division}: {order.title}",
                        value=f"{order.description}\nDue: <t:{int(order.end_date.timestamp())}:R>",
                        inline=False
                    )
                
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    div_embed,
                    self.last_division_order_message
                )
            
            # Save all changes
            self._save_orders()
            self._save_cycle()
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error creating synchronized orders: {e}")
            await interaction.followup.send(f"❌ An error occurred while creating orders: {str(e)}", ephemeral=True)
            
    @app_commands.command(name="add_progress_update", description="Add a progress update to an existing order")
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def add_progress_update(
        self,
        interaction: discord.Interaction,
        order_id: str,
        update_text: str
    ):
        """Add a progress update to an existing order"""
        await interaction.response.defer()
        
        try:
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
                
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            
            # Add progress update
            order.add_progress_update(interaction.user.id, update_text)
            
            # Add user as participant
            if hasattr(order, 'add_participant'):
                order.add_participant(interaction.user.id)
            
            self._save_orders()
            
            # Create updated embed
            embed = await self.create_order_embed(order)
            
            # Update channel message
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
            
            await interaction.followup.send("✅ Progress update added successfully.", embed=embed)
            
            # Record in profile system
            if order.order_type == OrderType.MISSION:
                await self.record_order_completion(
                    interaction.user.id,
                    order,
                    f"Participated in mission: {update_text}"
                )
            
        except Exception as e:
            logger.error(f"Error adding progress update: {e}")
            await interaction.followup.send(f"❌ An error occurred while adding the progress update: {str(e)}", ephemeral=True)
            
    @app_commands.command(name="list_active_orders", description="List all currently active orders")
    async def list_active_orders(self, interaction: discord.Interaction):
        """List all currently active orders"""
        await interaction.response.defer()
        
        try:
            # Get all active orders
            active_missions = [o for o in self.scheduler._active_missions.values() 
                              if o.status == OrderStatus.ACTIVE]
            active_division_orders = [o for o in self.scheduler._division_orders.values() 
                                     if o.status == OrderStatus.ACTIVE]
            active_major_orders = [o for o in self.scheduler._major_orders.values() 
                                  if o.status == OrderStatus.ACTIVE]
            
            # Create embed
            embed = discord.Embed(
                title="Active Orders",
                description=f"There are currently {len(active_missions) + len(active_division_orders) + len(active_major_orders)} active orders",
                color=discord.Color.blue()
            )
            
            # Add major orders
            if active_major_orders:
                major_text = []
                for order in active_major_orders:
                    major_text.append(f"• **{order.title}** (ID: `{order.order_id}`)\n  Due: <t:{int(order.end_date.timestamp())}:R>")
                
                embed.add_field(
                    name="Major Orders",
                    value="\n".join(major_text),
                    inline=False
                )
            
            # Add division orders
            if active_division_orders:
                div_text = []
                for order in active_division_orders:
                    div_text.append(f"• **{order.division}**: {order.title} (ID: `{order.order_id}`)\n  Due: <t:{int(order.end_date.timestamp())}:R>")
                
                embed.add_field(
                    name="Division Orders",
                    value="\n".join(div_text),
                    inline=False
                )
            
            # Add missions
            if active_missions:
                mission_text = []
                for order in active_missions:
                    mission_text.append(f"• **{order.title}** (ID: `{order.order_id}`)\n  Type: {order.mission_type}\n  Due: <t:{int(order.end_date.timestamp())}:R>")
                
                embed.add_field(
                    name="Weekly Missions",
                    value="\n".join(mission_text),
                    inline=False
                )
            
            # If no active orders
            if not (active_missions or active_division_orders or active_major_orders):
                embed.description = "There are currently no active orders."
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error listing active orders: {e}")
            await interaction.followup.send(f"❌ An error occurred while listing active orders: {str(e)}", ephemeral=True)
            
    @app_commands.command(name="refresh_order_messages", description="Refresh all order channel messages")
    @app_commands.default_permissions(administrator=True)
    async def refresh_order_messages_command(self, interaction: discord.Interaction):
        """Refresh all order channel messages"""
        await interaction.response.defer()
        
        try:
            # Call refresh method
            personal, major, division = await self.refresh_order_messages()
            
            # Create result message
            result = []
            if personal:
                result.append(f"✅ Refreshed personal order message")
            if major:
                result.append(f"✅ Refreshed major order message")
            if division:
                result.append(f"✅ Refreshed division order message")
                
            if not result:
                await interaction.followup.send("⚠️ No active orders to refresh", ephemeral=True)
            else:
                await interaction.followup.send("\n".join(result), ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error refreshing order messages: {e}")
            await interaction.followup.send(f"❌ An error occurred while refreshing messages: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="change_order_status", description="Change the status of an order")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    @app_commands.describe(
        order_id="The ID of the order to modify",
        new_status="The new status to set",
        status_note="Optional note explaining the status change"
    )
    async def change_order_status(
        self,
        interaction: discord.Interaction,
        order_id: str,
        new_status: str,
        status_note: str = ""
    ):
        """Change the status of an order"""
        await interaction.response.defer()
        
        try:
            # Find the order
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
                
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            
            # Validate and set new status
            try:
                new_status_enum = OrderStatus(new_status)
            except ValueError:
                status_options = ", ".join([s.value for s in OrderStatus])
                await interaction.followup.send(
                    f"❌ Invalid status. Valid options are: {status_options}", 
                    ephemeral=True
                )
                return
            
            # Record old status for message
            old_status = order.status
            
            # Update the status
            order.status = new_status_enum
            
            # Add progress update if note provided
            if status_note:
                order.add_progress_update(
                    interaction.user.id,
                    f"Status changed from {old_status.value} to {new_status_enum.value}: {status_note}"
                )
            else:
                order.add_progress_update(
                    interaction.user.id,
                    f"Status changed from {old_status.value} to {new_status_enum.value}"
                )
            
            # If completing, add completion data
            if new_status_enum == OrderStatus.COMPLETED:
                order.completion_data = {
                    'completed_by': interaction.user.id,
                    'completed_at': datetime.now().isoformat(),
                    'notes': status_note if status_note else f"Completed by {interaction.user.name}"
                }
                
                # Record completion in profile system
                await self.record_order_completion(
                    interaction.user.id,
                    order,
                    status_note if status_note else f"Completed by {interaction.user.name}"
                )
            
            self._save_orders()
            
            # Create updated embed
            embed = await self.create_order_embed(order)
            
            # Update channel message
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
            
            await interaction.followup.send(
                f"✅ Status changed from **{old_status.value}** to **{new_status_enum.value}**", 
                embed=embed
            )
            
        except Exception as e:
            logger.error(f"Error changing order status: {e}")
            await interaction.followup.send(f"❌ An error occurred while changing status: {str(e)}", ephemeral=True)
    
    @change_order_status.autocomplete('new_status')
    async def autocomplete_status(self, interaction: discord.Interaction, current: str):
        """Autocomplete for order status values"""
        return [
            app_commands.Choice(name=status.value, value=status.value)
            for status in OrderStatus
            if current.lower() in status.value.lower()
        ]
    
    @app_commands.command(name="cancel_order", description="Cancel an active order")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def cancel_order(
        self,
        interaction: discord.Interaction,
        order_id: str,
        reason: str = "No reason provided"
    ):
        """Cancel an active order with a reason"""
        await interaction.response.defer()
        
        try:
            # Find the order
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
                
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            
            # Add confirmation dialog for major orders
            if order.order_type == OrderType.MAJOR and not hasattr(interaction, '_confirmed'):
                confirm_view = discord.ui.View(timeout=30)
                
                async def confirm_callback(confirm_interaction: discord.Interaction):
                    if confirm_interaction.user.id != interaction.user.id:
                        await confirm_interaction.response.send_message(
                            "This confirmation is not for you.", 
                            ephemeral=True
                        )
                        return
                    
                    # Set flag to avoid confirmation loop
                    setattr(confirm_interaction, '_confirmed', True)
                    
                    # Call command again with confirmation
                    await self.cancel_order(confirm_interaction, order_id, reason)
                
                async def cancel_callback(cancel_interaction: discord.Interaction):
                    if cancel_interaction.user.id != interaction.user.id:
                        await cancel_interaction.response.send_message(
                            "This confirmation is not for you.", 
                            ephemeral=True
                        )
                        return
                    
                    await cancel_interaction.response.send_message("Order cancellation aborted.", ephemeral=True)
                
                confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
                confirm_button.callback = confirm_callback
                
                cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
                cancel_button.callback = cancel_callback
                
                confirm_view.add_item(confirm_button)
                confirm_view.add_item(cancel_button)
                
                await interaction.followup.send(
                    f"⚠️ You're about to cancel a **{order.order_type.value}** order. This may impact associated orders. Continue?",
                    view=confirm_view,
                    ephemeral=True
                )
                return
            
            # Update the status
            old_status = order.status
            order.status = OrderStatus.CANCELLED
            
            # Add update
            order.add_progress_update(
                interaction.user.id,
                f"Order cancelled: {reason}"
            )
            
            self._save_orders()
            
            # Create updated embed
            embed = await self.create_order_embed(order)
            
            # Update channel message
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
            
            await interaction.followup.send(
                f"✅ Order cancelled. Status changed from **{old_status.value}** to **{OrderStatus.CANCELLED.value}**", 
                embed=embed
            )
            
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            await interaction.followup.send(f"❌ An error occurred while cancelling the order: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="set_order_due_date", description="Set a new due date for an order")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    @app_commands.autocomplete(new_date=autocomplete_date_callback)
    async def set_order_due_date(
        self,
        interaction: discord.Interaction,
        order_id: str,
        new_date: str,
        reason: str = "No reason provided"
    ):
        """Set a new due date for an order"""
        await interaction.response.defer()
        
        try:
            # Find the order
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
                
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            
            # Parse new date
            try:
                new_end_date = datetime.fromisoformat(new_date)
            except ValueError:
                try:
                    # Try alternate format
                    new_end_date = datetime.strptime(new_date, '%Y-%m-%d')
                except ValueError:
                    await interaction.followup.send(
                        "❌ Invalid date format. Use YYYY-MM-DD format.", 
                        ephemeral=True
                    )
                    return
            
            # Store old date for message
            old_end_date = order.end_date
            
            # Update the due date
            order.end_date = new_end_date
            
            # Add update
            order.add_progress_update(
                interaction.user.id,
                f"Due date changed from {old_end_date.strftime('%Y-%m-%d')} to {new_end_date.strftime('%Y-%m-%d')}: {reason}"
            )
            
            self._save_orders()
            
            # Create updated embed
            embed = await self.create_order_embed(order)
            
            # Update channel message
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
            
            await interaction.followup.send(
                f"✅ Due date changed from **{old_end_date.strftime('%Y-%m-%d')}** to **{new_end_date.strftime('%Y-%m-%d')}**", 
                embed=embed
            )
            
        except Exception as e:
            logger.error(f"Error setting order due date: {e}")
            await interaction.followup.send(f"❌ An error occurred while setting the due date: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="order_status_report", description="Generate a status report of all active orders")
    async def order_status_report(self, interaction: discord.Interaction):
        """Generate a comprehensive status report of all orders"""
        await interaction.response.defer()
        
        try:
            # Get all orders grouped by status
            active_orders = []
            pending_orders = []
            completed_orders = []
            expired_orders = []
            
            # Process mission orders
            for order in self.scheduler._active_missions.values():
                if order.status == OrderStatus.ACTIVE:
                    active_orders.append(order)
                elif order.status == OrderStatus.PENDING:
                    pending_orders.append(order)
                elif order.status == OrderStatus.COMPLETED:
                    completed_orders.append(order)
                elif order.status == OrderStatus.EXPIRED:
                    expired_orders.append(order)
            
            # Process major orders
            for order in self.scheduler._major_orders.values():
                if order.status == OrderStatus.ACTIVE:
                    active_orders.append(order)
                elif order.status == OrderStatus.PENDING:
                    pending_orders.append(order)
                elif order.status == OrderStatus.COMPLETED:
                    completed_orders.append(order)
                elif order.status == OrderStatus.EXPIRED:
                    expired_orders.append(order)
            
            # Process division orders
            for order in self.scheduler._division_orders.values():
                if order.status == OrderStatus.ACTIVE:
                    active_orders.append(order)
                elif order.status == OrderStatus.PENDING:
                    pending_orders.append(order)
                elif order.status == OrderStatus.COMPLETED:
                    completed_orders.append(order)
                elif order.status == OrderStatus.EXPIRED:
                    expired_orders.append(order)
            
            # Create embed
            embed = discord.Embed(
                title="📊 Order Status Report",
                description=f"Current status of all orders as of {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                color=discord.Color.blue()
            )
            
            # Add active orders
            if active_orders:
                active_text = []
                for order in sorted(active_orders, key=lambda o: o.end_date):
                    emoji = self.get_order_emoji(order)
                    order_type = order.order_type.value
                    if order.order_type == OrderType.DIVISION:
                        order_type = f"{order_type} ({order.division})"
                    active_text.append(f"{emoji} **{order.title}** - {order_type}\n  Due: <t:{int(order.end_date.timestamp())}:R>")
                
                embed.add_field(
                    name=f"🟢 Active Orders ({len(active_orders)})",
                    value="\n".join(active_text[:10]) + (f"\n...and {len(active_orders) - 10} more" if len(active_orders) > 10 else ""),
                    inline=False
                )
            
            # Add pending orders
            if pending_orders:
                embed.add_field(
                    name=f"🟡 Pending Orders ({len(pending_orders)})",
                    value=f"There are {len(pending_orders)} orders waiting to be activated",
                    inline=False
                )
            
            # Add recent completions
            if completed_orders:
                # Sort by completion date, most recent first
                sorted_completions = sorted(
                    [o for o in completed_orders if 'completed_at' in o.completion_data],
                    key=lambda o: o.completion_data.get('completed_at', ''),
                    reverse=True
                )
                
                completion_text = []
                for order in sorted_completions[:5]:  # Show only 5 most recent
                    emoji = self.get_order_emoji(order)
                    completed_at = order.completion_data.get('completed_at', 'Unknown')
                    if completed_at != 'Unknown':
                        try:
                            completed_dt = datetime.fromisoformat(completed_at)
                            completed_at = f"<t:{int(completed_dt.timestamp())}:R>"
                        except:
                            pass
                    completion_text.append(f"{emoji} **{order.title}** - Completed {completed_at}")
                
                if completion_text:
                    embed.add_field(
                        name=f"✅ Recent Completions",
                        value="\n".join(completion_text),
                        inline=False
                    )
            
            # Add expired orders stats
            if expired_orders:
                embed.add_field(
                    name=f"⏱️ Expired Orders",
                    value=f"There are {len(expired_orders)} expired orders",
                    inline=False
                )
            
            # Add monthly cycle info
            monthly_goal_met, completion_pct, details = await self.scheduler.evaluate_monthly_progress()
            cycle = self.scheduler.monthly_cycle
            
            # Create progress bar
            bar_length = 20
            filled = int(bar_length * completion_pct / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            embed.add_field(
                name="Monthly Progress",
                value=f"Week: {cycle.current_week + 1}/4\n"
                      f"Progress: **{completion_pct:.1f}%**\n"
                      f"{bar}",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error generating order status report: {e}")
            await interaction.followup.send(f"❌ An error occurred while generating the report: {str(e)}", ephemeral=True)
            
    @app_commands.command(name="cleanup_expired_orders", description="Archive or remove expired orders")
    @app_commands.default_permissions(administrator=True)
    async def cleanup_expired_orders(self, interaction: discord.Interaction, days_threshold: int = 7):
        """Clean up orders that have been expired for more than the specified number of days"""
        await interaction.response.defer()
        
        try:
            now = datetime.now()
            threshold = now - timedelta(days=days_threshold)
            
            # Count orders to clean up
            mission_count = 0
            major_count = 0
            division_count = 0
            
            # Clean up mission orders
            for order_id, order in list(self.scheduler._active_missions.items()):
                if order.status == OrderStatus.EXPIRED and order.end_date < threshold:
                    self.scheduler._active_missions.pop(order_id)
                    mission_count += 1
            
            # Clean up major orders
            for order_id, order in list(self.scheduler._major_orders.items()):
                if order.status == OrderStatus.EXPIRED and order.end_date < threshold:
                    self.scheduler._major_orders.pop(order_id)
                    major_count += 1
            
            # Clean up division orders
            for order_id, order in list(self.scheduler._division_orders.items()):
                if order.status == OrderStatus.EXPIRED and order.end_date < threshold:
                    self.scheduler._division_orders.pop(order_id)
                    division_count += 1
            
            # Save changes
            self._save_orders()
            
            total_cleaned = mission_count + major_count + division_count
            
            if total_cleaned > 0:
                await interaction.followup.send(
                    f"✅ Cleaned up {total_cleaned} expired orders:\n"
                    f"• {mission_count} mission orders\n"
                    f"• {major_count} major orders\n"
                    f"• {division_count} division orders"
                )
            else:
                await interaction.followup.send(
                    f"ℹ️ No expired orders older than {days_threshold} days found."
                )
            
        except Exception as e:
            logger.error(f"Error cleaning up expired orders: {e}")
            await interaction.followup.send(f"❌ An error occurred while cleaning up orders: {str(e)}", ephemeral=True)

    @app_commands.command(name="contribute_to_order", description="Record your contribution to an order")
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def contribute_to_order(
        self,
        interaction: discord.Interaction,
        order_id: str,
        contribution_text: str
    ):
        """Record your own contribution to an existing order"""
        await interaction.response.defer()
        
        try:
            # Find the order
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
                
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            
            # Make sure the order is active
            if order.status != OrderStatus.ACTIVE:
                await interaction.followup.send(f"❌ You can only contribute to active orders. This order's status is {order.status.value}.", ephemeral=True)
                return
            
            # Add progress update
            contribution_update = f"Contribution: {contribution_text}"
            order.add_progress_update(interaction.user.id, contribution_update)
            
            # Add user as participant
            if hasattr(order, 'add_participant'):
                order.add_participant(interaction.user.id)
            
            self._save_orders()
            
            # Create updated embed
            embed = await self.create_order_embed(order)
            
            # Update channel message
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
            
            # Create a simpler embed for the response
            contribution_embed = discord.Embed(
                title=f"Contribution Recorded - {order.title}",
                description=f"Your contribution to this order has been recorded.",
                color=discord.Color.green()
            )
            contribution_embed.add_field(
                name="Your Contribution",
                value=contribution_text,
                inline=False
            )
            contribution_embed.add_field(
                name="Order Type",
                value=order.order_type.value,
                inline=True
            )
            if isinstance(order, DivisionOrder):
                contribution_embed.add_field(
                    name="Division",
                    value=order.division,
                    inline=True
                )
            
            await interaction.followup.send(embed=contribution_embed)
            
            # Record in profile system
            await self.record_order_completion(
                interaction.user.id,
                order,
                f"Contributed: {contribution_text}"
            )
            
        except Exception as e:
            logger.error(f"Error recording contribution to order: {e}")
            await interaction.followup.send(f"❌ An error occurred while recording your contribution: {str(e)}", ephemeral=True)
            
    @app_commands.command(name="record_member_contribution", description="Record another member's contribution to an order")
    @app_commands.default_permissions(administrator=True)
    @app_commands.autocomplete(order_id=autocomplete_order_id_callback)
    async def record_member_contribution(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        order_id: str,
        contribution_text: str
    ):
        """Record another member's contribution to an existing order (admin only)"""
        await interaction.response.defer()
        
        try:
            # Find the order
            order = None
            if order_id in self.scheduler._active_missions:
                order = self.scheduler._active_missions[order_id]
            elif order_id in self.scheduler._major_orders:
                order = self.scheduler._major_orders[order_id]
            elif order_id in self.scheduler._division_orders:
                order = self.scheduler._division_orders[order_id]
                
            if not order:
                await interaction.followup.send("❌ Order not found.", ephemeral=True)
                return
            
            # Add progress update
            contribution_update = f"Contribution by {member.name}: {contribution_text}"
            order.add_progress_update(member.id, contribution_update)
            
            # Add user as participant
            if hasattr(order, 'add_participant'):
                order.add_participant(member.id)
            
            self._save_orders()
            
            # Create updated embed
            embed = await self.create_order_embed(order)
            
            # Update channel message
            if order.order_type == OrderType.MISSION:
                self.last_personal_order_message = await self.update_channel_message(
                    PERSONAL_ORDERS_CHANNEL,
                    embed,
                    self.last_personal_order_message
                )
            elif order.order_type == OrderType.MAJOR:
                self.last_major_order_message = await self.update_channel_message(
                    MAJOR_ORDERS_CHANNEL,
                    embed,
                    self.last_major_order_message
                )
            elif order.order_type == OrderType.DIVISION:
                self.last_division_order_message = await self.update_channel_message(
                    DIVISION_ORDERS_CHANNEL,
                    embed,
                    self.last_division_order_message
                )
            
            # Create a simpler embed for the response
            contribution_embed = discord.Embed(
                title=f"Member Contribution Recorded - {order.title}",
                description=f"You've recorded a contribution for {member.mention} to this order.",
                color=discord.Color.green()
            )
            contribution_embed.add_field(
                name="Member",
                value=member.mention,
                inline=True
            )
            contribution_embed.add_field(
                name="Contribution",
                value=contribution_text,
                inline=False
            )
            contribution_embed.add_field(
                name="Order Type",
                value=order.order_type.value,
                inline=True
            )
            if isinstance(order, DivisionOrder):
                contribution_embed.add_field(
                    name="Division",
                    value=order.division,
                    inline=True
                )
            
            await interaction.followup.send(embed=contribution_embed)
            
            # Record in profile system
            await self.record_order_completion(
                member.id,
                order,
                f"Contribution recorded by {interaction.user.name}: {contribution_text}"
            )
            
        except Exception as e:
            logger.error(f"Error recording member contribution to order: {e}")
            await interaction.followup.send(f"❌ An error occurred while recording the contribution: {str(e)}", ephemeral=True)
            
    @app_commands.command(name="list_member_contributions", description="List a member's contributions to orders")
    @app_commands.default_permissions(administrator=True)
    async def list_member_contributions(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):
        """List contributions made by a member (or yourself if no member specified)"""
        await interaction.response.defer()
        
        try:
            # If no member specified, use the command invoker
            if member is None:
                member = interaction.user
            
            # Find all orders where this member is a participant
            member_orders = []
            
            # Check each type of order
            for order in self.scheduler._active_missions.values():
                if member.id in order.participants:
                    member_orders.append(order)
                    
            for order in self.scheduler._major_orders.values():
                if member.id in order.participants:
                    member_orders.append(order)
                    
            for order in self.scheduler._division_orders.values():
                if member.id in order.participants:
                    member_orders.append(order)
            
            if not member_orders:
                if member.id == interaction.user.id:
                    await interaction.followup.send("You haven't contributed to any orders yet.", ephemeral=True)
                else:
                    await interaction.followup.send(f"{member.name} hasn't contributed to any orders yet.", ephemeral=True)
                return
            
            # Create an embed to list the contributions
            embed = discord.Embed(
                title=f"Order Contributions - {member.name}",
                description=f"Showing contributions made by {member.mention} to orders",
                color=discord.Color.blue()
            )
            
            # Group orders by type
            mission_orders = [o for o in member_orders if o.order_type == OrderType.MISSION]
            major_orders = [o for o in member_orders if o.order_type == OrderType.MAJOR]
            division_orders = [o for o in member_orders if o.order_type == OrderType.DIVISION]
            
            # Add fields for each type, sorted by most recent
            if mission_orders:
                mission_text = []
                for order in sorted(mission_orders, key=lambda o: o.end_date, reverse=True)[:5]:
                    status_emoji = self.get_status_emoji(order.status)
                    # Get this member's contributions from progress updates
                    member_updates = [u for u in order.progress_updates if u.get('update_by') == member.id]
                    if member_updates:
                        latest_update = member_updates[-1]
                        mission_text.append(f"{status_emoji} **{order.title}** - {latest_update.get('update_text', 'No details')}")
                    else:
                        mission_text.append(f"{status_emoji} **{order.title}** - Participated")
                
                embed.add_field(
                    name=f"Mission Orders ({len(mission_orders)})",
                    value="\n".join(mission_text) if mission_text else "No contributions found",
                    inline=False
                )
            
            if major_orders:
                major_text = []
                for order in sorted(major_orders, key=lambda o: o.end_date, reverse=True)[:5]:
                    status_emoji = self.get_status_emoji(order.status)
                    # Get this member's contributions from progress updates
                    member_updates = [u for u in order.progress_updates if u.get('update_by') == member.id]
                    if member_updates:
                        latest_update = member_updates[-1]
                        major_text.append(f"{status_emoji} **{order.title}** - {latest_update.get('update_text', 'No details')}")
                    else:
                        major_text.append(f"{status_emoji} **{order.title}** - Participated")
                
                embed.add_field(
                    name=f"Major Orders ({len(major_orders)})",
                    value="\n".join(major_text) if major_text else "No contributions found",
                    inline=False
                )
            
            if division_orders:
                div_text = []
                for order in sorted(division_orders, key=lambda o: o.end_date, reverse=True)[:5]:
                    status_emoji = self.get_status_emoji(order.status)
                    # Get this member's contributions from progress updates
                    member_updates = [u for u in order.progress_updates if u.get('update_by') == member.id]
                    if member_updates:
                        latest_update = member_updates[-1]
                        div_text.append(f"{status_emoji} **{order.division}: {order.title}** - {latest_update.get('update_text', 'No details')}")
                    else:
                        div_text.append(f"{status_emoji} **{order.division}: {order.title}** - Participated")
                
                embed.add_field(
                    name=f"Division Orders ({len(division_orders)})",
                    value="\n".join(div_text) if div_text else "No contributions found",
                    inline=False
                )
            
            # Add total count
            embed.set_footer(text=f"Total Orders: {len(member_orders)} | Showing most recent 5 per category")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error listing member contributions: {e}")
            await interaction.followup.send(f"❌ An error occurred while listing contributions: {str(e)}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(OrdersCog(bot))
