# Cloud Daily candidate builder

The candidate builder moves generated public files through Git on a GitHub
runner, without putting multi-megabyte payloads in connected-tool arguments.
It prepares an isolated branch; it does not merge `main`, publish Cloudflare
assets, or certify the required CI/browser/performance checks.

## Reviewed input

Install the helper and workflow on trusted `main` before opening a build request.
The installation PR has no Daily JSON and does not execute the builder. A build
PR must have base `main`, belong to this repository, and use a head branch named
`codex/cloud-daily-YYYY-MM-DD`. Its complete base-to-head input diff must add
exactly `data/daily-scan/YYYY-MM-DD.json`; scripts, configuration, old snapshots,
and generated output are not accepted as input changes.

Use a strict JSON PR body with these fields. Replace every placeholder with
reviewed public build metadata; the example deliberately fails validation.

```json
{
  "date": "YYYY-MM-DD",
  "baseline_commit": "REVIEWED_MAIN_COMMIT_SHA",
  "baseline_manifest_sha256": "SHA256_OF_BASELINE_DIST_MANIFEST",
  "outgoing_cloudflare_version": "VERIFIED_PRODUCTION_VERSION_UUID",
  "daily_sha256": "SHA256_OF_REVIEWED_DAILY_JSON",
  "compiled_at": "EXACT_TIME_FROM_REVIEWED_DAILY_JSON",
  "expected_candidate_manifest_sha256": null
}
```

The baseline commit must equal the PR base. The Daily date, Pacific timezone,
source digest and timezone-aware compilation time must match the reviewed JSON.
The helper never creates a fresh compilation timestamp. If a candidate was
already frozen, supply its expected manifest digest; a mismatch stops the build.
The publisher must independently verify the baseline's relationship to the live
production version. The workflow has no Cloudflare access to establish that.

Private research, publishing controls, authorization records and operational
receipts must stay outside this public input and workflow artifacts.

## Candidate preparation

The workflow checks out the helper from the trusted base and validates the
entire input before running repository code or installing packages. It uses
Python 3.12, Node 22, `npm ci`, and `requirements-qa.txt`. Checkout credentials
are not persisted, and build subprocesses do not receive token/key/secret
environment variables.

Before building, it reads the pinned baseline's current summary and root/Explore
HTML entrypoints, follows their runtime references, and verifies asset hashes.
It retains that outgoing runtime generation plus the newest previous generation
in `release-assets/`. The candidate's own generated files never become the
retention baseline.

The existing public builder writes to a separate empty directory. Every output
hash and prior dated snapshot JSON is checked, then only `dist/` and
`release-assets/` are committed after exact-build verification. Unexpected staged
or unstaged changes stop preparation. The single push uses the runner's built-in
token only in that step, an explicit isolated branch, and an exact expected-head
lease. A failed or interrupted push requires branch readback before another
attempt; it is not retried automatically.

## Final CI and publication

The builder uploads its public commit/tree/manifest receipt. After verifying
those identities, the existing GitHub App creates a child commit with the same
tree and moves the PR branch against the expected builder head. That App update
triggers the unchanged PR checks without relying on token-generated push events.
The builder skips synchronize events that did not change the dated source JSON,
so its own output and a same-tree checkpoint do not create a build loop.

Verify the actual final CI runs, source and checkout trees, full unit coverage,
browser partitions, accessibility, performance and exact artifact. A prepared
branch or an acknowledged push is not a passing release. Publication still uses
the repository's separate exact-artifact and coordination process.

Before enabling this path, verify the App's workflow-file/commit/ref access,
effective `contents: write` permission on the runner, the real PR/checkpoint
trigger sequence, baseline retention, runner build reproduction and cloud
retrieval of the committed artifact. No new API key or credential is needed.
