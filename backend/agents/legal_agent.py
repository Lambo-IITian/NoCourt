import json
from backend.services.openai_service import ask_gpt

def run_legal_agent(case_data: dict) -> dict:
    """
    Takes structured case data.
    Returns relevant laws, statutes, and legal standing.
    """

    system_prompt = """You are an expert legal research assistant with knowledge of laws across India, USA, UK, and international jurisdictions.

Given a structured legal case, identify the most relevant laws and legal provisions.

You MUST return ONLY valid JSON with exactly these fields:
{
  "applicable_laws": [
    {
      "law_name": "Name of the law or act",
      "section": "Relevant section number if applicable",
      "jurisdiction": "Country/State this applies to",
      "description": "What this law says in simple terms",
      "relevance": "HIGH, MEDIUM, or LOW",
      "favors": "CLAIMANT, RESPONDENT, or NEUTRAL"
    }
  ],
  "legal_standing": "STRONG, MODERATE, or WEAK — overall assessment of the claimant's position",
  "key_rights": ["list of 3-4 key legal rights the claimant has in this situation"],
  "respondent_defenses": ["possible defenses the respondent could raise"],
  "recommended_action": "NEGOTIATE, SEND_NOTICE, FILE_COMPLAINT, or GO_TO_COURT",
  "legal_summary": "2-3 sentence plain English summary of the legal situation"
}"""

    user_message = f"""Analyze this legal case and find applicable laws:

Dispute Type: {case_data.get('dispute_type')}
Jurisdiction: {case_data.get('jurisdiction')}
Claimant Role: {case_data.get('claimant_role')}
Respondent Role: {case_data.get('respondent_role')}
Claim Amount: {case_data.get('claim_amount')} {case_data.get('currency')}
Key Facts: {json.dumps(case_data.get('key_facts', []))}
Summary: {case_data.get('summary')}"""

    raw = ask_gpt(system_prompt, user_message, json_mode=True)
    return json.loads(raw)