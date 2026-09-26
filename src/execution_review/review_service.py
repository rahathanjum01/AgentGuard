from src.audit_security.audit_service import record_audit_event
from src.execution_review.execution_service import execute_tool
from src.execution_review.review import (
    create_review_request,
    get_review_queue,
    get_review_request,
    resolve_review,
)


def create_pending_review(action, doc_hash, guard_result):
    return create_review_request(action, doc_hash, guard_result)


def list_reviews():
    return get_review_queue()


def get_review(review_id):
    return get_review_request(review_id)


def decide_review(review_id, decision, reviewer_id="demo-operator"):
    resolved = resolve_review(review_id, decision, reviewer_id)
    if resolved is not None:
        approved = decision == "APPROVED"
        record_audit_event(
            resolved["doc_hash"],
            {
                "decision": "ALLOW" if approved else "BLOCK",
                "trust": resolved["trust"],
                "latency": 0.0,
                "reason": "Human reviewer approved the request; execution was not started by this API." if approved else "Human reviewer rejected the request.",
                "reason_code": "HUMAN_APPROVAL_RECORDED" if approved else "HUMAN_REJECTION",
                "policy_name": "agentguard-human-review",
                "policy_version": resolved.get("policy_version", "v1"),
            },
            resolved["action"],
            review=resolved,
        )
    return resolved


def decide_and_execute_review(review_id, decision, reviewer_id="demo-operator"):
    """Resolve a review, execute the tool if approved, and record in the audit chain."""
    resolved = resolve_review(review_id, decision, reviewer_id)
    if resolved is None:
        return None, None

    execution = None
    if decision == "APPROVED":
        execution = execute_tool(resolved["action"], resolved["review_id"], {"decision": "ALLOW"})
        record_audit_event(
            resolved["doc_hash"],
            {
                "decision": "ALLOW",
                "trust": resolved["trust"],
                "latency": 0.0,
                "reason": "Approved with human operator override.",
                "reason_code": "HUMAN_OVERRIDE",
                "policy_name": resolved.get("policy_version", "agentguard-hitl"),
                "policy_version": "v1",
            },
            resolved["action"],
            execution=execution.model_dump(),
            review=resolved,
        )
    elif decision == "REJECTED":
        execution = execute_tool(resolved["action"], resolved["review_id"], {"decision": "BLOCK"})
        record_audit_event(
            resolved["doc_hash"],
            {
                "decision": "BLOCK",
                "trust": resolved["trust"],
                "latency": 0.0,
                "reason": "Rejected and blocked by human operator.",
                "reason_code": "HUMAN_REJECTION",
                "policy_name": resolved.get("policy_version", "agentguard-hitl"),
                "policy_version": "v1",
            },
            resolved["action"],
            execution=execution.model_dump(),
            review=resolved,
        )

    return resolved, execution
