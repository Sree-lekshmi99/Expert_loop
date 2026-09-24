import os
import time
import pytest

WRITE = {"X-ExpertLoop": "1"}


def test_health_and_ui(client):
    assert client.get("/health").json()["status"] == "ok"
    ui = client.get("/")
    assert ui.status_code == 200
    assert "ExpertLoop" in ui.text
    assert "frame-ancestors 'none'" in ui.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200


def test_dashboard_and_task_detail(client):
    assert client.get("/api/dashboard").json()["counts"]["holdout"] == 30
    tasks = client.get("/api/tasks?split=development").json()
    assert len(tasks) == 12
    detail = client.get("/api/tasks/"+tasks[0]["id"]).json()
    assert detail["evaluation"]["passed"] is False
    assert "not a live model response" in detail["candidate_origin"]


def test_missing_record_is_404(client):
    assert client.get("/api/tasks/missing").status_code == 404
    assert client.get("/api/runs/missing").status_code == 404


def test_write_guard_and_origin(client):
    assert client.post("/api/generate", json={}).status_code == 403
    assert client.post("/api/generate", json={}, headers={**WRITE,"Origin":"https://evil.example"}).status_code == 403
    assert client.post("/api/generate", json={}, headers=WRITE).status_code == 200


def test_rejects_unknown_hosts(client):
    assert client.get("/health", headers={"Host":"evil.example"}).status_code == 400


def test_rejects_unknown_request_fields(client):
    assert client.post("/api/runs", headers=WRITE, json={"provider":"demo", "fake":"field"}).status_code == 422


def test_approval_and_export_through_api(client):
    task_id = client.get("/api/tasks?split=development").json()[0]["id"]
    task = client.get("/api/tasks/"+task_id).json()["task"]
    response = client.post(f"/api/tasks/{task_id}/review", headers=WRITE, json={
        "action":"approved", "sql":task["reference_sql"], "reviewer":"API test",
        "note":"Removed the duplicated order-level sum.", "revision":0})
    assert response.status_code == 200
    assert response.json()["review_status"] == "approved"
    export = client.get("/api/export?format=provenance")
    assert "attachment" in export.headers["content-disposition"]
    assert task_id in export.text


def test_no_live_mode_without_credentials(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/api/runs", headers=WRITE, json={"provider":"openai", "model":"test-model"})
    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_api_key_is_not_in_dashboard(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-marker")
    response = client.get("/api/dashboard")
    assert response.json()["live_available"]
    assert "super-secret-marker" not in response.text
