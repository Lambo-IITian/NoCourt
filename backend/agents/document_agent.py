"""
Document Agent — Three completely separate PDF generators.
Each has its own dedicated GPT prompt agent and its own PDF layout.

Agent 1 → generate_demand_letter_pdf()   (Navy blue — formal demand letter)
Agent 2 → generate_court_file_pdf()      (Red      — court preparation package)
Agent 3 → generate_settlement_pdf()      (Green    — settlement agreement)

Unicode fix: ₹ is replaced with "Rs." for ReportLab (Helvetica has no Unicode).
"""

import json
import os
import re
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)

from backend.services.openai_service import ask_gpt


# ══════════════════════════════════════════════════════════════
# SHARED UTILITIES
# ══════════════════════════════════════════════════════════════

def _safe(text: str) -> str:
    """
    Make text safe for ReportLab (Helvetica/Times — no Unicode).
    Replaces currency symbols and other non-Latin-1 chars.
    """
    if not text:
        return ""
    text = str(text)
    text = text.replace("₹", "Rs.")
    text = text.replace("€", "EUR ")
    text = text.replace("£", "GBP ")
    text = text.replace("©", "(c)")
    text = text.replace("®", "(R)")
    text = text.replace("™", "(TM)")
    text = text.replace("\u2013", "-")   # en dash
    text = text.replace("\u2014", "--")  # em dash
    text = text.replace("\u2018", "'")   # left single quote
    text = text.replace("\u2019", "'")   # right single quote
    text = text.replace("\u201c", '"')   # left double quote
    text = text.replace("\u201d", '"')   # right double quote
    text = text.replace("\u2022", "-")   # bullet
    text = text.replace("\u2026", "...")  # ellipsis
    # Remove any remaining non-Latin-1 characters
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text


def _sym(case_data: dict) -> str:
    """Returns currency prefix safe for ReportLab."""
    cur = case_data.get("currency", "")
    mapping = {"INR": "Rs.", "USD": "$", "GBP": "GBP ", "EUR": "EUR "}
    return mapping.get(cur, str(cur) + " " if cur else "")


def _amount_str(case_data: dict) -> str:
    if case_data.get("is_monetary", True):
        amt = case_data.get("claim_amount") or 0
        return f"{_sym(case_data)}{int(float(amt)):,}"
    return _safe(case_data.get("non_monetary_demand", "Non-monetary relief"))


def _make_doc(filename: str) -> SimpleDocTemplate:
    os.makedirs("outputs", exist_ok=True)
    return SimpleDocTemplate(
        filename, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )


def _header_table(text: str, bg_color: colors.Color) -> Table:
    t = Table([[_safe(text)]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg_color),
        ("TEXTCOLOR",     (0, 0), (-1, -1), colors.white),
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 15),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    return t


def _body_style(align=TA_JUSTIFY) -> ParagraphStyle:
    return ParagraphStyle(
        "body", fontName="Helvetica", fontSize=10,
        leading=16, spaceAfter=7, alignment=align,
    )


def _h2_style(color: colors.Color) -> ParagraphStyle:
    return ParagraphStyle(
        "h2", fontName="Helvetica-Bold", fontSize=11,
        textColor=color, spaceAfter=5, spaceBefore=10,
    )


def _bullet_style() -> ParagraphStyle:
    return ParagraphStyle(
        "bul", fontName="Helvetica", fontSize=10,
        leading=15, spaceAfter=4, leftIndent=12,
    )


def _sig_style() -> ParagraphStyle:
    return ParagraphStyle(
        "sig", fontName="Helvetica", fontSize=8,
        textColor=colors.HexColor("#607D8B"), leading=12,
    )


def _divider(color: colors.Color, thickness: float = 0.5) -> HRFlowable:
    return HRFlowable(width="100%", thickness=thickness, color=color)


# ══════════════════════════════════════════════════════════════
# AGENT 1 — DEMAND LETTER
# ══════════════════════════════════════════════════════════════

