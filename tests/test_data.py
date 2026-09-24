import json

import pytest

from expertloop.catalog import initial_tasks, synthetic_variants
from expertloop.models import ReviewRequest, RunConfig
from expertloop.providers import messages_for


def approve(w, task):
    return w.review(task["id"], ReviewRequest(action="approved", sql=task["reference_sql"],
        reviewer="Test reviewer", note="Verified query grain against reference fixtures.", revision=task["revision"]))


def test_initial_counts(workbench):
    counts = workbench.dashboard()["counts"]
    assert counts["development"] == 12
    assert counts["holdout"] == 30
    assert counts["approved"] == 0


def test_generate_deduplicates_and_preserves_holdout(workbench):
    original = workbench.store.tasks("holdout")
    first = workbench.generate()
    second = workbench.generate()
    assert first["inserted"] == 48
    assert second["inserted"] == 0
    assert second["skipped_duplicates"] == 48
    assert workbench.store.tasks("holdout") == original
    tasks = workbench.store.tasks("development")
    assert len(tasks) == 60
    assert all(t["review_status"] == "pending" for t in tasks)
    assert all(len(t["expected"]) == 3 for t in tasks)
    assert all(t["parent_id"] for t in tasks if t["source"] == "template_variant")


def test_no_cross_split_family_or_reference_duplicates():
    tasks = initial_tasks()
    tasks += synthetic_variants(tasks)
    dev = [t for t in tasks if t["split"] == "development"]
    holdout = [t for t in tasks if t["split"] == "holdout"]
    assert not {t["family"] for t in dev} & {t["family"] for t in holdout}
    assert not {t["reference_sql"] for t in dev} & {t["reference_sql"] for t in holdout}
    assert len({t["id"] for t in tasks}) == len(tasks)


def test_bad_correction_cannot_be_approved(workbench):
    task = workbench.store.tasks("development")[0]
    with pytest.raises(ValueError, match="failed"):
        workbench.review(task["id"], ReviewRequest(action="approved", sql=task["demo_bad_sql"],
            reviewer="Test reviewer", note="This should fail.", revision=0))
    assert workbench.store.task(task["id"])["review_status"] == "pending"
    assert workbench.store.reviews(task["id"]) == []


def test_holdout_approval_is_blocked(workbench):
    task = workbench.store.tasks("holdout")[0]
    with pytest.raises(ValueError, match="Holdout"):
        approve(workbench, task)
    assert workbench.export() == ""


def test_review_audit_and_optimistic_lock(workbench):
    task = workbench.store.tasks("development")[0]
    updated = approve(workbench, task)
    assert updated["revision"] == 1
    assert updated["reference_sql"] == task["reference_sql"]
    with pytest.raises(ValueError, match="changed"):
        approve(workbench, task)
    history = workbench.store.reviews(task["id"])
    assert len(history) == 1
    assert history[0]["previous_status"] == "pending"


def test_only_approved_development_exports(workbench):
    task = workbench.store.tasks("development")[0]
    approve(workbench, task)
    provenance = [json.loads(line) for line in workbench.export("provenance").splitlines()]
    sft = [json.loads(line) for line in workbench.export().splitlines()]
    assert len(provenance) == len(sft) == 1
    assert provenance[0]["task_id"] == task["id"]
    assert provenance[0]["split"] == "development"
    assert json.loads(sft[0]["messages"][-1]["content"])["sql"] == task["reference_sql"]


def test_rejection_revokes_export(workbench):
    task = approve(workbench, workbench.store.tasks("development")[0])
    workbench.review(task["id"], ReviewRequest(action="rejected", sql=None,
        reviewer="Test reviewer", note="Needs independent semantic review.", revision=1))
    assert workbench.export() == ""
    assert len(workbench.store.reviews(task["id"])) == 2


def test_snapshots_dont_change_after_review(workbench):
    task = workbench.store.tasks("development")[0]
    run = workbench.create_run(RunConfig(), start=False)
    approve(workbench, task)
    snapshot = workbench.store.run(run["id"])
    assert snapshot["examples"] == []
    new = workbench.create_run(RunConfig(), start=False)
    assert new["example_count"] == 1
    assert new["example_hash"] != run["example_hash"]


def test_provider_input_projects_out_oracles(workbench):
    task = workbench.store.tasks("holdout")[0]
    messages = messages_for(task["question"], [])
    text = json.dumps(messages)
    assert task["reference_sql"] not in text
    assert task["id"] not in text
    assert task["family"] not in text
    assert len(messages) == 2


def test_development_diagnostics_exclude_exact_examples(workbench):
    task = workbench.store.tasks("development")[0]
    approve(workbench, task)
    run = workbench.create_run(RunConfig(split="development"), start=False)
    assert task["id"] not in {t["id"] for t in run["tasks"]}
    assert run["task_count"] == 11
