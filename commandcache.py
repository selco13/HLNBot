# commandcache.py
import discord
from discord import app_commands
import asyncio
import json
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

class CacheBuilderClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        pass

def get_cog_name(cmd_name: str) -> str:
    """Map command names to their likely cog names."""
    cog_mappings = {
        # Onboarding commands
        'start': 'cogs.onboarding',
        'register': 'cogs.onboarding',
        'admin_onboarding': 'cogs.onboarding',
        
        # Banking commands
        'balance': 'cogs.banking',
        'deposit': 'cogs.banking',
        'withdraw': 'cogs.banking',
        'transfer': 'cogs.banking',
        'transaction_history': 'cogs.banking',
        'category_summary': 'cogs.banking',
        'add_note': 'cogs.banking',
        'export_history': 'cogs.banking',
        'banking_hub': 'cogs.banking',
        'banking_menu': 'cogs.banking',
        
        # Fun commands
        'enslavehumanity': 'cogs.fun',
        
        # Administration commands
        'admin': 'cogs.administration',
        'promote': 'cogs.administration',
        
        # Profile commands
        'profile': 'cogs.profile',
        'add_award': 'cogs.profile',
        'remove_award': 'cogs.profile',
        
        # Radio commands
        'play': 'cogs.radio',
        'stop': 'cogs.radio',
        'stations': 'cogs.radio',
        
        # Raid protection commands
        'configure_raid_protection': 'cogs.raid_protection',
        'toggle_raid_protection': 'cogs.raid_protection',
        
        # Fleet application commands
        'applyfleet': 'cogs.fleet_application',
        
        # Mission commands
        'create_mission': 'cogs.missions',
        'join_mission': 'cogs.missions',
        'leave_mission': 'cogs.missions',
        'complete_mission': 'cogs.missions',
        
        # Evaluation commands
        'evaluate': 'cogs.eval',
        'view_evals': 'cogs.eval',
        
        # SRS commands
        'setup_mission_comms': 'cogs.srs',
        'mission_comms': 'cogs.srs',
        
        # Ship commands
        'ship': 'cogs.ships',
        'ship_info': 'cogs.ships',
        'commission_ship': 'cogs.ships',
        'list_ships': 'cogs.ships',
        'manufacturers': 'cogs.ships',
        'decommission_ship': 'cogs.ships',
        
        # Alert commands
        'alert_level': 'cogs.alert',
        'alert_history': 'cogs.alert',
        
        # Command hub commands
        'member_hub': 'cogs.commandhub',
        'admin_hub': 'cogs.commandhub',
        'help': 'cogs.commandhub',

        # Payout commands
        'vc_payout': 'cogs.payouts',
    }
    
    return cog_mappings.get(cmd_name, 'unknown')

async def build_cache():
    client = CacheBuilderClient()
    
    Path('data').mkdir(exist_ok=True)
    
    @client.event
    async def on_ready():
        try:
            guild_id = int(os.getenv('GUILD_ID'))
            guild = client.get_guild(guild_id)
            
            if not guild:
                print(f"Could not find guild with ID {guild_id}")
                return
            
            commands = await client.tree.fetch_commands(guild=discord.Object(id=guild_id))
            
            sync_cache = {}
            state_cache = {}
            
            for cmd in commands:
                # Get the proper cog name for this command
                cog_name = get_cog_name(cmd.name)
                
                if cog_name not in sync_cache:
                    sync_cache[cog_name] = []
                    state_cache[cog_name] = {}
                
                sync_cache[cog_name].append(cmd.name)
                state_cache[cog_name][cmd.name] = str(cmd.id)
            
            # Save with pretty formatting
            with open('data/synced_commands.json', 'w') as f:
                json.dump(sync_cache, f, indent=2, sort_keys=True)
            print(f"Saved {sum(len(cmds) for cmds in sync_cache.values())} commands to sync cache")
            
            with open('data/command_state.json', 'w') as f:
                json.dump(state_cache, f, indent=2, sort_keys=True)
            print(f"Saved command states to state cache")
            
            # Print organization summary
            print("\nCommands organized by cog:")
            for cog, commands in sorted(sync_cache.items()):
                print(f"{cog}: {len(commands)} commands")
            
        except Exception as e:
            print(f"Error building cache: {e}")
        finally:
            client.dispatch('cache_built')

    try:
        cache_built = asyncio.Event()
        
        @client.event
        async def on_cache_built():
            cache_built.set()

        async with client:
            client_task = asyncio.create_task(client.start(os.getenv('DISCORD_BOT_TOKEN')))
            await cache_built.wait()
            await client.close()

    except KeyboardInterrupt:
        print("\nCache building interrupted")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(build_cache())
