# Pending 2.5.1 corrections

Prepared 23 October 2026. Every source in items 1 to 5 and in the sidecar notes at the end was rechecked live on that date.

Items 6 to 10 were added on 25 October 2026, and their 2.5.0 values were rechecked against the dataset that day. The sources quoted in items 6, 8 and 9 were also read live that day. Item 7 rests on figures already stored in the records. Item 10 changes wording only.

Dataset 2.5.0 is pinned by hash in `tests/redesign_checks.py`, and `observatory.py import` requires the 29 raw files listed in `raw_inputs` (`data/raw/...`). Those files live only in the research repository, so these corrections must be released there. The public repository already carries the sidecar fixes noted at the end.

## Record changes

**1. Handshake run-rate date.** Dealroom, "Handshake's ARR crosses $1B as AI training revenue surges", was published 14 April 2026. The 23 April date belongs to the separate Notable Capital interview (`handshake_ai.source.audit-h4`), which stays as it is.

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `handshake_ai.claim.oct14-major-financial-0` | `as_of` | `2026-04-23` | `2026-04-14` |
| `handshake_ai.claim.oct14-major-financial-0` | `date_note` | `The observation date is October 14. An undated page is not assigned a synthetic publication date.` | `Dealroom published the article on 14 April 2026. The observation date is October 14.` |
| `handshake_ai.metric.major-growth_metrics-0` | `as_of` | `2026-04-23` | `2026-04-14` |
| `handshake_ai.source.oct14-e0de0f3911dc` | `published_on` | absent | `2026-04-14` |

The sibling `handshake_ai.claim.oct14-major-financial-1` and `handshake_ai.metric.oct14-major-financial-1` (about $1.15B group gross run rate, same article) use `2026-04`. That is consistent and needs no change.

**2. BenchFlow contact address.** `benchflow.claim.worker_opportunities-0` `statement`:
- 2.5.0: `Current site invites contact at xiangyi@benchflow.ai and open research contributions; no current paid remote-contract opening verified`
- 2.5.1: `Current site invites contact via its About page and open research contributions; no current paid remote-contract opening verified`

The About page still has a "Work with us" link and a contact link. PostTrain still says contributions are open and runs are paused.

**3. Labelbox pay FAQ.** `labelbox.source.l10`: `help.labelbox.com` now serves Intercom's certificate and fails TLS. The same article (id 13600616, "Alignerr Payment FAQs", dated 16 April 2026) is live on Alignerr's Intercom help center.
- `url`: `https://help.labelbox.com/en/articles/13600616-alignerr-payment-faqs` → `https://intercom.help/alignerr/en/articles/13600616-alignerr-payment-faqs`
- `publisher`: `help.labelbox.com` → `intercom.help`
- `accessed_on`: `2026-10-12` → `2026-10-23`

**4. Sama ownership and founder sources.** All of `www.leilajanahfoundation.org` now returns 404 with a Wix "domain isn't connected" page. This hits `sama.source.audit-sa-ljf` (`/about`) and `sama.source.audit-sa-leila` (`/rememberingleila`). Wayback lists captures from 15 June and 13 July 2026, but this session could not open them.

Add one company source and re-source both claims:
- New `sama.source.sama-founder-page`: url `https://www.sama.com/leila-janah-founder` · title `Our founder: Leila Janah` · publisher `www.sama.com` · `source_type` `company` · `published_on` null · `accessed_on` `2026-10-23`. The page states that Leila Janah founded Samasource in 2008 and also founded Samaschool and LXMI. It covers her Harvard and World Bank background, her work at Katzenbach Partners, her death on 24 January 2020 and Wendy Gonzalez becoming CEO. It also says: "In 2019, Leila re-established Samasource as Sama, a for-profit tech company, with the original nonprofit, now known as The Leila Janah Foundation, as the company's largest shareholder."
- `sama.claim.expansion-sama-founder`: in `source_ids`, replace `sama.source.audit-sa-leila` with `sama.source.sama-founder-page` and move the old id to `historical_source_ids`. The statement stays. The TED 2009 guide still supports the Ashoka India and Katzenbach details.
- `sama.claim.expansion-sama-ownership-history`: set `source_ids` to `["sama.source.sama-founder-page", "sama.source.audit-sa-interview"]` and move `sama.source.audit-sa-ljf` to `historical_source_ids`. No live source states the 2020 renaming year, so drop that clause unless the retained raw read supports it. This also fixes the "2,019" rendering. New statement: `Nonprofit origin; the Leila Janah Foundation remains a major owner. Samasource became the for-profit Sama in 2019, with the original nonprofit, now the Leila Janah Foundation, as its largest shareholder. The CEO described the foundation as primary shareholder in November 2024.` Keep confidence B: one company page plus the CEO interview (pulse2.com, live).

