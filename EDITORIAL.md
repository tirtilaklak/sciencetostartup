# Editorial work reviews

ScienceToStartup is an independent public-source guide. A recorded route is not
proof of hiring, application acceptance, project allocation or payment.

`data/canonical.json` remains research dataset **2.5.0**, byte for byte. Its JSON
and SQLite downloads are historical research snapshots. Routine work reviews use
`data/work-routes.json` and the separately versioned `data/editorial-release.json`.
Do not bump the canonical dataset version to advertise a newer editorial check.
The older `source_dataset_version` inside the work sidecar is retained provenance;
the editorial release explicitly binds the selected canonical 2.5.0 bytes.

## What this release reviewed

All 135 stored records have a cited editorial classification and explicit field
states. The initial 12-route calibration audits the stored evidence and records
new public retrieval attempts. It is not a claim that every fact on those pages
was reverified. Only separately approved source-content receipts refresh field
review dates. In the first editorial release, Sage and the Mercor network have
new approved key-terms receipts. Their reviewer is **Codex source review**, under
the user's authorization; no human signoff is invented.

The named/program distinction describes the source destination. A named paid
fellowship can be a named listing even if the historical research status says
`program`. Networks may contain many projects. Migration information, contribution
documentation and indirect company-profile leads stay in Other records until a
review establishes a usable paid-work route. Past records and other company jobs
remain available without inflating the primary work-route count.

The 8 November disposition review found the original AfterQuery security/
infrastructure and Terac ML-scenarios URLs unavailable in both posting and
description forms. Their exact role IDs were not observed in the fetched official
boards. They are historical page-unavailable records, with prior facts retained
and current company career boards linked as separate destinations. This does not
claim that either employer stopped hiring. The resulting initial discovery scope
is 78 recorded work routes: 56 named listings and 22 networks/programs.

## Field states and dates

- `sourced`: a recorded value has cited support. `basis: stored_evidence` retains
  the earlier research; it does not claim a new page review. If no precise field
  review date was recorded, `reviewed_on` is null.
- `source_not_stated`: the specific reviewed source did not state the field. It
  requires a date, source reference and note identifying that limited scope.
- `not_researched`: the field has not been reviewed. Its review date is null.
- `conflicting`: source wording or components need reconciliation. Keep the
  qualifications visible; do not silently pick the most attractive amount.

Blocked, missing and JavaScript-only responses are retrieval outcomes, separate
from these fact states. Preserve the last sourced value and its date on failure.
An HTTP 200 challenge is not readable source content. A failed check or build time
never refreshes a successful field-review date. A review date is not a source's
publication date. Age alone never means closed or unpaid.

`route_kind`, `engagement_type` and `arrangements` are independent. Hourly pay does
not prove contractor status. A city alone does not prove an on-site schedule.
Mixed source wording such as on-site preferred/remote considered supports both
possibilities, with the condition retained. Remote is not worldwide eligibility.
Preserve country, state, authorization and project/domain-specific exceptions.

`pay_terms.unit` and `hourly_comparable` control pay grouping and sorting. Task
fees and hourly equivalents are not actual hourly payment. Network averages are
context, never an individual role's offer. Keep base salary, target cash, total
compensation, maxima and approval conditions distinct.

## Daily candidate queue

Automated checks run daily; an editor reviews the queue on five days per week.
The agreed initial operating budget is 5–7 editorial hours/week, reassessed after
two weeks. Prioritize destination failures and changes to compensation,
eligibility, qualifications, assessments and commitment. Rotating marketing
content is not itself a factual update.

```sh
python3 scripts/check_work_sources.py --output build/editorial-candidates/today.json
python3 scripts/check_work_sources.py --previous build/editorial-candidates/today.json --output build/editorial-candidates/next.json
```

