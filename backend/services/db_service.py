import sqlite3
import json
from datetime import datetime

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "..", "legal_resolver.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    # Cases table
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
    # User sessions table — simple email-based history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_id   TEXT PRIMARY KEY,
            email        TEXT NOT NULL,
            created_at   TEXT,
            last_seen    TEXT
        )
    """)
    conn.commit()
    conn.close()


def create_case(
    case_id: str,
    claimant_email: str,
    respondent_email: str,
    case_data: dict,
) -> str:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?)",
        (
            case_id,
            "ANALYZED",
            "",
            json.dumps(case_data),
            claimant_email,
            respondent_email,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return case_id


def update_case(case_id: str, status: str, case_data: dict):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE cases SET status=?, case_data=? WHERE case_id=?",
        (status, json.dumps(case_data), case_id),
    )
    conn.commit()
    conn.close()


def get_case(case_id: str) -> dict | None:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT * FROM cases WHERE case_id=?", (case_id,)
    ).fetchone()
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


def get_cases_by_email(email: str) -> list:
    """Returns all cases where this email is claimant or respondent."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT * FROM cases WHERE claimant_email=? OR respondent_email=? ORDER BY created_at DESC",
        (email, email),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        cd = json.loads(row[3])
        c  = cd.get("case", {})
        result.append({
            "case_id":      row[0],
            "status":       row[1],
            "created_at":   row[6],
            "dispute_type": c.get("dispute_type"),
            "summary":      c.get("summary"),
            "claim_amount": c.get("claim_amount"),
            "currency":     c.get("currency"),
            "is_monetary":  c.get("is_monetary", True),
            "role":         "claimant" if row[4] == email else "respondent",
        })
    return result