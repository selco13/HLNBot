# cogs/eval.py
from __future__ import annotations
from typing import Dict, List, Optional, Any, Set, Tuple, TYPE_CHECKING

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import os
from datetime import datetime, timedelta, timezone
import json
import pytz
from enum import Enum

# Import BaseCog instead of using commands.Cog directly
from .utils.base_cog import BaseCog

if TYPE_CHECKING:
    from .utils.profile_utils import calculate_activity_score
    from .utils.profile_events import ProfileEvent, ProfileEventType
    from .utils.sc_profile_types import (
        SCProfile, CareerPath, ExperienceLevel,
        StarCitizenMetrics
    )

# Configure logging
logger = logging.getLogger('evaluation')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='evaluation.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

GUILD_ID = int(os.getenv('GUILD_ID'))

# Command Staff roles that can perform evaluations
COMMAND_STAFF_ROLES = [
    'Admiral',
    'Vice Admiral',
    'Rear Admiral',
    'Commodore',
    'Fleet Captain',
    'Captain'
]

class EvalCategory(Enum):
    LEADERSHIP = "Leadership"
    TEAMWORK = "Teamwork"
    COMBAT = "Combat Skills"
    MISSION = "Mission Success"
    ATTENDANCE = "Mission Attendance"
    COMMUNICATION = "Communication"
    LOGISTICS = "Logistics"
    TACTICS = "Tactical Knowledge"

class EvalPeriod(Enum):
    MONTHLY = "Monthly"
    QUARTERLY = "Quarterly"
    YEARLY = "Yearly"
    PROMOTION = "Promotion Review"

