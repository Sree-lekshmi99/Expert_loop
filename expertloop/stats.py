"""Paired bootstrap clustered by template family, not by correlated variants."""
from __future__ import annotations

from collections import defaultdict
import random
import statistics


def quantile(sorted_values: list[float], p: float) -> float:
    index = (len(sorted_values)-1)*p
    lo = int(index)
    hi = min(lo+1, len(sorted_values)-1)
    return sorted_values[lo] + (index-lo)*(sorted_values[hi]-sorted_values[lo])


def paired_summary(tasks: list[dict], results: list[dict], seed: int = 7, replicates: int = 5000) -> dict:
    indexed = {(r["task_id"], r["arm"]): r for r in results}
    pairs = []
    for task in tasks:
        a = indexed.get((task["id"], "baseline"))
        b = indexed.get((task["id"], "improved"))
        if a is not None and b is not None:
            pairs.append((task, a, b))
    empty = {"n": 0, "total_tasks": len(tasks), "families": 0, "baseline_accuracy": None,
             "improved_accuracy": None, "delta": None, "ci95": None, "categories": [],
             "wins": 0, "regressions": 0, "unchanged": 0,
             "bootstrap": {"method": "paired family-cluster percentile bootstrap", "seed": seed, "replicates": replicates},
             "arms": {}}
    if not pairs:
        return empty
    grouped = defaultdict(list)
    categories = defaultdict(list)
    for task, a, b in pairs:
        delta = int(b["evaluation"]["passed"]) - int(a["evaluation"]["passed"])
        grouped[task["family"]].append(delta)
        categories[task["category"]].append((a["evaluation"]["passed"], b["evaluation"]["passed"]))
    groups = [grouped[key] for key in sorted(grouped)]
    rng = random.Random(seed)
    estimates = []
    for _ in range(replicates):
        sampled = [groups[rng.randrange(len(groups))] for _ in groups]
        estimates.append(sum(sum(g) for g in sampled)/sum(len(g) for g in sampled))
    estimates.sort()
    baseline = sum(a["evaluation"]["passed"] for _, a, _ in pairs)/len(pairs)
    improved = sum(b["evaluation"]["passed"] for _, _, b in pairs)/len(pairs)
    deltas = [d for group in groups for d in group]
    arms = {}
    for arm in ("baseline", "improved"):
        records = [indexed[(t["id"], arm)] for t, _, _ in pairs]
        latencies = sorted(r["latency_ms"] for r in records if r.get("latency_ms") is not None)
        arms[arm] = {
            "median_latency_ms": round(statistics.median(latencies), 2) if latencies else None,
            "p95_latency_ms": round(quantile(latencies, .95), 2) if latencies else None,
            "input_tokens": sum(r.get("input_tokens") or 0 for r in records),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in records),
            "provider_errors": sum(bool(r.get("error")) for r in records),
        }
    return {**empty, "n": len(pairs), "families": len(groups),
            "baseline_accuracy": baseline, "improved_accuracy": improved, "delta": improved-baseline,
            "ci95": [quantile(estimates, .025), quantile(estimates, .975)] if len(groups) > 1 else None,
            "wins": sum(d > 0 for d in deltas), "regressions": sum(d < 0 for d in deltas),
            "unchanged": sum(d == 0 for d in deltas), "arms": arms,
            "categories": [{"category": k, "n": len(v), "baseline": sum(a for a, _ in v)/len(v),
                            "improved": sum(b for _, b in v)/len(v)} for k, v in sorted(categories.items())]}
