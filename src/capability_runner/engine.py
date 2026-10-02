"""Orchestration and deterministic execution. Only discovery can construct a planner."""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Any
import uuid

from .control import ControlError, ControlGate
from .planner import Planner, PlannerError, make_planner
from .policy import Policy, PolicyViolation
from .profile import CAPABILITY_NAME, CHECKPOINT, HANDLERS, INPUTS, OUTPUTS, SCREENS, TARGETS, profile_digest, safe_goal
from .schema import Action, Candidate, Capability, Observation, RunResult, Step
from .settings import Settings
from .storage import AuditLog, Catalog, atomic_json
from .surface import BrowserSurface, Surface, SurfaceError


class StopRun(Exception):
    def __init__(self, code: str, business: bool = False):
        self.code, self.business = code, business
        super().__init__(code)


def check_artifact(capability: Capability, policy: Policy, origin: str) -> None:
    # Artifact content cannot self-authorize new selectors, egress, inputs, or risky controls.
    if (capability.name != CAPABILITY_NAME or capability.profile_digest != profile_digest()
            or capability.targets != TARGETS or capability.inputs != INPUTS or capability.outputs != OUTPUTS
            or capability.error_handlers != HANDLERS or capability.checkpoint != CHECKPOINT):
        raise ValueError("artifact does not match the reviewed binding and contract")
    screens = set(SCREENS.values())
    for index, step in enumerate(capability.steps):
        policy.check_action(step.action, origin)
        if step.after not in screens or step.before not in screens | {"any"}:
            raise ValueError("unknown checkpoint screen")
        if index and step.before != capability.steps[index - 1].after:
            raise ValueError("discontinuous step preconditions")
        if index and step.action.kind == "navigate":
            raise ValueError("this reviewed capability permits only its entry navigation")


@dataclass
class Run:
    id: str
    mode: str
    goal: str
    inputs: dict[str, Any]
    surface: Surface
    audit: AuditLog
    gate: ControlGate
    capability: Capability | None = None
    planner: Planner | None = None
    task: asyncio.Task | None = None
    result: RunResult | None = None
    observation: Observation | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    step: int = 0
    expected: str | None = None
    snapshots: int = 0
    recoveries: Counter = field(default_factory=Counter)
    finished_at: float | None = None

    async def view(self, include_outputs: bool = True) -> dict:
        control = await self.gate.view()
        result = self.result.model_dump() if self.result else None
        if result is not None and not include_outputs:
            result["outputs"] = {key: "[REDACTED]" for key in result["outputs"]}
        return {"run_id": self.id, "mode": self.mode, "capability": CAPABILITY_NAME,
                "session_id": self.surface.session_id, "step": self.step, "control": control,
                "status": self.result.status if self.result else control["state"].lower(),
                "observation": self.observation.model_dump() if self.observation else None,
                "result": result}


