# Citation and publication preparation

Ordinary builds call `write_publication_assets(context, output)` from
`scripts/research_citations.py`. This is an offline standard-library operation:
no login, credential discovery, HTTP request, external account creation or
publication occurs. The legacy authoring policy retained in
`data/research/policy.json` remains `prepare_only`; the authorized first launch
uses a separate private `publish_enabled` policy whose reviewed release adapters
act only after their applicable gates pass. After verified publication, the
authenticated `data/research/published-source.json` selector chooses the public
frozen edition in `replay_only` mode before private authoring inputs are opened.
This replay grants no authority for a fresh publication. The first-launch
scientific checkpoint has
accepted coverage, reference and screening audits, and matching report synthesis;
the [screening admission](first-edition-screening-review.md) explicitly retains
the known-reference repeat, operational deviations and evidence limits. It does
not establish an unseen holdout or pristine access-mode compliance. Privacy and
exact-artifact technical checks remain mandatory for publication and activation.

Account authentication, draft creation, production publication, anonymous public
file verification and mirror writes are separately evidenced operations.
Sandbox drafts and reserved DOIs do not establish a production publication.
Credentials and operational journals stay outside the public checkout. Consult
the served `/research/` hub, `/publication/package-status.json` and
`/publication/current-metadata.json` for that edition's identity, archive status
and citation; website and mirror receipts establish their respective outcomes.

The generated `publication/` directory contains a full text report, standalone
offline HTML and evidence appendix, citations in BibTeX, RIS, CSL JSON and Citation File Format, metadata,
readiness, a privacy-filtered dataset in equivalent JSON/CSV/SQLite, a deterministic
ZIP archive, an internal checksummed manifest, and prepared Zenodo/Hub metadata.
`package-status.json` keeps archive, website, GitHub and Hugging Face states
separate. A built site or mirror does not establish permanent archival publication.

Current graph projection 1.2.0 retains the privacy boundary introduced in 1.1.0,
which omits private local reading-ledger filenames embedded in
review notes. It retains the surrounding scope and limitations, actual review
identity and time, verdict, source IDs and exact scientific assertion digests.
The private original review records remain unchanged. An unrecognized local path
holds export for inspection; relative repository locators remain usable.
Graph export manifests record this projection version. Frozen earlier archives
retain their original projection and reproduction recipe.

Prelaunch citation files identify a preparation snapshot. They omit registered
DOI and publication-date fields. A reserved version DOI may appear only in the
explicit note “Reserved version DOI (not registered)”; it is never placed in a
registered DOI citation field. Published citation metadata requires the authoritative final
gate and an actual published archive receipt, including the release identity,
artifact digest, record URL and confirmation date. A real publication date is
emitted only when supplied by the archive; a source or verification date is never
substituted for it. The publisher comes from `data/public-identity.json`.

## Separate report synthesis review

Approved source assertions do not by themselves approve an analytical synthesis.
`data/research/report-reviews.json` records actual evidence-auditor and adversarial
report reviews, from distinct invocations, against the exact report-content and
approved-graph digests. These are separate AI reviews, not human peer review.
`schema/report-review.schema.json` documents the registry and accompanies the
archive. The review registry also travels with the source-context policy.

The synthesis digest excludes only lifecycle status, the edition ledger and archive
outcomes, avoiding a circular dependency on publication receipts. Changing report
wording, finding bindings or the graph invalidates review readiness. Unreviewed
executive findings are withheld. Passing synthesis review cannot substitute for
coverage floors, frozen-core disposition, the actual reference and screening
audits under their versioned methods, source cutoff rules or actual archival
publication.

## Public projection and equivalence

Canonical dataset 2.5.0 and its legacy downloads remain byte-identical. The new
archive contains independently versioned public projection **1.2.0**, with the
canonical data and public supplemental graph as inputs. The projection omits raw
inputs/caches/full-text fields, source quote fields and structured contact fields.
Email patterns are redacted throughout nested text, including the known legacy
personal email. This is a broad safeguard, not an allowlist for other addresses.
The archive does not redistribute company imagery, logos or scraped source bodies.
The graph projection publishes only approved assertions and explicitly historical
descriptions. Candidate and rejected assertion wording and their exclusive review
receipts remain private. Entity/source metadata can still describe coverage gaps.
The source manifest uses this same public allowlist.

`clean-dataset.json` is the authoritative structured projection. CSV and SQLite
share the lossless `projection_rows` representation:

