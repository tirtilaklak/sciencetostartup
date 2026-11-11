# Non-registry paper identity proposal (unadopted)

This backwards-compatible runtime/schema extension is preparation for a future
edition. It changes no graph, report, methods manifest, frozen archive, approved
partition, publication status or launch floor. A successful identity check grants
no source read, independent review, assertion approval, core eligibility or coverage
credit. Ordinary builds remain offline. Existing records and exports without the
optional field retain their previous fields and bytes.

Before adoption, independently verify this contract, pin the selected implementation
and schema, and issue a **new methods version** explaining the expanded work-identity
admission semantics. Do not reuse an existing method/version/reproducer identity for
changed semantics. Frozen editions keep their own exact validators and bytes.
The global presentation source identity hashes scripts and schemas: do not cherry-pick
this proposal into frozen `prelaunch.1`. Adoption needs a new matching graph/report/
archive/build, recipes, schema, source identity and verification result. A normal
existing-release rebuild is not evidence that this new contract was adopted safely.

## Two authority profiles

`paper`/`paper_work` may carry optional `bibliographic_identity`. Supplying `ceur` or
`bibliographic` in `identifiers` requires that object. Merely supplying a public URL,
a title, a journal string or a response hash is insufficient. All fields in the
object are explicit; unused creator-host fields are null under the CEUR profile.
The JSON schema expresses structure; runtime checks references and identity rules.

* `ceur`: `identifiers.ceur` and identity `key` normalize to `vol-N/article`, with a
  positive integer volume and a simple publication basename. An official CEUR PDF
  URL may normalize to the same work key. Each provenance source must be a captured
  paper at the exact publisher volume/article PDF under `ceur-ws.org` or
  `www.ceur-ws.org`. Title, ordered creators, venue and year are recorded from
  primary bibliography. Status `publisher_item` identifies the publisher item; it
  does not claim peer-review depth, final text status or original data licensing.
* `creator_hosted_journal`: `identifiers.bibliographic` and identity `key` must
  equal `bibliographic_key(title, creators)`. The identity remains
  `provisional_creator_copy`. It requires the cited venue, year, volume, issue,
  named hosting creator, institution, authority basis, conflict/limitation
  qualifications, and an explicit captured creator/institution source and locator.
  That source's concise excerpt must name a paper creator. The captured primary
  paper must share its hostname and non-root creator directory. A metadata-only
  record cannot provide creator authority or primary identity evidence. The
  relationship is auditable provenance, not a registry-issued article identifier.

Validators cannot determine whether a claimed institutional relationship or
bibliographic interpretation is true. Actual source-first independent identity
review must establish those facts before adoption. A same-directory URL alone is
insufficient editorial proof. This contract does not authenticate web domains or
perform network calls during validation.

## Local identity, collisions and exact manifestations

The local bibliographic fingerprint is SHA-256 over compact UTF-8 JSON
`[normalized_title, [normalized_creator_1, ...]]`, prefixed `sha256:`. Normalization
applies Unicode NFKC and casefold, then retains only Unicode alphanumeric characters.
Creator order is retained. Venue, year, response bytes and URL are deliberately
excluded: contradictory citations and mirrors must not automatically create works.
This is an internal collision guard, **not an authoritative global identifier or
complete deduplication algorithm**. Initials, transliteration, author order and
revised titles can split the same work; distinct works can share a fingerprint.
Ambiguous collisions must be rejected and manually resolved; do not mint another
work or change spelling to evade the collision check.

Explicit `identifier_aliases` use only known schemes DOI, arXiv, ACL, PMLR, CEUR or
bibliographic. Their normalized keys share the work-identifier collision index,
including existing registry works and aliases introduced later in the entity list.
Equivalent identifiers belong on one work. Free-text entity `aliases` remain display
names, not proof of identifier equivalence. Omitted/unrecognized equivalence cannot
be inferred automatically; spelling/initials/transliteration cases require review
and explicit alias linkage. A declared alias is a factual identity claim requiring
source evidence, not a way to reserve unrelated identifiers.

