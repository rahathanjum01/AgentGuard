import uuid
import time

from src.execution_review.execution_service import execute_tool
from src.execution_review.review_service import create_pending_review
from src.policy.moss_validator import runtime_guard


def guarded_tool_call(action, doc_hash, context_text=None, transaction=None):
    """Evaluate an agent tool request before allowing the tool to execute."""
    request_started = time.perf_counter_ns()
    request_id = f"REQ-{uuid.uuid4().hex[:12].upper()}"
    guard_result = runtime_guard(doc_hash, action, context_text, transaction)
    execution_started = time.perf_counter_ns()
    execution = execute_tool(
        action,
        request_id,
        guard_result,
        doc_hash=doc_hash,
        evidence=guard_result.get("evidence"),
    )
    if guard_result["decision"] == "ALLOW" and not execution.executed:
        guard_result = {
            **guard_result,
            "allow": False,
            "decision": "BLOCK",
            "action": "BLOCKED",
            "reason": execution.result,
            "reason_code": "SANDBOX_EXECUTION_FAILED",
            "color": "red",
        }
    execution_latency_ms = round((time.perf_counter_ns() - execution_started) / 1_000_000, 4)
    review_request = None
    if guard_result["decision"] == "REVIEW":
        review_request = create_pending_review(action, doc_hash, guard_result)
    request_latency_ms = round((time.perf_counter_ns() - request_started) / 1_000_000, 4)
    stage_latency_ms = {
        **guard_result.get("stage_latency_ms", {}),
        "tool_execution_boundary": execution_latency_ms,
        "request_total": request_latency_ms,
    }
    guard_result["stage_latency_ms"] = stage_latency_ms
    guard_result["request_latency_ms"] = request_latency_ms
    return {
        "request_id": request_id,
        "tool": action,
        "executed": execution.executed,
        "execution": execution.model_dump(),
        "decision": guard_result["decision"],
        "reason": guard_result["reason"],
        "review_request": review_request,
        "stage_latency_ms": stage_latency_ms,
        "request_latency_ms": request_latency_ms,
        "guard": guard_result,
    }
