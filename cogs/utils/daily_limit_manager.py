import logging
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger('daily_limit')

class DailyLimitManager:
    """Manages Discord's daily command creation limits."""
    
    def __init__(self):
        self.daily_commands_used = 0
        self.last_reset = datetime.now()
        self.daily_limit = 180  # Conservative limit below Discord's 200
        self.data_file = Path('data/command_limit_state.json')
        self.data_file.parent.mkdir(exist_ok=True)
        self.load_state()

    def load_state(self):
        """Load saved state if it exists."""
        try:
            if self.data_file.exists():
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.daily_commands_used = data.get('daily_commands_used', 0)
                    self.last_reset = datetime.fromisoformat(data.get('last_reset', datetime.now().isoformat()))
                    self.check_reset()
        except Exception as e:
            logger.error(f"Error loading limit state: {e}")
            self.reset_daily_count()

    def save_state(self):
        """Save current state."""
        try:
            with open(self.data_file, 'w') as f:
                json.dump({
                    'daily_commands_used': self.daily_commands_used,
                    'last_reset': self.last_reset.isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Error saving limit state: {e}")

    def check_reset(self):
        """Check if we should reset the daily count."""
        now = datetime.now()
        
        # Reset if it's been 24 hours since last reset
        time_diff = now - self.last_reset
        if time_diff.total_seconds() >= 24 * 60 * 60:  # 24 hours in seconds
            self.reset_daily_count()
            return True
            
        return False

    def reset_daily_count(self):
        """Reset the daily command count."""
        self.daily_commands_used = 0
        self.last_reset = datetime.now()
        self.save_state()
        logger.info("Reset daily command count")

    def can_add_commands(self, count: int) -> bool:
        """Check if we can add more commands today."""
        was_reset = self.check_reset()
        if was_reset:
            logger.info("Daily limit was reset")
        
        remaining = self.daily_limit - self.daily_commands_used
        can_add = (self.daily_commands_used + count) <= self.daily_limit
        
        logger.info(f"Can add {count} commands? {can_add} (Used: {self.daily_commands_used}, Remaining: {remaining})")
        return can_add

    def add_commands(self, count: int):
        """Record that commands were added."""
        self.daily_commands_used += count
        self.save_state()
        remaining = self.daily_limit - self.daily_commands_used
        logger.info(f"Added {count} commands. Used: {self.daily_commands_used}/{self.daily_limit} (Remaining: {remaining})")

    def get_remaining(self) -> int:
        """Get remaining commands for today."""
        self.check_reset()
        return max(0, self.daily_limit - self.daily_commands_used)
