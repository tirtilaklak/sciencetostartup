# Market publication-date review, 22 November 2026

The retained publisher responses show three article datelines. Codex source review applied them to the five exact citation IDs below. The receipt scope is article publication date. Each correction binds the original source record in `data/source-updates.json`. The response timestamps record the retained publication retrieval in UTC. The October research dates and content checks remain separate.

| Exact source ID | Publisher date | Original research record | Separate October page read |
| --- | --- | --- | --- |
| `afterquery.source.round2-funding` | 2026-04-09 | 2026-10-14 | 2026-10-28 |
| `afterquery.source.oct14-fd3e4675dd42` | 2026-04-09 | 2026-10-14 | — |
| `datacurve.source.oct14-9b179f419da7` | 2025-10-09 | 2026-10-14 | — |
| `scale_ai.source.oct14-891cd0d871ee` | 2025-07-01 | 2026-10-14 | 2026-10-28 |
| `surge_ai.source.oct14-891cd0d871ee` | 2025-07-01 | 2026-10-14 | 2026-10-28 |

The AfterQuery article displays “Apr 9, 2026” in its `time` element. Both exact records cite the same direct URL. The 09:01:44 UTC response body SHA-256 is `41a816cbd0b8359effa729aa64f8ff7aadfd6e49936e563192f7aca6774fec59`. [AfterQuery article](https://www.afterquery.com/blog/human-expertise-reimagined)

Chemistry displays “October 9, 2025” in the article date block. The stored URL directly returned the article URL. The 09:01:44 UTC response body SHA-256 is `3b23bcfac2d494cb86c002d4e0034d19844dbe952edcc12687a3823fa5a4b235`. [Chemistry article](https://www.chemistry.vc/post/staying-ahead-of-the-curve)

Reuters via AOL displays “Tue, July 1, 2025 at 3:23 PM UTC” in its `time` element. Both exact records cite the `/news/` URL. That endpoint returned HTTP 308 to the canonical endpoint, which returned HTTP 200. The 09:02:16 UTC response body SHA-256 is `52b85943e89d7a23afc6a2c62d44dfe632cc9677bc347609453388ba5245c8cd`. [Stored AOL route](https://www.aol.com/news/exclusive-scale-ais-bigger-rival-152327362.html) · [Canonical AOL route](https://www.aol.com/exclusive-scale-ais-bigger-rival-152327362.html)

Three already-dated records keep their original roles and 2026-10-12 research dates. `afterquery.source.b_aq3` and `surge_ai.source.b_sg4` are summary-only records in the research snapshot. The Surge canonical-endpoint record also has a distinct 2026-10-28 content-check receipt. `datacurve.source.audit-chemistry` is an earlier checked record. First Round’s Labelbox interview had a date in markup and no visible dateline in the retained response. This review leaves its publication date unassigned and preserves the December 2018 reporting snapshot.

The publication evidence was replayed against the fourth candidate `43337bbf50aa5f39ee75`. Its frozen `research.json`, canonical dataset and stored 2.5.0 release all have SHA-256 `948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061`. The retained publisher receipt digest is `e92388cad27d8c868440ee5de60e8d6038d75b81f4391aa7258c177dccdf197f` and the original browser receipt digest is `ec6c23af97f2b83f9533fa9aaab90f3fa5df34c2c704fc02591645ebd798be08`.
