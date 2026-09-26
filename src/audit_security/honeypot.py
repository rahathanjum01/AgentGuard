"""Safe, read-only honeypot demo and suspicious-activity trace writer."""

import json
from pathlib import Path

from src.audit_security.otel_formatter import to_otel_format
from src.audit_security.security_service import security_trace


DECOY_RECORD = {
    "invoice_id": "DECOY-INV-0042",
    "vendor": "Example Decoy Trading Ltd.",
    "amount": "7250.00",
    "currency": "USD",
    "status": "PENDING REVIEW",
    "purchase_order": "DECOY-PO-0042",
    "bank_account_last4": "0000",
    "notice": "Fabricated read-only demo data. No payment or external action is available.",
}


def _append_security_event(event):
    otel_data = to_otel_format(event)
    log_path = Path(__file__).resolve().parents[2] / "honeypot_events.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(otel_data) + "\n")
    except OSError:
        return False
    return True


def honeypot_trap(doc_hash, is_blocked, security_findings=None):
    result = security_trace(doc_hash, is_blocked, security_findings)
    if not result.get("activated"):
        return result
    finding_codes = [item.get("code", "UNKNOWN") for item in (security_findings or [])]
    event = {
        "event_type": "suspicious_request_blocked",
        "attack_type": finding_codes[0] if finding_codes else result.get("trigger", "UNKNOWN"),
        "severity": "high",
        "trace_id": result["trace_id"],
        "payload": f"Suspicious document reference {doc_hash}"[:500],
        "is_blocked": True,
    }
    result["telemetry_recorded"] = _append_security_event(event)
    return result


def read_decoy_record(trace_id, requested_action="read"):
    """Return the fixed fabricated decoy and record the read-only interaction."""
    if not trace_id or not str(trace_id).startswith("TRACE-"):
        raise ValueError("A valid honeypot trace ID is required.")
    log_path = Path(__file__).resolve().parents[2] / "honeypot_events.jsonl"
    try:
        with open(log_path, encoding="utf-8") as trace_file:
            trace_exists = False
            for line in trace_file:
                if not line.strip():
                    continue
                try:
                    stored_event = json.loads(line).get("_original_legacy_event", {})
                except json.JSONDecodeError:
                    continue
                if stored_event.get("trace_id") == trace_id:
                    trace_exists = True
                    break
    except FileNotFoundError:
        trace_exists = False
    if not trace_exists:
        raise ValueError("No active suspicious-request trace matches that ID.")
    event = {
        "event_type": "decoy_record_viewed",
        "attack_type": "HONEYPOT_DECOY_ACCESS",
        "severity": "medium",
        "trace_id": str(trace_id),
        "requested_action": str(requested_action)[:80],
        "payload": f"Read-only decoy access: {trace_id}",
        "is_blocked": True,
    }
    if not _append_security_event(event):
        raise RuntimeError("Could not record decoy access telemetry.")
    return {**DECOY_RECORD, "trace_id": str(trace_id), "read_only": True}
