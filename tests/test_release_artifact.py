import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_artifact", Path(__file__).parents[1] / "tools" / "release_artifact.py"
)
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


def test_artifact_is_bound_to_source_commit_and_unchanged_bytes(tmp_path):
    wheel = tmp_path / "synthetic.whl"
    wheel.write_bytes(b"synthetic test artifact")
    record = artifact.manifest(wheel, "a" * 40)
    assert artifact.verify(tmp_path, record, "a" * 40) == record
    with pytest.raises(ValueError):
        artifact.verify(tmp_path, record, "b" * 40)
    wheel.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        artifact.verify(tmp_path, record, "a" * 40)


def test_artifact_manifest_cannot_escape_download_directory(tmp_path):
    wheel = tmp_path / "synthetic.whl"
    wheel.write_bytes(b"synthetic test artifact")
    record = artifact.manifest(wheel, "a" * 40)
    record["file"] = "../synthetic.whl"
    with pytest.raises(ValueError):
        artifact.verify(tmp_path, json.loads(json.dumps(record)), "a" * 40)
