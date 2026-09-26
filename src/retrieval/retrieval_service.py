import json
import time
from functools import lru_cache
from pathlib import Path

from src.policy.context_normalizer import normalize_context
from src.retrieval.local_retrieval import local_demo_search, moss_error_result
from src.retrieval.moss_client import MossIntegrationError, MossNotConfigured, search_moss
from src.retrieval.retrieval_models import RetrievalResult


@lru_cache(maxsize=1)
def _approved_records():
    path = Path(__file__).resolve().parents[2] / "approval_records.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    return {record["invoice_id"].casefold(): record for record in records}


def _attach_approval_evidence(context):
    """Join invoice context to a separate trusted approval fixture by invoice ID."""
    context = dict(context)
    evidence = dict(context.get("evidence") or {})
    invoice_id = str(evidence.get("invoice_id", "")).strip().casefold()
    try:
        approval = _approved_records().get(invoice_id)
    except (OSError, ValueError, KeyError):
        approval = None
        evidence["approval_source_available"] = False
    if approval:
        evidence["verified_approval"] = approval
    context["evidence"] = evidence
    return context


def retrieve_context(doc_hash):
    """Retrieve and normalize context before policy evaluation."""
    start = time.perf_counter_ns()
    try:
        context = search_moss(doc_hash)
    except MossNotConfigured:
        context = local_demo_search(doc_hash)
    except MossIntegrationError:
        latency = round((time.perf_counter_ns() - start) / 1_000_000, 4)
        context = moss_error_result(latency)
    except Exception:
        latency = round((time.perf_counter_ns() - start) / 1_000_000, 4)
        context = moss_error_result(latency)

    return RetrievalResult.model_validate(normalize_context(_attach_approval_evidence(context)))
