# sciencetostartup

ScienceToStartup is a static, evidence-linked field guide to AI data organizations.
The current public site is https://sciencetostartup.com.

## Reviewed public v30 snapshot

This repository preserves the reviewed public source and distribution for Sites
version 30. Its source snapshot comes from commit
`8bc0017148bcd37bf4410135c204cea713616f0d`; `SOURCE_PROVENANCE.json` records
individual source-file hashes. The GitHub history starts with this repository's
existing initial commit. Earlier Sites Git history was not imported.

The existing MIT license is preserved. The snapshot includes the already-public
research data, verified adult outreach projection, official assets and their
provenance. It excludes raw research archives, unpublished personal records,
internal reports, credentials, browser output and deployment configuration.

## Files

- `web/`: editable HTML, CSS, JavaScript and local assets.
- `data/canonical.json`: authoritative research dataset 2.5.0.
- Other `data/*.json`: public profile, editorial, Work, outreach and source context.
- `schema/`: data and relational contracts.
- `scripts/observatory.py`, `scripts/schema_def.py`: unchanged v30 builder.
- `scripts/build_public_snapshot.py`: build the approved public snapshot.
- `dist/`: exact v30 HTML, assets, JSON/CSV exports and portable SQLite database.
- `docs/research-id-crosswalk.json`: public profile aliases required by the builder.

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
```

Historical comparison tests and local audit reports are not part of this public
snapshot. The snapshot includes 46 standalone unit tests, rather than the full
private/local research verification environment.

## Hosting

The live website remains on the existing ChatGPT Sites project through
Cloudflare. GitHub is the source repository and reviewed backup. No deployment
workflow or hosting migration was added; pushing this repository does not change
our configured Sites deployment.
