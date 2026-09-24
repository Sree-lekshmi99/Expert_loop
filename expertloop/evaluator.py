from __future__ import annotations

import json
from collections import Counter
import math
import os
import subprocess
import sys
from pathlib import Path

from .sql_worker import execute_one

EVALUATOR_VERSION = "sqlite-suite-v1"


def run_sql(sql: str, fixtures: dict[str, Path], timeout: float = 5.0) -> dict:
    """Untrusted candidate SQL always runs in a child with no inherited API key."""
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "WINDIR") if k in os.environ}
    env["PYTHONHASHSEED"] = "0"
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", str(Path(__file__).with_name("sql_worker.py"))],
            input=json.dumps({"sql": sql, "fixtures": {k: str(v) for k, v in fixtures.items()}}),
            text=True, capture_output=True, timeout=timeout, env=env, check=False,
        )
        if proc.returncode != 0:
            raise ValueError("SQL worker terminated (resource limit or invalid response)")
        return json.loads(proc.stdout)
    except subprocess.TimeoutExpired:
        error = "SQL worker exceeded wall-clock limit"
    except (ValueError, OSError) as exc:
        error = str(exc)
    return {name: {"ok": False, "columns": [], "rows": [], "error": error,
                   "execution_ms": None} for name in fixtures}


def equal_cell(a: object, b: object) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    return type(a) is type(b) and a == b


def equal_row(a: list, b: list) -> bool:
    return len(a) == len(b) and all(equal_cell(x, y) for x, y in zip(a, b))


def compare_tables(expected: dict, actual: dict, ordered: bool) -> tuple[bool, str]:
    if not expected["ok"]:
        return False, "Invalid reference result"
    if not actual["ok"]:
        return False, "Execution error: " + str(actual["error"])
    if len(expected["columns"]) != len(actual["columns"]):
        return False, "Column count differs"
    a, b = expected["rows"], actual["rows"]
    if len(a) != len(b):
        return False, f"Row count differs: expected {len(a)}, received {len(b)}"
    if ordered:
        return (True, "Match") if all(equal_row(x, y) for x, y in zip(a, b)) else (False, "Values or row order differ")
    if Counter(map(tuple, a)) == Counter(map(tuple, b)):
        return True, "Match"
    # A multiset, not a set: repeated rows must be preserved. Use a perfect
    # bipartite match so floating-point tolerance cannot make greedy matching fail.
    adjacency = [[j for j, row in enumerate(b) if equal_row(x, row)] for x in a]
    match: dict[int, int] = {}

    def augment(i: int, seen: set[int]) -> bool:
        for j in adjacency[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in match or augment(match[j], seen):
                match[j] = i
                return True
        return False

    for i in range(len(a)):
        if not augment(i, set()):
            return False, "Values or duplicate-row counts differ"
    return True, "Match"


def evaluate(task: dict, sql: str, fixtures: dict[str, Path]) -> dict:
    actual = run_sql(sql, fixtures)
    checks = {}
    for name, expected in task["expected"].items():
        passed, reason = compare_tables(expected, actual[name], task["ordered"])
        checks[name] = {"passed": passed, "reason": reason, "expected": expected, "actual": actual[name]}
    return {"passed": all(c["passed"] for c in checks.values()), "fixtures": checks,
            "evaluator_version": EVALUATOR_VERSION}


def prepare_task(task: dict, fixtures: dict[str, Path]) -> dict:
    """Only our code-authored templates take this fast in-process path."""
    task = dict(task)
    task["expected"] = {name: execute_one(path, task["reference_sql"]) for name, path in fixtures.items()}
    for name, result in task["expected"].items():
        if not result["ok"]:
            raise ValueError(f"Invalid template {task['family']} on {name}: {result['error']}")
        result.pop("execution_ms", None)  # Deterministic dataset hash; no runtime timing.
    task["reference_checks"] = len(task["expected"])
    return task
