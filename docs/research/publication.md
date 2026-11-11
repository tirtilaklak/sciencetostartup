# Citation and publication preparation

Ordinary builds call `write_publication_assets(context, output)` from
`scripts/research_citations.py`. This is an offline standard-library operation:
no login, credential discovery, HTTP request, external account creation or
publication occurs. The current policy is `prepare_only` while research quality
gates remain held. Zenodo production, Zenodo Sandbox and Hugging Face passed
read-only authentication on 2026-11-10. Credentials are stored outside the
repository, and the Hub setup dataset remains private without uploaded research.
Account connection does not satisfy the evidence, cutoff or release gates.

The generated `publication/` directory contains a full text report, standalone
offline HTML and evidence appendix, citations in BibTeX, RIS, CSL JSON and Citation File Format, metadata,
readiness, a privacy-filtered dataset in equivalent JSON/CSV/SQLite, a deterministic
ZIP archive, an internal checksummed manifest, and prepared Zenodo/Hub metadata.
`package-status.json` keeps archive, website, GitHub and Hugging Face states
separate. A built site or mirror does not establish permanent archival publication.

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
coverage floors, frozen-core disposition, the two real 200-record audits, source
cutoff rules or actual archival publication.

## Public projection and equivalence

Canonical dataset 2.5.0 and its legacy downloads remain byte-identical. The new
archive contains independently versioned public projection **1.0.0**, with the
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

New preparation uses **package context contract v2**. `MANIFEST.json`,
`PREPARED.json` and new PDF receipts explicitly carry `context_contract_version: 2`;
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
Fresh PDF preparation now writes a v3 receipt; older source PDF receipts cannot
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
original research-only digest is checked using `context_digest(context,
version=1)` and its exact original `source-context.json`, manifest, PDF and ZIP
remain byte-verified. It is never regenerated, rewritten or retrofitted with new
schema/code/license bytes. Published legacy builds use the frozen PDF directly;
they do not reread or rewrite its old source PDF receipt. Existing v1 release
journals retain their exact ZIP markers, and existing v1 reservation journals
retain their original source marker for retry reconciliation. New reservation
journals bind the current v3 contract. A reservation and frozen package must use the same context
contract; a legacy reservation without a legacy freeze needs explicit operator
review before a transaction using a newer contract.

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

New packages use source-context contract 3. Live report pages, offline HTML,
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
match. Neither the current prelaunch dataset nor `prepare_only` policy qualifies.

The explicit caller first constructs a `PublicationPlan` with a reservation
journal **outside the source checkout**. `Zenodo(plan).draft()` creates/resumes
the deposit and reserves its version DOI before PDF preparation. It passes the
same authoritative research gate and `publish_enabled` policy check as a release,
but cannot upload or publish without a frozen bundle. The reservation journal is
bound to source inputs, excluding reservation outcomes. After rendering and
freezing, a separate release journal binds exact archive bytes. A concrete
sequence, only after accounts are connected and the policy is deliberately
enabled, is:

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
to run under the current `prepare_only` policy.

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
An existing conflicting tag or asset blocks replacement. Hugging Face uses the
official optional `huggingface_hub` SDK, an existing dataset repository, a pinned
parent commit and manifest-first reconciliation. After commit, downloads at one
immutable commit verify both archive and dataset bytes. A lost commit response
cannot silently create duplicate commits. Mirror success never changes website
production state.

No adapter was executed against a real account during implementation. Unit tests
use explicitly synthetic remote and gate fixtures to exercise failure recovery;
these fixtures are not review receipts, audit evidence or publication records.

Official API references used for the implementation:

- [Zenodo REST API](https://developers.zenodo.org/) documents draft metadata,
  reserved DOI status, bucket uploads, file checksums, publication and versions.
- [GitHub Releases REST API](https://docs.github.com/en/rest/releases/releases)
  documents draft releases, version tags and publication state.
- [Hugging Face uploads](https://huggingface.co/docs/huggingface_hub/guides/upload)
  and [Hub client reference](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)
  document commits, existing repositories, explicit credentials and parent commits.
