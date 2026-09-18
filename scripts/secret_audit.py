"""Inspect deliverable or Git-tracked paths without printing matched secret values."""

import re
import subprocess
from pathlib import Path


root = Path(__file__).resolve().parents[1]
ignored = {
    ".git",
    ".venv",
    "node_modules",
    "runtime",
    "artifacts",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
}
try:
    paths = [
        root / x
        for x in subprocess.check_output(
            ["git", "ls-files"], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).splitlines()
    ]
    mode = "Git-tracked files"
except subprocess.CalledProcessError:
    paths = [
        p
        for p in root.rglob("*")
        if p.is_file() and not any(part in ignored for part in p.relative_to(root).parts) and p.name != ".env"
    ]
    mode = "Deliverable source files (repository not initialized)"
patterns = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
]
problems = []
for path in paths:
    relative = path.relative_to(root)
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        problems.append(str(relative) + ": private environment file is tracked")
    if path.suffix.lower() in {".png", ".jpg", ".gif", ".zip", ".woff2"} or path.stat().st_size > 2_000_000:
        continue
    content = path.read_text(errors="ignore")
    for pattern in patterns:
        if pattern.search(content):
            problems.append(str(relative) + ": possible secret pattern")
print(mode)
if problems:
    print("\n".join(problems))
    raise SystemExit(1)
print(
    f"No private env paths or supported secret patterns found in {len(paths)} files. This is not a comprehensive secret scanner."
)
