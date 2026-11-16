# Daily scan

`/daily/` shows the latest selected reading list. `/daily/YYYY-MM-DD/` retains a
dated snapshot, beginning 2026-11-16. The date is the selection day in
America/Los_Angeles, not a claim that every source was published that day.
Every item retains the original source date and its date basis. arXiv submission
dates use UTC and are identified as such.

## Daily update

1. Inspect current public `origin/main`, the live manifest, existing scan dates
   and any in-flight release before making changes. Use an isolated `codex/`
   branch based only on current public main; preserve unrelated work.
2. Use three separate `gpt-6.1-sol` workers with `ultra` reasoning, each with one
   role: RLHF/post-training papers; data/datasets/evaluation; company news.
   Record the requested configuration and any actual availability limits.
3. Browse arXiv, original papers, official datasets/repositories, company
   announcements, filings and original reporting. Select 10–20 useful items,
   normally from the previous 14 days. On quiet days widen the window and show
   the dates honestly; do not invent news or pad with weak items. Distinguish
   a new paper from a new announcement about older research. Recheck source
   dates against visible dates, submission histories and metadata; hidden date
   widgets and search snippets are insufficient.
4. Cross-check the selected findings across the workers. Keep author/company
   results attributed, identify abstract-only reads, and retain material limits.
   Availability is not source review; reading a paper is not replication.
5. Add `data/daily-scan/YYYY-MM-DD.json`. Use the schema of the initial snapshot:
   `id`, `title`, `kind`, `topics`, `publisher`, `published_on`, `date_basis`,
   `focus`, `finding`, `caveat`, `read_scope` and `sources` with visible labels.
   The filters are defined in `scripts/daily_scan.py`. Keep the factual notes
   concise, as structured fragments rather than new narrative sentences.
6. For explanatory prose, reuse only complete, exact, suitable sentences from
   downloaded Wikipedia articles. The initial context excerpts and revision,
   history, license and download hashes are in
   `data/daily-scan/wikipedia-context.json`. Download relevant articles only,
   check warnings and topic identity, pin the revision and response hash,
   verify suitability against primary evidence, and attribute excerpts visibly
   under CC BY-SA 4.0. Do not stitch fragments into invented Wikipedia sentences,
   use generic definitions as evidence for current company events, hide reuse,
   or claim human authorship or a guaranteed detector score. Titles, dates,
   names, interface labels and structured facts retain their primary sources.
7. Preserve earlier snapshot files. Correct a factual error transparently using
   a dated correction note; never backdate a missed run. Keep full research
   receipts under the workspace's `research/daily-scan/YYYY-MM-DD/` outside
   the public Git checkout. Public JSON contains only selected facts and links.
8. Build, test and publish through the current README's exact-artifact process.
   Validate daily data, responsive filters, source disclosures, date navigation,
   deep links, no-JavaScript reading, accessibility and payload/performance.
   Run the repository's required checks. Test the exact inactive Cloudflare
   version before promoting it; confirm production has not changed underneath
   the release and verify the live manifest, daily page and source links.

This reading list is independent of the archived research editions. It does not
change the canonical dataset, frozen publication files, DOI or research mirrors.
The existing weekly publisher remains responsible for archival editions.
Coordinate shared deployment work using the established release lock/journal;
do not overwrite another publisher's active work. A no-change or blocked run
keeps the last passing scan live and records the precise reason.

The daily local Codex automation targets 08:00 America/Los_Angeles. It requires
the Codex host to be available; delayed runs retain their actual selection date.
