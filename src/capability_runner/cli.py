"""Small CLI: services, discovery, replay and artifact import/export."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import httpx
import uvicorn

from .schema import Capability
from .settings import Settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cu-runner")
    parser.add_argument("--api", default=None, help="Runner base URL; defaults to localhost RUNNER_PORT")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Start the authenticated runner and operator console")
    commands.add_parser("sandbox", help="Start the synthetic legacy HTML application")
    schema = commands.add_parser("schema", help="Export the JSON Schema")
    schema.add_argument("--out", default="docs/capability.schema.json")
    import_command = commands.add_parser("import", help="Import a reviewed artifact into the catalog")
    import_command.add_argument("path", type=Path)
    export = commands.add_parser("export")
    export.add_argument("capability")
    export.add_argument("--out", required=True, type=Path)
    for name in ("discover", "replay"):
        command = commands.add_parser(name)
        command.add_argument("--inputs", required=True, help="JSON object, or '-' to read JSON from stdin")
        command.add_argument("--target")
        command.add_argument("--no-wait", action="store_true")
        if name == "discover":
            command.add_argument("--goal", required=True)
        else:
            command.add_argument("--capability", default="read_savings_balance.v1")
    for name in ("status", "cancel"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    if args.command == "serve":
        from .api import create_api
        uvicorn.run(create_api(settings), host=os.getenv("RUNNER_HOST", "127.0.0.1"),
                    port=int(os.getenv("RUNNER_PORT", "8000")), access_log=False)
        return
    if args.command == "sandbox":
        from .sandbox import create_sandbox
        uvicorn.run(create_sandbox(), host=os.getenv("SANDBOX_HOST", "127.0.0.1"),
                    port=int(os.getenv("SANDBOX_PORT", "8765")), access_log=False)
        return
    if args.command == "schema":
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(Capability.model_json_schema(), indent=2) + "\n")
        print(str(path))
        return
    token = settings.runner_token.get_secret_value()
    if not token:
        parser.error("RUNNER_TOKEN is missing; run scripts/init_env.py")
    base = args.api or "http://127.0.0.1:" + os.getenv("RUNNER_PORT", "8000")
    try:
        with httpx.Client(base_url=base, headers={"Authorization": "Bearer " + token}, timeout=15) as client:
            def request(method: str, path: str, body=None):
                response = client.request(method, path, json=body)
                response.raise_for_status()
                return response.json()
            if args.command == "import":
                result = request("POST", "/api/capabilities", json.loads(args.path.read_text()))
            elif args.command == "export":
                result = request("GET", "/api/capabilities/" + args.capability)
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(result, indent=2) + "\n")
                result = {"path": str(args.out)}
            elif args.command in {"status", "cancel"}:
                result = request("GET" if args.command == "status" else "POST", "/api/runs/" + args.run_id + ("/cancel" if args.command == "cancel" else ""), {} if args.command == "cancel" else None)
            else:
                inputs = json.loads(sys.stdin.read() if args.inputs == "-" else args.inputs)
                body = {"inputs": inputs, "target": args.target}
                if args.command == "discover":
                    body["goal"] = args.goal
                    endpoint = "/api/discoveries"
                else:
                    body["capability"] = args.capability
                    endpoint = "/api/replays"
                result = request("POST", endpoint, body)
                run_id = result["run_id"]
                if not args.no_wait:
                    state = None
                    try:
                        while True:
                            status = request("GET", "/api/runs/" + run_id)
                            if status["result"] is not None:
                                result = status["result"]
                                break
                            if status["status"] != state:
                                state = status["status"]
                                print("run " + run_id + ": " + state, file=sys.stderr)
                            time.sleep(0.4)
                    except KeyboardInterrupt:
                        request("POST", "/api/runs/" + run_id + "/cancel", {})
                        raise SystemExit(130)
            print(json.dumps(result, indent=2))
            if result.get("status") in {"failure", "business_outcome"}:
                raise SystemExit(2 if result["status"] == "business_outcome" else 1)
    except (httpx.HTTPError, json.JSONDecodeError, OSError) as error:
        # Do not print request bodies, auth headers, parameter values or provider responses.
        print("Command failed: " + type(error).__name__ + ". Check service availability, schema and configuration.", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