def _demand_letter_agent(case_data: dict, legal_data: dict) -> str:
    """
    DEDICATED GPT AGENT for demand letter body text only.
    Separate from the court file agent — different prompt, different output.
    Returns plain text paragraphs separated by double newlines.
    """
    system_prompt = """You are a senior legal writer specialising in pre-litigation demand letters.

Write a formal, assertive demand letter body. Requirements:
- Exactly 5 paragraphs
- Paragraph 1: Formal salutation + opening reference to dispute
- Paragraph 2: Chronological statement of facts
- Paragraph 3: Cite specific laws and how they support the claim
- Paragraph 4: State the exact demand with a firm 7-day deadline
- Paragraph 5: Consequences if demand is not met (court filing, costs awarded)
- Tone: firm and professional, NOT aggressive
- Use the real names provided — do NOT use [Placeholder] anywhere
- Separate paragraphs with a blank line
- Do NOT add section headers
- Do NOT use bullet points
- Keep total length under 500 words"""

    user_message = f"""Write the demand letter:

From: {case_data.get('claimant_name', 'Claimant')}
To: {case_data.get('respondent_name', 'Respondent')} ({case_data.get('respondent_role', '')})
Dispute summary: {case_data.get('summary', '')}
Demand: {_amount_str(case_data)}
Key facts: {json.dumps(case_data.get('key_facts', []))}
Applicable laws: {json.dumps([l.get('law_name', '') for l in legal_data.get('applicable_laws', [])])}
Legal rights of claimant: {json.dumps(legal_data.get('key_rights', []))}
Legal standing: {legal_data.get('legal_standing', '')}
Jurisdiction: {case_data.get('jurisdiction', 'General')}"""

    return ask_gpt(system_prompt, user_message, json_mode=False)


def generate_demand_letter_pdf(
    case_id: str,
    case_data: dict,
    legal_data: dict,
    analytics_data: dict,
) -> str:
    """Generates demand letter PDF. Returns file path."""
    NAVY   = colors.HexColor("#0F2A4A")
    ACCENT = colors.HexColor("#1565C0")
    LIGHT  = colors.HexColor("#E8F0FE")

    filename = f"outputs/demand_letter_{case_id}.pdf"
    doc      = _make_doc(filename)
    story    = []
    today    = datetime.now().strftime("%B %d, %Y")

    # ── Header ────────────────────────────────────────────
    story.append(_header_table("LEGAL DEMAND NOTICE", NAVY))
    story.append(Spacer(1, 7 * mm))

    # ── Info box ──────────────────────────────────────────
    is_mon  = case_data.get("is_monetary", True)
    win_str = f"{analytics_data.get('win_probability', 'N/A')}%" if is_mon else "Non-monetary"

    info = Table(
        [
            [_safe("Case ID:"),    _safe(case_id),
             _safe("Date:"),       _safe(today)],
            [_safe("Claimant:"),   _safe(case_data.get("claimant_name", "")),
             _safe("Demand:"),     _safe(_amount_str(case_data))],
            [_safe("Respondent:"), _safe(case_data.get("respondent_name", "")),
             _safe("Win Probability:"), _safe(win_str)],
        ],
        colWidths=[30 * mm, 65 * mm, 38 * mm, 37 * mm],
    )
    info.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",      (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 1,   ACCENT),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#90A4AE")),
    ]))
    story.append(info)
    story.append(Spacer(1, 7 * mm))

    # ── Letter body from dedicated agent ──────────────────
    letter_body = _demand_letter_agent(case_data, legal_data)
    bs = _body_style()
    for para in letter_body.split("\n\n"):
        para = _safe(para.strip())
        if para:
            story.append(Paragraph(para.replace("\n", " "), bs))

    story.append(Spacer(1, 8 * mm))
    story.append(_divider(ACCENT, thickness=1))
    story.append(Spacer(1, 5 * mm))

    # ── Applicable laws table ─────────────────────────────
    story.append(Paragraph("APPLICABLE LAWS", _h2_style(NAVY)))
    laws = legal_data.get("applicable_laws", [])
    if laws:
        rows = [["Law / Act", "Jurisdiction", "Favours"]]
        for law in laws:
            fav = {"CLAIMANT": "Claimant", "RESPONDENT": "Respondent", "NEUTRAL": "Neutral"}
            rows.append([
                _safe(law.get("law_name", "")),
                _safe(law.get("jurisdiction", "")),
                _safe(fav.get(law.get("favors", ""), "-")),
            ])
        lt = Table(rows, colWidths=[97 * mm, 47 * mm, 26 * mm])
        lt.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  NAVY),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("LEFTPADDING",    (0, 0), (-1, -1), 6),
            ("BOX",            (0, 0), (-1, -1), 0.5, ACCENT),
            ("INNERGRID",      (0, 0), (-1, -1), 0.3, colors.HexColor("#CFD8DC")),
        ]))
        story.append(lt)

    story.append(Spacer(1, 7 * mm))

    # ── Signature block ───────────────────────────────────
    ss = _sig_style()
    story.append(Paragraph(_safe(f"Issued by: {case_data.get('claimant_name', '')}"), ss))
    story.append(Paragraph(_safe(f"Date: {today}  |  Case #{case_id}"), ss))
    story.append(Paragraph(
        "This notice was prepared with AI legal assistance. "
        "Consult a licensed attorney before formal proceedings.", ss,
    ))

    doc.build(story)
    print(f"[PDF] Demand letter generated: {filename}")
    return filename


