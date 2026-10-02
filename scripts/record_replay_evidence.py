"""Record real replay/API evidence against the bundled synthetic UI.

Requires cu-runner serve. The operator handoff is driven by this explicitly labelled
operator stand-in, not claimed to be a person. Every action hits the real API and browser.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import time
import uuid

import httpx

from capability_runner.settings import Settings
from capability_runner.storage import atomic_json, verify_chain

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = Settings.from_env()
    settings.check_api_tokens()
    manifest = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15) as client:
        def request(method: str, path: str, body=None, *, operator: bool = False, lease: str = "") -> dict:
            token = settings.operator_token if operator else settings.runner_token
            headers = {"Authorization": "Bearer " + token.get_secret_value()}
            if lease:
                headers["X-Control-Token"] = lease
            for attempt in range(4):
                response = client.request(method, path, headers=headers, json=body)
                if response.status_code != 429 or method != "GET":
                    response.raise_for_status()
                    return response.json()
                time.sleep(min(15, max(1, int(response.headers.get("Retry-After", "10")))))
            raise RuntimeError("Evidence polling remained rate-limited")

        imported = request("POST", "/api/capabilities", json.loads((ROOT / "evidence/example-capability.json").read_text()))
        scenarios = [
            ("replay", "normal", "10002", "success", "OK"),
            ("not-found", "normal", "99999", "business_outcome", "NOT_FOUND"),
            ("validation", "normal", "00000", "business_outcome", "VALIDATION_ERROR"),
            ("recovery", "transient", "10003", "success", "OK"),
            ("handoff", "session", "10002", "success", "OK"),
            ("hard-failure", "permission", "10002", "failure", "RUN_CANCELLED"),
        ]
        for name, scenario, member_id, expected_status, expected_code in scenarios:
            target = "sandbox://legacy?scenario=" + scenario
            created = request("POST", "/api/replays", {"capability": imported["id"], "inputs": {"member_id": member_id}, "target": target})
            run_id = created["run_id"]
            base = "/api/operator/runs/" + run_id
            handled = False
            session_id = None
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                view = request("GET", "/api/runs/" + run_id)
                if session_id is None:
                    session_id = view["session_id"]
                assert session_id == view["session_id"], "Browser session changed"
                if view["result"]:
                    result = view["result"]
                    break
                if view["control"]["state"] == "PAUSED" and not handled:
                    handled = True
                    if scenario == "permission":
                        assert view["control"]["intervention"]["code"] == "PERMISSION_DENIED"
                        request("POST", base + "/cancel", {}, operator=True)
                    elif scenario == "session":
                        assert view["control"]["intervention"]["code"] == "SESSION_EXPIRED"
                        claimed = request("POST", base + "/claim", {"revision": view["control"]["revision"]}, operator=True)
                        revision, lease = claimed["revision"], claimed["control_token"]
                        request("POST", base + "/actions", {"revision": revision, "request_id": uuid.uuid4().hex,
                                "action": {"kind": "click", "target": "restore_session"}}, operator=True, lease=lease)
                        request("POST", base + "/resume", {"revision": revision}, operator=True, lease=lease)
                    else:
                        raise RuntimeError("Unexpected intervention in " + name)
                time.sleep(0.4)
            else:
                request("POST", "/api/runs/" + run_id + "/cancel", {})
                raise RuntimeError("Evidence run timed out: " + name)
            assert (result["status"], result["code"], result["llm_calls"]) == (expected_status, expected_code, 0), result["code"]
            if expected_status == "success":
                expected_balance = "0.00" if member_id == "10003" else "807.20"
                assert result["outputs"] == {"balance": expected_balance, "currency": "USD"}
            source = settings.data_dir / "runs" / run_id
            destination = ROOT / "evidence" / name
            # Do not overwrite the genuine discovery record or unrelated evidence.
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination)
            assert verify_chain(destination / "events.jsonl")
            safe_result = json.loads((destination / "result.json").read_text())
            assert all(value == "[REDACTED]" for value in safe_result["outputs"].values())
            manifest.append({"directory": name, "run_id": run_id, "status": result["status"], "code": result["code"],
                             "llm_calls": 0, "same_session_verified": True, "transport": "real-localhost-HTTP-to-live-Chromium",
                             "operator": "automated-test-stand-in" if handled else "none"})
            print(name + ": " + result["status"] + " / " + result["code"] + " / zero model calls", flush=True)
    atomic_json(ROOT / "evidence/replay-manifest.json", manifest)


if __name__ == "__main__":
    main()
