from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load_env(path: Path = Path(".env")):
    """Minimal dotenv reader: KEY=VALUE, optional matching quotes, no expansion."""
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


def main():
    load_env()
    parser = argparse.ArgumentParser(description="ExpertLoop local applied-AI workbench")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Run the browser UI and API")
    serve.add_argument("--port", type=int, default=int(os.getenv("EXPERTLOOP_PORT", "8000")))
    serve.add_argument("--data-dir", type=Path, default=Path(os.getenv("EXPERTLOOP_DATA_DIR", "state")))
    serve.add_argument("--host", default="127.0.0.1", help="Keep loopback unless using the included Docker setup")
    init = sub.add_parser("init", help="Create fixtures and the initial 42 tasks")
    init.add_argument("--data-dir", type=Path, default=Path(os.getenv("EXPERTLOOP_DATA_DIR", "state")))
    demo = sub.add_parser("demo", help="Execute a labeled, scripted pipeline example; no model API calls")
    demo.add_argument("--data-dir", type=Path, default=Path("state/demo"))
    demo.add_argument("--output", type=Path, default=Path("reports/demo"))
    args = parser.parse_args()
    if args.command in (None, "serve"):
        if hasattr(args, "data_dir"):
            os.environ["EXPERTLOOP_DATA_DIR"] = str(args.data_dir)
        import uvicorn
        uvicorn.run("expertloop.app:app", host=getattr(args, "host", "127.0.0.1"),
                    port=getattr(args, "port", 8000), workers=1)
        return
    from .service import Workbench
    from .models import ReviewRequest, RunConfig
    w = Workbench(args.data_dir)
    try:
        if args.command == "init":
            print(json.dumps(w.dashboard()["counts"], indent=2))
            return
        # Never impersonate human review. The explicit CLI demo records a clearly
        # labeled automation actor. Keep this demo state separate from real work.
        seen = set()
        for task in w.store.tasks("development"):
            if task["category"] in seen:
                continue
            seen.add(task["category"])
            w.review(task["id"], ReviewRequest(
                action="approved", sql=task["reference_sql"], reviewer="SCRIPTED_DEMO_NOT_HUMAN",
                note="Automated demo approval to exercise the pipeline; not domain-expert review.",
                revision=task["revision"],
            ))
        w.generate()
        run = w.create_run(RunConfig(name="Scripted end-to-end example", provider="demo"), start=False)
        w.execute_run(run["id"])
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "report.md").write_text(w.report_markdown(run["id"]))
        (args.output / "artifact.json").write_text(json.dumps({"run": w.store.run(run["id"]),
                                                             "results": w.store.results(run["id"])}, indent=2))
        (args.output / "demo-approved.jsonl").write_text(w.export("provenance"))
        print(json.dumps({"run_id": run["id"], "report": str(args.output/"report.md"),
                          "warning": "Scripted simulation only. Automated approvals are NOT human validation.",
                          "summary": w.run_view(run["id"])["summary"]}, indent=2))
    finally:
        w.shutdown()
