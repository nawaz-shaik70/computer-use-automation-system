"""Reviewed vendor binding. Locators are not invented by the model at execution time.

The ordering below is NOT a workflow: all visible controls are offered to discovery.
The model must choose the next action, a parameter binding, and when to finish.
"""
import hashlib
import json
import re

from .schema import Checkpoint, ErrorHandler, LocatorSpec, Parameter, TargetSpec


def role(name: str, kind: str) -> LocatorSpec:
    return LocatorSpec(strategy="role", value=name, role=kind)


def text(name: str) -> LocatorSpec:
    return LocatorSpec(strategy="text", value=name)


def control(name: str, kind: str = "link", risk: str = "reversible") -> TargetSpec:
    return TargetSpec(
        locators=[role(name, kind), text(name)], action="click", risk=risk,
        purpose="Exact accessible name, then exact visible text; ambiguous matches fail closed.",
    )


def signal(name: str) -> TargetSpec:
    return TargetSpec(locators=[text(name)], action="signal", purpose="Exact reviewed status text.")


TARGETS = {
    "member_number": TargetSpec(
        locators=[LocatorSpec(strategy="label", value="Member number"),
                  LocatorSpec(strategy="table_input", value="Member number")],
        action="fill", purpose="Label preferred; legacy fallback anchors a unique row label to its input.",
    ),
    "search": control("Search", "button"),
    "open_member": control("Open member"),
    "view_accounts": control("View accounts"),
    "savings": control("Savings"),
    "balance": TargetSpec(
        locators=[LocatorSpec(strategy="table_value", value="Available balance")],
        action="extract", purpose="Unique row label and adjacent value cell; no dynamic IDs or coordinates.",
    ),
    "currency": TargetSpec(
        locators=[LocatorSpec(strategy="table_value", value="Currency")],
        action="extract", purpose="Read the value adjacent to a unique static row label.",
    ),
    "continue_notice": control("Continue", "button"),
    "retry_load": control("Retry", "button"),
    "restore_session": control("Restore session", "button", "human_only"),
    "acknowledge_warning": control("Acknowledge warning", "button", "human_only"),
    "close_account": control("Close account", "button", "forbidden"),
    "search_screen": signal("Member lookup"),
    "results_screen": signal("Search results"),
    "member_screen": signal("Member overview"),
    "accounts_screen": signal("Member accounts"),
    "savings_screen": signal("Savings account"),
    "not_found": signal("No such member"),
    "invalid_member": signal("Invalid member number"),
    "permission_denied": signal("Permission denied"),
    "session_expired": signal("Session expired"),
    "maintenance_notice": signal("Maintenance notice"),
    "transient_load": signal("Service temporarily unavailable"),
    "unexpected_dialog": signal("Unexpected confirmation"),
    "version_marker": TargetSpec(
        frames=[], locators=[text("Legacy Servicing / version 1")], action="signal",
        purpose="Fail closed if the reviewed vendor version is not present.",
    ),
}

SCREENS = {
    "search_screen": "search", "results_screen": "results", "member_screen": "member",
    "accounts_screen": "accounts", "savings_screen": "savings",
}
HANDLERS = [
    ErrorHandler(signal="not_found", category="business", code="NOT_FOUND"),
    ErrorHandler(signal="invalid_member", category="business", code="VALIDATION_ERROR"),
    ErrorHandler(signal="permission_denied", category="hard", code="PERMISSION_DENIED"),
    ErrorHandler(signal="maintenance_notice", category="recoverable", code="NOTICE", recovery_target="continue_notice"),
    ErrorHandler(signal="transient_load", category="recoverable", code="TRANSIENT_LOAD", recovery_target="retry_load"),
    ErrorHandler(signal="session_expired", category="intervention", code="SESSION_EXPIRED"),
    ErrorHandler(signal="unexpected_dialog", category="intervention", code="UNEXPECTED_DIALOG"),
]
INPUTS = {"member_id": Parameter(type="string", pattern=r"\d{5}", description="Five-digit member identifier; never stored.")}
OUTPUTS = {
    "balance": Parameter(type="decimal", pattern=r"-?\d+\.\d{2}", description="Decimal monetary amount represented as a string."),
    "currency": Parameter(type="string", enum=["USD"], sensitive=False, description="ISO currency code."),
}
CHECKPOINT = Checkpoint(screen="savings", required_outputs=["balance", "currency"])
CAPABILITY_NAME = "read_savings_balance"
SAFE_TEXT = frozenset(
    [loc.value for target in TARGETS.values() for loc in target.locators]
    + ["Member number", "Available balance", "Currency", "USD", "Synthetic data only", "Legacy workspace"]
)


def profile_digest() -> str:
    body = {"targets": {k: v.model_dump() for k, v in TARGETS.items()},
            "handlers": [h.model_dump() for h in HANDLERS],
            "inputs": {k: v.model_dump() for k, v in INPUTS.items()},
            "outputs": {k: v.model_dump() for k, v in OUTPUTS.items()},
            "checkpoint": CHECKPOINT.model_dump()}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


# Keep free-form goals out of model egress and persisted evidence unless every token is reviewed.
# Values belong in typed inputs. Unknown words (including names) are removed, never guessed as safe.
GOAL_WORDS = frozenset("look lookup up find search member the using identified by supplied parameter member_id and read get return their current available savings account balance currency for please of a an this show fetch retrieve number id in from".split())


def safe_goal(goal: str, inputs: dict) -> str:
    for value in inputs.values():
        if isinstance(value, str) and value:
            goal = goal.replace(value, "member_id")
    words = re.findall(r"[A-Za-z_]+|[^\sA-Za-z_]+", goal.lower())
    return " ".join(word if word in GOAL_WORDS else "[REDACTED]" for word in words)[:1200]
