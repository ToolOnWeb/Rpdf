"""Bundle extraction rejects modified files, links and escaped paths."""
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_bundle", Path(__file__).parents[1] / "tools/release_bundle.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
COMMIT = "a" * 40


def make_bundle(path, extra=None, dirty=False, corrupt=False):
    files = {
        "app/bin/pdf_control_web": b"#!/bin/sh\nexit 0\n",
        "engine/demo.whl": b"test wheel",
        "engine/requirements-runtime.lock": b"test lock",
    }
    record = {
        "version": 2, "kind": "liveview-bundle", "source_commit": COMMIT,
        "worktree_dirty": dirty, "beam_cookie_excluded": True,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    if corrupt:
        files["engine/demo.whl"] = b"tampered"
    with tarfile.open(path, "w:gz") as archive:
        for name, data in {**files, "manifest.json": json.dumps(record).encode()}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            entry.mode = 0o755 if name.startswith("app/bin/") else 0o644
            archive.addfile(entry, io.BytesIO(data))
        if extra is not None:
            archive.addfile(extra, io.BytesIO(b"x") if extra.isfile() else None)


def test_valid_bundle_and_fresh_destination(tmp_path):
    archive = tmp_path / "bundle.tar.gz"
    make_bundle(archive)
    target = tmp_path / "out"
    result = module.unpack(archive, target, COMMIT)
    assert result["source_commit"] == COMMIT
    assert result["wheel"] == "engine/demo.whl"
    assert (target / "app/bin/pdf_control_web").stat().st_mode & 0o111
    with pytest.raises(ValueError):
        module.unpack(archive, target, COMMIT)


@pytest.mark.parametrize("name", ["../escape", "/escape", "app/COOKIE", "app/.cookie"])
def test_unsafe_members_rejected_before_writing(tmp_path, name):
    archive = tmp_path / "bundle.tar.gz"
    entry = tarfile.TarInfo(name)
    entry.size = 1
    make_bundle(archive, extra=entry)
    with pytest.raises(ValueError):
        module.unpack(archive, tmp_path / "out", COMMIT)
    assert not (tmp_path / "out").exists()


def test_symlinks_rejected(tmp_path):
    archive = tmp_path / "bundle.tar.gz"
    entry = tarfile.TarInfo("engine/link")
    entry.type = tarfile.SYMTYPE
    entry.linkname = "/etc/passwd"
    make_bundle(archive, extra=entry)
    with pytest.raises(ValueError):
        module.unpack(archive, tmp_path / "out", COMMIT)


@pytest.mark.parametrize("dirty,corrupt,commit", [
    (True, False, COMMIT), (False, True, COMMIT), (False, False, "b" * 40)
])
def test_unreviewed_or_changed_bundle_rejected(tmp_path, dirty, corrupt, commit):
    archive = tmp_path / "bundle.tar.gz"
    make_bundle(archive, dirty=dirty, corrupt=corrupt)
    with pytest.raises(ValueError):
        module.unpack(archive, tmp_path / "out", commit)
