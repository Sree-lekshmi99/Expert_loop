from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import os
import threading
import uuid

from .catalog import CATEGORIES, GENERATOR_VERSION, initial_tasks, synthetic_variants
from .evaluator import EVALUATOR_VERSION, evaluate, prepare_task
from .fixtures import build_fixtures, fixture_manifest, fingerprint, RULES, SCHEMA
from .models import ReviewRequest, RunConfig
from .providers import (BudgetExhausted, RunStopped, PROMPT_VERSION, SYSTEM_PROMPT,
                        demo_answer, live_answer)
from .stats import paired_summary
from .store import Store, dump, now


class Workbench:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.fixtures = build_fixtures(self.root / "fixtures")
        self.manifest = fixture_manifest(self.fixtures)
        self.store = Store(self.root / "metadata.sqlite")
        if not self.store.tasks():
            self.store.add_tasks([prepare_task(t, self.fixtures) for t in initial_tasks()])
        self.store.recover()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_id: str | None = None

    def dashboard(self) -> dict:
        tasks = self.store.tasks()
        dev = [t for t in tasks if t["split"] == "development"]
        test = [t for t in tasks if t["split"] == "holdout"]
        runs = [self.run_view(r["id"], full=False) for r in self.store.runs()[:10]]
        return {
            "counts": {"development": len(dev), "holdout": len(test),
                       "approved": sum(t["review_status"] == "approved" for t in dev),
                       "pending": sum(t["review_status"] == "pending" for t in dev),
                       "rejected": sum(t["review_status"] == "rejected" for t in dev),
                       "synthetic": sum(t["source"] == "template_variant" for t in dev),
                       "fixtures": len(self.fixtures)},
            "categories": [{"id": cat, "label": label,
                            "development": sum(t["category"] == cat for t in dev),
                            "approved": sum(t["category"] == cat and t["review_status"] == "approved" for t in dev),
                            "holdout": sum(t["category"] == cat for t in test)} for cat, label in CATEGORIES.items()],
            "runs": runs, "activity": self.store.reviews(limit=8),
            "batches": self.store.batches()[:5], "fixture_manifest": self.manifest,
            "live_available": bool(os.environ.get("OPENAI_API_KEY")),
            "default_model": os.environ.get("OPENAI_MODEL", ""),
            "schema": SCHEMA, "rules": RULES,
        }

    def generate(self) -> dict:
        seeds = [t for t in self.store.tasks("development") if not t["parent_id"]]
        generated = [prepare_task(t, self.fixtures) for t in synthetic_variants(seeds)]
        count = self.store.add_tasks(generated)
        batch = {"id": "batch_"+uuid.uuid4().hex[:10], "inserted": count,
                 "generator_version": GENERATOR_VERSION, "source": "deterministic templates (not an LLM)",
                 "candidate_count": len(generated), "skipped_duplicates": len(generated)-count,
                 "parent_ids": [s["id"] for s in seeds], "human_approved": False,
                 "dataset_hash": self.dataset_hash()}
        self.store.add_batch(batch)
        return batch

    def dataset_hash(self) -> str:
        return fingerprint(self.store.tasks())

    def review(self, task_id: str, request: ReviewRequest) -> dict:
        task = self.store.task(task_id)
        if task["split"] != "development":
            raise ValueError("Holdout tasks cannot be reviewed or exported as training data")
        validation = None
        if request.action == "approved":
            if not request.sql:
                raise ValueError("An approved example requires corrected SQL")
            validation = evaluate(task, request.sql, self.fixtures)
            if not validation["passed"]:
                raise ValueError("Correction failed one or more fixtures. Validate and fix it before approval.")
        return self.store.review(task_id, request.action, request.sql, request.reviewer,
                                 request.note, request.revision, validation)

    def preview(self, task_id: str) -> dict:
        task = self.store.task(task_id)
        candidate = task["demo_bad_sql"]
        origin = "Scripted faulty example (not a live model response)"
        for run in self.store.runs():
            if run["config"]["split"] != "development":
                continue
            result = next((r for r in self.store.results(run["id"])
                           if r["task_id"] == task_id and r["arm"] == "baseline"), None)
            if result and result.get("sql"):
                candidate = result["sql"]
                origin = f"{run['config']['provider']} baseline · {run['id']}"
                break
        return {"task": task, "candidate_sql": candidate, "candidate_origin": origin,
                "evaluation": evaluate(task, candidate, self.fixtures),
                "reviews": self.store.reviews(task_id)}

    def approved_examples(self, limit: int = 12) -> list[dict]:
        approved = [t for t in self.store.tasks("development") if t["review_status"] == "approved"]
        # Fixed, category-diverse selection independent of each held-out question.
        picked, seen = [], set()
        for task in approved:
            if task["category"] not in seen:
                picked.append(task)
                seen.add(task["category"])
        picked += [t for t in approved if t not in picked]
        return [{"id": t["id"], "question": t["question"], "sql": t["corrected_sql"],
                 "category": t["category"], "family": t["family"], "revision": t["revision"],
                 "reviewer": t["reviewer"]} for t in picked[:limit]]

    def export(self, format_: str = "sft") -> str:
        lines = []
        for t in self.store.tasks("development"):
            if t["review_status"] != "approved":
                continue
            if format_ == "sft":
                record = {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                       {"role": "user", "content": t["question"]},
                                       {"role": "assistant", "content": dump({"sql": t["corrected_sql"]})}]}
            else:
                record = {"task_id": t["id"], "question": t["question"], "sql": t["corrected_sql"],
                          "family": t["family"], "category": t["category"], "parent_id": t["parent_id"],
                          "source": t["source"], "revision": t["revision"], "reviewer": t["reviewer"],
                          "note": t["review_note"], "split": "development", "fixture_manifest": self.manifest,
                          "reference_status": t["reference_status"]}
            lines.append(dump(record))
        return "\n".join(lines) + ("\n" if lines else "")

    def create_run(self, config: RunConfig, start: bool = True) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise ValueError("Another evaluation is active. Pause it or let it finish first.")
            cfg = config.model_dump()
            if cfg["provider"] == "openai":
                cfg["model"] = cfg["model"] or os.environ.get("OPENAI_MODEL", "")
                if not os.environ.get("OPENAI_API_KEY") or not cfg["model"]:
                    raise ValueError("Live mode needs OPENAI_API_KEY and a model name")
            else:
                cfg["model"] = "scripted-demo-v1"
            tasks = self.store.tasks(cfg["split"])
            examples = self.approved_examples(cfg["few_shot_limit"])
            # For development diagnostics, exclude any exact evaluation tasks from
            # few-shot examples: evaluate only the remaining development tasks.
            if cfg["split"] == "development":
                example_ids = {e["id"] for e in examples}
                tasks = [t for t in tasks if t["id"] not in example_ids]
            if not tasks:
                raise ValueError("No evaluation tasks remain after excluding the few-shot examples")
            if cfg["split"] == "holdout" and {t["family"] for t in tasks} & {e["family"] for e in examples}:
                raise ValueError("Development/holdout family leakage detected")
            run = {"id": "run_"+uuid.uuid4().hex[:10], "config": cfg, "tasks": tasks,
                   "examples": examples, "dataset_hash": fingerprint(tasks), "example_hash": fingerprint(examples),
                   "fixture_manifest": self.manifest, "prompt_version": PROMPT_VERSION,
                   "system_prompt_hash": fingerprint(SYSTEM_PROMPT), "system_prompt": SYSTEM_PROMPT,
                   "evaluator_version": EVALUATOR_VERSION, "created_by": "local-user", "error": None,
                   "caveat": "Scripted simulation; not model evidence" if cfg["provider"] == "demo"
                             else "Small synthetic benchmark; not evidence of broad professional capability"}
            self.store.create_run(run)
            if start:
                self._start_unlocked(run["id"])
            return self.run_view(run["id"])

    def _start_unlocked(self, run_id: str):
        self.store.set_status(run_id, "queued")
        self._stop.clear()
        self._active_id = run_id
        self._thread = threading.Thread(target=self.execute_run, args=(run_id,), daemon=True)
        self._thread.start()

    def resume(self, run_id: str, extra_requests: int = 0) -> dict:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise ValueError("An evaluation is still active")
            run = self.store.run(run_id)
            if run["status"] == "completed":
                return self.run_view(run_id)
            if run["evaluator_version"] != EVALUATOR_VERSION:
                raise ValueError("Evaluator version changed. Start a new experiment instead of resuming.")
            if run["fixture_manifest"] != self.manifest:
                raise ValueError("Fixtures changed. Start a new experiment instead of resuming.")
            if extra_requests:
                with self.store.connect() as con:
                    con.execute("UPDATE runs SET max_requests=max_requests+? WHERE id=?", (extra_requests, run_id))
            self._start_unlocked(run_id)
        return self.run_view(run_id)

    def pause(self, run_id: str):
        with self._lock:
            if self._active_id != run_id or not self._thread or not self._thread.is_alive():
                raise ValueError("This run is not active")
            self._stop.set()
        return {"message": "Pause requested; in-flight requests may finish"}

    def execute_run(self, run_id: str):
        self.store.set_status(run_id, "running")
        run = self.store.run(run_id)
        completed = {(r["task_id"], r["arm"]) for r in self.store.results(run_id)}
        errors = []

        def one(task: dict, arm: str):
            if self._stop.is_set():
                raise RunStopped()
            examples = run["examples"] if arm == "improved" else []
            reserve = lambda: self.store.reserve_request(run_id)
            if run["config"]["provider"] == "demo":
                answer = demo_answer(task, examples, reserve, self._stop.is_set)
            else:
                answer = live_answer(task["question"], examples, run["config"], reserve, self._stop.is_set, run["system_prompt"])
            assessment = evaluate(task, answer["sql"], self.fixtures)
            self.store.save_result(run_id, task["id"], arm, {**answer, "evaluation": assessment})

        # Alternate arm order across tasks rather than always running baseline first.
        jobs = []
        for i, task in enumerate(run["tasks"]):
            arms = ("baseline", "improved") if i % 2 == 0 else ("improved", "baseline")
            jobs += [(task, arm) for arm in arms if (task["id"], arm) not in completed]
        try:
            with ThreadPoolExecutor(max_workers=run["config"]["concurrency"]) as pool:
                futures = [pool.submit(one, task, arm) for task, arm in jobs]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except BudgetExhausted:
                        errors.append("Request cap reached; add a budget allowance to resume")
                        self._stop.set()
                    except RunStopped:
                        pass
                    except Exception as exc:
                        errors.append(f"Worker error: {type(exc).__name__}: {str(exc)[:200]}")
                        self._stop.set()
            n = len(self.store.results(run_id))
            status = "completed" if n == len(run["tasks"])*2 else "paused"
            self.store.set_status(run_id, status, errors[0] if errors else None)
        except Exception as exc:
            self.store.set_status(run_id, "failed", f"Coordinator error: {type(exc).__name__}")

    def run_view(self, run_id: str, full: bool = True) -> dict:
        run = self.store.run(run_id)
        results = self.store.results(run_id)
        summary = paired_summary(run["tasks"], results)
        view = {k: v for k, v in run.items() if k not in ("tasks", "examples", "system_prompt")}
        view.update(summary=summary, completed_results=len(results), total_results=len(run["tasks"])*2,
                    example_count=len(run["examples"]), task_count=len(run["tasks"]))
        if full:
            view["results"] = results
            view["tasks"] = [{k: t[k] for k in ("id", "question", "category", "family", "split")} for t in run["tasks"]]
            view["examples"] = run["examples"]
        return view

    def shutdown(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=6)

    def report_markdown(self, run_id: str) -> str:
        run = self.run_view(run_id)
        s = run["summary"]
        pct = lambda v: f"{v*100:.1f}%" if v is not None else "not available"
        ci = "not available" if s["ci95"] is None else f"[{s['ci95'][0]*100:+.1f}, {s['ci95'][1]*100:+.1f}] percentage points"
        lines = [f"# ExpertLoop experiment: {run['config']['name']}", "", f"**{run['caveat']}**", "",
                 f"Generated: {now()}", f"Run: `{run_id}` · Status: **{run['status']}**", "",
                 "## Configuration", "", f"Provider: {run['config']['provider']}",
                 f"Requested model: `{run['config']['model']}`", f"Split: {run['config']['split']}",
                 f"Fixed approved development examples: {run['example_count']}",
                 f"Dataset hash: `{run['dataset_hash']}`", f"Example hash: `{run['example_hash']}`",
                 f"Prompt version: `{run['prompt_version']}`", f"Evaluator: `{run['evaluator_version']}`", "",
                 "## Paired results", "", f"Completed pairs: {s['n']}/{s['total_tasks']}; template families: {s['families']}",
                 f"Baseline execution accuracy: {pct(s['baseline_accuracy'])}",
                 f"Approved-example execution accuracy: {pct(s['improved_accuracy'])}",
                 f"Difference: {s['delta']*100:+.1f} percentage points" if s["delta"] is not None else "Difference: not available",
                 f"95% family-cluster paired-bootstrap interval: {ci}",
                 f"Wins / regressions / unchanged: {s['wins']} / {s['regressions']} / {s['unchanged']}", "",
                 "| Category | Paired tasks | Baseline | Approved examples |",
                 "|---|---:|---:|---:|"]
        for c in s["categories"]:
            lines.append(f"| {CATEGORIES[c['category']]} | {c['n']} | {pct(c['baseline'])} | {pct(c['improved'])} |")
        lines += ["", "## Usage and latency", "", f"Attempted requests (including retries): {run['request_count']} / {run['max_requests']}",
                  "These are scripted calls, with no tokens or model latency, in demo mode." if run["config"]["provider"] == "demo"
                  else "Recorded token counts cover responses with returned usage. Provider billing can include unobserved timed-out or interrupted calls."]
        for arm, values in s["arms"].items():
            lines.append(f"- {arm}: {values}")
        lines += ["", "## Interpretation and limitations", "",
                  "A task passes only if its result matches the reference on all three fixtures. Aliases are ignored; column position, duplicates, NULLs and task-specified row order matter.",
                  "The bootstrap resamples template families and retains paired baseline/improved results. It uses 5,000 replicates and seed 7. With only ten holdout families, uncertainty estimates are preliminary.",
                  "Repeated holdout use can contaminate future decisions. Freeze this test set before model/prompt selection and create a fresh independent test set for final claims.",
                  "Templates, questions and fixtures are synthetic and are not independently domain-expert-certified. Passing fixtures does not prove SQL equivalence on every possible database.",
                  "Partial reports use completed pairs only and must not be compared as final experiment results.",
                  "The approved-example arm is few-shot prompting, not parameter training. No fine-tuning is included.",
                  "Development runs exclude exact few-shot tasks but may contain related template siblings. They are diagnostics, not generalization evidence.",
                  "A local single-user service is not a production multi-tenant deployment. See docs/SECURITY.md.", ""]
        return "\n".join(lines)
