# Research evidence graph

This additive graph is **prelaunch**. It does not replace canonical dataset 2.5.0,
its JSON, its SQLite database, or their dates.

## Reviewed integration checkpoint

The 10 November 2026 integration checkpoint selected through approved partitions
`20-papers-cohort9-2026-11-10.json` and `21-identity-bridges-2026-11-10.json`
retains 39 historical organization descriptions and 1,713 approved assertions.
Computed coverage is 65 qualifying suppliers, 152 reviewed paper works,
63 dataset families and 21 benchmark families. All 39 legacy organizations have
completed source inclusion audits; 38 have conclusive commercial dispositions.
BenchFlow remains commercially unresolved and contributes no qualifying supplier
or disposed frozen-core unit. Coverage method 1.3 keeps these measures distinct.

Its 1,754 scoped source records include 1,753 captured records representing
501 distinct captured document versions. The 187 new identity edges connect
124 paper versions to works and 63 documentation manifestations to families.
Documentation pins do not establish underlying corpus-byte releases. Source
versions, aliases and mirrored releases do not inflate the object counts.

Each approved assertion has exact-content, separate author, source-verifier and
adversarial AI receipts. Seven cohort 9 locator gaps were repaired with fresh
three-role receipts for the new digests; 21 superseded receipts, including seven
negative records, remain preserved separately. All 73 unaffected triples retain
their original records. A scoped methods/results/limitations review does not claim
every appendix, proof, corpus row or experimental result was reproduced.

The FHIBE institutional manuscript copy remains distinct from the publisher PDF.
MuSiQue counts once as a human-composed question family; seed datasets,
answerability configurations and serializations do not add families. Restrictive
or unresolved corpus licenses are catalogue findings and imply no permission to
redistribute underlying third-party data.

The eligible core and both actual 200-record audits remain unfinished. The expanded
report and matching package are not yet prepared. Prior synthesis receipts and
frozen archive bytes remain bound to their original graph.

## Historical initial baseline

The initial baseline retained 39
historical organization descriptions and 173 approved assertions. The latest batch
contributes 163 assertions after separate author, source-verifier and adversarial
AI review of pinned primary sources. Eight disputed assertions remain quarantined;
one redundant MMLU assertion was omitted rather than counting a study twice.

Coverage is eight existing organization inclusion audits, eight qualifying
suppliers, eight full-source paper works, eight dataset families and five benchmark
families. The 194 scoped evidence records represent 75 distinct captured document
versions, not 194 independent documents. These are reviewed baseline observations,
not a comprehensive market census or completed launch audit.

That initial calculation counted FineWeb-Edu separately. The current identity
review treats it as a FineWeb subset release and counts one family. Historical
frozen files retain their exact bytes; the next synthesis must identify this
correction rather than silently rewriting archived calculations.

The graph retains the actual UTC capture and review times. Captures on 9 November
in Los Angeles occur on 10 November UTC; they do not retroactively satisfy the
preceding Friday's source cutoff. New independent reviews can inspect captured
versions later, but cannot move a source capture into an earlier release window.

## Offline interfaces

`scripts/research_graph.py` uses only the standard library. Ordinary builds never
retrieve sources or require credentials.

- `load_graph(root=ROOT)` loads `data/research/graph.json`, appends any explicitly
  pinned approved partitions, validates the complete graph's references and
  provenance, and verifies the exact canonical dataset bytes and version.
- `load_partition_records(root=ROOT)` reads the optional approved index and returns
  only `entities`, `sources`, `assertions`, and `reviews` arrays. It verifies input
  shape, byte hashes, paths, ordering, and approved assertion status. Cross-record
  references and actual approval receipts are validated only after merging by
  `load_graph`; calling this helper alone does not establish a valid graph.
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

## Approved source partitions

The existing monolithic source remains valid. If
`data/research/approved/index.json` is absent, loading and export behavior are
unchanged. An empty index is also valid. Builds never scan directories for research
or read intake records from `output/`; only exact files named by the index enter
the graph.

