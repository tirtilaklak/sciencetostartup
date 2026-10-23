# Pending 2.5.1 corrections

Prepared 23 October 2026. Every source below was rechecked live on that date.

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

**Optional.** `elorian.claim.worker_opportunities-0` says "Live Model Safety Contractor role" as of 2026-10-12. The listing showed "Job not found" on 2026-10-23. The work sidecar already marks the route historical.

## Release mechanics

Do these steps in this order. If the version moves before step 1, every published correction silently disappears.

1. Remove the literal `2.5.0` checks. They are in `scripts/observatory.py` at line 371 (Terac snapshot), 416 (Ooak snapshot), 560 (work-route reference checks) and 646 (`SOURCE_UPDATES` is set to `None` for any other version), and in `web/source-updates.js` at line 46 (Terac) and 97 (Ooak). In the snapshot checks, keep only `snapshot.dataset_version === DATA.dataset_version` and its Python twin. Lines 560 and 646 should use one constant set per release, and the build should fail if `data/source-updates.json` `baseline_dataset_version` differs from it.
2. Rebaseline `data/source-updates.json`. Set `baseline_dataset_version` and every `historical_snapshot.dataset_version` to `2.5.1`. `handshake-reporting-context-2026-10-17` snapshots the Handshake rows changed above, so retire it, because 2.5.1 now carries the 14 April date. No other snapshot contains a changed row.
3. In the research repository, set `dataset_version` to `2.5.1`, update `meta.as_of` and add one line to `meta.coverage_notes`. Then run `python3 scripts/observatory.py import <canonical>`. It checks every raw file and writes `data/versions/2.5.1.json`, `data/canonical.json` and `dist/`.
4. In this repository, copy in `data/canonical.json` and `data/versions/2.5.1.json`. Set `PINNED_VERSION = '2.5.1'` and `PINNED_SHA256` in `tests/redesign_checks.py` to the `sha256` printed by the import, and update the comment above them.
5. Clean up. Keep the link-health entries for the three dead URLs while they appear under "Previous citations". Remove any interim display rewrite of the BenchFlow statement in `web/app.js`.

## Already fixed in the public sidecars (23 October 2026)

- `data/work-routes.json`: The Elorian Model Safety Contractor route is now historical (`official_role_not_found`), and the G2I Senior Software Engineer, AI Training listing is live again. The Labelbox pay FAQ link has moved to intercom.help, and the BenchFlow evidence no longer includes the address.
- `data/link-health.json`: New entries cover the dead `help.labelbox.com`, Leila Janah Foundation and Elorian posting URLs. Existing entries were rechecked, except the Caltech preprint, whose host fails certificate checks through this session's proxy.
- `data/profile-content.json`: The Mercor relationship card for Meta now notes the April 2026 pause reported by TechCrunch (9 April) and HR Dive (13 April), both citing Wired.
