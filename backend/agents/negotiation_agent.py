import json
from backend.services.openai_service import ask_gpt

def run_negotiation_round(
    case_data: dict,
    legal_data: dict,
    analytics_data: dict,
    round_number: int,
    claimant_offer: float,
    respondent_offer: float,
    history: list
) -> dict:
    """
    Given both parties' current offers, AI mediator proposes a fair settlement.
    Returns negotiation analysis and AI recommendation for this round.
    """

    system_prompt = """You are an expert AI legal mediator with 20 years of experience in alternative dispute resolution.
Your job is to analyze both parties' positions and guide them toward a fair settlement.

You MUST return ONLY valid JSON with exactly these fields:
{
  "round_assessment": "Brief assessment of where both parties stand",
  "claimant_position": "STRONG, FAIR, or WEAK — assessment of claimant's offer",
  "respondent_position": "STRONG, FAIR, or WEAK — assessment of respondent's offer",
  "ai_proposed_amount": number — the fair settlement amount you recommend,
  "proposal_reasoning": "2-3 sentences explaining why this amount is fair",
  "gap_analysis": "How far apart the parties are and what it means",
  "pressure_on_claimant": "One sentence telling the claimant why they should consider settling",
  "pressure_on_respondent": "One sentence telling the respondent why they should consider settling",
  "likely_to_settle": true or false,
  "next_step": "CONTINUE_NEGOTIATION, RECOMMEND_SETTLEMENT, or ESCALATE_TO_COURT",
  "mediator_message": "A professional, neutral 2-3 sentence message from the AI mediator to both parties"
}"""

    history_text = ""
    if history:
        history_text = "\nNegotiation History:\n"
        for h in history:
            history_text += f"Round {h['round']}: Claimant offered {h['claimant_offer']}, Respondent offered {h['respondent_offer']}, AI proposed {h['ai_proposed']}\n"

    user_message = f"""Mediate this negotiation round:

Case Type: {case_data.get('dispute_type')}
Original Claim: {case_data.get('claim_amount')} {case_data.get('currency')}
Legal Standing: {legal_data.get('legal_standing')}
Win Probability: {analytics_data.get('win_probability')}%
Recommended Settlement Range: {json.dumps(analytics_data.get('recommended_settlement_range', {}))}

Current Round: {round_number} of 3
Claimant's Offer (what they'll accept): {claimant_offer} {case_data.get('currency')}
Respondent's Offer (what they'll pay): {respondent_offer} {case_data.get('currency')}
{history_text}

Propose a fair resolution."""

    raw = ask_gpt(system_prompt, user_message, json_mode=True)
    return json.loads(raw)


def generate_settlement_agreement(case_data: dict, legal_data: dict, settled_amount: float) -> str:
    """Generates the text of a settlement agreement once both parties agree."""

    system_prompt = """You are a legal document specialist. Write a formal settlement agreement.
It must be professional, legally worded, and clearly state the terms.
Write it as a proper legal document with numbered clauses.
Do not use placeholders — use the actual names and amounts provided."""

    user_message = f"""Write a formal settlement agreement for:

Case Type: {case_data.get('dispute_type')}
Claimant: {case_data.get('claimant_name')}
Respondent: {case_data.get('respondent_name')}
Original Claim: {case_data.get('claim_amount')} {case_data.get('currency')}
Settled Amount: {settled_amount} {case_data.get('currency')}
Key Facts: {json.dumps(case_data.get('key_facts', []))}
Applicable Law: {legal_data.get('applicable_laws', [{}])[0].get('law_name', '') if legal_data.get('applicable_laws') else ''}

Include: payment terms (within 7 days), confidentiality clause, full and final settlement clause, 
and a clause that this resolves all claims between the parties."""

    return ask_gpt(system_prompt, user_message, json_mode=False)