```text
data/research/graph.json             # root metadata and central entity registry
data/research/approved/index.json    # explicit ordered list of pinned batches
data/research/approved/<batch>.json  # reviewed records, not candidate intake
output/research-candidates/          # untracked candidate/discovery output
```

The index has exactly `schema_version` and `partitions`. Its schema version is the
same string as the graph's, currently `"1.0.0"`. Every entry has exactly `path` and
`sha256`; paths are relative to `data/research/approved/`, use canonical POSIX
spelling, and appear in strictly increasing lexical order. Duplicate entries,
absolute paths, `.`/`..` segments, backslashes, and symlinks are refused. Symlinks
in the index path, approved directory, or partition parent directories are refused
too. Each digest is 64 lowercase hexadecimal characters binding the complete file
bytes, including whitespace and final newline. A missing file or digest mismatch
stops the build. Generate a digest locally with `hashlib.sha256(path.read_bytes())`;
no source retrieval is part of aggregation.

An empty index is:

```json
{"schema_version": "1.0.0", "partitions": []}
```

A partition has required `schema_version: "1.0.0"` and any of the optional
`entities`, `sources`, `assertions`, and `reviews` arrays. Omitted arrays mean empty
arrays. No other root properties are allowed: `graph.json` alone owns release ID,
as-of time, canonical binding, coverage scope, and audit manifests. Every supplied
record retains the existing graph schema, with no extensions. Within each supplied
array, stable IDs must be strictly increasing. IDs must be unique across tables,
partitions, and the base graph; a partition cannot patch or replace an existing row.
Duplicate JSON keys and non-finite JSON numbers also fail loading.

The base graph's array order remains intact. Arrays from each partition append in
index order, retaining their declared row order. All partitions merge before the
existing graph validator runs, so assertions, entities, evidence, and reviews may
refer to records in earlier or later partitions or the base graph. Unknown
references still fail. Each partition assertion must already be `approved` and
must pass the unchanged full source-content, exact-assertion-hash, three-role,
distinct-invocation, chronology, and reciprocal-reference checks. Candidate,
quarantined, rejected, and historical assertions cannot enter approved partitions.
A file hash proves input identity; it creates no source read or review receipt.

Keep entity identity and its current review-depth/disposition metadata in the
central `graph.json` registry when practical. Its `assertion_ids` may point into
approved partitions. Partitions may introduce new entities, but must not duplicate
registry IDs; approved evidence records can live entirely outside the registry.
Registry status and review depth do not themselves approve an assertion or bypass
coverage and publication gates. The graph's as-of time must still cover all actual
source captures and reviews.

Carry forward every previously accepted partition and its pin in each subsequent
index, then add separately reviewed batches in lexical order. An index replacement
does not inherit omitted records. Changes to a batch require an intentional new
pin; changed assertion content additionally requires new actual reviews bound to
that content. Preserve source versions, capture times, and original review times
when carrying evidence forward. Keep new discovery and candidate research in
untracked `output/` until its actual independent reviews finish. Existing historical
and candidate records in the monolithic graph retain their original handling.

Exports aggregate the merged graph into the existing privacy-filtered JSON, CSV,
and SQLite projections. The exported graph includes all retained entities,
sources, assertions, and reviews directly; it requires no partition files or index
to validate or reproduce the public graph offline. Its canonical byte binding and
publication gates remain unchanged. Repeated builds from the same base and pinned
partitions produce identical export bytes.

## What a record means

