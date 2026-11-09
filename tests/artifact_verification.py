"""Verify editable-source provenance and every deterministic build output."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import build


def verify_artifact(destination, source_paths=()):
    destination = Path(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    for name in source_paths:
        expected = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert manifest["source_sha256"].get(name) == expected, "Build source provenance differs: " + name
    with tempfile.TemporaryDirectory(prefix="verify-frontend-") as temporary:
        fresh = Path(temporary)
        build(json.loads((ROOT / "data/canonical.json").read_text()), fresh)
        expected = json.loads((fresh / "manifest.json").read_text())
        assert manifest == expected, "Built manifest differs from a fresh deterministic build"
        for name, digest in expected["sha256"].items():
            actual = destination / name
            assert actual.is_file() and hashlib.sha256(actual.read_bytes()).hexdigest() == digest, "Built output differs from a fresh deterministic build: " + name
    return manifest
