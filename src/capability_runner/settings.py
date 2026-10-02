"""Explicit environment configuration. Tokens have no insecure defaults."""
from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_target: str = "sandbox://legacy"
    target_origin: str = "http://127.0.0.1:8765"
    policy_file: Path = Path("config/policy.json")
    data_dir: Path = Path(".runtime")
    bridge_dir: Path = Path(".bridge")
    chromium_executable: str | None = None
    headless: bool = True
    action_timeout_ms: int = Field(default=3000, ge=100, le=30000)
    run_timeout_seconds: int = Field(default=180, ge=5, le=1800)
    intervention_timeout_seconds: int = Field(default=90, ge=1, le=900)
    human_lease_seconds: int = Field(default=60, ge=1, le=300)
    max_steps: int = Field(default=24, ge=1, le=50)
    max_active_runs: int = Field(default=4, ge=1, le=8)
    model_provider: str = "openai"
    model_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    model_api_key: SecretStr = SecretStr("")
    model_timeout_seconds: int = Field(default=45, ge=1, le=1200)
    runner_token: SecretStr = SecretStr("")
    operator_token: SecretStr = SecretStr("")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=False)
        values = {name: os.environ[name.upper()] for name in cls.model_fields if name.upper() in os.environ}
        if not values.get("chromium_executable"):
            values["chromium_executable"] = None
        return cls.model_validate(values)

    def check_api_tokens(self) -> None:
        caller = self.runner_token.get_secret_value()
        operator = self.operator_token.get_secret_value()
        if min(len(caller), len(operator)) < 32 or caller == operator:
            raise ValueError("Set two distinct random tokens of at least 32 characters; run scripts/init_env.py")
