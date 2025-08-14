"""Discord-compatible visualization utilities."""

import io
import logging
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
import discord
from typing import List, Dict, Any, Optional

logger = logging.getLogger('profile.visualizations')

async def generate_stats_chart(profile_data: Dict[str, Any]) -> discord.File:
    """Generate a matplotlib chart for profile statistics and return as Discord file."""
    try:
        # Extract relevant data
        mission_count = int(profile_data.get('Mission Count') or 0)
        combat_missions = len(profile_data.get('Combat Missions', []))
        awards = len(profile_data.get('Awards', []))
        certifications = len(profile_data.get('Certifications', []))
        
        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), dpi=100)
        
        # Create bar chart for main stats
        categories = ['Missions', 'Combat', 'Awards', 'Certifications']
        values = [mission_count, combat_missions, awards, certifications]
        colors = ['#4e73df', '#1cc88a', '#f6c23e', '#36b9cc']
        
        ax1.bar(categories, values, color=colors)
        ax1.set_title('Service Statistics', fontsize=16)
        ax1.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add data labels
        for i, v in enumerate(values):
            ax1.text(i, v+0.5, str(v), ha='center')
        
        # Create pie chart for mission types
        mission_types = profile_data.get('Mission Types', [])
        if mission_types:
            # Count occurrences of each mission type
            type_counts = {}
            for mission_type in mission_types:
                if isinstance(mission_type, str):
                    mission_type = mission_type.split(' (')[0]  # Extract base type before any parentheses
                    type_counts[mission_type] = type_counts.get(mission_type, 0) + 1
            
            if type_counts:
                labels = list(type_counts.keys())
                sizes = list(type_counts.values())
                
                ax2.pie(sizes, labels=labels, autopct='%1.1f%%', 
                        shadow=True, startangle=90)
                ax2.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
                ax2.set_title('Mission Type Distribution', fontsize=16)
            else:
                ax2.text(0.5, 0.5, 'No mission data available', 
                        ha='center', va='center', fontsize=14)
                ax2.axis('off')
        else:
            ax2.text(0.5, 0.5, 'No mission data available', 
                    ha='center', va='center', fontsize=14)
            ax2.axis('off')
        
        plt.tight_layout()
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        
        # Close the figure to free memory
        plt.close(fig)
        
        # Return as Discord file
        return discord.File(buf, filename='profile_stats.png')
    except Exception as e:
        logger.error(f"Error generating stats chart: {e}", exc_info=True)
        # Create simple error image
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, f"Error generating visualization:\n{str(e)}", 
                ha='center', va='center', fontsize=14)
        ax.axis('off')
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        
        return discord.File(buf, filename='error.png')

