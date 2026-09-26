from typing import Literal

from pydantic import BaseModel, ConfigDict


ExecutionStatus = Literal["EXECUTED", "PREVENTED", "FAILED"]


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    action: str
    decision: Literal["ALLOW", "BLOCK", "REVIEW"]
    executed: bool
    status: ExecutionStatus
    result: str
    sandbox_record_id: str | None = None
