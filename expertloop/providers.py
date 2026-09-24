"""An explicitly scripted demo and an optional real Responses-API provider."""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections.abc import Callable

import httpx

from .fixtures import SCHEMA, RULES

PROMPT_VERSION = "sql-assistant-v1"
SYSTEM_PROMPT = "You answer business questions with one read-only SQLite query.\n\n" + SCHEMA + "\n\n" + RULES
RESPONSE_SCHEMA = {"type": "object", "properties": {"sql": {"type": "string"}},
                   "required": ["sql"], "additionalProperties": False}


class BudgetExhausted(Exception):
    pass


class RunStopped(Exception):
    pass


def messages_for(question: str, examples: list[dict], system_prompt: str = SYSTEM_PROMPT) -> list[dict]:
    # Explicit input projection: no holdout SQL, labels, IDs, expected results,
    # failed answers or fixture contents can reach the live model.
    messages = [{"role": "system", "content": system_prompt}]
    for ex in examples:
        messages.extend([
            {"role": "user", "content": ex["question"]},
            {"role": "assistant", "content": json.dumps({"sql": ex["sql"]})},
        ])
    messages.append({"role": "user", "content": question})
    return messages


def demo_answer(task: dict, examples: list[dict], reserve: Callable[[], bool],
                stopped: Callable[[], bool]) -> dict:
    if stopped():
        raise RunStopped()
    if not reserve():
        raise BudgetExhausted()
    # This intentionally uses the oracle. It is a pipeline simulation, NOT an LLM
    # and NOT evidence of model improvement. UI, reports and README say so.
    number = int(hashlib.sha256(task["id"].encode()).hexdigest()[:8], 16)
    known_categories = {e["category"] for e in examples}
    correct = number % 5 == 0 or (task["category"] in known_categories and number % 7 != 0)
    return {"sql": task["reference_sql"] if correct else task["demo_bad_sql"],
            "input_tokens": None, "output_tokens": None, "latency_ms": None,
            "model": "scripted-demo-v1", "provider_response_id": None,
            "attempts": 1, "simulation": True, "error": None}


def live_answer(question: str, examples: list[dict], config: dict,
                reserve: Callable[[], bool], stopped: Callable[[], bool],
                system_prompt: str = SYSTEM_PROMPT) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("Set OPENAI_API_KEY on the server to use live mode")
    payload = {
        "model": config["model"], "input": messages_for(question, examples, system_prompt), "store": False,
        "max_output_tokens": config["max_output_tokens"],
        "text": {"format": {"type": "json_schema", "name": "sql_answer", "strict": True,
                            "schema": RESPONSE_SCHEMA}},
    }
    started = time.perf_counter()
    last_error = None
    usage = {"input_tokens": 0, "output_tokens": 0}
    with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0), follow_redirects=False, trust_env=False) as client:
        for attempt in range(1, 4):
            if stopped():
                raise RunStopped()
            if not reserve():
                raise BudgetExhausted()
            response_id = None
            resolved_model = config["model"]
            try:
                response = client.post(
                    "https://api.openai.com/v1/responses", json=payload,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"Provider returned HTTP {response.status_code}"
                    if attempt < 3:
                        time.sleep(min(4.0, .5 * 2**(attempt-1) + random.random()*.2))
                        continue
                response.raise_for_status()
                body = response.json()
                response_id = body.get("id")
                resolved_model = body.get("model", config["model"])
                for key in usage:
                    usage[key] += int(body.get("usage", {}).get(key, 0))
                if body.get("status") != "completed":
                    raise ValueError("Provider response was incomplete; increase the output limit or inspect the model configuration")
                texts = [c.get("text", "") for item in body.get("output", [])
                         if item.get("type") == "message" for c in item.get("content", [])
                         if c.get("type") == "output_text"]
                answer = json.loads("".join(texts))
                sql = answer.get("sql")
                if not isinstance(sql, str) or not sql.strip() or len(sql.encode()) > 20_000:
                    raise ValueError("Provider returned missing or oversized SQL")
                return {"sql": sql, **usage, "latency_ms": round((time.perf_counter()-started)*1000, 2),
                        "model": resolved_model, "provider_response_id": response_id,
                        "attempts": attempt, "simulation": False, "error": None}
            except httpx.HTTPStatusError as exc:
                # Do not persist raw provider response bodies, headers, or credentials.
                last_error = f"Provider HTTP {exc.response.status_code}. Check account/model access or rate limits."
                break
            except httpx.TransportError:
                last_error = "Provider transport error or timeout"
                if attempt < 3:
                    time.sleep(min(4.0, .5 * 2**(attempt-1)))
                    continue
                break
            except (ValueError, TypeError, KeyError) as exc:
                last_error = str(exc)[:250]
                break
    return {"sql": "", **usage, "latency_ms": round((time.perf_counter()-started)*1000, 2),
            "model": resolved_model, "provider_response_id": response_id, "attempts": attempt,
            "simulation": False, "error": last_error or "Unknown provider failure"}
