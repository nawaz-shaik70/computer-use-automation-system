"""Deny by default at both the action and browser-network boundaries."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pydantic import Field

from .profile import TARGETS
from .schema import Action, StrictModel


class PolicyViolation(Exception):
    def __init__(self, code: str = "POLICY_DENIED"):
        self.code = code
        super().__init__(code)


class Policy(StrictModel):
    version: int
    allowed_origins: list[str]
    allowed_routes: dict[str, list[str]]
    allowed_actions: list[str]
    allowed_query: dict[str, list[str]] = Field(default_factory=dict)
    max_recoveries: int = Field(default=2, ge=0, le=5)

    @classmethod
    def load(cls, path: Path) -> "Policy":
        return cls.model_validate_json(path.read_text())

    def allows_url(self, url: str, method: str = "GET") -> bool:
        try:
            parsed = urlsplit(url)
            if parsed.scheme == "sandbox":
                if "sandbox://legacy" not in self.allowed_origins or parsed.netloc != "legacy" or parsed.path or parsed.fragment or method != "GET":
                    return False
                query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                return all(len(values) == 1 and values[0] in self.allowed_query.get(key, []) for key, values in query.items())
            if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
                return False
            if "\\" in url or "%" in parsed.path or ".." in parsed.path or "//" in parsed.path:
                return False
            if parsed.fragment or parsed.port is None:
                # This demo policy deliberately requires explicit ports, even for remote profiles.
                return False
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in self.allowed_origins or method not in self.allowed_routes.get(parsed.path, []):
                return False
            query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
            return all(len(values) == 1 and values[0] in self.allowed_query.get(key, []) for key, values in query.items())
        except (ValueError, TypeError):
            return False

    def check_action(self, action: Action, origin: str, actor: str = "automation") -> None:
        if action.kind not in self.allowed_actions:
            raise PolicyViolation()
        if action.kind == "navigate":
            if not action.path or not action.path.startswith("/") or action.path.startswith("//"):
                raise PolicyViolation()
            if not self.allows_url(origin + action.path):
                raise PolicyViolation()
            return
        target = TARGETS.get(action.target)
        if target is None or target.action != action.kind:
            raise PolicyViolation()
        if target.risk == "forbidden":
            raise PolicyViolation("IRREVERSIBLE_BLOCKED")
        if target.risk == "human_only" and actor != "human":
            raise PolicyViolation("HUMAN_APPROVAL_REQUIRED")
        if action.kind == "fill" and (action.target, action.parameter) != ("member_number", "member_id"):
            raise PolicyViolation("PARAMETER_BINDING_DENIED")
        if action.kind == "extract" and action.target != action.output:
            raise PolicyViolation("OUTPUT_BINDING_DENIED")
