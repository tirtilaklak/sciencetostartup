# Independent publication v3 technical review

Verdict: PASS for the reviewed publication code after two confirmed export privacy defects were corrected. No unresolved findings remain in this scope. This is a code and artifact-contract review, not research synthesis approval, a production publication receipt, or deployment validation.

Reviewed base: 2f8611cad3c89d670d084d9b92d3269a939a41c5 plus coordinator-owned changes. Source hashes were frozen before tests; final hashes are in source-hashes-final.json. Source files remained stable during the final targeted run; later test/doc edits were reread and the final public-block test cohort was rerun. No tracked files were edited by this reviewer, no dist build/deploy was performed, and no publication, mirror or outreach request was sent.

Final source hashes:

- scripts/research_citations.py: e14ec5155537f0a1d0fe92c1c4894493d47adfd7fbda2226e2c15cf75bc1546b
- scripts/research_pdf.py: 7add221b4ee5f61e09a0e9a303ff00dfae769d80a8e329089b8631bdb14f0ea1
- scripts/research_brief.py: b3b3dc94f62e0d4970af76f588e0fc3f4dde09947fbdc6d62c6d356211b1e658
- tests/test_research_public_blocks.py: 0c126f8acf0017449e4ca87137c8860060cfdc89a7413388a2a2efc17d78a6ea

Resolved findings:

1. P1: METHODS.md copied candidate-linked paragraph text even when the report, HTML and source context withheld it. The final package writer applies paragraph_supported at scripts/research_citations.py:734. A synthetic held-method sentinel is now absent from every loose package file and every uncompressed ZIP member, while allowed method prose and a withholding explanation remain.
2. P2: offline_html escaped its title but bypassed privacy_filter. A synthetic email and credential were redacted from report.md but present in the HTML title. The final direct renderer filters report and gate at scripts/research_citations.py:284 and escapes the filtered title at :340. Whole-package/ZIP probes now pass. Direct rendering also prevents report prose from being reparsed as generated HTML/anchors.

Independent execution evidence:

- Initial focused publication suite: 62 tests passed with the bundled ReportLab/pypdf Python, no skips.
- Rendering, reader and published replay/privacy suite: 34 tests passed in 127.520 seconds, no skips. The real graph snapshot loaded at this run was the then-current 1,752-assertion snapshot; later scientific graph additions were outside this code review.
- Final direct-renderer targeted suite: 68 tests passed in 14.135 seconds, no skips. Includes citations, context contracts, publication adapters, brief, held paragraphs, and five reader contracts. See sts-independent-v3-direct-renderer.log.
- Final changed public-block cohort: 6 tests passed in 0.194 seconds, no skips. Includes final archive title-email/credential sentinels and chapter navigation stable under a heading rename. See sts-independent-v3-final-public-blocks.log.
- Independent custom probes: every loose file and every ZIP member excludes held method text, title email and title credential; a small synthetic PDF is byte-deterministic, redacts title/body, and names the actual offline reproduce.py instruction. review-counterexamples.py reproduces the archive privacy probes.
- Synthetic v3 digest probes: changing held wording, updated_on or source_cutoff invalidates the context; reservation=False planning is stable through reservation; reserved freeze identity is stable through publication receipt/lifecycle and superseded status overlays.
- Both standalone imports and scripts.research_brief / scripts.research_citations / scripts.research_pdf named imports passed.

Actual archived v2 evidence, without fabricated publication status:

- Current read_prepared_package successfully read the actual archived prelaunch.3 package against its exact historical raw graph reconstructed from tracked commit 89c416a. The original graph commitment and complete source-context bytes matched. The original ten-input recipe worked with LOCATORS.md absent; 32 frozen files returned. See actual-v2-current-reader-compatibility.json.
- Actual archive: 29 manifest files, 30 exact ZIP members, 2,225,747 bytes; all checksums, ZIP bytes, member bytes, JSON/CSV/SQLite equivalence and offline table reproduction passed. ZIP SHA-256 a1d4934b4f16ec97849b1af4a4ab789afb71a52d336249797cb6c6e3d34f6b83. See actual-v2-reproduction.json.
- All 38 original frozen/sibling files remained byte-identical to base commit 2f8611c. Canonical 2.5.0 SHA-256 remained 948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061.

Browser evidence uses explicitly SYNTHETIC TEST ONLY content, never production research:

- Chromium at 390 x 844: brief and final report document width = viewport width = 390; zero script elements; confidence, limitations, reasoning, and what-would-change text remain visible. Final report TOC uses one column on mobile. Screenshots in output/playwright/.
- Actual chapter and assertion evidence links were clicked and reached existing local targets; the assertion target retained qualifications, locator, excerpt hash, and three review links. Brief-to-full-finding target also resolved.
- Injected script and anchor markup stayed literal text; no forged finding anchor existed. Only console error was the local server's missing optional favicon, not a rendering/script failure.

Synthetic fake-remote tests verify state-machine contracts only. No real DOI registration, production publication, deployment, or current scientific readiness is established by this review.
