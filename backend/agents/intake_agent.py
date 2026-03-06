import json
from backend.services.openai_service import ask_gpt

def run_intake_agent(dispute_text: str) -> dict:
    """
    Takes raw dispute text from user.
    Returns a structured case object as a Python dict.
    """

    system_prompt = """You are a legal case intake specialist. 
Your job is to read a person's dispute description and extract structured information from it.

You MUST return ONLY valid JSON with exactly these fields:
{
  "dispute_type": one of ["rental_deposit", "unpaid_salary", "consumer_fraud", "contract_breach", "other"],
  "claimant_name": "name if mentioned, else 'Claimant'",
  "respondent_name": "name if mentioned, else 'Respondent'",
  "claimant_role": "e.g. tenant, employee, buyer, contractor",
  "respondent_role": "e.g. landlord, employer, seller, client",
  "claim_amount": number or null if not mentioned,
  "currency": "USD, INR, GBP, etc based on context",
  "incident_date": "date if mentioned, else null",
  "jurisdiction": "country or state/city if mentioned, else 'General'",
  "key_facts": ["list", "of", "3-5", "key", "facts", "from", "the", "dispute"],
  "evidence_mentioned": ["any evidence the user mentioned, or empty list"],
  "summary": "One clear sentence summarizing the dispute"
}

Be smart — infer jurisdiction from currency, names, or context clues."""

    user_message = f"Extract structured case information from this dispute:\n\n{dispute_text}"

    raw = ask_gpt(system_prompt, user_message, json_mode=True)
    return json.loads(raw)