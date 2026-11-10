# Research preparation and edition operations

All scheduler actions are offline. They write only a separate state directory;
they never change canonical data, `web/`, `dist/`, external accounts, or the
production website. Current policy is `prepare_only` because Zenodo and Hugging
Face are not connected. A prepared package, reserved DOI, published archive,
mirror sync, and website deployment are distinct states.

## Local calendar

Prepare daily at **16:00 America/Los_Angeles**. Target weekly editions at
**Monday 09:00 America/Los_Angeles**, using source versions captured by the
preceding **Friday 17:00**. `zoneinfo` constructs each wall-clock instant from
its local calendar date. Across a DST transition, cutoff and publication may
have different UTC offsets; subtracting a fixed number of UTC hours is wrong.

The scheduler rejects naive timestamps and date-only source capture values.
Capture at the cutoff is allowed; capture one second later is not. Review may
occur later against the captured source version. Its review date stays later.
Never backdate a capture or relabel a later source as an earlier version.

```sh
python3 scripts/research_schedule.py status
# Daily preparation: the upcoming edition.
python3 scripts/research_schedule.py prepare --state-directory output/research-state
# Monday publication check, or a catchup after the local computer was offline.
python3 scripts/research_schedule.py prepare-due --state-directory output/research-state
# Equivalent explicit due selection:
python3 scripts/research_schedule.py prepare --due --state-directory output/research-state
# A deliberately selected Monday:
python3 scripts/research_schedule.py prepare --edition 2026-11-16 --state-directory output/research-state
```

The `status` command reports the latest due Monday, next Monday, and whether
today's 16:00 preparation is due. Daily `prepare` selects `next_edition`.
Weekly jobs must call `prepare-due` (or `prepare --due`), which selects
`latest_due_edition`. At Monday 09:00 these are different editions: a run on
2026-11-09 at 17:00 UTC stages **2026-11-09** with `prepare-due`, while daily
`prepare` stages **2026-11-16**. A Wednesday catchup still selects that week's
Monday. Before Monday 09:00, the latest due edition is the preceding Monday.
A local computer that was offline cannot run retroactively or claim an on-time
release; every journal entry and preparation retains its actual timestamp.

Preparation stages a deep copy of graph/report/policy/public identity and, when
present, the roles registry. It never edits those source inputs. The staged
report gets the Monday `edition_date`, deterministic first-release identity
`research-YYYY-MM-DD.1`, the Friday `source_cutoff`, and scheduled `publish_at`.
Actual `prepared_on` stays outside the stable input identity; source capture and
review dates, graph/audit release bindings, and content `updated_on` are not
relabelled. An old archive receipt or reserved DOI is cleared when staging a new
edition. Staging sets the report status to `prepared`, never `published`.
Corrections to an already released edition use the separate revision process.

## Frozen core continuity

The first validated, nonempty `coverage.frozen_core.entity_ids` inventory is
recorded as `core_frozen` in the shared scheduler journal **before** readiness is
evaluated. This also happens while coverage is incomplete and the candidate is
held. A gate interruption therefore cannot discard the declared denominator.
The certificate records the actual sorted IDs, their frozen-core digest, the
source graph digest, and an immutable source snapshot digest. Invalid graphs
write no snapshot or journal state. The journal and referenced snapshots must be
preserved together across daily preparations, catchups, and later editions.

An unchanged inventory reuses its certificate, including after draft, source,
review, or identity changes. A strict superset records `core_expanded`, bound to
its exact validated graph and preceding inventory digest. Every previously
frozen ID must remain in the declared universe: documented exclusions and
historical-only dispositions do not remove IDs. Rewriting eligibility flags,
freeze metadata, or the inventory hash cannot authorize a smaller inventory or
return it to an unfrozen state. An ordinary job has no shrink override; a genuine
scope correction needs an explicitly versioned methodology process.