The checker performs bounded public GETs with TLS verification and at most four
workers. It stores hashes and comparison signals, not raw page bodies. JobPosting
documents are compared without rotating page chrome where available. Every result
is a candidate requiring source review. The command never edits data or status,
and refuses candidate output inside `data/` or `dist/`. A first run establishes a
comparison baseline. No automated signal verifies current hiring or pay.
Repeated unchanged failures remain receipts marked `unchanged_failure`; keep one
open editorial issue per route rather than generating a new daily correction.

Human/editorial triage:

1. Inspect the official source and its relevant policy. For a missing role, check
   the destination and official employer board before asserting removal.
2. Keep unresolved or blocked checks qualified. A failed request is not proof
   that work ended. Record only the fields actually read.
3. Update current facts only with source references and locators. Keep prior
   statements/receipts in history. Add a response hash, actual check timestamp,
   reviewer and `approval_basis: source_content_review`.
4. A `field_review` receipt approves only its listed fields. A `key_terms` receipt
   used for homepage promotion must address all seven explicit field states:
   destination, pay, location, requirements, assessment, commitment and duration.
   A reviewed source may leave a field unstated; do not manufacture a value.
5. Inspect the resulting card, source disclosure and counts. Corrections enter
   this same queue; the published seven-day correction-review commitment remains.

## Cadence and promotion

The homepage work example is reviewed on each editor day and expires after the
three-day review window. The same rule applies to an approved network fallback.
Use the approved candidate order, then a neutral Browse paid work panel. A company
summary has its own semantic review date; do not borrow a financial date or work
receipt for it.

Named listings are reviewed weekly. A successful approved key-terms receipt starts
the review clock: at 14 UTC days the listing is marked Needs recheck. Pay-only
reviews, page checks and failed retrievals do not reset that clock. A named listing
without an approved full-terms receipt says Full terms review not recorded. These
labels do not assert closure. Static pages calculate age at the explicit publication
timestamp and print that date; the interactive guide may age the label using the
current UTC day without changing the stored facts or review dates.

Programs are reviewed monthly, sooner on a material change. The 45-day limit is an
editorial rule for any future recent-review promotion; this release adds no such
filter or badge. Homepage network fallbacks already use the stricter three-day
rule. All dated records remain browsable.

The small homepage runtime guard withdraws expired work examples. A publication
regenerates the static HTML; the scheduled quality monitor checks the deployed
release and does not rebuild or deploy it. Without JavaScript the homepage retains
the neutral Browse paid work panel. Failed publications must alert the release
owner. Absolute review dates remain attached to the recorded facts.

## Prepare a reproducible publication

After source review, stage an editorial publication from approved data. Preparation
changes publication identity and hashes, not fact values, review dates or approvals.
Explicit timestamps make repeated preparation reproducible.

```sh
python3 scripts/prepare_editorial_release.py --release-id 2026-11-08.2 --publication-as-of 2026-11-08T23:00:00Z --output build/editorial-staged
python3 -m unittest discover -s tests -p 'test_editorial_work.py'
```

Review the staged `work-routes.json` and `editorial-release.json` diff before copying
them into `data/`. Then run the repository's build, browser, accessibility,
performance, privacy and release checks. This staging command does not deploy or
approve monitoring candidates. The release owner handles publication and rollback.
The build rejects changed canonical bytes, mismatched work hashes, fabricated
review dates, invalid source references and unbound homepage approvals.

Current-result CSV exports use the effective visible selection, including its
period, business scope, currency and source. Canonical JSON/SQLite remain labeled
research snapshots; do not silently rewrite their provenance.

Daily monitoring runs at 07:17 UTC through `.github/workflows/quality-monitor.yml`.
It records source-change candidates and a dated heartbeat as GitHub Actions artifacts.
The editor checks the latest run and heartbeat on each working day. A missing heartbeat
is a gap in monitoring, not evidence that the website is down. Scheduled checks are
best effort; existing Cloudflare RUM and logs remain the operational evidence.
