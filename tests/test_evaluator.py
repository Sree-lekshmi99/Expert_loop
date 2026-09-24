import sqlite3

import pytest

from expertloop.evaluator import compare_tables, evaluate, run_sql
from expertloop.sql_worker import execute_one


def table(rows, columns=None):
    return {"ok": True, "rows": rows, "columns": columns or ["x"], "error": None}


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders",
    "DELETE FROM orders",
    "UPDATE orders SET total_cents=0",
    "INSERT INTO customers VALUES (999, 'bad', 'US')",
    "ATTACH DATABASE '/tmp/other.sqlite' AS other",
    "PRAGMA table_info(orders)",
    "SELECT load_extension('/tmp/evil.so')",
    "SELECT * FROM sqlite_master",
    "SELECT readfile('/etc/passwd')",
    "SELECT * FROM pragma_database_list()",
    "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT * FROM x",
    "SELECT 1; DELETE FROM orders",
    "WITH x AS (SELECT 1) DELETE FROM orders",
    "SELECT randomblob(1000000000)",
])
def test_rejects_unsafe_sql(workbench, sql):
    result = run_sql(sql, workbench.fixtures)
    assert all(not r["ok"] for r in result.values())
    con = sqlite3.connect(workbench.fixtures["standard"])
    try:
        assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] > 0
    finally:
        con.close()


def test_seed_references_and_faults(workbench):
    for task in workbench.store.tasks("development"):
        assert evaluate(task, task["reference_sql"], workbench.fixtures)["passed"], task["id"]
        assert not evaluate(task, task["demo_bad_sql"], workbench.fixtures)["passed"], task["id"]


def test_holdout_references(workbench):
    for task in workbench.store.tasks("holdout"):
        assert evaluate(task, task["reference_sql"], workbench.fixtures)["passed"]


def test_aliases_ignored():
    assert compare_tables(table([[1]], ["a"]), table([[1]], ["b"]), False)[0]


def test_column_position_preserved():
    assert not compare_tables(table([[1, 2]], ["a", "b"]), table([[2, 1]], ["b", "a"]), False)[0]


def test_row_order_is_task_specific():
    a, b = table([[1], [2]]), table([[2], [1]])
    assert compare_tables(a, b, False)[0]
    assert not compare_tables(a, b, True)[0]


def test_duplicates_preserved():
    assert not compare_tables(table([[1], [1], [2]]), table([[1], [2], [2]]), False)[0]


def test_numeric_tolerance_and_types():
    assert compare_tables(table([[1.0]]), table([[1.00000001]]), False)[0]
    assert not compare_tables(table([[1]]), table([["1"]]), False)[0]
    assert not compare_tables(table([[None]]), table([[0]]), False)[0]


def test_ambiguous_numeric_matching():
    assert compare_tables(table([[0.0000008], [0]]), table([[0], [0.0000016]]), False)[0]


def test_empty_tables_still_check_columns():
    assert not compare_tables(table([], ["a"]), table([], ["a", "b"]), False)[0]


def test_row_limit(workbench):
    result = run_sql("SELECT a.order_id FROM orders a CROSS JOIN orders b", workbench.fixtures)
    assert not result["standard"]["ok"]


def test_inexpensive_query_with_comment_and_cte(workbench):
    result = run_sql("-- safe comment\nWITH x AS (SELECT order_id FROM orders) SELECT COUNT(*) FROM x", workbench.fixtures)
    assert all(r["ok"] for r in result.values())


def test_scrubs_api_key_from_subprocess(workbench, monkeypatch):
    from expertloop import evaluator
    original = evaluator.subprocess.run
    captured = {}
    def wrapped(*args, **kwargs):
        captured.update(kwargs["env"])
        assert "-I" in args[0]
        return original(*args, **kwargs)
    monkeypatch.setenv("OPENAI_API_KEY", "secret-test-value")
    monkeypatch.setattr(evaluator.subprocess, "run", wrapped)
    assert run_sql("SELECT 1", workbench.fixtures)["standard"]["ok"]
    assert "OPENAI_API_KEY" not in captured


def test_instruction_budget(workbench):
    result = run_sql("SELECT SUM(a.order_id*b.order_id*c.order_id*d.order_id) FROM orders a, orders b, orders c, orders d", workbench.fixtures)
    assert not result["standard"]["ok"]


def test_large_duplicate_multiset_does_not_recurse():
    a = table([[1]] * 1000)
    assert compare_tables(a, a, False)[0]


def test_like_is_supported_for_read_only_filters(workbench):
    result = run_sql("SELECT COUNT(*) FROM orders WHERE ordered_at LIKE '2025-%'", workbench.fixtures)
    assert all(r["ok"] for r in result.values())
