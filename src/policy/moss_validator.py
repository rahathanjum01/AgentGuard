from src.audit_security.security_analysis import (
    analyze_request,
    security_block_result,
    validate_retrieved_context,
)
from src.policy.policy_engine import evaluate_policy
import time


def runtime_guard(doc_hash, action, context_text=None, transaction=None):
    from src.retrieval.retrieval_service import retrieve_context

    guard_started = time.perf_counter_ns()
    retrieval_started = time.perf_counter_ns()
    context = retrieve_context(doc_hash)
    retrieval_service_ms = round((time.perf_counter_ns() - retrieval_started) / 1_000_000, 4)
    policy_started = time.perf_counter_ns()
    result = evaluate_policy(action, context).as_legacy_result()
    policy_ms = round((time.perf_counter_ns() - policy_started) / 1_000_000, 4)
    content_started = time.perf_counter_ns()
    findings = analyze_request(context_text, transaction, context.evidence)
    content_ms = round((time.perf_counter_ns() - content_started) / 1_000_000, 4)
    validation_ms = 0.0
    if context.found:
        validation_started = time.perf_counter_ns()
        findings.extend(validate_retrieved_context(action, doc_hash, context.evidence))
        validation_ms = round((time.perf_counter_ns() - validation_started) / 1_000_000, 4)
    if findings:
        if result["decision"] in {"ALLOW", "REVIEW"}:
            result = security_block_result(result, findings)
        else:
            result["security_findings"] = findings
    else:
        result["security_findings"] = []
    total_ms = round((time.perf_counter_ns() - guard_started) / 1_000_000, 4)
    result["stage_latency_ms"] = {
        "retrieval_service": retrieval_service_ms,
        "retrieval_query": context.latency,
        "moss_index_load": context.index_load_latency_ms,
        "policy_evaluation": policy_ms,
        "content_security": content_ms,
        "context_validation": validation_ms,
        "guard_total": total_ms,
    }
    result["guard_latency_ms"] = total_ms
    return result
