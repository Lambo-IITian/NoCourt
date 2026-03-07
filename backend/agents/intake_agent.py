import json
from backend.services.openai_service import ask_gpt


def run_intake_agent(dispute_text: str) -> dict:
    """
    Takes raw dispute text. Returns structured case object.
    Handles ALL dispute types — monetary and non-monetary.
    """

    system_prompt = """You are a legal case intake specialist.
Read the person's dispute and extract structured information.

You MUST return ONLY valid JSON with exactly these fields:
{
  "dispute_type": one of [
    "rental_deposit", "unpaid_salary", "consumer_fraud", "contract_breach",
    "physical_assault", "harassment", "defamation", "property_damage",
    "neighbor_dispute", "domestic_matter", "apology_demand", "other"
  ],
  "is_monetary": true or false — is money the primary demand?,
  "claimant_name": "name if mentioned, else 'Claimant'",
  "respondent_name": "name if mentioned, else 'Respondent'",
  "claimant_role": "e.g. tenant, employee, buyer, victim, neighbor",
  "respondent_role": "e.g. landlord, employer, seller, accused, neighbor",
  "claim_amount": number or null if not monetary,
  "non_monetary_demand": "what the claimant wants if not money — e.g. 'public apology', 'stop harassment', 'return of property'",
  "currency": "USD, INR, GBP, etc — or null if non-monetary",
  "incident_date": "date if mentioned, else null",
  "jurisdiction": "country or city if mentioned, else 'General'",
  "severity": "LOW, MEDIUM, HIGH, CRIMINAL — how serious is this?",
  "key_facts": ["3-5 key facts from the dispute"],
  "evidence_mentioned": ["any evidence the user mentioned, or empty list"],
  "summary": "One clear sentence summarizing the dispute and what the claimant wants"
}

For non-monetary cases: claim_amount = null, fill non_monetary_demand clearly.
For criminal-level cases (assault, threats): set severity = CRIMINAL and note it."""

    user_message = f"Extract structured case information:\n\n{dispute_text}"
    raw = ask_gpt(system_prompt, user_message, json_mode=True)
    return json.loads(raw)