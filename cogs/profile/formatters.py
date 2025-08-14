"""Enhanced formatting classes for profile displays."""

import logging
import discord
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import math
from .utils import calculate_service_time, format_stellar_date, get_rank_info, parse_list_field
from .security import get_security_classification, get_clearance_code, generate_auth_code
from .constants import (
    SECURITY_LEVELS, STATUS_INDICATORS, DIVISION_ICONS, FIELD_ID_NUMBER,
    FIELD_DIVISION, FIELD_RANK, FIELD_STATUS, FIELD_SPECIALIZATION,
    FIELD_JOIN_DATE, FIELD_AWARDS, FIELD_CERTIFICATIONS, FIELD_COMPLETED_MISSIONS,
    FIELD_MISSION_COUNT, FIELD_COMBAT_MISSIONS, FIELD_STRATEGIC_ASSESSMENT,
    FIELD_COMMAND_EVALUATION, FIELD_SPECIAL_OPERATIONS, FIELD_STRATEGIC_PLANNING,
    FIELD_CLASSIFIED_INFO, DIVISION_RANKS, DIVISION_TO_STANDARD_RANK,
    FLEET_WING_ICONS
)

logger = logging.getLogger('profile.formatters')

def create_progress_bar(value, max_value, width=10):
    """
    Create a Unicode progress bar.
    
    Args:
        value: Current value
        max_value: Maximum value
        width: Width of progress bar in characters
        
    Returns:
        String containing a progress bar
    """
    if max_value <= 0:
        return "░" * width
    
    # Calculate number of filled blocks
    filled = min(width, max(0, int(value / max_value * width)))
    
    # Create the bar with different block characters for visual dimension
    return "█" * filled + "▒" * (width - filled)

