# Static research discovery

`scripts/research_pages.py` provides two offline interfaces:

```python
pages = write_research_pages(output, context)
search_records = research_search_entries(context)
```

The context is the validated graph, report, publication gate, public identity, and
policy returned by `research_report.build_context()`. `pages` contains HTML-only
`{path, lastmod}` records, with a leading-slash site path. `lastmod` is the latest
report or evidence snapshot date. The coordinator adds these records to the
sitemap and merges search records into the existing compact local search index.

The renderer writes its own `research.css`, RSS and Atom files. It does not touch
navigation, the existing company builder, the canonical dataset, or `dist/`.
All essential content and links work without JavaScript. The layout uses the
existing static document shell and research-only styles.

## Routes and evidence states

- `/research/`: report, calculated launch progress, evidence indexes, all chapters.
- `/research/state-of-ai-data-labs/`: the complete current report, with each of its
  dynamic section IDs as an anchor, paragraph-kind labels, and assertion links.
- `/research/data/`: coverage and actual gate blockers, exports, citation formats,
  historical records, candidate queue, source records, and entity register.
- `/review/`: source-backed corrections, scoped review, and public reuse forms;
  actual AI review and voluntary external participation are explained separately.
- `/research/{papers,datasets,benchmarks,workflows}/`: indexes and stable-ID detail
  pages. Record titles and metadata may appear before approval, clearly labeled
  as candidate records. Unapproved assertion wording is withheld from findings.

Only approved assertions are synthesized as findings. Every approved assertion
shows its exact evidence locator, source record, qualifications, assertion date,
and actual recorded review invocations. Historical imports keep the historical
label and original dates; they do not become current findings. A captured source
does not count as source-content verification. Search summaries follow the same
rules and do not include candidate assertion text.

Source and assertion permalinks are `/research/data/#source-<stable-id>` and
`/research/data/#assertion-<stable-id>`. The full ID is retained in the HTML `id`,
with percent encoding in URLs as needed. A stable ID is encoded as a single path
segment for detail pages; slashes never introduce extra directory levels.

Existing organizations point to `/company/<legacy-id>/`. The renderer never
rewrites those pages. It creates `/company/<stable-id>/` only for a new approved
organization that is the subject of an approved assertion. A candidate supplier
or an object-only mention does not create a profile.

## Publication-only editions and feeds

An edition entry must have `status: published` and a stable `release_id`. For the
current release it can reference the current context. An older immutable edition
provides its `graph`, `report`, and `policy` snapshots, plus optional `identity`.
The snapshot's report must have the same release ID and published/superseded
status. The renderer recomputes `publication_gate()` against that snapshot.
An asserted `ready` flag in edition metadata has no authority.

Only an actually passing published entry creates an edition HTML route at
`/research/state-of-ai-data-labs/editions/<release-id>/` or an RSS/Atom item.
`/research/feed.xml` and `/research/atom.xml` are valid empty feeds while there is
no published edition. A prelaunch framework does not become a fake announcement.

## Assets and reuse

The data page links to `research_graph.write_exports()` output at the site root
and the citation owner's `/publication/` assets. Approved-record JSON/CSV/SQLite
exports and the all-status evidence graph have distinct labels. The prepared
reproduction ZIP is described as preparation, with package-status and SHA-256
inventory links. An optional PDF is not assumed to exist. The citation owner and
coordinator write those assets; the renderer never invents an archive or DOI.

## Verification

```sh
python3 -m unittest discover -s tests -p test_research_pages.py -v
```

The tests cover truthful baseline routes, all 12 visible chapters, candidate
leakage, historical dates, source/assertion anchors, approved-subject-only company
profiles, escaping, forged edition gates, published feed routing, deterministic
output, URL encoding, and compact search entries. Synthetic approval receipts
exist only in test fixtures and never enter public source data.

Browser inspection should use a scratch static build with real shared CSS and
assets. Check desktop and 320 px widths, the report contents, candidate details,
data/source anchors, and review links. The coordinator runs full-artifact link,
accessibility, and shared-navigation checks after integration.
