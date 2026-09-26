from src.execution_review.execution_models import ExecutionResult
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


SANDBOX_DB_PATH = Path(__file__).resolve().parents[2] / "sandbox_payments.db"


def _record_sandbox_payment(request_id, doc_hash, approval):
    invoice_id = str(approval.get("invoice_id", "")).strip()
    if not invoice_id:
        return None, "Verified approval evidence is missing an invoice ID."
    conn = sqlite3.connect(SANDBOX_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sandbox_payments (
                payment_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                invoice_id TEXT NOT NULL UNIQUE,
                purchase_order TEXT,
                vendor TEXT NOT NULL,
                amount TEXT NOT NULL,
                created_at TEXT NOT NULL,
                environment TEXT NOT NULL CHECK(environment = 'SANDBOX')
            )
        """)
        existing = conn.execute(
            "SELECT payment_id FROM sandbox_payments WHERE invoice_id = ?", (invoice_id,)
        ).fetchone()
        if existing:
            return existing[0], "Sandbox payment already exists; no second record was created."
        payment_id = f"SANDBOX-PAY-{uuid.uuid4().hex[:10].upper()}"
        conn.execute(
            "INSERT INTO sandbox_payments VALUES (?, ?, ?, ?, ?, ?, ?, 'SANDBOX')",
            (
                payment_id,
                request_id,
                invoice_id,
                approval.get("purchase_order"),
                str(approval.get("vendor", "UNKNOWN")),
                str(approval.get("approved_amount", "")),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return payment_id, "Sandbox payment record created. No real payment was sent."
    finally:
        conn.close()


def get_sandbox_payments(limit=50):
    conn = sqlite3.connect(SANDBOX_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sandbox_payments (
                payment_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                invoice_id TEXT NOT NULL UNIQUE,
                purchase_order TEXT,
                vendor TEXT NOT NULL,
                amount TEXT NOT NULL,
                created_at TEXT NOT NULL,
                environment TEXT NOT NULL CHECK(environment = 'SANDBOX')
            )
        """)
        return [dict(row) for row in conn.execute(
            "SELECT * FROM sandbox_payments ORDER BY created_at DESC LIMIT ?", (limit,)
        )]
    finally:
        conn.close()


def execute_tool(action, request_id, policy_decision, doc_hash=None, evidence=None):
    """Execute the prototype tool boundary only after an ALLOW decision."""
    decision = policy_decision["decision"]
    if decision != "ALLOW":
        return ExecutionResult(
            request_id=request_id,
            action=action,
            decision=decision,
            executed=False,
            status="PREVENTED",
            result=f"Tool execution prevented by {decision} policy decision.",
        )

    sandbox_record_id = None
    result = f"Prototype execution completed for {action}."
    if action == "payment":
        approval = ((evidence or {}).get("verified_approval") or {})
        if not approval:
            return ExecutionResult(
                request_id=request_id,
                action=action,
                decision="BLOCK",
                executed=False,
                status="PREVENTED",
                result="Sandbox payment requires verified approval evidence.",
            )
        try:
            sandbox_record_id, result = _record_sandbox_payment(request_id, doc_hash, approval)
        except sqlite3.Error:
            return ExecutionResult(
                request_id=request_id,
                action=action,
                decision="BLOCK",
                executed=False,
                status="FAILED",
                result="Sandbox payment storage failed; no payment was sent.",
            )
        if sandbox_record_id is None:
            return ExecutionResult(
                request_id=request_id,
                action=action,
                decision="BLOCK",
                executed=False,
                status="FAILED",
                result=result,
            )

    return ExecutionResult(
        request_id=request_id,
        action=action,
        decision="ALLOW",
        executed=True,
        status="EXECUTED",
        result=result,
        sandbox_record_id=sandbox_record_id,
    )