| Column | Meaning |
| --- | --- |
| `collection` | A root property, or `canonical.<property>` / `graph.<property>` |
| `position` | `-1` for the collection declaration; otherwise zero-based position |
| `kind` | `array` or `value` declaration; `record` for an actual JSON value |
| `value_json` | UTF-8 JSON value, retaining booleans, nulls, nested objects and arrays |

An empty array still has a declaration row. An ordinary object or scalar has one
record. This preserves data types and empty collections. There is no extra CSV
index column. SQLite has one `projection_rows` table with the same columns and a
primary key on `(collection, position)`. Read it using:

```sql
SELECT collection, position, kind, value_json
FROM projection_rows ORDER BY collection, position;
```

`projection_from_rows()` reconstructs the JSON document. The builder reads both
exports back and refuses any semantic difference. CSV readers should treat the
JSON column as data rather than evaluating it as a spreadsheet formula.

ZIP member names are sorted, timestamps are fixed to 1980-01-01, permissions are
stable, and the internal manifest records every member's SHA-256 and byte count
except itself. The archive contains that exact manifest. Ordinary preparation
defaults to stored ZIP members. Explicit preparation may select standard ZIP
deflate; no newer or proprietary compression is required by readers.
SQLite secure deletion, page size and insertion order are explicit. Fresh
preparation under a different SQLite or zlib runtime requires exact-build
verification. A frozen package is reused byte for byte, including SQLite, PDF and
ZIP bytes, without invoking any writer or compression runtime.

## Offline reading

Open `report.html`, then `evidence.html`. Report paragraph and executive-finding
evidence links use native relative anchors in the extracted edition. The appendix
contains a recorded-scope comparison table, entity dossiers, approved assertions
with qualifications and dates, explicitly labeled historical assertions, source
metadata and source locators, and recorded review receipts. It renders structured
financial/operational scope without converting unknown values to zero or inferring
performance. It adds no analytical judgments or review approvals.

The appendix has no JavaScript, remote assets, fonts or network requirement.
Source URLs remain optional citations; source bodies, third-party media and source
excerpts are not reproduced in the appendix. Existing concise evidence excerpts
and their hashes remain in the approved public machine projection. Candidates are
excluded from the public projection and unapproved wording is never a finding.
All generated appendix bytes belong to the same checksummed manifest as the report.

## Weekly-scale preparation and file limits

