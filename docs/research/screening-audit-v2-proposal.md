# Screening audit v2 — implementation and adoption proposal

Status: implementation proposal awaiting an independent review and explicit
coordinator adoption. The central reader, SCI, source truth and publication state
are unchanged. No actual SUT run, validation receipt or admission accompanies it.

## Policy choice for review

This version evaluates the adopted production source-screening workflow on the
entire exposed, enriched historical 269-candidate frame. It is a post-remediation
benchmark on a bounded known workload, not an untouched holdout, a test of unseen
entity generalization, or a discovery-wide recall estimate. The original written
screening contract remains 200 distinct independently eligible logical units,
190 recovered, and all four major strata at least 90%. All other research and
publication gates remain independent.

This version retains the historical seed and first-eligible canonical selection
within the historical 50 supplier / 65 paper / 60 dataset / 25 benchmark quotas.
These are historical design commitments, not newly claimed user floors. No quota
transfer or new seed is available. Insufficient eligible canonical units produces
an incomplete result. A different design requires a new reviewed method version,
not a caller override or result-conditioned repair.

## Required execution order

1. Independently review and adopt the exact scientific scope, production endpoint,
   method/code capsule, input projections, source-capture/extraction recipes,
   source packet, complete frame, exposure disclosure and failure rules. Freeze
   all exact bytes and preserve the original 269 and original 200-key artifacts.
2. A genuinely new SUT invocation sees only the frozen source input projection.
   It must not see old/new keys, graph approval/deep-review labels, prior rationales
   or performance targets. Its author’s historical exposure remains disclosed.
   Seal actual source-scoped dispositions for every one of the 269 candidates.
3. After the prediction seal, two distinct new truth invocations receive source-
   only projections, without predictions, prior labels, approval state or each
   other's notes. They freeze source-only observations before decisions. Preserve
   original independent keys, discrepancies and Unknowns in the bound truth
   artifacts. A separate tie invocation first reads source-only materials before
   any earlier rationale. Final review receipts bind exact resolved canonical
   truth without overwriting the independent initial decisions.
4. Freeze full canonical truth and all mappings. `select_screening_panel` chooses
   first eligible canonical units by the historical original-ID SHA-256 rank.
   Its signature has no prediction argument. Freeze membership before comparison.
5. A distinct prediction-source-check invocation then examines the sealed SUT’s
   actual source proof, scope and identity. It cannot amend the sealed blind key.
   Bind its checks to each exact prediction digest, retaining failures and
   unresolved critical-attribution findings. This is separate from scientific
   assertion approval.
6. Open and score once. Preserve all predictions, truth, aliases, nonunits,
   Unknowns, failed retrievals, prior keys and prior results. Report the new
   first-eligible panel, the complete 269 ledger, and the original fixed 200 with
   both its exact old three-valued key and the separate current canonical mapping.
7. An independent actual execution validator authenticates original artifacts and
   all source response bytes; it preserves every hold. A different independent
   reviewer inspects those private inputs, actual execution provenance, source
   reading scope, blinded projections and exact validator capsule before admitting
   exact public receipt bytes. Completion authorization is explicit and separate.

## Operational endpoint

A SUT prediction contains a stable original `record_id`, state (`eligible`,
`unknown`, `not_logical_unit`, `excluded`), exact resolved `logical_id`, retained
related/parent identities, mandatory-workload retention, route A/B/C/D, source
pins/locators/reading-scope commitment and an actual invocation identity.

A recovered selected eligible unit requires an `eligible` decision, retained
mandatory workload, correct canonical identity, nonempty source-scoped proof and
an independently admitted check that the exact predicted proof supports that
decision. Unknown, mere identifier presence, scheduled retrieval, old inclusion,
wrong family, or an unsupported bare boolean cannot count. The source check
reviews the operational decision; it does not create a graph approval.

The complete ledger exposes false-inclusion behavior as well. Screening’s
contractual recovery floor alone is not a precision floor. An all-eligible raw
retention baseline cannot establish source-screening performance without actual
source-proof validation. No prevalence or population inference follows from this
enriched frame.

## Public and private interfaces

The new standard-library module provides:

```python
select_screening_panel(frame, truths, *, seed=HISTORICAL_SEED,
                       quotas=HISTORICAL_QUOTAS) -> ordered_record_ids
recompute_screening(audit, *, thresholds=None) -> metrics
original200_sensitivity(audit) -> diagnostics
validate_private_screening_execution(
    audit_bytes, graph, *, expected_artifact_hashes, artifact_payloads,
    source_payloads, invocation_id, reviewer, fixture,
) -> exact_validation_receipt_bytes
validate_public_screening_audit(
    audit_bytes, graph, validation_receipt_bytes, *, trusted_admission,
    thresholds=None,
) -> (errors, metrics)
```

The private validator authenticates the hard-pinned original frame artifact and
original 200-key artifact. It compares the public frame's original IDs/strata
with that exact original frame. It directly checks the privacy-safe projection
of original key `records` using only the original `id`, `record_id`, `stratum`
and three-valued `screening_eligibility` strings. It never invents a canonical
logical-ID field in the old key. Current canonical mapping is separate and must
match the complete new blind truth. Full source response bytes authenticate all
published response digests. These byte checks are not scientific source reads.

