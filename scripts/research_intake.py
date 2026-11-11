#!/usr/bin/env python3
"""Run bounded, restartable discovery partitions; never approve research facts."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from check_research_sources import ADAPTER_HOSTS, PublicClient, discover, oai_candidate_rank, safe_output, write_json

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
    # Bootstrap only: after the first window starts, durable completed-through
    # dates and captured queries replace the rolling lookback (see run_oai).
    since = (at - timedelta(days=14)).date().isoformat()
    result.insert(0, {"id": "oai-updates", "adapter": "oai", "query": since, "limit": size})
    if len({row["id"] for row in result}) != len(result):
        raise ValueError("Discovery partition IDs must be distinct")
    return result


def select_partitions(rows, previous, limit):
    """Service expiring OAI tokens every run; fairly rotate the remaining slots."""
    if not 1 <= limit <= 20:
        raise ValueError("A run may attempt 1..20 partitions")
    order = {row["id"]: index for index, row in enumerate(rows)}
    updates = [row for row in rows if row.get("adapter") == "oai"]
    others = [row for row in rows if row.get("adapter") != "oai"]
    return (updates + sorted(others, key=lambda row: (previous.get(row["id"], {}).get("attempted_at", ""), order[row["id"]])))[:limit]


def partition_digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def configuration_digest(row):
    # Preserve the v1 identity so existing unfinished queries resume verbatim.
    # The dated query is a run input, not a configuration change.
    return partition_digest({**row, "query": "rolling-14-days-v1"} if row["adapter"] == "oai" else row)


def oai_completed_until(previous):
    if previous.get("last_completed_until"):
        return date.fromisoformat(previous["last_completed_until"])
    if previous.get("window_complete", previous.get("complete")):
        query = previous["partition"]["query"].split("/")
        # Legacy open-ended queries have no captured upper bound. Conservatively
        # credit only the last whole UTC day before their original run started.
        return (date.fromisoformat(query[1]) if len(query) == 2 else
                date.fromisoformat(previous["discovery_window"][:10]) - timedelta(days=1))
    return None


def oai_candidates(client, current):
    """Rebuild the materialized candidate file even if its last write was lost."""
    candidates = {}
    batches = [progress.get("candidates", []) for progress in client.state.get("cursors", {}).values()] + [current]
    for batch in batches:
        for row in batch:
            old = candidates.get(row["id"])
            # An overlap replay must not restore older metadata over a deletion
            # or a newer modification already captured in another window.
            if old is None or oai_candidate_rank(row) >= oai_candidate_rank(old):
                candidates[row["id"]] = row
    return sorted(candidates.values(), key=lambda row: row["id"])


def run_oai(row, ledger, ledger_path, state, stamp, request_times, page_budget):
    """Drain inclusive, captured date ranges within a shared page-request budget.

    Advancing the watermark is the final commit, after both the page checkpoint
    and the cumulative candidate file exist. No wall-clock lookback can skip a
    pending range. Queries cover metadata modifications, including old papers.
    """
    target = date.fromisoformat(stamp[:10]) - timedelta(days=1)
    configuration = configuration_digest(row)
    checkpoint = state / "checkpoints" / (row["id"] + ".json")
    if ledger["partitions"].get(row["id"], {}).get("discovery_window") and not checkpoint.exists():
        raise ValueError("OAI checkpoint missing; restore the original state before continuing")
    client = PublicClient(state / "cache", checkpoint, ADAPTER_HOSTS["oai"])
    if not checkpoint.exists():
        # The query journal must never refer to a checkpoint that a process
        # interruption prevented us from creating in the first place.
        client.save()
    client.last_request = request_times
    requests, completed_windows = 0, 0
    while requests < page_budget:
        previous = ledger["partitions"].get(row["id"], {})
        completed = oai_completed_until(previous)
        compatible = previous.get("configuration_sha256") == configuration
        resume = (previous.get("discovery_window") and
                  (not previous.get("window_complete", previous.get("complete")) or
                   (compatible and completed is not None and completed >= target)))
        if resume:
            active = previous["partition"]
            if partition_digest(active) != previous.get("partition_sha256"):
                raise ValueError("Stored discovery partition changed during pagination")
        else:
            since = completed - timedelta(days=1) if completed is not None else date.fromisoformat(row["query"].split("/")[0])
            until = min(target, since + timedelta(days=6))
            active = {**row, "query": since.isoformat() + "/" + until.isoformat()}
        generation = previous.get("discovery_generation", 0) + (0 if resume else 1)
        window = previous["discovery_window"] if resume else stamp[:10] + ":" + str(generation)
        identity = {"partition_sha256": partition_digest(active), "configuration_sha256": configuration,
                    "partition": active, "discovery_window": window, "discovery_generation": generation}
        pending = {"attempted_at": stamp, "complete": False, "window_complete": False,
                   "approved": False, "last_completed_until": completed.isoformat() if completed else None, **identity}
        ledger["partitions"][row["id"]] = pending
        write_json(ledger_path, ledger)
        result = discover(client, "oai", active["query"], limit=active["limit"], pages=page_budget - requests, window=window)
        requests += result["requests_made"]
        result["current_window_candidates"] = len(result["candidates"])
        result["candidates"] = oai_candidates(client, result["candidates"])
        path = state / "candidates" / (row["id"] + ".json")
        write_json(path, result)
        # Never persist a completed-through date before materializing candidates.
        if result["complete"]:
            boundary = active["query"].split("/")
            until = (date.fromisoformat(boundary[1]) if len(boundary) == 2 else
                     date.fromisoformat(window[:10]) - timedelta(days=1))
            completed = max(completed, until) if completed else until
            completed_windows += 1
        summary = {**pending, "complete": bool(result["complete"] and completed is not None and completed >= target),
                   "window_complete": bool(result["complete"]), "candidates": len(result["candidates"]),
                   "last_completed_until": completed.isoformat() if completed else None,
                   "target_until": target.isoformat(), "requests_made": requests,
                   "completed_windows": completed_windows, "result_path": str(path),
                   "retry_reason": result.get("retry_reason"), "token_restarts": result.get("token_restarts", 0)}
        if not summary["complete"] and requests >= page_budget:
            summary["retry_reason"] = result.get("retry_reason") or "oai_page_budget_exhausted_resume_same_utc_day"
        ledger["partitions"][row["id"]] = summary
        write_json(ledger_path, ledger)
        if not result["complete"] or summary["complete"]:
            break
    return summary


def run(root, state, at, max_partitions=4, oai_pages=20):
    root, state = Path(root), safe_output(state)
    if at.tzinfo is None:
        raise ValueError("Intake time must have an explicit timezone")
    if not 1 <= oai_pages <= 20:
        raise ValueError("OAI page budget must be 1..20")
    at = at.astimezone(timezone.utc)
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
    # Each partition keeps its own durable pagination checkpoint, but requests
    # to the same host must share throttling across those separate clients.
    request_times = {}
    for row in selected:
        if row["adapter"] == "oai":
            try:
                summary = run_oai(row, ledger, ledger_path, state, stamp, request_times, oai_pages)
            except Exception as error:
                summary = {**ledger["partitions"].get(row["id"], {}), "attempted_at": stamp,
                           "complete": False, "approved": False, "error_type": type(error).__name__, "error": str(error)[:300]}
                ledger["partitions"][row["id"]] = summary
                write_json(ledger_path, ledger)
            outcomes.append({"id": row["id"], **summary})
            continue
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
        client.last_request = request_times
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
    parser.add_argument("--oai-pages", type=int, default=20, help="Total OAI page requests per run, 1..20; remaining partitions use one page")
    parser.add_argument("--now")
    args = parser.parse_args()
    at = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    print(json.dumps(run(args.root, args.state, at, args.max_partitions, args.oai_pages), indent=2))


if __name__ == "__main__":
    main()