Before accepting an inventory, the scheduler also reconciles older journaled
preparations, activations, or published snapshots that predate certificates.
Their immutable source bindings establish the retained inventory; a new empty
declaration cannot erase it. Divergent historical inventories require a validated
source graph retaining their union. Missing, changed, or invalid historical
sources stop processing for inspection.

Coordinator approval, local activation (including `already_active` retries),
and exports authorized by an archive receipt recheck the latest recorded
inventory. A candidate prepared before a later expansion cannot authorize
release until a new candidate retains the expanded scope. Read-only historical
resolution and ordinary prepared exports still preserve the older frozen inputs.

## Exact identity, coordinator review, and retries

Each candidate binds its edition date, report release, calendar window, and all
input digests. Identical input retries resume the same candidate and its original
preparation timestamp; changed input produces another candidate requiring its own
review. Two editions remain distinct even when no facts changed. A preparation
is not itself a publication attempt. Current missing research/archive prerequisites
are printed as `held` with reasons.

Frozen input objects live in `snapshots/<snapshot-sha256>.json`; candidates in
`candidates/<candidate-sha256>.json` bind them by digest. Compact per-edition
references live in `editions/<Monday>/<candidate-sha256>.json`. These files are
immutable and verified on retry. No credentials or raw caches belong in this
public state. Candidate records include a separate digest over their actual
preparation metadata so a changed timestamp is detected too.

An older edition must resolve its stored inputs, never fall back to the current
report. The coordinator can use `load_edition(state, "2026-11-09", candidate_id)`
or `resolve_edition_reference(state, entry)` from `research_schedule`. The latter
accepts a `candidate_sha256` and/or `snapshot_sha256` compact reference and checks
its release binding. To feed the existing renderer, hydrate each reference as
`{**entry, **resolve_edition_reference(state, entry)}` before rendering. Recompute
its publication gate and require its actual archive receipt; a stored preparation
or an entry labelled published does not establish publication. Without a candidate
digest, `load_edition` selects that Monday's latest journaled preparation.

Older embedded snapshots in `report.editions` are externalized to compact digest
references when staging. Nested edition histories are externalized as well, so
freezing another weekly report does not embed every prior report inside itself.
Current canonical `report.editions` is empty: this storage does not invent a
published history, public edition URL, or feed item.

## Committable edition source snapshots

Scheduler state defaults to `output/research-state`, outside disposable `build/`
artifacts. Preserve that directory and its journal across local runs. State files
are operational inputs, not an automatically published or tracked edition ledger.

Export one verified candidate's public source inputs to a deliberately selected
JSON file with:

```sh
python3 scripts/research_schedule.py export-edition --candidate SHA256 \
  --output output/research-2026-11-09.1.prepared.json
```

The helper `export_edition(state, candidate_id, output)` writes deterministic
JSON and a sibling `.receipt.json`. The receipt includes the **SHA-256 of the
exact JSON file bytes** as `snapshot_sha256`, its byte count, original candidate
and frozen snapshot digests, edition/release identity, and actual preparation
time. An exact retry writes the same bytes. Existing different output cannot be
overwritten. The source file contains graph, report, policy, public identity,
and roles; its `report.editions` is empty to avoid recursive histories. Private
or credential-bearing inputs make export fail rather than silently redacting
bound evidence. Correct the public inputs and prepare a new candidate instead.

Default exports remain `prepared` / `not_published`. After actual archive
publication, the caller may supply the real receipt from
`Release.archive_receipt()` with `--archive-receipt /absolute/path/archive.json`.
It must bind the exact release and artifact, identify verified **production**
Zenodo publication, preserve any frozen reserved DOI/deposition identity, and
pass the authoritative final gate. Its confirmation must follow the edition's
publication window. This overlay affects only the exported copy, never the
frozen scientific candidate. Only a passing receipt overlay permits exported
`report.status: published`; invalid or still-held receipts produce no output.
Use a separate final output filename rather than overwriting a prepared export.