class MilitaryIDFormatter:
    """Formats military profile information for display with enhanced visuals."""
    
    @staticmethod
    def create_header(rank: str, values: dict, member: discord.Member) -> str:
        """Create the header section of a profile display with fleet wing icons."""
        from .constants import FLEET_WING_ICONS, SECURITY_LEVELS
        
        classification = get_security_classification(rank or "")
        security_emoji = SECURITY_LEVELS.get(classification, '⚪')
        display_name = member.display_name
        
        # Get fleet wing and its icon if available
        fleet_wing = values.get('Fleet Wing', '')
        wing_icon = FLEET_WING_ICONS.get(fleet_wing, '')
        
        # Include fleet wing icon in the header if available
        fleet_text = f"{wing_icon} {fleet_wing}" if wing_icon and fleet_wing else ""
        
        return (
            f"{security_emoji} **{display_name}** {security_emoji}\n"
            f"{fleet_text}\n"
            f"{security_emoji} **HLN GROUP STARWARD FLEET** {security_emoji}\n"
            "```yaml\n"
            f"SECURITY CLASSIFICATION: {classification}\n"
            f"CLEARANCE CODE: {get_clearance_code(rank or '')}\n"
            "```"
        )

    @staticmethod
    def create_mobile_header(rank: str, values: dict, member: discord.Member) -> str:
        """Create a more compact header for mobile devices with fleet wing."""
        from .constants import FLEET_WING_ICONS, SECURITY_LEVELS
        
        classification = get_security_classification(rank or "")
        security_emoji = SECURITY_LEVELS.get(classification, '⚪')
        display_name = member.display_name
        
        # Get fleet wing and its icon
        fleet_wing = values.get('Fleet Wing', '')
        wing_icon = FLEET_WING_ICONS.get(fleet_wing, '')
        
        # Include fleet wing icon in the header if available
        fleet_text = f"{wing_icon}" if wing_icon else ""
        
        return (
            f"{security_emoji} **{display_name}** {fleet_text} {security_emoji}\n"
            f"```yaml\n"
            f"CLASS: {classification} | {get_clearance_code(rank or '')}\n"
            "```"
        )

    @staticmethod
    def format_basic_info(values: dict, is_mobile: bool = False) -> str:
        """Format basic member information with fleet wing only (no division)."""
        from .constants import STATUS_INDICATORS
        
        # Pull relevant fields with fallbacks
        fleet_wing = values.get('Fleet Wing', 'Non-Fleet')
        
        status = values.get('Status', 'Active')
        status_emoji = STATUS_INDICATORS.get(status, '⚪')
        
        # Get current rank and specialization with proper defaults
        current_rank = values.get('Rank', 'N/A')
        specialty = values.get('Specialization', 'N/A')
        
        # Get ship assignment with fallback and icon
        ship_assignment = values.get('Ship Assignment', '')
        if ship_assignment is None or ship_assignment == '':
            ship_display = "🚫 Unassigned"
        else:
            ship_display = f"🚢 {ship_assignment}"
        
        # If mobile, use a more compact format
        if is_mobile:
            return (
                "```yaml\n"
                f"ID: {values.get('ID Number', 'N/A')}\n"
                f"RANK: {current_rank}\n"
                f"FLEET: {fleet_wing}\n"
                f"SPEC: {specialty}\n"
                f"STATUS: {status_emoji} {status}\n"
                f"SHIP: {ship_display}\n"
                "```"
            )
        else:
            return (
                "```yaml\n"
                f"SERVICE ID: {values.get('ID Number', 'N/A')}\n"
                f"RANK: {current_rank}\n"
                f"FLEET WING: {fleet_wing}\n"
                f"SPECIALIZATION: {specialty}\n"
                f"STATUS: {status_emoji} {status}\n"
                f"SHIP ASSIGNMENT: {ship_display}\n"
                "```"
            )

    @staticmethod
    def format_service_record(values: dict, is_mobile: bool = False) -> str:
        """Format service record information with Fleet Wing only."""
        join_date = values.get('Join Date', 'N/A')
        from .utils import calculate_service_time, format_stellar_date
        service_time = calculate_service_time(join_date)
        
        # Only use Fleet Wing for current assignment
        fleet_wing = values.get('Fleet Wing', 'Non-Fleet')
        
        # Get security clearance with enhanced display
        security_clearance = values.get('Security Clearance', '')
        if not security_clearance:
            security_display = "Standard Clearance"
        else:
            security_display = security_clearance
        
        if is_mobile:
            # Compact format for mobile
            return (
                "```yaml\n"
                f"ENLISTED: {format_stellar_date(join_date)}\n"
                f"SERVICE: {service_time}\n"
                f"WING: {fleet_wing}\n"
                f"CLEARANCE: {security_display}\n"
                "```"
            )
        else:
            return (
                "```yaml\n"
                f"ENLISTMENT DATE: {format_stellar_date(join_date)}\n"
                f"TIME IN SERVICE: {service_time}\n"
                f"FLEET WING: {fleet_wing}\n"
                f"SECURITY CLEARANCE: {security_display}\n"
                "```"
            )

    @staticmethod
    def format_awards(values: dict, is_mobile: bool = False) -> str:
        """Format awards information with better parsing."""
        from .utils import parse_list_field
        
        # Try multiple possible field names for awards
        award_field_names = ['Awards', 'awards', 'FIELD_AWARDS']
        
        # Get the first non-empty field
        awards = None
        for field_name in award_field_names:
            if field_name in values and values[field_name]:
                awards = parse_list_field(values[field_name])
                break
        
        # If no awards found
        if not awards:
            return "```yaml\nNo decorations awarded 🏅\n```"
            
        # Debug log to see what we found
        logger.debug(f"Found {len(awards)} awards: {awards}")
            
        if is_mobile and len(awards) > 3:
            # Show only the most recent 3 for mobile
            lines = []
            for i, award in enumerate(awards[:3]):
                medal_icon = "🥇" if "gold" in award.lower() else "🥈" if "silver" in award.lower() else "🏅"
                lines.append(f"{medal_icon} {award}")
            lines.append(f"...and {len(awards) - 3} more")
            return "```yaml\n" + "\n".join(lines) + "\n```"
        else:
            lines = []
            for award in awards:
                medal_icon = "🥇" if "gold" in award.lower() else "🥈" if "silver" in award.lower() else "🏅"
                lines.append(f"{medal_icon} {award}")
            return "```yaml\n" + "\n".join(lines) + "\n```"

    @staticmethod
    def format_classified_info(values: dict, rank: str) -> Optional[str]:
        """Format classified information if available."""
        from .constants import CLEARANCE_LEVELS
        clearance = CLEARANCE_LEVELS.get(rank, {'level': 1})
        if clearance['level'] >= 4:  # e.g. rank >= Commodore
            cinfo = values.get(FIELD_CLASSIFIED_INFO)
            if cinfo:
                return (
                    "```yaml\n"
                    f"CLASSIFIED INFORMATION - {get_clearance_code(rank)}\n"
                    f"{cinfo}\n"
                    "```"
                )
        return None

    @staticmethod
    def format_mission_log(values: dict, is_mobile: bool = False) -> str:
        """Format mission log information with visual enhancements."""
        missions = parse_list_field(values.get(FIELD_COMPLETED_MISSIONS, []))
        if not missions:
            return "```yaml\nNo missions completed 🚀\n```"
            
        # Format missions with mission type icons
        formatted_missions_list = []
        for mission in missions:
            # Add mission type icons based on content
            if "combat" in mission.lower():
                icon = "⚔️"
            elif "rescue" in mission.lower() or "medical" in mission.lower():
                icon = "🚑"
            elif "transport" in mission.lower() or "cargo" in mission.lower():
                icon = "🚢"
            elif "exploration" in mission.lower() or "survey" in mission.lower():
                icon = "🔭"
            else:
                icon = "🚀"
                
            # Check if we need to convert old-style dates to in-game format
            mission_parts = mission.split(' - ')
            if len(mission_parts) >= 3:
                # Check if the last part is a date in format YYYY-MM-DD
                date_str = mission_parts[-1].strip()
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    # Check if this is already an in-game date (year > 2900)
                    if date_obj.year < 2900:
                        # Convert to in-game date
                        ingame_year = date_obj.year + 930
                        ingame_date = f"{ingame_year}-{date_obj.month:02d}-{date_obj.day:02d}"
                        mission_parts[-1] = ingame_date
                        mission = " - ".join(mission_parts)
                except ValueError:
                    # Not a date or not in expected format, leave as is
                    pass
                    
            formatted_missions_list.append(f"{icon} {mission}")
                
        if is_mobile and len(missions) > 3:
            # Show only the 3 most recent missions for mobile
            formatted_missions = "\n".join(formatted_missions_list[:3])
            formatted_missions += f"\n...and {len(missions) - 3} more"
        else:
            formatted_missions = "\n".join(formatted_missions_list)
            
        return f"```yaml\n{formatted_missions}\n```"

    @staticmethod
    def format_certifications(values: dict, is_mobile: bool = False) -> str:
        """Format certification information with better parsing."""
        from .utils import parse_list_field
        
        # Try multiple possible field names
        cert_field_names = ['Certifications', 'certifications', 'FIELD_CERTIFICATIONS']
        
        # Get the first non-empty field
        certifications = None
        for field_name in cert_field_names:
            if field_name in values and values[field_name]:
                certifications = parse_list_field(values[field_name])
                break
        
        # Debug log
        logger.debug(f"Found {len(certifications) if certifications else 0} certifications") 
        
        if not certifications:
            return "```yaml\nNo certifications recorded 📝\n```"
            
        if is_mobile and len(certifications) > 5:
            # Show only top 5 for mobile
            formatted_certs = "\n".join([f"• {cert}" for cert in certifications[:5]])
            formatted_certs += f"\n...and {len(certifications) - 5} more"
        else:
            formatted_certs = "\n".join([f"• {cert}" for cert in certifications])
            
        return f"```yaml\n{formatted_certs}\n```"
        
    @staticmethod
    def format_grouped_certifications(values: dict, is_mobile: bool = False) -> str:
        """Format certifications grouped by type with better parsing."""
        from .utils import parse_list_field
        
        # Try multiple possible field names
        cert_field_names = ['Certifications', 'certifications', 'FIELD_CERTIFICATIONS']
        
        # Get the first non-empty field
        certifications = None
        for field_name in cert_field_names:
            if field_name in values and values[field_name]:
                certifications = parse_list_field(values[field_name])
                break
        
        if not certifications:
            return "```yaml\nNo certifications recorded 📝\n```"
            
        # Group certifications by type
        combat_certs = []
        technical_certs = []
        special_certs = []
        other_certs = []
        
        for cert in certifications:
            if any(x in cert.lower() for x in ['combat', 'tactical', 'weapons']):
                combat_certs.append(cert)
            elif any(x in cert.lower() for x in ['engineering', 'technical', 'systems', 'communications', 'srs']):
                technical_certs.append(cert)
            elif any(x in cert.lower() for x in ['special', 'advanced', 'classified', 'command', 'officer']):
                special_certs.append(cert)
            else:
                other_certs.append(cert)
                
        # If mobile, limit the number of displayed certs
        if is_mobile:
            max_per_category = 2
            if len(combat_certs) > max_per_category:
                combat_certs = combat_certs[:max_per_category] + [f"...and {len(combat_certs) - max_per_category} more"]
            if len(technical_certs) > max_per_category:
                technical_certs = technical_certs[:max_per_category] + [f"...and {len(technical_certs) - max_per_category} more"]
            if len(special_certs) > max_per_category:
                special_certs = special_certs[:max_per_category] + [f"...and {len(special_certs) - max_per_category} more"]
            if len(other_certs) > max_per_category:
                other_certs = other_certs[:max_per_category] + [f"...and {len(other_certs) - max_per_category} more"]
                
        # Format output
        output = ["```yaml"]
        if combat_certs:
            output.append("⚔️ Combat Certifications:")
            output.extend(f"  • {cert}" for cert in combat_certs)
        if technical_certs:
            output.append("\n🔧 Technical Certifications:")
            output.extend(f"  • {cert}" for cert in technical_certs)
        if special_certs:
            output.append("\n🌟 Special Certifications:")
            output.extend(f"  • {cert}" for cert in special_certs)
        if other_certs:
            output.append("\n📜 Other Certifications:")
            output.extend(f"  • {cert}" for cert in other_certs)
        output.append("```")
        
        return '\n'.join(output)
        
    @staticmethod
    def format_quick_stats(values: dict, is_mobile: bool = False) -> str:
        """Format quick statistics about the member with direct field access."""
        # Get mission count with fallback from multiple possible field names
        mission_count = 0
        for field in ['Mission Count', 'mission_count', 'FIELD_MISSION_COUNT', 'mission_count']:
            if field in values and values[field] not in [None, '']:
                try:
                    mission_count = int(values[field])
                    break
                except (ValueError, TypeError):
                    pass
    
        # Get combat missions with better parsing
        from .utils import parse_list_field
        combat_missions_raw = values.get('Combat_Missions', values.get('combat_missions', []))
        if isinstance(combat_missions_raw, (int, float)):
            # If it's a direct number
            combat_missions = int(combat_missions_raw)
        else:
            # If it's a list or string
            combat_list = parse_list_field(combat_missions_raw)
            combat_missions = len(combat_list)
    
        # Get awards count
        awards_raw = values.get('Awards', values.get('awards', []))
        awards_list = parse_list_field(awards_raw)
        total_awards = len(awards_list)
    
        # Get service time calculation
        join_date = values.get('Join Date', 'Unknown')
        from .utils import calculate_service_time
        service_time = calculate_service_time(join_date)
    
        # Create colorful progress bars
        mission_progress = create_progress_bar(mission_count, 50)
        combat_progress = create_progress_bar(combat_missions, 20)
        award_progress = create_progress_bar(total_awards, 10)
    
        # Debug logging
        logger.debug(f"Stats data: missions={mission_count}, combat={combat_missions}, awards={total_awards}")
    
        # Format differently based on device
        if is_mobile:
            return (
                "```yaml\n"
                "STATISTICS:\n"
                f"Missions: {mission_count} {mission_progress}\n"
                f"Combat: {combat_missions} {combat_progress}\n"
                f"Awards: {total_awards} {award_progress}\n"
                "```"
            )
        else:
            return (
                "```yaml\n"
                "QUICK STATISTICS:\n"
                f"Total Missions: {mission_count} {mission_progress}\n"
                f"Combat Operations: {combat_missions} {combat_progress}\n"
                f"Decorations: {total_awards} {award_progress}\n"
                f"Time in Service: {service_time}\n"
                "```"
            )

class WatermarkGenerator:
    """Generate security watermarks for displays."""
    
    @staticmethod
    def generate_pattern(classification: str) -> str:
        """Generate a pattern for a security classification."""
        patterns = {
            'TOP_SECRET': '▲',
            'SECRET': '■',
            'CONFIDENTIAL': '●',
            'RESTRICTED': '○',
        }
        return f"{patterns.get(classification, '○')} {classification} {patterns.get(classification, '○')}"