Entities distinguish paper works from paper versions; dataset families from
releases; benchmark families from versions; organizations, suppliers, models,
institutions, and workflow instances. `parent_id` binds each manifestation to its
work or family. Duplicate work identifiers and duplicate family records fail
validation. `review_depth` is `metadata`, `abstract`, `full_source`, or `historical`.
An abstract read never counts as a deeply reviewed paper. Each entity carries
independent domain, modality, workflow, expertise, origin, labels, and oversight
facets. Those seven arrays remain required. Optional `delivery_model` and
`data_purpose` arrays record independent delivery and data-use classifications;
existing records need no migration. All present facets require unique, nonempty
strings, and unknown facet names fail validation. Omitted optional facets and empty
arrays mean unclassified, not absence of a capability.

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

Some approved assertions retain an original qualification beginning “Author-only
candidate”. This is an unchanged record of their original author stage. The reader
labels it “Original author-stage note”; current approval is established separately
by the exact-content, three-role review receipts. Changing that stored assertion
text would require new reviews, so promotion never silently rewrites it.

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
research. OAI resumption tokens expire daily; an expired token restarts the same
query and window, preserving checkpointed candidates for deduplication. Do not
change the date range to bypass unread pages. An OAI query may be an inclusive
`from/until` pair, for example `2026-11-01/2026-11-07`. The durable preparation
runner manages these ranges, catch-up, and candidate materialization; see
[intake operation and recovery](intake.md).

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

The launch floors require inclusion audits of all 39 legacy organizations, 60 qualifying suppliers,
150 distinct deeply reviewed paper works, 60 dataset families, 20 benchmark
families, and 90% disposition of a hash-bound frozen eligible core. Countable
supplier/paper/family entities require an included disposition, full-source review depth, and an approved
assertion; suppliers additionally require an approved capability assertion. Versions,
aliases, candidate matches, historical descriptions, and duplicate releases do not
inflate coverage.

Legacy inclusion auditing is measured separately from commercial qualification.
`legacy_inclusion_audits` requires full-source depth and approved subject-owned
source evidence with actual three-role reviews; candidate assertions, metadata
and inherited historical descriptions do not suffice. Pending commercial
qualification does not contribute a supplier or a disposed core unit.
`legacy_dispositions` continues to count only conclusive dispositions. The
1.3.0 method and `research-launch-2` policy correct the earlier implementation's
label/count mismatch without changing the agreed 39-audit minimum or any other
launch threshold. Frozen historical methods and archives are unchanged.

Coverage method 1.3.0 retains the 1.2.0 identity rollup: an explicit, approved, full-source paper version or
release rolls up to its approved, full-source, included parent work or family. The same
reviewed-parent proof applies to the frozen core's disposition counter, without
copying version claims onto the parent. Candidate, abstract-only or pending
parents or manifestations cannot supply that proof. Frozen core units are
organization, paper-work and dataset/benchmark-family identities; versions,
releases, model rows and workflow labels cannot inflate its denominator. It counts
each parent once. This identity rollup creates no supplier relationship and never
turns a metadata-only parent into a reviewed work. Suppliers still need direct
approved capability evidence. Source-record totals count scoped evidence records;
`captured_source_versions` deduplicates their exact version and response digest.

Core inclusion counts require the same approved substantive review. A documented
exclusion or historical-only disposition requires a full-source review and its
own subject-bound approved evidence; being the object of a supplier relationship
does not certify an artifact dossier. Conclusive `legacy_dispositions` counts use
the same substantive-disposition requirement. Completed `legacy_inclusion_audits`
use the separate full-source, approved subject-owned evidence rule above;
pending commercial qualification adds no supplier or disposed core coverage. A candidate,
abstract-only screen or failed
retrieval cannot satisfy the 90% gate. Historical calculation behavior remains
in each edition's exact checksummed validator/reproducer, rather than being
rewritten when the current coverage method changes.

The initial eligible core is explicitly **not frozen**. Both the source-anchored
200-assertion quality holdout and separate 200-record screening audit are null.
No calculated total can replace actual reviewed audit records. The report gate owns
precision, recall, critical-attribution failures, recovery, stratum coverage, cutoff,
and release-window checks. Until those requirements and the real coverage pass,
the report must remain held in prelaunch state.
