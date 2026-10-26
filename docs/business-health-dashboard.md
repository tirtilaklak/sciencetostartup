# Business health dashboard

The overview answers five business questions: is paid demand growing, does delivery leave a margin, do customers return, is expert supply doing paid work, and can the business sustain growth?

## Layout

The dashboard is one board. Five signal tiles sit above it, each with its question and how many of the 39 organizations report a figure for it. The board's left side is an evidence grid with every organization as a row and the five signals as columns; the grid scrolls inside the board, so the whole field stays within one screen on a desktop. A cell shows the best available figure with a short tag (measure and period), tinted green for a reported or calculated figure and amber for context such as reach or headcount. A dash marks no public disclosure and `n/a` marks nonprofit research. The tag also names the scope when a figure covers one line of business or a segment rather than the whole company, a letter gives the research grade of the cited claim (A strongest), and figures more than a year older than the dataset date are tagged historical and muted, the same rule the company cards use. The toolbar searches, filters by business group, orders rows by evidence coverage, by the selected signal (figures are only ordered by size within one measure and basis) or by name, and can hide rows without evidence.

The right side is an inspector for the selected cell: value, evidence type, date, scope, accounting basis, source links, a collapsed caveats block with the source wording, the same measure across other companies in separate same-basis panels, and a line of the company's own dated observations when the same series has more than one point. Selecting a tile sorts the grid by that signal and opens its leading observation; under a group filter the comparison starts on the measure that group reports most. On phones the board stacks: tiles scroll sideways, the grid scrolls both ways with the company column pinned, and tapping a cell brings the inspector into view.

The recommended north star for the commercial AI data businesses is **gross profit from repeat paying customers**: recognized revenue from returning customers less direct delivery costs attributable to that work. It combines durable demand and delivery economics. It is an analytical recommendation, not a number publicly established for this universe. Compute businesses, software vendors and nonprofit research need their own operating context.

## Evidence and calculations

`data/business-health.json` is a curated presentation layer bound to the unchanged reviewed dataset v2.5.0. It contains 98 observations across 28 organizations, joined to 65 sources already in the canonical research. The matrix covers all 39 organizations, including explicit missing and research/not-applicable states.

Raw inputs are canonical numeric metrics and exact attributed claims. The sidecar adds periods, human-readable business scope, compatible cohorts, measurement definitions, source references, and explicit arithmetic for six derived figures. It retains original wording. For example, the TaskUs retention record's inherited USD unit is normalized to percent with an explanatory note; the original record remains inspectable.

Recognized revenue, annualized pace, statutory net income, adjusted EBITDA, gross margin, cumulative payouts, daily payouts, customer concentration, and retention are distinct measures. The source's company/AI-service/parent scope stays visible. Revenue-history lines connect only the same period type, scope, currency and accounting basis. Dates remain explicit. A source's undisclosed gross/net basis remains undisclosed.

Customer counts, expert networks and team snapshots are marked as context. They do not establish repeat paying customers, paid utilization or capital efficiency. Cash without a burn rate does not establish runway. No composite health score is produced.

The margin-range calculator multiplies one cited revenue input by user-selected hypothetical gross margins. It never writes a scenario into the evidence matrix. Outputs retain the revenue period, accounting caveat and source qualifier; a lower-bound input does not create a forecast upper bound. No retained-customer profit is inferred without retention data.

## Freshness and validation

Dashboard curation is dated October 23, 2026. Underlying research retains its October 12–15 review dates. Attempts to refresh three primary filings returned HTTP 403, so this release claims no fresh source-content verification. Original source links and dates are available in the evidence dialog and JSON export.

The build validates supported same-company claim/metric/source bindings and finite numbers. Focused tests independently reconstruct derived ratios, reject broken provenance, check bounds and missing-value semantics, and exercise filters and scenario arithmetic. Chromium checks on this layout drove search, the group filter, the evidence-only toggle, the three row orders, cell selection including a missing cell, the company history line, measure switching, bar selection and arrow-key tabs at desktop and phone widths, with no console errors. The canonical audit and public snapshot reproducibility checks remain in place.
