# Reproduce an evidence locator

`data/research/source-manifestations.json` records the response digest, source
version, exact extraction recipe and derived digest behind repaired locators.
The assertion binding preserves the original source ID and full scoped locator.
Source bodies are not redistributed. Obtain the named version independently;
matching a URL alone does not establish matching bytes.

Use `scripts/research_manifestations.py` with the response digest and expected
manifestation digest from that manifest. For example, replacing the descriptive
values with the exact manifest values:

```text
python3 research_manifestations.py downloaded-source.html \
  --source-sha256 RESPONSE_SHA256 --recipe html_textnodes_v1 \
  --expected-sha256 MANIFESTATION_SHA256 --output inspected-text.txt
```

The tool requires both digests and refuses different existing output bytes. Raw
UTF-8 preserves BOM, CR, form feeds and terminal empty LF lines. HTML text-node
coordinates use the declared parser recipe; they do not imply browser visibility.
PDF extraction additionally requires `--page` with the one-based physical page
and `--tool-version` with the exact recorded `pdftotext` version. It preserves
the extractor's stdout bytes. A changed source or tool must not silently inherit
old coordinates. The optional extractor needs Poppler for PDF sources; routine
offline website and archive builds do not extract or retrieve source documents.

The independent reader must inspect the complete supporting context, including
table headers, denominators and qualifications. Reproducing bytes is a mechanical
check, not a scientific review, an endorsement, or verification of a provider's
operational performance. Full source text retains its original rights.

The implementation was checked against all 438 retained manifestation references
(392 distinct byte streams) used for the 62-case repair corpus on November 11,
2026. Those exact-byte checks confer no coverage or audit-performance credit.
Only currently approved assertion bindings appear in the public manifest; prior
keys, negative results and superseded candidates remain preserved separately.
