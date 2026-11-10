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
python3 scripts/research_schedule.py prepare --edition 2026-11-16 --state-directory build/research-state
```

The `status` command reports the latest due Monday, next Monday, and whether
today's 16:00 preparation is due. `prepare` defaults to the next edition, freezes
its graph/report/policy/public-identity inputs, computes the strict gate at that
edition's cutoff, and writes a candidate keyed by SHA-256. It prints `held`
with reasons when prerequisites are missing. A scheduler should call `status`
before preparing, and explicitly choose the latest due edition for a Monday
publication check. A daily preparation is not itself a publication attempt.

## Exact identity, approval, and retries

Each candidate binds its edition date, report release, window, and the digests
of all inputs. Identical input retries resume the same candidate; any changed
input produces a new identity requiring its own approval. Candidates contain
only the public projection and public report inputs; no credentials or raw
caches belong in state that may be archived.

An existing approval receipt can be imported with:

```sh
python3 scripts/research_schedule.py approve --candidate SHA256 --receipt /absolute/path/approval.json
python3 scripts/research_schedule.py activate --candidate SHA256
```

The receipt needs `candidate_sha256`, `release_id`, `decision: approved`,
`approved_by`, `approved_on` (aware timestamp), and `rationale`. Importing a
receipt does not perform research review or manufacture approval. It must name
the exact prepared candidate; a later edit invalidates the binding. A held
candidate remains held even if an approval receipt is imported.

`activate` records local activation only after the scientific and archive gates,
explicit approval, publication window, and `publish_enabled` policy all pass.
It does not publish to external services. Present policy therefore holds every
activation attempt. A production release adapter must additionally verify
actual account connections, archive and mirror receipts, exact-artifact preview
tests, and serialized website promotion. Changing JSON policy is not evidence
of an external publication.

Activation dates advance monotonically. A delayed old job cannot replace a
newer edition. Retrying the active candidate returns `already_active` and
restores the convenience pointer if a prior process stopped after journaling.
Corrections to an active edition require the documented new release process;
do not overwrite an already active edition's identity.

## Lock and journal recovery

The state directory has an exclusive local lock containing hostname, PID and a
random ownership token. Live locks are never stolen. A stale lock is recovered
only when its local owner PID no longer exists. A malformed lock or a lock from
another host requires inspection; age alone does not establish safe recovery.

`journal.jsonl` is append-only, fsynced, sequenced and hash chained. It is the
authoritative history for prepared, approved, held and locally activated states.
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
