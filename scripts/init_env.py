"""Generate local-only credentials without printing them or overwriting an existing .env."""
from pathlib import Path
import os
import secrets
import shutil

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env already exists; it was left unchanged.")
body = (root / ".env.example").read_text()
body = body.replace("RUNNER_TOKEN=\n", "RUNNER_TOKEN=" + secrets.token_urlsafe(32) + "\n")
body = body.replace("OPERATOR_TOKEN=\n", "OPERATOR_TOKEN=" + secrets.token_urlsafe(32) + "\n")
browser = shutil.which("chromium") or shutil.which("chromium-browser")
if browser:
    body = body.replace("CHROMIUM_EXECUTABLE=\n", "CHROMIUM_EXECUTABLE=" + browser + "\n")
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write(body)
print("Created .env with independent random caller/operator tokens. Tokens were not printed.")
