"""Typed release payload verification/extraction; does not build, execute or deploy."""

import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

MAX_FILES = 5000
MAX_BYTES = 512 * 1024 * 1024


def unpack(archive, destination, commit):
    archive, destination = Path(archive), Path(destination)
    if archive.is_symlink() or not archive.is_file() or destination.exists():
        raise ValueError("A regular archive and fresh destination are required")
    with tarfile.open(archive, "r:gz") as tar:
        entries = tar.getmembers()
        names = []
        if len(entries) > MAX_FILES or sum(e.size for e in entries) > MAX_BYTES:
            raise ValueError("Bundle exceeds reviewed limits")
        for entry in entries:
            path = PurePosixPath(entry.name)
            if (
                not entry.isfile()
                or path.is_absolute()
                or any(
                    part in ("", ".", "..") or not re.fullmatch(r"[A-Za-z0-9_.+-]+", part)
                    for part in path.parts
                )
                or "\\" in entry.name
                or Path(entry.name).name in ("COOKIE", ".cookie")
            ):
                raise ValueError("Unsafe bundle member")
            names.append(entry.name)
        if len(set(names)) != len(names) or names.count("manifest.json") != 1:
            raise ValueError("Duplicate paths or missing manifest")
        metadata = next(e for e in entries if e.name == "manifest.json")
        if metadata.size > 2 * 1024 * 1024:
            raise ValueError("Manifest too large")
        record = json.load(tar.extractfile(metadata))
        if (
            record.get("version") != 2
            or record.get("kind") != "liveview-bundle"
            or record.get("source_commit") != commit
            or record.get("worktree_dirty") is not False
            or record.get("beam_cookie_excluded") is not True
            or set(record.get("files", {})) != set(names) - {"manifest.json"}
        ):
            raise ValueError("Bundle source identity mismatch")
        destination.mkdir(parents=True, exist_ok=False)
        for entry in entries:
            data = tar.extractfile(entry).read()
            if (
                entry.name != "manifest.json"
                and hashlib.sha256(data).hexdigest() != record["files"][entry.name]
            ):
                raise ValueError("Bundle file digest mismatch")
            target = destination / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(data)
            target.chmod(0o755 if entry.mode & 0o111 else 0o644)
    wheels = list((destination / "engine").glob("*.whl"))
    if (
        len(wheels) != 1
        or not (destination / "engine/requirements-runtime.lock").is_file()
        or not (destination / "app/bin/pdf_control_web").is_file()
    ):
        raise ValueError("Incomplete runtime bundle")
    return {
        "kind": "liveview-bundle",
        "source_commit": commit,
        "file_count": len(entries),
        "wheel": str(wheels[0].relative_to(destination)),
        "files": record["files"],
    }