class RunManager:
    def __init__(self, settings: Settings, policy: Policy | None = None):
        self.settings = settings
        self.policy = policy or Policy.load(settings.policy_file)
        if settings.target_origin not in self.policy.allowed_origins:
            raise ValueError("TARGET_ORIGIN must be explicitly present in the reviewed policy")
        self.catalog = Catalog(settings.data_dir / "capabilities")
        self.runs: dict[str, Run] = {}

    def _prune(self) -> None:
        for run_id, run in list(self.runs.items()):
            if run.finished_at and (time.monotonic() - run.finished_at > 900 or len(self.runs) > 100):
                run.outputs.clear()
                if run.result:
                    run.result.outputs.clear()
                del self.runs[run_id]

    async def cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            self._prune()

    def get(self, run_id: str) -> Run:
        self._prune()
        return self.runs[run_id]

    def start(self, mode: str, inputs: dict[str, Any], target_url: str | None = None,
              goal: str = "", capability: Capability | None = None, planner: Planner | None = None) -> Run:
        self._prune()
        if sum(run.result is None for run in self.runs.values()) >= self.settings.max_active_runs:
            raise StopRun("CAPACITY_EXCEEDED")
        if set(inputs) != set(INPUTS) or any(not param.check(inputs[key]) for key, param in INPUTS.items()):
            raise ValueError("inputs do not match the reviewed capability contract")
        if mode not in {"discovery", "replay"}:
            raise ValueError("invalid run mode")
        if mode == "replay":
            if capability is None:
                raise ValueError("replay requires a capability")
            check_artifact(capability, self.policy, self.settings.target_origin)
        target_url = target_url or self.settings.default_target
        surface = BrowserSurface(self.settings, self.policy, target_url)
        run_id = uuid.uuid4().hex
        audit = AuditLog(self.settings.data_dir / "runs" / run_id, run_id)
        gate = ControlGate(audit, self.settings.human_lease_seconds, self.settings.intervention_timeout_seconds)
        run = Run(id=run_id, mode=mode, goal=safe_goal(goal, inputs), inputs=dict(inputs),
                  surface=surface, audit=audit, gate=gate, capability=capability, planner=planner)
        self.runs[run_id] = run
        run.task = asyncio.create_task(self._execute(run), name="run-" + run_id)
        return run

    async def _snapshot(self, run: Run) -> str:
        run.snapshots += 1
        name = f"snapshot-{run.snapshots:03d}.dom.json"
        try:
            state = await run.surface.snapshot()
        except Exception:
            state = {"format": "redacted-dom-v1", "state": "session_unavailable"}
        atomic_json(run.audit.directory / name, state)
        return name

    async def _handoff(self, run: Run, code: str) -> None:
        if run.gate.count >= 2:
            raise StopRun("UNRESOLVED_INTERVENTION")
        snapshot = await self._snapshot(run)
        context = {"code": code, "step": run.step, "capability": CAPABILITY_NAME,
                   "expected": run.expected, "snapshot": snapshot,
                   "session_id": run.surface.session_id,
                   "observation": run.observation.model_dump() if run.observation else None}
        await run.gate.pause(context)
        run.audit.emit("automation_rechecking", step=run.step, session_id=run.surface.session_id)

    async def _settle(self, run: Run, expected: str | None = None) -> Observation:
        start = time.monotonic()
        run.expected = expected
        while True:
            observation = await run.surface.observe()
            run.observation = observation
            if "network_denied" in observation.signals:
                await self._handoff(run, "NETWORK_POLICY_DENIED")
                start = time.monotonic()
                continue
            if not observation.app_version_ok:
                await self._handoff(run, "APP_VERSION_MISMATCH")
                start = time.monotonic()
                continue
            if any(control.matches > 1 for control in observation.controls):
                await self._handoff(run, "AMBIGUOUS_TARGET")
                start = time.monotonic()
                continue
            handler = next((item for item in HANDLERS if item.signal in observation.signals), None)
            if handler:
                snapshot = await self._snapshot(run)
                run.audit.emit("exceptional_state", code=handler.code, step=run.step,
                               signals=observation.signals, snapshot=snapshot)
                if handler.category == "business":
                    raise StopRun(handler.code, business=True)
                if handler.category == "recoverable" and run.recoveries[handler.signal] < self.policy.max_recoveries:
                    run.recoveries[handler.signal] += 1
                    run.audit.emit("recovery_action", target=handler.recovery_target,
                                   attempt=run.recoveries[handler.signal], code=handler.code)
                    try:
                        await run.surface.act(Action(kind="click", target=handler.recovery_target), run.inputs)
                    except (SurfaceError, PolicyViolation) as error:
                        await self._handoff(run, error.code)
                else:
                    await self._handoff(run, "RECOVERY_EXHAUSTED" if handler.category == "recoverable" else handler.code)
                start = time.monotonic()
                continue
            if observation.screen != "unknown" and (expected is None or observation.screen == expected):
                return observation
            if time.monotonic() - start >= self.settings.action_timeout_ms / 1000:
                await self._handoff(run, "CHECKPOINT_MISMATCH")
                start = time.monotonic()
            await asyncio.sleep(0.04)

    async def _perform(self, run: Run, action: Action, expected_after: str | None = None) -> Any:
        for attempt in range(3):
            run.audit.emit("action_started", step=run.step, action=action.kind, target=action.target,
                           parameter=action.parameter, output=action.output, actor="automation", attempt=attempt + 1)
            try:
                value = await run.surface.act(action, run.inputs)
                run.audit.emit("action_completed", step=run.step, action=action.kind, target=action.target)
                return value
            except PolicyViolation as error:
                if error.code == "HUMAN_APPROVAL_REQUIRED":
                    await self._handoff(run, error.code)
                else:
                    await self._snapshot(run)
                    raise StopRun(error.code) from error
            except SurfaceError as error:
                observation = await run.surface.observe()
                run.observation = observation
                # A navigation timeout may have committed the read-only transition. Never blindly click again.
                if expected_after and action.kind == "click" and observation.screen == expected_after:
                    return None
                safe_retry = action.kind == "navigate" or TARGETS[action.target].retry_safe
                if safe_retry and attempt == 0 and error.code in {"ACTION_TIMEOUT", "TARGET_MISSING", "SURFACE_ERROR"}:
                    run.audit.emit("action_retry", code=error.code, step=run.step, attempt=attempt + 1)
                    await asyncio.sleep(0.1)
                    continue
                await self._handoff(run, error.code)
            observation = await run.surface.observe()
            if expected_after and action.kind == "click" and observation.screen == expected_after:
                return None
        raise StopRun("ACTION_FAILED")

    @staticmethod
    def _accept_output(run: Run, action: Action, value: Any) -> None:
        if action.kind == "extract":
            if not OUTPUTS[action.output].check(value):
                raise StopRun("OUTPUT_VALIDATION_FAILED")
            run.outputs[action.output] = value

    @staticmethod
    def _candidates(run: Run, observation: Observation) -> list[Candidate]:
        candidates = []
        for control in observation.controls:
            target = TARGETS[control.key]
            if control.matches != 1 or not control.enabled or target.risk != "reversible":
                continue
            if target.action == "fill" and not control.populated:
                candidates.append(Candidate(id="fill_" + control.key, description="Enter the member_id input into Member number.",
                                            action=Action(kind="fill", target=control.key, parameter="member_id")))
            elif target.action == "click":
                candidates.append(Candidate(id="click_" + control.key, description="Click " + target.locators[0].value + ".",
                                            action=Action(kind="click", target=control.key)))
            elif target.action == "extract" and control.key not in run.outputs:
                candidates.append(Candidate(id="extract_" + control.key, description="Read the declared " + control.key + " output.",
                                            action=Action(kind="extract", target=control.key, output=control.key)))
        if observation.screen == CHECKPOINT.screen and set(run.outputs) == set(OUTPUTS):
            candidates.append(Candidate(id="finish", description="The required outputs are present; complete the capability."))
        candidates.append(Candidate(id="escalate", description="Request an operator because no safe action can achieve the goal."))
        # Stable alphabetical ordering, not the intended workflow ordering.
        return sorted(candidates, key=lambda candidate: candidate.id)

    async def _discover(self, run: Run) -> str:
        action = Action(kind="navigate", path="/legacy")
        await self._perform(run, action)
        observation = await self._settle(run, "search")
        steps = [Step(index=0, action=action, before="any", after=observation.screen)]
        run.planner = run.planner or make_planner(self.settings, run.audit)
        run.audit.emit("planner_configured", provider=run.planner.provider, model=run.planner.model)
        repetitions = Counter()
        for index in range(1, self.settings.max_steps + 1):
            run.step = index
            observation = await self._settle(run)
            candidates = self._candidates(run, observation)
            request = {"request_id": uuid.uuid4().hex, "goal": run.goal,
                       "observation": observation.model_dump(), "input_parameters": list(INPUTS),
                       "required_outputs": list(OUTPUTS), "collected_outputs": sorted(run.outputs),
                       "checkpoint": CHECKPOINT.model_dump(),
                       "history": [{"kind": step.action.kind, "target": step.action.target, "after": step.after} for step in steps[-8:]],
                       "candidates": [candidate.model_dump() for candidate in candidates]}
            try:
                decision = await run.planner.decide(request)
            except PlannerError as error:
                await self._handoff(run, error.code)
                continue
            selected = next((item for item in candidates if item.id == decision.candidate_id), None)
            if decision.request_id != request["request_id"] or selected is None:
                await self._handoff(run, "INVALID_MODEL_ACTION")
                continue
            run.audit.emit("model_decision", step=index, request_id=request["request_id"],
                           candidate_id=selected.id, reason=decision.reason, provider=run.planner.provider)
            if selected.id == "escalate":
                await self._handoff(run, "MODEL_REQUESTED_OPERATOR")
                continue
            if selected.id == "finish":
                await self._settle(run, CHECKPOINT.screen)
                capability = Capability(
                    name=CAPABILITY_NAME, revision=self.catalog.next_revision(CAPABILITY_NAME),
                    profile_digest=profile_digest(), inputs=INPUTS, outputs=OUTPUTS, targets=TARGETS,
                    steps=steps, checkpoint=CHECKPOINT, error_handlers=HANDLERS,
                )
                check_artifact(capability, self.policy, self.settings.target_origin)
                artifact_id = self.catalog.save(capability)
                atomic_json(run.audit.directory / "artifact.json", capability.model_dump())
                return artifact_id
            signature = (observation.digest, selected.id)
            repetitions[signature] += 1
            if repetitions[signature] > 2:
                await self._handoff(run, "DEAD_END")
                continue
            value = await self._perform(run, selected.action)
            self._accept_output(run, selected.action, value)
            after = await self._settle(run)
            steps.append(Step(index=len(steps), action=selected.action, before=observation.screen, after=after.screen))
        await self._handoff(run, "STEP_LIMIT")
        raise StopRun("STEP_LIMIT")

    async def _replay(self, run: Run) -> str:
        capability = run.capability
        for step in capability.steps:
            run.step = step.index
            if step.before != "any":
                await self._settle(run, step.before)
            value = await self._perform(run, step.action, step.after)
            self._accept_output(run, step.action, value)
            await self._settle(run, step.after)
        run.expected = capability.checkpoint.screen
        await self._settle(run, capability.checkpoint.screen)
        if set(run.outputs) != set(capability.outputs):
            raise StopRun("OUTPUTS_MISSING")
        return f"{capability.name}.v{capability.revision}"

    async def _execute(self, run: Run) -> None:
        start = time.monotonic()
        code, status, artifact = "INTERNAL_ERROR", "failure", None
        run.audit.emit("run_started", mode=run.mode, session_id=run.surface.session_id, profile_digest=profile_digest())
        try:
            async with asyncio.timeout(self.settings.run_timeout_seconds):
                await run.surface.start()
                artifact = await (self._discover(run) if run.mode == "discovery" else self._replay(run))
                status, code = "success", "OK"
        except StopRun as error:
            code = error.code
            status = "business_outcome" if error.business else "failure"
        except (ControlError, PolicyViolation, SurfaceError, PlannerError) as error:
            code = error.code
        except asyncio.TimeoutError:
            code = "RUN_TIMEOUT"
        except asyncio.CancelledError:
            code = "RUN_CANCELLED"
        except Exception as error:
            run.audit.emit("unexpected_error", code="INTERNAL_ERROR", error_type=type(error).__name__)
        finally:
            if status == "failure":
                snapshot = await self._snapshot(run)
                run.audit.emit("failure_evidence", code=code, step=run.step, snapshot=snapshot,
                               expected=run.expected, observed=(["screen:" + run.observation.screen] + run.observation.signals) if run.observation else [])
            result = RunResult(run_id=run.id, status=status, code=code,
                               outputs=dict(run.outputs) if status == "success" else {}, step=run.step,
                               expected=run.expected, observed=(["screen:" + run.observation.screen] + run.observation.signals) if run.observation else [],
                               llm_calls=run.planner.calls if run.planner else 0,
                               interventions=run.gate.count, artifact=artifact)
            await run.gate.finish()
            await run.surface.close()
            run.inputs.clear()
            run.goal = ""
            run.result, run.finished_at = result, time.monotonic()
            run.audit.emit("run_duration", duration_ms=round((time.monotonic() - start) * 1000))
            run.audit.finish(result)

    async def cancel(self, run_id: str) -> None:
        run = self.get(run_id)
        if run.result is None and run.task:
            # Serialize with any in-flight operator action before closing its page.
            await run.gate.finish()
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
            if run.result is None:
                # A task cancelled before its first scheduling turn never enters its finally block.
                run.inputs.clear()
                run.goal = ""
                run.result = RunResult(run_id=run.id, status="failure", code="RUN_CANCELLED")
                run.finished_at = time.monotonic()
                run.audit.emit("cancelled_before_start", code="RUN_CANCELLED")
                run.audit.finish(run.result)

    async def close(self) -> None:
        await asyncio.gather(*(self.cancel(run.id) for run in list(self.runs.values()) if run.result is None), return_exceptions=True)
        for run in self.runs.values():
            run.inputs.clear()
            run.outputs.clear()
            if run.result:
                run.result.outputs.clear()
