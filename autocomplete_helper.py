from __future__ import annotations

from typing import List, Dict, Any, Optional, Callable, Coroutine, Union, TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio

if TYPE_CHECKING:
    from discord import Interaction
    from .commandhub import CommandHubCog

logger = logging.getLogger('autocomplete_helper')
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='autocomplete_helper.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class AutocompleteHelper(commands.Cog):
    """Helper cog to manage autocomplete data across the bot"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.autocomplete_data = {
            'ships': [],
            'users': [],
            'missions': [],
            'stations': [],
            'divisions': [],
            'ranks': [],
            'certifications': [],
            'awards': []
        }
        self.last_update = {}
        self._task = bot.loop.create_task(self.background_refresh_task())
        logger.info("AutocompleteHelper cog initialized")
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self._task:
            self._task.cancel()
    
    async def background_refresh_task(self):
        """Background task to periodically refresh autocomplete data"""
        try:
            await self.bot.wait_until_ready()
            while not self.bot.is_closed():
                await self.refresh_all_data()
                await asyncio.sleep(300)  # Refresh every 5 minutes
        except asyncio.CancelledError:
            # Task was cancelled, clean up
            pass
        except Exception as e:
            logger.error(f"Error in background refresh task: {e}")
    
    async def refresh_all_data(self):
        """Refresh all autocomplete data"""
        try:
            await self.refresh_ship_data()
            await self.refresh_mission_data()
            await self.refresh_station_data()
            await self.refresh_user_data()
            await self.refresh_division_data()
            await self.refresh_rank_data()
            await self.refresh_certification_data()
            await self.refresh_award_data()
            
            # Update command hub's cache if it exists
            command_hub = self.bot.get_cog('CommandHubCog')
            if command_hub and hasattr(command_hub, '_autocomplete_cache'):
                command_hub._autocomplete_cache.update(self.autocomplete_data)
                
            logger.info("Refreshed all autocomplete data")
        except Exception as e:
            logger.error(f"Error refreshing autocomplete data: {e}")
    
    async def refresh_ship_data(self):
        """Refresh ship data from IntegratedShipsCog"""
        try:
            ships_cog = self.bot.get_cog('IntegratedShipsCog')
            if ships_cog and hasattr(ships_cog, 'get_ship_names'):
                self.autocomplete_data['ships'] = await ships_cog.get_ship_names()
                self.last_update['ships'] = discord.utils.utcnow()
                logger.info(f"Refreshed ship data: {len(self.autocomplete_data['ships'])} ships")
        except Exception as e:
            logger.error(f"Error refreshing ship data: {e}")
    
    async def refresh_mission_data(self):
        """Refresh mission data from MissionCog"""
        try:
            mission_cog = self.bot.get_cog('MissionCog')
            if mission_cog and hasattr(mission_cog, 'get_active_missions'):
                self.autocomplete_data['missions'] = await mission_cog.get_active_missions()
                self.last_update['missions'] = discord.utils.utcnow()
                logger.info(f"Refreshed mission data: {len(self.autocomplete_data['missions'])} missions")
        except Exception as e:
            logger.error(f"Error refreshing mission data: {e}")
    
    async def refresh_station_data(self):
        """Refresh station data from RadioCog"""
        try:
            radio_cog = self.bot.get_cog('RadioCog')
            if radio_cog and hasattr(radio_cog, 'get_stations'):
                self.autocomplete_data['stations'] = await radio_cog.get_stations()
                self.last_update['stations'] = discord.utils.utcnow()
                logger.info(f"Refreshed station data: {len(self.autocomplete_data['stations'])} stations")
        except Exception as e:
            logger.error(f"Error refreshing station data: {e}")
    
    async def refresh_user_data(self):
        """Cache member data for user autocomplete"""
        try:
            # We'll only store basic member info to keep memory usage reasonable
            members = []
            for guild in self.bot.guilds:
                for member in guild.members:
                    members.append({
                        'id': str(member.id),
                        'name': member.name,
                        'display_name': member.display_name,
                        'nick': member.nick
                    })
            
            self.autocomplete_data['users'] = members
            self.last_update['users'] = discord.utils.utcnow()
            logger.info(f"Refreshed user data: {len(self.autocomplete_data['users'])} users")
        except Exception as e:
            logger.error(f"Error refreshing user data: {e}")
    
    async def refresh_division_data(self):
        """Refresh division data"""
        try:
            division_cog = self.bot.get_cog('DivisionSelectionCog')
            if division_cog and hasattr(division_cog, 'get_divisions'):
                self.autocomplete_data['divisions'] = await division_cog.get_divisions()
                self.last_update['divisions'] = discord.utils.utcnow()
                logger.info(f"Refreshed division data: {len(self.autocomplete_data['divisions'])} divisions")
        except Exception as e:
            logger.error(f"Error refreshing division data: {e}")
    
    async def refresh_rank_data(self):
        """Refresh rank data"""
        try:
            admin_cog = self.bot.get_cog('AdministrationCog')
            if admin_cog and hasattr(admin_cog, 'get_ranks'):
                self.autocomplete_data['ranks'] = await admin_cog.get_ranks()
                self.last_update['ranks'] = discord.utils.utcnow()
                logger.info(f"Refreshed rank data: {len(self.autocomplete_data['ranks'])} ranks")
        except Exception as e:
            logger.error(f"Error refreshing rank data: {e}")
    
    async def refresh_certification_data(self):
        """Refresh certification data"""
        try:
            admin_cog = self.bot.get_cog('AdministrationCog')
            if admin_cog and hasattr(admin_cog, 'get_certifications'):
                self.autocomplete_data['certifications'] = await admin_cog.get_certifications()
                self.last_update['certifications'] = discord.utils.utcnow()
                logger.info(f"Refreshed certification data: {len(self.autocomplete_data['certifications'])} certifications")
        except Exception as e:
            logger.error(f"Error refreshing certification data: {e}")
    
    async def refresh_award_data(self):
        """Refresh award data"""
        try:
            profile_cog = self.bot.get_cog('ProfileCog')
            if profile_cog and hasattr(profile_cog, 'get_awards'):
                self.autocomplete_data['awards'] = await profile_cog.get_awards()
                self.last_update['awards'] = discord.utils.utcnow()
                logger.info(f"Refreshed award data: {len(self.autocomplete_data['awards'])} awards")
        except Exception as e:
            logger.error(f"Error refreshing award data: {e}")
    
    # Autocomplete handlers that can be used by other cogs
    async def autocomplete_ship(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for ship names"""
        # Refresh if no data
        if not self.autocomplete_data['ships']:
            await self.refresh_ship_data()
        
        ships = self.autocomplete_data['ships']
        
        # Filter ships that match the current input
        matches = [ship for ship in ships if current.lower() in ship.lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=ship, value=ship)
            for ship in matches[:25]
        ]
    
    async def autocomplete_user(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for users"""
        # For users, we'll do a live search of the guild to ensure most up-to-date data
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
        """Autocomplete for mission names"""
        # Refresh if no data
        if not self.autocomplete_data['missions']:
            await self.refresh_mission_data()
        
        missions = self.autocomplete_data['missions']
        
        # Filter missions that match the current input
        matches = [mission for mission in missions if current.lower() in mission['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=mission['name'], value=str(mission['id']))
            for mission in matches[:25]
        ]
    
    async def autocomplete_station(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for radio stations"""
        # Refresh if no data
        if not self.autocomplete_data['stations']:
            await self.refresh_station_data()
        
        stations = self.autocomplete_data['stations']
        
        # Filter stations that match the current input
        matches = [station for station in stations if current.lower() in station['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=station['name'], value=station['id'])
            for station in matches[:25]
        ]
    
    async def autocomplete_division(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for divisions"""
        # Refresh if no data
        if not self.autocomplete_data['divisions']:
            await self.refresh_division_data()
        
        divisions = self.autocomplete_data['divisions']
        
        # Filter divisions that match the current input
        matches = [div for div in divisions if current.lower() in div['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=div['name'], value=div['id'])
            for div in matches[:25]
        ]
    
    async def autocomplete_rank(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for ranks"""
        # Refresh if no data
        if not self.autocomplete_data['ranks']:
            await self.refresh_rank_data()
        
        ranks = self.autocomplete_data['ranks']
        
        # Filter ranks that match the current input
        matches = [rank for rank in ranks if current.lower() in rank['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=rank['name'], value=rank['id'])
            for rank in matches[:25]
        ]
    
    async def autocomplete_certification(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for certifications"""
        # Refresh if no data
        if not self.autocomplete_data['certifications']:
            await self.refresh_certification_data()
        
        certifications = self.autocomplete_data['certifications']
        
        # Filter certifications that match the current input
        matches = [cert for cert in certifications if current.lower() in cert['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=cert['name'], value=cert['id'])
            for cert in matches[:25]
        ]
    
    async def autocomplete_award(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for awards"""
        # Refresh if no data
        if not self.autocomplete_data['awards']:
            await self.refresh_award_data()
        
        awards = self.autocomplete_data['awards']
        
        # Filter awards that match the current input
        matches = [award for award in awards if current.lower() in award['name'].lower()]
        
        # Return up to 25 choices (Discord's limit)
        return [
            app_commands.Choice(name=award['name'], value=award['id'])
            for award in matches[:25]
        ]
    
    # Helper method to register autocomplete with app commands
    def register_autocomplete(self, command: app_commands.Command, param_name: str, autocomplete_type: str):
        """Register an autocomplete handler for a command parameter"""
        autocomplete_map = {
            'ship': self.autocomplete_ship,
            'user': self.autocomplete_user,
            'mission': self.autocomplete_mission,
            'station': self.autocomplete_station,
            'division': self.autocomplete_division,
            'rank': self.autocomplete_rank,
            'certification': self.autocomplete_certification,
            'award': self.autocomplete_award
        }
        
        if autocomplete_type in autocomplete_map:
            command.autocomplete(param_name)(autocomplete_map[autocomplete_type])
            logger.info(f"Registered {autocomplete_type} autocomplete for {command.name}.{param_name}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutocompleteHelper(bot))
    logger.info("AutocompleteHelper cog loaded successfully")