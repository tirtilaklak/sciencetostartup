#!/usr/bin/env python3
"""Stage a reproducible editorial release from already reviewed work data.

This is not a source monitor or a deploy command. It never approves facts and
never writes to data/ or dist/. Review the staged diff before copying it in.
"""
import argparse
import hashlib
import json
from pathlib import Path

from editorial_work import prepare_editorial_release

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True, help="YYYY-MM-DD.N publication identity")
    parser.add_argument("--publication-as-of", required=True, help="Explicit UTC YYYY-MM-DDTHH:MM:SSZ; not a source review date")
    parser.add_argument("--work", type=Path, default=ROOT / "data/work-routes.json")
    parser.add_argument("--previous-release", type=Path, default=ROOT / "data/editorial-release.json")
    parser.add_argument("--output", type=Path, required=True, help="Separate empty staging directory")
    args = parser.parse_args()
    destination = args.output.resolve()
    if any(parent == destination or parent in destination.parents for parent in (ROOT / "data", ROOT / "dist")):
        parser.error("staging output cannot replace reviewed data or published files")
    if destination.exists() and any(destination.iterdir()):
        parser.error("staging output must be empty")
    canonical_path = ROOT / "data/canonical.json"
    work, release = prepare_editorial_release(
        json.loads(args.work.read_text()), json.loads(args.previous_release.read_text()),
        json.loads(canonical_path.read_text()), release_id=args.release_id,
        publication_as_of=args.publication_as_of,
        canonical_sha256=hashlib.sha256(canonical_path.read_bytes()).hexdigest())
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in (("work-routes.json", work), ("editorial-release.json", release)):
        (destination / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "staged_not_published", "release_id": release["release_id"],
                      "facts_approved": False, "output": str(destination), "work_routes_sha256": release["work_routes_sha256"]}))


if __name__ == "__main__":
    main()
