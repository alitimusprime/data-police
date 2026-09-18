"""Generate local-only secrets without replacing an existing environment."""

import argparse
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    if target.exists():
        print("Existing .env preserved.")
        return
    password = secrets.token_urlsafe(18)
    replacements = {
        "DP_ADMIN_PASSWORD": password,
        "DP_SESSION_SECRET": secrets.token_urlsafe(48),
        "POSTGRES_PASSWORD": secrets.token_hex(24),
        "REDIS_PASSWORD": secrets.token_hex(24),
    }
    lines = []
    for line in (root / ".env.example").read_text().splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={replacements[key]}" if key in replacements else line)
    target.write_text("\n".join(lines) + "\n")
    target.chmod(0o600)
    (root / "runtime").mkdir(exist_ok=True)
    print("Local configuration created. Keep .env private.")
    if not options.quiet:
        print("Sign-in email: admin@datapolice.local")
        print("Sign-in password:", password)


if __name__ == "__main__":
    main()
