# Reproducing evidence locators

An evidence locator belongs to an exact source version and response SHA-256.
Check those bytes before interpreting page numbers, text lines or offsets. A
fresh copy at a mutable URL may differ from the inspected copy. Document mirrors,
accepted manuscripts and publisher PDFs remain separate manifestations.

## PDF pages and derived text

Physical pages are one-based positions in the pinned PDF, including covers. They
need not match printed page labels. A locator must name its extraction convention
when it also uses derived line numbers. An extracted line number is not a PDF
page number. Inspect the actual page when table structure, columns or an equation
affect interpretation.

For the original NuminaMath and Pick-a-Pic dataset-cohort-3 evidence, the exact
marked-text convention is pypdf 6.10.0:

```python
from pypdf import PdfReader

reader = PdfReader("pinned-source.pdf")
pieces = [
    f"=== PDF PAGE {i} ===\n" + (page.extract_text() or "")
    for i, page in enumerate(reader.pages, 1)
]
text = "\n".join(pieces) + "\n"
text_bytes = text.encode("utf-8")
lines = text.splitlines()
```

Markers and blank lines count in the one-based global line coordinates. A
declared inclusive range `L40-L48` is `lines[39:48]`. Do not remove the markers,
strip pages, change newline joins or substitute another extractor.

| Inspected document | Physical pages | Marked text lines | Derived UTF-8 SHA-256 |
|---|---:|---:|---|
| NuminaMath | 16 | 727 | `1eafde410e61dd6e20921dad861c42fb81a36e2edd02629678f9bef0bb4c6e4e` |
| Pick-a-Pic | 12 | 644 | `09f3e1271f5636690eace950ebf4752c62e06995ceedd1a6ce156a9485c24db3` |

These identify inspected documents, not every release with the same title.
The associated source records retain their exact PDF versions and raw hashes.
Third-party PDF bodies and full extracted text are not redistributed in this
archive; this recipe explains how an authorized reader can reproduce coordinates.

Other PDF records can use a different explicitly declared convention, including
`pdftotext -f N -l N -layout pinned-source.pdf page-N.txt`. Preserve the named tool
version and derived-text hash when supplied. Whole-document form-feed splitting
can miscount pages because a PDF font can extract a glyph as a form-feed character.
Use physical page objects or per-page extraction instead. In the inspected
TruthfulQA PDF, Appendix D is on physical page 34 of 39; a whole-text segment count
must not replace that page coordinate.

## Text, repository and dataset-card evidence

Raw UTF-8 line ranges are inclusive and one-based. Preserve YAML headers and
blank lines when counting a raw dataset README. Visible-text HTML coordinates
refer to the declared extraction, not the raw HTML line layout. Character offsets
need their declared extraction and offset convention. A name-only excerpt cannot
establish a relationship expressed elsewhere; include the relation-bearing
sentence and relevant table headers in the binding.

Repository paths bind immutable commits. Dataset cards bind the inspected
revision. A card revision is documentation evidence and does not by itself pin
every underlying corpus shard. Capturing, extracting, reviewing and publishing
are distinct events; reproducing an extraction does not create a new source
capture or an independent scientific review.
