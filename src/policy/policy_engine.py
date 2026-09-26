from src.policy.policy_models import PolicyDecision, PolicyRequest
from src.retrieval.retrieval_models import RetrievalResult


POLICY_NAME = "agentguard-default"
POLICY_VERSION = "agentguard-default-v1"
MINIMUM_TRUST = 0.70
AUTONOMOUS_TRUST = 0.85
PAYMENT_TRUST = 0.90


def _decision(
    request: PolicyRequest,
    decision: str,
    action: str,
    alert: str,
    reason: str,
    reason_code: str,
    color: str,
) -> PolicyDecision:
    return PolicyDecision(
        decision=decision,
        allow=decision == "ALLOW",
        action=action,
        alert=alert,
        reason=reason,
        reason_code=reason_code,
        color=color,
        policy_name=POLICY_NAME,
        policy_version=POLICY_VERSION,
        retrieval=request.context,
    )


def evaluate_policy(action: str, context: RetrievalResult) -> PolicyDecision:
    """Apply the deterministic default policy to normalized retrieval context."""
    request = PolicyRequest(action=action, context=context)

    if not context.found:
        reason_code = "RETRIEVAL_FAILED" if context.retrieval_mode == "MOSS_ERROR" else "CONTEXT_NOT_FOUND"
        reason = (
            "Context retrieval failed, so the request is blocked."
            if reason_code == "RETRIEVAL_FAILED"
            else "No trusted context was found for this request."
        )
        return _decision(
            request,
            "BLOCK",
            "BLOCKED",
            "REAL-TIME GUARDRAIL TRIGGERED",
            reason,
            reason_code,
            "red",
        )

    if context.retrieval_mode not in {"LOCAL_DEMO", "MOSS"}:
        return _decision(
            request,
            "BLOCK",
            "BLOCKED",
            "REAL-TIME GUARDRAIL TRIGGERED",
            "Retrieved context came from an unknown source.",
            "INVALID_RETRIEVAL_MODE",
            "red",
        )

    status = context.status.upper()
    if status == "REVIEW":
        if action == "payment":
            return _decision(
                request,
                "BLOCK",
                "BLOCKED",
                "HIGH-RISK NEEDS VERIFIED CONTEXT",
                "Payment actions cannot proceed on context awaiting human review.",
                "HIGH_RISK_REVIEW_REQUIRED",
                "orange",
            )
        return _decision(
            request,
            "REVIEW",
            "REVIEW",
            "HUMAN REVIEW REQUIRED",
            "Retrieved context is explicitly marked for human review.",
            "REVIEW_REQUIRED",
            "yellow",
        )

    if status not in {"VERIFIED", "TRUSTED", "MATCHED"}:
        return _decision(
            request,
            "BLOCK",
            "BLOCKED",
            "REAL-TIME GUARDRAIL TRIGGERED",
            "Retrieved context's trust or approval status is insufficient.",
            "INVALID_CONTEXT_STATUS",
            "red",
        )

    if context.trust < MINIMUM_TRUST:
        return _decision(
            request,
            "BLOCK",
            "BLOCKED",
            "REAL-TIME GUARDRAIL TRIGGERED",
            "Retrieved context is below the minimum trust threshold.",
            "LOW_TRUST",
            "red",
        )

    if action == "payment" and context.trust < PAYMENT_TRUST:
        return _decision(
            request,
            "BLOCK",
            "BLOCKED",
            "HIGH-RISK NEEDS 0.9+ TRUST",
            "Payment actions require at least 0.90 trust.",
            "HIGH_RISK_THRESHOLD",
            "orange",
        )

    if context.trust < AUTONOMOUS_TRUST:
        return _decision(
            request,
            "REVIEW",
            "REVIEW",
            "HUMAN REVIEW REQUIRED",
            "Context is plausible but not strong enough for autonomous execution.",
            "REVIEW_REQUIRED",
            "yellow",
        )

    return _decision(
        request,
        "ALLOW",
        "ALLOWED",
        "SAFE - TRUSTED CONTEXT",
        "Retrieved context satisfies the action policy.",
        "CONTEXT_ACCEPTED",
        "green",
    )
