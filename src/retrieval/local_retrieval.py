import time
import sqlite3
import os
import json
from pathlib import Path

DB_PATH = "local_fallback.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trusted_docs (
            doc_hash TEXT PRIMARY KEY,
            name TEXT,
            trust REAL,
            vendor TEXT,
            status TEXT NOT NULL DEFAULT 'VERIFIED',
            evidence TEXT NOT NULL DEFAULT '{}'
        )
    """)
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(trusted_docs)")}
    if "status" not in columns:
        cursor.execute("ALTER TABLE trusted_docs ADD COLUMN status TEXT NOT NULL DEFAULT 'VERIFIED'")
    if "evidence" not in columns:
        cursor.execute("ALTER TABLE trusted_docs ADD COLUMN evidence TEXT NOT NULL DEFAULT '{}'")
    
    # Seed/update the local demo fixture from the same committed corpus used by Moss.
    corpus_path = Path(__file__).resolve().parents[2] / "agentguard-context.json"
    records = json.loads(corpus_path.read_text(encoding="utf-8"))
    demo_docs = [
        (
            record["metadata"]["doc_hash"],
            record["text"],
            float(record["metadata"]["trust"]),
            record["metadata"].get("vendor", "UNKNOWN"),
            record["metadata"].get("status", "UNTRUSTED"),
            json.dumps(record["metadata"], sort_keys=True),
        )
        for record in records
    ]
    cursor.executemany(
        "INSERT INTO trusted_docs (doc_hash, name, trust, vendor, status, evidence) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(doc_hash) DO UPDATE SET name=excluded.name, trust=excluded.trust, "
        "vendor=excluded.vendor, status=excluded.status, evidence=excluded.evidence",
        demo_docs,
    )
    conn.commit()
    conn.close()

# Initialize on module load
init_db()

def _get_doc(doc_hash):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, trust, vendor, status, evidence FROM trusted_docs WHERE doc_hash = ?", (doc_hash,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "name": row[0], "trust": row[1], "vendor": row[2], "status": row[3],
            "evidence": json.loads(row[4]),
        }
    return None

def local_demo_search(doc_hash):
    start = time.perf_counter_ns()
    data = _get_doc(doc_hash)
    latency = round((time.perf_counter_ns() - start) / 1_000_000, 4)
    if data:
        return {
            "found": True,
            "trust": data["trust"],
            "latency": latency,
            "doc": data["name"],
            "status": data["status"],
            "vendor": data["vendor"],
            "retrieval_mode": "LOCAL_DEMO",
            "evidence": data["evidence"],
        }
    return {
        "found": False,
        "trust": 0.12,
        "latency": latency,
        "doc": "UNKNOWN / TAMPERED",
        "status": "UNTRUSTED",
        "vendor": "UNKNOWN",
        "retrieval_mode": "LOCAL_DEMO",
    }


def moss_error_result(latency=0.0):
    return {
        "found": False,
        "trust": 0.0,
        "latency": latency,
        "doc": "MOSS RETRIEVAL FAILED",
        "status": "UNTRUSTED",
        "vendor": "UNKNOWN",
        "retrieval_mode": "MOSS_ERROR",
    }
