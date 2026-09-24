import json

import httpx
import pytest

from expertloop.providers import BudgetExhausted, live_answer, messages_for


class FakeClient:
    responses = []
    payloads = []

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def post(self, url, **kwargs):
        self.payloads.append(kwargs["json"])
        return self.responses.pop(0)


def response(code, body):
    return httpx.Response(code, json=body, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))


def success(sql="SELECT 1"):
    return response(200, {"id":"resp_test", "model":"resolved-snapshot", "status":"completed",
        "usage":{"input_tokens":100,"output_tokens":12},
        "output":[{"type":"message","content":[{"type":"output_text","text":json.dumps({"sql":sql})}]}]})


@pytest.fixture
def fake(monkeypatch):
    from expertloop import providers
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setattr(providers.httpx, "Client", FakeClient)
    monkeypatch.setattr(providers.time, "sleep", lambda _: None)
    FakeClient.responses = []
    FakeClient.payloads = []
    return FakeClient


def test_live_provider_structured_output_and_usage(fake):
    fake.responses = [success()]
    result = live_answer("Question", [], {"model":"example-model","max_output_tokens":512}, lambda: True, lambda: False, "frozen-system")
    assert result["sql"] == "SELECT 1"
    assert result["input_tokens"] == 100
    assert result["model"] == "resolved-snapshot"
    assert fake.payloads[0]["input"][0]["content"] == "frozen-system"
    assert fake.payloads[0]["store"] is False
    assert fake.payloads[0]["text"]["format"]["strict"] is True


def test_retries_count_each_request(fake):
    fake.responses = [response(429, {}), success()]
    reservations = []
    def reserve():
        reservations.append(1)
        return True
    result = live_answer("Question", [], {"model":"example-model","max_output_tokens":512}, reserve, lambda: False)
    assert result["attempts"] == 2
    assert len(reservations) == 2


def test_exhausted_budget_stops_before_api_call(fake):
    with pytest.raises(BudgetExhausted):
        live_answer("Question", [], {"model":"x","max_output_tokens":512}, lambda: False, lambda: False)
    assert fake.payloads == []


def test_incomplete_response_not_silently_successful(fake):
    fake.responses = [response(200, {"status":"incomplete", "usage":{"input_tokens":90,"output_tokens":512}})]
    result = live_answer("Question", [], {"model":"x","max_output_tokens":512}, lambda: True, lambda: False)
    assert result["error"]
    assert result["sql"] == ""
    assert result["output_tokens"] == 512


def test_http_error_does_not_persist_raw_body(fake):
    fake.responses = [response(401, {"error":"super-secret-test-content"})]
    result = live_answer("Question", [], {"model":"x","max_output_tokens":512}, lambda: True, lambda: False)
    assert "401" in result["error"]
    assert "super-secret" not in str(result)
