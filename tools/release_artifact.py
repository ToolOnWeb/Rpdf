"""Verify a build-once artifact at each handoff; no rebuild or deployment."""

import hashlib
import json
import re
from pathlib import Path


def manifest(file, commit):
    p = Path(file)
    if (
        p.is_symlink()
        or not p.is_file()
        or not re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", p.name)
        or not re.fullmatch(r"[a-f0-9]{40}", commit)
    ):
        raise ValueError("Wheel and exact source commit required")
    return {
        "version": 1,
        "source_commit": commit,
        "file": p.name,
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }


def verify(directory, record, commit):
    if (
        set(record) != {"version", "source_commit", "file", "bytes", "sha256"}
        or record["version"] != 1
        or record["source_commit"] != commit
    ):
        raise ValueError("Artifact source identity mismatch")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", record["file"]):
        raise ValueError("Invalid artifact path")
    actual = manifest(Path(directory) / record["file"], commit)
    if actual != record:
        raise ValueError("Artifact content mismatch")
    return actual


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["create", "verify"])
    p.add_argument("path")
    p.add_argument("--commit", required=True)
    p.add_argument("--manifest", required=True)
    a = p.parse_args()
    if a.action == "create":
        result = manifest(a.path, a.commit)
        with Path(a.manifest).open("x") as stream:
            json.dump(result, stream, sort_keys=True)
    else:
        result = verify(a.path, json.loads(Path(a.manifest).read_text()), a.commit)
    print(json.dumps(result, sort_keys=True))
