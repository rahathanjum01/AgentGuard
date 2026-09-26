"""Persist human labels for later evaluation review; labels never change policy."""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing


FEEDBACK_DB_PATH = Path(__file__).resolve().parents[2] / "decision_feedback.db"


def record_decision_feedback(block_no, label, reviewer_id, reason=""):
    if label not in {"CORRECT", "INCORRECT"}:
        raise ValueError("Feedback label must be CORRECT or INCORRECT.")
    feedback = {
        "feedback_id": f"FB-{uuid.uuid4().hex[:12].upper()}",
        "block_no": int(block_no),
        "label": label,
        "reviewer_id": str(reviewer_id)[:120],
        "reason": str(reason)[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with closing(sqlite3.connect(FEEDBACK_DB_PATH)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    block_no INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO decision_feedback VALUES (?, ?, ?, ?, ?, ?)",
                tuple(feedback[key] for key in ("feedback_id", "block_no", "label", "reviewer_id", "reason", "created_at")),
            )
    return feedback


def get_decision_feedback(limit=200):
    with closing(sqlite3.connect(FEEDBACK_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM decision_feedback ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [dict(row) for row in rows]
