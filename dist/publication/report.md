# State of AI Data Labs and Human Feedback

Release: research-2026-11-09.prelaunch.2
Updated: 2026-11-09
Status: prelaunch

## Readiness and limitations

- The full report needs at least five evidence-backed executive findings.
- Full report chapter technical-landscape still lacks reviewed findings.
- Full report chapter datasets-and-benchmarks still lacks reviewed findings.
- Full report chapter human-expertise-and-operations still lacks reviewed findings.
- Full report chapter commercial-evidence still lacks reviewed findings.
- Full report chapter governance still lacks reviewed findings.
- Full report chapter buyer-decision-guides still lacks reviewed findings.
- Full report chapter research-outlook still lacks reviewed findings.
- The edition needs an explicit baseline or prior-edition comparison.
- Coverage legacy_dispositions: 1 / 39 required.
- Coverage qualifying_suppliers: 0 / 60 required.
- Coverage reviewed_papers: 0 / 150 required.
- Coverage dataset_families: 0 / 60 required.
- Coverage benchmark_families: 0 / 20 required.
- Coverage core_disposition_rate: 0.0 / 0.9 required.
- Eligible core denominator has not been frozen with its cutoff and date.
- Approved assertion claim.helpsteer3.preference-dataset uses a source captured after the edition cutoff.
- Approved assertion claim.instructgpt.human-rankings uses a source captured after the edition cutoff.
- Approved assertion claim.dpo.classification-objective uses a source captured after the edition cutoff.
- Approved assertion claim.datasheets.documentation uses a source captured after the edition cutoff.
- Approved assertion claim.fineweb.crawl-lineage uses a source captured after the edition cutoff.
- Approved assertion claim.swebench.task-construction uses a source captured after the edition cutoff.
- Approved assertion claim.truthfulqa.question-coverage uses a source captured after the edition cutoff.
- Approved assertion claim.mmlu.task-coverage uses a source captured after the edition cutoff.
- Approved assertion claim.helpsteer3.scale-annotation uses a source captured after the edition cutoff.
- Approved assertion claim.helpsteer3.translated-annotation uses a source captured after the edition cutoff.
- Actual reference audit has not been supplied.
- Actual screening audit has not been supplied.
- An actual public versioned archive receipt with DOI and exact artifact digest is required; a prepared package is not publication.

Coverage:

```json
{
  "abstract_reviewed_entities": 13,
  "approved_assertions": 10,
  "benchmark_families": 0,
  "candidate_assertions": 0,
  "candidate_entities": 0,
  "captured_sources": 9,
  "core_disposition_rate": 0.0,
  "core_dispositioned": 0,
  "core_eligible": 0,
  "coverage_floors_met": false,
  "dataset_families": 0,
  "historical_assertions": 39,
  "launch_floors": {
    "benchmark_families": 20,
    "core_disposition_rate": 0.9,
    "dataset_families": 60,
    "legacy_dispositions": 39,
    "qualifying_suppliers": 60,
    "reviewed_papers": 150
  },
  "legacy_dispositions": 1,
  "legacy_organizations": 39,
  "qualifying_suppliers": 0,
  "quality_audit_recorded": false,
  "reviewed_papers": 0,
  "screening_audit_recorded": false
}
```

## 1. Executive assessment

[method] The unit of research is a source-supported assertion connecting an organization, paper, dataset, benchmark, model, institution, or operational practice. The report distinguishes a supplier's publicly described capability from evidence that it delivered a particular artifact. Presence in a directory or a candidate queue does not establish a reviewed supplier relationship.

[sourced_fact] The historical canonical descriptions characterize Snorkel AI in terms of specialized datasets, evaluation systems, and executable environments, and Scale AI in terms of expert training data, evaluations, and deployed AI. These are inherited descriptions from dataset 2.5.0, not newly verified delivery findings for this report.

Evidence IDs: legacy.snorkel_ai.description, legacy.scale_ai.description

[analysis] A useful comparison therefore starts with the operational question: what work must be done, what artifact must be delivered, and what evidence would demonstrate success? Broad labels such as data company or RLHF provider are discovery aids. They are too coarse to establish substitutability, commercial quality, or a training contribution.

