# cogs/radio.py

import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import os
import json
import re
import time
from typing import Dict, Any, List, Optional, Tuple
import aiohttp
from io import BytesIO
from discord.errors import NotFound

# ------------------------------ Logging Setup ------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='radio.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)

# ------------------------------ Environment Variables ------------------------------
from dotenv import load_dotenv
load_dotenv()

GUILD_ID = os.getenv('GUILD_ID')
if GUILD_ID is None:
    logger.critical("GUILD_ID environment variable not set.")
    raise ValueError("GUILD_ID environment variable not set.")
else:
    GUILD_ID = int(GUILD_ID)

# ------------------------------ Constants ------------------------------
DEFAULT_VOLUME = 0.5  # 50% volume by default
STATIONS_FILE = 'data/radio_stations.json'
MAX_CUSTOM_STATIONS = 10
STATION_ICONS = {
    'hcnradio1': 'https://images.squarespace-cdn.com/content/v1/669848a030fd4051a56c5278/c77fbe80-0d44-4e0c-a3c1-96b89f361428/radio1.png',
    'hcnradio2': 'https://images.squarespace-cdn.com/content/v1/669848a030fd4051a56c5278/ae27275e-b435-4b55-b840-860a24e4f4cb/radio2.png',
    'hnni': 'https://images.squarespace-cdn.com/content/v1/669848a030fd4051a56c5278/7afbec65-9dcc-4d09-8388-2d6595503f9e/hcninvest.png',
    'hcnmusic': 'https://images.squarespace-cdn.com/content/v1/669848a030fd4051a56c5278/1682f620-153a-494a-bd5e-f7bf05fe1cf0/radio4final.png',
    'default': 'https://images.squarespace-cdn.com/content/v1/669848a030fd4051a56c5278/a7d241cb-2d78-4883-ba2f-c96e5500c3e0/HCNLogo1.png?format=1500w'
}

