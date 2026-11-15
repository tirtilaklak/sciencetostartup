# Independent audit-method and gate review — 11 November 2026

Reviewer task: `/root/audit_method_and_gate_review`. Scope: method, feasibility,
execution interfaces and publication-gate semantics. This is a review proposal,
not adopted policy, scientific source adjudication, an executed SUT, a completed
audit, an accepted validation receipt, or a publication authorization. Requested
model/reasoning is not provider-attested by this document.

No per-case source-gold key, prior case outcome or new scientific verdict was read
for this review. Aggregate historical states supplied by the coordinator are
context, not independently re-adjudicated findings. No SCI, `dist/`, credential,
external account or publication state is changed.

## Decision and contract boundary

**REVISE the proposed method before adopting or running it.** The source-screening
endpoint and prospective sealing requirements in protocol v2 are sound starting
points. Its demand for a completely exposure-disjoint screening frame is a
stronger design choice than the written user contract. It is not a demonstrated
prerequisite for the contract's separate screening audit. It becomes necessary
if the public claim is an untouched screening holdout or unseen-entity
generalization. Do not silently represent the old frame as such a holdout.

The written contract distinguishes these two requirements:

* A **source-anchored 200-assertion quality holdout**, at least 98% precision and
  95% recall, with no critical false attribution.
* A **separate 200-record screening audit**, recovering at least 190 eligible
  records with at least 90% recovery in every major stratum.

The contract supplies no 50-supplier quota, 20-per-stratum minimum, requirement
to discover new suppliers, or exposure-disjointness condition for screening.
It also does not authorize replacing a source-screening decision with identifier
matching. The coverage floors, original mandatory workload, family identities,
core-disposition floor and source/cutoff rules remain separate requirements.

The current implementation's `_audit` docstring and errors call both samples
holdouts. That is a method commitment in the implementation, and cannot simply
be ignored. The coordinator must explicitly choose a reviewed, versioned
screening-audit policy, bind its exact implementation into the public gate, and
state the restricted claim. This review is evidence for that decision; it does
not itself resolve ambiguity in any earlier user statement not present here.

## Can a fixed-frame rerun count as the screening audit?

**Conditionally, as a completed post-remediation benchmark on a bounded known
workload.** It cannot establish untouched holdout performance, discovery-wide
recall, supplier-universe coverage, or generalization to new entities. New blind
truth reduces independent-label contamination; it does not erase the SUT
author's historical exposure or tuning to these cases.

The defensible estimand is: among the independently established eligible
logical units selected by the declared rule from the immutable known candidate
frame, what fraction did this exact adopted operational workflow correctly retain
as eligible mandatory research workload, using source-supported identity and
admission-route decisions, before the new truth was disclosed?

This is useful operational evidence. The production workflow really must process
the backlog; its failures remain material after remediation. It is weaker
generalization evidence than an untouched evaluation, and can be easier because
roster membership and familiar scientific objects are already known. The public
description must expose that distinction where metrics appear.

Necessary safeguards:

1. Adopt the real production source-screening workflow and the restricted audit
   claim before running it. Freeze its policy, exact instructions, tools/source
   projection, method/code hashes, complete frame, ordering, source versions,
   failure rules and actual exposure history. A proposal-branch run supports
   only a candidate-workflow evaluation until operational adoption is established.
2. Use the entire fixed 269-candidate frame for SUT output, not only cases already
   known to be eligible. Preserve exact old frame and selected-200 bytes. The old
   187-eligible/13-Unknown key and identifier diagnostic retain their original
   labels, dates, counts and meaning.
3. Seal one actual, complete source-screening disposition ledger before any new
   truth-reader receives its packet. Missing output, failed retrieval, Unknown,
   wrong family, wrong entity and discarded leads remain recorded failures or
   unresolved workload. Read-only source-only input projections remove prior
   keys, graph approvals, old rationales and scoring targets. Explicitly disclose
   the SUT author's prior exposure; do not assert an unexposed author.
4. Use two new independent source readers with source-only packets, separate
   invocations and no predictions, old labels, graph approval/deep-review state,
   old rationales or one another's notes. Freeze source observations before
   decisions. Resolve disagreements before outcome comparison; preserve every
   version and Unknown. A coordinator who knows outcomes cannot serve as a
   newly blinded truth invocation merely by not opening a file again.
5. Establish canonical logical identity under the unchanged scientific scope.
   A paper version, dataset subset, generic container and roster alias cannot
   become extra units. A nonunit is not a false scientific hypothesis and an
   Unknown is not ineligible. Retain all manifestations and their unresolved
   questions in the complete ledger.
