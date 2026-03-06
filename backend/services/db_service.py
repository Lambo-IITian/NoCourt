import sqlite3
import json
import uuid
from datetime import datetime

DB_PATH = "legal_resolver.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id          TEXT PRIMARY KEY,
            status           TEXT DEFAULT 'INTAKE',
            dispute_raw      TEXT,
            case_data        TEXT,
            claimant_email   TEXT,
            respondent_email TEXT,
            created_at       TEXT
        )
    """)
    conn.commit()
    conn.close()

def create_case(dispute_text: str, claimant_email: str = "", respondent_email: str = "") -> str:
    case_id = str(uuid.uuid4())[:8].upper()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO cases VALUES (?,?,?,?,?,?,?)",
        (case_id, 'INTAKE', dispute_text, '{}',
         claimant_email, respondent_email, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return case_id

def update_case(case_id: str, status: str, case_data: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE cases SET status=?, case_data=? WHERE case_id=?",
        (status, json.dumps(case_data), case_id)
    )
    conn.commit()
    conn.close()

def update_emails(case_id: str, claimant_email: str, respondent_email: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE cases SET claimant_email=?, respondent_email=? WHERE case_id=?",
        (claimant_email, respondent_email, case_id)
    )
    conn.commit()
    conn.close()

def get_case(case_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "case_id":          row[0],
        "status":           row[1],
        "dispute_raw":      row[2],
        "case_data":        json.loads(row[3]),
        "claimant_email":   row[4],
        "respondent_email": row[5],
        "created_at":       row[6],
    }