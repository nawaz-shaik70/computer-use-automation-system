"""Atomic JSON artifacts and allowlisted, value-free audit records."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
from typing import Any

from .schema import Capability, RunResult


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Catalog:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, artifact_id: str) -> Path:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}\.v[1-9][0-9]*", artifact_id) is None:
            raise ValueError("invalid capability id")
        return self.root / (artifact_id + ".json")

    def save(self, capability: Capability) -> str:
        artifact_id = f"{capability.name}.v{capability.revision}"
        path = self.path(artifact_id)
        if path.exists():
            if Capability.model_validate_json(path.read_text()) != capability:
                raise ValueError("immutable capability revision already exists")
            return artifact_id
        # The single-process manager serializes revision assignment and saves without awaits.
        atomic_json(path, capability.model_dump())
        return artifact_id

    def load(self, artifact_id: str) -> Capability:
        path = self.path(artifact_id)
        if path.is_symlink() or path.stat().st_size > 1_000_000:
            raise ValueError("invalid capability file")
        return Capability.model_validate_json(path.read_text())

    def all(self) -> list[Capability]:
        result = []
        for path in sorted(self.root.glob("*.json")):
            result.append(self.load(path.stem))
        return result

    def next_revision(self, name: str) -> int:
        return 1 + max((item.revision for item in self.all() if item.name == name), default=0)


# Deliberately no generic logger.info(str(exception)), request body, goal, input, or output fields.
AUDIT_FIELDS = frozenset({
    "mode", "step", "action", "target", "parameter", "output", "screen", "signals",
    "code", "expected", "observed", "actor", "revision", "request_id", "candidate_id",
    "reason", "provider", "model", "llm_calls", "attempt", "snapshot", "artifact",
    "status", "interventions", "control", "session_id", "profile_digest", "duration_ms",
    "error_type", "prompt_tokens", "completion_tokens", "recovery", "transport",
})


class AuditLog:
    def __init__(self, directory: Path, run_id: str):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "events.jsonl"
        self.run_id = run_id
        self.sequence = 0
        self.previous = "0" * 64

    def emit(self, event: str, **data: Any) -> None:
        if set(data) - AUDIT_FIELDS:
            raise ValueError("unapproved audit field")
        self.sequence += 1
        record = {"sequence": self.sequence, "timestamp": now(), "run_id": self.run_id,
                  "event": event, "previous_hash": self.previous, **data}
        digest = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        record["hash"] = digest
        self.previous = digest
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as file:
            file.write(json.dumps(record, sort_keys=True) + "\n")

    def finish(self, result: RunResult) -> None:
        self.emit("run_finished", status=result.status, code=result.code, llm_calls=result.llm_calls,
                  interventions=result.interventions, artifact=result.artifact)
        safe = result.model_dump()
        # All outputs are withheld in evidence, even non-sensitive schema members.
        safe["outputs"] = {key: "[REDACTED]" for key in result.outputs}
        atomic_json(self.directory / "result.json", safe)


def verify_chain(path: Path) -> bool:
    previous = "0" * 64
    for sequence, line in enumerate(path.read_text().splitlines(), 1):
        record = json.loads(line)
        digest = record.pop("hash")
        if record["sequence"] != sequence or record["previous_hash"] != previous:
            return False
        if hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest() != digest:
            return False
        previous = digest
    return True
