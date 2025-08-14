import discord
import os
from discord.ext import commands
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging
import json

logger = logging.getLogger('profile_utils')

# Removed the unused ProfileMetrics class altogether
# Removed the redundant BackupManager here, using the one in shared_utils instead
# SharedAuditLogger has been moved to shared_utils.py
# Please import it from there: from .shared_utils import SharedAuditLogger

async def sync_profile_data(
    bot: commands.Bot,
    member: discord.Member
) -> bool:
    """
    Synchronize profile data across all systems.
    Returns True if successful.
    """
    try:
        profile_cog = bot.get_cog('ProfileAdministrationCog')
        if not profile_cog:
            return False

        profile_data = await profile_cog.get_member_row(str(member.id))
        if not profile_data:
            return False

        ships_cog = bot.get_cog('ShipsCog')
        if ships_cog:
            await ships_cog.sync_member_ships(member.id, profile_data)

        srs_cog = bot.get_cog('SRSCog')
        if srs_cog:
            await srs_cog.sync_member_stations(member.id, profile_data)

        eval_cog = bot.get_cog('EvaluationCog')
        if eval_cog:
            await eval_cog.sync_member_data(member.id, profile_data)

        return True

    except Exception as e:
        logger.error(f"Profile sync failed: {e}")
        return False

async def calculate_activity_score(
    bot: commands.Bot,
    member: discord.Member
) -> float:
    """
    Calculate member activity score based on:
    - Mission participation
    - Evaluations
    - Ship certifications
    - Training completion
    Returns a score from 0.0 to 1.0
    """
    try:
        score_components = []

        mission_cog = bot.get_cog('MissionCog')
        if mission_cog:
            total_missions = len(mission_cog.missions)
            member_missions = len([
                m for m in mission_cog.missions.values()
                if member.id in m.participants
            ])
            mission_score = member_missions / total_missions if total_missions > 0 else 0
            score_components.append(mission_score * 0.4)

        eval_cog = bot.get_cog('EvaluationCog')
        if eval_cog:
            evals = await eval_cog.get_member_evaluations(member.id)
            if evals:
                avg_score = sum(e.get('score', 0) for e in evals) / len(evals)
                eval_score = avg_score / 10
                score_components.append(eval_score * 0.3)

        ships_cog = bot.get_cog('ShipsCog')
        if ships_cog:
            certs_data = await ships_cog.get_member_certifications(member.id)
            if certs_data:
                cert_count = len(certs_data.get('certifications', []))
                score_components.append(min(cert_count / 5, 1.0) * 0.2)

        # Training or other factors could fill the remaining 0.1 as needed
        total = sum(score_components)
        return min(total, 1.0)

    except Exception as e:
        logger.error(f"Error calculating activity score: {e}")
        return 0.0
