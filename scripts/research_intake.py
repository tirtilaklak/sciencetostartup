#!/usr/bin/env python3
"""Run bounded, restartable discovery partitions; never approve research facts."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from check_research_sources import ADAPTER_HOSTS, PublicClient, discover, safe_output, write_json

ROOT = Path(__file__).resolve().parents[1]


def partitions(config, at):
    """Year/topic partitions keep the declared scope inspectable and resumable."""
    if config.get("schema_version") != "1.0.0" or not 2020 <= config["start_year"] <= at.year:
        raise ValueError("Unsupported research intake scope")
    size = config["default_page_size"]
    if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= 100:
        raise ValueError("Discovery page size must be 1..100")
    categories = " OR ".join("cat:" + value for value in config["arxiv_categories"])
    result = []
    # Newest partitions first; old years remain in the durable queue.
    for year in range(at.year, config["start_year"] - 1, -1):
        for topic in config["arxiv_topics"]:
            result.append({"id": f'arxiv-{year}-{topic["id"]}', "adapter": "arxiv", "limit": size,
                           "query": f'({categories}) AND ({topic["query"]}) AND submittedDate:[{year}01010000 TO {year}12312359]'})
    for query in config["huggingface_queries"]:
        result.append({"id": "hf-" + query, "adapter": "huggingface", "query": query, "limit": size})
    for collection in config["acl_collections"]:
        result.append({"id": "acl-" + collection, "adapter": "acl", "query": collection, "limit": size})
    # The rolling OAI query catches replacements to old arXiv works. Its stable
    # partition ID lets an unfinished run retain the original query and token.
    since = (at - timedelta(days=14)).date().isoformat()
    result.insert(0, {"id": "oai-updates", "adapter": "oai", "query": since, "limit": size})
    if len({row["id"] for row in result}) != len(result):
        raise ValueError("Discovery partition IDs must be distinct")
    return result


def select_partitions(rows, previous, limit):
    """Fair oldest-attempt-first scheduling prevents an endless first-page loop."""
    if not 1 <= limit <= 20:
        raise ValueError("A run may attempt 1..20 partitions")
    order = {row["id"]: index for index, row in enumerate(rows)}
    return sorted(rows, key=lambda row: (previous.get(row["id"], {}).get("attempted_at", ""), order[row["id"]]))[:limit]


def partition_digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def configuration_digest(row):
    # A rolling query date is a run input, not a configuration change. Freeze
    # that date until pagination finishes; the next run refreshes its lookback.
    return partition_digest({**row, "query": "rolling-14-days-v1"} if row["adapter"] == "oai" else row)


def run(root, state, at, max_partitions=4):
    root, state = Path(root), safe_output(state)
    if at.tzinfo is None:
        raise ValueError("Intake time must have an explicit timezone")
    config = json.loads((root / "data/research/intake.json").read_text())
    rows = partitions(config, at)
    state.mkdir(parents=True, exist_ok=True)
    ledger_path = state / "intake-ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"schema_version": "1.0.0", "partitions": {}}
    if ledger.get("schema_version") != "1.0.0":
        raise ValueError("Unsupported intake ledger")
    selected = select_partitions(rows, ledger["partitions"], max_partitions)
    stamp = at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    outcomes = []
    for row in selected:
        previous = ledger["partitions"].get(row["id"], {})
        configuration = configuration_digest(row)
        resume = (previous.get("configuration_sha256") == configuration
                  and previous.get("discovery_window")
                  and (not previous.get("complete") or previous.get("attempted_at", "")[:10] == stamp[:10]))
        if resume:
            row = previous["partition"]
            if partition_digest(row) != previous.get("partition_sha256"):
                raise ValueError("Stored discovery partition changed during pagination")
        binding = partition_digest(row)
        generation = previous.get("discovery_generation", 0) + (0 if resume else 1)
        window = previous["discovery_window"] if resume else stamp[:10] + ":" + str(generation)
        run_identity = {"partition_sha256": binding, "configuration_sha256": configuration,
                        "partition": row, "discovery_window": window, "discovery_generation": generation}
        # Persist the query identity before a page can reach its checkpoint. A
        # process interruption must not replace a partially consumed dated run.
        ledger["partitions"][row["id"]] = {"attempted_at": stamp, "complete": False,
                                           "approved": False, **run_identity}
        write_json(ledger_path, ledger)
        checkpoint = state / "checkpoints" / (row["id"] + ".json")
        client = PublicClient(state / "cache", checkpoint, ADAPTER_HOSTS[row["adapter"]])
        try:
            result = discover(client, row["adapter"], row["query"], limit=row["limit"], pages=1, window=window)
            path = state / "candidates" / (row["id"] + ".json")
            write_json(path, result)
            summary = {"attempted_at": stamp, "complete": bool(result["complete"]),
                       "candidates": len(result["candidates"]), "result_path": str(path), "approved": False}
        except Exception as error:
            # Every failed partition remains explicit and eligible for later retry.
            summary = {"attempted_at": stamp, "complete": False, "approved": False,
                       "error_type": type(error).__name__, "error": str(error)[:300]}
        summary.update(run_identity)
        ledger["partitions"][row["id"]] = summary
        write_json(ledger_path, ledger)
        outcomes.append({"id": row["id"], **summary})
    # Provider leads retain their unscreened status, including parent/brand questions.
    leads = {"schema_version": "1.0.0", "status": "candidates_only", "approved": False,
             "scope_id": config["scope_id"], "providers": config["additional_provider_candidates"]}
    write_json(state / "provider-leads.json", leads)
    return {"status": "candidates_only", "facts_modified": False, "approved": False,
            "scope_id": config["scope_id"], "scope_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
            "declared_partitions": len(rows), "attempted": outcomes,
            "completed_partitions": sum(bool(ledger["partitions"].get(row["id"], {}).get("complete"))
                                        and ledger["partitions"][row["id"]].get("configuration_sha256") == configuration_digest(row)
                                        for row in rows),
            "limitations": config["limitations"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--state", type=Path, default=ROOT / "output/research-intake")
    parser.add_argument("--max-partitions", type=int, default=4)
    parser.add_argument("--now")
    args = parser.parse_args()
    at = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    print(json.dumps(run(args.root, args.state, at, args.max_partitions), indent=2))


if __name__ == "__main__":
    main()
