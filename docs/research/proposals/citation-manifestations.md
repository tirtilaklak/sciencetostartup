# Explicit source manifestations for new citation candidates

This is an additive proposal. It does not amend a frozen reference panel, its
locators, source keys, SUT outputs or outcomes. It creates no approval and does
not substitute for a prospectively frozen independent launch audit.

A response-body digest identifies source bytes, not a text extraction. A complete
citation binding should identify both the exact source response and any derived
text manifestation used by its coordinates. Preserve the original source URL,
version, raw digest and capture timestamp. Copying a retained body or extracting
text now is not a new retrieval. Record the extraction/read times separately.

For raw UTF-8 text, preserve bytes including BOM, CR, form feed and a terminal LF.
Decode strictly as UTF-8. One-based line coordinates split on U+000A only; they do
not apply Python `splitlines`, strip whitespace, or discard an empty final segment.

For PDFs, bind each physical page separately to exact stdout from:

```text
pdftotext -f PAGE -l PAGE -layout -enc UTF-8 RAW_BODY -
```

Record the actual tool version, command, raw response digest, physical page,
stdout digest and length. Preserve terminal form feeds and whitespace. Inspect
rendered pages when tables, columns, symbols or figures affect the proposition.
A line number from another unspecified extractor is not silently converted.

For HTML, one possible declared manifestation is `html_textnodes_v1`: Python's
standard-library `HTMLParser(convert_charrefs=True)`, ignoring `script`, `style`
and `noscript` elements; strip each nonempty data node, join with LF and append
one terminal LF. Pin the complete extractor source and Python version as well as
the output bytes. These are text-node coordinates, not a claim of browser-visible
layout. Hidden data nodes can remain. State this limitation and inspect source
identity/context; do not mistake generated text for a source read. Unicode offsets
are zero-based decoded-character offsets; byte offsets must be identified separately.

Complete support may require a preceding subject, sentence continuation, table
header, denominator, date, document title, figure definition, or qualification in
another page. Bind every necessary span in the same version. A concise excerpt
need not contain the whole proposition; it must occur literally in a bound span,
and public excerpt limits still apply. Full source bodies and long supporting
spans remain private.

Where a scientific qualification names another document that is not bound,
either capture and inspect the exact necessary version or narrow/quarantine the
qualification in a genuinely new candidate. A citation gap does not establish a
false fact about the world. Preserve the old assertion, source, locator, digest,
reviews and negative audit result as historical evidence.

New scientific candidates receive new assertion/source IDs. Author, verifier and
adversarial invocations review their exact current assertion digests. The digest
projection contains every assertion field except `status` and `review_ids`, then
uses `json.dumps(content, sort_keys=True, separators=(',', ':'), ensure_ascii=False)`
and SHA-256 of its UTF-8 bytes. Status may advance only after actual separate
current-digest reviews. Source-only capsules precede hypotheses for blind readers;
digest-projection capsules enable independent recomputation without exposing
prior verdicts or statuses. Mechanically valid candidates remain unadmitted and
add no scientific coverage credit.
