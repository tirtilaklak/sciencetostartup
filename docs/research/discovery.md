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
provides complete `graph`, `report`, `policy`, and `identity` snapshots. Compact
entries bind a committed `data/research/editions/` JSON file through
`snapshot_path` and its exact-file `snapshot_sha256`. Missing or altered historical
inputs fail the build; local scheduler caches are not publication history.
The snapshot's report must have the same release ID and published/superseded
status. The renderer recomputes `publication_gate()` against that snapshot.
An asserted `ready` flag in edition metadata has no authority.

Only an actually passing published entry creates an edition HTML route at
`/research/editions/YYYY-MM-DD/` or an RSS/Atom item. Corrections to an edition
use a new revision URL such as `YYYY-MM-DD.r2/`, preserving the original.
`/research/feed.xml` and `/research/atom.xml` are valid empty feeds while there is
no published edition. A prelaunch framework does not become a fake announcement.

## Assets and reuse

The data page links to `research_graph.write_exports()` output at `/research/exports/`
and the citation owner's `/publication/` assets. Public-projection and graph JSON/CSV/SQLite
exports retain explicit approved and historical states; proposed assertion
wording is excluded. The prepared
reproduction ZIP is described as preparation, with package-status and SHA-256
inventory links. An optional PDF is not assumed to exist. The citation owner and
coordinator write those assets; the renderer never invents an archive or DOI.

Actual accepted corrections have their own readable archive at
`/research/corrections/` and RSS/Atom feeds under that path. The registry starts
empty; pending submissions do not become published corrections or reviews.

## Verified public HTTP access

The research infrastructure release is Cloudflare version 15, build
`2bee3851885cc35983a0`, from the reviewed source in PR #11. Its immutable preview
and production manifests match. Canonical v2.5.0 JSON and SQLite are unchanged.
The comprehensive research edition remains held; this is an infrastructure and
preparation release, with no registered research DOI.

The zone's Browser Integrity Check rejects default Python HTTP clients. A
configuration rule disables that header heuristic only for GET/HEAD requests to
the public research pages, profiles and exports. Existing WAF and DDoS controls
remain active. Ruleset `13b1723e38fc47f88b17880e5d40a696`, rule
`5b57752520f3472db081585b61f7bfa7`, reference `public_research_http_clients`, records
the setting. Default Python `urllib` successfully read eight public research and
download URLs after the change. Six named search/agent user agents also received
usable research HTML. These checks do not establish actual engine indexing or
answer citations; those measurements remain unknown.

Cloudflare's managed `workers.dev` preview host still requires an application
user agent. Use a descriptive value such as
`ScienceToStartup-ReleaseVerification/1.0 (+https://sciencetostartup.com/method/)`
for preview checks. No browser impersonation is needed.

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
