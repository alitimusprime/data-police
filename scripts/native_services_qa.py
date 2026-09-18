"""Optional Linux CI helper: real PostgreSQL and Redis without a Docker daemon.

Install test-only tools first: pip install pgserver redislite
All server files are created in a new temporary directory. No existing database is used.
"""

import os
import pwd
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
import redislite
from pgserver._commands import POSTGRES_BIN_PATH


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    root = Path(__file__).resolve().parents[1]
    temporary = Path(tempfile.mkdtemp(prefix="dp-native-qa-"))
    postgres_dir = temporary / "postgres"
    postgres_dir.mkdir()
    subprocess_options = {}
    if os.getuid() == 0:
        unprivileged = pwd.getpwnam("nobody")
        temporary.chmod(0o755)
        os.chown(postgres_dir, unprivileged.pw_uid, unprivileged.pw_gid)
        subprocess_options = {"user": unprivileged.pw_uid, "group": unprivileged.pw_gid}
    pg_port, redis_port = port(), port()
    ctl = str(POSTGRES_BIN_PATH / "pg_ctl")
    subprocess.run(
        [
            str(POSTGRES_BIN_PATH / "initdb"),
            "-D",
            str(postgres_dir),
            "-U",
            "postgres",
            "--auth=trust",
            "--no-locale",
            "-E",
            "UTF8",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        **subprocess_options,
    )
    subprocess.run(
        [
            ctl,
            "-D",
            str(postgres_dir),
            "-l",
            str(postgres_dir / "server.log"),
            "-o",
            f"-p {pg_port} -h 127.0.0.1 -k {postgres_dir}",
            "-w",
            "start",
        ],
        check=True,
        **subprocess_options,
    )
    redis = None
    try:
        with psycopg.connect(f"postgresql://postgres@127.0.0.1:{pg_port}/postgres", autocommit=True) as conn:
            version = conn.execute("select version()").fetchone()[0]
            conn.execute("CREATE DATABASE datapolice_test")
        print("Testing:", version, flush=True)
        redis = redislite.Redis(
            str(temporary / "redis.db"), serverconfig={"port": str(redis_port), "bind": "127.0.0.1"}
        )
        assert redis.ping()
        url = f"postgresql+psycopg://postgres@127.0.0.1:{pg_port}/datapolice_test"
        env = os.environ | {
            "DP_TEST_DATABASE_URL": url,
            "DP_TEST_SOURCE_DATABASE_URL": url,
            "DP_TEST_REDIS_URL": f"redis://127.0.0.1:{redis_port}/0",
        }
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root, env=env)
        if result.returncode:
            raise SystemExit(result.returncode)
        # Tests leave the schema at head without an Alembic stamp; use a fresh database for migration validation.
        with psycopg.connect(f"postgresql://postgres@127.0.0.1:{pg_port}/postgres", autocommit=True) as conn:
            conn.execute("CREATE DATABASE datapolice_migration_test")
        migration_env = os.environ | {
            "DP_DATABASE_URL": f"postgresql+psycopg://postgres@127.0.0.1:{pg_port}/datapolice_migration_test"
        }
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=migration_env, check=True
        )
        subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=root, env=migration_env, check=True)
        print("PostgreSQL migrations and real Redis worker verified.", flush=True)
    finally:
        if redis:
            redis.shutdown()
        subprocess.run([ctl, "-D", str(postgres_dir), "-m", "fast", "-w", "stop"], **subprocess_options)


if __name__ == "__main__":
    main()
