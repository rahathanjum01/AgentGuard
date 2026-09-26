"""SQLite-backed human review queue for durable demo decisions."""

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


REVIEW_DB_PATH = Path(__file__).resolve().parents[2] / "review_queue.db"


@contextmanager
def _connect():
    conn = sqlite3.connect(REVIEW_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS review_requests (
            review_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
    """)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load_request(row):
    return json.loads(row["payload"]) if row else None


class ReviewQueueProxy:
    """Small list-like compatibility layer backed by the durable queue."""

    def clear(self):
        with _connect() as conn:
            conn.execute("DELETE FROM review_requests")

    def __len__(self):
        with _connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM review_requests").fetchone()[0]

    def __iter__(self):
        return iter(get_review_queue())

    def __getitem__(self, index):
        return get_review_queue()[index]

    def append(self, request):
        with _connect() as conn:
            conn.execute(
                "INSERT INTO review_requests VALUES (?, ?, ?, ?)",
                (request["review_id"], request["status"], request["created_at"], json.dumps(request)),
            )


REVIEW_QUEUE = ReviewQueueProxy()


def create_review_request(action, doc_hash, guard_result):
    review_id = f"REVIEW-{int(time.time_ns())}-{doc_hash[:8]}"
    request = {
        "review_id": review_id,
        "action": action,
        "doc_hash": doc_hash,
        "decision": guard_result["decision"],
        "reason": guard_result["reason"],
        "reason_code": guard_result.get("reason_code"),
        "policy_version": guard_result.get("policy_version"),
        "trust": guard_result["trust"],
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "vendor": guard_result.get("vendor", "UNKNOWN"),
        "doc": guard_result.get("doc", "Context verification required"),
        "stage_latency_ms": guard_result.get("stage_latency_ms", {}),
    }
    REVIEW_QUEUE.append(request)
    return request


def get_review_queue():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM review_requests ORDER BY created_at ASC"
        ).fetchall()
    return [_load_request(row) for row in rows]


def get_review_request(review_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM review_requests WHERE review_id = ?", (review_id,)
        ).fetchone()
    return _load_request(row)


def resolve_review(review_id, status, reviewer_id="demo-operator"):
    if status not in {"APPROVED", "REJECTED"}:
        return None
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT payload FROM review_requests WHERE review_id = ? AND status = 'PENDING'",
            (review_id,),
        ).fetchone()
        if row is None:
            return None
        request = _load_request(row)
        request["status"] = status
        request["reviewed_at"] = datetime.now(timezone.utc).isoformat()
        request["reviewer_id"] = reviewer_id
        conn.execute(
            "UPDATE review_requests SET status = ?, payload = ? WHERE review_id = ?",
            (status, json.dumps(request), review_id),
        )
        return request
