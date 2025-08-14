"""
Profile management system package.
Handles member profiles, service records, and military information.
"""

import logging

async def setup(bot):
    """Setup function called by discord.py when loading the cog."""
    from .cog import ProfileCog
    
    # Create a logger if the bot doesn't have one
    logger = getattr(bot, 'logger', logging.getLogger('profile'))
    
    try:
        await bot.add_cog(ProfileCog(bot))
        logger.info("Successfully loaded ProfileCog")
    except Exception as e:
        logger.error(f"Failed to load ProfileCog: {e}")
        raise