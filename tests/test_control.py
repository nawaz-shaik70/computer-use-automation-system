import asyncio
import time
import uuid

import pytest

from capability_runner.control import ControlError, ControlGate
from capability_runner.schema import Action
from capability_runner.storage import AuditLog


async def paused_gate(tmp_path, lease=5, timeout=5):
    gate = ControlGate(AuditLog(tmp_path, "test"), lease, timeout)
    task = asyncio.create_task(gate.pause({"code": "SESSION_EXPIRED", "step": 4, "snapshot": "snapshot-001.dom.json"}))
    await asyncio.sleep(0)
    return gate, task


async def test_exclusive_claim(tmp_path):
    gate, paused = await paused_gate(tmp_path)
    results = await asyncio.gather(gate.claim(1), gate.claim(1), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    winner = next(result for result in results if isinstance(result, dict))
    await gate.resume(winner["control_token"], winner["revision"])
    await paused
    assert gate.state == "AUTOMATION"


async def test_stale_owner_cannot_act_or_resume(tmp_path):
    gate, paused = await paused_gate(tmp_path)
    claim = await gate.claim(1)
    with pytest.raises(ControlError):
        await gate.resume("wrong", claim["revision"])
    with pytest.raises(ControlError):
        await gate.resume(claim["control_token"], 1)
    gate.lease_until = time.monotonic() - 1
    with pytest.raises(ControlError):
        await gate.resume(claim["control_token"], claim["revision"])
    assert (await gate.view())["state"] == "PAUSED"
    replacement = await gate.claim(gate.revision)
    await gate.resume(replacement["control_token"], replacement["revision"])
    await paused


async def test_idempotent_operator_action(tmp_path):
    gate, paused = await paused_gate(tmp_path)
    claim = await gate.claim(1)
    count = 0
    async def operation():
        nonlocal count
        count += 1
    action = Action(kind="click", target="restore_session")
    request_id = uuid.uuid4().hex
    first = await gate.perform(claim["control_token"], claim["revision"], request_id, action, operation)
    second = await gate.perform(claim["control_token"], claim["revision"], request_id, action, operation)
    assert first == second and count == 1
    with pytest.raises(ControlError, match="IDEMPOTENCY_CONFLICT"):
        await gate.perform(claim["control_token"], claim["revision"], request_id, Action(kind="click", target="search"), operation)
    await gate.resume(claim["control_token"], claim["revision"])
    await paused


async def test_resume_serializes_with_action(tmp_path):
    gate, paused = await paused_gate(tmp_path)
    claim = await gate.claim(1)
    entered, release = asyncio.Event(), asyncio.Event()
    async def operation():
        entered.set()
        await release.wait()
    act = asyncio.create_task(gate.perform(claim["control_token"], claim["revision"], uuid.uuid4().hex,
                                          Action(kind="click", target="restore_session"), operation))
    await entered.wait()
    resume = asyncio.create_task(gate.resume(claim["control_token"], claim["revision"]))
    await asyncio.sleep(0.02)
    assert not resume.done()
    release.set()
    await asyncio.gather(act, resume, paused)


async def test_pause_timeout(tmp_path):
    gate, paused = await paused_gate(tmp_path, timeout=0.02)
    with pytest.raises(ControlError, match="INTERVENTION_TIMEOUT"):
        await paused
    assert gate.state == "PAUSED"
    await gate.finish()


async def test_renew_and_finish(tmp_path):
    gate, paused = await paused_gate(tmp_path)
    claim = await gate.claim(1)
    assert (await gate.renew(claim["control_token"], claim["revision"]))["lease_seconds"] == 5
    await gate.finish()
    with pytest.raises(ControlError, match="RUN_CANCELLED"):
        await paused
    with pytest.raises(ControlError):
        await gate.claim(gate.revision)