[Cloudflare Workers Static Assets](https://developers.cloudflare.com/workers/platform/limits/#static-assets)
allows **25 MiB (26,214,400 bytes) per file** on both Free and Paid, verified
2026-11-10. This applies independently to the ZIP, PDF, JSON, CSV, SQLite and HTML
downloads. `publication_asset_inventory(package_directory)` returns every exposed
file's byte length and an `oversized` map against that limit. Compression cannot
make an oversized separately exposed export acceptable; inspect the complete
inventory before deployment. Do not lower research gates or omit records to fit.

Use deflate only during explicit preparation, then bind ordinary builds to the
verified frozen result:

```python
package = freeze_publication_package(context, frozen_directory / "publication",
                                     archive_compression="deflate")
inventory = publication_asset_inventory(package)
if inventory["oversized"]:
    raise ValueError(inventory["oversized"])
context["prepared_package"] = str(package)
write_publication_assets(context, website_output)
```

Reserve the version DOI and prepare/review the PDF first when preparing an actual
archival publication, following the transaction below. This example does not
authorize publication. Existing stored frozen packages remain readable and are
never recompressed. Repeating a freeze verifies the first bytes, even if the
caller supplies a different compression preference.
Existing frozen editions also keep their original report and inventory; the new
offline appendix is created only when preparing a new package.

Storage evidence at `b351168` before this enhancement: the actual 173-approved-
assertion package was **15,132,935 bytes** with stored ZIP members. A separately
labeled **TEST-ONLY byte projection**, duplicating the current graph serialization
17 times without treating duplicate IDs as research, was 96,326,289 bytes stored
and 13,529,114 bytes deflated. That projection is storage evidence only, not an
approved graph or a forecast of final research size.

For a schema-valid workload, run:

```sh
python3 tests/publication_scale_fixture.py
python3 -m unittest discover -s tests -p 'test_publication_scale.py'
```

This **TEST-ONLY** fixture contains 150 paper works, 60 suppliers, 60 dataset
families and 20 benchmark families, ten assertions per entity (2,900 total),
8,700 explicitly synthetic three-role receipts, 12 chapters with 20 paragraphs
each, and an incompressible 1 MiB PDF byte allowance. It preserves the actual
privacy-filtered canonical projection. The fake PDF is not a render or review;
gate readiness is false, no audits exist, no files are written to `data/`, and
none of these fixture counts establish actual research coverage.

Measured on Python 3.9.6 / SQLite 3.54.0 / zlib 1.2.12:

| Asset | Bytes |
| --- | ---: |
| Deflated v2 archive, including all exports and offline appendix | 9,216,679 |
| JSON | 17,267,042 |
| CSV | 15,355,890 |
| SQLite | 17,047,552 |
| Offline evidence appendix | 16,447,720 |
| Source context | 14,442,778 |
| PDF byte allowance | 1,048,626 |

Every fixture asset fits the actual limit. These are measured workload bounds,
not a guarantee for arbitrarily long future records, appendices or PDF files.
Inspect each real edition's inventory; a larger edition must fail deployment
inspection until a complete hosting arrangement fits the constraints.

Before the v2 context upgrade, the actual edition was explicitly frozen with deflate and reused
under Python 3.9.6 / SQLite 3.54.0, Python 3.11.15 / SQLite 3.53.0, and Python
3.13.12 / SQLite 3.53.0. All 38 output file hashes matched, with SQLite writing,
PDF preparation, ZIP generation and HTTP access patched to fail if called.
All three installed runtimes used zlib 1.2.12; different zlib versions were not
executed in this check. Frozen reuse does not invoke zlib generation. The current
actual deflated archive with the appendix was 2,222,797 bytes in that check.
The v2 contract was separately exercised with a source-registry-selected
**TEST-ONLY** frozen fixture on those same three runtimes. All 38 output hashes
matched with SQLite, PDF and ZIP writers and HTTP access patched to fail.

## Frozen package transaction

Publication has three distinct inputs: research source, a DOI reservation, and
the exact prepared archive. Actual publication receipts are outcomes. They cannot
be inputs to their own PDF or archive checksum.

`context_digest()` binds graph, report text, release/edition identity, cutoff,
research readiness and audit metrics, policy, publisher identity and roles. The
reserved version DOI, deposition ID and API environment are also bound after
reservation. It excludes report lifecycle status, the editions publication ledger,
actual archive receipts and the final archive-only gate blockers. Changing
research text, audits, coverage, policy or reservation still invalidates the PDF
and frozen bundle. A registered version DOI must equal the reserved version DOI;
the concept DOI is a separate field and is never used as a version identifier.

Contract v2 introduced the owned-input recipe. Its `MANIFEST.json`,
`PREPARED.json` and PDF receipts explicitly carry `context_contract_version: 2`;
their existing envelope `schema_version` remains 1. In `source-context.json`,
`package_context.reproduction_inputs` binds the byte count and SHA-256 of these
owned scientific inputs, using exactly their archive member names:

- `research-graph.schema.json`, `report.schema.json`, `report-review.schema.json`,
  `report-audit.schema.json`, `publication-projection.schema.json`, and
  `publication-metadata.schema.json`;
- `research_graph.py` and `reproduce.py` (the latter comes from
  `scripts/reproduce_research_package.py`);
- `LICENSE` and `LICENSE-DATA.md`.

The package writer uses the same allowlist for the archived bytes. All ten inputs
must exist in every v2 package. Fresh preparation and unpublished reuse require
every current owned input too; missing inputs hold that edition. Test-only source
roots copy the same required owned inputs instead of bypassing this rule. Symlinked
inputs or parent components are rejected. Local source paths and file bodies do
not enter the descriptors. A schema correction, reproducer fix or license change
invalidates an unpublished v2 freeze even when its assertions and report wording are unchanged.
Fresh PDF preparation writes a contract6 receipt; older source PDF receipts cannot
be silently promoted into a new bundle. The v2 rules below describe preserved
historical packages.

The finalized v2 normalization identifies `graph_projection` as
`approved-historical-v1`. Its public source context contains exactly that public
graph projection, plus `input_commitments.graph_sha256`, an opaque hash of the
complete original input graph. Candidate/rejected wording and private graph/row
extensions cannot escape through `source-context.json`; changing an omitted draft
still changes the bound context. Approved assertion digests and actual receipts
are preserved. This finalization precedes any v2 publication; earlier unpublished
v2 preparations need a fresh context receipt and freeze.

A **typed, verified production archive receipt with the exact ZIP SHA-256**
permits historical v2 reuse. After verifying every frozen file and the ZIP, the
reader validates the pinned `package_context`: the exact ten-member allowlist,
non-null descriptors, hashes, byte counts and equality with `MANIFEST.json`.
It then compares the current canonical research core, including the original
graph commitment, with that frozen recipe. Current schema/reproducer/license
files may have changed or disappeared; they are never read for this replay.
The frozen recipe, source context, PDF and ZIP remain immutable. A sandbox receipt,
wrong artifact hash, bare `published` flag or caller option cannot select this
path. Changed research inputs still invalidate historical replay.
Historical replay cannot create a fresh freeze at a new target; prepare a new
edition from its prepublication source context instead.

A frozen package without the explicit context version is **legacy v1**. Its
original research-only digest is checked using its preserved historical
normalization and its exact original `source-context.json`, manifest, PDF and ZIP
remain byte-verified. It is never regenerated, rewritten or retrofitted with new
schema/code/license bytes. Published legacy builds use the frozen PDF directly;
they do not reread or rewrite its old source PDF receipt. Existing v1 release
journals retain their exact ZIP markers. Existing legacy reservation journals
retain their original source marker for explicit recovery. The current writer
preserves such a journal and stops before remote mutation when its authenticated
original frozen context is unavailable; it never creates a replacement deposit
by treating the current recipe as the old one. New reservation journals bind
context contract 6. A reservation and frozen package must use the same context
contract; a legacy reservation requires authenticated original-context recovery
before a transaction using a newer contract.

`freeze_publication_package(context, package_directory, archive_compression="stored")`
creates the package once; `archive_compression="deflate"` opts into level-9 ZIP
deflate at that explicit preparation step.
On a repeated call it verifies the existing package and never regenerates or
overwrites it. An incomplete prior freeze fails closed for inspection.
`MANIFEST.json` binds all ZIP members; `source-context.json` contains the exact
normalized public source inputs. `PREPARED.json` is outside the ZIP and binds
release ID, source digest, manifest digest, ZIP SHA-256 and length, and PDF
SHA-256 and length. Neither the ZIP itself nor publication/status receipts are
manifest members, so the package has no self-reference.

After publication, ordinary builds **must reuse** this exact package. They read
`context.prepared_package`, `report.archive.bundle_path`, or the default
`data/research/releases/<release_id>/publication`. A path inside the checkout
must be exactly that edition's release directory or its `publication` child.
An external directory must be explicitly supplied with an absolute path.
Traversal, unsafe members, unlisted inventory and symlinked member files are rejected. The builder
verifies the source contract, manifest, all files, PDF and ZIP bytes against the
actual archive receipt before copying them. It never rerenders the PDF or
reconstructs the archive to activate the published website.

The original `metadata.json`, `citation.*`, and `CITATION.cff` remain the frozen
prepublication files, including the reservation note. Live
`current-metadata.json`, `current-citation.*`, `current-CITATION.cff` and
`package-status.json` are outside the ZIP and reflect the actual production
archive receipt. The public website should link those current citation files.
Website deployment and mirrors remain separate states.

## Source-selected prepared bundle

`prepared_package_selection(context, root)` optionally reads
`data/research/prepared-packages.json` and returns a context overlay. This is a
small committed source registry, not a machine-local cache or environment
variable. Its shape is:

```json
{
  "schema_version": 1,
  "packages": [
    {
      "release_id": "research-YYYY-MM-DD.1",
      "path": "data/research/releases/research-YYYY-MM-DD.1/publication",
      "context_contract_version": 2,
      "context_sha256": "<64 lowercase hex characters from PREPARED.json>",
      "manifest_sha256": "<64 lowercase hex characters from PREPARED.json>",
      "archive_sha256": "<64 lowercase hex characters from PREPARED.json>"
    }
  ]
}
```

Replace the illustrative hash placeholders with the actual completed contract
values. Each release ID is unique. Paths must be exactly the named release's
committed directory or its `publication` child; absolute paths, traversal,
unrelated paths, symlinks in any component, duplicate JSON keys and unknown fields
are rejected. The selector verifies the selected bundle against all three pinned
hashes, its context version and its applicable source contract: current inputs for
unpublished preparation, or the typed-receipt-gated historical recipe above. An absent registry
or unmatched release selects nothing. A selected missing, partial or stale bundle
fails closed; it is never silently regenerated.

`build_context` preserves `root` and applies the selector after graph, report,
gate and policy are complete. Its explicit preparation option skips selection:

```python
# At the end of build_context(root, *, select_prepared=True):
context["root"] = Path(root)
if select_prepared:
    from research_citations import prepared_package_selection
    context.update(prepared_package_selection(context, root))
return context
```

Ordinary builds select strictly. Explicit preparation obtains the
source context with selection disabled, prepares/reviews the current-contract PDF, then calls
`freeze_publication_package(..., archive_compression="deflate")` on the intended
edition path even before that path exists. Only after the freeze verifies should
the coordinator add/update that release's registry entry using its actual
`PREPARED.json` hashes, preserving entries for other releases. A prelaunch bundle
may be selected too; selecting it establishes no publication readiness or DOI.

The explicit freeze function strips any inherited build-selection overlay before
generating a different new target. Registry pointers, absolute local paths and
expected-hash overlays are excluded from both context contracts, so committing a
selection after preparation cannot create a self-referential digest cycle.

## Prepared PDF

Static builds have no PDF dependency. `scripts/research_pdf.py` is an optional
ReportLab preparation step using embedded Bitstream Vera and deterministic PDF
metadata. It renders all report paragraphs, evidence IDs, coverage, limitations
and reproduction instructions from the same context. The full machine-readable
evidence remains beside the PDF in the archive.

After following the PDF skill's artifact marker requirement, prepare using the
bundled document Python or another environment with ReportLab installed:

```sh
python3 scripts/research_pdf.py --output data/research
pdftoppm -png data/research/report.pdf /tmp/research-report
```

Inspect the rendered pages and extracted text. Commit the prepared `report.pdf`
and `report-pdf.json` together only after that review. The receipt binds both PDF
bytes and source context. Static builds verify both digests and fail on a stale
PDF. Without a PDF, local packages are still prepared and explicitly report the
missing step; archival publication is blocked.

## Explicit external adapters

New packages use source-context contract 6. The contract 3 evidence rules remain:
live report pages, offline HTML,
Markdown and the PDF apply the same approved-evidence rule to every report block.
The machine-readable source context also replaces held paragraphs with an explicit
gap and omits draft executive judgments pending separate synthesis review. Its
input commitments retain hashes of the original graph and normalized authoring
report, so changing withheld draft content still invalidates an unpublished freeze.
The report commitment excludes publication lifecycle outcomes and retains the
reserved version identity; publishing an existing archive cannot create a digest
cycle.

The package includes `LOCATORS.md` with extraction conventions and the short
`executive-brief.html` and `executive-brief.md`. Brief findings use the same review
gate, qualifications and local evidence anchors as the complete report. Essential
content and navigation need no JavaScript.

Contracts 1 and 2 remain readable. Contract 2 retains its original reproduction
allowlist; the new locator guide is not retroactively required in older archives.
Confirmed production archives replay their exact pinned recipe and bytes. Pending
packages and uploads still require current matching inputs. Reservation journals
retain their original contract and marker across interruption and recovery.

`scripts/research_publish.py` provides `PublicationPlan`, `Release`, `Journal`, `Zenodo`,
`GitHubMirror` and `HuggingFaceMirror`. These are deliberately separate from
static builds. Creating an adapter without the relevant credential raises a
clear connection requirement; it does not prompt, search the filesystem or
create accounts. Credentials stay in process memory, are sent only in bearer
headers, and never enter package files, state journals or URLs. The stdlib HTTP
transport rejects a remote link on a different API origin.

Before any external operation, `Release.verify()` re-executes the report owner's
authoritative gate. Zenodo operations require `archival_ready` (all research,
coverage, cutoff and quality requirements) and policy mode `publish_enabled`.
Final website readiness separately requires the actual public archive receipt;
this avoids making archive creation depend on an archive that already exists.
The adapter cannot lower thresholds, discard blockers or trust a forged cached
`ready` flag. Prepared PDF, exact manifest, context and ZIP member bytes must all
match. A scientifically held candidate or `prepare_only` policy cannot qualify.

The explicit caller first constructs a `PublicationPlan` with a reservation
journal **outside the source checkout**. `Zenodo(plan).draft()` creates/resumes
the deposit and reserves its version DOI before PDF preparation. It passes the
same authoritative research gate and `publish_enabled` policy check as a release,
but cannot upload or publish without a frozen bundle. The reservation journal is
bound to source inputs, excluding reservation outcomes. After rendering and
freezing, a separate release journal binds exact archive bytes. A concrete
sequence, only with verified account capabilities, passing gates and
`publish_enabled` policy, is:

```python
plan = PublicationPlan(context, outside_state / "reservation.json")
Zenodo(plan, token=token).draft()  # previous_id=<integer version record> for updates
context["report"]["archive"] = plan.reservation()
# Prepare/review PDF from this exact context; do not rebuild it after publication.
package = freeze_publication_package(context, frozen_directory / "publication")
release = Release(context, package, outside_state / "publication.json", reservation=plan)
zenodo = Zenodo(release, token=token)
zenodo.upload()
zenodo.publish()
context["report"]["archive"] = release.archive_receipt()
context["report"]["status"] = "published"
context["gate"] = publication_gate(context["graph"], context["report"], context["policy"])
write_publication_assets(context, website_output)  # exact frozen bytes + live receipt
```

Keep the reservation and publication journals for retries, and persist the
reservation/receipt overlays into the correct edition source context. The
exported receipt includes `bundle_path`; a tracked release package can instead
use the whitelisted edition path. This code is a protocol example, not a command
to bypass an account, scientific, privacy or exact-artifact technical gate.

`upload()` reconciles and uploads exact package files, and `publish()` publishes
only after all checks.
`draft(previous_id=<latest-version-record-id>)` creates a new version via the
official `newversion` action and follows the returned `latest_draft` link. It
does not use a concept DOI as a version ID. The adapter refuses an unrelated
outstanding draft. Stable upload names replace corresponding inherited files;
unexpected inherited files block publication pending explicit reconciliation.

The publication journal is bound to release ID and exact ZIP digest. Every remote
mutation records intent before the request. A lost create response is reconciled
by the unique package marker in account deposit metadata. Ambiguous/missing
matches block automatic retry. New-version recovery follows the original
record's draft link. Upload retries first compare remote names, lengths and MD5
checksums; matching files are skipped. Publish retries first inspect deposit and
public record state; a pending publish is not blindly repeated. Only a public
record with one matching version DOI, a distinct typed concept DOI, consistent
version record ID, and verified exact public files marks the archive published.
A reserved DOI remains `reserved_doi`, never `doi`, in draft journal state.
A fully verified production publication journal can authorize the same exact
historical recipe replay for mirror and reconciliation retries. An unconfirmed
lost-publish response stays current-input strict; source changes block it until
the original inputs are restored or a verified production receipt is available.
If a typed published source receipt survives a lost local journal, recovery only
reconciles its named existing record. Upload and new-version creation are blocked;
recovery cannot fall through to creating another DOI.
`archive_receipt()` exports a production-only receipt containing API origin,
environment, verification flag, aware UTC confirmation timestamp, version record
URL/ID, release identity, exact artifact digest, separate concept/version DOI
fields and unchanged reservation fields. Sandbox receipts cannot activate the
published website or authorize a production mirror.

GitHub and Hub mirrors require a remotely verified published archive journal
receipt. GitHub resumes a uniquely tagged draft release with the package marker,
verifies uploaded asset SHA-256, then publishes and re-reads public release state.
`GitHubMirror(..., source_commit=<approved full lowercase 40-character SHA>)`
requires an existing lightweight `research-<release_id>` tag pointing directly to
that exact commit. Create and verify that tag separately after committing the
matching approved source and build; the mirror never creates or moves tags.
The expected commit is durably bound to the mirror journal before remote access,
and the tag is checked before release work, before publication and after the final
public release-state read. Missing, annotated, moved or conflicting tags hold the
mirror. Preserve the journal and commit identity on retries.
The live source field and its one retained binding event must agree. Lost,
malformed or conflicting history holds before any tag read or rebinding; only an
untouched prepared mirror can establish its first binding. These local consistency
checks cannot authenticate a journal whose entire trusted state/history was rewritten.
An existing conflicting tag or asset blocks replacement. Hugging Face uses the
official optional `huggingface_hub` SDK, an existing dataset repository, a pinned
parent commit and manifest-first reconciliation. After commit, authenticated
downloads at one immutable commit verify archive and dataset bytes. Separate
anonymous downloads must then match all four payloads, including the dataset
card and manifest, at that same commit. The default SDK client pins the official
Hub endpoint and explicitly uses `token=False` for those public reads. Public
repository metadata alone cannot establish access to a gated dataset. Failed
public verification leaves a recoverable, unverified journal state; retrying
reconciles the existing commit. A lost commit response cannot silently create
duplicate commits. Mirror success never changes website production state.

The live Hub card is generated from the verified production archive receipt and
contains the exact edition DOI and citation. It is a destination artifact, separate
from the immutable preparation card inside the frozen package. A matching manifest
with a stale destination card requires one reconciled commit; retries authenticate
both files and anonymously verify all payloads at the resulting immutable commit.
The frozen report, citations, card and ZIP are never rewritten after publication.
Zenodo's remote description describes the research and rights; a preparation-time
status sentence must not become a permanent false statement that the record is
unpublished. The archival record supplies its actual publication status.

Zenodo reconciliation separately reads the open record and all four uploaded
payloads without credentials. Actual anonymous bytes must match the frozen files;
authenticated checksums alone cannot establish public download access. A published
record whose public verification fails stays `published_unverified` in the journal.
Its DOI is retained, mirrors and website activation stay held, and retries verify
that same record without creating or publishing another deposition.

New website activation, edition export and mirror authorization require
`anonymous_verified: true` in the production receipt. A legacy `verified` flag
alone grants no new activation. Historical frozen research bytes remain intact;
they never substitute for a current public-access verification outcome.

Unit tests use explicitly synthetic remote and gate fixtures to exercise failure
recovery. Actual account operations require their own scoped receipts; a passed
fixture cannot establish a successful draft write, upload, publication or public
download. Test fixtures are not review receipts, audit evidence or publication
records.

Official API references used for the implementation:

- [Zenodo REST API](https://developers.zenodo.org/) documents draft metadata,
  reserved DOI status, bucket uploads, file checksums, publication and versions.
- [GitHub Releases REST API](https://docs.github.com/en/rest/releases/releases)
  documents draft releases, version tags and publication state.
- [Hugging Face uploads](https://huggingface.co/docs/huggingface_hub/guides/upload)
  and [Hub client reference](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)
  document commits, existing repositories, explicit credentials and parent commits.

## One-time initial launch timing

On November 11, 2026 the user authorized publishing the first edition as soon as
all research and technical gates pass. Its actual source cutoff and release ID
are bound to a one-time authorization in the release policy. This exception changes
only the initial calendar: coverage, source capture, independent review, audit,
privacy, archive and exact-artifact requirements still apply. Capture and publication
times are never backdated. After the first edition, Friday 17:00 Pacific source
cutoffs and Monday 09:00 Pacific publication targets remain in force. Weekly
preparation explicitly clears the exception and stages a weekly edition.

## Versioned actual audit inputs

The authoritative publication gate dispatches versioned audit documents through
`research_audit_dispatch.py`. Exact UTF-8 audit and separate validation-receipt
bytes are loaded from `data/research/<kind>-audit.json` and
`<kind>-validation-receipt.json`. Their parsed and exact views must agree. The
independent trust records come exclusively from the separately reviewed
`audit-admissions.json` registry. An empty registry admits no execution. A summary,
fixture, self-nominated admission or unsupported schema version cannot clear a gate.

The admitted screening-v3 execution is a known-reference post-remediation repeat
over the exposed fixed269 workload. Its 197/200 recovery includes benchmark
25/25, paper 65/65, supplier-lead 50/50 and dataset 57/60. Selected-panel and
full-frame critical-attribution and unresolved-conclusive counters are zero.
It is not an unseen-reference holdout, population precision/recall,
discovery recall or final supplier qualification. Original200 sensitivity remains
separate, its contract remains false, and the original thirteen Unknown cases
are not all declared resolved. Prior held runs and original frozen inputs remain
retained. Admission discloses prior coordinator byte hashing and Source1's
execute-only/helper violation; it does not certify strict access-mode compliance,
global blindness, a complete historical transcript or independent engine
attestation. The [first-edition screening review](first-edition-screening-review.md)
preserves the exact scope, operational deviations and evidence limits.

Reference-v4 evaluates the disposition of original source-bound hypotheses in a
finite 200-assertion panel. Precision 1.0 and recall 0.96354 describe that panel,
not extraction, discovery or population recall, or the precision of all final
corrected outputs. The reference and screening requirements use separate actual
SUT runs; shared primary sources do not turn assertions and logical records into
the same evaluation unit. Actual completed source work and independent execution
admission remain required after prospective method review. Numerical floors are
unchanged.

Current-input reference validation requires the complete private input ledger for
withheld assertions. An archive's filtered projection cannot reconstruct their
mutable wording. Archival replay must identify itself as validation of the admitted
frozen context; it must never claim current-input withheld verification.

## Context contract V4 and offline audit scope

New packages pin the evidence-coordinate extractor and manifestation manifest,
versioned audit readers/schemas, dispatcher and independent admission registry.
V2/V3 keep their original member allowlists; verified historical packages retain
their stored recipes and bytes. No earlier PDF or archive is rewritten.

The offline reproducer authenticates the archive's exact audit/receipt/admission
and code pins, recomputes raw finite-panel calculations, and checks retained
reference findings against their scientific bindings in the public projection.
A passing archival context requires both actual audit documents. It reports
`live_private_withheld_records_revalidated: false` and
`raw_sources_revalidated: false`: those unavailable inputs are not reconstructed,
fetched implicitly, or treated as newly verified. Current-input readiness remains
the authoritative gate's separate responsibility with the complete private ledger.

Public projection1.2.0 includes only source rows bound by approved or historical assertions. A grouped review is projected to the retained assertion IDs and their exact evidence source IDs; its actual identity, verdict, scientific digest bindings and timestamp remain unchanged. Original full reviews and draft-only source records stay in the private intake. Stable website source anchors for withheld rows remain as metadata-only notices; they do not expose an obsolete source version or unapproved locator. This projection is distinct from canonical2.5.0 and does not rewrite previously frozen packages.

Contract5 introduced explicit graph projection1.2.0 in the owned recipe. Legacy projection selection reads only verified owned code/schema metadata and executes no package Python. Current credential matching preserves harmless identifier substrings while actual credential patterns remain excluded; historical redaction bytes stay unchanged for replay. The screening-v3 reader is installed separately from method adoption or actual audit completion. Its known-reference repeat requires prospective input/exposure review, fresh operational/source-check execution, exact originals, unchanged thresholds and a separately reviewed admission. Installing or testing that reader publishes nothing.

## Context contract 6: compact encoding

New freezes encode `source-context.json` as sorted UTF-8 JSON with compact
separators, strict finite numbers and one trailing line feed. Every JSON value,
audit document string, evidence binding and owned-input commitment remains
present. Projection1.2.0 and its privacy rules are unchanged. This removes
formatting whitespace so complete audit provenance fits static-file limits;
the actual final inventory must still pass every size check.

PDF receipts, reservation identities and archive context digests bind those
exact compact bytes. Contracts1–5 retain their original indented encoding and
frozen-recipe verification; fresh preparation accepts only contract6. Old
reservation journals require their original authenticated context rather than
silently migrating their reconciliation marker. Unpublished historical reuse
still checks current scientific inputs and owned recipe bytes. Published replay
continues to use its verified frozen recipe. No old package is rewritten.

## Public checkout current-edition selection

After the actual gates and verified production archive publication, a public
checkout can select an immutable edition without redistributing its private
authoring graph, working partitions, report, policy or reading ledgers. Export
the descriptor with `research_edition_replay.py export` using the genuine archive
receipt and source-selected prepared package. Commit its exact bytes under
`data/research/editions/`, its registry/package pins and complete frozen public
package. No descriptor or selector establishes a new scientific approval.

`data/research/published-source.json` is an explicit source-owned selector with
exact fields `schema_version: "published-research-source-v1"`,
`current_release_id` and a nonempty `editions` array. Each entry has exactly
`release_id`, `status: "published"`, `snapshot_path` under `editions/`, the raw
descriptor's full `snapshot_sha256`, and optionally a positive integer
`revision` (default 1). Include the current release exactly once. Each current
and historical entry must independently resolve through the committed prepared
registry and actual verified publication descriptor. Duplicate release IDs,
descriptor paths or immutable edition date/revision URLs fail closed. Selection
is explicit; ledger order and dates do not choose the current edition.

`build_context` checks this selector before opening any private authoring input,
even with `select_prepared=False`. A malformed, changed or unsafe selector never
falls back to private files. Absence retains ordinary private authoring mode.
The selected context remains `replay_only`/`published_frozen_replay`, with
`archival_ready: false` and current-input/raw-source/private-withheld revalidation
false. Original private scientific commitments are retained, not equated with
the public projected graph or reminted as fresh acceptance.

The authenticated public edition ledger and verified `edition_snapshots` are
carried outside the exact frozen report. Renderers recheck the source selector,
ledger and frozen contexts before creating archive routes and feeds; they do
not mutate `report.editions`. Low-level `load_graph` and `load_report` remain
private-authoring APIs and do not synthesize substitute scientific inputs.
Tests of private authoring assumptions need explicit synthetic authoring
fixtures; public source checks use the selector and capsule directly.

The all-synthetic `test_public_research_source.py` fixture physically omits the
private authoring files and runs the ordinary `build_public_snapshot.py` entry
point in a separate public-only source checkout. It denies private input opens,
network, fresh gates and package freeze/export writers while checking current
and historical readers, feeds, local search, company evidence bridges, sitemap
and live citation overlay without changing any frozen package bytes. Synthetic
receipts in tests are never a real publication or a source-review result.