A final source export can then be committed under `data/research/editions/`.
The coordinator's `report.editions` entry uses `snapshot_path` relative to
`data/research`, such as `editions/research-2026-11-09.1.json`, and the sidecar's
raw-file `snapshot_sha256`. The loader must reject unsafe paths, hash mismatches,
or release mismatches before hydrating the renderer. Preparing/exporting a file
does not itself add an entry or claim an earlier edition exists.

The actual archive receipt may postdate the graph's evidence `as_of` and Friday
source cutoff: those timestamps describe different events. Source and review
dates remain unchanged. Published rendering also needs the exact frozen package,
`PREPARED.json`, and artifact digest at the receipt's `bundle_path`, preferably a
tracked `data/research/releases/<release-id>/publication` bundle. This source
export and its SHA receipt do not substitute for those verified archive bytes.

## Coordinator review and local activation

An actual coordinator review receipt can be imported with:

```sh
python3 scripts/research_schedule.py approve --candidate SHA256 --receipt /absolute/path/approval.json
python3 scripts/research_schedule.py activate --candidate SHA256
# Once the archive was actually published after the preparation snapshot:
python3 scripts/research_schedule.py activate --candidate SHA256 \
  --archive-receipt /absolute/path/archive.json
```

The receipt needs `candidate_sha256`, `release_id`, `decision: approved`,
`approved_by`, `approved_on` (aware timestamp), `rationale`, `role: coordinator`,
`reviewer_type: ai` (or `human` only for an actual human review), a distinct
`invocation_id`, `method: final_quality_review`, and `fixture: false`. Its time
must follow actual preparation and cannot be in the future. Scientific quality
(`archival_ready`) must already pass. A real AI coordinator may approve; there is
no human approval requirement. Importing a receipt does not perform the review or
manufacture approval, and it cannot turn a failed scientific gate into a pass.

`activate` records local activation only after scientific and archive gates,
actual coordinator review, the publication window, and `publish_enabled` policy
all pass. An optional `--archive-receipt` overlays a later actual publication
receipt in a transient context and rechecks the final gate. It cannot edit the
candidate's science identity or frozen inputs. Activation journals that receipt's
digest, release, exact artifact digest, and actual confirmation time; it refuses
a future confirmation or a different receipt on retry. It does not publish to
external services. Present policy therefore holds every activation attempt. A production release adapter must additionally
verify actual account connections, archive and mirror receipts, exact-artifact
preview tests, and serialized website promotion. Changing JSON policy is not
evidence of an external publication.

Activation dates advance monotonically. A delayed old job cannot replace a newer
edition. Retrying the active candidate returns `already_active` and restores the
convenience pointer if a prior process stopped after journaling. An activation
records `activated_on`, `scheduled_publish_at`, and whether it occurred at the
window or was delayed. Delayed work keeps its actual later time; local activation
still reports `publication: not_published` and performs no external mutation.
Do not overwrite an already active edition's identity.

## Lock and journal recovery

The state directory has an exclusive local lock containing hostname, PID and a
random ownership token. Live locks are never stolen. A stale lock is recovered
only when its local owner PID no longer exists. A malformed lock or a lock from
another host requires inspection; age alone does not establish safe recovery.

`journal.jsonl` is append-only, fsynced, sequenced and hash chained. It is the
authoritative history for frozen-core inventories, prepared, approved, held and locally activated states.
Candidate writes are atomic and fsynced; a crash after candidate write but before
journaling resumes by verifying the existing candidate and recording the missing
event. A crash after activation journaling resumes from the journal.

A changed event, broken chain, or incomplete final line stops processing. Preserve
the original journal and inspect the interrupted tail before recovery. Do not
silently truncate history, delete approvals, or advance activation to make a job
green. No journal state can stand in for external publication receipts.

Ordinary builds and scheduling need no credentials. When external accounts are
connected later, keep their credentials outside the repository and implement
network mutations only through the separately reviewed release adapters.
