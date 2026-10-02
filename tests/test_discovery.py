"""Scripted test double ONLY. Genuine live-LLM evidence lives separately in /evidence/."""
import asyncio
import json

import pytest

from capability_runner.planner import Planner
from capability_runner.schema import Decision

pytestmark = pytest.mark.browser


class TestPlanner(Planner):
    __test__ = False
    provider, model = "test-double", "test-fixture"
    def __init__(self, choices):
        self.choices = iter(choices)
        self.calls = 0
    async def decide(self, request):
        self.calls += 1
        choice = next(self.choices)
        return Decision(request_id=request["request_id"], candidate_id=choice, reason="advance")


async def wait_for_handoff(run):
    for _ in range(300):
        state = await run.gate.view()
        if state["state"] == "PAUSED":
            return state
        await asyncio.sleep(0.03)
    raise AssertionError("missing handoff")


async def test_discovery_recording_contract(manager):
    planner = TestPlanner(["fill_member_number", "click_search", "click_open_member", "click_view_accounts", "click_savings",
                           "extract_currency", "extract_balance", "finish"])
    run = manager.start("discovery", {"member_id": "10001"}, goal="Read the member savings balance and currency", planner=planner)
    await run.task
    assert run.result.status == "success", run.result
    artifact = manager.catalog.load(run.result.artifact)
    assert len(artifact.steps) == 8
    assert artifact.steps[6].action.output == "currency"  # Model chooses extraction order, not a hardcoded flow.
    assert run.result.llm_calls == 8
    assert '"10001"' not in artifact.model_dump_json()
    replay = manager.start("replay", {"member_id": "10002"}, capability=artifact)
    await replay.task
    assert replay.result.status == "success" and replay.result.outputs["balance"] == "807.20"


async def test_unoffered_model_action_escalates(manager):
    run = manager.start("discovery", {"member_id": "10001"}, goal="Read savings balance", planner=TestPlanner(["click_close_account"]))
    state = await wait_for_handoff(run)
    assert state["intervention"]["code"] == "INVALID_MODEL_ACTION"
    await manager.cancel(run.id)
    assert not manager.catalog.all()


async def test_step_budget_stops_discovery(manager):
    manager.settings.max_steps = 1
    run = manager.start("discovery", {"member_id": "10001"}, goal="Read savings balance", planner=TestPlanner(["fill_member_number"]))
    state = await wait_for_handoff(run)
    assert state["intervention"]["code"] == "STEP_LIMIT"
    await manager.cancel(run.id)
    assert not manager.catalog.all()


async def test_model_escalation_is_real_pause(manager):
    run = manager.start("discovery", {"member_id": "10001"}, goal="Read savings balance", planner=TestPlanner(["escalate"]))
    state = await wait_for_handoff(run)
    assert state["intervention"]["code"] == "MODEL_REQUESTED_OPERATOR"
    assert run.surface.page is not None
    await manager.cancel(run.id)