6. Select exactly 200 distinct independently eligible logical units by the frozen
   source/identity rule, without reading predictions. Freeze membership before
   comparison. No sample search, seed search, quota transfer, retrospective
   replacement, omission of failed SUT runs or result-conditioned amendment is
   allowed. If there are fewer than 200 eligible logical units, remain incomplete.
7. Independently check that each claimed recovery has the actual scoped source
   proof and identity required by the operational endpoint. Identifier presence,
   a scheduled URL, old graph inclusion or a bare `eligible=true` is insufficient.
   Preserve a separate source-support check of the predicted evidence; do not
   change the already sealed blind truth to agree with a prediction.
8. Recompute 190/200 and all four >=90% stratum rates over that exact selected
   panel. Show the full-frame disposition distribution and Unknown/nonunit ledger
   beside them. Require actual independent execution/provenance review and
   explicit completion admission before the authoritative gate can accept it.

The old 200 alone cannot become a 200-eligible audit if two cases are finally
confirmed nonunits: its ceiling is 198 eligible logical units before any other
identity collapse. A new version selected from all 269 is a new panel; it is not
a repaired spelling of the original sample. Its membership and limitations need
their own version and freeze.

## Ordering and quotas

The historical reservoir freeze already declares a deterministic SHA-256 seed,
within-stratum rank and 50/65/60/25 quotas. Those quotas are not user floors, but
they are actual prior method commitments. Reusing them, if feasible after honest
canonicalization, provides the cleanest continuity and avoids an unnecessary
post-exposure design change. This does not require new suppliers: the fixed
frame includes the existing supplier leads.

If those quotas cannot supply 200 distinct eligible units, that design is
incomplete. Do not quietly lower the deficient quota. A new source-canonical
first-200 rule can still be considered for the **exposed benchmark**, but:

* Declare the rule and justification before new SUT output or new truth; record
  the fact that earlier eligibility information was already known.
* Derive order from immutable historical frame membership and an existing seed
  or an independently fixed public rule. Do not choose among seeds/orders after
  seeing their eligible or recovery consequences. A renamed ID cannot change
  rank; canonical aliases map to the first original ranked manifestation.
* Include all four strata, with counts and resulting uncertainty visible. The
  contract does not set numerical stratum quotas. A small stratum makes its rate
  coarse and provides weak evidence. That limitation must be stated rather than
  hidden by adding an arbitrary new launch floor.
* Report the historical-quota selection result/sensitivity as well. A claim that
  changing quotas was unrelated to a known shortfall needs evidence, not a new
  label saying “prospective.”

Neither this review nor the contract establishes that the fixed 269 will actually
yield 200 eligible logical units after new source adjudication. This is a
feasibility condition to measure, not a promise of success. Failure is a legitimate
result. New directory expansion remains an optional untouched-evaluation design,
not a prerequisite invented to make launch indefinitely unreachable.

## The actual SUT and its performance bounds

The SUT is the production source-screening workflow writing the next intake
disposition ledger. It reads public source content and produces `eligible`,
`unknown`, `not_logical_unit` or `excluded`, the exact logical identity, source
versions and scoped A/B/C/D route proof. It also records whether mandatory
research workload is retained. It does not award deep-review completion,
commercial supplier qualification or scientific assertion approval.

A recovered eligible unit requires an `eligible` source-supported decision,
retention in mandatory workload, the correct canonical identity, and actual
evidence binding. Unknown is operationally retained but is not a recovered
eligible decision under this endpoint. The distinction prevents an all-Unknown
workflow from scoring 100% simply because it did not delete anything.

The screening audit is conditional recall on selected known positives. It does
not by itself measure screening precision or discovery recall. An all-eligible
baseline can attain perfect *raw retention* while producing unjustified outputs.
The complete frame, source-proof checks and false-inclusion diagnostics expose
that weakness. Do not claim the original 190/200 gate establishes a precision
floor it never specified; unsupported decisions also fail the declared actual
source-screening endpoint. Negative-control results are harness evidence, not
new scientific gold or actual performance measurements.

## Fresh reference holdout

The reference requirement is explicitly a holdout. The historical constructed
250 challenge, current 226-key reference material, repaired citations and exposed
case hypotheses cannot become fresh by issuing new review IDs or changing their
status. Keep their diagnostic value and original outcomes, but do not count
them toward an untouched reference holdout.

