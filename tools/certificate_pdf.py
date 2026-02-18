#!/usr/bin/env python3
"""
Clinical AI Documentation Integrity Certificate - PDF Generator

Generates an official-looking PDF certificate for clinical documentation integrity.
The certificate is designed for compliance officers and auditors.

Usage:
    python certificate_pdf.py <certificate.json> [output.pdf]
"""

import sys
import json
from pathlib import Path
from datetime import datetime
import io

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import qrcode
except ImportError:
    print("❌ Error: Required packages not installed.")
    print("Please install: pip install reportlab qrcode pillow")
    sys.exit(1)


def load_certificate(filepath: str) -> dict:
    """Load certificate JSON from file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Certificate file not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in certificate file: {e}")
        sys.exit(1)


def generate_qr_code(data: str, box_size: int = 10) -> io.BytesIO:
    """Generate QR code as BytesIO object."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


def create_certificate_pdf(packet: dict, output_path: str):
    """
    Generate a professional PDF certificate.
    
    Args:
        packet: The accountability packet/certificate
        output_path: Path to save the PDF
    """
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    story = []
    
    # Styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#333333'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#0066cc'),
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#1a1a1a'),
        fontName='Helvetica'
    )
    
    # Title
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("CLINICAL AI DOCUMENTATION", title_style))
    story.append(Paragraph("INTEGRITY CERTIFICATE", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Subtitle
    story.append(Paragraph("Cryptographically Verifiable Governance Proof", subtitle_style))
    story.append(Spacer(1, 0.5*inch))
    
    # Certificate Information Section
    story.append(Paragraph("Certificate Information", section_style))
    
    # Extract data
    cert_id = packet['transaction_id']
    timestamp = packet['gateway_timestamp_utc']
    model = packet.get('model_fingerprint', 'Unknown')
    policy_ref = packet['policy_receipt']['policy_change_ref']
    param_snapshot = packet.get('param_snapshot', {})
    human_reviewed = "Yes" if param_snapshot.get('human_reviewed', False) else "No"
    human_editor = param_snapshot.get('human_editor_id', 'N/A')
    
    # Governance metadata
    governance_metadata = packet.get('governance_metadata', {})
    encounter_id = 'N/A'
    note_type = 'N/A'
    if governance_metadata:
        clinical_context = governance_metadata.get('clinical_context', {})
        encounter_id = clinical_context.get('encounter_id', 'N/A')
        note_type = clinical_context.get('note_type', 'N/A')
    
    # Build info table
    info_data = [
        ['Certificate ID:', cert_id],
        ['Issued (UTC):', timestamp],
        ['Encounter ID:', encounter_id],
        ['Note Type:', note_type],
        ['AI Model:', model],
        ['Policy Version:', policy_ref],
        ['Human Reviewed:', human_reviewed],
    ]
    
    if human_editor != 'N/A':
        info_data.append(['Reviewer:', human_editor])
    
    info_table = Table(info_data, colWidths=[2*inch, 4.5*inch])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0066cc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Governance Checks Section
    if governance_metadata:
        checks = governance_metadata.get('governance_checks', [])
        if checks:
            story.append(Paragraph("Governance Checks Executed", section_style))
            checks_text = "<br/>".join([f"✓ {check}" for check in checks])
            story.append(Paragraph(checks_text, normal_style))
            story.append(Spacer(1, 0.3*inch))
    
    # Cryptographic Proof Section
    story.append(Paragraph("Cryptographic Proof", section_style))
    
    final_hash = packet['halo_chain']['final_hash']
    signature = packet['verification']['signature']
    
    crypto_data = [
        ['HALO Chain Hash:', final_hash[:40] + '...'],
        ['Digital Signature:', signature[:40] + '...'],
    ]
    
    crypto_table = Table(crypto_data, colWidths=[2*inch, 4.5*inch])
    crypto_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Courier'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#0066cc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    story.append(crypto_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Verification Instructions
    story.append(Paragraph("Verification Instructions", section_style))
    
    verification_text = """
    This certificate can be verified offline without contacting the issuer.<br/><br/>
    
    <b>To verify:</b><br/>
    1. Obtain the verification script: verify_clinical_certificate.py<br/>
    2. Run: python verify_clinical_certificate.py certificate.json<br/>
    3. The script will validate the HALO chain and cryptographic signature<br/><br/>
    
    <b>What this certificate proves:</b><br/>
    • AI documentation governance was executed at the time of generation<br/>
    • Note integrity is tamper-evident (any modification breaks the chain)<br/>
    • Certificate cannot be forged or backdated without cryptographic key<br/>
    • All governance checks listed above were performed<br/><br/>
    
    <b>What is NOT stored:</b><br/>
    • No Protected Health Information (PHI) in plaintext<br/>
    • No raw clinical note text<br/>
    • Only cryptographic hashes for integrity verification
    """
    
    story.append(Paragraph(verification_text, normal_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Footer
    story.append(Spacer(1, 0.5*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER,
        fontName='Helvetica-Oblique'
    )
    
    story.append(Paragraph(
        "This certificate is generated by ELI Sentinel Clinical Documentation Integrity Layer",
        footer_style
    ))
    story.append(Paragraph(
        f"Certificate Hash (first 16 chars): {final_hash[:16]}",
        footer_style
    ))
    
    # Build PDF
    doc.build(story)


def main():
    """Main execution flow."""
    
    if len(sys.argv) < 2:
        print("Usage: python certificate_pdf.py <certificate.json> [output.pdf]")
        sys.exit(1)
    
    certificate_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "certificate.pdf"
    
    print(f"\n📄 Loading certificate from: {certificate_path}")
    packet = load_certificate(certificate_path)
    
    print(f"📄 Generating PDF certificate: {output_path}")
    create_certificate_pdf(packet, output_path)
    
    print(f"✅ Certificate PDF generated successfully!")
    print(f"   Output: {output_path}\n")


if __name__ == "__main__":
    main()
