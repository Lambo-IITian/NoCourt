from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os, json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_JUSTIFY

from backend.services.db_service import init_db, create_case, update_case, get_case, update_emails
from backend.services.email_service import send_respondent_invite, send_settlement_email
from backend.agents.intake_agent import run_intake_agent
from backend.agents.legal_agent import run_legal_agent
from backend.agents.analytics_agent import run_analytics_agent
from backend.agents.document_agent import generate_demand_letter_pdf
from backend.agents.negotiation_agent import run_negotiation_round, generate_settlement_agreement

app = FastAPI(title="AI Legal Dispute Resolver")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_db()
app.mount("/static", StaticFiles(directory="frontend"), name="static")

BASE_URL = "http://localhost:8000"

# ── Request Models ────────────────────────────────────────────────
class DisputeInput(BaseModel):
    dispute_text: str
    claimant_email: str
    respondent_email: str
    claimant_name: Optional[str] = ""
    respondent_name: Optional[str] = ""

class InviteInput(BaseModel):
    case_id: str

class RespondentOfferInput(BaseModel):
    case_id: str
    respondent_offer: float
    respondent_name: Optional[str] = ""

class ClaimantOfferInput(BaseModel):
    case_id: str
    claimant_offer: float

class SettlementInput(BaseModel):
    case_id: str
    settled_amount: float

# ── Pages ─────────────────────────────────────────────────────────
@app.get("/")
def serve_frontend():
    return FileResponse("frontend/index.html")

@app.get("/respond/{case_id}", response_class=HTMLResponse)
def serve_respondent_portal(case_id: str):
    """Unique URL for the respondent — served from frontend."""
    with open("frontend/respond.html", "r") as f:
        return HTMLResponse(f.read())

# ── Analysis ──────────────────────────────────────────────────────
@app.post("/api/analyze")
async def analyze_dispute(input: DisputeInput):
    if len(input.dispute_text.strip()) < 20:
        raise HTTPException(400, "Please describe your dispute in more detail.")
    try:
        case_id = create_case(input.dispute_text, input.claimant_email, input.respondent_email)

        print(f"[{case_id}] Intake Agent...")
        case_data = run_intake_agent(input.dispute_text)

        # Override names if provided
        if input.claimant_name:
            case_data["claimant_name"] = input.claimant_name
        if input.respondent_name:
            case_data["respondent_name"] = input.respondent_name

        print(f"[{case_id}] Legal Research Agent...")
        legal_data = run_legal_agent(case_data)

        print(f"[{case_id}] Analytics Agent...")
        analytics_data = run_analytics_agent(case_data, legal_data)

        print(f"[{case_id}] Document Agent...")
        pdf_path = generate_demand_letter_pdf(case_id, case_data, legal_data, analytics_data)

        full_data = {
            "case": case_data, "legal": legal_data,
            "analytics": analytics_data, "pdf_path": pdf_path,
            "negotiation_history": [], "status": "AWAITING_RESPONDENT",
            "claimant_offer": None, "respondent_offer": None,
        }
        update_case(case_id, "AWAITING_RESPONDENT", full_data)
        print(f"[{case_id}] ✅ Done!")

        return {
            "case_id": case_id, "case": case_data,
            "legal": legal_data, "analytics": analytics_data,
            "pdf_ready": True,
        }
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(500, str(e))