**5. Figures from undated recruiting copy.** Two headline figures come only from undated job listings: `datacurve.metric.specialist-12` (the $150M "recruiting valuation claim"; the Datacurve risk row already says it is unverified) and `polymath_ai_labs.metric.specialist-5` (more than $8M raised). Set `preferred_for_comparison` to `false` on both, so the app and the static pages show them under "Other reported figures" instead of as headline figures.

**6. Mercor $2B run rate is recorded twice.** Felicis published on 21 July 2026 that "by June, Mercor said it had reached $2 billion in annualized revenue run-rate". Sacra estimates "$2B in annualized gross revenue in June 2026". This is one observation. 2.5.0 holds it as two current figures: `mercor.metric.oct14-major-financial-2` (grade B, whole company, Felicis) and `mercor.metric.major-growth_metrics-0` (grade C, AI business, Sacra and the same Felicis page). The two records differ in scope and in several other fields, so the profile shows $2B twice under "All dated figures". The app headline, the static page, the dashboard and the `mercor-gross-basis-support-2026-10-17` supplement already use the grade B record and attach Sacra's gross basis to it. Retire the copy. Rechecked 25 October 2026.

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `mercor.claim.major-growth_metrics-0-metric` | `status` | `supported` | `superseded` |
| `mercor.claim.major-growth_metrics-0-metric` | `caveat` | empty | `Same June 2026 figure as the $2B run rate Felicis reported. Sacra's gross-basis estimate stays linked to that figure. Retained as historical provenance; excluded from active fact selectors.` |
| `mercor.metric.major-growth_metrics-0` | `preferred_for_comparison` | `true` | absent |

The new caveat names no record ids, because the profile shows it to readers. The figure it repeats is `mercor.claim.oct14-major-financial-2`. Keep `mercor.claim.major-growth_metrics-0` (same statement, no metric) as `supported`: `validate_evidence_context` requires it as the Sacra binding of the supplement. No snapshot in `data/source-updates.json` and no `data/business-health.json` observation contains a changed row. The $2B Series B valuation of 20 February 2025 (`mercor.metric.major-round-valuation-2`) is a different figure and stays.

**7. Toloka FY2024 growth has two rates on two bases.** `toloka.metric.major-growth_metrics-0` (138%) uses the original FY2024 segment revenue in the Nebius FY2024 20-F ($26.4M against $11.1M). `toloka.metric.major-growth_metrics-1` (135.1%) is worked out from the restated revenue in the Nebius FY2025 20-F ($26.1M against $11.1M). Both are right for their basis. 2.5.0 already sets the $26.4M revenue (`toloka.metric.major-financial_metrics-3`) to `preferred_for_comparison: false` and compares $26.1M, but both growth rates are `true`. The tie breaks on record id, so a page that picks the preferred growth figure gets 138% next to $26.1M. The static Toloka page did this on 25 October 2026. The dashboard computes 135.1% (`dashboard.toloka.fy2024-revenue-growth`). Rechecked 25 October 2026 against the stored figures: 26.4 / 11.1 gives 138%, and 26.1 / 11.1 gives 135.1%.

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `toloka.metric.major-growth_metrics-0` | `preferred_for_comparison` | `true` | `false` |

