# sciencetostartup

ScienceToStartup is a static, evidence-linked field guide to AI data organizations.
The current public site is https://sciencetostartup.com.

## Research publication

The new `/research/` hub connects readable paper, dataset, benchmark and workflow
records with claim-level evidence, original source versions and reusable exports.
`/research/state-of-ai-data-labs/` is the complete living report route;
`/research/data/` contains the evidence ledger, citations and prepared archive,
and `/review/` accepts source-backed corrections, section review and reuse.
Essential content and downloads work without JavaScript. Both site search
implementations link directly to native research and organization pages.

The comprehensive weekly series is **prelaunch**. The initial approved evidence
is a small, separately AI-reviewed baseline, including abstract-level paper
records; these do not count as full-source paper reviews. Historical field-guide
evidence retains its dates and labels. No published edition, completed launch
audit, human peer review or DOI is claimed. Coverage is computed from the graph,
and code enforces the declared launch floors and substantive-report gates.

New research is versioned under `data/research/`, independently of canonical
v2.5.0. The public projection excludes private fields and personal contact data.
One release manifest generates citations, Zenodo/GitHub/Hugging Face metadata,
schemas, JSON/CSV/SQLite exports, checksums and a standalone reproduction package.
The optional PDF preparation uses ReportLab; ordinary builds only verify and
copy its prepared bytes and require no network, credentials or extra Python
packages. Independent source review is identified as **Separate AI review**.

Daily preparation targets 16:00 Pacific; the sole weekly release check targets
Monday 09:00, with the preceding Friday 17:00 captured-source cutoff. Native
Codex automations in the implementation chat run on the available local host;
missed runs are handled as delayed catch-up, never backdated publications.
Zenodo and Hugging Face remain in **prepare-only** mode until accounts connect.
The report stays held until coverage, real holdout audits, evidence, privacy and
technical checks pass. Archive publication, website activation and mirror status
are recorded separately, using a locked, recoverable journal.

See [the shared contract](docs/research/CONTRACT.md),
[operations](docs/research/operations.md),
[archival publication](docs/research/publication.md),
[evidence methods](docs/research/evidence.md),
[external identity updates](docs/research/external-profile-updates.md) and
[contribution policy](CONTRIBUTING.md). No reviewer invitations are sent by the
implementation or daily preparation.

The homepage introduces two equal journeys: understand AI data companies and find
paid AI training work. Its portrait collage preserves all three faces in responsive
WebP derivatives. Two examples show an offer-led company and a recently reviewed
public work route; stale work promotion falls back to an approved program or an
evergreen browse link. Without JavaScript the evergreen link remains available.

The interactive guide lives at `/explore/`; existing root hash links redirect there.
A compact, versioned summary powers discovery. Company evidence loads on demand,
with release identity, integrity and navigation guards. The full research JSON and
SQLite remain unchanged downloads. Script and evidence failures offer retry and
plain company, work and method pages rather than misleading empty results.

## Where this source came from

This repository began with the reviewed public source and distribution for Sites
version 31. That source snapshot comes from commit
`65e67210b80abc2b93d5f84a34a3975abbb03cc0`; `SOURCE_PROVENANCE.json` records
the source-file hashes at that import. Later commits changed the pages and
menus, so those hashes describe the starting point only. The GitHub history
starts with this repository's existing initial commit. Earlier Sites Git
history was not imported.

The snapshot includes the already-public research data, official assets and
their provenance. See License below for what each license covers. The alumni
outreach directory is no longer published or tracked here. It excludes raw research archives, unpublished personal records,
internal reports, credentials and browser output. `deployment.json` records only
sanitized public deployment settings; credentials never enter the repository.

## Files

