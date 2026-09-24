import threading
import time
from concurrent.futures import ThreadPoolExecutor

from expertloop.models import RunConfig
from expertloop.stats import paired_summary
from expertloop.service import Workbench


def test_demo_run_persisted_and_resumable(workbench):
    run = workbench.create_run(RunConfig(max_requests=4), start=False)
    workbench.execute_run(run["id"])
    partial = workbench.run_view(run["id"])
    assert partial["status"] == "paused"
    assert partial["request_count"] == 4
    assert partial["completed_results"] == 4
    initial = workbench.store.results(run["id"])
    workbench.resume(run["id"], extra_requests=80)
    workbench._thread.join(timeout=20)
    final = workbench.run_view(run["id"])
    assert final["status"] == "completed"
    assert final["completed_results"] == 60
    assert final["request_count"] == 60
    assert final["summary"]["n"] == 30
    assert final["summary"]["families"] == 10
    assert final["summary"]["delta"] == 0
    assert final["summary"]["ci95"] == [0, 0]
    assert all(r in workbench.store.results(run["id"]) for r in initial)
    assert all(r["input_tokens"] is None and r["latency_ms"] is None for r in final["results"])


def test_request_budget_is_atomic(workbench):
    run = workbench.create_run(RunConfig(max_requests=7), start=False)
    with ThreadPoolExecutor(max_workers=10) as pool:
        reservations = list(pool.map(lambda _: workbench.store.reserve_request(run["id"]), range(50)))
    assert sum(reservations) == 7
    assert workbench.store.run(run["id"])["request_count"] == 7


def test_recover_marks_interrupted_run_paused(workbench):
    run = workbench.create_run(RunConfig(), start=False)
    workbench.store.set_status(run["id"], "running")
    workbench.store.recover()
    assert workbench.store.run(run["id"])["status"] == "paused"


def test_partial_pairs_not_counted_as_complete():
    tasks = [{"id": "a", "family": "f", "category": "aggregation"}]
    result = [{"task_id": "a", "arm": "baseline", "evaluation": {"passed": True}}]
    summary = paired_summary(tasks, result)
    assert summary["n"] == 0
    assert summary["baseline_accuracy"] is None


def test_cluster_bootstrap_is_paired_and_reproducible():
    tasks = [{"id": str(i), "family": "f"+str(i//2), "category": "aggregation"} for i in range(6)]
    results = []
    for i in range(6):
        for arm in ("baseline", "improved"):
            results.append({"task_id": str(i), "arm": arm,
                            "evaluation": {"passed": arm == "improved"}})
    a = paired_summary(tasks, results)
    b = paired_summary(tasks, results)
    assert a == b
    assert a["families"] == 3
    assert a["delta"] == 1
    assert a["ci95"] == [1, 1]
    assert a["wins"] == 6


def test_artifact_and_report_warn_about_demo(workbench):
    run = workbench.create_run(RunConfig(), start=False)
    report = workbench.report_markdown(run["id"])
    assert "Scripted simulation; not model evidence" in report
    assert "not parameter training" in report
    assert "5,000" in report
