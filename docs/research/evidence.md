# Research evidence graph

This additive graph is **prelaunch**. It does not replace canonical dataset 2.5.0,
its JSON, its SQLite database, or their dates. The first graph imports 39 historical
organization descriptions without new review receipts. It includes eight actual
version-specific paper-abstract reads and an NVIDIA HelpSteer3 dataset-card read.
Those reads yield ten author-reviewed **candidate** assertions. They are not a
150-paper deep review, an independent supplier census, or a completed audit.

The graph retains the actual UTC capture and review times. Captures on 9 November
in Los Angeles occur on 10 November UTC; they do not retroactively satisfy the
preceding Friday's source cutoff. New independent reviews can inspect captured
versions later, but cannot move a source capture into an earlier release window.

## Offline interfaces

`scripts/research_graph.py` uses only the standard library. Ordinary builds never
retrieve sources or require credentials.

- `load_graph(root=ROOT)` loads `data/research/graph.json`, validates references and
  provenance, and verifies the exact canonical dataset bytes and version.
- `validate_graph(graph, canonical=None)` returns the graph or raises
  `GraphValidationError` with paths. Pass bytes or a path to bind the canonical
  hash; a parsed canonical object can verify identities and version only.
- `coverage_summary(graph)` computes counts from qualifying records, never stored
  totals. Full publication readiness belongs to `research_report.publication_gate`.
- `public_graph(graph)` produces the explicit versioned public allowlist and
  removes private extension fields and contact emails. Sensitive source evidence
  that cannot retain a valid hash after filtering is refused.
- `write_exports(graph, output)` writes deterministic `research-graph.json`,
  `research-entities.csv`, `research-sources.csv`, `research-assertions.csv`,
  `research-reviews.csv`, `research-graph.sqlite`, and
  `research-exports-manifest.json`; it returns their relative paths.

```sh
python3 scripts/research_graph.py
python3 scripts/research_graph.py --output build/research-exports
python3 -m unittest discover -s tests -p 'test_research_*.py'
```

The SQLite projection includes every public table plus relational
`assertion_evidence` and `assertion_reviews` joins with foreign keys. CSV cells are
escaped against spreadsheet formula execution. Output order, JSON formatting,
database construction, and file digests are deterministic. The database is created
from scratch with secure deletion, so prior database pages cannot retain private
values.

## What a record means

Entities distinguish paper works from paper versions; dataset families from
releases; benchmark families from versions; organizations, suppliers, models,
institutions, and workflow instances. `parent_id` binds each manifestation to its
work or family. Duplicate work identifiers and duplicate family records fail
validation. `review_depth` is `metadata`, `abstract`, `full_source`, or `historical`.
An abstract read never counts as a deeply reviewed paper. Each entity carries
independent domain, modality, workflow, expertise, origin, labels, and oversight
facets. Empty arrays mean unclassified, not absence of a capability.

Assertions have a stable subject, a nontransitive typed predicate, exactly one
object or typed value, precise source locators, excerpt hashes, qualifications,
scope date, and review references. `supplies_data_for` requires explicit evidence
of a supplier's contribution to the named artifact or workflow. `has_capability`
documents an offering and never implies a particular contribution. Stage predicates
such as `recruited`, `annotated`, `adjudicated`, `generated`, `labeled`, and
`filtered` preserve the limited contribution. `uses_training` and `evaluates_on`
keep training use distinct from evaluation use. Relationships are never inferred
by transitive graph traversal.

A captured source has its exact response SHA-256, version, capture timestamp,
concise permitted excerpt (at most 25 words), excerpt SHA-256, publisher, source
type, and locator. Publication date and license remain null when not established.
Historical references preserve the canonical binding and original ledger; import
does not create a new retrieval or review date. Metadata endpoints support discovery
and cannot serve as approved source-content evidence.

An approved assertion requires actual passing author, source-verifier, and
adversarial source-content review receipts. Each role uses a distinct invocation.
Reviews bind back to their assertions and source IDs, identify their actual AI or
human reviewer, and cannot precede source capture or follow graph as-of time. A
metadata review, unresolved negative review, invented reviewer, or automated
retrieval cannot supply an approval. The validator enforces the structural and
chronological receipts; editors remain responsible for their truthfulness.

The initial author invocation records only its own work. It creates no independent
source-verifier or adversarial receipt. Abstract-method claims remain candidates
until those separate reviews happen; full paper review must examine methods,
results, and limitations before setting `review_depth: full_source`.

