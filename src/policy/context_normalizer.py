DEFAULT_CONTEXT = {
    "found": False,
    "trust": 0.0,
    "latency": 0.0,
    "doc": "UNKNOWN",
    "status": "UNTRUSTED",
    "vendor": "UNKNOWN",
    "retrieval_mode": "UNKNOWN",
    "evidence": {},
}


def normalize_context(raw_context):
    """Return a stable, bounded context contract for policy evaluation."""
    context = {**DEFAULT_CONTEXT, **(raw_context or {})}
    try:
        trust = float(context["trust"])
    except (TypeError, ValueError):
        trust = 0.0

    context["trust"] = min(max(trust, 0.0), 1.0)
    context["latency"] = max(float(context["latency"] or 0.0), 0.0)
    context["found"] = bool(context["found"])
    if not isinstance(context["evidence"], dict):
        context["evidence"] = {}
    return context
