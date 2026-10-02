"""One-command deterministic replay using the genuine discovery artifact in evidence/.

Starts both real services. Never calls a model and never supplies canned browser results.
Uses only synthetic inputs. All subprocesses are terminated on success, error or Ctrl+C.
"""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    artifact_path = root / "evidence" / "example-capability.json"
    if not artifact_path.exists():
        raise SystemExit("Discovery artifact missing. Run a genuine discovery first.")
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(root / "src"), "RUNNER_TOKEN": secrets.token_urlsafe(32),
                "OPERATOR_TOKEN": secrets.token_urlsafe(32), "DATA_DIR": str(root / ".runtime" / "demo"),
                "RUNNER_HOST": "127.0.0.1", "RUNNER_PORT": "8000", "SANDBOX_HOST": "127.0.0.1",
                "SANDBOX_PORT": "8765", "TARGET_ORIGIN": "http://127.0.0.1:8765", "HEADLESS": "true"})
    if not env.get("CHROMIUM_EXECUTABLE"):
        env["CHROMIUM_EXECUTABLE"] = shutil.which("chromium") or shutil.which("chromium-browser") or ""
    for port in (8000, 8765):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.4)
        except httpx.HTTPError:
            continue
        raise SystemExit(f"Port {port} is already serving HTTP. Stop the existing demo services first.")

    def stop(process):
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    with ExitStack() as stack:
        for command, port in (("sandbox", 8765), ("serve", 8000)):
            process = subprocess.Popen([sys.executable, "-m", "capability_runner.cli", command], cwd=root, env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            stack.callback(stop, process)
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError(command + " failed to start; use the documented manual commands for diagnostics")
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.3).is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError(command + " startup timeout")
        with httpx.Client(base_url="http://127.0.0.1:8000", headers={"Authorization": "Bearer " + env["RUNNER_TOKEN"]}) as client:
            response = client.post("/api/capabilities", json=json.loads(artifact_path.read_text()))
            response.raise_for_status()
            artifact_id = response.json()["id"]
            created = client.post("/api/replays", json={"capability": artifact_id, "inputs": {"member_id": "10002"}})
            created.raise_for_status()
            run_id = created.json()["run_id"]
            for _ in range(300):
                response = client.get("/api/runs/" + run_id)
                response.raise_for_status()
                result = response.json()["result"]
                if result:
                    if result["status"] != "success" or result["llm_calls"] != 0:
                        raise RuntimeError("Replay failed: " + result["code"])
                    print(json.dumps(result, indent=2))
                    print("Verified: real browser replay, typed outputs, checkpoint passed, zero model calls.")
                    return
                time.sleep(0.2)
            raise RuntimeError("Replay did not finish within the demo timeout")


if __name__ == "__main__":
    main()
