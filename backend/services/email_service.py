import os
from azure.communication.email import EmailClient
from dotenv import load_dotenv

load_dotenv()

def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """
    Sends an email via Azure Communication Services.
    Returns True if sent successfully.
    """
    try:
        client = EmailClient.from_connection_string(
            os.getenv("AZURE_COMM_CONNECTION_STRING")
        )
        message = {
            "senderAddress": os.getenv("AZURE_SENDER_EMAIL"),
            "recipients": {
                "to": [{"address": to_email}]
            },
            "content": {
                "subject": subject,
                "html": html_body,
            }
        }
        poller = client.begin_send(message)
        result = poller.result()
        print(f"Email sent to {to_email} | Status: {result['status']}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def send_respondent_invite(
    respondent_email: str,
    respondent_name: str,
    claimant_name: str,
    case_id: str,
    dispute_summary: str,
    claim_amount: str,
    base_url: str = "http://localhost:8000"
):
    """Sends the respondent their unique link to join the case."""
    portal_link = f"{base_url}/respond/{case_id}"

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f8fafc;padding:20px">
      <div style="background:linear-gradient(135deg,#0F2A4A,#1565C0);padding:30px;border-radius:12px;text-align:center;margin-bottom:20px">
        <h1 style="color:white;margin:0;font-size:24px">⚖️ LegalAI Resolver</h1>
        <p style="color:#93C5FD;margin:8px 0 0">You have been invited to resolve a legal dispute</p>
      </div>

      <div style="background:white;padding:24px;border-radius:12px;margin-bottom:16px;border-left:4px solid #1565C0">
        <p style="margin:0 0 8px;color:#64748b;font-size:14px">Dear <b style="color:#1e293b">{respondent_name}</b>,</p>
        <p style="color:#374151;font-size:14px;line-height:1.6">
          <b>{claimant_name}</b> has filed a legal dispute against you through our AI-powered 
          pre-litigation resolution system. Before this matter escalates to court, you have the 
          opportunity to resolve it through AI-guided negotiation.
        </p>
      </div>

      <div style="background:#FEF3C7;border:1px solid #F59E0B;padding:16px;border-radius:12px;margin-bottom:16px">
        <p style="margin:0 0 6px;font-weight:bold;color:#92400E;font-size:13px">📋 DISPUTE DETAILS</p>
        <p style="margin:4px 0;color:#78350F;font-size:13px"><b>Case ID:</b> {case_id}</p>
        <p style="margin:4px 0;color:#78350F;font-size:13px"><b>Filed by:</b> {claimant_name}</p>
        <p style="margin:4px 0;color:#78350F;font-size:13px"><b>Amount Claimed:</b> {claim_amount}</p>
        <p style="margin:4px 0;color:#78350F;font-size:13px"><b>Summary:</b> {dispute_summary}</p>
      </div>

      <div style="background:#EFF6FF;border:1px solid #BFDBFE;padding:16px;border-radius:12px;margin-bottom:20px">
        <p style="margin:0 0 6px;font-weight:bold;color:#1E40AF;font-size:13px">✅ YOUR OPTIONS</p>
        <p style="margin:4px 0;color:#1E40AF;font-size:13px">1. <b>Respond & Negotiate</b> — Submit your counter-offer through our AI mediation portal</p>
        <p style="margin:4px 0;color:#1E40AF;font-size:13px">2. <b>Reach Settlement</b> — Avoid court costs and lengthy legal proceedings</p>
        <p style="margin:4px 0;color:#1E40AF;font-size:13px">3. <b>Ignore</b> — The claimant may escalate this to a formal court filing</p>
      </div>

      <div style="text-align:center;margin-bottom:20px">
        <a href="{portal_link}"
           style="background:linear-gradient(135deg,#0F2A4A,#1565C0);color:white;padding:14px 32px;
                  border-radius:10px;text-decoration:none;font-weight:bold;font-size:15px;display:inline-block">
          View Case & Respond →
        </a>
        <p style="color:#94a3b8;font-size:11px;margin-top:8px">This link is unique to your case: {case_id}</p>
      </div>

      <div style="border-top:1px solid #e2e8f0;padding-top:16px">
        <p style="color:#94a3b8;font-size:11px;text-align:center;margin:0">
          ⚖️ LegalAI Resolver — AI-Powered Pre-Litigation System<br>
          This is an automated notice. Responding within 7 days is recommended.
        </p>
      </div>
    </div>
    """
    return send_email(
        respondent_email,
        f"[Action Required] Legal Dispute Filed Against You — Case #{case_id}",
        html
    )


def send_settlement_email(
    email: str,
    name: str,
    case_id: str,
    settled_amount: str,
    download_url: str
):
    """Sends settlement confirmation with download link to both parties."""
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f8fafc;padding:20px">
      <div style="background:linear-gradient(135deg,#1B5E20,#2E7D32);padding:30px;border-radius:12px;text-align:center;margin-bottom:20px">
        <div style="font-size:48px;margin-bottom:8px">🎉</div>
        <h1 style="color:white;margin:0;font-size:24px">Case Successfully Settled!</h1>
        <p style="color:#A7F3D0;margin:8px 0 0">Case #{case_id}</p>
      </div>

      <div style="background:white;padding:24px;border-radius:12px;margin-bottom:16px">
        <p style="color:#374151;font-size:14px">Dear <b>{name}</b>,</p>
        <p style="color:#374151;font-size:14px;line-height:1.6">
          Great news — your dispute has been successfully resolved through AI-guided negotiation.
          Both parties have agreed to a settlement.
        </p>
        <div style="background:#D1FAE5;border:1px solid #6EE7B7;padding:16px;border-radius:10px;text-align:center;margin:16px 0">
          <p style="margin:0;color:#065F46;font-size:13px;font-weight:bold">SETTLED AMOUNT</p>
          <p style="margin:4px 0 0;color:#064E3B;font-size:28px;font-weight:900">{settled_amount}</p>
        </div>
        <p style="color:#374151;font-size:14px">Your signed settlement agreement is ready for download:</p>
        <div style="text-align:center;margin-top:16px">
          <a href="{download_url}"
             style="background:linear-gradient(135deg,#1B5E20,#2E7D32);color:white;padding:12px 28px;
                    border-radius:10px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block">
            📄 Download Settlement Agreement
          </a>
        </div>
      </div>

      <p style="color:#94a3b8;font-size:11px;text-align:center">
        ⚖️ LegalAI Resolver | This settlement was facilitated by AI mediation.
      </p>
    </div>
    """
    return send_email(email, f"✅ Settlement Confirmed — Case #{case_id}", html)