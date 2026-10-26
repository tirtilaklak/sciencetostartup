# sciencetostartup

ScienceToStartup is a static, evidence-linked field guide to AI data organizations.
The current public site is https://sciencetostartup.com.

## Reviewed research and current dashboard

This repository began with the reviewed public source and distribution for Sites
version 31. That source snapshot comes from commit
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
- `data/company-events.json`: dated lawsuits, incidents, customer and workforce changes and filings, reviewed after dataset 2.5.0.
- Other `data/*.json`: public profiles, editorial context and source updates.
- `schema/`: data and relational contracts.
- `scripts/observatory.py`, `scripts/schema_def.py`: research and export builder.
- `scripts/build_public_snapshot.py`: build the approved public snapshot.
- `data/business-health.json`: sourced business observations, reporting cohorts and calculations for the interactive dashboard.
- `dist/`: generated current HTML, assets, JSON/CSV exports and portable SQLite database.
- `docs/research-id-crosswalk.json`: public profile aliases required by the builder.
- `design-system/`, `scripts/design_system.py`: design system tokens and the build of its stylesheet; see `design-system/README.md`.

## View or reproduce

Python's standard library is sufficient for the snapshot build. Node.js runs
the logic checks. No hosted database, API key or npm install is
required to view or build the dashboard.

```sh
python3 -m http.server 8765 --directory dist
python3 scripts/build_public_snapshot.py --verify
python3 scripts/build_public_snapshot.py --output build/public-snapshot
```

`--verify` builds in a temporary directory and requires it to match
`dist/manifest.json` byte for byte. It then hashes every file in `dist/` against
that manifest and fails on any changed, extra or missing file, so `dist/` holds
exactly what the builder produces. Normal output must use an empty directory;
the command never writes to `dist/`.

The original `observatory.py build` command is a research-release operation. It
requires the exact original raw research files, which are deliberately excluded
from this public repository. The public snapshot wrapper calls the same
validated `build()` function without changing or weakening that release check.
It reproduces an approved snapshot; it does not attest to a new research release.

CI runs the same checks on pushes to `main` and on pull requests:

```sh
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

The 119 unit tests cover the pipeline, the build, static pages, company events,
the business health data, Work routes, link health and a privacy scan of the
published text files and database. The nine logic checks run the page scripts
in Node against a DOM stub; they are not browser proof.
Historical comparison tests and local audit reports remain in the research
repository.

## Hosting

The live website is served by the `sciencetostartup` Cloudflare Worker with Static
Assets on the apex and www custom domains. Deployment publishes the reviewed
`dist/` build; a GitHub push alone does not trigger deployment.

The Worker staging omits the domain-level `_redirects` file because Workers
Static Assets accepts relative source paths. Equivalent zone redirects enforce
HTTPS and the apex hostname while preserving paths and queries. `_headers` is
deployed unchanged.

## Business health dashboard

The overview explores revenue growth, delivery margins, customer durability, paid
expert activity and cash resilience. It covers all 39 organizations, with 98 dated
observations linked to 65 sources, explicit missing values and a separate
hypothetical margin calculator. Employee and registered-expert counts are context.
The recommended north star is gross profit from repeat paying customers.

See [dashboard definitions and evidence limits](docs/business-health-dashboard.md).
The underlying research remains dataset v2.5.0; the October 23 dashboard curation
does not imply all source material was freshly verified.

## Owner steps

Analytics is Cloudflare Web Analytics, injected at the edge and cookieless.

1. Search. Verify the domain in Google Search Console and Bing Webmaster Tools,
   and submit `https://sciencetostartup.com/sitemap.xml` in each.
2. Dataset corrections. Corrections that need a new dataset version are listed
   in `docs/pending-2.5.1-corrections.md`. Release them from the research
   repository; this repository pins dataset 2.5.0.
3. Deploying. Build into an empty directory, replace `dist/` with it, run the
   checks above and commit. Then deploy `dist/` to the `sciencetostartup`
   Worker, staging it without `_redirects` as described under Hosting.
   Pushing to GitHub does not deploy.

   ```sh
   python3 scripts/build_public_snapshot.py --output build/release
   rm -rf dist && mv build/release dist
   python3 scripts/build_public_snapshot.py --verify
   ```
