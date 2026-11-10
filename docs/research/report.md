# State of AI Data Labs and Human Feedback

`data/research/report.json` is the separately versioned, 12-chapter report. It
currently says **prelaunch**. It contains a methodology, practical decision
guidance, explicit research gaps, and a few graph-bound descriptions labeled as
historical. It does not claim a completed new research corpus or human review.
Canonical dataset 2.5.0 and its downloads are unchanged.

The chapters cover scope; evidence and AI review; suppliers; paper-to-practice
synthesis; dataset provenance; benchmarks; feedback formats; quality and
disagreement; attribution; economics and procurement; coverage and holdouts;
and versioned releases, reuse, and corrections. Paragraph kinds are
`sourced_fact`, `analysis`, `method`, and `research_gap`. Factual paragraphs need
stable graph assertion IDs; historical bindings require `historical: true` and
explicit dated wording. Candidate findings cannot become report facts.

## Publication gate

`scripts/research_report.py` exposes `load_report(root)`,
`publication_gate(graph, report, policy=None)`, and `build_context(root)`.
The context has `graph`, `report`, `gate`, `identity`, and `policy`.

The gate calls the graph's strict validator and computed coverage function. It
does not trust a report's stated counts or graph summary totals. These code
floors cannot be lowered in generated JSON policy:

| Requirement | Minimum |
|---|---:|
| Legacy organization inclusion audits | 39 |
| Qualifying suppliers | 60 |
| Distinct reviewed paper works | 150 |
| Dataset families | 60 |
| Benchmark families | 20 |
| Disposition of frozen eligible core | 90% |
| Source-anchored reference holdout | 200 assertions |
| Reference precision / recall | 98% / 95% |
| Critical false attribution | None |
| Separate screening holdout | 200 eligible records |
| Screening recovered | 190 |
| Each major screening stratum recall | 90% |

Organization inclusion audits and commercial dispositions are separate. A pending
commercial qualification can have a completed full-source inclusion audit with
subject-owned approved three-role evidence. It contributes neither a qualifying
supplier nor a disposed frozen-core unit. Conclusive dispositions remain visible
as `legacy_dispositions`; the unchanged 39-audit floor uses
`legacy_inclusion_audits`. Historical method versions retain their original counts.

`archival_ready` reports whether the scientific coverage, report, cutoff, and
audit requirements pass **before** an archive exists. This avoids requiring a
published archive before preparing a publishable archive. `archive_reasons`
records the separate archival blockers; final `ready` additionally requires the
actual published version's DOI, record URL, release ID, confirmation date and
artifact digest. Ordinary builds never fetch an API to assert archive state.
The public research hub can expose truthful prelaunch material while this gate
is false. Mirror synchronization and website deployment have their own receipts.

## Actual audit format

Do not create `data/research/reference-audit.json` or `screening-audit.json` until
the actual audits are complete. A test fixture is never publication evidence.
`schema/report-audit.schema.json` documents the row contract. The gate checks
more than JSON shape: graph and membership digests, distinct rows, source
bindings, independent invocation receipts, and metrics recomputed from rows.

Each file records `kind`, `status: completed`, `fixture: false`, `release_id`,
`graph_sha256`, `frozen_on`, `completed_on`, `holdout_ids_sha256`, and `items`.
Compute digests with `research_report.canonical_hash`, using the complete graph
and the sorted list of holdout row IDs respectively. Finalize the graph including
actual review receipts before binding its digest into the audit.

Each item records a unique `id`, its `assertion_id` (reference) or stable
`record_id` (screening), `stratum`, an explicit `adjudication`, boolean
`expected_positive` and `observed_positive`, `critical_false_attribution: false`,
source `evidence` with locators and excerpt digests, and `review_ids`. The latter
must resolve to separate passing source-verifier and adversarial source-content
reviews in the graph and bind the inspected sources. Freeze precedes
adjudication; raw aggregate accuracy fields are ignored.

For the reference audit, positives are source-supported assertions; observed
positives are assertions accepted by the evaluated extraction/review procedure.
Include rejected and missed cases so precision and recall have meaningful
denominators. Reference rows use distinct assertions. For screening, independently
establish 200 eligible records before testing recovery; all expected decisions
are positive. Declare at least `supplier`, `paper`, `dataset`, and `benchmark`
in `major_strata`. Report each stratum's denominator and recovered count.
Holdouts are separate samples with distinct row IDs. Record sampling procedures,
language/access limitations, and selection bias alongside the audit.

## Reproduce locally

```sh
python3 scripts/research_report.py
python3 -m unittest discover -s tests -p 'test_research_*.py'
```

The first command prints actual readiness and blockers without a network call.
The current report remains held because the required coverage, reviews,
holdouts, and public archive have not been established. This is a truthful
publication state, not a reason to fabricate records or weaken the floor.
