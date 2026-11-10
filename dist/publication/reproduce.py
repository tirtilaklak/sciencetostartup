#!/usr/bin/env python3
"""Verify a downloaded research package and reproduce its public tables offline."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3


def from_rows(rows):
    result, collections = {}, {}
    for collection, position, kind, payload in rows:
        if int(position) == -1:
            collections[collection] = {"kind": kind, "values": {}}
        else:
            collections[collection]["values"][int(position)] = json.loads(payload)
    for collection, item in collections.items():
        values = [item["values"][index] for index in sorted(item["values"])]
        value = values if item["kind"] == "array" else values[0]
        if collection.startswith(("canonical.", "graph.")):
            namespace, name = collection.split(".", 1)
            result.setdefault(namespace, {})[name] = value
        else:
            result[collection] = value
    return result


def verify(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "MANIFEST.json").read_text())
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if directory not in path.parents or not path.is_file():
            raise ValueError("Missing or unsafe package file: " + name)
        blob = path.read_bytes()
        if len(blob) != expected["bytes"] or hashlib.sha256(blob).hexdigest() != expected["sha256"]:
            raise ValueError("Package checksum mismatch: " + name)
    projection = json.loads((directory / "clean-dataset.json").read_text())
    with (directory / "clean-dataset.csv").open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.reader(stream))[1:]
    with sqlite3.connect((directory / "clean-dataset.sqlite").as_uri() + "?mode=ro", uri=True) as database:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        sql_rows = database.execute("SELECT collection, position, kind, value_json FROM projection_rows ORDER BY collection,position").fetchall()
    if from_rows(csv_rows) != projection or from_rows(sql_rows) != projection:
        raise ValueError("JSON, CSV and SQLite disagree")
    # This module is shipped alongside the package. It uses only the standard library.
    from research_graph import validate_graph, coverage_summary
    validate_graph(projection["graph"])
    return {"status": "verified", "release_id": manifest["release_id"],
            "files_verified": len(manifest["files"]), "exports_equivalent": True,
            "coverage": coverage_summary(projection["graph"]),
            "provenance": "The public projection is verified. Original private raw inputs are not revalidated."}, projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--write-tables", type=Path)
    args = parser.parse_args()
    summary, projection = verify(args.directory)
    if args.write_tables:
        args.write_tables.mkdir(parents=True, exist_ok=True)
        (args.write_tables / "coverage.json").write_text(json.dumps(summary["coverage"], indent=2, sort_keys=True) + "\n")
        with (args.write_tables / "approved-assertions.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["id", "subject", "predicate", "object", "value", "qualifications"])
            for row in sorted(projection["graph"]["assertions"], key=lambda item: item["id"]):
                if row["status"] == "approved":
                    writer.writerow([row["id"], row["subject_id"], row["predicate"], row["object_id"] or "",
                                     json.dumps(row["value"], sort_keys=True), "; ".join(row["qualifications"])])
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
