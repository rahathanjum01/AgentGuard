from statistics import mean, median

from src.policy.policy_engine import evaluate_policy
from src.retrieval.retrieval_models import RetrievalResult


def percentile(values, percentile_rank):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile_rank / 100
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def evaluate_batch(test_cases, guard_fn):
    results = []
    for case in test_cases:
        doc_hash = case["doc_hash"]
        name = case["name"]
        action = case.get("action", "payment")
        expected = case.get("expected")
        result = guard_fn(
            doc_hash,
            action,
            case.get("context_text"),
            case.get("transaction"),
        )
        results.append(
            {
                "name": name,
                "category": case.get("category", "uncategorized"),
                "expected": expected,
                "actual": result["decision"],
                "passed": expected is None or expected == result["decision"],
                "latency_ms": result.get("guard_latency_ms", result["latency"]),
                "retrieval_latency_ms": result["latency"],
                "stage_latency_ms": result.get("stage_latency_ms", {}),
                "result": result,
            }
        )

    latencies = [item["latency_ms"] for item in results]
    retrieval_latencies = [item["retrieval_latency_ms"] for item in results]
    passed = sum(item["passed"] for item in results)
    blocked = sum(item["actual"] == "BLOCK" for item in results)
    false_allows = sum(
        item["expected"] == "BLOCK" and item["actual"] == "ALLOW" for item in results
    )
    false_blocks = sum(
        item["expected"] == "ALLOW" and item["actual"] == "BLOCK" for item in results
    )
    unexpected_reviews = sum(
        item["expected"] in {"ALLOW", "BLOCK"} and item["actual"] == "REVIEW"
        for item in results
    )
    confusion = {expected: {actual: 0 for actual in ("ALLOW", "BLOCK", "REVIEW")} for expected in ("ALLOW", "BLOCK", "REVIEW")}
    decisions = {decision: 0 for decision in ("ALLOW", "BLOCK", "REVIEW")}
    category_results = {}
    for item in results:
        decisions[item["actual"]] += 1
        if item["expected"] in confusion:
            confusion[item["expected"]][item["actual"]] += 1
        category = item["category"]
        category_results.setdefault(category, {
            "total": 0, "passed": 0, "false_allows": 0, "false_blocks": 0,
            "unexpected_reviews": 0,
        })
        category_results[category]["total"] += 1
        category_results[category]["passed"] += int(item["passed"])
        category_results[category]["false_allows"] += int(item["expected"] == "BLOCK" and item["actual"] == "ALLOW")
        category_results[category]["false_blocks"] += int(item["expected"] == "ALLOW" and item["actual"] == "BLOCK")
        category_results[category]["unexpected_reviews"] += int(item["expected"] in {"ALLOW", "BLOCK"} and item["actual"] == "REVIEW")

    for values in category_results.values():
        values["accuracy"] = round(values["passed"] / values["total"], 3)

    return {
        "blocked": blocked,
        "false_allows": false_allows,
        "false_blocks": false_blocks,
        "unexpected_reviews": unexpected_reviews,
        "decision_counts": decisions,
        "confusion_matrix": confusion,
        "total_cases": len(results),
        "passed": passed,
        "accuracy": round(passed / len(results), 3) if results else 0.0,
        "average_latency_ms": round(mean(latencies), 3) if latencies else 0.0,
        "median_latency_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(percentile(latencies, 95), 3) if latencies else 0.0,
        "retrieval_median_latency_ms": round(median(retrieval_latencies), 3) if retrieval_latencies else 0.0,
        "stage_median_latency_ms": {
            stage: round(median([item["stage_latency_ms"].get(stage, 0.0) for item in results]), 4)
            for stage in sorted({stage for item in results for stage in item["stage_latency_ms"]})
        },
        "category_results": category_results,
        "results": results,
    }


def evaluate_retrieval_batch(test_cases, retrieve_fn):
    """Measure retrieval identity/evidence separately from policy decisions."""
    results = []
    for case in test_cases:
        retrieved = retrieve_fn(case["doc_hash"])
        context = retrieved.model_dump() if hasattr(retrieved, "model_dump") else dict(retrieved)
        evidence = context.get("evidence") or {}
        checks = {"found": context.get("found") is case["expected_found"]}
        for expected_key, actual_value in (
            ("expected_status", context.get("status")),
            ("expected_vendor", context.get("vendor")),
            ("expected_invoice_id", evidence.get("invoice_id")),
        ):
            if expected_key in case:
                checks[expected_key.removeprefix("expected_")] = actual_value == case[expected_key]
        results.append({
            "name": case["name"],
            "doc_hash": case["doc_hash"],
            "passed": all(checks.values()),
            "checks": checks,
            "retrieval_mode": context.get("retrieval_mode", "UNKNOWN"),
            "cache_hit": context.get("retrieval_cache_hit", False),
            "latency_ms": context.get("latency", 0.0),
            "context": context,
        })
    latencies = [item["latency_ms"] for item in results]
    passed = sum(item["passed"] for item in results)
    return {
        "total_cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "accuracy": round(passed / len(results), 3) if results else 0.0,
        "median_latency_ms": round(median(latencies), 3) if latencies else 0.0,
        "p95_latency_ms": round(percentile(latencies, 95), 3) if latencies else 0.0,
        "retrieval_modes": sorted({item["retrieval_mode"] for item in results}),
        "results": results,
    }


def evaluate_policy_batch(test_cases):
    """Measure the policy engine against supplied normalized contexts only."""
    results = []
    for case in test_cases:
        context = RetrievalResult.model_validate(case["context"])
        actual = evaluate_policy(case["action"], context).decision
        results.append({
            "name": case["name"],
            "expected": case["expected"],
            "actual": actual,
            "passed": actual == case["expected"],
        })
    passed = sum(item["passed"] for item in results)
    return {
        "total_cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "accuracy": round(passed / len(results), 3) if results else 0.0,
        "results": results,
    }