`expected_artifact_hashes` is an independently retained caller trust input; it
must never be obtained from the submitted audit. Source payloads and complete
private artifacts remain private. No function creates an accepted admission.
The separate reviewer’s actual review, not an arbitrary invocation string or
self-pin, establishes whether execution really happened.

The public reader needs only exact public audit bytes, current merged graph,
privacy-safe receipt, independently reviewed trusted admission, and checked-in
reader/schema/dispatch files. It recomputes membership, all recovery/stratum
metrics and original-200 sensitivity. It binds the exact entire graph and release
in this first implementation; even unrelated graph additions invalidate this
version's current binding. A future sampled-binding policy requires its own
explicit review. It does not search private caches or use network credentials.

The public document is an explicit field allowlist. It contains opaque record
identities, decisions, mapping metadata, source versions/URLs, exact hashes,
scoped locators and run metadata. It has no free-form scientific-hypothesis,
candidate-wording, excerpt, private path or raw-source field. Known path,
credential, credential-query and contact-address channels are rejected. This
allowlist is a defined privacy boundary, not general-purpose DLP. Any locator
wording remains subject to actual privacy review.

`numerical_thresholds_met`, `integrity_valid`, `execution_admitted`,
`completion_authorized` and `publication_eligible` have distinct meanings.
Numeric attainment cannot remove private-validation errors, unresolved critical
attribution, absent execution admission or an unapproved method/completion.
`recompute_screening` alone always returns `publication_eligible=False`.

## Proposed authoritative gate integration

`scripts/research_audit_dispatch.py::validate_audit` is present but unused by
the central gate. It preserves the legacy reader only for unversioned legacy
documents; new and unknown schema versions cannot fall back to it. It calls the
new public screening reader for `screening-audit-v2`. Its reference-v2 branch
requires the separately reviewed public reader from the existing `8c0dfce`
proposal, or an explicitly injected reader. That proposal is not copied,
installed or adopted by importing the dispatcher.

After independent review and coordinator adoption, the coordinator must:

* Preserve the existing `_audit` implementation as the legacy reader. Replace
  only its central call site with exact-byte version dispatch. Load receipt and
  admission from a committed reviewed registry; never derive trusted admission
  from submitted audit/receipt fields. Missing or unaccepted records stay held.
* Ensure `build_context`, public readiness pages, archive source-context inputs
  and `Release.verify()` all use that same authoritative dispatch. Serialize
  exact public audit/receipt/admission inputs into edition context; avoid a local
  path-only result that cannot be reproduced in an ordinary offline clone.
* Require returned `publication_eligible` as well as absence of errors for each
  versioned audit. Keep unchanged coverage, core, cutoff, synthesis, archive and
  numerical-floor checks. Do not clear those reasons from a cached gate object.
* Replace sample-separation-by-row-ID alone with separate unit/frame/execution
  commitments. Reference units are assertions and screening units are logical
  records; sharing an entity or public source need not make the two unit samples
  identical. Reusing one panel or execution under two row prefixes is invalid.
* Bind the method-adoption record to this exact implementation capsule and policy
  before any actual SUT run. Actual completion admission comes later and must
  name the already adopted method and exact real validation receipt bytes.

No gate, package manifest or public-site integration is made by this proposal.
Unknown reference schema versions fail closed until their actual reader exists.

## Reference method remains separate

The required fresh source-anchored assertion holdout excludes all old 250/226
case hypotheses and equivalents, plus all 62 citation-repair-touched findings
and scientific equivalents. It does **not** exclude every assertion about the
same entity. Pin an exposure projection keyed to scientific content, not only
IDs or URLs. Select genuine current released/candidate assertions and seal the
actual evaluated endpoint and predictions before new independent source truth.
Do not create false hypotheses, approvals or negative reviews to fill a quota.

The existing public-reference receipt proposal can supply the private/public
trust boundary. Its original graph-review bindings preserve any recorded verdict;
they must not be read as a requirement to approve a negative hypothesis. A
prospective format must honestly handle candidates without preexisting scientific
reviews and keep audit-truth receipts distinct. Any necessary prospective schema
revision still needs an independent review before use.

Use source-support acceptance of the exact scoped hypothesis as the endpoint
only if that is the adopted operational verifier. Existing graph acceptance is a
different endpoint. An approved-only frame cannot identify recall of true but
unaccepted findings; an all-accept verifier can score recall 1 while testing no
rejection behavior. TP/FP/FN/TN, abstentions, natural prevalence and uncertainties
must be reported for the actual panel. The unchanged floors remain at least 200
assertions, 98% precision, 95% recall and zero critical false attribution. No
screening output, identifier diagnostic or constructed challenge substitutes for
that holdout.

## Verification evidence

Focused controls use only invented in-memory fixture data. They do not write
actual audit, receipt or admission files. Run:

```sh
python3 -m unittest discover -s tests -p 'test_screening_audit_v2.py'
```

The controls cover source-proof and identity failure, all-Unknown and all-eligible
baselines, strata independent of total recovery, canonical duplicates, immutable
selection, complete269 retention, preserved original200 Unknowns, actual run/source
chronology, independent invocations, fixtures, projections, critical-attribution
holds, completion authorization, non-lowerable floors, strict JSON/privacy, and
version dispatch without a legacy fallback. Their fixture success is harness
behavior, not research performance or publication readiness.