# ------------------------------ Helper Classes ------------------------------
class RadioStation:
    """Class to represent a radio station with all its properties."""
    def __init__(
        self, 
        key: str, 
        name: str, 
        url: str, 
        description: str = "", 
        icon_url: str = None, 
        genre: str = "Variety", 
        added_by: int = None,
        custom: bool = False
    ):
        self.key = key
        self.name = name
        self.url = url
        self.description = description
        self.icon_url = icon_url or STATION_ICONS.get('default')
        self.genre = genre
        self.added_by = added_by
        self.custom = custom
        self.current_track: Optional[str] = None
        self.last_updated: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert station to dictionary for storage."""
        return {
            'key': self.key,
            'name': self.name,
            'url': self.url,
            'description': self.description,
            'icon_url': self.icon_url,
            'genre': self.genre,
            'added_by': self.added_by,
            'custom': self.custom
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RadioStation':
        """Create station from dictionary data."""
        return cls(
            key=data['key'],
            name=data['name'],
            url=data['url'],
            description=data.get('description', ''),
            icon_url=data.get('icon_url'),
            genre=data.get('genre', 'Variety'),
            added_by=data.get('added_by'),
            custom=data.get('custom', False)
        )

class NowPlayingView(discord.ui.View):
    """Interactive view for the now playing message."""
    def __init__(self, cog: 'RadioCog', guild_id: int):
        super().__init__(timeout=None)  # Make this a persistent view
        self.cog = cog
        self.guild_id = guild_id
    
    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="🛑", custom_id="radio:stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stop the currently playing station."""
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("This control panel is for another server.", ephemeral=True)
            return
        
        voice_client = self.cog.voice_clients.get(self.guild_id)
        if not voice_client or not voice_client.is_connected():
            await interaction.response.send_message("No station is currently playing.", ephemeral=True)
            return
        
        # Disconnect
        await self.cog.disconnect_voice_client(self.guild_id)
        await interaction.response.send_message("🛑 Radio stopped and disconnected.", ephemeral=True)
        
        # Update now playing message
        await self.cog.update_now_playing(self.guild_id, stopped=True)
    
    @discord.ui.button(label="Volume Down", style=discord.ButtonStyle.secondary, emoji="🔉", custom_id="radio:volume_down")
    async def volume_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Decrease the volume."""
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("This control panel is for another server.", ephemeral=True)
            return
        
        success, new_volume = await self.cog.adjust_volume(self.guild_id, -0.1)
        if success:
            await interaction.response.send_message(f"🔉 Volume set to {int(new_volume * 100)}%", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to adjust volume.", ephemeral=True)
            
    @discord.ui.button(label="Volume Up", style=discord.ButtonStyle.secondary, emoji="🔊", custom_id="radio:volume_up")
    async def volume_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Increase the volume."""
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("This control panel is for another server.", ephemeral=True)
            return
        
        success, new_volume = await self.cog.adjust_volume(self.guild_id, 0.1)
        if success:
            await interaction.response.send_message(f"🔊 Volume set to {int(new_volume * 100)}%", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to adjust volume.", ephemeral=True)

# Note: Since we can't have a persistent select menu with dynamic options
# We'll use a button to switch stations instead of a select dropdown

    @discord.ui.button(label="Switch Station", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="radio:switch_station")
    async def switch_station_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a menu to switch stations."""
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("This control panel is for another server.", ephemeral=True)
            return
        
        # Create a select menu with stations
        options = [
            discord.SelectOption(
                label=station.name,
                value=station.key,
                description=f"{station.genre}" + (f" - {station.description[:30]}..." if len(station.description) > 30 else "")
            )
            for station in self.cog.stations.values()
        ][:25]  # Discord limit
        
        class StationSwitchView(discord.ui.View):
            def __init__(self, cog: 'RadioCog'):
                super().__init__(timeout=60)  # Short timeout for this temporary view
                self.cog = cog
            
            @discord.ui.select(
                placeholder="Select a station to play",
                min_values=1,
                max_values=1,
                options=options
            )
            async def station_select(self, station_interaction: discord.Interaction, select: discord.ui.Select):
                selected_station = select.values[0]
                
                # Check if user is in a voice channel
                if not station_interaction.user.voice:
                    await station_interaction.response.send_message(
                        "You must be in a voice channel to switch stations.",
                        ephemeral=True
                    )
                    return
                
                # Switch stations
                await station_interaction.response.defer(ephemeral=True)
                success, message = await self.cog.play_station(station_interaction, selected_station)
                
                if success:
                    await station_interaction.followup.send(
                        f"🔄 Switched to station: {self.cog.stations[selected_station].name}",
                        ephemeral=True
                    )
                else:
                    await station_interaction.followup.send(
                        f"❌ Failed to switch stations: {message}",
                        ephemeral=True
                    )
                
                self.stop()
        
        # Send the station selection menu
        await interaction.response.send_message(
            "Select a station to play:",
            view=StationSwitchView(self.cog),
            ephemeral=True
        )

class StationPaginator(discord.ui.View):
    """Paginated view for browsing stations."""
    def __init__(self, cog: 'RadioCog', interaction: discord.Interaction, page_size: int = 5):
        super().__init__(timeout=120)  # Non-persistent view with 2 minute timeout
        self.cog = cog
        self.interaction = interaction
        self.page_size = page_size
        self.current_page = 0
        self.filter = None
        self.stations_list = list(cog.stations.values())
        self.max_pages = max(1, (len(self.stations_list) + page_size - 1) // page_size)
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="◀️", disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the previous page."""
        self.current_page = max(0, self.current_page - 1)
        # Update button states
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.max_pages - 1)
        # Update embed
        embed = self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the next page."""
        self.current_page = min(self.max_pages - 1, self.current_page + 1)
        # Update button states
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.max_pages - 1)
        # Update embed
        embed = self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Play Selected", style=discord.ButtonStyle.primary, emoji="▶️", row=1)
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open a menu to select a station to play."""
        # Create a select menu with the current page's stations
        stations = self.get_current_page_stations()
        
        options = [
            discord.SelectOption(
                label=station.name,
                value=station.key,
                description=f"{station.genre}" + (f" - {station.description[:30]}..." if len(station.description) > 30 else "")
            )
            for station in stations
        ]
        
        class StationSelectView(discord.ui.View):
            def __init__(self, cog: 'RadioCog', parent_interaction: discord.Interaction):
                super().__init__(timeout=30)
                self.cog = cog
                self.parent_interaction = parent_interaction
                
            @discord.ui.select(
                placeholder="Select a station to play",
                min_values=1,
                max_values=1,
                options=options
            )
            async def station_select(self, select_interaction: discord.Interaction, select: discord.ui.Select):
                """Play the selected station."""
                await select_interaction.response.defer(ephemeral=True)
                selected_station = select.values[0]
                
                success, message = await self.cog.play_station(select_interaction, selected_station)
                
                if success:
                    await select_interaction.followup.send(
                        f"▶️ Now playing: {self.cog.stations[selected_station].name}",
                        ephemeral=True
                    )
                else:
                    await select_interaction.followup.send(f"❌ Failed to play station: {message}", ephemeral=True)
                
                self.stop()
        
        view = StationSelectView(self.cog, interaction)
        await interaction.response.send_message("Select a station to play:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Filter", style=discord.ButtonStyle.secondary, emoji="🔍", row=1)
    async def filter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Filter the stations list."""
        # Create a modal for filtering
        class FilterModal(discord.ui.Modal, title="Filter Stations"):
            filter_input = discord.ui.TextInput(
                label="Filter by name, genre or description",
                placeholder="Enter text to filter stations",
                required=False
            )
            
            async def on_submit(self, modal_interaction: discord.Interaction):
                # Apply the filter
                filter_text = self.filter_input.value.lower() if self.filter_input.value else None
                await modal_interaction.response.defer(ephemeral=True)
                
                # Update the filter
                if filter_text:
                    self.view.filter = filter_text
                    self.view.stations_list = [
                        station for station in self.view.cog.stations.values()
                        if (filter_text in station.name.lower() or 
                            filter_text in station.genre.lower() or
                            filter_text in station.description.lower())
                    ]
                else:
                    self.view.filter = None
                    self.view.stations_list = list(self.view.cog.stations.values())
                
                # Reset pagination
                self.view.current_page = 0
                self.view.max_pages = max(1, (len(self.view.stations_list) + self.view.page_size - 1) // self.view.page_size)
                self.view.previous_button.disabled = True
                self.view.next_button.disabled = (self.view.max_pages <= 1)
                
                # Update the embed
                embed = self.view.get_current_page_embed()
                
                try:
                    # Try to edit the original message
                    await self.view.interaction.edit_original_response(embed=embed, view=self.view)
                    await modal_interaction.followup.send(
                        f"Filter applied. Found {len(self.view.stations_list)} stations.",
                        ephemeral=True
                    )
                except Exception as e:
                    logger.error(f"Failed to update view after filtering: {e}")
                    await modal_interaction.followup.send(
                        "Failed to update the station list. Please try again.",
                        ephemeral=True
                    )
        
        # Show the filter modal
        await interaction.response.send_modal(FilterModal())
    
    def get_current_page_stations(self) -> List[RadioStation]:
        """Get the stations for the current page."""
        start_idx = self.current_page * self.page_size
        end_idx = min((self.current_page + 1) * self.page_size, len(self.stations_list))
        return self.stations_list[start_idx:end_idx]
    
    def get_current_page_embed(self) -> discord.Embed:
        """Create an embed for the current page of stations."""
        stations = self.get_current_page_stations()
        
        embed = discord.Embed(
            title="📻 Radio Stations",
            description=f"Page {self.current_page + 1}/{self.max_pages}" +
                        (f" (Filtered: '{self.filter}')" if self.filter else ""),
            color=discord.Color.blue()
        )
        
        for station in stations:
            # Format the station entry
            station_info = f"**Genre:** {station.genre}\n"
            if station.description:
                station_info += f"**Info:** {station.description}\n"
            if station.custom:
                added_by = self.interaction.guild.get_member(station.added_by)
                added_by_name = added_by.display_name if added_by else "Unknown"
                station_info += f"**Added by:** {added_by_name}\n"
            
            embed.add_field(
                name=f"`{station.key}` - {station.name}",
                value=station_info,
                inline=False
            )
        
        if not stations:
            embed.add_field(
                name="No stations found",
                value="Try adjusting your filter or adding some stations.",
                inline=False
            )
        
        # Add instructions for using the buttons
        embed.set_footer(text="Use the buttons below to navigate and play stations.")
        
        return embed

# ------------------------------ Cog Definition ------------------------------
class RadioCog(commands.Cog):
    """Enhanced cog for playing radio stations in voice channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stations: Dict[str, RadioStation] = {}  # Using RadioStation objects instead of dicts
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        self.ffmpeg_available = False
        self.guild_volumes: Dict[int, float] = {}
        self.now_playing_messages: Dict[int, Tuple[discord.Message, str]] = {}
        self.metadata_tasks: Dict[int, asyncio.Task] = {}
        
        # Initialize with default stations
        self._init_default_stations()
        
        # Create the data directory if it doesn't exist
        os.makedirs(os.path.dirname(STATIONS_FILE), exist_ok=True)
        
        # Load custom stations
        self._load_stations()

    async def cog_load(self):
        self.ffmpeg_available = await self.is_ffmpeg_available()
        if not self.ffmpeg_available:
            logger.error("FFmpeg is not available. Radio functionality will be disabled.")
        else:
            logger.info("FFmpeg is available. Radio functionality is enabled.")
            
        # Add our persistent view
        for guild_id in [GUILD_ID]:  # You can add more guild IDs if needed
            self.bot.add_view(NowPlayingView(self, guild_id))
        
        logger.info("Registered persistent views for radio controls.")

    def _init_default_stations(self):
        """Initialize default radio stations."""
        default_stations = {
            'hcnradio1': RadioStation(
                key='hcnradio1',
                name='HCN-Radio 1',
                url='http://hcnradio.ddns.me:8000/stream/1/?type=http',
                description='Main HCN radio station with news and varied programming',
                icon_url=STATION_ICONS.get('hcnradio1'),
                genre='News & Entertainment'
            ),
            'hcnradio2': RadioStation(
                key='hcnradio2',
                name='HCN-Radio 2',
                url='http://hcnradio.ddns.me:8000/stream/2/?type=http',
                description='Alternative programming and talk shows',
                icon_url=STATION_ICONS.get('hcnradio2'),
                genre='Talk & Entertainment'
            ),
            'hnni': RadioStation(
                key='hnni',
                name='HCN-Investigative',
                url='http://hcnradio.ddns.me:8000/stream/3/?type=http',
                description='Investigative fringe stories and hard rock',
                icon_url=STATION_ICONS.get('hnni'),
                genre='Special Interest'
            ),
            'hcnmusic': RadioStation(
                key='hcnmusic',
                name='HCN-Music',
                url='http://hcnradio.ddns.me:8000/stream/4/?type=http',
                description='24/7 music station with various genres',
                icon_url=STATION_ICONS.get('hcnmusic'),
                genre='Music'
            )
        }
        
        # Initialize stations dictionary
        self.stations = default_stations

    def _load_stations(self):
        """Load custom stations from file."""
        try:
            if os.path.exists(STATIONS_FILE):
                with open(STATIONS_FILE, 'r') as f:
                    stations_data = json.load(f)
                
                for station_data in stations_data:
                    station = RadioStation.from_dict(station_data)
                    # Only add if not already in defaults
                    if station.key not in self.stations:
                        self.stations[station.key] = station
                
                logger.info(f"Loaded {len(stations_data)} custom stations from file.")
            else:
                logger.info("No custom stations file found. Using default stations only.")
        except Exception as e:
            logger.error(f"Error loading custom stations: {e}")

    def _save_stations(self):
        """Save custom stations to file."""
        try:
            # Filter for only custom stations
            custom_stations = [
                station.to_dict() for station in self.stations.values()
                if station.custom
            ]
            
            with open(STATIONS_FILE, 'w') as f:
                json.dump(custom_stations, f, indent=4)
            
            logger.info(f"Saved {len(custom_stations)} custom stations to file.")
        except Exception as e:
            logger.error(f"Error saving custom stations: {e}")

    async def is_ffmpeg_available(self) -> bool:
        """Check if FFmpeg is available in the system."""
        try:
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-version',
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await process.wait()
            return True
        except FileNotFoundError as e:
            logger.error(f"FFmpeg not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking FFmpeg availability: {e}")
            return False

    # ------------------------------ Commands ------------------------------
    @app_commands.command(
        name='play',
        description='Play a radio station in your voice channel.'
    )
    @app_commands.describe(station='The radio station to play.')
    async def play(self, interaction: discord.Interaction, station: str):
        """Play a radio station in the user's voice channel."""
        try:
            await interaction.response.defer()
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return  # Cannot proceed if deferral failed

        success, message = await self.play_station(interaction, station)
        
        if success:
            await interaction.followup.send(message)
        else:
            await interaction.followup.send(message, ephemeral=True)

    @play.autocomplete('station')
    async def station_autocomplete(self, interaction: discord.Interaction, current: str):
        """Provides autocomplete suggestions for station names."""
        current = current.lower()
        choices = [
            app_commands.Choice(name=f"{station.name} ({station.genre})", value=key)
            for key, station in self.stations.items()
            if current in key.lower() or current in station.name.lower() or current in station.genre.lower()
        ]
        return choices[:25]

    @app_commands.command(
        name='stop',
        description='Stop playing and disconnect from the voice channel.'
    )
    async def stop(self, interaction: discord.Interaction):
        """Stop playing and disconnect from the voice channel."""
        try:
            await interaction.response.defer(ephemeral=True)
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            voice_client = self.voice_clients.get(interaction.guild.id)

            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                del self.voice_clients[interaction.guild.id]
                
                # Update the now playing message if it exists
                await self.update_now_playing(interaction.guild.id, stopped=True)
                
                await interaction.followup.send(
                    "🛑 Stopped playing and disconnected from the voice channel."
                )
                logger.info(f"Disconnected from voice channel in guild {interaction.guild.name}.")
            else:
                await interaction.followup.send(
                    "❌ I'm not connected to a voice channel.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in stop command: {e}")
            try:
                await interaction.followup.send(
                    "An error occurred while trying to stop the radio.",
                    ephemeral=True
                )
            except Exception as send_error:
                logger.error(f"Failed to send error message: {send_error}")

    @app_commands.command(
        name='stations',
        description='List available radio stations.'
    )
    async def stations_command(self, interaction: discord.Interaction):
        """List available radio stations with pagination."""
        try:
            await interaction.response.defer(ephemeral=True)
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            # Create paginator view
            paginator = StationPaginator(self, interaction)
            embed = paginator.get_current_page_embed()
            
            await interaction.followup.send(embed=embed, view=paginator, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in stations command: {e}")
            await interaction.followup.send(
                "An error occurred while listing the stations.",
                ephemeral=True
            )

    @app_commands.command(
        name='volume',
        description='Adjust the volume of the radio (0-100).'
    )
    @app_commands.describe(volume='The volume level (0-100)')
    async def volume_command(self, interaction: discord.Interaction, volume: int):
        """Adjust the volume of the radio."""
        try:
            await interaction.response.defer(ephemeral=True)
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            # Validate volume input
            if volume < 0 or volume > 100:
                await interaction.followup.send(
                    "❌ Volume must be between 0 and 100.",
                    ephemeral=True
                )
                return
            
            # Convert to float between 0 and 1
            volume_float = volume / 100.0
            
            # Adjust volume
            success, _ = await self.adjust_volume(interaction.guild.id, volume_float, set_directly=True)
            
            if success:
                await interaction.followup.send(
                    f"🔊 Volume set to {volume}%",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ I'm not currently playing in a voice channel.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error in volume command: {e}")
            await interaction.followup.send(
                "An error occurred while adjusting the volume.",
                ephemeral=True
            )
    
    @app_commands.command(
        name='nowplaying',
        description='Show currently playing radio station.'
    )
    async def now_playing_command(self, interaction: discord.Interaction):
        """Show information about the currently playing station."""
        try:
            await interaction.response.defer()
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            guild_id = interaction.guild.id
            voice_client = self.voice_clients.get(guild_id)
            
            if not voice_client or not voice_client.is_connected():
                await interaction.followup.send(
                    "❌ Nothing is currently playing.",
                    ephemeral=True
                )
                return
            
            # Find which station is playing
            current_station = None
            for message, station_key in self.now_playing_messages.values():
                if message.guild.id == guild_id:
                    current_station = self.stations.get(station_key)
                    break
            
            if not current_station:
                await interaction.followup.send(
                    "❌ Could not determine the current station.",
                    ephemeral=True
                )
                return
            
            # Create the now playing embed
            embed = self.create_now_playing_embed(current_station, guild_id)
            
            # Create view with controls
            view = NowPlayingView(self, guild_id)
            
            # Send the now playing message
            message = await interaction.followup.send(embed=embed, view=view)
            
            # Store the message for future updates
            if guild_id in self.now_playing_messages:
                # Try to delete the old message
                old_message, _ = self.now_playing_messages[guild_id]
                try:
                    await old_message.delete()
                except:
                    pass  # Ignore errors with deletion
            
            # Store the new message
            self.now_playing_messages[guild_id] = (message, current_station.key)
            
            # Start or restart the metadata update task
            if guild_id in self.metadata_tasks and not self.metadata_tasks[guild_id].done():
                self.metadata_tasks[guild_id].cancel()
            
            self.metadata_tasks[guild_id] = asyncio.create_task(
                self.update_metadata_loop(guild_id, current_station)
            )
        except Exception as e:
            logger.error(f"Error in now playing command: {e}")
            await interaction.followup.send(
                "An error occurred while fetching the currently playing station.",
                ephemeral=True
            )
    
    @app_commands.command(
        name='addstation',
        description='Add a custom radio station.'
    )
    @app_commands.describe(
        name='The name of the station',
        url='The stream URL of the station',
        genre='The genre of the station (optional)',
        description='Description of the station (optional)'
    )
    async def add_station_command(self, interaction: discord.Interaction, name: str, url: str, 
                                 genre: str = "Variety", description: str = ""):
        """Add a custom radio station."""
        try:
            await interaction.response.defer(ephemeral=True)
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            # Count existing custom stations from this user
            user_stations = sum(1 for station in self.stations.values() 
                              if station.custom and station.added_by == interaction.user.id)
            
            if user_stations >= MAX_CUSTOM_STATIONS:
                await interaction.followup.send(
                    f"❌ You have reached the maximum limit of {MAX_CUSTOM_STATIONS} custom stations.",
                    ephemeral=True
                )
                return
            
            # Validate URL (basic check)
            if not url.startswith(('http://', 'https://')):
                await interaction.followup.send(
                    "❌ URL must start with http:// or https://",
                    ephemeral=True
                )
                return
            
            # Generate a unique key for the station
            # Use a simplified version of the name for the key
            key_base = re.sub(r'[^a-z0-9]', '', name.lower())
            key = key_base
            counter = 1
            
            # Ensure the key is unique
            while key in self.stations:
                key = f"{key_base}{counter}"
                counter += 1
            
            # Create the station
            station = RadioStation(
                key=key,
                name=name,
                url=url,
                description=description,
                genre=genre,
                added_by=interaction.user.id,
                custom=True
            )
            
            # Add to stations and save
            self.stations[key] = station
            self._save_stations()
            
            await interaction.followup.send(
                f"✅ Added custom station: {name}\n"
                f"Key: `{key}`\n"
                f"Use `/play {key}` to play this station.",
                ephemeral=True
            )
            logger.info(f"User {interaction.user.name} added custom station: {name} ({key})")
        except Exception as e:
            logger.error(f"Error in add station command: {e}")
            await interaction.followup.send(
                "An error occurred while adding the custom station.",
                ephemeral=True
            )
    
    @app_commands.command(
        name='removestation',
        description='Remove a custom radio station.'
    )
    @app_commands.describe(station='The station to remove.')
    async def remove_station_command(self, interaction: discord.Interaction, station: str):
        """Remove a custom radio station."""
        try:
            await interaction.response.defer(ephemeral=True)
            logger.debug("Interaction deferred successfully.")
        except Exception as e:
            logger.error(f"Failed to defer interaction: {e}")
            return

        try:
            # Check if station exists
            if station not in self.stations:
                await interaction.followup.send(
                    f"❌ Station `{station}` not found.",
                    ephemeral=True
                )
                return
            
            target_station = self.stations[station]
            
            # Check if it's a custom station
            if not target_station.custom:
                await interaction.followup.send(
                    f"❌ You cannot remove default stations.",
                    ephemeral=True
                )
                return
            
            # Check if the user has permission (either added by them or admin)
            is_admin = interaction.user.guild_permissions.administrator
            is_owner = target_station.added_by == interaction.user.id
            
            if not (is_admin or is_owner):
                await interaction.followup.send(
                    f"❌ You don't have permission to remove this station.",
                    ephemeral=True
                )
                return
            
            # Remove the station
            del self.stations[station]
            self._save_stations()
            
            await interaction.followup.send(
                f"✅ Removed station: {target_station.name}",
                ephemeral=True
            )
            logger.info(f"User {interaction.user.name} removed station: {target_station.name} ({station})")
        except Exception as e:
            logger.error(f"Error in remove station command: {e}")
            await interaction.followup.send(
                "An error occurred while removing the station.",
                ephemeral=True
            )
    
    @remove_station_command.autocomplete('station')
    async def remove_station_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for custom stations that user can remove."""
        current = current.lower()
        
        # Get custom stations the user can remove
        user_id = interaction.user.id
        is_admin = interaction.user.guild_permissions.administrator
        
        removable_stations = [
            (key, station) for key, station in self.stations.items()
            if station.custom and (is_admin or station.added_by == user_id)
        ]
        
        # Filter based on input
        filtered_stations = [
            (key, station) for key, station in removable_stations
            if current in key.lower() or current in station.name.lower()
        ]
        
        # Create choices
        choices = [
            app_commands.Choice(name=f"{station.name} (Custom)", value=key)
            for key, station in filtered_stations
        ]
        
        return choices[:25]

    # ------------------------------ Helper Methods ------------------------------
    async def play_station(self, interaction: discord.Interaction, station: str) -> Tuple[bool, str]:
        """Play a radio station in the user's voice channel."""
        try:
            if not self.ffmpeg_available:
                return False, "❌ FFmpeg is not available on the server."
    
            # Validate station
            station = station.lower()
            if station not in self.stations:
                available_stations = ', '.join(self.stations.keys())
                return False, f"❌ Invalid station name. Available stations: {available_stations}."
    
            # Ensure user is in a voice channel
            voice_channel = getattr(interaction.user.voice, 'channel', None)
            if not voice_channel:
                return False, "❌ You are not connected to a voice channel."
    
            # Check bot permissions
            bot_member = interaction.guild.me or interaction.guild.get_member(self.bot.user.id)
            bot_perms = voice_channel.permissions_for(bot_member)
            if not bot_perms.connect or not bot_perms.speak:
                return False, "❌ I need the Connect and Speak permissions to join the voice channel."
    
            # Connect or move to voice channel
            voice_client = self.voice_clients.get(interaction.guild.id)
            if voice_client and voice_client.is_connected():
                if voice_client.channel != voice_channel:
                    await voice_client.move_to(voice_channel)
            else:
                voice_client = await voice_channel.connect()
                self.voice_clients[interaction.guild.id] = voice_client
                logger.info(f"Connected to voice channel {voice_channel.name}.")
    
            # Initialize volume if not set
            if interaction.guild.id not in self.guild_volumes:
                self.guild_volumes[interaction.guild.id] = DEFAULT_VOLUME
    
            # Stop if already playing
            if voice_client.is_playing():
                voice_client.stop()
                logger.info("Stopped the currently playing audio.")
                
                # Cancel any existing metadata update task
                if interaction.guild.id in self.metadata_tasks and not self.metadata_tasks[interaction.guild.id].done():
                    self.metadata_tasks[interaction.guild.id].cancel()
    
            # FIX: Use FFmpegPCMAudio instead of FFmpegOpusAudio so we can control volume
            # Create PCM audio source with volume control
            source = discord.FFmpegPCMAudio(
                self.stations[station].url,
                options='-vn -b:a 128k'  # Better audio quality
            )
            
            # Wrap it in a volume transformer BEFORE playing
            audio_source = discord.PCMVolumeTransformer(
                source, 
                volume=self.guild_volumes[interaction.guild.id]
            )
            
            # Play the audio with volume control
            voice_client.play(
                audio_source,
                after=lambda e: self.after_playback(interaction.guild.id, e)
            )
            
            logger.info(
                f"Started playing {self.stations[station].name} "
                f"in {voice_channel.name} for {interaction.user}."
            )
            
            # Create and send the now playing message
            current_station = self.stations[station]
            embed = self.create_now_playing_embed(current_station, interaction.guild.id)
            
            view = NowPlayingView(self, interaction.guild.id)
            
            # Check if there's an existing now playing message
            if interaction.guild.id in self.now_playing_messages:
                old_message, _ = self.now_playing_messages[interaction.guild.id]
                try:
                    # Update the existing message instead of sending a new one
                    updated_message = await old_message.edit(embed=embed, view=view)
                    self.now_playing_messages[interaction.guild.id] = (old_message, station)
                except Exception:
                    # If editing fails, send a new message
                    message = await interaction.channel.send(embed=embed, view=view)
                    self.now_playing_messages[interaction.guild.id] = (message, station)
            else:
                # Send a new message
                message = await interaction.channel.send(embed=embed, view=view)
                self.now_playing_messages[interaction.guild.id] = (message, station)
            
            # Start the metadata update task
            if interaction.guild.id in self.metadata_tasks and not self.metadata_tasks[interaction.guild.id].done():
                self.metadata_tasks[interaction.guild.id].cancel()
            
            self.metadata_tasks[interaction.guild.id] = asyncio.create_task(
                self.update_metadata_loop(interaction.guild.id, current_station)
            )
            
            return True, f"▶️ Now playing **{current_station.name}** in **{voice_channel.name}**."
    
        except Exception as e:
            logger.error(f"Error in play_station: {e}")
            return False, f"An error occurred: {str(e)}"

    def after_playback(self, guild_id: int, error):
        if error:
            logger.error(f"Playback error: {error}")
        asyncio.run_coroutine_threadsafe(self.disconnect_voice_client(guild_id), self.bot.loop)

    async def disconnect_voice_client(self, guild_id: int):
        voice_client = self.voice_clients.get(guild_id)
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            logger.info(f"Disconnected from voice channel in guild ID {guild_id}.")
            if guild_id in self.voice_clients:
                del self.voice_clients[guild_id]
            
            # Cancel metadata update task
            if guild_id in self.metadata_tasks and not self.metadata_tasks[guild_id].done():
                self.metadata_tasks[guild_id].cancel()
                if guild_id in self.metadata_tasks:
                    del self.metadata_tasks[guild_id]
    
    async def adjust_volume(self, guild_id: int, adjustment: float, set_directly: bool = False) -> Tuple[bool, float]:
        """Adjust the volume for a guild."""
        voice_client = self.voice_clients.get(guild_id)
        if not voice_client or not voice_client.is_connected() or not voice_client.source:
            return False, 0.0
        
        # Get current volume
        if guild_id not in self.guild_volumes:
            self.guild_volumes[guild_id] = DEFAULT_VOLUME
        
        # Calculate new volume
        if set_directly:
            new_volume = adjustment  # Direct value
        else:
            new_volume = max(0.0, min(1.0, self.guild_volumes[guild_id] + adjustment))
        
        # Apply the new volume
        voice_client.source.volume = new_volume
        self.guild_volumes[guild_id] = new_volume
        
        return True, new_volume
    
    def create_now_playing_embed(self, station: RadioStation, guild_id: int) -> discord.Embed:
        """Create an embed for the now playing message."""
        embed = discord.Embed(
            title="📻 Now Playing",
            description=f"**{station.name}**",
            color=discord.Color.blue()
        )
        
        # Add station details
        embed.add_field(
            name="Station Information",
            value=(
                f"**Genre:** {station.genre}\n"
                f"**Station ID:** `{station.key}`\n"
                + (f"**Description:** {station.description}\n" if station.description else "")
            ),
            inline=False
        )
        
        # Add current track if available
        if station.current_track:
            embed.add_field(
                name="Currently Playing",
                value=station.current_track,
                inline=False
            )
        
        # Add volume information
        volume_percent = int(self.guild_volumes.get(guild_id, DEFAULT_VOLUME) * 100)
        embed.add_field(
            name="Volume",
            value=f"{volume_percent}%",
            inline=True
        )
        
        # Add station icon if available
        if station.icon_url:
            embed.set_thumbnail(url=station.icon_url)
        
        # Add timestamp
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="Use the buttons below to control playback")
        
        return embed
    
    async def update_now_playing(self, guild_id: int, stopped: bool = False):
        """Update the now playing message."""
        if guild_id not in self.now_playing_messages:
            return
        
        message, station_key = self.now_playing_messages[guild_id]
        try:
            if stopped:
                # Edit to show stopped state
                embed = discord.Embed(
                    title="📻 Radio Stopped",
                    description="The radio is no longer playing.",
                    color=discord.Color.red()
                )
                embed.timestamp = discord.utils.utcnow()
                
                # Try to edit without view (disable controls)
                await message.edit(embed=embed, view=None)
                
                # Remove from tracking
                del self.now_playing_messages[guild_id]
            else:
                # Update the now playing message
                station = self.stations.get(station_key)
                if station:
                    embed = self.create_now_playing_embed(station, guild_id)
                    await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Error updating now playing message: {e}")
            # If there's an error, remove it from tracking
            if guild_id in self.now_playing_messages:
                del self.now_playing_messages[guild_id]
    
    async def update_metadata_loop(self, guild_id: int, station: RadioStation):
        """Loop to update metadata information periodically."""
        try:
            while True:
                # Only perform updates if the bot is still in a voice channel
                voice_client = self.voice_clients.get(guild_id)
                if not voice_client or not voice_client.is_connected():
                    break
                
                # Try to fetch metadata
                new_track = await self.fetch_station_metadata(station)
                
                # If metadata changed, update the embed
                if new_track and new_track != station.current_track:
                    station.current_track = new_track
                    station.last_updated = time.time()
                    await self.update_now_playing(guild_id)
                    logger.debug(f"Updated metadata for {station.name}: {new_track}")
                
                # Wait before next update
                await asyncio.sleep(30)  # Update every 30 seconds
        except asyncio.CancelledError:
            logger.debug(f"Metadata update task for guild {guild_id} was cancelled.")
        except Exception as e:
            logger.error(f"Error in metadata update loop: {e}")
    
    async def fetch_station_metadata(self, station: RadioStation) -> Optional[str]:
        """Try to fetch current track metadata from the stream."""
        try:
            # This is a simple implementation that works for some Icecast/Shoutcast streams
            # A more robust solution would use a library like PyIcy or custom parsing
            async with aiohttp.ClientSession() as session:
                async with session.get(station.url, headers={'Icy-MetaData': '1'}) as response:
                    # Check headers for metadata
                    icy_name = response.headers.get('icy-name', '').strip()
                    icy_description = response.headers.get('icy-description', '').strip()
                    icy_genre = response.headers.get('icy-genre', '').strip()
                    
                    # Try to get the currently playing track
                    # Many streams include this in the icy-name or other headers
                    result = []
                    if icy_name:
                        result.append(f"**{icy_name}**")
                    
                    # Some stations include the current track in response content
                    # This is a very simplified approach - many stations require more complex parsing
                    content_bytes = await response.content.read(4096)  # Read just a sample
                    content = content_bytes.decode('utf-8', errors='ignore')
                    
                    # Look for common metadata patterns
                    track_patterns = [
                        r'StreamTitle=\'([^\']+)\'',
                        r'<nowplaying>([^<]+)</nowplaying>',
                        r'current_song="([^"]+)"'
                    ]
                    
                    for pattern in track_patterns:
                        match = re.search(pattern, content)
                        if match:
                            current_track = match.group(1).strip()
                            result.append(f"**Now Playing:** {current_track}")
                            break
                    
                    # Add additional information if available
                    if icy_genre and "Variety" not in icy_genre:
                        result.append(f"**Genre:** {icy_genre}")
                    
                    if icy_description:
                        result.append(f"**Info:** {icy_description}")
                    
                    return "\n".join(result) if result else None
        except Exception as e:
            logger.error(f"Error fetching metadata for {station.name}: {e}")
            return None
    
    # ------------------------------ Cog Events ------------------------------
    async def cog_unload(self):
        # Clean up voice clients when the cog is unloaded
        for voice_client in list(self.voice_clients.values()):
            try:
                await voice_client.disconnect()
                logger.info(
                    f"Disconnected from voice channel in guild {voice_client.guild.name} during cog unload."
                )
            except:
                pass
        self.voice_clients.clear()
        
        # Cancel all metadata tasks
        for task in self.metadata_tasks.values():
            if not task.done():
                task.cancel()
        
        logger.info("Cleaned up all voice clients and tasks on cog unload.")

# ------------------------------ Cog Setup ------------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(RadioCog(bot))
    logger.info("Loaded RadioCog.")