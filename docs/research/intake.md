# Intake operation and recovery

`scripts/research_intake.py` produces private, unapproved discovery candidates.
It never edits the graph, approves research, or regenerates the public snapshot.

arXiv documents that [OAI tokens expire daily, and datestamps describe metadata
modifications](https://info.arxiv.org/help/oa/index.html), including changes to old
papers. They are neither submission dates nor retrieval timestamps. [OAI date
bounds are inclusive, and deletion headers carry modification datestamps](https://www.openarchives.org/OAI/openarchivesprotocol.html).
The public [arXiv Identify endpoint](https://oaipmh.arxiv.org/oai?verb=Identify)
reported persistent deletion tracking and day granularity in a bounded read on
2026-11-10 UTC. Deleted headers become unapproved review candidates; they do not
delete published facts. Version histories remain attached to replacement leads.

## Durable preparation

```sh
python3 scripts/research_intake.py --state output/research-intake \
  --max-partitions 4 --oai-pages 20
```

OAI gets the first partition slot on every run. The other three default slots
rotate oldest-attempt-first across all configured years and other adapters.
Requests across partition clients share one host throttle. Each OAI run uses at
most 20 page requests, with at most three HTTP attempts per page and the existing
3.1-second minimum host interval. Other adapters keep their one-page bound.

Use one intake process per state directory. The first OAI harvest bootstraps from
the 14-day lookback. This is not
an initial copy of all historical arXiv metadata. Once started, its lower bound
comes from durable state, even after downtime longer than 14 days:

- New queries capture inclusive ranges of at most seven calendar days and stop
  at the last whole UTC day before the run. Several ranges may finish within the
  same total page budget. The current UTC day's changes are harvested on a later run.
- `last_completed_until` advances only after the complete page checkpoint and
  cumulative candidate file have been written. Later queries begin one day
  before that date, preserving overlap and deduplicating work IDs.
- A partially read range retains its exact query and discovery-window identity.
  `badResumptionToken` clears only the cursor, then restarts that same query with
  all prior candidate IDs retained. Expiry attempts consume the page budget.
- Existing open-ended v1 queries resume verbatim. On completion they conservatively
  credit only the whole UTC days before the original discovery-window date,
  then transition to bounded queries with overlap. Keep existing state intact.
- The OAI candidate file combines all checkpointed windows. A lost materialized
  candidate write can be repaired from checkpoints without losing earlier leads.

`complete` in the intake ledger means OAI is caught up through `target_until`;
`window_complete` records the active query's pagination status. Neither measures
the research universe or establishes a factual approval. The candidate file's
`complete` refers to its active query, with `current_window_candidates` separate
from its cumulative candidate array.

## Resume and exceptional bulk dates

If `retry_reason` is `oai_page_budget_exhausted_resume_same_utc_day`, run the same
command again within the UTC day. For an OAI-only continuation:

```sh
python3 scripts/research_intake.py --state output/research-intake \
  --max-partitions 1 --oai-pages 20
```

Return to the normal four-partition command after catch-up so historical topic
partitions continue rotating. Do not remove the ledger, checkpoints, or cache;
do not supply a new date window just to bypass an expired cursor. Check
`last_completed_until`, `target_until`, `window_complete`, `retry_reason`, and
`token_restarts` in the ledger. An HTTP error, challenge, malformed response, or
repeated cursor remains incomplete and never advances the watermark.

arXiv warns that bulk metadata updates can create unusually large modification
dates. A range larger than one run's page budget needs same-day continuations.
Repeated daily expirations with no completed-through progress require operator
attention and sufficient same-day invocations to drain the range; the runner
keeps that backlog visible rather than skipping it. Credentials are not required.

The operational simulations in `tests/test_research_oai_reliability.py` are
synthetic offline fixtures, including 1,300-record pages, daily token expiry,
interruptions, candidate-write loss, a month of downtime, old-work replacements,
and deletion headers. They are never research evidence or review receipts.
