"""Restricted SQL worker, invoked with python -I and a scrubbed environment.

This is defense in depth for a local portfolio app, not a multi-tenant OS sandbox.
Only this file (stdlib only) runs in the evaluation child process.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

TABLES = {"customers", "orders", "order_items", "products"}
FUNCTIONS = {
    "abs", "avg", "coalesce", "count", "date", "datetime", "ifnull", "julianday",
    "length", "lower", "ltrim", "max", "min", "nullif", "replace", "round", "rtrim",
    "strftime", "substr", "substring", "sum", "time", "total", "trim", "upper",
    "row_number", "rank", "dense_rank", "lag", "lead", "first_value", "last_value",
    "like", "glob", "instr", "printf", "format", "group_concat",
    "nth_value", "ntile", "percent_rank", "cume_dist", "iif", "typeof",
}
MAX_ROWS = 1000
MAX_SQL_BYTES = 20_000


def authorize(action: int, arg1: str | None, arg2: str | None,
              database: str | None, source: str | None) -> int:
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ and (arg1 or "").lower() in TABLES and database in ("main", None):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or arg1 or "").lower() in FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_one(path: Path, sql: str) -> dict:
    started = time.perf_counter()
    conn = None
    try:
        if not sql or len(sql.encode()) > MAX_SQL_BYTES:
            raise ValueError("SQL is empty or exceeds 20 KB")
        # A lexical precheck is only a convenience; the authorizer is the actual
        # statement/function/table boundary and execute() rejects multiple statements.
        stripped = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S).lstrip()
        if not re.match(r"(?i)^(select|with)\b", stripped):
            raise ValueError("Only SELECT or non-recursive WITH queries are permitted")
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.execute("PRAGMA temp_store=MEMORY")
        if hasattr(conn, "setlimit"):
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_SQL_BYTES)
            conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 64)
            conn.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
            conn.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 10)
            conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        conn.set_authorizer(authorize)
        ticks = 0

        def stop_large_query() -> int:
            nonlocal ticks
            ticks += 1
            return int(ticks > 2000 or time.perf_counter() - started > 2.0)

        conn.set_progress_handler(stop_large_query, 1000)
        cursor = conn.execute(sql)
        if cursor.description is None:
            raise ValueError("The statement did not return a table")
        rows = cursor.fetchmany(MAX_ROWS + 1)
        if len(rows) > MAX_ROWS:
            raise ValueError("Result exceeds the 1,000-row evaluation limit")
        if any(isinstance(v, bytes) or (isinstance(v, float) and not math.isfinite(v))
               for row in rows for v in row):
            raise ValueError("Binary or non-finite values are not supported")
        return {"ok": True, "columns": [c[0] for c in cursor.description],
                "rows": [list(row) for row in rows], "error": None,
                "execution_ms": round((time.perf_counter() - started)*1000, 3)}
    except (sqlite3.Error, ValueError, OverflowError, MemoryError) as exc:
        return {"ok": False, "columns": [], "rows": [], "error": str(exc)[:500],
                "execution_ms": round((time.perf_counter() - started)*1000, 3)}
    finally:
        if conn is not None:
            conn.close()


def set_os_limits() -> None:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    except (ImportError, ValueError, OSError):
        # Windows lacks resource; parent wall timeout and SQLite limits still apply.
        pass


if __name__ == "__main__":
    set_os_limits()
    request = json.loads(sys.stdin.read(100_000))
    response = {name: execute_one(Path(path), request["sql"])
                for name, path in request["fixtures"].items()}
    print(json.dumps(response, allow_nan=False))