Optional, so the two figures read differently under "All dated figures":

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `toloka.metric.major-growth_metrics-0` | `label` | `Revenue growth` | `Revenue growth, as first reported in the Nebius FY2024 annual report` |
| `toloka.metric.major-growth_metrics-1` | `label` | `Revenue growth` | `Revenue growth, restated in the Nebius FY2025 annual report` |
| `toloka.claim.major-growth_metrics-1-metric` | `confidence_reason` | `Attributed public statement` | `Worked out from FY2024 revenue ($26.1M) and FY2023 revenue ($11.1M) in the Nebius FY2025 Form 20-F.` |

The static pages keep main's "Other reported figures" list. After this row, Toloka's 138% does not appear there either: that list shows only the newest figure of each kind, and the preferred 135.1% wins the date tie. The 138% figure stays in the app's "All dated figures".

**8. Toloka 200K network is recorded twice.** Toloka's post of 6 May 2025 says "over 200K experts and annotators". `toloka.metric.oct14-0-expert-and-annotator-pool` (at least 200,000, 6 May 2025) is the profile headline and the dashboard record. `toloka.metric.major-growth_metrics-3` (exactly 200,000, May 2025) cites the same post through `toloka.source.audit-tol_invest`. The profile shows 200K twice. Retire the copy. Rechecked 25 October 2026.

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `toloka.claim.major-growth_metrics-3-metric` | `status` | `supported` | `superseded` |
| `toloka.claim.major-growth_metrics-3-metric` | `caveat` | `Not active paid worker count or commercial throughput.` | `Not active paid worker count or commercial throughput. Same figure from the same Toloka post as the record of over 200,000 experts and annotators. Retained as historical provenance; excluded from active fact selectors.` |
| `toloka.metric.major-growth_metrics-3` | `preferred_for_comparison` | `true` | absent |

The record the caveat points to is `toloka.claim.oct14-metric-0-expert-and-annotator-pool`. The caveat names no record id, because the profile shows it to readers.

**9. TaskUs and Appen FY2025 revenue is graded B.** The October 14 pass bound four FY2025 revenue figures to new claims graded B. The same figures already sit in supported claims graded A that cite the same reports (`taskus.claim.expansion-0-metric`, `taskus.claim.expansion-2-metric`, `appen.claim.major-financial_metrics-2-metric`, `appen.claim.major-financial_metrics-3-metric`), and sibling figures from the same tables stay A. TaskUs: Note 4 of the SEC copy of the 2025 annual report (printed page 75, PDF page 85) gives service revenue of $1,183,547K and AI Services revenue of $214,218K for 2025, in the same table as the 2024 and 2023 figures graded A. The 2025 net income and the 58.6% AI Services growth from the same report are graded A. Appen: Note 3 (segment information) of the financial report in the 2025 annual report gives FY2025 revenue of US$127,874K for Appen Global and US$102,900K for Appen China, US$230,774K in total (PDF page 80, printed page 78; page 81 of the ASX copy). Note 4 (revenue, PDF page 82, printed page 80; page 83 of the ASX copy) repeats the split. The Global figure is graded A. The reason "not independently audited" is wrong for this report, which carries the independent auditor's report (PDF page 117). Rechecked 25 October 2026.

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `taskus.claim.oct14-major-financial-0` | `confidence` | `B` | `A` |
| `taskus.claim.oct14-major-financial-0` | `confidence_reason` | `Revenue disaggregation from the audited FY2025 financial statements in the SEC-filed annual report. The existing research grade is retained.` | `AI Services revenue in Note 4 of the FY2025 financial statements in the SEC-filed 2025 annual report (printed page 75). The same table gives the FY2024 and FY2023 figures, graded A.` |
| `taskus.claim.oct14-major-financial-1` | `confidence` | `B` | `A` |
| `taskus.claim.oct14-major-financial-1` | `confidence_reason` | `Revenue disaggregation from the audited FY2025 financial statements in the SEC-filed annual report. The existing research grade is retained.` | `Service revenue in Note 4 of the FY2025 financial statements in the SEC-filed 2025 annual report (printed page 75). The same table gives the FY2024 and FY2023 figures, graded A.` |
| `appen.claim.oct14-major-financial-0` | `confidence` | `B` | `A` |
| `appen.claim.oct14-major-financial-0` | `confidence_reason` | `Attributed primary-source statement reviewed in the October 14 research pass; not independently audited.` | `Total revenue in Note 3 (segment information) of the financial report in Appen's 2025 annual report, released to the ASX on 25 February 2026. The same note gives the Appen Global figure, graded A.` |
| `appen.claim.oct14-major-financial-0` | `evidence_label` | `Attributed primary-source evidence` | `audited public company` |
| `appen.claim.oct14-major-financial-1` | `confidence` | `B` | `A` |
| `appen.claim.oct14-major-financial-1` | `confidence_reason` | `Attributed primary-source statement reviewed in the October 14 research pass; not independently audited.` | `Appen China revenue in Note 3 (segment information) of the financial report in Appen's 2025 annual report, released to the ASX on 25 February 2026. The same note gives the Appen Global figure, graded A.` |
| `appen.claim.oct14-major-financial-1` | `evidence_label` | `Attributed primary-source evidence` | `audited public company` |