Freeze a real current released/candidate **assertion** sampling frame and an
exposure registry before sampling. Exclude prior evaluation hypotheses and
equivalent scientific content, not just old assertion IDs or source URLs. Fresh
here means withheld from the evaluated SUT's development/evaluation exposure;
it need not mean that a production assertion has never been reviewed by anyone.
If 200 suitable assertions do not exist, report the shortfall. Do not invent
mutations, new assertions, fake failures, approved statuses or fabricated reviews.

Choose the endpoint before choosing the sample:

* For an evaluation of the current source-verification workflow, the SUT reads
  exact candidate hypotheses and pinned cited sources and returns source-supported
  acceptance versus nonacceptance. This is a new source-support decision. Call
  it production performance only when these exact instructions and decisions
  constitute the adopted operational verification stage.
* For an evaluation of the existing graph's approval decisions, `observed_positive`
  is the frozen actual production acceptance state, established before new blind
  truth. Approved-only sampling cannot estimate false-negative recall: with no
  evaluated negatives its recall can be 1 by construction. Include actual
  candidate/held decisions in the declared population, or state that recall is
  unidentified and the contractual audit is incomplete. Do not make `candidate`
  mean scientifically false.

The first option can be implementable without inventing approvals: evaluating an
assertion is not approving it for the graph. But a separately invented verifier
prompt is a candidate-method test until actually adopted. Reusing historic graph
PASS receipts as new predictions is not an execution of that new verifier.

Blind truth asks whether the exact scoped hypothesis is supported by its pinned
source, including subject/object identity, predicate, quantitative/date scope,
version and qualifications. A truthful negative source-support adjudication is a
valid audit review. It is never factual approval of the unsupported hypothesis.
Store that adjudication in an audit-specific registry; do not create an approved
scientific assertion solely so the old `_audit` accepts a negative case.

Cases give TP when independently supported and accepted, FP when independently
unsupported and accepted, FN when supported and not accepted, and TN when
unsupported and not accepted. A materially false accepted attribution is also
critical even if aggregate precision passes. Gold Unknown is not TN: keep the
original sampled membership and remain incomplete until it is resolved under
the predeclared source policy. SUT Unknown/nonacceptance counts as FN when gold
is positive. Publish abstention counts separately and retain truthful limitations.

Natural candidate pools may have few actual negatives. Do not manufacture them
or sample to obtain passing metrics. With zero actual gold negatives the realized
precision can still be computed for that panel, but rejection behavior and
specificity are untested; zero errors gives no population-wide guarantee.
The point floors are 98%/95%, not lower-confidence-bound floors. Report numerator,
denominator, prevalence, selection design and uncertainty; do not turn a small
or highly enriched panel into a stronger accuracy claim.

An all-reject verifier has undefined/no demonstrated precision and zero recall
when gold positives exist. An all-accept verifier has recall 1 but precision equal
to the panel's supported prevalence. These are meaningful baselines, not tricks
for gaining approval. Screening and reference must remain distinct samples of
their different units and distinct execution artifacts.

## Gate-binding findings

`scripts/research_report.py::_audit` currently:

* Demands `verdict=pass` from every graph review while also attempting to use
  those reviews as audit truth. This cannot faithfully encode a source review
  concluding that an evaluated hypothesis is unsupported.
* Requires graph assertion references for every adjudication. That need not be
  wrong for an approved **meta-assertion** accurately describing a disposition,
  but it must not require approving the evaluated false hypothesis. The present
  reference shape does not distinguish those concepts.
* Has no actual sealed SUT instructions/output provenance or prediction-before-
  new-truth requirement. Completion flags, hashes and invented invocation strings
  alone cannot establish actual blinded execution.
* Binds the entire graph hash, making unrelated additions invalidate a sample;
  sampled assertion/source/identity/review commitments are a possible explicit
  alternative, not a silent weakening. Changes to sampled scientific content
  must invalidate the binding.
* Checks sample separation through row IDs only. Distinct arbitrary row prefixes
  do not establish distinct underlying cases or prevent the same execution from
  being reused for both metrics.

Keep the legacy reader for historical files. Add explicit schema-version dispatch
for new audit formats and reject unknown versions. Do not catch a v2 validation
failure and retry the weaker legacy reader. The authoritative build and external
publication adapters must call the same dispatch, with unchanged numerical floors
and all remaining coverage/report/cutoff/archive checks.

