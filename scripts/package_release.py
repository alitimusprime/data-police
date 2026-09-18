"""Package tracked source and the built interface, excluding credentials and runtime data."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=root.parent / "Data-Police-v0.1.0.zip")
    args = parser.parse_args()
    git_root = Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=root, text=True).strip()
    )
    if git_root != root:
        raise SystemExit("Initialize and stage this project's source before packaging.")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    files = {root / name for name in tracked if name}
    built = root / "web" / "dist"
    if not (built / "index.html").is_file():
        raise SystemExit("Build the interface before packaging: cd web, then npm ci and npm run build.")
    files.update(path for path in built.rglob("*") if path.is_file())
    forbidden = {
        ".git",
        ".venv",
        "node_modules",
        "runtime",
        "artifacts",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    }
    payload = {}
    for path in sorted(files):
        relative = path.relative_to(root)
        if any(part in forbidden for part in relative.parts) or path.is_symlink():
            raise SystemExit(f"Refusing unsafe release path: {relative}")
        if path.name.startswith(".env") and path.name != ".env.example":
            raise SystemExit("Refusing an environment file in the release")
        if path.suffix in {".db", ".sqlite", ".parquet", ".zip", ".tsbuildinfo"}:
            raise SystemExit(f"Refusing generated data: {relative}")
        payload[str(relative)] = path.read_bytes()
    manifest = {
        "product": "Data Police",
        "version": "0.1.0",
        "files": [
            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(payload.items())
        ],
    }
    payload["RELEASE_MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo("data-police/" + name, date_time=(2026, 9, 14, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():
            raise SystemExit("Archive integrity check failed")
        for item in manifest["files"]:
            if hashlib.sha256(archive.read("data-police/" + item["path"])).hexdigest() != item["sha256"]:
                raise SystemExit("Manifest checksum verification failed")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n")
    print(f"Created {output.name}: {len(payload)} files, {output.stat().st_size:,} bytes")
    print(
        "Archive integrity and every manifest checksum verified. No runtime data or environment file included."
    )


if __name__ == "__main__":
    main()
