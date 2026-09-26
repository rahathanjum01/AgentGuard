from src.audit_security.blockchain import add_to_ledger, get_ledger, verify_ledger


def record_audit_event(doc_hash, guard_result, action, execution=None, review=None, security_trace=None):
    result = {
        **guard_result,
        "execution_status": execution.get("status") if execution else "NOT_RUN",
        "review_id": review.get("review_id") if review else None,
        "security_trace_id": security_trace.get("trace_id") if security_trace else None,
        "request_id": execution.get("request_id") if execution else None,
        "sandbox_record_id": execution.get("sandbox_record_id") if execution else None,
        "reviewer_id": review.get("reviewer_id") if review else None,
        "stage_latency_ms": guard_result.get("stage_latency_ms", {}),
    }
    return add_to_ledger(doc_hash, result, action)


def get_audit_events():
    return get_ledger()


def verify_audit_chain():
    return verify_ledger()
