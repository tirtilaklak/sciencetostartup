# Business health dashboard

The overview starts with a chart of revenue over completed reporting periods.
Its default selects the latest compatible group containing at least two companies.
Five tabs expose revenue, profitability, customers, expert activity and cash.
Company scopes, periods, currencies and accounting bases remain explicit. A source
panel describes the selected figure; detailed caveats and the full company evidence
grid open on request. The hypothetical margin calculator is removed from the UI.

## Evidence

The October 28, 2026 supplement contains 109 observations across 28 organizations
and 65 source records. The full grid covers 39 organizations and keeps missing
values separate from zero and nonprofit entities separate from commercial vendors.
The original canonical dataset remains v2.5.0.

Nine fresh claims bind exact values, units, scope and reporting periods to retrieved
source excerpts and document locators. Each cited response has a SHA-256 receipt.
The validator checks those bindings alongside the canonical provenance and checks
derived growth/margin arithmetic. There are 11 additional observations in total,
including two calculations. A successful request alone is not content verification.

The source ledger records 24 checks: 21 content checks, one availability-only and
two unavailable sources. These include a duplicate alias and TaskUs's notice that
Q3 results are scheduled for November 4, so they are not 24 newly published reports.
Sources outside this refresh retain their earlier review dates. New source checks
do not change the period measured by a historical figure.

TaskUs and Appen can be compared on H1 2026 whole-company USD revenue. RWS's fiscal
half-year and GBP currency remain separate. Recognized revenue and annualized pace,
statutory profit and adjusted EBITDA, and current and cumulative payouts are distinct
measures. Historical charts place points by actual elapsed time, without inventing
intermediate observations. Bounds and approximate values retain their qualifiers.

Employee counts, registered networks and customer reach remain context. They do not
establish active paid experts, retention or capital efficiency. Cash without a burn
rate does not establish runway. No composite business-health score is produced.

## Review

Run the checks listed in `.github/workflows/ci.yml`. Browser review covers numeric
measure switching, source inspection, historical evidence, directory search,
comparison add/remove/share, paid-work filters and all key routes on desktop and
mobile. The public snapshot builder verifies every deployed payload against its
manifest; supplemental evidence does not rewrite canonical JSON or SQLite records.
