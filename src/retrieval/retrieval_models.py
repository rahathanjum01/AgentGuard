from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: bool
    trust: float = Field(ge=0.0, le=1.0)
    latency: float = Field(ge=0.0)
    index_load_latency_ms: float = Field(default=0.0, ge=0.0)
    retrieval_cache_hit: bool = False
    doc: str
    status: str
    vendor: str
    retrieval_mode: Literal["LOCAL_DEMO", "MOSS", "MOSS_ERROR", "UNKNOWN"]
    evidence: dict[str, Any] = Field(default_factory=dict)