[research_gap] This prelaunch edition does not establish market shares, a complete supplier census, independently comparable provider performance, or a current industry ranking. Its coverage page reports calculated progress against the frozen launch requirements. Missing evidence remains unknown; it is not scored as poor performance or zero activity.

## 2. Weekly developments

[method] Each full edition separates events announced during the evidence window from older events first discovered by this research. A source publication date, event date, capture timestamp and actual review time are recorded separately. The weekly digest links to changed claims, prior values, corrections, withdrawals and unresolved objections.

[method] Ordinary sources captured after Friday 5 p.m. Pacific enter the following edition. Later verification can inspect a source version already captured before the cutoff. Critical integrity notices can hold an edition without silently adding unrelated post-cutoff findings.

[research_gap] The first complete weekly edition has not launched. There is no prior published edition against which to calculate a weekly change digest. Preparation activity and candidate discovery are not industry developments.

## 3. Market structure

[method] Qualifying suppliers need an approved capability assertion connected to an included organization. Candidate suppliers, software-only adjacency, research institutions, and historical-only organizations remain visible with their actual disposition. An organization can supply several workflow types without being counted several times.

[sourced_fact] The historical canonical descriptions span professional expertise, training data, evaluations, enterprise agents, licensed datasets, expert datasets, and environments: Mercor and Turing illustrate that breadth. These inherited descriptions provide examples of taxonomy scope, not a new verification of each current offering.

Evidence IDs: legacy.mercor.description, legacy.turing.description

[method] Use explicit capability labels for collection, annotation, preference comparison, scalar assessment, expert demonstration, critique, editing, red teaming, evaluation, and executable environments. Record domain, language, modality, annotator qualification, quality process, and delivery format separately. Do not infer language coverage from office locations or specialized expertise from a large registered network.

[analysis] For procurement, compare suppliers within the same task, domain, delivery unit, and acceptance criteria. Distinguish access to software from delivery of labeled data and distinguish a recruiting network from verified paid task execution. A capability disclosure can justify a shortlist; a representative pilot with agreed acceptance criteria is needed to assess fit.

[research_gap] The qualifying-supplier launch floor is 60, with dispositions for every one of the 39 legacy organizations. The historical directory does not by itself satisfy that supplier floor. Exclusions require a reason, and unclear cases remain unresolved rather than becoming affirmative coverage.

## 4. Technical landscape

[method] Each reviewed paper should answer an operational question, identify the data and evaluation setup, describe the contribution supported by its results, and retain assumptions and limits. Metadata retrieval and abstract extraction create screening candidates. They do not constitute a source-content review of methods, experiments, or appendices.

[method] Deduplicate preprint revisions and published versions into one work using stable identifiers and an explicit crosswalk. Preserve version-specific claims when methods or results change. Count distinct reviewed works rather than URLs, PDF copies, or arXiv revisions. Retracted or superseded findings need dated dispositions and retained correction history.

[analysis] Translate a result into a decision only after checking the task, model, data source, annotation budget, evaluator, and baseline. An improvement under one experimental setup is a reason to examine a workflow; it does not establish a universal procurement rule. Make the proposed transfer explicit and name the experiment that would test it.

[research_gap] The launch corpus requires 150 distinct reviewed paper works. This prelaunch handbook makes no aggregate finding about that corpus while the floor and independent review requirements remain unmet. Candidate paper summaries must not be presented as reviewed findings.

[analysis] Start with the target decision. Pairwise preference can express a choice between outputs; scalar rubrics can express several dimensions; demonstrations can specify desired behavior; critiques and edits can identify a localized problem and a proposed correction. These are design options, not a finding that one format always outperforms another.

[method] Write an annotation specification with the task objective, audience, examples, ambiguous cases, allowed tools, abstention criteria, and escalation path. Define whether annotators judge the response alone or consult evidence. Keep factual verification, stylistic preference, and policy compliance separate when they require different information.

[analysis] Pilot several representative tasks before fixing the format. Inspect annotation time, disagreement, error categories, and downstream usefulness under a stated budget. Pairwise labels can hide why an output was chosen; a long rubric can impose unnecessary work. The appropriate tradeoff is an empirical question for the intended task.

[research_gap] This edition provides decision guidance rather than a causal estimate of the best format or required annotation volume. Quantitative recommendations require a reviewed study with a matching setup or a disclosed local experiment.

