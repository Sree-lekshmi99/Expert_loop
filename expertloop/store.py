"""SQLite metadata with short transactions and immutable run snapshots."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, split TEXT NOT NULL, family TEXT NOT NULL,
              status TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, created_at TEXT NOT NULL,
              payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS batches (
              id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, request_count INTEGER NOT NULL DEFAULT 0,
              max_requests INTEGER NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS results (
              run_id TEXT NOT NULL, task_id TEXT NOT NULL, arm TEXT NOT NULL,
              created_at TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(run_id,task_id,arm)
            );
            CREATE INDEX IF NOT EXISTS tasks_status ON tasks(split,status);
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def add_tasks(self, tasks: list[dict]) -> int:
        with self.connect() as con:
            before = con.total_changes
            con.executemany("INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?,?)", [
                (t["id"], t["split"], t["family"], t["review_status"], t["ordinal"], dump(t)) for t in tasks
            ])
            return con.total_changes - before

    def tasks(self, split: str | None = None) -> list[dict]:
        with self.connect() as con:
            if split:
                rows = con.execute("SELECT payload FROM tasks WHERE split=? ORDER BY ordinal,id", (split,))
            else:
                rows = con.execute("SELECT payload FROM tasks ORDER BY ordinal,id")
            return [json.loads(row[0]) for row in rows]

    def task(self, task_id: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT payload FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return json.loads(row[0])

    def review(self, task_id: str, action: str, sql: str | None, reviewer: str,
               note: str, revision: int, validation: dict | None) -> dict:
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT payload FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise KeyError(task_id)
            task = json.loads(row[0])
            if task["split"] != "development":
                raise ValueError("Holdout tasks cannot enter the review/training pipeline")
            if task["revision"] != revision:
                raise ValueError("This task changed. Reload before submitting your review.")
            audit = {"action": action, "reviewer": reviewer, "note": note,
                     "previous_revision": revision, "previous_status": task["review_status"],
                     "previous_sql": task.get("corrected_sql"), "sql": sql,
                     "validation_passed": validation["passed"] if validation else None}
            task.update(review_status=action, corrected_sql=sql if action == "approved" else None,
                        reviewer=reviewer, review_note=note, revision=revision+1)
            con.execute("UPDATE tasks SET status=?,payload=? WHERE id=?", (action, dump(task), task_id))
            con.execute("INSERT INTO reviews(task_id,created_at,payload) VALUES(?,?,?)", (task_id, now(), dump(audit)))
            return task

    def reviews(self, task_id: str | None = None, limit: int = 100) -> list[dict]:
        with self.connect() as con:
            if task_id:
                rows = con.execute("SELECT * FROM reviews WHERE task_id=? ORDER BY id DESC LIMIT ?", (task_id, limit))
            else:
                rows = con.execute("SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,))
            return [{"id": r["id"], "task_id": r["task_id"], "created_at": r["created_at"], **json.loads(r["payload"])} for r in rows]

    def add_batch(self, batch: dict):
        with self.connect() as con:
            con.execute("INSERT INTO batches VALUES(?,?,?)", (batch["id"], now(), dump(batch)))

    def batches(self) -> list[dict]:
        with self.connect() as con:
            return [{**json.loads(r["payload"]), "created_at": r["created_at"]}
                    for r in con.execute("SELECT * FROM batches ORDER BY created_at DESC")]

    def create_run(self, run: dict):
        ts = now()
        with self.connect() as con:
            con.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                        (run["id"], "queued", ts, ts, 0, run["config"]["max_requests"], dump(run)))

    def run(self, run_id: str) -> dict:
        with self.connect() as con:
            r = con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not r:
            raise KeyError(run_id)
        run = json.loads(r["payload"])
        run.update(status=r["status"], created_at=r["created_at"], updated_at=r["updated_at"],
                   request_count=r["request_count"], max_requests=r["max_requests"])
        return run

    def runs(self) -> list[dict]:
        with self.connect() as con:
            ids = [r[0] for r in con.execute("SELECT id FROM runs ORDER BY created_at DESC LIMIT 100")]
        return [self.run(id_) for id_ in ids]

    def set_status(self, run_id: str, status: str, error: str | None = None):
        with self.connect() as con:
            row = con.execute("SELECT payload FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            payload = json.loads(row[0])
            payload["error"] = error
            con.execute("UPDATE runs SET status=?,updated_at=?,payload=? WHERE id=?",
                        (status, now(), dump(payload), run_id))

    def reserve_request(self, run_id: str) -> bool:
        # Counts every attempted provider request, including failed/retried calls.
        with self.connect() as con:
            cur = con.execute("UPDATE runs SET request_count=request_count+1,updated_at=? "
                              "WHERE id=? AND request_count<max_requests", (now(), run_id))
            return cur.rowcount == 1

    def save_result(self, run_id: str, task_id: str, arm: str, result: dict):
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO results VALUES(?,?,?,?,?)",
                        (run_id, task_id, arm, now(), dump(result)))

    def results(self, run_id: str) -> list[dict]:
        with self.connect() as con:
            return [{"task_id": r["task_id"], "arm": r["arm"], **json.loads(r["payload"])}
                    for r in con.execute("SELECT * FROM results WHERE run_id=? ORDER BY task_id,arm", (run_id,))]

    def recover(self):
        with self.connect() as con:
            con.execute("UPDATE runs SET status='paused',updated_at=? WHERE status IN ('queued','running')", (now(),))