# ══════════════════════════════════════════════════════════════
# AGENT 2 — COURT-READY CASE FILE
# ══════════════════════════════════════════════════════════════

def _court_file_agent(case_data: dict, legal_data: dict, analytics_data: dict) -> dict:
    """
    DEDICATED GPT AGENT for court file content.
    Completely different prompt from the demand letter agent.
    Returns structured JSON — not a letter but a litigation preparation package.
    """
    system_prompt = """You are an experienced litigation solicitor preparing a court case file package.

This is NOT a demand letter. This is a structured litigation preparation document.

Return ONLY valid JSON with EXACTLY these fields:
{
  "case_title": "Formal case title e.g. Rajesh Kumar v. ABC Pvt Ltd - Unpaid Salary",
  "court_type": "Which court to file in and why",
  "jurisdiction_basis": "Why this court has jurisdiction over this matter",
  "statement_of_facts": [
    "Fact 1 - specific, numbered, chronological",
    "Fact 2",
    "Fact 3",
    "Fact 4",
    "Fact 5"
  ],
  "legal_arguments": [
    {"heading": "Short argument heading", "detail": "Full legal reasoning with statute references"},
    {"heading": "...", "detail": "..."},
    {"heading": "...", "detail": "..."}
  ],
  "relief_sought": "Exact court orders being requested - be specific",
  "evidence_checklist": [
    {"item": "Document or evidence name", "importance": "CRITICAL", "tip": "How to obtain or present"},
    {"item": "...", "importance": "SUPPORTING", "tip": "..."}
  ],
  "witnesses": [
    {"type": "Witness type", "testimony": "What they can testify about"}
  ],
  "filing_steps": [
    "Step 1: specific action",
    "Step 2: specific action",
    "Step 3: specific action",
    "Step 4: specific action",
    "Step 5: specific action"
  ],
  "pre_filing_actions": [
    "Action to take before filing 1",
    "Action to take before filing 2"
  ],
  "estimated_fee": "Approximate filing fee with currency",
  "time_estimate": "Realistic resolution timeline",
  "case_assessment": "2-3 sentences honest assessment of strengths and risks for court"
}"""

    user_message = f"""Prepare court file for:

Dispute type: {case_data.get('dispute_type')}
Claimant: {case_data.get('claimant_name')} ({case_data.get('claimant_role')})
Respondent: {case_data.get('respondent_name')} ({case_data.get('respondent_role')})
Jurisdiction: {case_data.get('jurisdiction')}
Demand: {_amount_str(case_data)}
Summary: {case_data.get('summary')}
Key facts: {json.dumps(case_data.get('key_facts', []))}
Evidence available: {json.dumps(case_data.get('evidence_mentioned', []))}
Severity: {case_data.get('severity', 'MEDIUM')}
Applicable laws: {json.dumps([l.get('law_name') for l in legal_data.get('applicable_laws', [])])}
Legal standing: {legal_data.get('legal_standing')}
Respondent defenses: {json.dumps(legal_data.get('respondent_defenses', []))}
Win probability: {analytics_data.get('win_probability', 'N/A')}%"""

    raw = ask_gpt(system_prompt, user_message, json_mode=True)
    return json.loads(raw)


