import json
from backend.services.openai_service import ask_gpt

def run_analytics_agent(case_data: dict, legal_data: dict) -> dict:
    """
    Takes case + legal research data.
    Returns probability, cost, timeline estimates.
    """

    system_prompt = """You are a legal analytics expert who has analyzed thousands of small claims cases.
You provide realistic probabilistic assessments based on case strength, jurisdiction, and legal standing.

You MUST return ONLY valid JSON with exactly these fields:
{
  "win_probability": number between 0 and 100 (percentage),
  "confidence_level": "HIGH, MEDIUM, or LOW — how confident you are in this estimate",
  "timeline_estimate": {
    "negotiation_days": number,
    "if_court_months_min": number,
    "if_court_months_max": number
  },
  "cost_estimate": {
    "negotiation_cost": number,
    "court_filing_fee": number,
    "legal_representation": number,
    "total_if_court": number,
    "currency": "same as claim currency"
  },
  "is_worth_going_to_court": true or false,
  "reasoning": "2-3 sentences explaining the probability estimate",
  "risk_factors": ["list of 2-3 things that could weaken the case"],
  "strengthening_factors": ["list of 2-3 things that strengthen the case"],
  "recommended_settlement_range": {
    "minimum": number,
    "optimal": number,
    "maximum": number
  }
}

Be realistic — base your numbers on actual small claims court statistics."""

    user_message = f"""Estimate the outcome probabilities for this case:

Dispute Type: {case_data.get('dispute_type')}
Claim Amount: {case_data.get('claim_amount')} {case_data.get('currency')}
Legal Standing: {legal_data.get('legal_standing')}
Applicable Laws Count: {len(legal_data.get('applicable_laws', []))}
Recommended Action: {legal_data.get('recommended_action')}
Key Facts: {json.dumps(case_data.get('key_facts', []))}
Evidence: {json.dumps(case_data.get('evidence_mentioned', []))}
Risk Factors from Law: {json.dumps(legal_data.get('respondent_defenses', []))}"""

    raw = ask_gpt(system_prompt, user_message, json_mode=True)
    return json.loads(raw)