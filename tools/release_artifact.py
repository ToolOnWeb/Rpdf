"""Build-once payload identity: legacy wheels and typed bundles."""

import hashlib
import json
import re
from pathlib import Path


def manifest(file, commit):
    path = Path(file)
    if path.is_symlink() or not path.is_file() or not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("A regular payload and exact source commit are required")
    if re.fullmatch(r"[A-Za-z0-9_.-]+\.whl", path.name):
        version, kind = 1, None
    elif re.fullmatch(r"[A-Za-z0-9_.-]+\.tar\.gz", path.name):
        version, kind = 2, "liveview-bundle"
    else:
        raise ValueError("Unsupported payload type")
    value = {
        "version": version,
        "source_commit": commit,
        "file": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    if kind:
        value["kind"] = kind
    return value


def verify(directory, record, commit):
    expected = {"version", "source_commit", "file", "bytes", "sha256"}
    if record.get("version") == 2:
        expected.add("kind")
        if record.get("kind") != "liveview-bundle":
            raise ValueError("Unsupported artifact kind")
    if set(record) != expected or record.get("version") not in (1, 2):
        raise ValueError("Invalid artifact record")
    name = record["file"]
    if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("Invalid artifact path")
    actual = manifest(Path(directory) / name, commit)
    if actual != record:
        raise ValueError("Artifact source/content mismatch")
    return actual


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["create", "verify"])
    parser.add_argument("path")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    if args.action == "create":
        result = manifest(args.path, args.commit)
        with Path(args.manifest).open("x") as stream:
            json.dump(result, stream, sort_keys=True)
    else:
        result = verify(args.path, json.loads(Path(args.manifest).read_text()), args.commit)
    print(json.dumps(result, sort_keys=True))
