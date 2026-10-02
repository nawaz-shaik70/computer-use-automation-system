"""Single-owner live-session control, leased claims and idempotent operator actions."""
from __future__ import annotations

import asyncio
import hmac
import secrets
import time
from typing import Awaitable, Callable, Any

from .schema import Action
from .storage import AuditLog


class ControlError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ControlGate:
    def __init__(self, audit: AuditLog, lease_seconds: int, timeout_seconds: int):
        self.audit, self.lease_seconds, self.timeout_seconds = audit, lease_seconds, timeout_seconds
        self.lock = asyncio.Lock()
        self.state = "AUTOMATION"
        self.revision = 0
        self.lease = ""
        self.lease_until = 0.0
        self.intervention: dict | None = None
        self.count = 0
        self.event = asyncio.Event()
        self.idempotency: dict[str, tuple[dict, dict]] = {}

    def _expire(self) -> None:
        if self.state == "HUMAN" and time.monotonic() >= self.lease_until:
            self.state, self.lease = "PAUSED", ""
            self.revision += 1
            self.audit.emit("lease_expired", control=self.state, revision=self.revision)

    def _authorize(self, token: str, revision: int) -> None:
        self._expire()
        if self.state != "HUMAN" or revision != self.revision or not hmac.compare_digest(token, self.lease):
            raise ControlError("STALE_OR_UNAUTHORIZED_CONTROL")

    async def view(self) -> dict:
        async with self.lock:
            self._expire()
            return {"state": self.state, "revision": self.revision, "intervention": self.intervention,
                    "lease_remaining_seconds": max(0, round(self.lease_until - time.monotonic())) if self.state == "HUMAN" else 0}

    async def pause(self, context: dict) -> None:
        async with self.lock:
            if self.state != "AUTOMATION":
                raise ControlError("INVALID_PAUSE_TRANSITION")
            self.state = "PAUSED"
            self.revision += 1
            self.count += 1
            self.intervention = {"number": self.count, **context}
            self.event.clear()
            self.audit.emit("intervention_requested", control=self.state, revision=self.revision,
                            code=context["code"], step=context["step"], snapshot=context["snapshot"])
        try:
            await asyncio.wait_for(self.event.wait(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError as error:
            raise ControlError("INTERVENTION_TIMEOUT") from error
        async with self.lock:
            if self.state != "AUTOMATION":
                raise ControlError("RUN_CANCELLED")

    async def claim(self, revision: int) -> dict:
        async with self.lock:
            self._expire()
            if self.state != "PAUSED" or revision != self.revision:
                raise ControlError("CONTROL_ALREADY_CLAIMED_OR_STALE")
            self.state = "HUMAN"
            self.revision += 1
            self.lease = secrets.token_urlsafe(32)
            self.lease_until = time.monotonic() + self.lease_seconds
            self.idempotency.clear()
            self.audit.emit("control_claimed", control=self.state, revision=self.revision, actor="human")
            return {"revision": self.revision, "control_token": self.lease, "lease_seconds": self.lease_seconds}

    async def renew(self, token: str, revision: int) -> dict:
        async with self.lock:
            self._authorize(token, revision)
            self.lease_until = time.monotonic() + self.lease_seconds
            return {"revision": self.revision, "lease_seconds": self.lease_seconds}

    async def perform(self, token: str, revision: int, request_id: str, action: Action,
                      operation: Callable[[], Awaitable[Any]]) -> dict:
        async with self.lock:
            self._authorize(token, revision)
            if request_id in self.idempotency:
                old_action, response = self.idempotency[request_id]
                if old_action != action.model_dump():
                    raise ControlError("IDEMPOTENCY_CONFLICT")
                return response
            if len(self.idempotency) >= 100:
                raise ControlError("OPERATOR_ACTION_LIMIT")
            await operation()
            response = {"status": "applied", "request_id": request_id, "revision": self.revision}
            self.idempotency[request_id] = (action.model_dump(), response)
            self.audit.emit("human_action", action=action.kind, target=action.target, parameter=action.parameter,
                            request_id=request_id, actor="human", revision=self.revision)
            return response

    async def read_live(self, token: str, revision: int, operation: Callable[[], Awaitable[Any]]) -> Any:
        async with self.lock:
            self._authorize(token, revision)
            return await operation()

    async def resume(self, token: str, revision: int) -> dict:
        async with self.lock:
            self._authorize(token, revision)
            self.state, self.lease = "AUTOMATION", ""
            self.revision += 1
            self.intervention = None
            self.audit.emit("control_resumed", control=self.state, revision=self.revision, actor="human")
            self.event.set()
            return {"state": self.state, "revision": self.revision}

    async def finish(self) -> None:
        async with self.lock:
            self.state, self.lease = "FINISHED", ""
            self.revision += 1
            self.intervention = None
            self.event.set()