- `web/`: editable HTML, CSS, JavaScript and local assets.
- `data/canonical.json`: authoritative research dataset 2.5.0.
- `data/work-routes.json`: curated Work routes, including reviewed additions and availability checks.
- `data/editorial-release.json`: separately versioned review identity, approved counts and publication policy; canonical v2.5.0 stays byte-identical.
- `EDITORIAL.md`: the approved 5–7 hour weekly review workflow and candidate-only checks.
- `scripts/presentation.py`, `scripts/home.py`: reproducible summaries, evidence graphs and promotion templates.
- `web/data-runtime.js`: the single asynchronous route owner and guarded evidence loading.
- `release-assets/`: checksummed assets from the prior two public runtime generations.
- `deployment.json`, `scripts/release_artifact.py`: exact-artifact upload preparation and short-lived asset upload authorization.
- `data/company-events.json`: dated lawsuits, incidents, customer and workforce changes and filings, reviewed after dataset 2.5.0.
- `data/business-health.json`: sourced business observations, reporting cohorts and calculations for the interactive dashboard.
- Other `data/*.json`: public profiles, editorial context and source updates.
- `schema/`: data and relational contracts.
- `scripts/observatory.py`, `scripts/schema_def.py`: research and export builder.
- `scripts/static_pages.py`: plain pages for search engines and link previews, plus `sitemap.xml`.
- `scripts/build_public_snapshot.py`: build the approved public snapshot.
- `dist/`: the built site. It must match a fresh build byte for byte. It holds
  `index.html`, its script bundles in `js/`, the plain pages (`company/<id>/`,
  `companies/`, `work/`, `method/`, `404.html`), assets, JSON/CSV exports and
  a portable SQLite database.
- `docs/research-id-crosswalk.json`: public profile aliases required by the builder.
- `design-system/`, `scripts/design_system.py`: design system tokens and the build of its stylesheet; see `design-system/README.md`.

## How the page is built

`build()` in `scripts/observatory.py` turns `web/` and the data into `dist/`.

- CSS is inlined into `dist/explore/index.html`: `style.css` first, then the files in
  `REDESIGN_CSS`, then `icons.css`. Between two equally specific rules, the
  later file wins.
- `icons.js` runs first in its own tag. The other scripts join into one
  classic script in this order: `link-health.js`, `app.js`, `editorial.js`,
  `work-v3.js`, then `INITIAL_PRESENTATION_JS` (`work-v4.js`,
  `profiles-v2.js`, `source-updates.js`, `site-nav.js`).
  When two files declare a function with the same name, the later one is the
  one that runs. `data-runtime.js` owns asynchronous navigation, validated
  context installation and readiness. The logical test order in `PRESENTATION_JS`
  also includes `business-health.js`; production loads it as an inert, hashed
  factory with native subresource integrity. Company, overview and archive routes
  initialize it once before installing full evidence. Directory and work browsing
  use the compiled financial models without downloading the dashboard module.
- That script and the page data go to content-hashed files,
  `dist/js/app.<hash>.js` and `dist/js/data.<hash>.js` (the name changes when
  the content changes). Head preloads discover them early; execution remains
  sequential after the first paint. A compact bootstrap stays inline in the
  interactive page. Search text, company evidence and the full archive load
  through versioned presentation assets when requested.
  Small route hints in the document head overlap the initial research route's
  byte request with app loading. They cannot install or render evidence;
  the route owner still verifies the digest, release and current navigation.
- `scripts/static_pages.py` writes the plain pages from the same data.

## View or reproduce

Viewing the checked-in static site requires only a file server. Rebuilding uses
Python and Node.js 22 or later. Run `npm ci` once to install the pinned frontend
packager and QA tools. Python builds the research exports and presentation models;
esbuild minifies the classic JavaScript without bundling or hiding its globals.
The deployed site remains static and requires no application server or API key.

The builder explicitly enables SQLite secure deletion so different library
defaults do not leave different bytes in unused database space. Exact snapshot
verification passes with SQLite 3.46.1 and 3.53.1.

```sh
python3 -m http.server 8765 --directory dist
npm ci
python3 scripts/build_public_snapshot.py --verify
python3 scripts/build_public_snapshot.py --output build/public-snapshot
```

`--verify` builds in a temporary directory and requires it to match
`dist/manifest.json` byte for byte. It then hashes every file in `dist/` against
that manifest and fails on any changed, extra or missing file, so `dist/` holds
exactly what the builder produces. Normal output must use an empty directory;
the command never writes to `dist/`. After you change `web/` or `data/`,
rebuild `dist/` and commit it with your change:

```sh
rm -rf build/snap && python3 scripts/build_public_snapshot.py --output build/snap
rm -rf dist && cp -r build/snap dist && rm -rf build
python3 scripts/build_public_snapshot.py --verify
```

The original `observatory.py build` command is a research-release operation. It
requires the exact original raw research files, which are deliberately excluded
from this public repository. The public snapshot wrapper calls the same
validated `build()` function without changing or weakening that release check.
It reproduces an approved snapshot; it does not attest to a new research release.

CI runs the same checks on pushes to `main` and on pull requests:

