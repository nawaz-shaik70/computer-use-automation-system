"""Test-only manufactured contracts. These are never presented as LLM discovery evidence."""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import shutil

import pytest
import pytest_asyncio

from capability_runner.engine import RunManager
from capability_runner.policy import Policy
from capability_runner.profile import CAPABILITY_NAME, CHECKPOINT, HANDLERS, INPUTS, OUTPUTS, TARGETS, profile_digest
from capability_runner.schema import Action, Capability, Step
from capability_runner.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sandbox_origin():
    # Browser tests use the bundled in-memory UI and make no HTTP requests.
    return "http://127.0.0.1:8765"


@pytest.fixture
def policy(sandbox_origin):
    body = json.loads((ROOT / "config/policy.json").read_text())
    body["allowed_origins"] = [sandbox_origin, "sandbox://legacy"]
    return Policy.model_validate(body)


@pytest.fixture
def settings(tmp_path, sandbox_origin, policy):
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(policy.model_dump_json())
    return Settings(target_origin=sandbox_origin, policy_file=policy_file, data_dir=tmp_path / "data",
                    bridge_dir=tmp_path / "bridge", chromium_executable=shutil.which("chromium") or shutil.which("chromium-browser"),
                    action_timeout_ms=1500, run_timeout_seconds=45, intervention_timeout_seconds=3,
                    human_lease_seconds=5, runner_token=secrets.token_urlsafe(32), operator_token=secrets.token_urlsafe(32))


@pytest.fixture
def artifact():
    actions = [
        (Action(kind="navigate", path="/legacy"), "any", "search"),
        (Action(kind="fill", target="member_number", parameter="member_id"), "search", "search"),
        (Action(kind="click", target="search"), "search", "results"),
        (Action(kind="click", target="open_member"), "results", "member"),
        (Action(kind="click", target="view_accounts"), "member", "accounts"),
        (Action(kind="click", target="savings"), "accounts", "savings"),
        (Action(kind="extract", target="balance", output="balance"), "savings", "savings"),
        (Action(kind="extract", target="currency", output="currency"), "savings", "savings"),
    ]
    return Capability(name=CAPABILITY_NAME, revision=1, profile_digest=profile_digest(), inputs=INPUTS,
                      outputs=OUTPUTS, targets=TARGETS, checkpoint=CHECKPOINT, error_handlers=HANDLERS,
                      steps=[Step(index=i, action=action, before=before, after=after) for i, (action, before, after) in enumerate(actions)])


@pytest_asyncio.fixture
async def manager(settings, policy):
    manager = RunManager(settings, policy)
    yield manager
    await manager.close()
