# cogs/utils/shared_utils.py

import discord
from discord.ext import commands
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from datetime import datetime, timezone
import logging
import json
import os
import aiohttp
import pytz
from pathlib import Path
import asyncio

logger = logging.getLogger('shared_utils')

# CodaAPIManager has been removed. Please use CodaAPIClient from coda_api.py instead:
# from .coda_api import CodaAPIClient

class SharedAuditLogger:
    """Centralized audit logging system for all cogs."""
    
    def __init__(self, bot: commands.Bot, audit_channel_id: int):
        self.bot = bot
        self.channel_id = audit_channel_id
        self._cache = []
        self._batch_size = 10
        self._lock = asyncio.Lock()

    async def log_action(
        self,
        action_type: str,
        actor: discord.Member,
        target: Optional[discord.Member] = None,
        details: str = "",
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        severity: str = "INFO"
    ):
        """Log an administrative action."""
        try:
            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                logger.error(f"Audit log channel {self.channel_id} not found")
                return False

            embed = discord.Embed(
                title=f"Admin Action: {action_type}",
                description=details,
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(name="Actor", value=f"{actor.mention} ({actor.id})")
            if target:
                embed.add_field(name="Target", value=f"{target.mention} ({target.id})")
            
            if old_value and new_value:
                embed.add_field(name="Old Value", value=old_value, inline=True)
                embed.add_field(name="New Value", value=new_value, inline=True)

            await channel.send(embed=embed)
            logger.info(f"Audit log created for {action_type}")
            return True
        except Exception as e:
            logger.error(f"Error logging action: {e}")
            return False

    async def log(
        self,
        action_type: str,
        actor: discord.Member,
        details: str,
        target: Optional[discord.Member] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        severity: str = "INFO"
    ):
        """Log an action with batching support."""
        try:
            async with self._lock:
                self._cache.append({
                    'action_type': action_type,
                    'actor_id': actor.id,
                    'actor_name': str(actor),
                    'target_id': target.id if target else None,
                    'target_name': str(target) if target else None,
                    'details': details,
                    'old_value': old_value,
                    'new_value': new_value,
                    'severity': severity,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
                
                if len(self._cache) >= self._batch_size:
                    await self._flush_cache()
            return True
        except Exception as e:
            logger.error(f"Error in log method: {e}")
            return False

    async def _flush_cache(self):
        """Flush cached logs to Discord channel."""
        if not self._cache:
            return
            
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logger.error(f"Audit log channel {self.channel_id} not found")
            return

        try:
            embed = discord.Embed(
                title="Audit Log Batch",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            for entry in self._cache:
                value = (
                    f"**Actor:** <@{entry['actor_id']}>\n"
                    f"**Action:** {entry['action_type']}\n"
                )
                if entry['target_id']:
                    value += f"**Target:** <@{entry['target_id']}>\n"
                if entry['old_value'] and entry['new_value']:
                    value += f"**Change:** {entry['old_value']} → {entry['new_value']}\n"
                value += f"**Details:** {entry['details']}\n"
                
                embed.add_field(
                    name=f"{entry['severity']} - {entry['timestamp']}",
                    value=value,
                    inline=False
                )
                
            await channel.send(embed=embed)
            self._cache.clear()
            
        except Exception as e:
            logger.error(f"Error flushing audit logs: {e}")

class BackupManager:
    """Handles data backups across all systems."""
    
    def __init__(self, base_dir: str = 'backups'):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
    async def create_backup(
        self,
        data: Dict[str, Any],
        system_name: str,
        backup_type: str = 'auto'
    ) -> Path:
        """Create a backup file with versioning."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = self.base_dir / system_name
        backup_dir.mkdir(exist_ok=True)
        
        filename = f"{backup_type}_{timestamp}.json"
        filepath = backup_dir / filename
        
        try:
            # Try to use aiofiles (async) but fall back to regular file ops if not available
            try:
                import aiofiles
                async with aiofiles.open(filepath, 'w') as f:
                    await f.write(json.dumps(data, indent=2))
            except ImportError:
                logger.warning("aiofiles not available, using synchronous file operations")
                with open(filepath, 'w') as f:
                    f.write(json.dumps(data, indent=2))
            
            # Maintain backup rotation
            await self._rotate_backups(backup_dir, backup_type)
            
            logger.info(f"Created backup: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            # Return a default path instead of raising to avoid disrupting operations
            return self.base_dir / "backup_failed.json"
            
    async def _rotate_backups(self, backup_dir: Path, backup_type: str, keep: int = 5):
        """Maintain limited number of backups per type."""
        pattern = f"{backup_type}_*.json"
        backups = sorted(backup_dir.glob(pattern))
        
        while len(backups) > keep:
            oldest = backups.pop(0)
            try:
                oldest.unlink()
                logger.info(f"Removed old backup: {oldest}")
            except Exception as e:
                logger.error(f"Failed to remove old backup {oldest}: {e}")

    async def restore_from_backup(
        self,
        system_name: str,
        backup_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Restore data from a backup file."""
        backup_dir = self.base_dir / system_name
        
        if not backup_id:
            # Get latest backup
            backups = sorted(backup_dir.glob("*.json"))
            if not backups:
                return None
            backup_path = backups[-1]
        else:
            backup_path = backup_dir / f"{backup_id}.json"
            
        if not backup_path.exists():
            return None
            
        try:
            # Try to use aiofiles but fall back to regular file ops if not available
            try:
                import aiofiles
                async with aiofiles.open(backup_path, 'r') as f:
                    data = json.loads(await f.read())
            except ImportError:
                logger.warning("aiofiles not available, using synchronous file operations")
                with open(backup_path, 'r') as f:
                    data = json.load(f)
                    
            logger.info(f"Restored from backup: {backup_path}")
            return data
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return None

class MetricsTracker:
    """Tracks and aggregates metrics across systems."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._metrics_cache = {}
        self._last_update = {}
        
    async def get_member_metrics(
        self,
        member_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Get aggregated metrics for a member."""
        cache_key = f"member_{member_id}"
        
        # Check cache first
        if not force_refresh and cache_key in self._metrics_cache:
            last_update = self._last_update.get(cache_key, 0)
            if datetime.now().timestamp() - last_update < 3600:  # 1 hour cache
                return self._metrics_cache[cache_key]
        
        metrics = {}
        
        # Gather from various systems
        mission_metrics = await self._get_mission_metrics(member_id)
        if mission_metrics:
            metrics.update(mission_metrics)
            
        evaluation_metrics = await self._get_evaluation_metrics(member_id)
        if evaluation_metrics:
            metrics.update(evaluation_metrics)
            
        ship_metrics = await self._get_ship_metrics(member_id)
        if ship_metrics:
            metrics.update(ship_metrics)
            
        # Cache the results
        self._metrics_cache[cache_key] = metrics
        self._last_update[cache_key] = datetime.now().timestamp()
        
        return metrics
        
    async def _get_mission_metrics(self, member_id: int) -> Dict[str, Any]:
        """Get metrics from MissionCog."""
        mission_cog = self.bot.get_cog('MissionCog')
        if not mission_cog:
            return {}
            
        metrics = {
            'total_missions': 0,
            'successful_missions': 0,
            'mission_roles': set(),
            'mission_ships': set(),
        }
        
        for mission in mission_cog.missions.values():
            if str(member_id) in mission.participants:
                metrics['total_missions'] += 1
                if mission.status.value == "COMPLETED":
                    metrics['successful_missions'] += 1
                    
                participant = mission.participants[str(member_id)]
                if hasattr(participant, 'role'):
                    metrics['mission_roles'].add(participant.role)
                if hasattr(participant, 'ship_name'):
                    metrics['mission_ships'].add(participant.ship_name)
                    
        # Convert sets to lists for JSON serialization
        metrics['mission_roles'] = list(metrics['mission_roles'])
        metrics['mission_ships'] = list(metrics['mission_ships'])
        
        return metrics
        
    async def _get_evaluation_metrics(self, member_id: int) -> Dict[str, Any]:
        """Get metrics from EvaluationCog."""
        eval_cog = self.bot.get_cog('EvaluationCog')
        if not eval_cog:
            return {}
            
        evals = await eval_cog.get_member_evaluations(member_id)
        if not evals:
            return {}
            
        metrics = {
            'total_evaluations': len(evals),
            'average_score': sum(e.get('score', 0) for e in evals) / len(evals),
            'commendations': [],
            'areas_for_improvement': []
        }
        
        for eval_data in evals:
            if 'commendations' in eval_data:
                metrics['commendations'].extend(eval_data['commendations'])
            if 'improvements' in eval_data:
                metrics['areas_for_improvement'].extend(eval_data['improvements'])
                
        return metrics
        
    async def _get_ship_metrics(self, member_id: int) -> Dict[str, Any]:
        """Get metrics from ShipsCog."""
        ships_cog = self.bot.get_cog('ShipsCog')
        if not ships_cog:
            return {}
            
        cert_data = await ships_cog.get_member_certifications(member_id)
        if not cert_data:
            return {}
            
        return {
            'ship_certifications': cert_data.get('certifications', []),
            'primary_role': cert_data.get('primary_role'),
            'flight_hours': cert_data.get('flight_hours', {})
        }

class DataValidator:
    """Validates data structures across systems."""
    
    @staticmethod
    def validate_profile(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate profile data structure."""
        errors = []
        
        # Required fields
        required_fields = [
            'discord_user_id',
            'discord_username',
            'rank',
            'division'
        ]
        
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
                
        # Validate rank
        if 'rank' in data and data['rank'] not in [r[0] for r in RANKS]:
            errors.append(f"Invalid rank: {data['rank']}")
            
        # Validate division
        if 'division' in data and data['division'] not in DIVISION_CODES:
            errors.append(f"Invalid division: {data['division']}")
            
        return not bool(errors), errors

class AsyncTimer:
    """Utility for timing async operations."""
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = None
        
    async def __aenter__(self):
        self.start_time = datetime.now()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        logger.debug(f"{self.name} took {duration:.2f} seconds")
        
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        else:
            minutes = seconds // 60
            seconds = seconds % 60
            return f"{minutes:.0f}m {seconds:.0f}s"