`audited public company` is the label of the FY2023 and FY2024 Appen revenue claims. The app shows it as "Public company annual report" (`evidenceLabel` in `web/app.js`, `PROFILE_EVIDENCE_LABELS` in `web/profiles-v2.js`), because the site never calls these figures "audited". Bindings do not change. `data/business-health.json` copies each claim's `evidence_label` into `evidence_assurance`, so the observation `appen.metric.major-financial_metrics-2` must be updated at the step 4 rebaseline (see below). The other 43 filing-backed claims graded B are right under the rubric: unaudited TaskUs releases and slides, guidance, inherited gate grades, syntheses, company descriptions, supplier customer claims, and statements whose shown figure is not in the filing.

**10. Scale AI shareholder-payout wording.** Wording only; no source was rechecked for this item. Three fields on two records say "Includes shareholder liquidity; not equivalent to new primary venture funding." Readers see the claim statement when they open the evidence for the $14.3B Meta stake. The Scale readout uses the same term ("included substantial shareholder liquidity"), and `scale_ai.editorial` repeats it, so five fields on four records change. The new wording keeps the meaning in plain words and uses the app's own label for mixed deals ("The total is not all new company funding."). Amounts, dates, sources and grades stay as they are.

| Record | Field | 2.5.0 | 2.5.1 |
| --- | --- | --- | --- |
| `scale_ai.claim.oct14-major-financial-0` | `statement` | `$14.3B Meta stake investment. 49% stake. Includes shareholder liquidity; not equivalent to new primary venture funding.; Scope: company; Original period/date: 2025-06-12; Revenue/accounting basis: not disclosed` | `$14.3B Meta stake investment. 49% stake. Part of the money went to existing shareholders. The total is not all new company funding.; Scope: company; Original period/date: 2025-06-12; Revenue/accounting basis: not disclosed` |
| `scale_ai.claim.oct14-major-financial-0` | `caveat` | `49% stake. Includes shareholder liquidity; not equivalent to new primary venture funding.; Scope: company; Original period/date: 2025-06-12; Revenue/accounting basis: not disclosed` | `49% stake. Part of the money went to existing shareholders. The total is not all new company funding.; Scope: company; Original period/date: 2025-06-12; Revenue/accounting basis: not disclosed` |
| `scale_ai.metric.oct14-major-financial-0` | `basis` | `49% stake. Includes shareholder liquidity; not equivalent to new primary venture funding.; Scope: company; Original period/date: 2025-06-12; Revenue/accounting basis: not disclosed` | `49% stake. Part of the money went to existing shareholders. The total is not all new company funding.; Scope: company; Original period/date: 2025-06-12; Revenue/accounting basis: not disclosed` |
| `scale_ai.claim.audit-readout` | `statement` | `Scale has the strongest combination here of long-lived delivery examples, a buyer-confirmed government award, major financing and a large reported revenue base. It now spans data, evaluations, enterprise applications and public-sector systems, so reducing it to an annotation marketplace is misleading. Meta’s investment changed its ownership and commercial context and included substantial shareholder liquidity. The latest public update emphasizes bookings and applications growth; it does not supply an audited 2025 revenue amount.` | `Scale has the strongest combination here of long-lived delivery examples, a buyer-confirmed government award, major financing and a large reported revenue base. It now spans data, evaluations, enterprise applications and public-sector systems, so reducing it to an annotation marketplace is misleading. Meta’s investment changed its ownership and commercial context and included large payouts to existing shareholders. The latest public update emphasizes bookings and applications growth; it does not supply an audited 2025 revenue amount.` |
| `scale_ai.editorial` | `readout` | `Scale has the strongest combination here of long-lived delivery examples, a buyer-confirmed government award, major financing and a large reported revenue base. It now spans data, evaluations, enterprise applications and public-sector systems, so reducing it to an annotation marketplace is misleading. Meta’s investment changed its ownership and commercial context and included substantial shareholder liquidity. The latest public update emphasizes bookings and applications growth; it does not supply an audited 2025 revenue amount.` | `Scale has the strongest combination here of long-lived delivery examples, a buyer-confirmed government award, major financing and a large reported revenue base. It now spans data, evaluations, enterprise applications and public-sector systems, so reducing it to an annotation marketplace is misleading. Meta’s investment changed its ownership and commercial context and included large payouts to existing shareholders. The latest public update emphasizes bookings and applications growth; it does not supply an audited 2025 revenue amount.` |

