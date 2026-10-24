# sciencetostartup

ScienceToStartup is a static, evidence-linked field guide to AI data organizations.
The current public site is https://sciencetostartup.com.

## Where this source came from

This repository began as the reviewed public source and distribution for Sites
version 31. That snapshot comes from commit
`65e67210b80abc2b93d5f84a34a3975abbb03cc0`; `SOURCE_PROVENANCE.json` records
the source-file hashes at that import. Later commits changed the pages and
menus, so those hashes describe the starting point only. The GitHub history
starts with this repository's existing initial commit. Earlier Sites Git
history was not imported.

The existing MIT license is preserved. The snapshot includes the already-public
research data, official assets and their provenance. The alumni outreach
directory is no longer published or tracked here. It excludes raw research archives, unpublished personal records,
internal reports, credentials, browser output and deployment configuration.

## Files

- `web/`: editable HTML, CSS, JavaScript and local assets.
- `data/canonical.json`: authoritative research dataset 2.5.0.
- `data/work-routes.json`: curated Work routes, including reviewed additions and availability checks.
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

## How the page is built

`build()` in `scripts/observatory.py` turns `web/` and the data into `dist/`.

- CSS is inlined into `dist/index.html`: `style.css` first, then the files in
  `REDESIGN_CSS`, then `icons.css`. Between two equally specific rules, the
  later file wins.
- `icons.js` runs first in its own tag. The other scripts join into one
  classic script in this order: `link-health.js`, `app.js`, `editorial.js`,
  `work-v3.js`, then the files in `PRESENTATION_JS` (`work-v4.js`,
  `profiles-v2.js`, `source-updates.js`, `site-nav.js`). When two files declare
  a function with the same name, the later one is the one that runs.
- That script and the page data go to content-hashed files,
  `dist/js/app.<hash>.js` and `dist/js/data.<hash>.js` (the name changes when
  the content changes). They load after the first paint. The research dataset
  stays inline in `index.html` as JSON.
- `scripts/static_pages.py` writes the plain pages from the same data.

## View or reproduce

Python's standard library is sufficient for the snapshot build. Node.js is used
by some optional logic checks. No hosted database, API key or npm install is
required to view or build the dashboard.

```sh
python3 -m http.server 8765 --directory dist
python3 scripts/build_public_snapshot.py --verify
python3 scripts/build_public_snapshot.py --output build/public-snapshot
```

`--verify` builds in a temporary directory and checks every payload against the
checked-in public release manifest. Normal output must use an empty directory;
the command preserves the reviewed `dist/` files. After you change `web/`,
rebuild `dist/` and commit it with your change:

```sh
rm -rf build/snap && python3 scripts/build_public_snapshot.py --output build/snap
rm -rf dist && cp -r build/snap dist && rm -rf build
```

The original `observatory.py build` command is a research-release operation. It
requires the exact original raw research files, which are deliberately excluded
from this public repository. The public snapshot wrapper calls the same
validated `build()` function without changing or weakening that release check.
It reproduces an approved snapshot; it does not attest to a new research release.

The included standalone Python unit modules can be run with:

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/js_logic.py
python3 tests/company_search_prefix_logic.py
```

CI runs those three commands and `--verify`. The suite has 82 unit tests. More
Node logic checks run by hand: `tests/redesign_checks.py`,
`tests/revision_work_logic.py`, `tests/work_route_summary_logic.py`,
`tests/revision_app_logic.py`, `tests/reliability_copy_context_logic.py` and
`tests/reliability_failure_state_logic.py`. Some of them pin counts from the
current data, so a research update may need new expected values. Historical
comparison tests and local audit reports remain in the research repository.

## Hosting

The live website remains on the existing ChatGPT Sites project through
Cloudflare. GitHub is the source repository and reviewed backup. No deployment
workflow or hosting migration was added; pushing this repository does not change
our configured Sites deployment.

A deploy must upload all of `dist/`, including `dist/js/`: the app page
(`index.html`) loads its scripts from there. Those file names change with their content, so
`web/_headers` and `vercel.json` let browsers cache them for a year.
