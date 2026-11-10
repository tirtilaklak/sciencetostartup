# Public correction records

`data/research/corrections.json` retains affected stable claim identifiers and explanations. An accepted record can name a distinct approved `replacement_claim_id`; the seven-field legacy format remains valid when no replacement is recorded. Acceptance records a research correction and does not claim publication or distribution.

The initial 26 records document citation locator, context and extraction repairs. Their scientific assertion values are unchanged. Each timestamp is the latest actual PASS-review time for its replacement. Summaries identify the replacement's three recorded review receipts. Original candidates and their positive and negative receipts remain in the research graph.

`research_corrections.py` validates the registry and projects only accepted or published records. Pending and rejected summaries stay private. Public summary text redacts email contacts and credential patterns. The live correction page and its RSS/Atom feeds use the same projection as the archival `corrections.json`.

The script-free offline evidence appendix preserves old identifiers as metadata-only anchors when they are absent from the public graph. Each points to its correction explanation and approved local replacement. It never restores unapproved wording or old source excerpts.

Context contract V3 binds the exact public correction projection and an opaque SHA-256 commitment to the raw correction input. A private proposal change therefore invalidates an unpublished prepared context without redistributing that proposal. The archive manifest covers `corrections.json`; the owned reproduction inventory includes the validator and schema. V1/V2 source-context bytes and reproduction allowlists are unchanged. Existing PDF receipts must be regenerated after this V3 input change; they must not be retargeted.