# ── Send Invite to Respondent ─────────────────────────────────────
@app.post("/api/send-invite")
async def send_invite(input: InviteInput):
    """Sends Azure email to respondent with their unique portal link."""
    case = get_case(input.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    case_data  = case["case_data"].get("case", {})
    claim_amt  = f"{case_data.get('currency','')} {case_data.get('claim_amount','N/A')}"

    sent = send_respondent_invite(
        respondent_email = case["respondent_email"],
        respondent_name  = case_data.get("respondent_name", "Respondent"),
        claimant_name    = case_data.get("claimant_name", "Claimant"),
        case_id          = input.case_id,
        dispute_summary  = case_data.get("summary", ""),
        claim_amount     = claim_amt,
        base_url         = BASE_URL,
    )
    if not sent:
        raise HTTPException(500, "Failed to send email. Check Azure Communication Services config.")

    updated = case["case_data"]
    updated["invite_sent"] = True
    update_case(input.case_id, "AWAITING_RESPONDENT", updated)

    return {"success": True, "message": f"Invite sent to {case['respondent_email']}"}


# ── Respondent submits their offer ───────────────────────────────
@app.post("/api/respondent-offer")
async def respondent_offer(input: RespondentOfferInput):
    """Called from the respondent's portal when they submit their offer."""
    case = get_case(input.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    updated = case["case_data"]
    updated["respondent_offer"] = input.respondent_offer
    if input.respondent_name:
        updated["case"]["respondent_name"] = input.respondent_name
    updated["status"] = "RESPONDENT_REPLIED"
    update_case(input.case_id, "RESPONDENT_REPLIED", updated)

    return {
        "success": True,
        "case_id": input.case_id,
        "case_summary": updated["case"].get("summary"),
        "claim_amount": updated["case"].get("claim_amount"),
        "currency": updated["case"].get("currency"),
        "legal_standing": updated["legal"].get("legal_standing"),
        "win_probability": updated["analytics"].get("win_probability"),
        "respondent_offer": input.respondent_offer,
    }


# ── Get respondent view of a case ────────────────────────────────
@app.get("/api/case-for-respondent/{case_id}")
def get_case_for_respondent(case_id: str):
    """Returns limited case info for the respondent portal."""
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    cd = case["case_data"]
    return {
        "case_id":        case_id,
        "status":         case["status"],
        "summary":        cd.get("case", {}).get("summary"),
        "dispute_type":   cd.get("case", {}).get("dispute_type"),
        "claim_amount":   cd.get("case", {}).get("claim_amount"),
        "currency":       cd.get("case", {}).get("currency"),
        "claimant_name":  cd.get("case", {}).get("claimant_name"),
        "respondent_name":cd.get("case", {}).get("respondent_name"),
        "key_facts":      cd.get("case", {}).get("key_facts", []),
        "legal_standing": cd.get("legal", {}).get("legal_standing"),
        "legal_summary":  cd.get("legal", {}).get("legal_summary"),
        "key_rights":     cd.get("legal", {}).get("key_rights", []),
        "respondent_defenses": cd.get("legal", {}).get("respondent_defenses", []),
        "win_probability":cd.get("analytics", {}).get("win_probability"),
        "recommended_action": cd.get("legal", {}).get("recommended_action"),
        "respondent_offer_submitted": cd.get("respondent_offer") is not None,
    }


# ── Claimant submits their offer, triggers AI mediation ──────────
@app.post("/api/negotiate")
async def negotiate(input: ClaimantOfferInput):
    case = get_case(input.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    cd = case["case_data"]
    respondent_offer = cd.get("respondent_offer")

    if respondent_offer is None:
        raise HTTPException(400, "Respondent has not submitted their offer yet.")

    case_data      = cd.get("case", {})
    legal_data     = cd.get("legal", {})
    analytics_data = cd.get("analytics", {})
    history        = cd.get("negotiation_history", [])
    round_number   = len(history) + 1

    if round_number > 3:
        raise HTTPException(400, "Maximum 3 negotiation rounds reached.")

    try:
        print(f"[{input.case_id}] Negotiation Round {round_number}...")
        result = run_negotiation_round(
            case_data, legal_data, analytics_data,
            round_number, input.claimant_offer, respondent_offer, history
        )

        history.append({
            "round": round_number,
            "claimant_offer": input.claimant_offer,
            "respondent_offer": respondent_offer,
            "ai_proposed": result.get("ai_proposed_amount"),
            "timestamp": datetime.now().isoformat()
        })

        cd["negotiation_history"] = history
        cd["claimant_offer"] = input.claimant_offer
        cd["status"] = "NEGOTIATING"
        update_case(input.case_id, "NEGOTIATING", cd)

        return {
            "case_id": input.case_id,
            "round": round_number,
            "result": result,
            "history": history,
            "rounds_remaining": 3 - round_number,
            "claimant_offer": input.claimant_offer,
            "respondent_offer": respondent_offer,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Settlement ────────────────────────────────────────────────────
@app.post("/api/settle")
async def settle(input: SettlementInput):
    case = get_case(input.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    case_data  = case["case_data"].get("case", {})
    legal_data = case["case_data"].get("legal", {})

    try:
        agreement_text = generate_settlement_agreement(case_data, legal_data, input.settled_amount)
        os.makedirs("outputs", exist_ok=True)
        pdf_path = f"outputs/settlement_{input.case_id}.pdf"

        NAVY  = colors.HexColor("#0F2A4A")
        BLUE  = colors.HexColor("#1565C0")
        LIGHT = colors.HexColor("#E8F0FE")
        GREEN = colors.HexColor("#2E7D32")

        doc = SimpleDocTemplate(pdf_path, pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        story  = []

        hdr = Table([["✅  SETTLEMENT AGREEMENT"]], colWidths=[170*mm])
        hdr.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),GREEN), ("TEXTCOLOR",(0,0),(-1,-1),colors.white),
            ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),16),
            ("ALIGN",(0,0),(-1,-1),"CENTER"), ("TOPPADDING",(0,0),(-1,-1),12), ("BOTTOMPADDING",(0,0),(-1,-1),12),
        ]))
        story.append(hdr)
        story.append(Spacer(1,6*mm))

        info = Table([
            ["Case ID:", input.case_id, "Date:", datetime.now().strftime("%B %d, %Y")],
            ["Claimant:", case_data.get("claimant_name",""), "Respondent:", case_data.get("respondent_name","")],
            ["Settled Amount:", f"{case_data.get('currency','')} {input.settled_amount:,.0f}", "Status:", "FULLY SETTLED"],
        ], colWidths=[30*mm,65*mm,30*mm,45*mm])
        info.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),LIGHT), ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),
            ("FONTNAME",(2,0),(2,-1),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),9),
            ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6),
            ("LEFTPADDING",(0,0),(-1,-1),8), ("BOX",(0,0),(-1,-1),1,BLUE),
            ("INNERGRID",(0,0),(-1,-1),0.3,colors.HexColor("#90A4AE")),
        ]))
        story.append(info)
        story.append(Spacer(1,8*mm))

        body_s = ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=16, spaceAfter=8, alignment=TA_JUSTIFY)
        head_s = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY, spaceAfter=4, spaceBefore=6)
        for para in agreement_text.split('\n\n'):
            para = para.strip()
            if not para: continue
            if para.isupper() or para[0].isdigit():
                story.append(Paragraph(para, head_s))
            else:
                story.append(Paragraph(para, body_s))

        story.append(Spacer(1,10*mm))
        story.append(HRFlowable(width="100%", thickness=1, color=BLUE))
        sig_s = ParagraphStyle("sig", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#546E7A"), leading=14)
        story.append(Spacer(1,4*mm))
        story.append(Paragraph(f"AI-facilitated settlement | Case #{input.case_id} | {datetime.now().strftime('%B %d, %Y')}", sig_s))
        doc.build(story)

        # Email both parties
        sym = "₹" if case_data.get("currency") == "INR" else "$"
        amount_str = f"{sym}{input.settled_amount:,.0f}"
        download_url = f"{BASE_URL}/api/download-settlement/{input.case_id}"

        if case["claimant_email"]:
            send_settlement_email(case["claimant_email"], case_data.get("claimant_name","Claimant"),
                                  input.case_id, amount_str, download_url)
        if case["respondent_email"]:
            send_settlement_email(case["respondent_email"], case_data.get("respondent_name","Respondent"),
                                  input.case_id, amount_str, download_url)

        updated = case["case_data"]
        updated["settlement_amount"] = input.settled_amount
        updated["settlement_pdf"]    = pdf_path
        updated["status"]            = "SETTLED"
        update_case(input.case_id, "SETTLED", updated)

        return {"case_id": input.case_id, "settled_amount": input.settled_amount, "pdf_ready": True}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Downloads ─────────────────────────────────────────────────────
@app.get("/api/download/{case_id}")
def download_demand(case_id: str):
    path = f"outputs/demand_letter_{case_id}.pdf"
    if not os.path.exists(path): raise HTTPException(404, "PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=f"demand_letter_{case_id}.pdf")

@app.get("/api/download-settlement/{case_id}")
def download_settlement(case_id: str):
    path = f"outputs/settlement_{case_id}.pdf"
    if not os.path.exists(path): raise HTTPException(404, "PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=f"settlement_{case_id}.pdf")

@app.get("/api/case/{case_id}")
def get_case_by_id(case_id: str):
    case = get_case(case_id)
    if not case: raise HTTPException(404, "Case not found")
    return case