```sh
python3 -m pip install -r requirements-qa.txt
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/build_public_snapshot.py --verify
python3 tests/js_logic.py
python3 tests/company_search_prefix_logic.py
python3 tests/redesign_checks.py
python3 tests/revision_app_logic.py
python3 tests/revision_work_logic.py
python3 tests/work_route_summary_logic.py
python3 tests/reliability_copy_context_logic.py
python3 tests/reliability_failure_state_logic.py
python3 tests/risk_section_logic.py
```

The unit tests cover the pipeline, the build, the design system tokens
(the same check as `python3 scripts/design_system.py --check`), download sizes,
static pages, company events, the business health data, Work routes, the Paid
work page, site search, link health and a privacy scan of every file in `dist/`.
The nine logic checks run the page scripts in Node against a DOM stub; they are
not browser proof. Some of them pin counts
from the current data, so a research update may need new expected values.
Historical comparison tests and local audit reports remain in the research
repository.

## Hosting

The live website is served by the `sciencetostartup` Cloudflare Worker with Static
Assets on the apex and www custom domains. Deployment publishes the reviewed
`dist/` build; a GitHub push alone does not trigger deployment.

A deploy must upload all manifested public assets, including `dist/js/` and
`dist/presentation/`. The homepage and `/explore/` use different entry points;
company evidence and the full search index load on demand. Hashed file names
change with their content, so `web/_headers` lets browsers cache them for a year.

The Worker staging omits the domain-level `_redirects` file because Workers
Static Assets accepts relative source paths. Equivalent zone redirects enforce
HTTPS and the apex hostname while preserving paths and queries. `_headers` is
passed unchanged as asset configuration, rather than served as a public file.

The release sequence is deliberate:

1. Freeze one complete build and run unit, logic, exact-build, payload, browser
   and three-run mobile performance gates against that directory. Record manual
   accessibility checks separately; an automated score does not certify VoiceOver.
2. Commit the matching source and `dist/`. Prepare the upload with
   `python3 scripts/release_artifact.py prepare --dist <frozen-directory> --output <receipt-directory> --source-commit <commit>`.
   The receipt binds source, build, editorial release, manifest and sanitized
   deployment configuration. Preparation and upload both verify every asset.
3. Create an asset upload session through the connected Cloudflare API. Keep
   short-lived authorization files outside this repository. Upload those exact
   bytes once, create an assets-only version, and test its immutable version URL.
   Preserve `deployment.json`'s existing non-versioned logs and analytics settings.
4. Confirm the current production predecessor, then promote that tested version
   to 100 percent. Verify identity, routes, source dialogs, downloads, redirects
   and headers again. If a functional or identity check fails, immediately restore
   the predecessor at 100 percent and record the failure.

Keep the prior two production generations in `release-assets/generations.json`,
including their hashed JavaScript and presentation JSON. Add the outgoing
generation before the next build; never prune assets from a frozen artifact.
The release receipt must add the Cloudflare version, deployment and post-release
check results. A GitHub push or a successful upload is not a production release.

Cloudflare Web Analytics is injected at the edge and sets no cookies.

## Business health dashboard

The overview starts with a revenue ledger: actual revenue, annualized pace and
growth. Each row keeps its period, business scope and source type. Select a figure
to inspect the evidence and history. Advanced opens the full metric charts.
Reporting periods, currencies and business scopes stay separate. The complete 39-organization
coverage grid and detailed evidence remain available in disclosures. There is no
composite score or hypothetical financial calculator in the interface.

The evidence layer contains 113 dated observations across 28 organizations, linked
to 67 source records. On 28 October 2026, selected financial documents were read
again and thirteen new source claims added with exact excerpts, locators, response
hashes and separately validated quantities. The source-check ledger records 26
checks (including a duplicate source alias and an upcoming-results notice): 23
content checks, one availability-only check and two unavailable sources.

Paid-work verification requested all 135 recorded route URLs. Of these, 67 received
content review, including 55 compensation checks; 61 had link-only checks and seven
were blocked. Link reachability does not establish hiring or current pay. Each
route retains its own review scope, date and response receipt.

The underlying research remains dataset v2.5.0. New evidence is a validated
supplement, not a claim that the entire historical dataset has been re-audited.
See [dashboard definitions and evidence limits](docs/business-health-dashboard.md)
and [financial source checks](data/fresh-source-checks.json).

Cards, profiles, Compare and plain company pages use the same supplemental
financial selection. Mercor’s H1 $614M figure is identified as a Sacra estimate;
its $2B annualized figure retains an undisclosed gross/net basis. Operating
activity and registered networks stay separate from revenue and paid delivery.