def generate_court_file_pdf(
    case_id: str,
    case_data: dict,
    legal_data: dict,
    analytics_data: dict,
) -> str:
    """Generates court-ready case file PDF. Completely different from demand letter. Returns file path."""
    RED  = colors.HexColor("#991B1B")
    LRED = colors.HexColor("#FFF5F5")
    MRED = colors.HexColor("#FEE2E2")
    NAVY = colors.HexColor("#0F2A4A")

    filename = f"outputs/court_file_{case_id}.pdf"
    doc      = _make_doc(filename)
    story    = []
    today    = datetime.now().strftime("%B %d, %Y")

    # Get content from dedicated court file agent
    ct = _court_file_agent(case_data, legal_data, analytics_data)

    h2  = _h2_style(RED)
    bs  = _body_style()
    bul = _bullet_style()
    ss  = _sig_style()

    # ── Header ────────────────────────────────────────────
    story.append(_header_table("COURT-READY CASE FILE", RED))
    story.append(Spacer(1, 5 * mm))

    # ── Case title ────────────────────────────────────────
    story.append(Paragraph(
        _safe(ct.get("case_title", f"Case #{case_id}")),
        ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=12,
                       textColor=RED, spaceAfter=3, alignment=TA_CENTER),
    ))
    story.append(Paragraph(
        _safe(f"Case #{case_id}  |  {today}  |  {case_data.get('jurisdiction', 'General')}"),
        ParagraphStyle("sub", fontName="Helvetica", fontSize=8,
                       textColor=colors.HexColor("#6B7280"), spaceAfter=5, alignment=TA_CENTER),
    ))
    story.append(_divider(RED, thickness=2))
    story.append(Spacer(1, 4 * mm))

    # ── Parties ───────────────────────────────────────────
    parties = Table(
        [
            ["CLAIMANT", "  VS  ", "RESPONDENT"],
            [
                _safe(f"{case_data.get('claimant_name', '')}\n({case_data.get('claimant_role', '')})"),
                "",
                _safe(f"{case_data.get('respondent_name', '')}\n({case_data.get('respondent_role', '')})"),
            ],
        ],
        colWidths=[72 * mm, 26 * mm, 72 * mm],
    )
    parties.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#EFF6FF")),
        ("BACKGROUND",    (2, 0), (2, -1), LRED),
        ("BACKGROUND",    (1, 0), (1, -1), colors.HexColor("#F9FAFB")),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("BOX",           (0, 0), (-1, -1), 0.8, RED),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
    ]))
    story.append(parties)
    story.append(Spacer(1, 5 * mm))

    # ── Court & Jurisdiction ──────────────────────────────
    story.append(Paragraph("COURT & JURISDICTION", h2))
    story.append(Paragraph(_safe(f"Court: {ct.get('court_type', '')}"), bs))
    story.append(Paragraph(_safe(f"Basis: {ct.get('jurisdiction_basis', '')}"), bs))
    story.append(_divider(MRED))

    # ── Statement of facts ────────────────────────────────
    story.append(Paragraph("STATEMENT OF FACTS", h2))
    for i, fact in enumerate(ct.get("statement_of_facts", []), 1):
        story.append(Paragraph(_safe(f"{i}.  {fact}"), bul))
    story.append(_divider(MRED))

    # ── Legal arguments ───────────────────────────────────
    story.append(Paragraph("LEGAL ARGUMENTS", h2))
    for arg in ct.get("legal_arguments", []):
        heading = _safe(arg.get("heading", arg.get("argument", "")))
        detail  = _safe(arg.get("detail",  arg.get("basis", "")))
        story.append(KeepTogether([
            Paragraph(f"<b>► {heading}</b>", bs),
            Paragraph(detail, bul),
            Spacer(1, 2 * mm),
        ]))
    story.append(_divider(MRED))

    # ── Relief sought ─────────────────────────────────────
    story.append(Paragraph("RELIEF SOUGHT", h2))
    story.append(Paragraph(_safe(ct.get("relief_sought", "")), bs))
    story.append(_divider(MRED))

    # ── Evidence checklist ────────────────────────────────
    story.append(Paragraph("EVIDENCE CHECKLIST", h2))
    evid = ct.get("evidence_checklist", [])
    if evid:
        rows = [["#", "Evidence / Document", "Importance", "Tip", "Got?"]]
        for i, e in enumerate(evid, 1):
            imp    = _safe(e.get("importance", "SUPPORTING"))
            imp_lbl = f"[!] {imp}" if imp == "CRITICAL" else imp
            rows.append([
                str(i),
                _safe(e.get("item", "")),
                imp_lbl,
                _safe(e.get("tip", e.get("notes", ""))),
                "[ ]",
            ])
        et = Table(rows, colWidths=[8 * mm, 52 * mm, 28 * mm, 68 * mm, 14 * mm])
        et.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  RED),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LRED]),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("LEFTPADDING",    (0, 0), (-1, -1), 5),
            ("VALIGN",         (0, 0), (-1, -1), "TOP"),
            ("BOX",            (0, 0), (-1, -1), 0.5, RED),
            ("INNERGRID",      (0, 0), (-1, -1), 0.3, MRED),
        ]))
        story.append(et)
    story.append(_divider(MRED))

    # ── Witnesses ─────────────────────────────────────────
    story.append(Paragraph("SUGGESTED WITNESSES", h2))
    for w in ct.get("witnesses", ct.get("witness_list", [])):
        wtype = _safe(w.get("type", ""))
        wtxt  = _safe(w.get("testimony", w.get("purpose", "")))
        story.append(Paragraph(f"<b>{wtype}</b> - {wtxt}", bul))
    story.append(_divider(MRED))

    # ── Pre-filing actions ────────────────────────────────
    story.append(Paragraph("ACTIONS BEFORE FILING", h2))
    for item in ct.get("pre_filing_actions", ct.get("pre_filing_checklist", [])):
        story.append(Paragraph(_safe(f"[ ]  {item}"), bul))
    story.append(_divider(MRED))

    # ── Filing steps ──────────────────────────────────────
    story.append(Paragraph("HOW TO FILE - STEP BY STEP", h2))
    for step in ct.get("filing_steps", ct.get("filing_procedure", [])):
        story.append(Paragraph(_safe(f"->  {step}"), bul))
    story.append(Spacer(1, 4 * mm))

    # ── Fee and time box ──────────────────────────────────
    fee  = _safe(ct.get("estimated_fee", ct.get("estimated_filing_fee", "Varies")))
    time = _safe(ct.get("time_estimate", ct.get("time_to_resolve", "Varies")))
    ft = Table(
        [[f"Estimated Fee: {fee}", f"Time to Resolve: {time}"]],
        colWidths=[85 * mm, 85 * mm],
    )
    ft.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 1,   colors.HexColor("#F59E0B")),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, colors.HexColor("#FDE68A")),
    ]))
    story.append(ft)
    story.append(Spacer(1, 4 * mm))

    # ── Applicable laws ───────────────────────────────────
    story.append(Paragraph("APPLICABLE LAWS", _h2_style(NAVY)))
    laws = legal_data.get("applicable_laws", [])
    if laws:
        lr = [["Law / Act", "Section", "Jurisdiction", "Favours"]]
        for law in laws:
            fav = {"CLAIMANT": "You", "RESPONDENT": "Them", "NEUTRAL": "-"}
            lr.append([
                _safe(law.get("law_name", "")),
                _safe(law.get("section", "-")),
                _safe(law.get("jurisdiction", "")),
                _safe(fav.get(law.get("favors", ""), "-")),
            ])
        lt = Table(lr, colWidths=[75 * mm, 22 * mm, 45 * mm, 28 * mm])
        lt.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  NAVY),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF6FF")]),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ("LEFTPADDING",    (0, 0), (-1, -1), 6),
            ("BOX",            (0, 0), (-1, -1), 0.5, NAVY),
            ("INNERGRID",      (0, 0), (-1, -1), 0.3, colors.HexColor("#CFD8DC")),
        ]))
        story.append(lt)

    story.append(Spacer(1, 4 * mm))

    # ── Case assessment box ───────────────────────────────
    assessment = _safe(ct.get("case_assessment", ct.get("honest_assessment", "")))
    if assessment:
        ab = Table(
            [[f"Case Assessment: {assessment}"]],
            colWidths=[170 * mm],
        )
        ab.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("BOX",           (0, 0), (-1, -1), 1, colors.HexColor("#86EFAC")),
        ]))
        story.append(ab)

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_safe(f"Prepared: {today}  |  Case #{case_id}  |  LegalAI Resolver"), ss))
    story.append(Paragraph("AI-generated guide only. Consult a licensed attorney before filing.", ss))

    doc.build(story)
    print(f"[PDF] Court file generated: {filename}")
    return filename


