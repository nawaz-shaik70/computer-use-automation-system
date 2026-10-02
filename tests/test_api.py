import asyncio
import json

import httpx
import pytest
import pytest_asyncio

from capability_runner.api import create_api
from capability_runner.sandbox import create_sandbox


@pytest_asyncio.fixture
async def api(settings, policy):
    app = create_api(settings, policy)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            yield app, client


def caller(settings):
    return {"Authorization": "Bearer " + settings.runner_token.get_secret_value()}


def operator(settings):
    return {"Authorization": "Bearer " + settings.operator_token.get_secret_value()}


async def test_health_openapi_console_and_assets(api):
    _, client = api
    assert (await client.get("/health")).json()["status"] == "ok"
    spec = (await client.get("/openapi.json")).json()
    assert "/api/discoveries" in spec["paths"] and "/api/replays" in spec["paths"]
    for path in ("/", "/static/console.js", "/static/console.css"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


async def test_authentication_and_role_separation(api, settings):
    _, client = api
    assert (await client.get("/api/capabilities")).status_code == 401
    assert (await client.get("/api/capabilities", headers=operator(settings))).status_code == 401
    assert (await client.get("/api/operator/interventions", headers=caller(settings))).status_code == 401
    assert (await client.get("/api/operator/interventions", headers=operator(settings))).status_code == 200


async def test_origin_boundary(api, settings):
    _, client = api
    response = await client.get("/api/capabilities", headers={**caller(settings), "Origin": "https://evil.invalid"})
    assert response.status_code == 403
    assert (await client.get("/api/capabilities", headers={**caller(settings), "Origin": "http://testserver"})).status_code == 200


async def test_no_input_echo_on_validation(api, settings):
    _, client = api
    response = await client.post("/api/replays", headers=caller(settings), json={"capability": "secret-person@example.invalid", "inputs": {"member_id": "secret-value"}})
    assert response.status_code == 422
    assert "secret" not in response.text


async def test_request_size_limit(api, settings):
    _, client = api
    response = await client.post("/api/replays", headers=caller(settings), content="x" * 66_000)
    assert response.status_code == 413


async def test_import_catalog_schema_and_reject_mutation(api, settings, artifact):
    _, client = api
    response = await client.post("/api/capabilities", headers=caller(settings), json=artifact.model_dump())
    assert response.status_code == 201, response.text
    artifact_id = response.json()["id"]
    assert (await client.get("/api/capabilities/" + artifact_id, headers=caller(settings))).json()["schema_version"] == "1.0"
    assert len((await client.get("/api/capabilities", headers=caller(settings))).json()["capabilities"]) == 1
    assert (await client.get("/api/schema", headers=caller(settings))).json()["additionalProperties"] is False
    bad = artifact.model_dump()
    bad["targets"]["search"]["locators"][0]["value"] = "Delete everything"
    assert (await client.post("/api/capabilities", headers=caller(settings), json=bad)).status_code == 422


async def test_missing_resources(api, settings):
    _, client = api
    assert (await client.get("/api/runs/" + "a" * 32, headers=caller(settings))).status_code == 404
    assert (await client.get("/api/capabilities/read_savings_balance.v999", headers=caller(settings))).status_code == 404


@pytest.mark.browser
async def test_api_real_replay(api, settings, artifact):
    _, client = api
    artifact_id = (await client.post("/api/capabilities", headers=caller(settings), json=artifact.model_dump())).json()["id"]
    response = await client.post("/api/replays", headers=caller(settings), json={"capability": artifact_id, "inputs": {"member_id": "10002"}})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(400):
        response = await client.get("/api/runs/" + run_id, headers=caller(settings))
        result = response.json()["result"]
        if result:
            break
        await asyncio.sleep(0.08)
    assert result["status"] == "success" and result["outputs"]["balance"] == "807.20"
    assert result["llm_calls"] == 0
    hidden = await client.get("/api/operator/runs/" + run_id, headers=operator(settings))
    assert hidden.json()["result"]["outputs"]["balance"] == "[REDACTED]"


async def test_capacity_and_immediate_cancel(api, settings, artifact):
    app, client = api
    app.state.manager.settings.max_active_runs = 1
    name = (await client.post("/api/capabilities", headers=caller(settings), json=artifact.model_dump())).json()["id"]
    first = await client.post("/api/replays", headers=caller(settings), json={"capability": name, "inputs": {"member_id": "10002"}})
    run_id = first.json()["run_id"]
    second = await client.post("/api/replays", headers=caller(settings), json={"capability": name, "inputs": {"member_id": "10002"}})
    assert second.status_code == 429
    assert (await client.post("/api/runs/" + run_id + "/cancel", headers=caller(settings), json={})).status_code == 200
    run = app.state.manager.get(run_id)
    assert run.result and run.result.code == "RUN_CANCELLED"
    assert not run.inputs


async def test_http_sandbox_serves_same_real_ui():
    app = create_sandbox()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sandbox") as client:
        assert (await client.get("/health")).json()["synthetic_only"] is True
        response = await client.get("/legacy?scenario=session")
        assert response.status_code == 200 and "srcdoc=" in response.text
        assert "Legacy workspace" in response.text and "Restore session" in response.text
        assert (await client.get("/legacy?scenario=unknown")).status_code == 400
        assert (await client.get("/api/members")).status_code == 404
