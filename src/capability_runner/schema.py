"""The serialized capability is the contract, not an LLM conversation."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Parameter(StrictModel):
    type: Literal["string", "integer", "boolean", "decimal"]
    description: str = Field(max_length=160)
    sensitive: bool = True
    pattern: str | None = None
    enum: list[str] | None = None

    def check(self, value: Any) -> bool:
        if self.type == "integer":
            return type(value) is int
        if self.type == "boolean":
            return type(value) is bool
        if not isinstance(value, str) or len(value) > 256:
            return False
        if self.pattern and re.fullmatch(self.pattern, value) is None:
            return False
        if self.enum is not None and value not in self.enum:
            return False
        if self.type == "decimal":
            try:
                return Decimal(value).is_finite()
            except InvalidOperation:
                return False
        return True


class LocatorSpec(StrictModel):
    strategy: Literal["label", "role", "text", "table_input", "table_value"]
    value: str = Field(min_length=1, max_length=120)
    role: Literal["button", "link", "textbox", "heading"] | None = None

    @model_validator(mode="after")
    def role_required(self) -> LocatorSpec:
        if (self.strategy == "role") != (self.role is not None):
            raise ValueError("role is required only for a role locator")
        return self


class TargetSpec(StrictModel):
    frames: list[str] = Field(default_factory=lambda: ["Legacy workspace"])
    locators: list[LocatorSpec] = Field(min_length=1, max_length=3)
    purpose: str = Field(max_length=200)
    risk: Literal["reversible", "human_only", "forbidden"] = "reversible"
    retry_safe: bool = True
    action: Literal["click", "fill", "extract", "signal"]


class Action(StrictModel):
    kind: Literal["navigate", "click", "fill", "extract"]
    target: Slug | None = None
    parameter: Slug | None = None
    output: Slug | None = None
    path: str | None = None

    @model_validator(mode="after")
    def shape(self) -> Action:
        present = {k for k in ("target", "parameter", "output", "path") if getattr(self, k) is not None}
        required = {
            "navigate": {"path"}, "click": {"target"},
            "fill": {"target", "parameter"}, "extract": {"target", "output"},
        }[self.kind]
        if present != required:
            raise ValueError("action fields do not match action kind")
        return self


class Step(StrictModel):
    index: int = Field(ge=0)
    action: Action
    before: str
    after: str


class Checkpoint(StrictModel):
    screen: Slug
    required_outputs: list[Slug] = Field(min_length=1)


class ErrorHandler(StrictModel):
    signal: Slug
    category: Literal["business", "recoverable", "hard", "intervention"]
    code: str = Field(pattern=r"^[A-Z_]{1,64}$")
    recovery_target: Slug | None = None


class Capability(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    name: Slug
    revision: int = Field(ge=1)
    app_family: Literal["legacy-servicing"] = "legacy-servicing"
    app_version: Literal["1"] = "1"
    profile_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    entry_path: Literal["/legacy"] = "/legacy"
    inputs: dict[Slug, Parameter]
    outputs: dict[Slug, Parameter]
    targets: dict[Slug, TargetSpec]
    steps: list[Step] = Field(min_length=2, max_length=50)
    checkpoint: Checkpoint
    error_handlers: list[ErrorHandler]

    @model_validator(mode="after")
    def consistent(self) -> Capability:
        if [s.index for s in self.steps] != list(range(len(self.steps))):
            raise ValueError("step indexes must be contiguous")
        if self.steps[0].action != Action(kind="navigate", path=self.entry_path):
            raise ValueError("first step must navigate to the entry point")
        extracted = []
        for step in self.steps:
            action = step.action
            if action.target is not None and action.target not in self.targets:
                raise ValueError("unknown target reference")
            if action.parameter is not None and action.parameter not in self.inputs:
                raise ValueError("unknown input reference")
            if action.output is not None:
                if action.output not in self.outputs:
                    raise ValueError("unknown output reference")
                extracted.append(action.output)
        if set(extracted) != set(self.outputs) or len(extracted) != len(set(extracted)):
            raise ValueError("each output must have exactly one extraction step")
        if set(self.checkpoint.required_outputs) != set(self.outputs):
            raise ValueError("checkpoint must require all outputs")
        return self

    def validate_inputs(self, values: dict[str, Any]) -> None:
        if set(values) != set(self.inputs):
            raise ValueError("input names do not match contract")
        if any(not parameter.check(values[key]) for key, parameter in self.inputs.items()):
            raise ValueError("input types or constraints do not match contract")


class ControlObservation(StrictModel):
    key: Slug
    matches: int
    enabled: bool
    populated: bool = False


class Observation(StrictModel):
    screen: str
    signals: list[Slug]
    controls: list[ControlObservation]
    digest: str
    app_version_ok: bool = True


class Candidate(StrictModel):
    id: Slug
    description: str
    action: Action | None = None


class Decision(StrictModel):
    request_id: str
    candidate_id: Slug
    reason: Literal["supply_input", "advance", "read_output", "goal_complete", "request_operator"]


class RunResult(StrictModel):
    run_id: str
    status: Literal["success", "business_outcome", "failure"]
    code: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    step: int | None = None
    expected: str | None = None
    observed: list[str] = Field(default_factory=list)
    llm_calls: int = 0
    interventions: int = 0
    artifact: str | None = None
