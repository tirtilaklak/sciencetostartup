# sciencetostartup

ScienceToStartup is a static, evidence-linked field guide to AI data organizations.
The current public site is https://sciencetostartup.com.

## Reviewed public v31 snapshot

This repository preserves the reviewed public source and distribution for Sites
version 31. Its source snapshot comes from commit
`65e67210b80abc2b93d5f84a34a3975abbb03cc0`; `SOURCE_PROVENANCE.json` records
individual source-file hashes. The GitHub history starts with this repository's
existing initial commit. Earlier Sites Git history was not imported.

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
- `scripts/build_public_snapshot.py`: build the approved public snapshot.
- `dist/`: exact v31 HTML, assets, JSON/CSV exports and portable SQLite database.
- `docs/research-id-crosswalk.json`: public profile aliases required by the builder.
- `design-system/`, `scripts/design_system.py`: design system tokens and the build of its stylesheet; see `design-system/README.md`.

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
the command preserves the reviewed `dist/` files.

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

The snapshot includes 55 standalone unit tests and public logic checks. Historical
comparison tests and local audit reports remain in the research repository.

## Hosting

The live website remains on the existing ChatGPT Sites project through
Cloudflare. GitHub is the source repository and reviewed backup. No deployment
workflow or hosting migration was added; pushing this repository does not change
our configured Sites deployment.
