# Next-edition operating notices

This optional source-owned notice describes the next weekly edition while the
current public edition remains unchanged. It is not a research input, publication
receipt, archive, review, account status, or release authorization. No real status
file is supplied by this change: the first launch must not be called delayed
without an actually published predecessor and an observed weekly event.

The source path is `data/research/operating-status.json`, with schema
`schema/research-operating-status.schema.json`. There is no free-text field.
Only these exact fields are permitted:

```json
{
  "schema_version": "research-operating-status-v1",
  "state": "held",
  "observed_on": "2026-11-16T17:10:00Z",
  "published_source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "current_release_id": "SYNTHETIC-NEVER-PUBLISHED",
  "current_edition_date": "2026-11-12",
  "next_edition_date": "2026-11-16",
  "reason_codes": ["research_review"]
}
```

This example is invented, is not a publication or actual status, and must not be
copied into the live source. Its values have no release authority.

`published_source_sha256` is the exact selector byte digest returned by the
verified public context's `published_source_selection.sha256`. It is not a digest
of a private candidate or the status itself. The release and current edition date
must equal the selected, actually published frozen edition. The target must be
the first Monday strictly after that edition date, at 09:00 America/Los_Angeles.
An overdue target stays visible until publication; a later preparation cannot
silently skip the missed target. Launch editions may retain a non-Monday date.

`observed_on` records the actual observation, with seconds and explicit timezone.
It must follow actual archive confirmation and cannot be later than the actual
aware validation clock. `held` needs at least one known reason and an observation
at or after the target. `preparing` has an empty reason list and requires an
observation before the target. The observation remains valid after that target
passes: the rendered wording describes the recorded observation and exposes its
actual date and target. Host downtime cannot rewrite that history. A dated held
observation can also remain while the same edition stays published; neither state
implies new checking on every build.
A new selector invalidates an old binding even when a release name is reused.

Known coarse reasons map to fixed public wording:

| Code | Public wording |
| --- | --- |
| `publication_preparation` | Final publication preparation was still in progress. |
| `research_review` | Research review was still in progress. |
| `source_checks` | Source checks were still in progress. |
| `technical_checks` | Final file and website checks were still in progress. |

Use only reasons actually known at the observation. Unknown or unresolved results
do not establish a failed review. Do not insert scores, private review text,
candidate findings, contacts, paths, service credentials, or account/outreach
claims. Unknown fields, booleans as reasons, duplicate fields/reasons, nonfinite
JSON, malformed dates, a future observation, unsafe files, and stale bindings
fail closed. A file without a verified current public selector is refused. The
loader reuses public historical verification and does not require fresh-candidate
`archival_ready`; verified frozen replay correctly has that flag false.

## Weekly publisher workflow

Daily preparation remains private and prepare-only. It must not create, edit,
commit, deploy, or remove the public notice, switch the public source selector,
reserve a DOI, or mutate production. A daily job may record an operational
proposal in its separate private state for the sole weekly publisher to inspect.

At the weekly release check, or an actual delayed catch-up:

1. Run the authorized research and release checks against the real candidate.
   Preserve all actual results and times. A missed host run is not an on-time
   publication and an unexecuted check is not a pass or failure.
2. If publication remains held, retain the last actually verified published
   selector, ledger, capsule, report, source/review dates, PDF, ZIP, and DOI bytes.
   Obtain this context through `research_report.build_context`, which selects the
   published source before any private authoring read. Do not retarget the
   selector to the failed or merely prepared candidate.
3. Only the sole weekly publisher may write this small public operating file
   using the actual observation and known allowed reasons. It may publish a
   truthful notice against the retained verified capsule after the ordinary exact
   site artifact and production checks. That operation publishes a site notice;
   it does not publish a research edition or create an archive/feed item/DOI.
4. When a subsequent edition actually publishes, remove the old optional status
   in the same reviewed source change that selects the new verified capsule, or
   explicitly create a correctly bound future notice. A stale file must not be
   silently ignored or refreshed by the builder.

Absent status means no notice and no status-derived date. It makes no claim that
the next edition is published, on time, delayed, or actively being prepared.
Normal builds remain offline and credential-free. The actual clock is passed
only to reject future observations; it never expires a past preparation
observation, changes source files, or appears in output. Valid unchanged source
renders identical bytes both before and after its target. A missed run is visible
through the unchanged dated observation and target, without claiming publication.

## Coordinator integration contract

The workstream owns only the new pure module, schema, tests, and this document.
The coordinator owns the central hooks in `scripts/research_pages.py`. Apply the
notice only to current public pages; leave archived edition contexts and all
publication-asset generation untouched.

Import `with_operating_status` and `operating_status_notice` from
`research_operating_status`. At the start of `write_research_pages`, after its
caller has obtained the source-selected context, create the rendering-only
shallow overlay:

```python
context = with_operating_status(context, now=datetime.now(timezone.utc))
```

Add `timezone` to that file's existing datetime import. The passed clock is an
actual aware validation instant used only to reject future observations, never a
persisted publication timestamp or an input that expires old preparation history.
Do not call this hook in `build_context` before published-source selection, or
in citations, archive/PDF/ZIP generation, frozen report hashing, or the release
gate. The overlay keeps the exact report object and only adds `operating_status`
to a local rendering dictionary. Never serialize that runtime dataclass as part
of frozen source context.

Insert the fragment in these three current-page bodies:

* `_hub`: immediately after the hero header and before the coverage section.
* `_report`: immediately after `header`; use `'' if edition else
  operating_status_notice(context)` so immutable edition pages never gain it.
* `_data`: immediately after the page header and before the coverage section.

Each insertion is `+ operating_status_notice(context)` except the explicit
immutable-edition guard above. It emits ordinary HTML with a heading, fixed
human wording, published edition date/release, target time, and actual observed
time. It requires no CSS addition or JavaScript, including for the data hub.
Do not change `_status`, `_meta`, research counts, evidence/review dates, citation
content, current published report identity, immutable routes, downloads, or feeds.

After the existing `_page_revisions = _revision_dates(context)` assignment,
optionally include the observation as the substantive page modification date
for these three current paths only, using the existing `_day` Pacific conversion:

```python
status = context.get('operating_status')
if status is not None:
    observed_day = _day(status.observed_on.isoformat())
    for path in ('/research/', REPORT_PATH, '/research/data/'):
        context['_page_revisions'][path] = max(
            context['_page_revisions'].get(path) or observed_day, observed_day)
```

This changes only the current HTML page modification metadata when the notice is
present; it must not revise source-review dates or archived page metadata.
For complete removal, use the real removal revision date under the repository's
normal page-revision policy, without inventing a research review.

Run the focused synthetic-only tests with:

```sh
python3 -m unittest discover -s tests -p test_research_operating_status.py -v
```

These tests explicitly mock the public replay proof boundary. They test notice
validation, no-status identity/no I/O, preservation of opaque synthetic frozen
bytes and original report fields, deterministic HTML, refusal without replay
verification, and unsafe/stale inputs. They do not claim a real research or
publication check. The coordinator must add integrated hub/report/data assertions
against an isolated source-selected public fixture, check the no-status build
matches its baseline bytes, verify immutable/download artifacts stay unchanged,
and perform final actual QA after the real research gates.
