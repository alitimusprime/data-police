"""Exercise first-run installation, generated credentials and the packaged UI in an isolated copy."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    environment = {key: value for key, value in os.environ.items() if not key.startswith("DP_")}
    with tempfile.TemporaryDirectory(prefix="data-police-install-") as directory:
        staged = Path(directory)
        for name in ("backend", "scripts", "migrations"):
            shutil.copytree(root / name, staged / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(root / "web/dist", staged / "web/dist")
        for name in ("alembic.ini", "pyproject.toml", ".env.example"):
            shutil.copy2(root / name, staged / name)
        subprocess.run(
            [sys.executable, "scripts/bootstrap.py", "--quiet"],
            cwd=staged,
            env=environment,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        config = dotenv_values(staged / ".env")
        with (staged / "startup.log").open("w+") as log:
            process = subprocess.Popen(
                [sys.executable, "scripts/start_local.py", "--no-schedule"],
                cwd=staged,
                env=environment,
                stdout=log,
                stderr=log,
            )
            try:
                with httpx.Client(base_url="http://127.0.0.1:8000", timeout=3, trust_env=False) as client:
                    for _ in range(120):
                        if process.poll() is not None:
                            raise RuntimeError("Local launcher stopped before readiness")
                        try:
                            if client.get("/api/health").status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.25)
                    else:
                        raise RuntimeError("Local launcher readiness timeout")
                    response = client.post(
                        "/api/auth/login",
                        headers={"X-DP-Request": "1"},
                        json={"email": config["DP_ADMIN_EMAIL"], "password": config["DP_ADMIN_PASSWORD"]},
                    )
                    assert response.status_code == 200, "Generated first-run credentials must work"
                    overview = client.get("/api/overview").json()
                    assert overview["stats"]["datasets"] == 19
                    assert overview["stats"]["healthy"] == 19
                    assert overview["stats"]["active_incidents"] == 0
                    assert len(overview["runs"]) == 12
                    assert client.get("/").status_code == 200
                    assert client.get("/api/docs").status_code == 200
                result = {
                    "status": "passed",
                    "checks": [
                        "Clean local installation and migration",
                        "Generated credentials accepted",
                        "Twelve measured baseline runs",
                        "Nineteen healthy datasets",
                        "Bundled product interface and API docs",
                    ],
                }
                (root / "artifacts").mkdir(exist_ok=True)
                (root / "artifacts/local-startup.json").write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result, indent=2))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
