"""
Certificate PDF Generation Service

Generates formal PDF certificates for legal and audit purposes.
Uses ReportLab to create professional-looking PDF documents.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from typing import Dict, Any
from datetime import datetime


def generate_certificate_pdf(certificate: Dict[str, Any], valid: bool = None) -> bytes:
    """
    Generate a formal PDF certificate.
    
    Args:
        certificate: Certificate dictionary
        valid: Optional verification status (True/False/None if not verified)
        
    Returns:
        PDF bytes
    """
    buffer = BytesIO()
    
    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=18,
    )
    
    # Build story (content elements)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2c5282'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold'
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        fontName='Helvetica'
    )
    
    # Title
    title = Paragraph("Clinical Documentation Integrity Certificate", title_style)
    story.append(title)
    story.append(Spacer(1, 0.3 * inch))
    
    # Verification Status Seal (if provided)
    if valid is not None:
        status_text = "VERIFIED" if valid else "INVALID"
        status_color = colors.green if valid else colors.red
        
        status_style = ParagraphStyle(
            'StatusStyle',
            parent=styles['Heading1'],
            fontSize=36,
            textColor=status_color,
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        status_para = Paragraph(f"<b>{status_text}</b>", status_style)
        story.append(status_para)
        story.append(Spacer(1, 0.2 * inch))
    
    # Certificate Information
    story.append(Paragraph("Certificate Information", heading_style))
    
    cert_info_data = [
        ["Certificate ID:", certificate.get("certificate_id", "N/A")],
        ["Tenant ID:", certificate.get("tenant_id", "N/A")],
        ["Issued:", _format_timestamp(certificate.get("timestamp"))],
        ["Finalized:", _format_timestamp(certificate.get("finalized_at"))],
    ]
    
    cert_info_table = Table(cert_info_data, colWidths=[2*inch, 4*inch])
    cert_info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c5282')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(cert_info_table)
    story.append(Spacer(1, 0.2 * inch))
    
    # Governance Metadata
    story.append(Paragraph("Governance & Compliance", heading_style))
    
    gov_data = [
        ["Model Version:", certificate.get("model_version", "N/A")],
        ["Prompt Version:", certificate.get("prompt_version", "N/A")],
        ["Policy Version:", certificate.get("governance_policy_version", "N/A")],
        ["Policy Hash:", _format_hash_prefix(certificate.get("policy_hash"))],
        ["Human Reviewed:", "Yes" if certificate.get("human_reviewed") else "No"],
    ]
    
    gov_table = Table(gov_data, colWidths=[2*inch, 4*inch])
    gov_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c5282')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(gov_table)
    
    # Governance summary if available
    if certificate.get("governance_summary"):
        story.append(Spacer(1, 0.1 * inch))
        summary_para = Paragraph(
            f"<i>{certificate['governance_summary']}</i>",
            body_style
        )
        story.append(summary_para)
    
    story.append(Spacer(1, 0.2 * inch))
    
    # Integrity Chain
    story.append(Paragraph("Integrity Chain", heading_style))
    
    chain = certificate.get("integrity_chain", {})
    prev_hash = chain.get("previous_hash")
    chain_hash = chain.get("chain_hash")
    
    chain_data = [
        ["Previous Hash:", _format_hash_prefix(prev_hash) if prev_hash else "(First in chain)"],
        ["Chain Hash:", _format_hash_prefix(chain_hash)],
    ]
    
    chain_table = Table(chain_data, colWidths=[2*inch, 4*inch])
    chain_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c5282')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(chain_table)
    
    story.append(Spacer(1, 0.1 * inch))
    integrity_note = Paragraph(
        "<i>Any modification to the certificate data breaks verification.</i>",
        body_style
    )
    story.append(integrity_note)
    story.append(Spacer(1, 0.2 * inch))
    
    # Cryptographic Signature
    story.append(Paragraph("Cryptographic Signature", heading_style))
    
    sig = certificate.get("signature", {})
    sig_data = [
        ["Key ID:", sig.get("key_id", "N/A")],
        ["Algorithm:", sig.get("algorithm", "N/A")],
        ["Signature:", _format_hash_prefix(sig.get("signature"), length=32) + "..."],
    ]
    
    sig_table = Table(sig_data, colWidths=[2*inch, 4*inch])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2c5282')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 0.3 * inch))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    
    footer_text = (
        "This certificate provides cryptographic proof of clinical documentation integrity. "
        "Full hash values and verification details are not included to protect sensitive data. "
        "Verify authenticity using the official verification API or offline verification tool."
    )
    footer = Paragraph(footer_text, footer_style)
    story.append(footer)
    
    # Build PDF
    doc.build(story)
    
    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


def _format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return ts


def _format_hash_prefix(hash_str: str, length: int = 16) -> str:
    """Format hash for display (prefix only)."""
    if not hash_str:
        return "N/A"
    if len(hash_str) <= length:
        return hash_str
    return f"{hash_str[:length]}..."