The existing proposed `reference_audit_v2.py` / `reference_audit_receipt.py` code
at `8c0dfce` provides useful separation between immutable original evidence,
truthful negative adjudication, numeric results, private validation and separately
reviewed public admission. Its receipt cannot admit itself. It remains a proposal,
not actual adoption or an actual receipt, and its historical projection path is
not automatically the right schema for a prospective candidate-pool holdout.
In particular, required original review-record bindings cannot force every
previously unapproved candidate to acquire fictitious scientific receipts.

## Minimal interfaces and acceptance controls

Use four independent results: `integrity_valid`, `execution_admitted`,
`numerical_thresholds_met` and `completion_authorized`. A readable held receipt
may have the first true and the others false. Only a versioned policy can combine
them into `publication_eligible`; a harness itself must not mint authorization.

Suggested boundaries:

```python
freeze_method(policy_bytes, frame_bytes, source_manifest_bytes,
              instructions_bytes, implementation_capsule) -> method_commitment
seal_sut_output(method_commitment, complete_dispositions, actual_run_evidence)
    -> prediction_commitment
seal_blind_truth(method_commitment, complete_source_decisions,
                 actual_independent_receipts) -> truth_commitment
select_screening_panel(frozen_order, canonical_truth, selection_rule)
    -> exact_membership             # no predictions argument
score_screening(exact_membership, sealed_predictions, sealed_truth,
                independent_prediction_source_checks) -> diagnostics
validate_private_execution(all_exact_inputs, trusted_external_commitments)
    -> validation_receipt          # preserves holds; no admission creator
validate_public_audit(audit_bytes, public_graph, receipt_bytes,
                      trusted_reviewed_admission, thresholds)
    -> errors, metrics             # public, offline, no private-cache fallback
```

The public receipt should expose exact input/output/code hashes, full membership
or public-safe identity commitments, actual execution/truth/admission chronology,
all errors, all counts, evaluation kind and scope limitations. Scientific-review
and audit-truth roles remain separate. Privacy review must prevent rejected or
candidate wording, private source paths, raw source bodies and credentials from
escaping through an audit document; public metrics and scientific-content digests
can be published without publishing prohibited candidate text.

Meaningful rejection controls must include:

1. Constant identifiers / URL lookup / old graph membership with no source-scoped
   decisions cannot count as a SUT or recovery.
2. A complete all-Unknown output produces zero recovered eligible units. An
   all-eligible output cannot pass independent source-proof admission by a
   boolean alone. Both retain all full-frame rows.
3. Missing predictions, extra predictions, duplicate canonical families, wrong
   logical identity, incomplete source pins or a changed source version cause a
   hold or a nonrecovery according to the declared failure rule.
4. Changing predictions never changes selected membership. A score-improving
   seed/quota/frame change, removed Unknown, duplicate alias or changed gold key
   breaks its prior commitment and cannot be silently resealed.
5. Predictions after new truth reads; truth readers sharing SUT invocations;
   backdated/future seals; source captures after their asserted use; and admitted
   receipt bytes without a separate actual independent review all fail.
6. A properly source-adjudicated negative reference hypothesis is admissible
   audit evidence without becoming an approved scientific assertion. A negative
   truth review incorrectly represented as scientific PASS is rejected.
7. True FP/FN/critical-attribution cases change the recomputed metrics and holds;
   caller-provided aggregate success flags cannot mask them. Numeric success
   never clears an unrecorded critical-attribution adjudication or missing
   execution/completion admission.
8. An admitted historical diagnostic remains diagnostic/held. Fixture tests,
   constructed challenge scores, new review IDs and a changed `completed` string
   cannot turn it into either formal audit.

All controls must use explicitly synthetic fixtures and write no real admission.
The tests establish harness behavior only. They do not supply actual case truth,
scientific approvals, source-reading receipts, SUT results or gate readiness.

## Required next decision

The coordinator can adopt a rigorously disclosed fixed-frame post-remediation
screening benchmark as the contract's screening audit after independent method
review and a matching public reader. Alternatively, it can keep the stronger
untouched-screening design and fund its genuinely new frame. Do not switch
between those claims after seeing scores. The fresh reference holdout remains
required under either choice. Neither choice clears any current launch gate.

Reviewed method inputs: current `docs/research/CONTRACT.md`, `evidence.md`,
`operations.md`, `publication.md`, `scripts/research_report.py`; protocol proposal
v2 at SHA-256 `850f92783d3e33f387f30045a0998b4749cab9774e14085c2bb3347f93000514`;
its v2 handoff, frame/harness checkpoints; the historical reservoir preregistration
and its neutral rank/selection rules; and proposed public-receipt implementation
at `8c0dfce`. Historical keys and per-case outcomes were not review inputs.
