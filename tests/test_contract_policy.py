import json

import jsonschema
import pytest
from pydantic import ValidationError

from capability_runner.engine import check_artifact
from capability_runner.policy import PolicyViolation
from capability_runner.profile import safe_goal
from capability_runner.schema import Action, Capability, Parameter
from capability_runner.settings import Settings
from capability_runner.storage import AuditLog, Catalog, verify_chain


def test_schema_roundtrip(artifact):
    body = json.loads(artifact.model_dump_json())
    jsonschema.validate(body, Capability.model_json_schema())
    assert Capability.model_validate_json(artifact.model_dump_json()) == artifact


@pytest.mark.parametrize("body", [
    {"kind": "fill", "target": "member_number"},
    {"kind": "click", "target": "search", "parameter": "member_id"},
    {"kind": "navigate", "path": "/legacy", "target": "search"},
    {"kind": "extract", "target": "balance"},
    {"kind": "evaluate", "path": "alert(1)"},
    {"kind": "fill", "target": "member_number", "parameter": "member_id", "literal": "12345"},
])
def test_invalid_actions_rejected(body):
    with pytest.raises(ValidationError):
        Action.model_validate(body)


@pytest.mark.parametrize("inputs", [{}, {"member_id": 10001}, {"member_id": "1234"}, {"member_id": "123456"},
                                    {"member_id": True}, {"member_id": "10001", "extra": "secret"}])
def test_typed_inputs(artifact, inputs):
    with pytest.raises(ValueError):
        artifact.validate_inputs(inputs)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e1000", 100, None])
def test_decimal_outputs_strict(value):
    assert not Parameter(type="decimal", pattern=r"-?\d+\.\d{2}", description="amount").check(value)


def test_integer_not_boolean():
    parameter = Parameter(type="integer", description="count")
    assert parameter.check(1)
    assert not parameter.check(True)


@pytest.mark.parametrize("suffix,method", [
    ("/close-account", "POST"), ("/legacy/../../secret", "GET"), ("/%2flegacy", "GET"),
    ("/legacy?unknown=secret", "GET"), ("/legacy?scenario=normal&scenario=session", "GET"),
    ("/legacy?scenario=notallowed", "GET"), ("/lookup", "GET"), ("//legacy", "GET"),
    ("/legacy#secret", "GET"), ("/legacy?broken", "GET"),
])
def test_route_policy_rejects(policy, sandbox_origin, suffix, method):
    assert not policy.allows_url(sandbox_origin + suffix, method)


@pytest.mark.parametrize("url", ["https://evil.invalid/legacy", "file:///etc/passwd", "javascript:alert(1)",
                                "http://user:pass@127.0.0.1:8765/legacy", "http://127.0.0.1:9999/legacy",
                                "http://127.0.0.1:notaport/legacy", "http://127.0.0.1/legacy"])
def test_origin_and_protocol_policy(policy, url):
    assert not policy.allows_url(url)


def test_explicit_allowlist(policy, sandbox_origin):
    assert policy.allows_url(sandbox_origin + "/legacy?scenario=normal")
    assert policy.allows_url("sandbox://legacy?scenario=normal")
    assert not policy.allows_url(sandbox_origin + "/lookup", "POST")


@pytest.mark.parametrize("actor", ["automation", "human"])
def test_irreversible_always_blocked(policy, sandbox_origin, actor):
    with pytest.raises(PolicyViolation, match="IRREVERSIBLE_BLOCKED"):
        policy.check_action(Action(kind="click", target="close_account"), sandbox_origin, actor)


def test_human_only_guard(policy, sandbox_origin):
    action = Action(kind="click", target="restore_session")
    with pytest.raises(PolicyViolation, match="HUMAN_APPROVAL_REQUIRED"):
        policy.check_action(action, sandbox_origin)
    policy.check_action(action, sandbox_origin, "human")


def test_parameter_confusion_blocked(policy, sandbox_origin):
    with pytest.raises(PolicyViolation):
        policy.check_action(Action(kind="fill", target="member_number", parameter="password"), sandbox_origin)


def test_modified_binding_rejected(artifact, policy, sandbox_origin):
    artifact.targets = dict(artifact.targets)
    artifact.targets["balance"] = artifact.targets["currency"]
    with pytest.raises(ValueError):
        check_artifact(artifact, policy, sandbox_origin)


def test_discontinuous_flow_rejected(artifact, policy, sandbox_origin):
    artifact.steps[2].before = "member"
    with pytest.raises(ValueError):
        check_artifact(artifact, policy, sandbox_origin)


def test_version_rejected(artifact):
    body = artifact.model_dump()
    body["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        Capability.model_validate(body)


def test_unknown_input_reference_rejected(artifact):
    body = artifact.model_dump()
    body["steps"][1]["action"]["parameter"] = "secret"
    with pytest.raises(ValidationError):
        Capability.model_validate(body)


def test_missing_output_rejected(artifact):
    body = artifact.model_dump()
    body["steps"].pop()
    with pytest.raises(ValidationError):
        Capability.model_validate(body)


def test_goal_redaction():
    value = safe_goal("Read member 10001 savings balance for Alice alice@example.com password supersecret!", {"member_id": "10001"})
    for secret in ("10001", "alice", "example", "supersecret"):
        assert secret not in value
    assert "savings" in value and "member_id" in value


def test_catalog_immutable_and_traversal(tmp_path, artifact):
    catalog = Catalog(tmp_path)
    name = catalog.save(artifact)
    assert catalog.load(name) == artifact
    assert catalog.save(artifact) == name
    with pytest.raises(ValueError):
        catalog.path("../../secrets")
    altered = artifact.model_copy(deep=True)
    altered.steps[0].after = "member"
    with pytest.raises(ValueError):
        catalog.save(altered)


def test_audit_field_allowlist_and_chain(tmp_path):
    log = AuditLog(tmp_path, "test")
    log.emit("test", code="OK")
    log.emit("test", step=1)
    assert verify_chain(log.path)
    with pytest.raises(ValueError):
        log.emit("test", raw_input="secret")
    log.path.write_text(log.path.read_text().replace('"OK"', '"MODIFIED"'))
    assert not verify_chain(log.path)


def test_auth_config_fails_closed():
    with pytest.raises(ValueError):
        Settings().check_api_tokens()
    with pytest.raises(ValueError):
        Settings(runner_token="x" * 32, operator_token="x" * 32).check_api_tokens()
