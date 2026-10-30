"""Assemble one BEAM+wheel payload; no secrets, installation, publication or deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = """#!/usr/bin/env sh
set -eu
BUNDLE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
: "${SECRET_KEY_BASE:?Supply the deployment session secret}"
: "${PHX_HOST:?Supply the verified deployment hostname}"
export RELEASE_DISTRIBUTION=none
export RELEASE_COOKIE=unused-when-distribution-is-disabled
export PDF_CONTROL_ROOT="$BUNDLE/app"
export PDF_CONTROL_PYTHON="${PDF_CONTROL_PYTHON:-$BUNDLE/.venv/bin/python}"
export PHX_SERVER=true
exec "$BUNDLE/app/bin/pdf_control_web" start
"""


def assemble(target, *, wheel=None, commit=None, archive=None):
    target = Path(target).resolve()
    target.relative_to(ROOT)
    if target.exists():
        raise ValueError("Output exists; preserve it and choose a new output")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    if commit is not None and (commit != head or dirty):
        raise ValueError("Production payload requires the exact clean reviewed commit")
    release = ROOT / "web/_build/prod/rel/pdf_control_web"
    if not (release / "bin/pdf_control_web").is_file():
        raise ValueError("Build the BEAM release exactly once before packaging")
    target.mkdir(parents=True)
    shutil.copytree(release, target / "app", ignore=shutil.ignore_patterns("COOKIE", ".cookie"))
    shutil.copytree(ROOT / "src/pdf_control/static", target / "app/src/pdf_control/static")
    engine = target / "engine"
    engine.mkdir()
    if wheel:
        wheel = Path(wheel).resolve()
        if not wheel.is_file() or wheel.is_symlink() or not wheel.name.endswith(".whl"):
            raise ValueError("An already-built regular wheel is required")
        shutil.copyfile(wheel, engine / wheel.name)
    else:
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(engine)],
            cwd=ROOT,
            check=True,
        )
    shutil.copy2(ROOT / "requirements-runtime.lock", engine / "requirements-runtime.lock")
    for name in (
        "liveview_acceptance.py",
        "liveview_accuracy.py",
        "liveview_load.py",
        "liveview_release_probe.py",
    ):
        (target / "tools").mkdir(exist_ok=True)
        shutil.copyfile(ROOT / "tools" / name, target / "tools" / name)
    (target / "run.sh").write_text(LAUNCHER)
    files = {
        str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }
    record = {
        "version": 2,
        "kind": "liveview-bundle" if commit else "local-review-bundle",
        "source_commit": head,
        "worktree_dirty": dirty,
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "beam_cookie_excluded": True,
        "files": files,
    }
    (target / "manifest.json").write_text(json.dumps(record, sort_keys=True, indent=2))
    if archive:
        archive = Path(archive).resolve()
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists():
            raise ValueError("Archive already exists")
        with tarfile.open(archive, "x:gz", dereference=True) as tar:
            for path in sorted(target.rglob("*")):
                if path.is_file():
                    tar.add(path, arcname=str(path.relative_to(target)), recursive=False)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--commit")
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    result = assemble(args.output, wheel=args.wheel, commit=args.commit, archive=args.archive)
    print(
        json.dumps(
            {
                "source_commit": result["source_commit"],
                "kind": result["kind"],
                "files": len(result["files"]),
            }
        )
    )