`scale_ai.editorial.readout` repeats `scale_ai.claim.audit-readout.statement` word for word; keep them the same. The readout comes from `data/raw/major-audit/major-ten-corrections.json` at `/companies/4/commercial_verdict`. The October 14 records carry no `raw_path`, so fix the note that the October 14 pass turns into their statement, caveat and basis, and keep the `; Scope: …` suffix that pass adds. The funding-round note "Includes ownership transfer or shareholder liquidity; not a pure primary-capital amount." on six rounds is not part of this item. Until 2.5.1, `web/app.js` shows the new wording through an interim block in `PUBLIC_COPY_EDITS`.

**Checked, no record change.** Turing's $300M run rate for 2024 (release of 28 January 2025) and its $167M run rate at the time its Series E was priced (release of 6 March 2025) are two observations, and both records match their sources. The app explains why the undated $167M figure lists first with a note in `PUBLIC_COPY_EDITS`, which stays valid after 2.5.1. Nine more same-figure repeats from the 14 October pass (Abundant, AfterQuery three times, Bespoke Labs, Proximal, Surge AI, Terac twice) are folded into one tile each by `SAME_OBSERVATION` in `web/app.js`. Retiring them needs care per record, because some of their claims back the dashboard or other figures, so they are left to a later release.

**Optional.** `elorian.claim.worker_opportunities-0` says "Live Model Safety Contractor role" as of 2026-10-12. The listing showed "Job not found" on 2026-10-23. The work sidecar already marks the route historical.

## Release mechanics

Do these steps in this order. If the dataset version moves before steps 1 and 4 are done, the published corrections and the dated events silently disappear.