Each `provenance` row names an existing captured primary paper source, exact
`response_sha256`, exact `source_version`, bibliographic `locator`, and one existing
`paper_version` entity whose parent is this work. The version's identifiers must
repeat the exact response hash and source version. Every child manifestation needs
one such binding. A source record ID is not a document identity: several concise
source records can describe one response. Different source IDs, mirrored URLs,
changed version labels and matching response bytes cannot create extra versions.
A primary document already used as another paper work's subject-owned evidence
cannot become a new work through this contract. No version is itself a countable
work. A genuinely changed response still needs its own source/version proof and
review; different bytes alone establish neither a new work nor a new scientific
result. Registry-only records retain existing behavior.

## Source-first preparation examples

The private producer packet is pinned separately at
`site/output/research-next/mandatory-paper-cohort3-author/HANDOFF.json`; its original
candidate graph rejects exactly three works under the old runtime while passing
its structural schema. The proposal creates a separate private graph and identity
records; it never rewrites the producer packet or substantive assertions/receipts.

* [CEUR Vol-2932](https://ceur-ws.org/Vol-2932/) lists *VLDB 2021 Crowd Science
  Challenge on Aggregating Crowdsourced Audio Transcriptions*, Ustalov, Pavlichenko,
  Stelmakh and Kuznetsov, and links `invited1.pdf`. The captured title page confirms
  the ordered creators and publisher volume/article margin. Work key
  `vol-2932/invited1`; capture SHA-256
  `fb49f2021942a49d40c699446313ba08397ba84dc721c311b498c032d905bdbc`.
* [CEUR Vol-3357](https://ceur-ws.org/Vol-3357/) lists *WSDM Cup 2023 Challenge on
  Visual Question Answering*, Ustalov, Pavlichenko, Likhobaba and Smirnova, and links
  `invited1.pdf`. The captured title page confirms these creators and the margin.
  Work key `vol-3357/invited1`; capture SHA-256
  `f72ce0cdc18b596cf8ec5f06f554ca0342e4a066004f6c73123a996afc69d555`.
* [Hovy/Lavid CMU creator copy](https://www.cs.cmu.edu/~hovy/papers/10KNS-annotation-Hovy-Lavid.pdf)
  has title *Towards a ‘Science’ of Corpus Annotation: A New Methodological Challenge
  for Corpus Linguistics*, Eduard Hovy and Julia Lavid. Physical page 1 says
  *International Journal of Translation* 22(1), Jan-Jun 2010. Conflicting creator
  bibliography records say *Translation Studies* and a Lavid project bibliography
  reports Jan-Dec and pages 13-36. These conflicts remain unresolved; no publisher
  article ID, final version of record, page range or globally unique journal ID is
  asserted. The [CMU creator bibliography](https://www.cs.cmu.edu/~hovy/publications.html) names
  Eduard Hovy and directly links the exact paper; a separately captured bio names
  Carnegie Mellon University. The provisional title/creator key is
  independent of the conflicting journal metadata. PDF SHA-256
  `0ce0c6a23e1ce3a167ecbed07c9d64fb96464dfa06ea56a4d04790f1fdbe531d`.

These checks inspect bibliographic front matter and authority provenance only.
They are not new reviews of the papers' methods, results, limitations or rights.
The original substantive claims retain their separately reviewed bindings and
review-packet lineage. This identity proposal supplies no new scholarly reviews;
it still needs independent identity-contract review, coordinator import and a new
edition before adoption. No DOI/arXiv identifiers are invented.

Focused failure probes cover missing identity/provenance, arbitrary mirror URLs,
wrong source digest/version/parent, metadata-only evidence, duplicate works and
mirrored/relabelled manifestations, missing child bindings, cross-scheme alias
collisions in either ordering, creator provenance gaps, and legacy export fields.
