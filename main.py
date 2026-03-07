import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from backend.agents.intake_agent      import run_intake_agent
from backend.agents.legal_agent       import run_legal_agent
from backend.agents.analytics_agent   import run_analytics_agent
from backend.agents.document_agent    import (
    generate_demand_letter_pdf,
    generate_court_file_pdf,
    generate_settlement_pdf,          # ← replaces old _save_settlement_pdf + generate_settlement_agreement
)
from backend.agents.negotiation_agent import run_negotiation_round
from backend.services.db_service      import create_case, get_case, update_case, get_cases_by_email
from backend.services.email_service   import send_email

BASE_URL = os.environ.get("BASE_URL", "https://nocourt-1.onrender.com")

app = FastAPI(title="LegalAI Resolver")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ══════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════
class DisputeInput(BaseModel):
    dispute_text:     str
    claimant_email:   str
    respondent_email: Optional[str] = ""
    claimant_name:    Optional[str] = ""
    respondent_name:  Optional[str] = ""
    mode:             Optional[str] = "full"   # "full" or "analysis_only"


class SendInviteInput(BaseModel):
    case_id: str


class RespondentOfferInput(BaseModel):
    case_id:          str
    respondent_offer: float
    respondent_name:  Optional[str] = ""


class ClaimantOfferInput(BaseModel):
    case_id:        str
    claimant_offer: float


class ProposalResponseInput(BaseModel):
    case_id:      str
    party:        str   # "claimant" or "respondent"
    action:       str   # "accept" or "reject"
    round_number: int


class SettleInput(BaseModel):
    case_id:        str
    settled_amount: float


class HistoryInput(BaseModel):
    email: str


# ══════════════════════════════════════════════════════════════
# HTML PAGES
# ══════════════════════════════════════════════════════════════
def _read_html(filename: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "frontend", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/", response_class=HTMLResponse)
def serve_index():
    return HTMLResponse(_read_html("index.html"))


@app.get("/respond/{case_id}", response_class=HTMLResponse)
def serve_respond(case_id: str):
    return HTMLResponse(_read_html("respond.html"))


# ══════════════════════════════════════════════════════════════
# ANALYZE  (runs 4 agents)
# ══════════════════════════════════════════════════════════════
OUTPUTS_DIR = os.environ.get("OUTPUTS_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs"))
@app.post("/api/analyze")
async def analyze_dispute(inp: DisputeInput):
    case_id = uuid.uuid4().hex[:8].upper()

    # Agent 1 — Intake
    print(f"[{case_id}] Intake Agent...")
    case_data = run_intake_agent(inp.dispute_text)
    if inp.claimant_name:
        case_data["claimant_name"] = inp.claimant_name
    if inp.respondent_name:
        case_data["respondent_name"] = inp.respondent_name

    # Agent 2 — Legal Research
    print(f"[{case_id}] Legal Agent...")
    legal_data = run_legal_agent(case_data)

    # Agent 3 — Analytics
    print(f"[{case_id}] Analytics Agent...")
    analytics_data = run_analytics_agent(case_data, legal_data)

    # Agent 4 — Documents (demand letter + court file generated upfront)
    print(f"[{case_id}] Document Agent...")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    try:
        generate_demand_letter_pdf(case_id, case_data, legal_data, analytics_data)
    except Exception as e:
        print(f"[{case_id}] Demand letter warning: {e}")

    try:
        generate_court_file_pdf(case_id, case_data, legal_data, analytics_data)
    except Exception as e:
        print(f"[{case_id}] Court file warning: {e}")

    print(f"[{case_id}] Done!")

    cd = {
        "case":                case_data,
        "legal":               legal_data,
        "analytics":           analytics_data,
        "mode":                inp.mode,
        "negotiation_history": [],
        "respondent_offers":   {},
        "proposal_responses":  {},
        "status":              "ANALYZED",
    }

    create_case(case_id, inp.claimant_email, inp.respondent_email or "", cd)

    return {
        "case_id":   case_id,
        "case":      case_data,
        "legal":     legal_data,
        "analytics": analytics_data,
        "mode":      inp.mode,
    }


# ══════════════════════════════════════════════════════════════
# USER HISTORY (email-based)
# ══════════════════════════════════════════════════════════════
@app.post("/api/my-cases")
def my_cases(inp: HistoryInput):
    if not inp.email:
        raise HTTPException(400, "Email required")
    return {"email": inp.email, "cases": get_cases_by_email(inp.email)}