# ══════════════════════════════════════════════════════════════
# AGENT 3 — SETTLEMENT AGREEMENT
# ══════════════════════════════════════════════════════════════

def _settlement_agent(case_data: dict, legal_data: dict, settled_amount: float) -> str:
    """
    DEDICATED GPT AGENT for settlement agreement text.
    Returns clause-numbered legal agreement text.
    """
    system_prompt = """You are a specialist in drafting legally binding settlement agreements.

Write a formal settlement and release agreement. Rules:
- Number every clause: 1. 2. 3. etc.
- Clause 1: Parties - full identification
- Clause 2: Background - brief dispute history
- Clause 3: Settlement amount and payment terms (7 days, bank transfer)
- Clause 4: Full and final settlement - releases all claims
- Clause 5: Confidentiality
- Clause 6: Non-disparagement
- Clause 7: No admission of liability
- Clause 8: Governing law and jurisdiction
- Clause 9: Entire agreement
- End with a signature block
- Use REAL names - NO placeholders
- Professional legal language throughout
- Separate clauses with blank lines"""

    user_message = f"""Draft the settlement agreement:

Claimant: {case_data.get('claimant_name', 'Claimant')} ({case_data.get('claimant_role', '')})
Respondent: {case_data.get('respondent_name', 'Respondent')} ({case_data.get('respondent_role', '')})
Dispute type: {case_data.get('dispute_type', '')}
Original claim: {_amount_str(case_data)}
Agreed settlement: {_sym(case_data)}{int(settled_amount):,} {case_data.get('currency', '')}
Jurisdiction: {case_data.get('jurisdiction', 'General')}
Governing law: {legal_data.get('applicable_laws', [{}])[0].get('law_name', 'Applicable local laws') if legal_data.get('applicable_laws') else 'Applicable local laws'}"""

    return ask_gpt(system_prompt, user_message, json_mode=False)


