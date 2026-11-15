"""Run whole unittest modules in deterministic shards and verify full coverage."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def discover(count):
    loader = unittest.TestLoader()
    tests = list(cases(loader.discover(str(ROOT / "tests"), pattern="test_*.py")))
    if loader.errors:
        raise ValueError("Unittest discovery failed: " + "\n".join(loader.errors))
    ids = [test.id() for test in tests]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Discovery must contain unique tests")
    modules = {}
    for test in tests:
        modules.setdefault(test.__class__.__module__, []).append(test)
    shards = [[] for _ in range(count)]
    sizes = [0] * count
    for name in sorted(modules, key=lambda name: (-len(modules[name]), name)):
        index = min(range(count), key=lambda index: (sizes[index], index))
        shards[index].append(name)
        sizes[index] += len(modules[name])
    return ids, modules, shards


def source_commit():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip():
        raise ValueError("Tracked source changed; shard receipts require a clean checkout")
    return commit


def run(index, count, output):
    commit = source_commit()
    ids, modules, shards = discover(count)
    selected = [test for name in shards[index] for test in modules[name]]
    expected = [test.id() for test in selected]
    completed = []

    class Result(unittest.TextTestResult):
        def stopTest(self, test):
            completed.append(test.id())
            super().stopTest(test)

    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(unittest.TestSuite(selected))
    unchanged = source_commit() == commit
    passed = (result.wasSuccessful() and not result.skipped and completed == expected and unchanged)
    receipt = {
        "schema_version": "unittest-shard-v1", "source_commit": commit,
        "source_commit_unchanged": unchanged,
        "index": index, "count": count, "all_test_ids": ids,
        "modules": shards[index], "expected_test_ids": expected,
        "completed_test_ids": completed, "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "unexpected_successes": len(result.unexpectedSuccesses),
        "passed": passed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0 if passed else 1


def verify(directory, count):
    commit = source_commit()
    expected, modules, shards = discover(count)
    paths = sorted(directory.glob("unit-shard-*.json"))
    if len(paths) != count:
        raise ValueError("Missing or extra shard receipts")
    receipts = [json.loads(path.read_bytes()) for path in paths]
    if (any(type(item.get("index")) is not int for item in receipts)
            or {item["index"] for item in receipts} != set(range(count))):
        raise ValueError("Missing or duplicate shard index")
    completed = []
    for item in receipts:
        selected = [test.id() for name in shards[item["index"]] for test in modules[name]]
        if (item.get("schema_version") != "unittest-shard-v1" or item["count"] != count
                or item["source_commit"] != commit or item["all_test_ids"] != expected
                or item.get("source_commit_unchanged") is not True
                or item["modules"] != shards[item["index"]] or item["expected_test_ids"] != selected
                or item["passed"] is not True or any(type(item[key]) is not int or item[key] != 0 for key in
                    ("failures", "errors", "skipped", "unexpected_successes"))
                or item["completed_test_ids"] != item["expected_test_ids"]
                or type(item["tests_run"]) is not int or item["tests_run"] != len(item["completed_test_ids"])):
            raise ValueError("Incomplete, failed or inconsistent shard")
        completed.extend(item["completed_test_ids"])
    if Counter(completed) != Counter(expected):
        raise ValueError("Tests were omitted or executed more than once")
    if source_commit() != commit:
        raise ValueError("Source commit changed during receipt verification")
    print(json.dumps({"status": "passed", "source_commit": commit,
                      "tests": len(expected), "shards": count, "exact_once_coverage": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "verify"))
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--index", type=int)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    if args.command == "run":
        if args.index is None or not 0 <= args.index < args.count or args.receipt is None:
            parser.error("run requires a valid --index and --receipt")
        return run(args.index, args.count, args.receipt)
    if args.directory is None:
        parser.error("verify requires --directory")
    verify(args.directory, args.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