## 5. Provider dossiers

[method] A supplier-to-artifact edge requires an explicit source naming the organization and its contribution to the specific dataset, paper, benchmark, or model. Preserve whether the contribution was collection, annotation, evaluation, software, funding, or another role. A general client logo, capability page, or plausible industry connection is insufficient.

[sourced_fact] The historical canonical description identifies AfterQuery with expert-generated datasets and environments, plus custom enterprise evaluations and deployment work. That broad description does not identify a supplier contribution to any particular paper or dataset; each such relationship needs its own reviewed evidence.

Evidence IDs: legacy.afterquery.description

[method] Qualify attribution by version, stage, and source voice. An author acknowledgment supports what it states; a supplier announcement remains a supplier statement; a buyer account can provide a distinct perspective. Do not upgrade contributor status into exclusive authorship, a paid contract, or end-to-end responsibility without evidence.

[research_gap] New attribution examples remain in the candidate graph until separate source verification and adversarial review are complete. They do not contribute to deep coverage or report findings. The quality holdout allows no critical false supplier attribution.

[method] Every included provider dossier records its legal or operating identity, parent and brand relationships, actual offer, delivery model, modalities, domains, geography and languages, quality processes, governance evidence, documented artifacts, buyer evidence, commercial observations, limitations and unanswered questions. Each field retains its own substantive review date.

## 6. Dataset and benchmark landscape

[method] Track dataset families separately from revisions, subsets, translations, mirrors, and reformats. Record original collection, upstream material, annotation method, annotator population where disclosed, human or synthetic origin, intended use, license statement, and access conditions. Preserve unknown fields instead of filling them from neighboring artifacts.

[analysis] For a reuse decision, inspect the exact artifact version and its upstream chain. A repository license statement alone may not resolve all rights in underlying material, annotations, or personal data. Record the source's wording and unresolved questions, and seek appropriate review before relying on a legal interpretation.

[method] Human-written, human-ranked, model-generated, model-ranked, and mixed-origin examples are distinct categories. Describe the stage to which the origin label applies: prompt, response, comparison, critique, or final acceptance. A human audit of a subset does not convert every generated item into human-authored data.

[research_gap] The launch floor is 60 distinct dataset families with reviewed assertions. A mirror or a new version does not increase family coverage. This report does not certify consent, ownership, licensing compatibility, or demographic representativeness for an unreviewed dataset.

[method] Benchmark records keep family, version, task, evaluator, sampling procedure, metric, test conditions, and source date. Results attach to the tested artifact and protocol. A changed benchmark, model checkpoint, prompt, judging procedure, or contamination assumption may invalidate a direct comparison.

[analysis] Choose an evaluation that reflects the intended deployment decision. Separate held-out task success, preference agreement, factual correctness, safety behavior, latency, and cost. A single aggregate score can conceal opposite behavior across important domains; inspect strata and disagreement before deciding that a result transfers.

[method] Keep training and evaluation provenance distinguishable. Record known overlap and unavailable contamination information. Use independent evaluation examples where possible, document any tuning against the test set, and retain unsuccessful or inconclusive comparisons. A public benchmark score is not a measurement of a supplier's overall service quality.

[research_gap] The launch floor is 20 benchmark families. No comparable provider leaderboard is established by this edition. The index will report the availability and scope of evidence before making any cross-provider performance claim.

## 7. Human expertise and operations

[method] Specify quality at the unit of delivery: accepted example, adjudicated comparison, verified solution, or functioning environment. Define measurable acceptance criteria before delivery, and record how errors are detected, corrected, and sampled. Keep first-pass acceptance, corrected acceptance, and final quality separate.

[analysis] Treat disagreement as a diagnostic signal. It may reflect an unclear rubric, different information, legitimate preferences, domain uncertainty, or an annotation mistake. Inspect examples before choosing majority voting, expert adjudication, a distributional label, or exclusion. Agreement alone does not demonstrate correctness when annotators share an error.

[method] Record disclosed qualification and calibration procedures without equating job titles or claimed credentials with verified performance. Where expertise matters, evaluate it on representative tasks. Separate training examples from quality-control examples and disclose sampling, adjudication, exclusions, and known blind spots.

