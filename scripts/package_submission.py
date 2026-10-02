"""Package the reviewed source/evidence allowlist, excluding runtime data and secrets."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import zipfile

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "ahmed-nawaz-shaik-computer-use-automation-take-home-assessment.zip"
TOP_FILES = {"README.md", "REPORT.md", "REQUIREMENTS.md", "pyproject.toml", "requirements.txt",
             "requirements-dev.txt", ".env.example", ".gitignore"}
TOP_DIRS = {"config", "src", "scripts", "tests", "docs", "evidence", ".github"}
EXCLUDED = {"__pycache__", ".pytest_cache", ".runtime", ".bridge", ".venv", "build", "dist", "node_modules"}
SUFFIXES = {".py", ".json", ".jsonl", ".md", ".txt", ".xml", ".html", ".css", ".js", ".yml", ".yaml", ".toml", ".png"}


def main() -> None:
    local_env = dotenv_values(ROOT / ".env")
    secrets = [local_env.get(key) for key in ("RUNNER_TOKEN", "OPERATOR_TOKEN", "MODEL_API_KEY")]
    secrets = [value.encode() for value in secrets if value and len(value) >= 16]
    files: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if path.is_symlink() or not path.is_file():
            continue
        if any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts):
            continue
        allowed = relative.as_posix() in TOP_FILES or (relative.parts[0] in TOP_DIRS and path.suffix in SUFFIXES)
        if not allowed:
            continue
        content = path.read_bytes()
        if any(secret in content for secret in secrets):
            raise SystemExit("Local secret found in " + relative.as_posix())
        if re.search(rb"sk-[a-zA-Z0-9_-]{24,}", content) or (b"-----BEGIN " + b"PRIVATE KEY-----") in content:
            raise SystemExit("Potential credential found in " + relative.as_posix())
        files.append(path)
    for required in ("README.md", "REPORT.md", "REQUIREMENTS.md", "evidence/example-capability.json", "docs/VERIFICATION.md"):
        if ROOT / required not in files:
            raise SystemExit("Missing required deliverable: " + required)
    manifest = ROOT / "SUBMISSION_MANIFEST.sha256"
    manifest.write_text("".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.relative_to(ROOT).as_posix() + "\n" for path in files))
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files + [manifest]:
            archive.write(path, arcname=ROOT.name + "/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None, "ZIP integrity check failed"
        assert all(not name.endswith("/.env") for name in archive.namelist())
    print(f"Packaged {len(files) + 1} files; ZIP integrity and local-secret checks passed.")
    print(str(OUTPUT))


if __name__ == "__main__":
    main()
