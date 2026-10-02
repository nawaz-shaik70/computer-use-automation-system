"""Real console JS + real API + real browser session, using an in-process test transport.

The evaluation container blocks HTTP browser navigation by managed policy. We do not change
that policy: the project's own console HTML is rendered in memory, and a TEST-ONLY fetch
transport dispatches to the real FastAPI ASGI application. No responses are canned. Standard
HTTP browser delivery remains a separately documented, unverified environment path.
"""
import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest
from playwright.async_api import async_playwright, expect

from capability_runner.api import create_api

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.browser
async def test_operator_console_live_session(settings, policy):
    settings.intervention_timeout_seconds = 25
    settings.human_lease_seconds = 25
    settings.run_timeout_seconds = 80
    app = create_api(settings, policy)
    caller = {"Authorization": "Bearer " + settings.runner_token.get_secret_value()}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            genuine_artifact = json.loads((ROOT / "evidence/example-capability.json").read_text())
            response = await client.post("/api/capabilities", headers=caller, json=genuine_artifact)
            assert response.status_code == 201
            response = await client.post("/api/replays", headers=caller, json={"capability": response.json()["id"], "inputs": {"member_id": "10002"}, "target": "sandbox://legacy?scenario=session"})
            run_id = response.json()["run_id"]
            run = app.state.manager.get(run_id)
            original_session = run.surface.session_id
            async with async_playwright() as playwright:
                options = {"headless": True}
                if settings.chromium_executable:
                    options["executable_path"] = settings.chromium_executable
                browser = await playwright.chromium.launch(**options)
                try:
                    page = await browser.new_page(viewport={"width": 1400, "height": 1100})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(type(error).__name__))
                    async def transport(payload):
                        assert payload["url"].startswith("/api/operator/")
                        response = await client.request(payload["method"], payload["url"], headers=payload["headers"], content=payload.get("body"))
                        return {"status": response.status_code, "headers": dict(response.headers),
                                "bytes": base64.b64encode(response.content).decode()}
                    await page.expose_function("__testTransport", transport)
                    template = (ROOT / "src/capability_runner/static/index.html").read_text()
                    template = template.replace('<link rel="stylesheet" href="/static/console.css">', '')
                    template = template.replace('<script src="/static/console.js" defer></script>', '')
                    await page.set_content(template)
                    await page.add_style_tag(content=(ROOT / "src/capability_runner/static/console.css").read_text())
                    await page.evaluate("""() => { window.fetch = async (url, options={}) => {
                        const response = await window.__testTransport({url, method:options.method || 'GET', headers:options.headers || {}, body:options.body});
                        const bytes = Uint8Array.from(atob(response.bytes), char => char.charCodeAt(0));
                        return new Response(bytes, {status:response.status, headers:response.headers});
                    }; }""")
                    await page.add_script_tag(content=(ROOT / "src/capability_runner/static/console.js").read_text())
                    await page.locator("#token").fill(settings.operator_token.get_secret_value())
                    await page.locator("#connect").click()
                    await expect(page.locator("#queue .run-item")).to_contain_text("SESSION_EXPIRED", timeout=30000)
                    await page.locator("#queue .run-item").click()
                    await page.locator("#claim").click()
                    await expect(page.locator("#screen")).to_be_visible(timeout=10000)
                    await page.wait_for_function("document.getElementById('screen').naturalWidth > 0")
                    await page.locator("#control").select_option(label="Restore session / click")
                    await page.locator("#act").click()
                    await expect(page.locator("#activity")).to_contain_text("Applied reviewed control: restore_session", timeout=10000)
                    assert run.surface.session_id == original_session
                    assert run.surface.page is not None
                    await page.locator("#resume").click()
                    await run.task
                    assert run.result.status == "success", run.result
                    assert run.result.outputs == {"balance": "807.20", "currency": "USD"}
                    assert run.result.interventions == 1 and run.result.llm_calls == 0
                    assert not errors, errors
                    assert run.surface.session_id == original_session
                    assert settings.operator_token.get_secret_value() not in run.audit.path.read_text()
                    assert (await page.locator("#token").input_value()) == ""
                finally:
                    await browser.close()