## Candidate discovery and capture

`scripts/check_research_sources.py` retrieves only public, free sources. It never
changes graph data, statuses, dates, dispositions, or approvals. It refuses output
under `data/`, `dist/`, `web/`, and `release-assets/`, including symlink aliases.
Keep raw caches and checkpoints outside tracked files, for example `/tmp`.

```sh
python3 scripts/check_research_sources.py \
  --cache /tmp/sts-research-cache \
  --checkpoint /tmp/sts-research-checkpoint.json \
  --output build/research-candidates/arxiv.json \
  discover --adapter arxiv --query 'all:"human feedback"' --limit 50 --pages 2

python3 scripts/check_research_sources.py \
  --cache /tmp/sts-research-cache \
  --checkpoint /tmp/sts-research-checkpoint.json \
  --output build/research-candidates/acl.json \
  discover --adapter acl --query 2022.emnlp

python3 scripts/check_research_sources.py \
  --cache /tmp/sts-research-cache \
  --checkpoint /tmp/sts-research-checkpoint.json \
  --output build/research-candidates/oai.json \
  discover --adapter oai --query 2026-11-01 --pages 1

python3 scripts/check_research_sources.py \
  --cache /tmp/sts-research-cache \
  --checkpoint /tmp/sts-research-checkpoint.json \
  --output build/research-candidates/hf.json \
  discover --adapter huggingface --query HelpSteer --limit 50

python3 scripts/check_research_sources.py \
  --cache /tmp/sts-research-cache \
  --checkpoint /tmp/sts-research-checkpoint.json \
  --output build/research-candidates/crossref.json \
  discover --adapter crossref --query 'preference data' --limit 50
```

The arXiv Atom adapter pages bounded results. OAI uses the current
[`https://oaipmh.arxiv.org/oai` endpoint and `arXivRaw` format](https://info.arxiv.org/help/oa/index.html),
preserves version histories and deleted-record handling, and resumes tokens. OAI
metadata datestamps describe modification, not submission dates. ACL uses official
Anthology collection XML. Hugging Face follows available next-page links; a full
page without one remains explicitly truncated. Optional Crossref discovery uses
cursor pagination; bibliographic metadata does not prove a contribution.

Queries are identified by adapter, text, page size, and dated discovery window.
The default window is the current UTC day; use `--window` for an explicit run
identity. Same-window retries resume completed pages. A new day or window starts
fresh discovery instead of retaining a permanently completed mutable query. A
completed query covers only that adapter's returned partition, not all relevant
research. OAI resumption tokens expire daily; restart with a new window after an
expired token and retain the prior candidate records for deduplication.

Each request uses public credential-free HTTPS, TLS verification, an explicit host
allowlist, DNS checks that reject local/private/reserved destinations, redirect
checks, a maximum 8 MiB read, at most three attempts, and per-host throttling.
Conditional GET retains the original captured bytes and timestamp on a 304 and
verifies the cached digest first. A broken cache causes an unconditional retrieval.
429/503 retry instructions up to 30 seconds are respected; longer instructions
defer the request to another run rather than retrying early. Challenges and failed
requests do not become source reads. Checkpoints are written atomically after
every request and successful page.

The `capture` command requires `--url`, `--allow-host`, `--excerpt`, `--locator`,
and `--version`. The excerpt must match the actual captured visible text literally,
and the receipt's response hash must match the complete bounded response. It emits
a capture **candidate**, with `approved: false`, for later scoped source review.
Raw bodies stay in the private/untracked cache and never enter the public graph.

## Floors and remaining work

The launch floors remain 39 actual legacy dispositions, 60 qualifying suppliers,
150 distinct deeply reviewed paper works, 60 dataset families, 20 benchmark
families, and 90% disposition of a hash-bound frozen eligible core. Countable
entities require an included disposition, full-source review depth, and an approved
assertion; suppliers additionally require an approved capability assertion. Versions,
aliases, candidate matches, historical descriptions, and duplicate releases do not
inflate coverage.

The initial eligible core is explicitly **not frozen**. Both the source-anchored
200-assertion quality holdout and separate 200-record screening audit are null.
No calculated total can replace actual reviewed audit records. The report gate owns
precision, recall, critical-attribution failures, recovery, stratum coverage, cutoff,
and release-window checks. Until those requirements and the real coverage pass,
the report must remain held in prelaunch state.
