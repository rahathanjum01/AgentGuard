"""Reproducible local/Moss guardrail latency benchmark.

Run: python scripts/benchmark.py --iterations 100
The report labels the active retrieval provider; local timings are never Moss
claims. Configure MOSS_PROJECT_ID and MOSS_PROJECT_KEY to benchmark Moss.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation_cases import EVALUATION_CASES
from src.moss_validator import runtime_guard


def percentile(values: list[float], value: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round((len(ordered) - 1) * value)))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")

    moss_setting = os.getenv("MOSS_ENABLED", "").lower()
    has_credentials = bool(os.getenv("MOSS_PROJECT_ID") and os.getenv("MOSS_PROJECT_KEY"))
    moss_enabled = moss_setting in {"1", "true", "yes"} or (
        has_credentials and moss_setting not in {"0", "false", "no", "off"}
    )
    if moss_enabled:
        preflight = runtime_guard(EVALUATION_CASES[0]["doc_hash"], EVALUATION_CASES[0]["action"])
        if preflight["retrieval_mode"] != "MOSS":
            raise SystemExit(
                "Moss preflight failed (mode: "
                f"{preflight['retrieval_mode']}). Stopping before the benchmark to conserve credits. "
                "Fix or replace the index, then retry."
            )

    retrieval_ms, end_to_end_ms, modes = [], [], Counter()
    stage_ms: dict[str, list[float]] = {}
    for _ in range(args.iterations):
        for case in EVALUATION_CASES:
            started = time.perf_counter_ns()
            result = runtime_guard(
                case["doc_hash"],
                case["action"],
                case.get("context_text"),
                case.get("transaction"),
            )
            end_to_end_ms.append((time.perf_counter_ns() - started) / 1_000_000)
            retrieval_ms.append(result["latency"])
            for stage, latency in result.get("stage_latency_ms", {}).items():
                stage_ms.setdefault(stage, []).append(latency)
            modes[result["retrieval_mode"]] += 1

    print(f"samples: {len(end_to_end_ms)}")
    print(f"retrieval modes: {dict(modes)}")
    print(f"retrieval ms  p50={statistics.median(retrieval_ms):.4f} p95={percentile(retrieval_ms, .95):.4f}")
    print(f"end-to-end ms p50={statistics.median(end_to_end_ms):.4f} p95={percentile(end_to_end_ms, .95):.4f}")
    for stage, values in sorted(stage_ms.items()):
        print(f"{stage} ms p50={statistics.median(values):.4f} p95={percentile(values, .95):.4f}")
    if set(modes) != {"MOSS"}:
        print("NOTE: This is not a Moss benchmark. Configure Moss credentials for MOSS-only results.")


if __name__ == "__main__":
    main()
