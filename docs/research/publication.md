# Citation and publication preparation

Ordinary builds call `write_publication_assets(context, output)` from
`scripts/research_citations.py`. This is an offline standard-library operation:
no login, credential discovery, HTTP request, external account creation or
publication occurs. The current policy is `prepare_only`. The user has elected
to prepare inspectable packages until external accounts are connected.

The generated `publication/` directory contains a full text report, standalone
offline HTML, citations in BibTeX, RIS, CSL JSON and Citation File Format, metadata,
readiness, a privacy-filtered dataset in equivalent JSON/CSV/SQLite, a deterministic
ZIP archive, an internal checksummed manifest, and prepared Zenodo/Hub metadata.
`package-status.json` keeps archive, website, GitHub and Hugging Face states
separate. A built site or mirror does not establish permanent archival publication.

Prelaunch citation files identify a preparation snapshot. They omit DOI and
publication-date fields. A reserved DOI is operational draft state, never a
published citation. Published citation metadata requires the authoritative final
gate and an actual published archive receipt, including the release identity,
artifact digest, record URL and confirmation date. A real publication date is
emitted only when supplied by the archive; a source or verification date is never
substituted for it. The publisher comes from `data/public-identity.json`.

## Public projection and equivalence

Canonical dataset 2.5.0 and its legacy downloads remain byte-identical. The new
archive contains independently versioned public projection **1.0.0**, with the
canonical data and public supplemental graph as inputs. The projection omits raw
inputs/caches/full-text fields, source quote fields and structured contact fields.
Email patterns are redacted throughout nested text, including the known legacy
personal email. This is a broad safeguard, not an allowlist for other addresses.
The archive does not redistribute company imagery, logos or scraped source bodies.

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

ZIP member names are sorted, timestamps are fixed to 1980-01-01, compression is
stored, permissions are stable, and the internal manifest records every member's
SHA-256 and byte count except itself. The archive contains that exact manifest.
SQLite secure deletion, page size and insertion order are explicit. Rebuilding
the same inputs produces the same bytes on the repository's supported SQLite
versions; a runtime migration still requires exact-build verification.

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

`scripts/research_publish.py` provides `Release`, `Journal`, `Zenodo`,
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

The explicit caller constructs a release with a journal path **outside the source
checkout**, then constructs a credentialed adapter. A Zenodo caller invokes
`draft()` to create/resume a deposit and reserve its DOI, `upload()` to reconcile
and upload exact package files, and `publish()` to publish after all checks.
`draft(previous_id=<latest-version-record-id>)` creates a new version via the
official `newversion` action and follows the returned `latest_draft` link. It
does not use a concept DOI as a version ID. The adapter refuses an unrelated
outstanding draft. Stable upload names replace corresponding inherited files;
unexpected inherited files block publication pending explicit reconciliation.

The state journal is bound to release ID and manifest digest. Every remote
mutation records intent before the request. A lost create response is reconciled
by the unique package marker in account deposit metadata. Ambiguous/missing
matches block automatic retry. New-version recovery follows the original
record's draft link. Upload retries first compare remote names, lengths and MD5
checksums; matching files are skipped. Publish retries first inspect deposit and
public record state; a pending publish is not blindly repeated. Only a public
record with registered DOI and verified exact files marks the archive published.
A reserved DOI remains `reserved_doi`, never `doi`, in draft journal state.

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
