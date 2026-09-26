# src/observability/otel_formatter.py
# ADDITIVE: Converts honeypot dict to OpenTelemetry JSON without touching old logger

import uuid
import time
import re
from datetime import datetime, timezone

def to_otel_format(honeypot_event: dict) -> dict:
    """
    Takes your EXISTING honeypot dict and returns OTel-compatible dict
    Does NOT modify the original event
    """
    trace_ref = str(honeypot_event.get("trace_id", "")).removeprefix("TRACE-")
    trace_id = (
        trace_ref.zfill(32)
        if re.fullmatch(r"[0-9a-fA-F]{1,32}", trace_ref)
        else format(uuid.uuid4().int & ((1 << 128) - 1), "032x")
    )
    span_id = format(uuid.uuid4().int & ((1 << 64)-1), '016x')
    
    return {
        "traceId": trace_id,
        "spanId": span_id,
        "traceState": "",
        "name": "honeypot.attack_detected",
        "kind": "SPAN_KIND_SERVER",
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1e9),
        "duration": 0,
        "attributes": {
            "service.name": "agentguard-honeypot",
            "honeypot.attack_type": honeypot_event.get("attack_type", "unknown"),
            "honeypot.source_ip": honeypot_event.get("ip", "0.0.0.0"),
            "honeypot.severity": honeypot_event.get("severity", "high"),
            "honeypot.payload": str(honeypot_event.get("payload", ""))[:500],
            "honeypot.session_id": honeypot_event.get("session_id", str(uuid.uuid4())),
            "honeypot.trace_id": honeypot_event.get("trace_id", ""),
            "security.event.type": honeypot_event.get("event_type", "honeypot_trigger"),
            "http.client_ip": honeypot_event.get("ip", ""),
        },
        "events": [
            {
                "name": "security_violation",
                "timestamp": int(time.time_ns()),
                "attributes": honeypot_event
            }
        ],
        "status": {
            "code": "ERROR" if honeypot_event.get("severity") == "critical" else "OK"
        },
        # Keep original for backward compat reference
        "_original_legacy_event": honeypot_event
    }
