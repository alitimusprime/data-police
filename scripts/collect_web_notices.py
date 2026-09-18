"""Collect installed production dependency notices alongside the distributable browser build."""

import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
packages = json.loads((root / "web/package-lock.json").read_text())["packages"]
sections = [
    "# Third-party browser dependency notices",
    "",
    "Generated from the locked, installed browser dependencies. Python dependencies are installed separately from requirements.lock and retain their packaged licenses.",
    "",
]
for key, metadata in sorted(packages.items()):
    if not key or (metadata.get("dev") and key != "node_modules/swagger-ui-dist"):
        continue
    folder = root / "web" / key
    if not folder.is_dir():
        raise SystemExit(f"Install the locked frontend dependencies first: {key}")
    name = key.split("node_modules/")[-1]
    sections += [
        f"## {name} {metadata.get('version', '')}",
        "",
        f"Declared license: {metadata.get('license', 'See package notices')}",
        "",
    ]
    notices = sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and (p.name.lower().startswith(("license", "notice", "copying")) or p.name.endswith(".LICENSE.txt"))
    )
    license_dir = folder / "licenses"
    if license_dir.is_dir():
        notices += sorted(p for p in license_dir.rglob("*") if p.is_file())
    for path in notices:
        sections += [
            f"### {path.relative_to(folder)}",
            "",
            "````text",
            path.read_text(errors="replace"),
            "````",
            "",
        ]
(root / "THIRD_PARTY_NOTICES.md").write_text("\n".join(sections) + "\n")
print("Browser dependency notices collected from the installed locked packages.")
