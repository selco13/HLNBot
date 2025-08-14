# cogs/news_updater.py

import discord
from discord.ext import commands, tasks
import feedparser
import logging
import os
from typing import Set
import json
from datetime import datetime
import requests  # Ensure this is installed: pip install requests
from bs4 import BeautifulSoup  # For parsing HTML

# Import your configuration
import config

class NewsUpdaterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.feed_url = 'https://status.robertsspaceindustries.com/index.xml'
        self.seen_entries_file = 'cogs/seen_entries.json'
        self.seen_entries: Set[str] = set()
        self.game_news_channel_id = config.GAME_NEWS_CHANNEL_ID
        self.admin_notifications_channel_id = config.ADMIN_NOTIFICATIONS_CHANNEL_ID
        self.fetch_interval = config.FETCH_INTERVAL_MINUTES

        # Load seen entries from file if it exists
        self.load_seen_entries()

        # If starting fresh, mark all current entries as seen without posting
        if not self.seen_entries:
            logging.info("No seen entries found. Marking all current feed entries as seen.")
            self.mark_current_entries_as_seen()

        # Start the background task
        self.fetch_feed.start()

    def cog_unload(self):
        self.fetch_feed.cancel()
        self.save_seen_entries()

    def load_seen_entries(self):
        """Load seen entries from a JSON file to prevent duplicate postings."""
        if os.path.exists(self.seen_entries_file):
            try:
                with open(self.seen_entries_file, 'r') as f:
                    self.seen_entries = set(json.load(f))
                logging.info(f"Loaded {len(self.seen_entries)} seen entries from {self.seen_entries_file}.")
            except Exception as e:
                logging.error(f"Failed to load seen entries: {e}")
        else:
            self.seen_entries = set()
            logging.info("No seen entries file found. Starting fresh.")

    def save_seen_entries(self):
        """Save seen entries to a JSON file."""
        try:
            with open(self.seen_entries_file, 'w') as f:
                json.dump(list(self.seen_entries), f)
            logging.info(f"Saved {len(self.seen_entries)} seen entries to {self.seen_entries_file}.")
        except Exception as e:
            logging.error(f"Failed to save seen entries: {e}")

    def mark_current_entries_as_seen(self):
        """Fetch the current RSS feed and mark all entries as seen without posting."""
        try:
            response = requests.get(self.feed_url)
            response.encoding = 'utf-8'  # Force utf-8 encoding

            if response.status_code != 200:
                error_message = f"Failed to fetch RSS feed during initialization. Status code: {response.status_code}"
                logging.error(error_message)
                # Optionally, notify admins
                asyncio.create_task(self.notify_admin(error_message))
                return

            feed = feedparser.parse(response.text)

            if feed.bozo:
                error_message = f"Failed to parse feed during initialization: {feed.bozo_exception}"
                logging.error(error_message)
                asyncio.create_task(self.notify_admin(error_message))
                return

            for entry in feed.entries:
                self.seen_entries.add(entry.id)

            self.save_seen_entries()
            logging.info("All current feed entries have been marked as seen.")
        except Exception as e:
            error_message = f"An error occurred during initialization while marking entries as seen: {e}"
            logging.error(error_message)
            asyncio.create_task(self.notify_admin(error_message))

    @tasks.loop(minutes=1.0)  # Placeholder, will be set in before_loop
    async def fetch_feed(self):
        """Background task to fetch RSS feed and post updates."""
        try:
            logging.info("Fetching RSS feed...")
            response = requests.get(self.feed_url)
            response.encoding = 'utf-8'  # Force utf-8 encoding

            if response.status_code != 200:
                error_message = f"Failed to fetch RSS feed. Status code: {response.status_code}"
                logging.error(error_message)
                await self.notify_admin(error_message)
                return

            feed = feedparser.parse(response.text)

            if feed.bozo:
                error_message = f"Failed to parse feed: {feed.bozo_exception}"
                logging.error(error_message)
                await self.notify_admin(error_message)
                return

            new_entries = [entry for entry in feed.entries if entry.id not in self.seen_entries]

            if not new_entries:
                logging.info("No new updates found.")
                return

            channel = self.bot.get_channel(self.game_news_channel_id)
            if not channel:
                error_message = f"Game News channel with ID {self.game_news_channel_id} not found."
                logging.error(error_message)
                await self.notify_admin(error_message)
                return

            for entry in new_entries:
                # Format the message by stripping HTML
                title = self.strip_html(entry.title)
                link = entry.link
                summary = self.strip_html(entry.summary) if 'summary' in entry else 'No summary available.'

                embed = discord.Embed(
                    title=title,
                    url=link,
                    description=summary,
                    color=0x00ff00,  # Green color
                )

                # Add publication timestamp if available
                if 'published_parsed' in entry and entry.published_parsed:
                    publish_time = datetime(*entry.published_parsed[:6])
                    embed.timestamp = publish_time

                # Add image if available
                if 'media_content' in entry:
                    media = entry.media_content
                    if isinstance(media, list) and len(media) > 0 and 'url' in media[0]:
                        embed.set_image(url=media[0]['url'])

                embed.set_footer(text="Powered by Roberts Space Industries Status Feed")

                try:
                    await channel.send(embed=embed)
                    logging.info(f"Posted new update: {title}")
                    # Mark this entry as seen
                    self.seen_entries.add(entry.id)
                except discord.Forbidden:
                    error_message = f"Missing permissions to send messages in channel ID {self.game_news_channel_id}."
                    logging.error(error_message)
                    await self.notify_admin(error_message)
                except discord.HTTPException as e:
                    error_message = f"Failed to send message in channel ID {self.game_news_channel_id}: {e}"
                    logging.error(error_message)
                    await self.notify_admin(error_message)

            # Save the updated seen entries
            self.save_seen_entries()

        except Exception as e:
            error_message = f"An error occurred while fetching the RSS feed: {e}"
            logging.error(error_message)
            await self.notify_admin(error_message)

    @fetch_feed.before_loop
    async def before_fetch_feed(self):
        """Wait until the bot is ready before starting the task and set fetch interval."""
        await self.bot.wait_until_ready()
        logging.info("NewsUpdaterCog is now running.")
        self.fetch_feed.change_interval(minutes=self.fetch_interval)

    async def notify_admin(self, message: str):
        """Send error notifications to the Admin Notifications channel."""
        try:
            admin_channel = self.bot.get_channel(self.admin_notifications_channel_id)
            if admin_channel:
                embed = discord.Embed(
                    title="News Updater Error",
                    description=message,
                    color=0xff0000,  # Red color
                    timestamp=datetime.utcnow()
                )
                await admin_channel.send(embed=embed)
            else:
                logging.error(f"Admin Notifications channel with ID {self.admin_notifications_channel_id} not found.")
        except Exception as e:
            logging.error(f"Failed to send notification to admin channel: {e}")

    @commands.command(name='manual_fetch_news', help='Manually fetch and post the latest news updates.')
    @commands.has_any_role(*[discord.Object(id=role_id) for role_id in config.AUTHORIZED_ROLE_IDS])
    async def manual_fetch_news(self, ctx):
        """Command to manually fetch and post the latest news updates."""
        await ctx.send("🔄 Fetching the latest news updates...")
        await self.fetch_feed()

    # Error handling for commands within this cog
    @manual_fetch_news.error
    async def manual_fetch_news_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send("❌ You do not have permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("❌ An error occurred while fetching the news.")
            logging.error(f"Error in manual_fetch_news command: {error.original}")
        else:
            await ctx.send("❌ An unexpected error occurred.")
            logging.error(f"Unexpected error in manual_fetch_news command: {error}")

    def strip_html(self, html_content: str) -> str:
        """Utility method to strip HTML tags from a string."""
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text()

async def setup(bot):
    await bot.add_cog(NewsUpdaterCog(bot))