[research_gap] No universal annotator count, quality-control percentage, or expert premium is inferred here. The reference audit measures this publication's assertion quality; it does not measure a supplier's annotation quality or certify all underlying data.

[method] Record qualifications, recruitment method, training, annotation instructions, independent judgments, disagreement treatment, adjudication and acceptance checks only where disclosed. Distinguish registered networks, available expertise, active contributors and paid delivery. Retain source-scoped compensation units, geography, eligibility and task conditions.

## 8. Commercial evidence

[method] Financial observations retain currency, unit, period, gross or net basis where known, business scope, source date, and whether a figure is reported or estimated. Revenue, annualized pace, transaction volume, funding, valuation, registered networks, and active paid work measure different things. Missing disclosure is not zero.

[analysis] For a pilot budget, compare total cost per accepted deliverable under matching acceptance criteria, including setup, adjudication, rework, tooling, and internal review. A quoted hourly rate or per-task price alone cannot establish delivery cost. Ask what is measured, what is excluded, and what happens when the work fails acceptance.

[method] Use a decision record: required task and domain, evidence-backed supplier capabilities, pilot sample, rubric, acceptance threshold, evaluation plan, costs, privacy constraints, and unresolved risks. Preserve the date of each public claim. Recheck material assumptions before a consequential commitment.

[research_gap] This report does not estimate provider margins, market size, pricing superiority, or current hiring availability from incomplete public evidence. Commercial conclusions require comparable observations and an explicit denominator.

## 9. Governance

[method] Governance observations identify the exact public document, named control, covered organization or product, relevant period, verification source and limitations. A generic security statement, legal policy, certification badge and independently inspected assessment establish different things.

[method] Compare disclosed consent, provenance, licensing, data retention, privacy, residency, subcontracting, worker protections and incident or correction procedures. A missing statement is an evidence gap in the reviewed scope. It is not proof that a provider lacks a control.

[method] Keep third-party rights and personal information separate from the license for ScienceToStartup authored research. Public archival packages include only the documented clean projection and permitted material, with transformation records and original-source attribution.

[research_gap] This research does not establish undisclosed controls or certify any provider compliance. Provider-specific assessments await scoped primary evidence and separate source reviews.

## 10. Buyer decision guides

[method] Start procurement with a concrete task, domain, required artifact, volume, delivery unit, geography and evaluation target. Build shortlists from scoped capabilities and delivery evidence. Preserve unknown requirements instead of treating missing disclosure as a negative performance measurement.

[method] A representative pilot should specify a held-out evaluation set, annotation rubric, annotator qualifications, independent judgments, adjudication rules, acceptance thresholds, security requirements and a unit of cost. Report achieved task quality, disagreement, coverage, turnaround and the limits of extrapolation.

[method] Compare expert demonstrations, pairwise preference collection, scalar ratings, critique/edit workflows, red teaming, multilingual evaluation and agent environments as different use cases. Each comparison identifies required evidence and outstanding buyer questions. No universal supplier winner is inferred from market visibility or a funding figure.

[research_gap] Named use-case shortlists remain pending until qualifying supplier assertions and evidence-supported comparisons pass separate review. Candidate suppliers are not recommendations.

## 11. Research outlook

[method] Outlook statements identify the observed research inputs, proposed mechanism, important assumptions, counterevidence, and a measurable signal that would strengthen or weaken the assessment. Expected changes are analytical judgments rather than recorded market facts.

[method] Monitor changes in feedback formats, verifiable evaluation, expert task construction, synthetic data oversight, agent environments, multilingual coverage, and reproducible reward-model evaluation. Assess each under its actual experimental conditions and documented operational requirements.

[research_gap] No forecast of market size, provider share or universal training gains is established by the prelaunch corpus. The first evidence-backed outlook follows reviewed baseline coverage and validated comparisons.

## 12. Methods and appendices

[method] Every publishable assertion needs a stable subject and predicate, a typed value or object, a specific source version, a locator, and qualifications. A URL alone does not demonstrate that its content was read. Source receipts bind captured content and a concise permitted excerpt by digest; source date, capture date, assertion date, and review date remain separate fields.

