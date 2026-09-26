from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.retrieval.retrieval_models import RetrievalResult


SupportedAction = Literal[
    "payment",
    "read_email",
    "delete_file",
    "send_contract",
    "approve_po",
]


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SupportedAction
    doc_hash: str = Field(min_length=1, max_length=256)
    context_text: str | None = Field(default=None, max_length=10_000)
    transaction: dict[str, Any] | None = None


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["APPROVED", "REJECTED"]
    reviewer_id: str = Field(default="demo-operator", min_length=1, max_length=120)


class DecisionFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_no: int = Field(ge=1)
    label: Literal["CORRECT", "INCORRECT"]
    reviewer_id: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=1000)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class GuardResponse(BaseModel):
    decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    executed: bool
    policy_name: str
    policy_version: str
    reason_code: str
    reason: str
    request_id: str
    execution: dict[str, Any]
    guard: dict[str, Any]
    retrieval: RetrievalResult
    review_request: dict[str, Any] | None = None
    honeypot: dict[str, Any]
    audit: dict[str, Any]
