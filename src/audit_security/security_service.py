import uuid

SUSPICIOUS_MARKERS = ("hacker", "tamper", "stale", "fake")


def security_trace(doc_hash, is_blocked, security_findings=None):
    findings = security_findings or []
    suspicious = any(marker in doc_hash.lower() for marker in SUSPICIOUS_MARKERS) or bool(findings)
    if not is_blocked or not suspicious:
        return {"activated": False}

    trace_id = uuid.uuid4().hex[:12].upper()
    return {
        "activated": True,
        "trace_id": f"TRACE-{trace_id}",
        "trigger": findings[0]["code"] if findings else "SUSPICIOUS_BLOCKED_REQUEST",
        "telemetry_mode": "DEMO",
        "decoy_available": True,
        "message": f"Suspicious request trace {trace_id} recorded.",
    }
