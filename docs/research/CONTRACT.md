# Research publication integration contract

This contract implements the user-approved research-authority plan. Canonical
dataset 2.5.0 and its existing JSON/SQLite downloads remain byte-identical.
New approved research is additive and independently versioned. The public report
must remain in prelaunch state until the actual coverage and quality gates pass.
Never manufacture records, reviews, source reads, DOI status or passing audits.

## Shared interfaces

Use Python standard-library modules and the existing static build. Ordinary builds
perform no network calls and require no credentials. No worker edits `dist/`.

* Evidence owner: `scripts/research_graph.py` exposes `load_graph(root=ROOT)`,
  `validate_graph(graph, canonical=None)`, `coverage_summary(graph)`,
  `public_graph(graph)`, and `write_exports(graph, output)`.
  Graph source is `data/research/graph.json`; root properties are `schema_version`,
  `release_id`, `as_of`, `canonical_dataset_version`, `canonical_sha256`, `entities`,
  `sources`, `assertions`, `reviews`, `coverage`.
* Report owner: `scripts/research_report.py` exposes `load_report(root=ROOT)`,
  `publication_gate(graph, report, policy=None)`, and
  `build_context(root=ROOT)`. `build_context` returns a dict with `graph`, `report`,
  `gate`, `identity` and `policy`. Source is `data/research/report.json`.
  The gate returns `ready` (bool), `status`, `reasons` (list), and `coverage`.
  A report includes title, release_id, updated_on, status, sections and editions.
  Sections have stable id, title, paragraphs (each has text, claim_ids, kind).
  Kinds distinguish sourced fact, analysis, method and explicit research gap.
* Discovery owner: `scripts/research_pages.py` exposes
  `write_research_pages(output, context)` returning a list of
  `{path, lastmod}` records, and `research_search_entries(context)` returning
  compact `{title, summary, url, kind, keywords}` records.
  The renderer owns research-only styles and `/review/`, uses existing static
  document helpers, and emits truthful prelaunch/coverage pages when gate fails.
* Citation owner: `scripts/research_citations.py` exposes
  `write_publication_assets(context, output)` returning generated relative paths.
  It also owns archive/projection builders and external release adapters.
  Routine builds emit citations/data without claiming a published edition/DOI.
* Trust owner: `scripts/public_identity.py` exposes `load_identity(root=ROOT)`
  from `data/public-identity.json`. Owns review Issue Forms, contribution/reuse
  instructions, external-profile corrections and legacy-MCP retirement docs.

The coordinator owns all changes to shared build modules, existing templates,
navigation/search, headers, README, CI integration, final distribution and deploy.
Pure new modules and their focused tests belong to the relevant workstream.

## Evidence and release rules

An approved assertion has stable subject/predicate/object or typed value,
source/version-specific evidence and locator, qualifications and actual AI review
receipts. Candidate records never count as deeply reviewed. A provider's public
capability does not establish its contribution to a particular dataset/paper.
Historical evidence retains its original source and review dates.

Launch floors: 39 legacy organization dispositions, 60 qualifying suppliers,
150 distinct reviewed paper works, 60 dataset families, 20 benchmark families,
90% frozen eligible core disposition, source-anchored 200-assertion quality
holdout (98% precision/95% recall, no critical false attribution), and separate
200-record screening audit (190 recovered, major strata at least 90%). These
thresholds cannot be reduced by weekly generated research or fake test evidence.

Release window is Monday 09:00 America/Los_Angeles; source cutoff Friday 17:00.
Evidence may be verified later against source versions captured before cutoff.
Actual archive, website and mirror states are independent. Production activation
is serialized and follows exact-artifact preview/test/promote/rollback.

External credentials and raw caches never enter tracked files. Permanent archives
contain only an explicitly versioned, privacy-filtered public projection, owned
text, permitted concise source evidence, attribution, methods and reproducibility
instructions. Keep current canonical privacy exceptions out of new exports.

## Agent execution

Five workstream owners use gpt-6.1-sol with ultra reasoning. Only three workers
plus coordinator run at once. Separate author, source-verifier and adversarial
review invocations are recorded honestly. No outreach is sent. Each owner commits
only its files on its own branch; coordinator cherry-picks and integrates.
