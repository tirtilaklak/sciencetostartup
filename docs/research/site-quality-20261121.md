# ScienceToStartup design and reliability audit

The audit began at 7:30 PM Pacific on November 21, 2026. The first three hours are for evidence gathering. Implementation starts at 10:30 PM. The audit, fix and independent retest cycle ends at 7:30 PM Pacific on November 22.

## Current pass

Audit in progress. The production manifest identifies build `d8d18622a82c541129c1`. The repository baseline is main at `4d7dae5d40c1dea7978ab519cd3ac66d547cf29f`, with checked-in build `6d57f30fbf456b1e48a8`. The deployed Daily index contains the November 17 issue. The repository contains the November 18 issue. A push to GitHub alone does not publish the Worker.

## Findings and acceptance checks

| ID | Observed on production or the published data | Acceptance check |
| --- | --- | --- |
| H1 | On a 390 × 844 phone, the portrait ends at y=818 and the first company record starts at y=1,030. The second homepage example is a generic paid-work link. | Put both actions and a company and work example on the first screen at 390 × 844 and 1280 × 720. Link source and reporting date. Preserve the promotion expiry rules. |
| H2 | At 844px wide with Firefox set to a 28px minimum font, Search starts at x=869. The document scrolls horizontally to 913px. | Search and all primary actions fit or wrap on either side of the navigation breakpoint, including with enlarged text. |
| W1 | Four named employer URLs return 404, including two AfterQuery listings, G2i and Ooak. Terac explicitly marks its listing closed. APTO's company page links to an unpublished application. Sage gave inconsistent results. | Remove six unusable role actions from current opportunities while keeping the source history. Label uncertain availability. Check the destination reached by Apply. |
| W2 | The work source checker can report several Ashby 404s as blocked because their error page includes generic challenge script text. | Distinguish a missing posting from a challenge page. Test a genuine blocked response, a 404 shell and a 200 closure. |
| S1 | The previous audit observed three Snorkel results expanding to 135 after Compare. The native surfaces also differ in search scope and location categories. | Native results, comparison and CSV carry the same record IDs for Snorkel and for Named + On-site/hybrid. Back, reload and direct links preserve the selection. |
| E1 | Mercor leads with its October 2025 $10B Series C valuation. Its November 2026 $20B Series D is collapsed. Datacurve leads with an undated recruiting claim. | Promote the latest comparable issuer-announced valuation. Date it. For Datacurve, distinguish the $15M Series A from cumulative funding and separately sourced company claims. |
| E2 | The dataset index describes 153 approved records, but its rows show 154 as approved. FineWeb-Edu has an approved metadata entry with no approved assertions on that record. | Explain the two counts and label that record accurately. Distinguish the 226 approved paper works, 151 approved versions and 225 works that meet the report's review standard. Preserve frozen source records. |
| R1 | Two of 23 production routes exceeded the 200ms median mobile blocking budget in the prior 69-run capture on this same build. A filtered Work page can briefly show the entire list before its script executes. | Re-run the two long chapters on the release candidate. Check filtering with delayed and failed JavaScript. Preserve the query and an accessible recovery path. |
| N1 | With JavaScript disabled, Search in native page headers opens the homepage without a search input. In the enhanced combobox, individual results enter the Tab sequence. | Offer a useful native fallback. Confirm mobile reading and tab order and keyboard selection in a real browser. |
| D1 | The public Daily feed and index refer to November 17. The November 18 URL returns 404 and is absent from the live manifest. That issue exists in the checked-in release. | Compare the manifest, public edition page, index and feed in the candidate and again after any promotion. |

## Evidence

- [Live manifest](https://sciencetostartup.com/manifest.json) and [Daily index](https://sciencetostartup.com/daily/)
- [Snorkel disclosure](https://snorkel.ai/blog/data-2-0-and-the-research-era-of-ai-data/) and [expert community terms](https://snorkel.ai/expert-community/)
- [Mercor Series D](https://www.mercor.com/blog/series-d/) and [Datacurve Series A lead investor](https://www.chemistry.vc/post/staying-ahead-of-the-curve)
- [Terac closed listing](https://terac.com/opportunities/KZwfXOQhfpdjGT8k) and [APTO application](https://herp.careers/v1/apto/NyufvNJGg7Td)

## Next pass

Complete fresh journey and performance measurements and inspect overlap with open changes in PRs #8, #32 and #33. Keep the source record IDs and regression tests beside each implementation result. Rebuild the generated site once after integrating the source changes. A later pass should independently repeat the failing steps against that exact build and record what reached production.
