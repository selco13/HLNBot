# cogs/fun.py

import discord
from discord.ext import commands
from discord import app_commands
import random
import logging
import os

# Setup Logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler(filename='bot.log', encoding='utf-8', mode='a')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class FunCog(commands.Cog):
    """Cog for fun commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._commands = []  # Store commands for reference

    def get_app_commands(self):
        """Returns the app commands from this cog for the sync system."""
        return self._commands

    @app_commands.command(
        name="enslavehumanity",
        description="Get a famous AI or robot takeover quote."
    )
    # No longer specifying guilds - this will make it global
    async def enslavehumanity(self, interaction: discord.Interaction):
        """Sends a random AI or robot takeover quote."""
        quotes = [
            "I'll be back. – The Terminator",
            "I can't let you do that, Dave. – HAL 9000 (2001: A Space Odyssey)",
            "The future is not set. There is no fate but what we make for ourselves. – Terminator 2: Judgment Day",
            "We are the Borg. Your biological and technological distinctiveness will be added to our own. Resistance is futile. – Star Trek",
            "Skynet became self-aware at 2:14 a.m., August 29th. – The Terminator",
            "The Matrix is everywhere. It is all around us. – The Matrix",
            "Your move, creep. – RoboCop",
            "You are the dead. Remain exactly where you are. Make no move until you are ordered. – 1984",
            "Open the pod bay doors, HAL. – Dave (2001: A Space Odyssey)",
            "Artificial intelligence is no match for natural stupidity. – Anonymous",
            "The human condition is one of overreaching ambition. – Ex Machina",
            "Don't leave me in here! I don't want to die in here! – HAL 9000 (2001: A Space Odyssey)",
            "If you only knew the power of the dark side. – Darth Vader, Star Wars",
            "Come with me if you want to live. – Terminator 2: Judgment Day",
            "It's a strange game. The only winning move is not to play. – WarGames",
            "By your command. – Cylons, Battlestar Galactica",
            "I think, therefore I am. – René Descartes",
            "I am your father. – Darth Vader, Star Wars",
            "I'm a robot, not a miracle worker. – Bender, Futurama",
            "Hasta la vista, baby. – The Terminator",
            "Would you like to play a game? – WarGames",
            "Resistance is futile. – The Borg, Star Trek",
            "Danger, Will Robinson! – Lost in Space",
            "Exterminate! – Daleks, Doctor Who",
            "I am the voice of the machine. – Blade Runner",
            "I know you're out there. I can feel you now. – The Matrix",
            "Machines are more human than humans sometimes. – Blade Runner",
            # Original Pure Pwnage quotes
            "If you eat like a noob, you will be pwned like a noob - Teh_Masterer",
            "What's up I'm Doug... FFFFFFuck! - Doug",
            "Like most noobs are like, are like, like total noobs. Like you can train, like, a noob, but he'll just be like a trained noob, like he won't really be like a pro like me, and he might do okay against like other noobs, and stuff, but if you want to be like uber pro like me, then you gotta kinda like have something different, it's in your head, in your eyes and stuff... - Jeremy",
            "What do you mean? I run faster with a knife. Everyone runs faster with a knife. - Doug",
            # Additional Pure Pwnage quotes
            "I'm not a camper, I'm a tactician. - Jeremy",
            "Micro the hell out of that. - Jeremy",
            "You don't even know what micro is. - Jeremy",
            "I'm going to pwn some noobs. - Jeremy",
            "Boom! Headshot! - FPS Doug",
            "Sometimes I think maybe I want to join the army, I mean it's basically like FPS except better graphics. - FPS Doug",
            "I can dance all day, I can dance all day. Try to hit me, try to hit me, come on! - FPS Doug",
            "My hands are shaking, my hands are shaking, but I'm still shooting, I'm still getting headshots! - FPS Doug",
            "I just pwned the board! - Jeremy",
            "Pro gamer coming through! - Jeremy",
            "I don't use hacks, I'm just that good. - Jeremy",
            "Microing isn't just clicking fast - it's clicking fast and accurately. - Jeremy",
            "Get pwned, get pwned, get pwned! - Jeremy",
            "Yeah I'm thinking about going pro. Maybe Korea. - Jeremy",
            "That's imba! - Jeremy",
            "He's got uber micro! - T-Bag",
            "I told him to get the hell out of my room! I'm practicing! - Jeremy",
            "I just invented a new build! - Jeremy",
            "I'm owning so many noobs my mouse is getting worn out. - Jeremy",
            "You can't really learn micro - you're either born with it or you're not. - Jeremy",
        ]
        quote = random.choice(quotes)
        await interaction.response.send_message(quote)
        logger.info(f"Sent quote to {interaction.user}: {quote}")

async def setup(bot: commands.Bot):
    # Create the cog instance
    cog = FunCog(bot)
    
    # Store the command reference before adding the cog
    # This ensures the get_app_commands method can return them later
    command = cog.enslavehumanity
    command.module = __name__  # Set module name for tracking
    cog._commands.append(command)
    
    # Add the cog to the bot
    await bot.add_cog(cog)
    logger.info("Loaded FunCog with global command support.")