1. Remove the literal `2.5.0` snapshot checks. They are in `validate_relationship_assessment_context` (Terac) and `validate_historical_offer_context` (Ooak) in `scripts/observatory.py`, and in `relationshipAssessmentContextValid` (Terac) and `historicalOfferContextValid` (Ooak) in `web/source-updates.js`. Keep only `snapshot.dataset_version === DATA.dataset_version` and its Python twin.
2. Rebaseline `data/source-updates.json`. Set `baseline_dataset_version` and every `historical_snapshot.dataset_version` to `2.5.1`. `handshake-reporting-context-2026-10-17` snapshots the Handshake rows changed above, so retire it, because 2.5.1 now carries the 14 April date. No other snapshot contains a changed row. Items 6 to 10 change no row in any snapshot.
3. In the research repository, set `dataset_version` to `2.5.1`, update `meta.as_of` and add one line to `meta.coverage_notes`. Then run `python3 scripts/observatory.py import <canonical>`. It checks every raw file and writes `data/versions/2.5.1.json`, `data/canonical.json` and `dist/`.
4. In this repository, copy in `data/canonical.json` and `data/versions/2.5.1.json`. In the same commit, set `SIDECAR_DATASET_VERSION = "2.5.1"` in `scripts/observatory.py`. That one constant decides four things: whether `validate_work_routes` runs its reference checks, whether `build` sets `SOURCE_UPDATES` (it is `None` for any other version), whether `load_company_events` ships `data/company-events.json`, and whether `load_business_health` loads the dashboard. For any other version `load_company_events` returns no events, so every dated lawsuit and event would drop from the profiles and static pages. `tests/test_company_events.py` fails if that happens. After the bump the build stops with `business-health: source dataset version differs` until `data/business-health.json` is rebaselined: set its `source_dataset_version` to `2.5.1` and recheck every observation's `claim_ids`, `metric_ids` and `source_ids` against 2.5.1, because the loader rejects a binding that no longer resolves to a supported same-company claim. Then set `PINNED_VERSION = '2.5.1'` and `PINNED_SHA256` in `tests/redesign_checks.py` to the `sha256` printed by the import, and update the comment above them. When you rebaseline `data/business-health.json`, also change `evidence_assurance` of observation `appen.metric.major-financial_metrics-2` from `Attributed primary-source evidence` to `Public company annual report`, because item 9 changes the `evidence_label` of its bound claim. The dashboard prints this field as stored (`web/business-health.js`), so never paste the raw `audited public company` label. Items 6 to 10 change no binding, and no observation binds a claim that items 6 and 8 retire.

   Tests to update in the same commit: only the two pins in `tests/redesign_checks.py` above. The checks in `tests/js_logic.py` for items 6, 8 and 10 pass before and after 2.5.1: one Mercor $2B tile, one Toloka 200K tile, the retired claims still listed on the profile, and the plain Scale AI wording, which 2.5.1 stores word for word. No test pins a grade that item 9 changes, because `tests/test_static_pages.py` reads grades from the data. Run every check in `.github/workflows/ci.yml`.
5. Clean up. Keep the link-health entries for the three dead URLs while they appear under "Previous citations". Remove any interim display rewrite of the BenchFlow statement in `web/app.js`. Remove the `SAME_OBSERVATION` entries in `web/app.js` for `mercor.metric.major-growth_metrics-0` and `toloka.metric.major-growth_metrics-3`; they do nothing once those claims are superseded. Remove the interim Scale AI block from `PUBLIC_COPY_EDITS` in `web/app.js` (its comment names 2.5.1), and drop "until 2.5.1" from the comment above the Scale AI checks in `tests/js_logic.py`.

## Already fixed in the public sidecars (23 October 2026)

- `data/work-routes.json`: The Elorian Model Safety Contractor route is now historical (`official_role_not_found`), and the G2I Senior Software Engineer, AI Training listing is live again. The Labelbox pay FAQ link has moved to intercom.help, and the BenchFlow evidence no longer includes the address.
- `data/link-health.json`: New entries cover the dead `help.labelbox.com`, Leila Janah Foundation and Elorian posting URLs. Existing entries were rechecked, except the Caltech preprint, whose host fails certificate checks through this session's proxy.
- `data/company-events.json`: Meta's reported April 2026 pause of Mercor work is a dated event that cites Business Insider and TechCrunch. It also gives Mercor's 25 June 2026 statement that all frontier labs had increased their work with it, which does not name Meta. The Mercor relationship card for Meta carries only the Sacra relationship and its own evidence.