def generate_settlement_pdf(
    case_id: str,
    case_data: dict,
    legal_data: dict,
    settled_amount: float,
) -> str:
    """Generates settlement agreement PDF. Returns file path."""
    GREEN  = colors.HexColor("#14532D")
    LGREEN = colors.HexColor("#F0FDF4")

    filename = f"outputs/settlement_{case_id}.pdf"
    doc      = _make_doc(filename)
    story    = []
    today    = datetime.now().strftime("%B %d, %Y")

    # Get text from dedicated settlement agent
    text = _settlement_agent(case_data, legal_data, settled_amount)

    bs = _body_style()
    h2 = _h2_style(GREEN)
    ss = _sig_style()

    # ── Header ────────────────────────────────────────────
    story.append(_header_table("SETTLEMENT AGREEMENT", GREEN))
    story.append(Spacer(1, 6 * mm))

    # ── Summary box ───────────────────────────────────────
    is_mon = case_data.get("is_monetary", True)
    settled_display = (
        f"{_sym(case_data)}{int(settled_amount):,}"
        if is_mon
        else _safe(case_data.get("non_monetary_demand", "Agreement reached"))
    )

    info = Table(
        [
            [_safe("Case ID:"),    _safe(case_id),
             _safe("Date:"),       _safe(today)],
            [_safe("Claimant:"),   _safe(case_data.get("claimant_name", "")),
             _safe("Respondent:"), _safe(case_data.get("respondent_name", ""))],
            [_safe("Settlement:"), _safe(settled_display),
             _safe("Status:"),     "FULL & FINAL SETTLEMENT"],
        ],
        colWidths=[28 * mm, 62 * mm, 32 * mm, 48 * mm],
    )
    info.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LGREEN),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("FONTNAME",      (2, 0), (2, -1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 1,   GREEN),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#A5D6A7")),
    ]))
    story.append(info)
    story.append(Spacer(1, 5 * mm))

    # ── Settlement amount highlight ───────────────────────
    if is_mon:
        hl = Table(
            [[f"AGREED SETTLEMENT:   {settled_display}"]],
            colWidths=[170 * mm],
        )
        hl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), GREEN),
            ("TEXTCOLOR",     (0, 0), (-1, -1), colors.white),
            ("FONTNAME",      (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 13),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(hl)
        story.append(Spacer(1, 6 * mm))

    # ── Agreement body ────────────────────────────────────
    story.append(Paragraph("TERMS OF SETTLEMENT", h2))
    for para in text.split("\n\n"):
        para = _safe(para.strip())
        if para:
            story.append(Paragraph(para.replace("\n", "<br/>"), bs))

    story.append(Spacer(1, 10 * mm))
    story.append(_divider(GREEN, thickness=1.5))
    story.append(Spacer(1, 5 * mm))

    # ── Signature blocks ──────────────────────────────────
    sig_tbl = Table(
        [
            ["CLAIMANT", "", "RESPONDENT"],
            [_safe(case_data.get("claimant_name", "")), "",
             _safe(case_data.get("respondent_name", ""))],
            ["", "", ""],
            ["Signature: _______________________", "",
             "Signature: _______________________"],
            [_safe(f"Date: {today}"), "", _safe(f"Date: {today}")],
        ],
        colWidths=[70 * mm, 30 * mm, 70 * mm],
    )
    sig_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("BACKGROUND",    (0, 0), (0, -1), LGREEN),
        ("BACKGROUND",    (2, 0), (2, -1), LGREEN),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (0, -1), 0.5, GREEN),
        ("BOX",           (2, 0), (2, -1), 0.5, GREEN),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph(
        _safe(f"Generated by LegalAI Resolver  |  Case #{case_id}  |  {today}"), ss,
    ))
    story.append(Paragraph(
        "This agreement constitutes a legally binding document upon signature by both parties.", ss,
    ))

    doc.build(story)
    print(f"[PDF] Settlement agreement generated: {filename}")
    return filename