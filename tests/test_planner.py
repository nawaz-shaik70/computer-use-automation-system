import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from capability_runner.planner import BridgePlanner, OpenAIPlanner, PlannerError
from capability_runner.storage import AuditLog, atomic_json


@pytest.mark.parametrize("base", ["http://example.invalid/v1", "https://user:pass@example.invalid/v1", "https://example.invalid/v1?token=bad"])
def test_model_endpoint_constraints(settings, tmp_path, base):
    settings.model_base_url = base
    with pytest.raises(PlannerError):
        OpenAIPlanner(settings, AuditLog(tmp_path / "log", "test"))


def test_model_key_required(settings, tmp_path):
    with pytest.raises(PlannerError, match="MODEL_KEY_MISSING"):
        OpenAIPlanner(settings, AuditLog(tmp_path / "log", "test"))


async def test_hosted_adapter_shape_and_response(settings, tmp_path, monkeypatch):
    settings.model_api_key = SecretStr("unit-test-key-not-a-real-credential")
    request = {"request_id": "r1", "goal": "read savings balance", "candidates": [{"id": "click_search"}]}
    def respond(req):
        body = json.loads(req.content)
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["messages"][0]["role"] == "system"
        assert body["temperature"] == 0
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"request_id": "r1", "candidate_id": "click_search", "reason": "advance"})}}],
                                        "usage": {"prompt_tokens": 80, "completion_tokens": 10}})
    original = httpx.AsyncClient
    monkeypatch.setattr("capability_runner.planner.httpx.AsyncClient", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    planner = OpenAIPlanner(settings, AuditLog(tmp_path / "log", "test"))
    decision = await planner.decide(request)
    assert decision.candidate_id == "click_search" and planner.calls == 1
    assert "unit-test-key" not in (tmp_path / "log/events.jsonl").read_text()


@pytest.mark.parametrize("status,body,code,attempts", [
    (429, {}, "MODEL_UNAVAILABLE", 2),
    (503, {}, "MODEL_UNAVAILABLE", 2),
    (401, {}, "MODEL_REQUEST_REJECTED", 1),
    (200, {"choices": [{"message": {"content": "not-json"}}]}, "INVALID_MODEL_RESPONSE", 1),
    (200, {"choices": [{"message": {"refusal": "not allowed"}}]}, "MODEL_REFUSED", 1),
])
async def test_hosted_failures_bounded(settings, tmp_path, monkeypatch, status, body, code, attempts):
    settings.model_api_key = SecretStr("unit-test-key-not-real")
    original = httpx.AsyncClient
    monkeypatch.setattr("capability_runner.planner.httpx.AsyncClient", lambda **kw: original(transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body)), **kw))
    planner = OpenAIPlanner(settings, AuditLog(tmp_path / "log", "test"))
    with pytest.raises(PlannerError, match=code):
        await planner.decide({"request_id": "r1"})
    assert planner.calls == attempts


async def test_bridge_waits_for_explicit_external_decision(settings, tmp_path):
    planner = BridgePlanner(settings, AuditLog(tmp_path / "log", "test"))
    task = asyncio.create_task(planner.decide({"request_id": "r1", "goal": "read savings balance", "candidates": [{"id": "click_search"}]}))
    await asyncio.sleep(0.05)
    assert not task.done()
    assert (planner.directory / "001.request.json").exists()
    atomic_json(planner.directory / "001.response.json", {"request_id": "r1", "candidate_id": "click_search", "reason": "advance"})
    assert (await task).candidate_id == "click_search"
    assert planner.calls == 1


async def test_bridge_timeout_not_a_fake_success(settings, tmp_path):
    settings.model_timeout_seconds = 1
    planner = BridgePlanner(settings, AuditLog(tmp_path / "log", "test"))
    with pytest.raises(PlannerError, match="MODEL_TIMEOUT"):
        await planner.decide({"request_id": "r1"})


@pytest.mark.parametrize("request_id,candidate_id", [("stale", "click_search"), ("r1", "invented_control")])
async def test_bridge_rejects_stale_or_unoffered_decisions(settings, tmp_path, request_id, candidate_id):
    planner = BridgePlanner(settings, AuditLog(tmp_path / "log", "test"))
    task = asyncio.create_task(planner.decide({"request_id": "r1", "candidates": [{"id": "click_search"}]}))
    await asyncio.sleep(0.05)
    atomic_json(planner.directory / "001.response.json", {"request_id": request_id, "candidate_id": candidate_id, "reason": "advance"})
    with pytest.raises(PlannerError, match="INVALID_BRIDGE_RESPONSE"):
        await task
    assert not (tmp_path / "log/model_decisions/001.json").exists()
