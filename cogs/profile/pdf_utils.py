"""PDF export utilities for the profile system."""

import io
import logging
from typing import Dict, Any, Optional, List
import discord
from datetime import datetime, timezone

# Setup logging
logger = logging.getLogger('profile.pdf')

async def generate_profile_pdf(member: discord.Member, profile_data: Dict[str, Any], formatter) -> io.BytesIO:
    """
    Generate a PDF version of a profile.
    
    Args:
        member: The Discord member
        profile_data: The profile data dictionary
        formatter: The formatter to use for formatting fields
        
    Returns:
        BytesIO object containing the PDF data
    """
    try:
        # Import reportlab
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        
        values = profile_data.get('values', {})
        
        # Create a buffer for the PDF
        buffer = io.BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            alignment=1,  # Center alignment
            textColor=colors.darkgreen,
            spaceAfter=0.25*inch
        )
        
        subtitle_style = ParagraphStyle(
            'Subtitle',
            parent=styles['Heading2'],
            alignment=1,  # Center alignment
            textColor=colors.darkgreen,
            spaceAfter=0.25*inch
        )
        
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Heading2'],
            textColor=colors.darkblue,
            spaceBefore=0.2*inch,
            spaceAfter=0.1*inch
        )
        
        # Prepare content
        content = []
        
        # Add title
        content.append(Paragraph(f"HLN STARWARD FLEET", title_style))
        content.append(Paragraph(f"PERSONNEL FILE: {member.display_name}", subtitle_style))
        content.append(Spacer(1, 0.25*inch))
        
        # Add basic info
        content.append(Paragraph("BASIC INFORMATION", header_style))
        
        basic_info = [
            ["SERVICE ID:", values.get('ID Number', 'N/A')],
            ["RANK:", values.get('Rank', 'N/A')],
            ["DIVISION:", values.get('Division', 'N/A')],
            ["SPECIALIZATION:", values.get('Specialization', 'N/A')],
            ["STATUS:", values.get('Status', 'N/A')],
            ["JOIN DATE:", values.get('Join Date', 'N/A')]
        ]
        
        basic_table = Table(basic_info, colWidths=[2*inch, 4*inch])
        basic_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('RIGHTPADDING', (0, 0), (0, -1), 10),
            ('LEFTPADDING', (1, 0), (1, -1), 10),
        ]))
        
        content.append(basic_table)
        content.append(Spacer(1, 0.25*inch))
        
        # Add service statistics
        content.append(Paragraph("SERVICE STATISTICS", header_style))
        
        mission_count = values.get('Mission Count', 0)
        completed_missions = formatter.parse_list_field(values.get('Completed Missions', []))
        combat_missions = formatter.parse_list_field(values.get('Combat Missions', []))
        awards = formatter.parse_list_field(values.get('Awards', []))
        
        stats_info = [
            ["MISSION COUNT:", str(mission_count)],
            ["COMBAT OPERATIONS:", str(len(combat_missions))],
            ["DECORATIONS:", str(len(awards))]
        ]
        
        stats_table = Table(stats_info, colWidths=[2*inch, 4*inch])
        stats_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('RIGHTPADDING', (0, 0), (0, -1), 10),
            ('LEFTPADDING', (1, 0), (1, -1), 10),
        ]))
        
        content.append(stats_table)
        content.append(Spacer(1, 0.25*inch))
        
        # Add certifications
        content.append(Paragraph("CERTIFICATIONS", header_style))
        
        certifications = formatter.parse_list_field(values.get('Certifications', []))
        if certifications:
            cert_data = []
            for cert in certifications:
                cert_data.append([f"• {cert}"])
                
            cert_table = Table(cert_data, colWidths=[6*inch])
            cert_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('LEFTPADDING', (0, 0), (0, -1), 10),
            ]))
            
            content.append(cert_table)
        else:
            content.append(Paragraph("No certifications recorded", styles['Normal']))
            
        content.append(Spacer(1, 0.25*inch))
        
        # Add decorations and awards
        content.append(Paragraph("DECORATIONS AND AWARDS", header_style))
        
        if awards:
            award_data = []
            for award in awards:
                award_parts = award.split(' - ')
                award_name = award_parts[0]
                award_citation = award_parts[1] if len(award_parts) > 1 else "No citation"
                award_date = award_parts[2] if len(award_parts) > 2 else "No date"
                
                award_data.append([award_name, award_citation, award_date])
                
            award_table = Table(award_data, colWidths=[1.5*inch, 3*inch, 1*inch])
            award_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ]))
            
            content.append(award_table)
        else:
            content.append(Paragraph("No decorations or awards recorded", styles['Normal']))
            
        content.append(Spacer(1, 0.25*inch))
        
        # Add mission history
        content.append(Paragraph("MISSION HISTORY", header_style))
        
        if completed_missions:
            mission_data = []
            for mission in completed_missions:
                mission_data.append([f"• {mission}"])
                
            mission_table = Table(mission_data, colWidths=[6*inch])
            mission_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('LEFTPADDING', (0, 0), (0, -1), 10),
            ]))
            
            content.append(mission_table)
        else:
            content.append(Paragraph("No missions recorded", styles['Normal']))
            
        # Add footer
        content.append(Spacer(1, 0.5*inch))
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        content.append(Paragraph(f"Generated: {timestamp}", styles['Normal']))
        content.append(Paragraph("HLN STARWARD FLEET - CONFIDENTIAL", styles['Normal']))
        
        # Build the PDF
        doc.build(content)
        
        # Get the PDF data
        buffer.seek(0)
        return buffer
        
    except ImportError:
        logger.error("ReportLab library not installed - PDF generation not available")
        raise ImportError("ReportLab library is required for PDF generation")
    except Exception as e:
        logger.error(f"Error generating PDF: {e}", exc_info=True)
        raise