class EvaluationRecord:
    def __init__(self, member_id: int, evaluator_id: int, period: EvalPeriod):
        self.member_id = member_id
        self.evaluator_id = evaluator_id
        self.period = period
        self.date = datetime.now(timezone.utc)
        self.scores: Dict[EvalCategory, int] = {}
        self.comments: Dict[EvalCategory, str] = {}
        self.recommendations: str = ""
        self.goals: List[str] = []
        self.promotion_recommended: bool = False

    def to_dict(self) -> dict:
        return {
            'member_id': self.member_id,
            'evaluator_id': self.evaluator_id,
            'period': self.period.value,
            'date': self.date.isoformat(),
            'scores': {cat.value: score for cat, score in self.scores.items()},
            'comments': {cat.value: comment for cat, comment in self.comments.items()},
            'recommendations': self.recommendations,
            'goals': self.goals,
            'promotion_recommended': self.promotion_recommended
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'EvaluationRecord':
        period_str = data['period']
        period = next((p for p in EvalPeriod if p.value == period_str), None)
        if period is None:
            raise ValueError(f"Invalid period value: {period_str}")

        record = cls(
            member_id=data['member_id'],
            evaluator_id=data['evaluator_id'],
            period=period
        )
        record.date = datetime.fromisoformat(data['date'])

        record.scores = {}
        for cat_str, score in data['scores'].items():
            category_enum = next((c for c in EvalCategory if c.value == cat_str), None)
            if category_enum is None:
                raise ValueError(f"Invalid category value: {cat_str}")
            record.scores[category_enum] = score

        record.comments = {}
        for cat_str, comment in data['comments'].items():
            category_enum = next((c for c in EvalCategory if c.value == cat_str), None)
            if category_enum is None:
                raise ValueError(f"Invalid category value: {cat_str}")
            record.comments[category_enum] = comment

        record.recommendations = data['recommendations']
        record.goals = data['goals']
        record.promotion_recommended = data['promotion_recommended']
        return record

class EvalModal(discord.ui.Modal):
    def __init__(self, cog: 'EvaluationCog', member: discord.Member, category: EvalCategory):
        super().__init__(title=f"Evaluation - {category.value}")
        self.cog = cog
        self.member = member
        self.category = category
        
        self.score = discord.ui.TextInput(
            label="Score (1-10)",
            placeholder="Enter score from 1-10",
            min_length=1,
            max_length=2,
            required=True
        )
        self.add_item(self.score)
        
        self.comment = discord.ui.TextInput(
            label="Comments",
            placeholder="Enter detailed feedback...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.comment)

        self._add_role_fields()

    def _add_role_fields(self):
        """Add fields based on evaluation category."""
        if self.category == EvalCategory.COMBAT:
            self.add_item(
                discord.ui.TextInput(
                    label="Combat Metrics",
                    placeholder="K/D ratio, accuracy, etc.",
                    required=False
                )
            )
        elif self.category == EvalCategory.MISSION:
            self.add_item(
                discord.ui.TextInput(
                    label="Mission Success Rate",
                    placeholder="Percentage of successful missions",
                    required=False
                )
            )

    async def on_submit(self, interaction: discord.Interaction):
        profile = None
        if self.cog.profile_cog:
            profile = await self.cog.profile_cog.get_profile(self.member.id)

        try:
            score = int(self.score.value)
            if not 1 <= score <= 10:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid score between 1 and 10",
                ephemeral=True
            )
            return

        success, error = await self.cog.evaluate_member(
            self.member,
            interaction.user,
            {self.category: score},
            {self.category: self.comment.value}
        )

        if success:
            await interaction.response.send_message(
                f"Evaluation for {self.member.mention} recorded successfully!",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Error recording evaluation: {error}",
                ephemeral=True
            )

class EvalView(discord.ui.View):
    def __init__(self, cog: 'EvaluationCog', member: discord.Member):
        super().__init__(timeout=180)
        self.cog = cog
        self.member = member
        self.record = EvaluationRecord(member.id, None, EvalPeriod.MONTHLY)

        for category in EvalCategory:
            button = discord.ui.Button(
                label=category.value, 
                style=discord.ButtonStyle.primary,
                custom_id=f"eval_{category.name}"
            )
            button.callback = self.create_category_callback(category)
            self.add_item(button)

        submit_button = discord.ui.Button(
            label="Complete Evaluation",
            style=discord.ButtonStyle.success,
            custom_id="eval_submit"
        )
        submit_button.callback = self.submit_callback
        self.add_item(submit_button)

    def create_category_callback(self, category: EvalCategory):
        async def callback(interaction: discord.Interaction):
            if not self.cog.has_command_staff_role(interaction.user):
                await interaction.response.send_message(
                    "Only Command Staff can perform evaluations.",
                    ephemeral=True
                )
                return

            modal = EvalModal(self.cog, self.member, category)
            await interaction.response.send_modal(modal)
            await modal.wait()
            
            if not modal.is_finished():
                await interaction.followup.send("Evaluation canceled or timed out.", ephemeral=True)
                return
            
            try:
                self.record.scores[category] = int(modal.score.value)
                self.record.comments[category] = modal.comment.value
            except ValueError:
                await interaction.followup.send("Invalid score entered.", ephemeral=True)
                return

            for item in self.children:
                if item.custom_id == f"eval_{category.name}":
                    item.style = discord.ButtonStyle.success
                    break
                    
            await interaction.message.edit(view=self)
        return callback

    async def submit_callback(self, interaction: discord.Interaction):
        if not self.cog.has_command_staff_role(interaction.user):
            await interaction.response.send_message(
                "Only Command Staff can perform evaluations.",
                ephemeral=True
            )
            return

        if len(self.record.scores) != len(EvalCategory):
            await interaction.response.send_message(
                "Please complete all evaluation categories before submitting.",
                ephemeral=True
            )
            return

        self.record.evaluator_id = interaction.user.id
        await self.cog.save_evaluation(self.record)
        await self.cog.send_evaluation_summary(interaction, self.record)
        self.stop()

# Changed to inherit from BaseCog instead of commands.Cog
class EvaluationCog(BaseCog):
    def __init__(self, bot: commands.Bot):
        # Call BaseCog's __init__ method
        super().__init__(bot)
        
        # Use property accessors from BaseCog instead of direct bot attributes
        self.coda = self.coda_client
        self._profile_cog = None
        self.evaluations = {}
        self.eval_reminder.start()

    @property
    def profile_cog(self):
        if self._profile_cog is None:
            self._profile_cog = self.bot.get_cog('ProfileManagerCog')
        return self._profile_cog

    def cog_unload(self):
        self.eval_reminder.cancel()

    def has_command_staff_role(self, member: discord.Member) -> bool:
        return any(role.name in COMMAND_STAFF_ROLES for role in member.roles)

    async def evaluate_member(
        self,
        member: discord.Member,
        evaluator: discord.Member,
        scores: Dict[EvalCategory, int],
        comments: Dict[EvalCategory, str]
    ) -> Tuple[bool, Optional[str]]:
        try:
            # Create evaluation record
            record = EvaluationRecord(
                member_id=member.id,
                evaluator_id=evaluator.id,
                period=EvalPeriod.MONTHLY
            )
            record.scores = scores
            record.comments = comments

            # Queue profile update using profile_sync service
            await self.profile_sync.queue_update(
                ProfileEvent(
                    event_type=ProfileEventType.EVALUATION_COMPLETE,
                    member_id=member.id,
                    timestamp=datetime.now(timezone.utc),
                    data={
                        'evaluation_scores': scores,
                        'evaluation_comments': comments,
                        'metrics': await self._calculate_eval_metrics(record),
                        'evaluator_id': evaluator.id
                    }
                )
            )

            # Log the action using audit_logger service
            await self.audit_logger.log_action(
                'evaluation_complete',
                evaluator,
                member,
                f"Evaluation completed with average score {sum(scores.values())/len(scores):.2f}"
            )
            
            return True, None

        except Exception as e:
            logger.error(f"Error in evaluation: {e}")
            return False, str(e)

    async def _calculate_eval_metrics(
        self,
        record: EvaluationRecord
    ) -> Dict[str, Any]:
        metrics = {}
        
        for category, score in record.scores.items():
            metrics[f"{category.value.lower()}_rating"] = score

        avg_score = sum(record.scores.values()) / len(record.scores)
        metrics['overall_performance'] = avg_score

        strengths = [
            cat.value for cat, score in record.scores.items()
            if score >= 8
        ]
        improvements = [
            cat.value for cat, score in record.scores.items()
            if score <= 5
        ]
        
        metrics['strengths'] = strengths
        metrics['areas_for_improvement'] = improvements

        return metrics

    async def recommend_promotion(
        self,
        member: discord.Member,
        recommended_by: discord.Member,
        reason: str,
        achievements: List[str]
    ) -> Tuple[bool, Optional[str]]:
        try:
            if not self.profile_cog:
                return False, "Profile system not available"

            profile = await self.profile_cog.get_profile(member.id)
            if not profile:
                return False, "Profile not found"

            from .constants import RANKS, RANK_NUMBERS
            current_rank_idx = RANK_NUMBERS.get(profile.rank, 0)
            if current_rank_idx >= len(RANKS) - 1:
                return False, "Already at maximum rank"

            # Use profile_cog's sync_manager directly
            await self.profile_cog.sync_manager.queue_update(
                ProfileEvent(
                    event_type=ProfileEventType.RANK_UPDATED,
                    member_id=member.id,
                    timestamp=datetime.now(timezone.utc),
                    data={
                        'promotion_reason': reason,
                        'promotion_achievements': achievements,
                        'recommended_by': recommended_by.id,
                        'current_rank': profile.rank,
                        'recommended_rank': RANKS[current_rank_idx + 1][0]
                    },
                    actor_id=recommended_by.id,
                    reason="Promotion Recommendation"
                )
            )

            return True, None

        except Exception as e:
            logger.error(f"Error recommending promotion: {e}")
            return False, str(e)

    @tasks.loop(hours=24)
    async def eval_reminder(self):
        """Send reminders for pending evaluations."""
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return

        current_date = datetime.now(pytz.UTC)
        
        for member_id, records in self.evaluations.items():
            if not records:
                continue
                
            last_eval = max(records, key=lambda r: r.date)
            if last_eval.date.tzinfo is None:
                last_eval_date = last_eval.date.replace(tzinfo=pytz.UTC)
            else:
                last_eval_date = last_eval.date
                
            days_since_eval = (current_date - last_eval_date).days
            
            if days_since_eval >= 30:
                member = guild.get_member(member_id)
                if member:
                    channel = await self.get_eval_channel(guild)
                    if channel:
                        await channel.send(
                            f"⚠️ Evaluation reminder: {member.mention} is due for their monthly evaluation."
                        )

    async def get_eval_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get or create evaluation channel."""
        channel = discord.utils.get(guild.channels, name="evaluations")
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
            
            for role_name in COMMAND_STAFF_ROLES:
                role = discord.utils.get(guild.roles, name=role_name)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await guild.create_text_channel('evaluations', overwrites=overwrites)
        return channel

    async def save_evaluation(self, record: EvaluationRecord):
        """Save evaluation record to persistent state storage."""
        # Use state_manager if available
        if self.state_manager:
            # Store evaluation in the state manager
            member_evals = await self.state_manager.get('evaluations', str(record.member_id), [])
            member_evals.append(record.to_dict())
            await self.state_manager.set('evaluations', str(record.member_id), member_evals)
            logger.info(f"Saved evaluation for member {record.member_id} using state manager")
        else:
            # Legacy storage in instance variable
            if record.member_id not in self.evaluations:
                self.evaluations[record.member_id] = []
            self.evaluations[record.member_id].append(record)
            logger.info(f"Saved evaluation for member {record.member_id} using instance storage")
            
        # Dispatch an event for other cogs to react to
        await self.dispatch_event('evaluation_saved', 
                                 member_id=record.member_id,
                                 evaluator_id=record.evaluator_id,
                                 scores=record.scores,
                                 date=record.date)

    async def send_evaluation_summary(self, interaction: discord.Interaction, record: EvaluationRecord):
        """Send evaluation summary to designated channel."""
        guild = interaction.guild
        member = guild.get_member(record.member_id)

        embed = discord.Embed(
            title=f"Evaluation Summary - {member.display_name if member else 'Unknown'}",
            description=f"Period: {record.period.value}\nDate: {record.date.strftime('%Y-%m-%d')}",
            color=discord.Color.blue()
        )
        
        scores_text = ""
        for category, score in record.scores.items():
            scores_text += f"{category.value}: {score}/10\n"
        embed.add_field(name="Scores", value=scores_text, inline=False)
        
        for category, comment in record.comments.items():
            embed.add_field(name=f"{category.value} Comments", value=comment, inline=False)
        
        if record.recommendations:
            embed.add_field(name="Recommendations", value=record.recommendations, inline=False)
        
        if record.goals:
            embed.add_field(name="Goals", value="\n".join(f"• {goal}" for goal in record.goals), inline=False)
        
        channel = await self.get_eval_channel(guild)
        await channel.send(embed=embed)
        
        await interaction.response.send_message(
            "Evaluation completed and saved successfully!", 
            ephemeral=True
        )

    @app_commands.command(
        name="evaluate",
        description="Start a member evaluation"
    )
    # Removed @app_commands.guilds(discord.Object(id=GUILD_ID)) so it can sync globally
    @app_commands.describe(
        member="Member to evaluate",
        period="Evaluation period"
    )
    async def evaluate(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        period: EvalPeriod
    ):
        """Start a new member evaluation."""
        # Log command usage
        self.log_command_use(interaction, "evaluate")
        
        if not self.has_command_staff_role(interaction.user):
            await interaction.response.send_message(
                "Only Command Staff can perform evaluations.",
                ephemeral=True
            )
            return

        view = EvalView(self, member)
        view.record.period = period

        await interaction.response.send_message(
            f"Starting evaluation for {member.mention}",
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="view_evals",
        description="View evaluation history for a member"
    )
    # Removed @app_commands.guilds(discord.Object(id=GUILD_ID)) so it can sync globally
    @app_commands.describe(
        member="Member to view evaluations for",
        include_metrics="Include detailed metrics in the view"
    )
    async def view_evals(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        include_metrics: bool = False
    ):
        """View evaluation history for a member."""
        # Log command usage
        self.log_command_use(interaction, "view_evals")
        
        if not self.has_command_staff_role(interaction.user):
            await interaction.response.send_message(
                "Only Command Staff can view evaluations.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        embeds = []
        profile = None
        if self.profile_cog:
            profile = await self.profile_cog.get_profile(member.id)

        # Try to get evaluations from state manager first
        evals = []
        if self.state_manager:
            stored_evals = await self.state_manager.get('evaluations', str(member.id), [])
            for eval_dict in stored_evals:
                evals.append(EvaluationRecord.from_dict(eval_dict))
        else:
            # Fall back to instance variable storage
            evals = self.evaluations.get(member.id, [])
            
        if not evals:
            await interaction.followup.send(
                f"No evaluations found for {member.mention}",
                ephemeral=True
            )
            return

        base_embed = discord.Embed(
            title=f"Evaluation History: {member.display_name}",
            color=discord.Color.blue()
        )

        if profile:
            from .constants import RANKS, RANK_NUMBERS
            base_embed.add_field(
                name="Current Status",
                value=(
                    f"**Rank:** {profile.rank}\n"
                    f"**Division:** {profile.division}\n"
                    f"**Experience Level:** {profile.calculate_experience_level().value}\n"
                    f"**Total Missions:** {profile.total_missions}"
                ),
                inline=False
            )

        embeds.append(base_embed)

        for record in sorted(evals, key=lambda r: r.date, reverse=True):
            embed = discord.Embed(
                title=f"Evaluation - {record.date.strftime('%Y-%m-%d')}",
                description=f"Period: {record.period.value}",
                color=discord.Color.blue()
            )

            scores_text = "\n".join(
                f"{cat.value}: {score}/10" for cat, score in record.scores.items()
            )
            embed.add_field(name="Scores", value=scores_text, inline=False)

            if include_metrics and profile:
                metrics = await self._calculate_eval_metrics(record)
                metrics_text = "\n".join(
                    f"{k}: {v}" for k, v in metrics.items()
                    if not isinstance(v, (list, dict))
                )
                embed.add_field(name="Metrics", value=metrics_text, inline=False)

            embeds.append(embed)

        await interaction.followup.send(embeds=embeds[:10])

async def setup(bot: commands.Bot):
    await bot.add_cog(EvaluationCog(bot))
    logger.info("EvaluationCog loaded successfully")