async def generate_award_chart(awards: List[str]) -> Optional[discord.File]:
    """Generate a visual grid of awards."""
    if not awards:
        return None
    
    try:    
        # Prepare canvas
        fig, ax = plt.subplots(figsize=(10, max(4, len(awards)//3 + 1)), dpi=100)
        ax.axis('off')
        
        # Set background color
        fig.patch.set_facecolor('#36393F')  # Discord dark theme color
        
        # Prepare awards data
        award_names = []
        award_dates = []
        
        for award in awards:
            parts = award.split(' - ')
            name = parts[0]
            date = parts[2] if len(parts) > 2 else "Unknown"
            award_names.append(name)
            award_dates.append(date)
        
        # Create table
        table_data = []
        for i in range(len(award_names)):
            table_data.append([award_names[i], award_dates[i]])
        
        # Create table
        table = ax.table(
            cellText=table_data,
            colLabels=["Award", "Date"],
            loc='center',
            cellLoc='center',
            colWidths=[0.7, 0.3]
        )
        
        # Style the table
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1, 1.5)
        
        # Color rows based on award name
        for i in range(len(award_names)):
            name = award_names[i]
            if 'Gold' in name:
                color = '#FFD700'  # Gold
            elif 'Silver' in name:
                color = '#C0C0C0'  # Silver
            elif 'Excellence' in name:
                color = '#B19CD9'  # Light purple
            else:
                color = '#90EE90'  # Light green
            
            table[(i+1, 0)].set_facecolor(color)
            table[(i+1, 0)].set_text_props(color='black')
        
        plt.tight_layout()
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        
        # Close the figure to free memory
        plt.close(fig)
        
        # Return as Discord file
        return discord.File(buf, filename='awards.png')
    except Exception as e:
        logger.error(f"Error generating award chart: {e}", exc_info=True)
        return None

async def generate_career_timeline(profile_data: Dict[str, Any]) -> Optional[discord.File]:
    """Generate a timeline visualization of career progression."""
    try:
        join_date = profile_data.get('Join Date')
        if not join_date:
            return None
            
        # Create a figure
        fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
        
        # Set up basic timeline
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
        
        events = []
        
        # Add join date
        events.append((join_date, "Joined HLN Starward Fleet"))
        
        # Extract events from awards (sorted by date)
        awards = profile_data.get('Awards', [])
        for award in awards:
            parts = award.split(' - ')
            if len(parts) >= 3:
                award_name = parts[0]
                award_date = parts[2]
                events.append((award_date, f"Awarded {award_name}"))
        
        # Sort events by date
        try:
            from datetime import datetime
            sorted_events = sorted(events, key=lambda x: datetime.strptime(x[0], "%Y-%m-%d"))
        except:
            sorted_events = events
        
        # Plot timeline events
        for i, (date, description) in enumerate(sorted_events):
            ax.plot(i, 0, 'o', markersize=10, color='#1f77b4')
            ax.annotate(description, 
                        xy=(i, 0), 
                        xytext=(0, 10 if i % 2 == 0 else -30),
                        textcoords="offset points",
                        ha='center', 
                        va='bottom' if i % 2 == 0 else 'top',
                        fontsize=10,
                        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))
            ax.annotate(date, 
                        xy=(i, 0), 
                        xytext=(0, 30 if i % 2 == 0 else -10),
                        textcoords="offset points",
                        ha='center', 
                        fontsize=8,
                        color='gray')
        
        # Set the limits and remove axes
        ax.set_xlim(-0.5, len(sorted_events) - 0.5)
        ax.set_ylim(-2, 2)
        ax.axis('off')
        
        plt.tight_layout()
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        
        # Close the figure to free memory
        plt.close(fig)
        
        # Return as Discord file
        return discord.File(buf, filename='career_timeline.png')
    except Exception as e:
        logger.error(f"Error generating career timeline: {e}", exc_info=True)
        return None

async def generate_service_comparison(data1: Dict[str, Any], data2: Dict[str, Any], 
                                      member1_name: str, member2_name: str) -> Optional[discord.File]:
    """Generate a comparison chart for two members' service records."""
    try:
        # Extract key metrics for comparison
        metrics = [
            ('Mission Count', 'Missions'),
            ('Combat Missions', 'Combat Ops'),
            ('Awards', 'Awards'),
            ('Certifications', 'Certifications')
        ]
        
        # Get values
        values1 = []
        values2 = []
        labels = []
        
        for field, label in metrics:
            if field == 'Combat Missions':
                val1 = len(data1.get(field, []))
                val2 = len(data2.get(field, []))
            elif field == 'Awards' or field == 'Certifications':
                val1 = len(data1.get(field, []))
                val2 = len(data2.get(field, []))
            else:
                val1 = int(data1.get(field, 0))
                val2 = int(data2.get(field, 0))
                
            values1.append(val1)
            values2.append(val2)
            labels.append(label)
        
        # Create a bar chart
        x = np.arange(len(labels))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(10, 6), dpi=100)
        rects1 = ax.bar(x - width/2, values1, width, label=member1_name)
        rects2 = ax.bar(x + width/2, values2, width, label=member2_name)
        
        # Add labels and title
        ax.set_ylabel('Count')
        ax.set_title('Service Record Comparison')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.legend()
        
        # Add value labels above bars
        def autolabel(rects):
            for rect in rects:
                height = rect.get_height()
                ax.annotate(f'{height}',
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom')
        
        autolabel(rects1)
        autolabel(rects2)
        
        plt.tight_layout()
        
        # Save to bytes buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        
        # Close the figure to free memory
        plt.close(fig)
        
        # Return as Discord file
        return discord.File(buf, filename='service_comparison.png')
    except Exception as e:
        logger.error(f"Error generating service comparison: {e}", exc_info=True)
        return None