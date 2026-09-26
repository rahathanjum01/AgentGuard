import hmac
import os

from fastapi import FastAPI, Header, HTTPException

from src.agent import guarded_tool_call
from src.api_models import (
    DecisionFeedbackRequest,
    GuardResponse,
    HealthResponse,
    ReviewDecisionRequest,
    ToolRequest,
)
from src.audit_security.feedback import get_decision_feedback, record_decision_feedback
from src.audit_service import get_audit_events, record_audit_event, verify_audit_chain
from src.honeypot import honeypot_trap
from src.honeypot import read_decoy_record
from src.retrieval_models import RetrievalResult
from src.review_service import decide_review, get_review, list_reviews


app = FastAPI(
    title="AgentGuard Gateway",
    description="Runtime safety gateway for transaction-oriented AI agents.",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {
        "status": "ok",
        "service": "agentguard-gateway",
        "version": app.version,
    }


@app.post("/v1/guard/tool-request", response_model=GuardResponse)
def guard_tool_request(request: ToolRequest):
    agent_request = guarded_tool_call(
        request.action, request.doc_hash, request.context_text, request.transaction
    )
    guard_result = agent_request["guard"]
    retrieval = RetrievalResult.model_validate(
        {
            field: guard_result[field]
            for field in RetrievalResult.model_fields
        }
    )
    honeypot = honeypot_trap(
        request.doc_hash, not guard_result["allow"], guard_result.get("security_findings")
    )
    audit = record_audit_event(
        request.doc_hash,
        guard_result,
        request.action,
        execution=agent_request["execution"],
        review=agent_request["review_request"],
        security_trace=honeypot,
    )

    return {
        "request_id": agent_request["request_id"],
        "decision": agent_request["decision"],
        "executed": agent_request["executed"],
        "policy_name": guard_result["policy_name"],
        "policy_version": guard_result["policy_version"],
        "reason_code": guard_result["reason_code"],
        "reason": agent_request["reason"],
        "execution": agent_request["execution"],
        "guard": guard_result,
        "retrieval": retrieval,
        "review_request": agent_request["review_request"],
        "honeypot": honeypot,
        "audit": audit,
    }


@app.get("/v1/reviews")
def reviews():
    return {"reviews": list_reviews()}


@app.get("/v1/honeypot/decoys/{trace_id}")
def honeypot_decoy(trace_id: str):
    try:
        return {"decoy": read_decoy_record(trace_id, "api_read")}
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/v1/reviews/{review_id}")
def review(review_id: str):
    review_request = get_review(review_id)
    if review_request is None:
        return {"review": None}
    return {"review": review_request}


@app.post("/v1/reviews/{review_id}/decision")
def review_decision(
    review_id: str,
    request: ReviewDecisionRequest,
    authorization: str | None = Header(default=None),
):
    _require_reviewer_auth(authorization)
    review_request = decide_review(review_id, request.decision, request.reviewer_id)
    if review_request is None:
        return {"review": None, "updated": False}
    return {
        "review": review_request,
        "updated": True,
        "execution_started": False,
    }


def _require_reviewer_auth(authorization):
    expected_token = os.getenv("AGENTGUARD_REVIEW_TOKEN")
    if expected_token:
        supplied_token = authorization.removeprefix("Bearer ") if authorization else ""
        if not hmac.compare_digest(supplied_token, expected_token):
            raise HTTPException(status_code=401, detail="Reviewer authentication required.")


@app.get("/v1/feedback")
def decision_feedback():
    return {"feedback": get_decision_feedback()}


@app.post("/v1/feedback")
def submit_decision_feedback(
    request: DecisionFeedbackRequest,
    authorization: str | None = Header(default=None),
):
    _require_reviewer_auth(authorization)
    if request.block_no not in {item["block_no"] for item in get_audit_events()}:
        raise HTTPException(status_code=404, detail="Audit decision not found.")
    return {"feedback": record_decision_feedback(
        request.block_no, request.label, request.reviewer_id, request.reason
    )}


@app.get("/v1/audit")
def audit_events():
    return {"events": get_audit_events()}


@app.get("/v1/audit/verify")
def audit_verify():
    return {"valid": verify_audit_chain()}
