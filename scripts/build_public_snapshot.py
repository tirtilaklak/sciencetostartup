#!/usr/bin/env python3
"""Rebuild the reviewed public snapshot without importing private research inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from observatory import ROOT, build


def verify(destination, dist=ROOT / "dist"):
    expected = json.loads((dist / "manifest.json").read_text())
    actual = json.loads((destination / "manifest.json").read_text())
    if actual != expected:
        raise SystemExit("Rebuilt manifest differs from the checked-in public release.")
    for name, digest in expected["sha256"].items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Rebuilt public payload differs: " + name)
    deployed = {path.relative_to(dist).as_posix(): path for path in dist.rglob("*") if path.is_file()}
    for name, digest in expected["sha256"].items():
        if name in deployed and hashlib.sha256(deployed[name].read_bytes()).hexdigest() != digest:
            raise SystemExit("Deployed file differs from the manifest: " + name)
    extra = sorted(set(deployed) - set(expected["sha256"]) - {"manifest.json"})
    missing = sorted(set(expected["sha256"]) - set(deployed))
    if extra or missing:
        raise SystemExit("Deployed files differ from the manifest.\nExtra: " + (", ".join(extra) or "none") +
                         "\nMissing: " + (", ".join(missing) or "none"))
    print(json.dumps({"status": "passed", "payloads": len(expected["sha256"]), "deployed_files": len(deployed),
                      "dataset_version": expected["dataset_version"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/public-snapshot")
    parser.add_argument("--verify", action="store_true",
                        help="Build in a temporary directory, compare it with dist/manifest.json, "
                             "then check every file in dist/ against that manifest.")
    args = parser.parse_args()
    data = json.loads((ROOT / "data/canonical.json").read_text())
    if args.verify:
        with tempfile.TemporaryDirectory(prefix="sciencetostartup-public-") as temporary:
            destination = Path(temporary)
            build(data, destination)
            verify(destination)
    else:
        destination = args.output.resolve()
        if destination == ROOT / "dist" or destination in (ROOT, ROOT / "data", ROOT / "web"):
            raise SystemExit("Choose a separate output directory; the reviewed snapshot stays unchanged.")
        if destination.exists() and any(destination.iterdir()):
            raise SystemExit("Output directory must be empty.")
        build(data, destination)
        print(json.dumps({"status": "built", "output": str(destination)}))


if __name__ == "__main__":
    main()
