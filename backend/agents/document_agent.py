import json
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from backend.services.openai_service import ask_gpt

def generate_demand_letter_text(case_data: dict, legal_data: dict) -> str:
    """Uses GPT to write the actual demand letter content."""

    system_prompt = """You are an expert legal writer. Write a formal legal demand letter.
The letter must be:
- Professional and firm in tone
- Reference specific laws mentioned
- State the demand clearly with a deadline
- Be 4-5 paragraphs long
- Do NOT use placeholders like [Your Name] — use the actual names provided
- End with a clear consequence if demand is not met"""

    user_message = f"""Write a formal legal demand letter with these details:

From: {case_data.get('claimant_name')}
To: {case_data.get('respondent_name')} ({case_data.get('respondent_role')})
Dispute: {case_data.get('summary')}
Amount Claimed: {case_data.get('claim_amount')} {case_data.get('currency')}
Key Facts: {json.dumps(case_data.get('key_facts', []))}
Applicable Laws: {json.dumps([l['law_name'] for l in legal_data.get('applicable_laws', [])])}
Legal Standing: {legal_data.get('legal_standing')}
Key Rights: {json.dumps(legal_data.get('key_rights', []))}

Write the full letter body (no address headers needed, just the paragraphs)."""

    return ask_gpt(system_prompt, user_message, json_mode=False)


def generate_demand_letter_pdf(case_id: str, case_data: dict, legal_data: dict, analytics_data: dict) -> str:
    """
    Generates a professional PDF demand letter.
    Returns the file path of the saved PDF.
    """
    os.makedirs("outputs", exist_ok=True)
    filename = f"outputs/demand_letter_{case_id}.pdf"

    # Get letter content from GPT
    letter_body = generate_demand_letter_text(case_data, legal_data)

    # Colors
    NAVY = colors.HexColor("#0F2A4A")
    ACCENT = colors.HexColor("#1565C0")
    LIGHT = colors.HexColor("#E8F0FE")
    GRAY = colors.HexColor("#546E7A")

    doc = SimpleDocTemplate(filename, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    story = []

    # Header bar
    header = Table([["LEGAL DEMAND NOTICE"]], colWidths=[170*mm])
    header.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("TEXTCOLOR", (0,0), (-1,-1), colors.white),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 16),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 12),
        ("BOTTOMPADDING", (0,0), (-1,-1), 12),
    ]))
    story.append(header)
    story.append(Spacer(1, 8*mm))

    # Case info box
    today = datetime.now().strftime("%B %d, %Y")
    info_data = [
        ["Case ID:", case_id, "Date:", today],
        ["From:", case_data.get('claimant_name',''), "Claim Amount:", f"{case_data.get('claim_amount','N/A')} {case_data.get('currency','')}"],
        ["To:", case_data.get('respondent_name',''), "Win Probability:", f"{analytics_data.get('win_probability','N/A')}%"],
    ]
    info_tbl = Table(info_data, colWidths=[30*mm, 65*mm, 35*mm, 40*mm])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("BOX", (0,0), (-1,-1), 1, ACCENT),
        ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#90A4AE")),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 6*mm))

    # Letter body
    body_style = ParagraphStyle("body", fontName="Helvetica", fontSize=10,
        leading=16, spaceAfter=8, alignment=TA_JUSTIFY)

    for para in letter_body.split('\n\n'):
        para = para.strip()
        if para:
            story.append(Paragraph(para, body_style))

    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=ACCENT))
    story.append(Spacer(1, 4*mm))

    # Applicable laws section
    story.append(Paragraph("APPLICABLE LAWS", ParagraphStyle("h2",
        fontName="Helvetica-Bold", fontSize=11, textColor=NAVY, spaceAfter=4)))

    laws = legal_data.get("applicable_laws", [])
    if laws:
        law_data = [["Law", "Jurisdiction", "Relevance"]]
        for law in laws:
            law_data.append([
                law.get("law_name",""),
                law.get("jurisdiction",""),
                law.get("relevance",""),
            ])
        law_tbl = Table(law_data, colWidths=[90*mm, 50*mm, 30*mm])
        law_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), NAVY),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE", (0,0), (-1,-1), 8.5),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("BOX", (0,0), (-1,-1), 0.5, ACCENT),
            ("INNERGRID", (0,0), (-1,-1), 0.3, colors.HexColor("#CFD8DC")),
        ]))
        story.append(law_tbl)

    story.append(Spacer(1, 6*mm))

    # Signature block
    sig_style = ParagraphStyle("sig", fontName="Helvetica", fontSize=9,
        textColor=GRAY, leading=14)
    story.append(Paragraph(f"Submitted by: <b>{case_data.get('claimant_name','')}</b>", sig_style))
    story.append(Paragraph(f"Generated: {today} | Case #{case_id}", sig_style))
    story.append(Paragraph("This document was prepared with AI legal assistance. Consult a licensed attorney for formal legal advice.", sig_style))

    doc.build(story)
    return filename