# ══════════════════════════════════════════════════════════════
# SEND INVITE
# ══════════════════════════════════════════════════════════════
@app.post("/api/send-invite")
def send_invite(inp: SendInviteInput):
    case = get_case(inp.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    cd  = case["case_data"]
    c   = cd.get("case", {})
    sym = "Rs." if c.get("currency") == "INR" else ("$" if c.get("currency") == "USD" else (c.get("currency", "") + " "))

    amount_str = (
        f"{sym}{int(float(c.get('claim_amount') or 0)):,}"
        if c.get("is_monetary", True)
        else c.get("non_monetary_demand", "Non-monetary relief")
    )

    portal     = f"{BASE_URL}/respond/{inp.case_id}"
    claimant   = c.get("claimant_name", "The claimant")
    respondent = c.get("respondent_name", "")
    type_labels = {
        "rental_deposit":  "Rental Deposit Dispute",
        "unpaid_salary":   "Unpaid Salary Dispute",
        "consumer_fraud":  "Consumer Dispute",
        "contract_breach": "Contract Breach",
        "physical_assault":"Physical Assault Claim",
        "harassment":      "Harassment Complaint",
        "defamation":      "Defamation Claim",
        "property_damage": "Property Damage Claim",
        "neighbor_dispute":"Neighbor Dispute",
        "apology_demand":  "Formal Apology Demand",
    }
    dtype = type_labels.get(c.get("dispute_type", ""), "Legal Dispute")

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#f8fafc;padding:16px">
  <div style="background:linear-gradient(135deg,#0F2A4A,#1565C0);padding:32px;border-radius:16px;text-align:center;margin-bottom:16px">
    <div style="font-size:40px;margin-bottom:8px">&#x2696;&#xFE0F;</div>
    <h1 style="color:white;margin:0;font-size:22px;font-weight:800">Legal Dispute Filed</h1>
    <p style="color:#93C5FD;margin:8px 0 0;font-size:13px">Case #{inp.case_id}</p>
  </div>
  <div style="background:white;border-radius:12px;padding:24px;margin-bottom:12px;border:1px solid #e2e8f0">
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0 0 12px">
      {"Dear " + respondent + "," if respondent else "Hello,"}
    </p>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0 0 12px">
      <strong>{claimant}</strong> has filed a <strong>{dtype}</strong> claim against you.<br/>
      <strong>Demand:</strong> {amount_str}
    </p>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0">
      Instead of court, you can resolve this through AI-powered mediation.
      Click below to view the case and submit your response.
    </p>
  </div>
  <div style="text-align:center;margin:20px 0">
    <a href="{portal}"
       style="display:inline-block;background:linear-gradient(135deg,#0F2A4A,#1565C0);
              color:white;padding:14px 36px;border-radius:10px;text-decoration:none;
              font-weight:bold;font-size:15px">
      View Case &amp; Respond &rarr;
    </a>
  </div>
  <p style="color:#94a3b8;font-size:11px;text-align:center;margin:0">
    LegalAI Resolver &middot; Powered by Azure Communication Services
  </p>
</div>"""

    result = send_email(
        case["respondent_email"],
        f"[Action Required] Legal Dispute Case #{inp.case_id}",
        html,
    )
    if not result:
        raise HTTPException(500, "Failed to send email. Check Azure Communication Services config.")

    cd["invite_sent"] = True
    update_case(inp.case_id, "INVITED", cd)
    return {"success": True, "message": f"Invite sent to {case['respondent_email']}"}


# ══════════════════════════════════════════════════════════════
# CASE FOR RESPONDENT
# ══════════════════════════════════════════════════════════════
@app.get("/api/case-for-respondent/{case_id}")
def get_case_for_respondent(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    cd        = case["case_data"]
    history   = cd.get("negotiation_history", [])
    curr_rnd  = len(history) + 1
    offers    = cd.get("respondent_offers", {})
    responses = cd.get("proposal_responses", {})

    active_proposal = None
    if history:
        last = history[-1]
        r    = last["round"]
        if not responses.get(f"round_{r}_respondent"):
            active_proposal = {"round": r, "amount": last["ai_proposed"]}

    return {
        "case_id":             case_id,
        "status":              case["status"],
        "current_round":       curr_rnd,
        "already_submitted":   str(curr_rnd) in offers,
        "active_proposal":     active_proposal,
        "summary":             cd.get("case", {}).get("summary"),
        "dispute_type":        cd.get("case", {}).get("dispute_type"),
        "is_monetary":         cd.get("case", {}).get("is_monetary", True),
        "claim_amount":        cd.get("case", {}).get("claim_amount"),
        "non_monetary_demand": cd.get("case", {}).get("non_monetary_demand"),
        "currency":            cd.get("case", {}).get("currency"),
        "claimant_name":       cd.get("case", {}).get("claimant_name"),
        "respondent_name":     cd.get("case", {}).get("respondent_name"),
        "legal_standing":      cd.get("legal", {}).get("legal_standing"),
        "respondent_defenses": cd.get("legal", {}).get("respondent_defenses", []),
        "win_probability":     cd.get("analytics", {}).get("win_probability"),
        "negotiation_history": history,
        "proposal_responses":  responses,
    }


# ══════════════════════════════════════════════════════════════
# RESPONDENT SUBMITS OFFER
# ══════════════════════════════════════════════════════════════
@app.post("/api/respondent-offer")
def respondent_offer(inp: RespondentOfferInput):
    case = get_case(inp.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    cd      = case["case_data"]
    history = cd.get("negotiation_history", [])
    rnd     = len(history) + 1

    cd.setdefault("respondent_offers", {})[str(rnd)] = inp.respondent_offer
    cd["respondent_offer"] = inp.respondent_offer

    if inp.respondent_name:
        cd["case"]["respondent_name"] = inp.respondent_name

    update_case(inp.case_id, "RESPONDENT_REPLIED", cd)

    c      = cd.get("case", {})
    is_mon = c.get("is_monetary", True)
    sym    = "Rs." if c.get("currency") == "INR" else ("$" if c.get("currency") == "USD" else (c.get("currency", "") + " "))
    offer_display = (
        f"{sym}{int(inp.respondent_offer):,}"
        if is_mon
        else "Non-monetary offer submitted"
    )

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px">
  <div style="background:linear-gradient(135deg,#0F2A4A,#1565C0);padding:28px;border-radius:16px;text-align:center;margin-bottom:16px">
    <h1 style="color:white;margin:0;font-size:20px">Response Received!</h1>
    <p style="color:#93C5FD;margin:8px 0 0">Case #{inp.case_id} &middot; Round {rnd}</p>
  </div>
  <div style="background:white;border-radius:12px;padding:24px;text-align:center;border:1px solid #e2e8f0">
    <p style="color:#64748b;font-size:14px;margin:0 0 8px">Other party's Round {rnd} offer:</p>
    <div style="font-size:36px;font-weight:900;color:#1565C0">{offer_display}</div>
    <p style="color:#94a3b8;font-size:13px;margin-top:12px">Open your case portal and submit your offer to continue.</p>
    <a href="{BASE_URL}/"
       style="display:inline-block;margin-top:16px;background:#1565C0;color:white;
              padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:bold">
      Continue &rarr;
    </a>
  </div>
</div>"""

    send_email(
        case["claimant_email"],
        f"[Round {rnd}] Other party submitted their offer - Case #{inp.case_id}",
        html,
    )

    return {
        "success":      True,
        "round":        rnd,
        "case_id":      inp.case_id,
        "claim_amount": c.get("claim_amount"),
        "currency":     c.get("currency"),
        "is_monetary":  is_mon,
        "summary":      c.get("summary"),
    }


# ══════════════════════════════════════════════════════════════
# CLAIMANT OFFERS → AI MEDIATES
# ══════════════════════════════════════════════════════════════
@app.post("/api/negotiate")
async def negotiate(inp: ClaimantOfferInput):
    case = get_case(inp.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    cd      = case["case_data"]
    history = cd.get("negotiation_history", [])
    rnd     = len(history) + 1

    if rnd > 3:
        raise HTTPException(400, "Maximum 3 rounds reached.")

    respondent_offer = cd.get("respondent_offers", {}).get(str(rnd))
    if respondent_offer is None:
        raise HTTPException(
            400,
            f"Respondent has not submitted their Round {rnd} offer yet. "
            "Ask them to check their email.",
        )

    print(f"[{inp.case_id}] Negotiation Round {rnd}...")
    result = run_negotiation_round(
        cd.get("case", {}),
        cd.get("legal", {}),
        cd.get("analytics", {}),
        rnd,
        inp.claimant_offer,
        respondent_offer,
        history,
    )

    history.append({
        "round":            rnd,
        "claimant_offer":   inp.claimant_offer,
        "respondent_offer": respondent_offer,
        "ai_proposed":      result.get("ai_proposed_amount"),
        "timestamp":        datetime.now().isoformat(),
    })

    cd["negotiation_history"] = history
    cd["current_round"]       = rnd
    update_case(inp.case_id, "NEGOTIATING", cd)

    _notify_respondent_proposal(
        case, cd.get("case", {}), inp.case_id, rnd, result.get("ai_proposed_amount", 0)
    )

    return {
        "case_id":          inp.case_id,
        "round":            rnd,
        "result":           result,
        "history":          history,
        "rounds_remaining": 3 - rnd,
        "claimant_offer":   inp.claimant_offer,
        "respondent_offer": respondent_offer,
    }


# ══════════════════════════════════════════════════════════════
# ACCEPT / REJECT PROPOSAL
# ══════════════════════════════════════════════════════════════
@app.post("/api/proposal-response")
def proposal_response(inp: ProposalResponseInput):
    case = get_case(inp.case_id)
    if not case:
        raise HTTPException(404, "Case not found")

    cd = case["case_data"]
    cd.setdefault("proposal_responses", {})[f"round_{inp.round_number}_{inp.party}"] = inp.action

    cl_dec = cd["proposal_responses"].get(f"round_{inp.round_number}_claimant")
    re_dec = cd["proposal_responses"].get(f"round_{inp.round_number}_respondent")

    result_status  = "waiting"
    settled_amount = None

    if cl_dec and re_dec:
        if cl_dec == "accept" and re_dec == "accept":
            history        = cd.get("negotiation_history", [])
            settled_amount = next(
                (h["ai_proposed"] for h in reversed(history)
                 if h["round"] == inp.round_number), None
            )
            cd["settled_amount"] = settled_amount
            cd["status"]         = "SETTLED"
            result_status        = "settled"
            update_case(inp.case_id, "SETTLED", cd)
            _finalize_settlement(case, cd, inp.case_id, settled_amount)
        else:
            next_round = inp.round_number + 1
            if next_round <= 3:
                result_status = "next_round"
                update_case(inp.case_id, "NEGOTIATING", cd)
                _send_next_round_invite(case, cd.get("case", {}), inp.case_id, next_round)
            else:
                result_status = "escalate"
                cd["status"]  = "ESCALATED"
                update_case(inp.case_id, "ESCALATED", cd)
                _send_escalation_emails(case, inp.case_id)
    else:
        update_case(inp.case_id, cd.get("status", "NEGOTIATING"), cd)

    return {
        "case_id":             inp.case_id,
        "round":               inp.round_number,
        "party":               inp.party,
        "action":              inp.action,
        "claimant_decision":   cl_dec,
        "respondent_decision": re_dec,
        "result_status":       result_status,
        "settled_amount":      settled_amount,
    }


# ══════════════════════════════════════════════════════════════
# POLL PROPOSAL STATUS
# ══════════════════════════════════════════════════════════════
@app.get("/api/proposal-status/{case_id}/{round_number}")
def proposal_status(case_id: str, round_number: int):
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    cd        = case["case_data"]
    responses = cd.get("proposal_responses", {})
    return {
        "claimant_decision":   responses.get(f"round_{round_number}_claimant"),
        "respondent_decision": responses.get(f"round_{round_number}_respondent"),
        "status":              case["status"],
        "settled_amount":      cd.get("settled_amount"),
    }


# ══════════════════════════════════════════════════════════════
# SETTLE (manual fallback)
# ══════════════════════════════════════════════════════════════
@app.post("/api/settle")
def settle(inp: SettleInput):
    case = get_case(inp.case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    cd = case["case_data"]
    cd["settled_amount"] = inp.settled_amount
    cd["status"]         = "SETTLED"
    update_case(inp.case_id, "SETTLED", cd)
    _finalize_settlement(case, cd, inp.case_id, inp.settled_amount)
    return {"success": True, "settled_amount": inp.settled_amount}


# ══════════════════════════════════════════════════════════════
# DOWNLOADS
# ══════════════════════════════════════════════════════════════
@app.get("/api/download/{case_id}")
def download_demand(case_id: str):
    path = os.path.join(OUTPUTS_DIR, f"demand_letter_{case_id}.pdf")
    if not os.path.exists(path):
        case = get_case(case_id)
        if not case:
            raise HTTPException(404, "Case not found")
        cd = case["case_data"]
        try:
            generate_demand_letter_pdf(
                case_id, cd.get("case", {}), cd.get("legal", {}), cd.get("analytics", {})
            )
        except Exception as e:
            raise HTTPException(500, f"Could not generate demand letter: {e}")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"demand_letter_{case_id}.pdf")


@app.get("/api/download-settlement/{case_id}")
def download_settlement_pdf(case_id: str):
    path = os.path.join(OUTPUTS_DIR, f"settlement_{case_id}.pdf")
    if not os.path.exists(path):
        raise HTTPException(404, "Settlement PDF not found. Case may not be settled yet.")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"settlement_{case_id}.pdf")


@app.get("/api/download-court-file/{case_id}")
def download_court_file(case_id: str):
    path = os.path.join(OUTPUTS_DIR, f"court_file_{case_id}.pdf")
    if not os.path.exists(path):
        case = get_case(case_id)
        if not case:
            raise HTTPException(404, "Case not found")
        cd = case["case_data"]
        try:
            generate_court_file_pdf(
                case_id, cd.get("case", {}), cd.get("legal", {}), cd.get("analytics", {})
            )
        except Exception as e:
            raise HTTPException(500, f"Could not generate court file: {e}")
    return FileResponse(path, media_type="application/pdf",
                        filename=f"court_file_{case_id}.pdf")


@app.get("/api/case/{case_id}")
def get_case_detail(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _sym(case_data: dict) -> str:
    """Currency symbol safe for email HTML (no ReportLab involvement here)."""
    cur = case_data.get("currency", "")
    return {"INR": "Rs.", "USD": "$", "GBP": "GBP ", "EUR": "EUR "}.get(cur, cur + " " if cur else "")


def _finalize_settlement(case: dict, cd: dict, case_id: str, settled_amount: float):
    """
    Called when both parties accept a proposal.
    Uses generate_settlement_pdf() from document_agent — Unicode-safe, dedicated agent.
    """
    case_data  = cd.get("case", {})
    legal_data = cd.get("legal", {})
    is_mon     = case_data.get("is_monetary", True)

    # Generate settlement PDF via the dedicated document agent (Unicode-safe)
    try:
        generate_settlement_pdf(case_id, case_data, legal_data, settled_amount)
    except Exception as e:
        print(f"[WARN] Settlement PDF error for {case_id}: {e}")

    sym        = _sym(case_data)
    amt_display = (
        f"{sym}{int(settled_amount):,}"
        if is_mon
        else case_data.get("non_monetary_demand", "Non-monetary agreement")
    )

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px">
  <div style="background:linear-gradient(135deg,#1B5E20,#2E7D32);padding:32px;border-radius:16px;text-align:center;margin-bottom:16px">
    <div style="font-size:40px;margin-bottom:8px">&#x1F389;</div>
    <h1 style="color:white;margin:0;font-size:22px;font-weight:800">Case Settled!</h1>
    <p style="color:#A5D6A7;margin:8px 0 0">Case #{case_id}</p>
  </div>
  <div style="background:white;border-radius:12px;padding:28px;text-align:center;border:1px solid #e2e8f0;margin-bottom:16px">
    <p style="color:#64748b;font-size:14px;margin:0 0 8px">Agreed Settlement</p>
    <div style="font-size:40px;font-weight:900;color:#2E7D32">{amt_display}</div>
    {"<p style='color:#94a3b8;font-size:12px;margin-top:8px'>Payment due within 7 days.</p>" if is_mon else ""}
  </div>
  <div style="text-align:center">
    <a href="{BASE_URL}/api/download-settlement/{case_id}"
       style="display:inline-block;background:linear-gradient(135deg,#1B5E20,#2E7D32);
              color:white;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:bold">
      Download Agreement
    </a>
  </div>
</div>"""

    send_email(case["claimant_email"],   f"Settlement Confirmed - Case #{case_id}", html)
    send_email(case["respondent_email"], f"Settlement Confirmed - Case #{case_id}", html)


def _notify_respondent_proposal(
    case: dict, case_data: dict, case_id: str, rnd: int, proposed_amount: float
):
    if not case.get("respondent_email"):
        return

    is_mon = case_data.get("is_monetary", True)
    sym    = _sym(case_data)
    amt_display = (
        f"{sym}{int(proposed_amount):,}"
        if is_mon
        else "Non-monetary proposal (see portal)"
    )
    portal = f"{BASE_URL}/respond/{case_id}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px">
  <div style="background:linear-gradient(135deg,#4A148C,#7B1FA2);padding:28px;border-radius:16px;text-align:center;margin-bottom:16px">
    <div style="font-size:36px;margin-bottom:8px">&#x1F916;</div>
    <h1 style="color:white;margin:0;font-size:20px">AI Settlement Proposal</h1>
    <p style="color:#E1BEE7;margin:8px 0 0">Case #{case_id} &middot; Round {rnd}</p>
  </div>
  <div style="background:white;border-radius:12px;padding:28px;text-align:center;border:1px solid #e2e8f0;margin-bottom:16px">
    <p style="color:#64748b;font-size:14px;margin:0 0 8px">The AI Mediator proposes:</p>
    <div style="font-size:40px;font-weight:900;color:#7B1FA2">{amt_display}</div>
    <p style="color:#94a3b8;font-size:12px;margin-top:8px">Please Accept or Reject via your portal.</p>
  </div>
  <div style="text-align:center">
    <a href="{portal}"
       style="display:inline-block;background:linear-gradient(135deg,#4A148C,#7B1FA2);
              color:white;padding:14px 36px;border-radius:10px;text-decoration:none;font-weight:bold">
      View &amp; Decide &rarr;
    </a>
  </div>
</div>"""

    send_email(
        case["respondent_email"],
        f"[Round {rnd}] AI Settlement Proposal - Case #{case_id}",
        html,
    )


def _send_next_round_invite(
    case: dict, case_data: dict, case_id: str, next_round: int
):
    if not case.get("respondent_email"):
        return
    portal = f"{BASE_URL}/respond/{case_id}"

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px">
  <div style="background:linear-gradient(135deg,#0F2A4A,#1565C0);padding:28px;border-radius:16px;text-align:center;margin-bottom:16px">
    <h1 style="color:white;margin:0;font-size:20px">Round {next_round} - Your Turn</h1>
    <p style="color:#93C5FD;margin:8px 0 0">Case #{case_id}</p>
  </div>
  <div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:12px;padding:16px;margin-bottom:20px;text-align:center">
    <p style="color:#92400E;font-size:14px;margin:0">
      Round {next_round - 1} proposal was not accepted.<br/>
      <strong>Submit your updated offer for Round {next_round}.</strong><br/>
      <span style="font-size:12px">Round {next_round} of 3 - final chance to avoid court.</span>
    </p>
  </div>
  <div style="text-align:center">
    <a href="{portal}"
       style="display:inline-block;background:linear-gradient(135deg,#0F2A4A,#1565C0);
              color:white;padding:14px 36px;border-radius:10px;text-decoration:none;font-weight:bold">
      Submit Round {next_round} Offer &rarr;
    </a>
  </div>
</div>"""

    send_email(
        case["respondent_email"],
        f"[Round {next_round}] Submit Updated Offer - Case #{case_id}",
        html,
    )


def _send_escalation_emails(case: dict, case_id: str):
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;padding:16px">
  <div style="background:linear-gradient(135deg,#7F1D1D,#DC2626);padding:28px;border-radius:16px;text-align:center;margin-bottom:16px">
    <div style="font-size:36px;margin-bottom:8px">&#x1F3DB;&#xFE0F;</div>
    <h1 style="color:white;margin:0;font-size:20px">Mediation Unsuccessful</h1>
    <p style="color:#FCA5A5;margin:8px 0 0">Case #{case_id}</p>
  </div>
  <div style="background:white;border-radius:12px;padding:20px;text-align:center;border:1px solid #e2e8f0">
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0">
      After 3 rounds, no agreement was reached.<br/>
      A court-ready case file has been prepared.
    </p>
    <a href="{BASE_URL}/api/download-court-file/{case_id}"
       style="display:inline-block;margin-top:16px;background:#DC2626;color:white;
              padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:bold">
      Download Court File
    </a>
  </div>
</div>"""

    send_email(case["claimant_email"],   f"Mediation Concluded - Case #{case_id}", html)
    send_email(case["respondent_email"], f"Mediation Concluded - Case #{case_id}", html)