[method] The author proposes the assertion and its scope. A separate source-verifier invocation checks that the captured content supports the wording, quantity, entity, date, unit, and relationship. A separate adversarial invocation seeks false attribution, inconsistent denominators, omitted qualifications, and stronger interpretations than the source allows. The three invocation identities and actual outcomes are preserved.

[method] An inherited claim retains its original historical status. A candidate remains a candidate until the required receipts exist. AI review is labeled as AI review; model agreement is not a claim of independent human expertise. A later verification can check an older captured source version without changing that version's original capture date.

[analysis] Source independence concerns who is making the claim, not the number of URLs repeating it. A supplier announcement and a syndicated copy should not become two independent confirmations. Buyer-authored accounts can strengthen delivery evidence, while still requiring scope and date checks. A paper acknowledgment can support a narrow contribution without demonstrating a paid contract.

[research_gap] This preparation snapshot does not include completed source-anchored quality holdouts or a named external human review. The required quality holdouts remain a publication blocker. External human participation is voluntary and is not required for release. A test fixture or a generated summary of accuracy cannot substitute for actual adjudicated records and separate AI review receipts.

[method] Before launch, freeze the eligible core with its membership, date, and source cutoff. Publish dispositions for at least 90% of that frozen denominator and for all 39 legacy organizations. Additions discovered later enter the next documented core revision. Never improve coverage by deleting unresolved eligible cases or counting duplicate versions as independent works.

[method] The launch corpus also requires 60 qualifying suppliers, 150 distinct reviewed paper works, 60 dataset families, and 20 benchmark families. Counts derive from approved, source-supported graph records and actual review receipts. Candidate records, historical imports, unreviewed metadata, and repeated aliases do not count as deeply reviewed coverage.

[method] Use two separate real holdouts: a frozen source-anchored sample of at least 200 assertions requiring at least 98% precision, at least 95% recall, and no critical false attribution; and a separate 200-record eligibility screening sample requiring recovery of at least 190, with at least 90% recall in each major stratum. Preserve adjudications and compute metrics from rows.

[analysis] These are publication criteria, not evidence that the corpus represents the whole industry. Describe how the eligible frame and holdouts were assembled, which strata have sparse evidence, what the reviewers could inspect, and where access or language limitations remain. A passing sample does not remove the need for corrections.

[research_gap] Actual completed audit files are absent until the audits occur. Automated tests use isolated fixtures to check rejection behavior; those fixtures never enter publication data and never establish research accuracy. Current deficiencies keep the report in prelaunch state.

[method] Daily preparation runs at 16:00 America/Los_Angeles. Weekly publication targets Monday 09:00 in that timezone, using source versions captured by the preceding Friday at 17:00. Construct both local times from calendar dates so daylight-saving transitions are respected. Later verification may inspect an eligible captured version; a newly captured late version belongs to a later edition.

[method] A prepared candidate binds the exact graph, report, policy, public identity, cutoff, and release identity by digest. Approval binds that exact candidate. A changed input creates a new candidate. Serialized activation and an append-only journal prevent an older delayed job from replacing a newer edition; retries resume the same identity.

[method] Archive only a deliberately versioned public projection: owned report text, public evidence metadata, permitted concise excerpts, attribution, methodology, and reproducibility instructions. Exclude credentials, raw caches, private personal data, and historical privacy exceptions. Keep website deployment, archive publication, and mirror synchronization as separate receipts.

[research_gap] Zenodo and Hugging Face accounts are not connected for this release. The current policy prepares packages and records holds; it cannot claim a DOI, permanent archive, synchronized mirror, or published research edition. A reserved identifier or staged package is not an actual public archive.

[method] Cite an actual released version and its stable assertion identifiers. Submit corrections with the affected claim, source version, locator, proposed change, and reason. Accepted corrections preserve the earlier wording and provenance, record the new decision and review dates, and appear in the next edition's change history. Never silently rewrite historical source or review dates.

## Evidence and reproduction

The accompanying clean-dataset.json, CSV and SQLite contain the same versioned public projection. Canonical dataset 2.5.0 remains unchanged outside this archive. Contact details and raw source text are excluded from this projection. Review receipts describe actual review scope; a candidate is not a deeply reviewed record.

Use MANIFEST.json to verify each file's SHA-256. The archive is self-contained and makes no network requests. Source URLs and identifiers are retained in the accompanying public graph.
