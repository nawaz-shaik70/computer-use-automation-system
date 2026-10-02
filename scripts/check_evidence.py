"""Validate evidence linkage/integrity, not third-party model authorship attestation."""
import json
from pathlib import Path

from capability_runner.schema import Capability, Decision
from capability_runner.storage import verify_chain

root = Path(__file__).resolve().parents[1]
evidence = root / "evidence"
capability = Capability.model_validate_json((evidence / "example-capability.json").read_text())
assert capability.steps, "empty capability"
assert Capability.model_validate_json((evidence / "discovery/artifact.json").read_text()) == capability
chains = sorted(evidence.glob("*/events.jsonl"))
assert chains, "no evidence logs"
for path in chains:
    assert verify_chain(path), "audit chain mismatch: " + str(path)
    result = json.loads((path.parent / "result.json").read_text())
    assert all(value == "[REDACTED]" for value in result["outputs"].values()), "unredacted outputs"

requests = sorted((evidence / "discovery/model_requests").glob("*.json"))
decisions = sorted((evidence / "discovery/model_decisions").glob("*.json"))
assert requests and len(requests) == len(decisions), "missing model exchanges"
seen = set()
actions = []
for request_path, decision_path in zip(requests, decisions):
    assert request_path.name == decision_path.name
    request = json.loads(request_path.read_text())
    decision = Decision.model_validate_json(decision_path.read_text())
    assert decision.request_id == request["request_id"] and decision.request_id not in seen
    seen.add(decision.request_id)
    chosen = next((item for item in request["candidates"] if item["id"] == decision.candidate_id), None)
    assert chosen is not None, "unoffered candidate"
    if chosen["action"] is not None:
        actions.append(chosen["action"])
    elif chosen["id"] == "finish":
        assert request["observation"]["screen"] == capability.checkpoint.screen
        assert set(request["collected_outputs"]) == set(capability.outputs)
assert actions == [step.action.model_dump() for step in capability.steps[1:]], "model choices do not match artifact"
discovery_result = json.loads((evidence / "discovery/result.json").read_text())
assert discovery_result["status"] == "success" and discovery_result["llm_calls"] == len(decisions)

manifest_path = evidence / "replay-manifest.json"
if manifest_path.exists():
    for case in json.loads(manifest_path.read_text()):
        assert case["directory"] in {"replay", "not-found", "validation", "recovery", "handoff", "hard-failure"}
        result = json.loads((evidence / case["directory"] / "result.json").read_text())
        assert result["run_id"] == case["run_id"]
        assert result["status"] == case["status"] and result["code"] == case["code"]
        assert result["llm_calls"] == 0
print(f"Validated capability, {len(decisions)} linked discovery decisions, and {len(chains)} audit chains.")
