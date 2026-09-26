import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = str(Path(__file__).resolve().parents[2] / "audit_ledger.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            block_no INTEGER PRIMARY KEY,
            timestamp TEXT,
            doc_hash TEXT,
            action TEXT,
            decision TEXT,
            reason_code TEXT,
            policy_name TEXT,
            policy_version TEXT,
            trust REAL,
            prev_hash TEXT,
            latency_ms REAL,
            execution_status TEXT,
            review_id TEXT,
            security_trace_id TEXT,
            security_finding_codes TEXT,
            request_id TEXT,
            sandbox_record_id TEXT,
            reviewer_id TEXT,
            stage_latency_ms TEXT,
            block_hash TEXT
        )
    """)
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(blocks)")}
    for name, sql_type in (
        ("request_id", "TEXT"),
        ("sandbox_record_id", "TEXT"),
        ("reviewer_id", "TEXT"),
        ("stage_latency_ms", "TEXT"),
    ):
        if name not in columns:
            cursor.execute(f"ALTER TABLE blocks ADD COLUMN {name} {sql_type}")
    conn.commit()
    conn.close()

init_db()

# Provide a proxy object so existing code using `from ... import LEDGER` doesn't break
# if they just expect to clear it or modify it in tests
class LedgerProxy(list):
    def clear(self):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM blocks")
        conn.commit()
        conn.close()
        
    def __getitem__(self, idx):
        blocks = get_ledger()
        return blocks[idx]

    def __setitem__(self, idx, val):
        # Extremely hacky, but supports the test `LEDGER[0]["trust"] = 0.9`
        blocks = get_ledger()
        block = blocks[idx]
        block.update(val)
        
        # update DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE blocks SET trust = ?, block_hash = ? WHERE block_no = ?",
            (block["trust"], block.get("block_hash"), block["block_no"])
        )
        conn.commit()
        conn.close()

    def __len__(self):
        return len(get_ledger())

    def append(self, val):
        pass # Handled by add_to_ledger
        
    def __iter__(self):
        return iter(get_ledger())

LEDGER = LedgerProxy()


def add_to_ledger(doc_hash, result, action):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("BEGIN IMMEDIATE")
    previous = conn.execute(
        "SELECT block_no, block_hash FROM blocks ORDER BY block_no DESC LIMIT 1"
    ).fetchone()
    prev_hash = previous[1] if previous else ("0" * 64)
    block_no = (previous[0] + 1) if previous else 101
    block = {
        "block_no": block_no,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "doc_hash": doc_hash,
        "action": action,
        "decision": result["decision"],
        "reason_code": result.get("reason_code"),
        "policy_name": result.get("policy_name"),
        "policy_version": result.get("policy_version"),
        "trust": result["trust"],
        "prev_hash": prev_hash,
        "latency_ms": result["latency"],
        "execution_status": result.get("execution_status"),
        "review_id": result.get("review_id"),
        "security_trace_id": result.get("security_trace_id"),
        "security_finding_codes": [item["code"] for item in result.get("security_findings", [])] if result.get("security_findings") else [],
        "request_id": result.get("request_id"),
        "sandbox_record_id": result.get("sandbox_record_id"),
        "reviewer_id": result.get("reviewer_id"),
        "stage_latency_ms": result.get("stage_latency_ms", {}),
    }
    canonical = json.dumps(block, sort_keys=True, separators=(",", ":"))
    block["block_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    conn.execute("""
        INSERT INTO blocks (
            block_no, timestamp, doc_hash, action, decision, reason_code, 
            policy_name, policy_version, trust, prev_hash, latency_ms, 
            execution_status, review_id, security_trace_id, security_finding_codes,
            request_id, sandbox_record_id, reviewer_id, stage_latency_ms, block_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        block["block_no"], block["timestamp"], block["doc_hash"], block["action"],
        block["decision"], block["reason_code"], block["policy_name"], block["policy_version"],
        block["trust"], block["prev_hash"], block["latency_ms"], block["execution_status"],
        block["review_id"], block["security_trace_id"], json.dumps(block["security_finding_codes"]),
        block["request_id"], block["sandbox_record_id"], block["reviewer_id"],
        json.dumps(block["stage_latency_ms"], sort_keys=True),
        block["block_hash"]
    ))
    conn.commit()
    conn.close()
    
    return block


def get_ledger():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blocks ORDER BY block_no ASC")
    rows = cursor.fetchall()
    conn.close()
    
    blocks = []
    for r in rows:
        block = dict(r)
        # Parse JSON array back to list
        if block["security_finding_codes"]:
            block["security_finding_codes"] = json.loads(block["security_finding_codes"])
        else:
            block["security_finding_codes"] = []
        block["stage_latency_ms"] = json.loads(block.get("stage_latency_ms") or "{}")
        blocks.append(block)
    return blocks


def verify_ledger():
    blocks = get_ledger()
    legacy_chain = bool(blocks and len(blocks[0].get("block_hash", "")) == 16)
    previous_hash = "0" * (16 if legacy_chain else 64)
    for block in blocks:
        if block.get("prev_hash") != previous_hash:
            return False
        if len(block.get("block_hash", "")) == 16:
            legacy_keys = {
                "block_no", "timestamp", "doc_hash", "action", "decision", "reason_code",
                "policy_name", "policy_version", "trust", "prev_hash", "latency_ms",
                "execution_status", "review_id", "security_trace_id", "security_finding_codes",
            }
            payload = {key: block[key] for key in legacy_keys}
        else:
            payload = {key: value for key, value in block.items() if key != "block_hash"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256(canonical.encode()).hexdigest()
        if block.get("block_hash") != (expected_hash[:16] if len(block.get("block_hash", "")) == 16 else expected_hash):
            return False
        previous_hash = block["block_hash"]
    return True
