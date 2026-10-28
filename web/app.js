/* Portable, dependency-free public research. No network calls or local storage. */
'use strict';
const DATA=JSON.parse(document.getElementById('research-data').textContent);
const $=id=>document.getElementById(id), index=rows=>{const map={};for(const row of rows)map[row.id]=row;return map;};
const claims=index(DATA.claims),sources=index(DATA.sources),companies=index(DATA.companies),people=index(DATA.people),investors=index(DATA.investors);
const state={query:'',category:'',stage:'',financial:false,work:false,sort:'name',workQuery:'',workGroup:'',workPay:'',workEligibility:'',selected:[],mobileCompare:0,revenuePeriod:'annual',revenueCurrency:'USD',runratesExpanded:false,lastView:'market'};
// Presentation-only wording: original research and provenance remain in DATA and exports.
const PUBLIC_COPY_EDITS={
  "C1 blocks demonstrated/repeatable/established rubric stages despite strong financial scale; O2 is also not established by the inspected detail. Low disclosure is not low business scale.": "The reviewed sources do not identify a named AI Services customer or give enough detail on how AI-data work is checked and accepted. These disclosure gaps limit the assessment despite the division’s financial scale.",
  "A useful comparison should show both the rapid expansion and the absence of audited economics.": "Rapid expansion is reported, while audited economics remain unavailable.",
  "Announcement date must not be substituted for exact close date.": "Announcement and exact closing dates are distinct.",
  "Appen is the most financially transparent of these four and should be assessed as a listed operating-business turnaround.": "Appen has comparatively detailed financial disclosure as a listed operating business undergoing a turnaround.",
  "Broad company historical-commercial evidence only; display dates and ended-client status prominently": "Broad-company historical commercial evidence; customer relationships retain their dates and ended status.",
  "Classify each as open-data use or citation, never automatically as a paid customer.": "Open-data use and citations do not by themselves establish paid customer relationships.",
  "Company retrospective; distinguish parent founding from product brand launch.": "Company retrospective; parent founding and product launch are separate milestones.",
  "Compare its disclosed service revenue with other companies on a like-for-like basis; fundraising, ARR estimates and annualized monthly run rates are poor substitutes for Appen’s actual reported sales.": "Its disclosed service revenue has a different basis from fundraising, ARR estimates and annualized monthly run rates.",
  "Completed primary financing evidenced in the audited source register and final QA.": "Completed primary financing supported by the cited sources.",
  "Credit dated investor-reported contracts, while preserving revenue recognition, retention and named-buyer gaps.": "Dated investor-reported contracts are available; revenue recognition, retention and named-buyer evidence remain unresolved.",
  "Current about-page retrospective instead says $7.8m and conflates Series B chronology; retain conflicting alternative and exclude from strict exact observed sum pending reconciliation.": "The current about-page retrospective instead says $7.8m and conflates the Series B chronology. The conflicting amount is excluded from the strict disclosed-round sum pending reconciliation.",
  "Current canonical uses Andrey; keep Andrei as a source spelling/alias rather than creating another person.": "Andrey and Andrei are source spelling variants for the same person.",
  "Current search index exposes the company biography; preserve the co-founder title with historical qualification.": "The indexed company biography describes a co-founder title; this is historical evidence.",
  "Display: $23.5m announced rounds + $12.8m later BII commitment": "$23.5m announced rounds + $12.8m later BII commitment",
  "Distinguish business origin from platform/product launch; do not flatten the three milestones into one founding date.": "Business origin and platform/product launches are three separate milestones, not a single founding date.",
  "Do not badge as freshly verified.": "This evidence has not been freshly verified.",
  "Do not imply ongoing 2026 contract or SaaS production.": "An ongoing 2026 contract or SaaS production deployment is not established.",
  "Do not imply this 2022 year was newly verified from a primary source.": "The 2022 founding year has not been newly verified from a primary source.",
  "Do not infer capitalization from the standard YC deal.": "The standard YC deal does not establish this company’s capitalization.",
  "Do not invent investor check sizes.": "Individual investor check sizes are not disclosed.",
  "Do not mark acquired/private.": "The evidence does not establish acquired/private status.",
  "Do not set whole profile financials to unknown because standalone TrainAI revenue is undisclosed; no newer official financial disclosure found in targeted search.": "Standalone TrainAI revenue is undisclosed; parent financial figures remain available. No newer official financial disclosure was found.",
  "Do not store unnecessary tax identifiers.": "",
  "Do not use Meta as a current logo without new evidence.": "Meta is not established as a current customer.",
  "Earlier FY2024 report showed $26.4M as segment revenue; keep both with basis labels.": "The earlier FY2024 report showed $26.4M as segment revenue; both observations retain their different accounting bases.",
  "Exact close date remains unresolved; do not invent it.": "Exact closing date remains unresolved.",
  "Exact latest round size, closing date and investors": "Size, closing date and investors for the reported September 2026 financing",
  "Existing raw silently labels USD; retain the text and flag currency unspecified rather than treating $50m as verified revenue.": "Currency is unspecified in the source; $50m is not a verified USD revenue figure.",
  "Founder narrative; distinguish co-founders, founding advisers, board members and project contributors.": "Founder narrative; co-founders, founding advisers, board members and project contributors have different roles.",
  "Funding databases and founder/HQ aggregators conflict; primary YC/legal identities should control.": "Funding databases and founder/HQ aggregators conflict; identities here follow primary YC and legal sources.",
  "Google is a documented historical customer, terminated in early 2024; it must not be shown as a current customer.": "Google is a documented historical customer whose relationship terminated in early 2024.",
  "Historical parent funding and valuation should remain visible without being attributed to the AI division.": "Historical parent funding and valuation are distinct from the AI division’s finances.",
  "Image counts are rounded inconsistently within the source (1m+ heading versus nearly 1m text); retain approximately, not a precise floor.": "Image counts are rounded inconsistently within the source (1m+ heading versus nearly 1m text); the observation is approximate.",
  "Individual biographies do not map each named employer to every founder; retain team-level attribution.": "Individual biographies do not map each named employer to every founder; attribution is at team level.",
  "Investor job board now explicitly says no longer accepting applications; use as historical pay evidence only.": "The investor job board explicitly says it is no longer accepting applications; the advertised pay is historical.",
  "Investor list should not be lost just because no dollar total exists.": "Named investors are disclosed even though the funding total is not.",
  "Its disclosure-based gate result is constrained by unnamed AI buyers and must not be presented as an early-stage business classification.": "Its disclosure-based gate result is constrained by unnamed AI buyers; this is not an early-stage business classification.",
  "Its historical Google relationship must not be shown as current.": "Its Google relationship is historical, not current.",
  "Keep $55M reported funding aggregate visible independently.": "The $55M reported funding aggregate is a separate observation.",
  "Keep as attributed undated claim.": "Attributed undated claim.",
  "Keep as entity/funding-status prose.": "Entity and funding-status context; no numeric financing amount established.",
  "Keep excluded from closed venture-equity sums; no funding_unknown card should hide the pledge.": "The pledge is separate from closed venture-equity financing.",
  "Keep existing $65m reported-total metric and historical $42m May-2022 revenue run rate; do not replace with funding_unknown.": "The $65m reported funding total and $42m May-2022 revenue run rate are separate historical observations.",
  "Keep existing supporting claim/source; change normalized relationship only.": "",
  "Keep its independent-verification limit.": "Independent verification remains limited.",
  "Keep outside dated charts and do not equate to August gross figure.": "Undated claim, excluded from dated charts; not equivalent to the August gross figure.",
  "Keep outside realized/latest-reported numeric ranking.": "Excluded from reported actual-value comparisons.",
  "Keep project, fiscal sponsor and the mathematical AIXI model distinct.": "The project, fiscal sponsor and mathematical AIXI model are separate entities.",
  "Keep the separate $150.5m calculated disclosed-round sum; date that sum to the last included announcement, July 8, 2026.": "The $150.5m calculated disclosed-round sum is dated to the last included announcement, July 8, 2026.",
  "Keep this closing-month observation alongside the July 12, 2023 financing announcement, rather than changing announcement date.": "The closing-month observation is separate from the July 12, 2023 financing announcement.",
  "Later company retrospective additionally names Salesforce Ventures; keep that separately rather than silently changing the contemporaneous syndicate list.": "A later company retrospective additionally names Salesforce Ventures; the contemporaneous syndicate list differs.",
  "Linked Ramp X post returned 403, so do not upgrade to buyer-confirmed A evidence.": "The linked Ramp X post returned 403; buyer-confirmed A evidence is not established.",
  "Listed event amounts sum to $434M, leaving $1.5M unexplained; show both basis and discrepancy, do not force reconciliation.": "Listed event amounts sum to $434M, leaving an unexplained $1.5M difference from the derived reported cumulative total.",
  "Markets 100,000+ active vetted AI-data specialists; distinguish this from RWS’s broader 250,000-person cultural/language/domain network.": "The marketed 100,000+ active vetted AI-data specialists are distinct from RWS’s broader 250,000-person cultural/language/domain network.",
  "Motif 3 was publicly released; the inspected Motif technical report does not mention AfterQuery, so retain this as a named supplier claim rather than buyer-confirmed paid customer.": "Motif 3 was publicly released. Its inspected technical report does not mention AfterQuery; the relationship is supplier-reported, without buyer-confirmed payment.",
  "Never substitute funding_unknown because source amounts are strings.": "Financing amounts are disclosed.",
  "Never use as iMerit revenue or training-data market revenue.": "This is not iMerit revenue or training-data market revenue.",
  "No commercial maturity score should be created.": "Commercial maturity scoring is not applicable.",
  "No separate Astra corporate valuation or funding should be created.": "Astra does not have a separately established corporate valuation or funding total.",
  "Official retrospective funding chronology conflicts with contemporary Series B reporting; retain provenance rather than quietly rewrite the history.": "Official retrospective funding chronology conflicts with contemporary Series B reporting; the discrepancy remains unresolved.",
  "Operational hiring is primarily Paris; distinguish registry address from operating HQ.": "Operational hiring is primarily in Paris; registry address and operating headquarters are distinct.",
  "Percent versus percentage-point basis is not fully specified; preserve wording and avoid generalized performance claims.": "Percent versus percentage-point basis is not fully specified; the stated performance measure has limited comparability.",
  "Preserve $55M funding and named founding team; do not call financing unknown.": "$55M in funding and the named founding team are disclosed.",
  "Preserve Andy Konwinski’s $100m personal pledge separately from institutional research outlays and any Laude Ventures funds.": "Andy Konwinski’s $100m personal pledge is separate from institutional research outlays and Laude Ventures funds.",
  "Preserve a16z Scout Fund distinction from flagship institutional investing or accelerator admission.": "a16z Scout Fund participation is distinct from flagship institutional investment or accelerator admission.",
  "Preserve the $30M company Series A versus $32M later press discrepancy.": "The company’s $30M Series A figure differs from the later $32M press report.",
  "Preserve ~$59m standalone revenue, dated transfer-scope headcount, and the separate historical-funding, BII-commitment and acquisition categories.": "Approximately $59m in standalone revenue and dated transfer-scope headcount are separate from historical funding, the BII commitment and acquisition figures.",
  "R3 remains unsupported": "Public evidence of commercial activity across multiple years remains incomplete",
  "Retain $55M issuer/counsel figure and reported $300M separately; do not promote uncorroborated $500M estimates.": "The $55M issuer/counsel figure and reported $300M figure are separate observations. The $500M estimates are uncorroborated.",
  "Retain $60m Series D and >$115m company total; additional existing backers are not all confirmed new-money participants.": "The $60m Series D is separate from the >$115m company total; additional existing backers are not all confirmed new-money participants.",
  "Retain H1 FY2026 group revenue £360.3m and Generate revenue £99.4m as actual six-month figures; Generate includes both TrainAI and Content Technology.": "H1 FY2026 group revenue of £360.3m and Generate revenue of £99.4m are actual six-month figures; Generate includes both TrainAI and Content Technology.",
  "Retain both amounts and the discrepancy; no separate extra round is established.": "The amounts differ; no separate extra round is established.",
  "Retain claim: Yes": "",
  "Revised audit follow-up: Distinguish a named commissioned engagement from generic external-testing participation; commercial scale and payment remain undisclosed.": "A named commissioned engagement is documented; commercial scale and payment remain undisclosed.",
  "Revised audit follow-up: Existing R unknown rationale says no dated contract evidence exists; that is now factually obsolete.": "Dated investor-reported contract evidence is available, while the formal gate assessment remains historical.",
  "Revised audit follow-up: Raise confidence in demonstrated technical delivery because Snowflake independently confirms joint work; do not label all research collaborators paying customers.": "Snowflake independently confirms joint technical work; research collaboration does not by itself establish a paying customer.",
  "SkillsBench’s separately described 1.0 release has 100+ tasks, so retain version labels.": "SkillsBench’s separately described 1.0 release has 100+ tasks; counts refer to different versions.",
  "The prior profile materially understated commercial scale by omitting them.": "",
  "These should be prominently visible sourced text cards.": "",
  "This is an audit warning, not a dashboard headline revenue metric.": "This amount is not an established revenue observation.",
  "Treat Labelbox as an established platform supplier with a newer expert-data and RL push, not as a company with a verified current ARR figure.": "Labelbox is an established platform supplier with a newer expert-data and RL offering; current ARR is not verified.",
  "Treat as a Japan-focused lead rather than a confirmed US opportunity.": "Japan-focused route; a US opportunity is not confirmed.",
  "Treat it as rapidly scaled but financially opaque; missing named buyers, concentration and revenue-recognition details limit valuation comparisons.": "Reported scale has grown rapidly, while missing named buyers, concentration and revenue-recognition details limit valuation comparisons.",
  "Treat that scope as unresolved; SOC 2 report existence was visible but report scope/date not inspected.": "SOC 2 report existence was visible, but its scope and date were not inspected.",
  "Use HackerRank / Astra (HackerRank Bench) as aliases; this is not a separately funded entity.": "HackerRank / Astra (HackerRank Bench) are aliases, not separately funded entities.",
  "Use actual CEO statements; article has a chronology typo saying Series A followed Series B.": "The article’s chronology incorrectly places Series A after Series B; the quoted CEO statements provide separate evidence.",
  "Use company aggregate, retain discrepancy": "Company-reported aggregate; discrepancy remains unresolved.",
  "Use date-stamped ASX equity market capitalization if needed; no live price/market cap was independently checked in this pass.": "No current ASX share price or equity market capitalization was independently checked.",
  "Use dated transfer-scope figure for the main FTE card.": "Headcount refers to the dated transfer scope.",
  "Details-only disclosure minimum; never primary market-overview classification": "This disclosure minimum does not describe the company’s business scale.",
  "Gate assessment retained from the original reviewed snapshot; the revised narrative and new metrics do not automatically upgrade it.": "The assessment reflects the earlier dated evidence; newer financial observations do not establish every delivery criterion.",
  "Some supporting source checks were inherited rather than refreshed in the final audit; this remains a historical scoped assessment.": "Some supporting sources have not been rechecked; this remains a historical scoped assessment.",
  "financing talks and wealth-based valuations must not appear as closed funding": "financing talks and wealth-based valuations are not closed funding",
  "founding year: 2,023": "founding year: 2023",
  "closed_company_announced_round": "Company-announced financing round",
  "reported_cumulative_funding": "Reported cumulative funding",
  "funding_unknown": "funding not established"
};
Object.assign(PUBLIC_COPY_EDITS,{
  "$2.5M company-reported; retain $2.3M initial announcement as historical, do not sum": "$2.5M company-reported total; the historical $2.3M announcement is included, not additive.",
  "The products page still says 70+ languages; retain the different page snapshots rather than implying an audited growth series.": "The products page still says 70+ languages; different page snapshots do not establish an audited growth series.",
  "Current canonical third_party/C is wrong: this is a primary supplier case.": "Primary supplier case study; independent buyer confirmation was not reviewed.",
  "Canonical company_named is wrong when no lab is named.": "The claimed lab customers are unnamed.",
  "Existing prose says research collaboration, not four paying customers; normalization currently marks claimed_customer.": "Research collaboration is described; four paying customer relationships are not established.",
  "Later homepage metrics appear larger, but the forecast must not be mistaken for actual payout at that date.": "Later homepage metrics appear larger; the earlier forecast is not actual payout at that date.",
  "Private revenue databases mix year-end run-rate, revenue estimates, forecasts and bookings; none should be substituted for audited financials.": "Private revenue databases mix year-end run-rate, revenue estimates, forecasts and bookings; these are not audited financials.",
  "Subsequent revenue is not publicly comparable after deconsolidation, so neither a 2025 stub nor a financing amount should be used to imply today’s commercial scale.": "Subsequent revenue is not publicly comparable after deconsolidation; the 2025 stub and financing amounts do not establish current commercial scale.",
  "Supplier case describes image-labeling work and includes attributed buyer testimony; scope should remain the described pilot/project rather than assumed enterprise-wide deployment.": "Supplier case describes image-labeling work and includes attributed buyer testimony for a pilot/project; enterprise-wide deployment is not established.",
  "Work is project-matched and can end early; accepted-task approval matters to payment and no hours should be annualized into a salary.": "Work is project-matched and can end early; payment depends on accepted tasks, with no guaranteed annual salary.",
  "Toronto organization’s grants/metrics also do not belong here": "Grants and metrics for the separate Toronto organization are excluded.",
  "no O3 credit from marketing claims alone": "marketing claims alone do not establish the highest operating-controls criterion",
  "not fully re-audited": "not fully rechecked"
});
Object.assign(PUBLIC_COPY_EDITS,{
  "Compute/services run-rate should not be compared directly with net SaaS ARR or contractor-marketplace revenue.": "Compute and services run-rate figures have a different basis from net yearly recurring subscription revenue or contractor-marketplace revenue.",
  "aggregate growth should not conceal US/global weakness or project concentration.": "US/global weakness and project concentration remain relevant to group growth.",
  "DataAnnotation should not be counted as a separately funded competitor.": "DataAnnotation is Surge’s operating platform; separate financing is not established.",
  "Leave unknown financing while retaining commercial revenue/contract claims.": "Financing is undisclosed; commercial revenue and contract claims are disclosed separately.",
  "Funding event must read philanthropic pledge.": "This financing record describes a philanthropic pledge.",
  "do not blanket-erase funding because revenue is unknown.": "funding disclosures remain available while revenue is undisclosed.",
  "do not claim this is an independently reconstructed all-equity total or add it to the latest round.": "an independently reconstructed all-equity total is unavailable. The latest round is included in this reported total.",
  "Derived from rounded latest discontinued-operations comparatives; do not mix with original 138% segment headline.": "Derived from rounded latest discontinued-operations comparatives; the original 138% segment headline has a different accounting basis.",
  "Weak evidence for scope and recency; do not classify all logos as frontier-model customers or verified current contracts.": "Displayed logos provide limited evidence about scope and recency. They do not establish current frontier-model customers or verified contracts.",
  "do not mechanically subtract notices from old headcount.": "an updated payroll total cannot be derived by subtracting the redundancy notice from older headcount.",
  "Website claim of all top labs and older YC numerical claim should not be collapsed into a verified customer list.": "The website’s unnamed top-lab claim and older YC count do not establish a verified customer list.",
  "Do not interpret data-licensing payouts as individual hourly earnings.": "Data-licensing payouts describe company data sales; individual hourly earnings are not established.",
  "The old /solutions page returns 404; do not link it.": "The older /solutions page returned HTTP 404 (the page was not found) at the recorded check.",
  "Funding disclosure lists differ between homepage and careers; preserve source attribution.": "The homepage and careers page give different funding lists.",
  "Company-reported annualized figure; do not relabel audited revenue or ARR.": "Company-reported annualized figure; audited annual revenue and yearly recurring subscription revenue remain unverified.",
  "Current positioning has changed; do not show Quesma primarily as an RL-environment supplier.": "Quesma’s current main offer analyzes coding-agent activity.",
  "Founding engineers must not automatically be relabeled co-founders.": "Founding-engineer roles alone do not establish co-founder status.",
  "do not silently merge versions.": "these figures refer to different versions.",
  "Do not show prior OpenAI/Google customer relationships as current without fresh evidence.": "Current OpenAI and Google customer relationships are unverified.",
  "Keep Handshake AI and parent Handshake scopes separate.": "Handshake AI figures describe the AI business; Handshake figures may describe the parent company.",
  "Do not repeat the Reuters annual-revenue wording; the primary company release explicitly says annual revenue runrate.": "The primary company release calls this an annual revenue run rate; Reuters described it as annual revenue.",
  "Keep version 2 separate from the 912-task original benchmark.": "The original benchmark is a separate, 912-task version.",
  "No exact amount is established; do not synthesize a numeric revenue or profitability metric.": "No numeric revenue or profitability figure is established.",
  "Named accountable founders, screening/verification and payout process. Inconsistent headcount does not erase team identity, but current operational controls lack independent scope.": "Named founders are identified. The company describes screening and verification, alongside its payout process. Headcount reports conflict. Independent evidence about current operational controls is limited."
});
// Risk statements shown under Risks and disputes, written as public sentences rather than reviewer instructions.
Object.assign(PUBLIC_COPY_EDITS,{
  "Latest financing reported without company confirmation; unnamed lab participants should not be fabricated.": "Latest financing was reported without company confirmation, and the participating labs are not named.",
  "Do not label its full 11,000-builder network as AI-data contributors or interpret unnamed RL delivery cases as named customer validation.": "Its full 11,000-builder network is not a count of AI-data contributors, and unnamed RL delivery cases are not named-customer validation.",
  "Prefer official founders and record headcount as unresolved.": "Headcount is unresolved; the founders listed here follow official pages.",
  "High margins, run rate and $150M valuation originate in recruiting copy; require diligence before using as current financial facts": "High margins, the run rate and the $150M valuation come from recruiting copy and are not verified current financial figures.",
  "Press release contrasts its team with contractor-heavy competitors, but official listings explicitly recruit contractors; interpret as positioning, not absence of contract work": "A press release contrasts its team with contractor-heavy competitors, but official listings recruit contractors. The contrast is positioning and does not mean the company uses no contract work.",
  "Do not silently normalize into an incorporation year.": "None of these dates is an established incorporation year.",
  "Largest verified revenue scale in this batch, but old financial snapshot. Financing targets, secondary-market estimates and run-rate figures are widely conflated": "Its verified revenue is among the largest profiled here, but the financial snapshot is old. Financing targets, secondary-market estimates and run-rate figures are often conflated.",
  "Do not confuse pareto.ai with Pareto Securities, Pareto Holdings, trypareto.ai, Brazilian Pareto/Tess or other unrelated businesses.": "pareto.ai is unrelated to Pareto Securities, Pareto Holdings, trypareto.ai, Brazilian Pareto/Tess and other businesses with similar names.",
  "Meta ownership triggered customer-independence concerns and reported Google withdrawal plans.": "Meta’s 49% stake raised customer-independence concerns, and Google reportedly planned to cut ties with Scale.",
  "Do not count CEO’s historical $100M raised for a hedge fund as Trajectory funding.": "The $100M the CEO earlier raised for a hedge fund is not Trajectory funding.",
  "Do not compare the $100M philanthropy pledge, Institute grants, Laude Ventures capital or benchmark grant support with a commercial vendor’s revenue/venture funding.": "The $100M philanthropy pledge, Institute grants, Laude Ventures capital and benchmark grant support are not comparable with a commercial vendor’s revenue or venture funding.",
  "Job-board compensation/location mirrors conflict, so current employer pages take precedence": "Job-board copies of its listings give conflicting pay and locations; this profile follows the current employer pages."
});
// Interim plain wording for Scale AI until dataset 2.5.1 rewords these records (docs/pending-2.5.1-corrections.md).
// It rewrites five fields on four records: scale_ai.claim.oct14-major-financial-0 (statement, caveat),
// scale_ai.metric.oct14-major-financial-0 (basis), scale_ai.claim.audit-readout (statement) and scale_ai.editorial (readout).
// Remove this block after 2.5.1.
Object.assign(PUBLIC_COPY_EDITS,{
  "Includes shareholder liquidity; not equivalent to new primary venture funding.": "Part of the money went to existing shareholders. The total is not all new company funding.",
  "and included substantial shareholder liquidity.": "and included large payouts to existing shareholders."
});
// Turing has two run-rate figures from two releases, both kept. The $167M one has no exact date, so it lists
// above the $300M figure for 2024. Its note says why.
Object.assign(PUBLIC_COPY_EDITS,{
  "Release explicitly expands ARR as annualized revenue run rate.": "The Series E release says the round was priced when the run rate (recent revenue projected across a full year) reached $167M. It does not give that date. In January 2025, Turing reported a $300M run rate for 2024."
});
const PUBLIC_RECORD_IDS=new Set(Object.values(DATA).filter(Array.isArray).flatMap(rows=>rows.map(r=>r?.id).filter(Boolean)).concat(DATA.rubric.stages.map(s=>s.id),['not_applicable','pending']));
const PUBLIC_TEXT_CACHE=new Map();
// One scan finds the texts that contain an edited phrase; only those run the ordered edits below.
// No phrase is empty and no replacement contains a phrase, so other texts would come out unchanged.
const PUBLIC_COPY_PATTERN=new RegExp(Object.keys(PUBLIC_COPY_EDITS).map(phrase=>phrase.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|'));
// Every rewrite in publicTextCompute needs one of these fragments, so a text without any passes through unchanged.
const PUBLIC_REWRITE_PATTERN=/Superseded by the final|Retained as historical provenance|Final audit source |Earlier registry status: |Review status: |Retain claim: Yes|Source support was inherited|Historical statements are preserved|[12],\d\d\d|o not |must not be |should not be |id: |_|\s\s| \.|^\s|\s$/i;
const PUBLIC_COMMAND_VERBS={add:'adding',assume:'assuming',attribute:'attributing',call:'calling',characterize:'characterizing',choose:'choosing',compare:'comparing',confuse:'confusing',convert:'converting',count:'counting',directly:'directly',display:'displaying',equate:'equating',force:'forcing',imply:'implying',import:'importing',infer:'inferring',invent:'inventing',label:'labelling',mark:'marking',mechanically:'mechanically',mislabel:'mislabelling',normalize:'normalizing',present:'presenting',promote:'promoting',replace:'replacing',set:'setting',silently:'silently',substitute:'substituting',transfer:'transferring',treat:'treating',turn:'turning',upgrade:'upgrading',use:'using',guess:'guessing',fabricate:'fabricating',annualize:'annualizing',erase:'erasing'};
function publicText(value){
 const key=String(value??'');
 if(PUBLIC_TEXT_CACHE.has(key))return PUBLIC_TEXT_CACHE.get(key);
 const result=publicTextCompute(key);PUBLIC_TEXT_CACHE.set(key,result);return result;
}
function publicTextCompute(value){
 let text=String(value??'');
 if(PUBLIC_RECORD_IDS.has(text)||/^https?:\/\//i.test(text))return text;
 if(PUBLIC_COPY_PATTERN.test(text))for(const [original,copy] of Object.entries(PUBLIC_COPY_EDITS))text=text.split(original).join(copy);
 // Research notes can quote a person's address from a source page; say how contact works instead of repeating it.
 if(text.includes('contact at '))text=text.replace(/\bcontact at [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g,'contact by email');
 if(!PUBLIC_REWRITE_PATTERN.test(text))return text;
 text=text.replace(/Superseded by the final [^.]+\./g,'Replaced by later research.').replace(/Retained as historical provenance; excluded from active fact selectors\./g,'Historical observation; excluded from current comparisons.');
 text=text.replace(/Final audit source [\w.-]+: /g,'').replace(/Earlier registry status: /g,'Earlier source check: ').replace(/Review status: /g,'Source check: ').replace(/Retain claim: Yes\.?/g,'');
 text=text.replace(/Source support was inherited[^.]*\./g,'Source support has not been rechecked.').replace(/Historical statements are preserved[^.]*\./g,'Historical statements are dated and may not describe current conditions.');
 text=text.replace(/\b([Ff]ound(?:ed|ing)(?: year)?[^.\d]{0,12})([12]),(\d{3})\b/g,'$1$2$3');
 // Convert evidentiary cautions phrased as editing commands to declarative caveats.
 text=text.replace(/\b([Dd])o not (silently |mechanically |directly )?([a-z]+)\b/g,(all,cap,adverb,verb)=>Object.hasOwn(PUBLIC_COMMAND_VERBS,verb)?(cap==='D'?'The':'the')+' evidence does not support '+(adverb||'')+PUBLIC_COMMAND_VERBS[verb]:all);
 text=text.replace(/\bmust not be (shown|presented|represented|treated|counted|reported|label(?:l)?ed|equated|added|summed|merged|transferred)\b/g,'cannot be $1').replace(/\bshould not be (treated|mistaken|equated|relabeled|fabricated|read|combined|reported|substituted)\b/g,'cannot be $1');
 text=text.replace(/\b(?:Round id|Id): [a-z0-9_.-]+\.(?:\s|$)/gi,'').replace(/\b[a-zA-Z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+\b/g,word=>word.replaceAll('_',' '));
 return text.replace(/\s{2,}/g,' ').replace(/ \./g,'.').trim();
}
const esc=v=>publicText(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const title=v=>String(v||'').replaceAll('_',' ').replace(/^./,x=>x.toUpperCase());
const external=(url,label)=>/^https?:\/\//i.test(url||'')?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ${iconHTML('external')}<span class="sr-only"> (opens in a new tab)</span></a>${typeof window.linkAvailabilityHTML==='function'?window.linkAvailabilityHTML(url):''}`:esc(label);
const pill=(label,known=false)=>`<span class="marker ${known?'known':''}">${esc(label)}</span>`;
const currentClaims=id=>DATA.claims.filter(c=>c.company_id===id&&c.status!=='superseded');
const companyClaims=id=>DATA.claims.filter(c=>c.company_id===id);
const companySources=id=>DATA.sources.filter(s=>s.company_id===id||s.id.startsWith(id+'.source.'));
const brief=text=>String(text||'').split(/(?<=[.!?])\s+(?=[A-Z“])/).slice(0,2).join(' ').trim();
const editorialFor=id=>DATA.editorial_readouts.find(e=>e.company_id===id);
const scopeText=(scope,id)=>({company:['handshake_ai','hackerrank','rws_trainai'].includes(id)?'Parent company':'Whole company',ai_data:'AI business',research:companies[id]?.entity_type==='adjacent_research'?'Research organization':'Research activity',other_segment:id==='rws_trainai'?'Generate segment (includes TrainAI)':'Other business segment'}[scope]||title(scope));
const dateText=s=>s==='undated'?'Source date not stated':s;
function sourceReviewText(source){
 const date=source.accessed_on;
 if(source.retrieval_status==='checked')return 'Reviewed '+date;
 if(source.retrieval_status==='summary_only')return 'Recorded '+date+' · Summary only';
 if(source.retrieval_status==='unverified')return 'Recorded '+date+' · Not reverified';
 return 'Recorded '+date;
}
const compiledSnapshotLabel=asOf=>'Public research · compiled '+new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(asOf+'T00:00:00Z'));
function dateRank(s){const text=String(s),year=text.match(/(?:19|20)\d{2}/)?.[0];if(!year)return '0000';const iso=text.match(/(?:19|20)\d{2}-\d{2}(?:-\d{2})?/);if(iso)return iso[0];if(/H1|half.year|six.month/i.test(text))return year+'-06';if(/H2|end of|year.end/i.test(text))return year+'-12';const names=['january','february','march','april','may','june','july','august','september','october','november','december'];const month=names.findIndex(m=>text.toLowerCase().includes(m));return year+(month>=0?'-'+String(month+1).padStart(2,'0'):'');}
const byRecent=(a,b)=>dateRank(b.as_of||b.announced_on).localeCompare(dateRank(a.as_of||a.announced_on))||Number(b.preferred_for_comparison===true)-Number(a.preferred_for_comparison===true)||Number(b.id.includes('major-'))-Number(a.id.includes('major-'))||a.id.localeCompare(b.id);
const metricLabels={funding_total_reported:'Reported lifetime financing',funding_total_calculated:'Sum of disclosed rounds',valuation:'Valuation',arr:'Yearly recurring subscription revenue',annualized_revenue_run_rate:'Annualized revenue pace',revenue:'Period revenue',gmv:'Gross merchandise value',headcount:'Company team size',expert_network:'Expert / contributor network',active_paid_experts:'Active paid experts',customer_count:'Customer count',growth_rate:'Growth measure',other:'Other operating measure'};
const COMPACT_FORMATS={compact:new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:2}),standard:new Intl.NumberFormat('en',{notation:'standard',maximumFractionDigits:2})};
const compact=v=>COMPACT_FORMATS[Math.abs(v)>=100000?'compact':'standard'].format(v);
function metricValue(m){return ({at_least:'≥ ',greater_than:'> ',less_than:'< ',nearly:'Nearly ',at_most:'≤ ',approximate:'≈ ',range:'',exact:''}[m.qualifier]||'')+(m.unit==='currency'?({USD:'$',GBP:'£',EUR:'€'}[m.currency]||m.currency+' '):'')+compact(m.value)+(m.qualifier==='range'?'–'+compact(m.upper_value):'')+(m.unit==='percent'?'%':m.unit==='multiple'?'×':'');}
function financialPeriod(m){if(m.period_type)return ['week','quarter','partial'].includes(m.period_type)?'short':m.period_type;const s=(m.period_label||m.label||'')+' '+m.as_of;return /half|H1|H2|six.month/i.test(s)?'half':/week|quarter|Q[1-4]|month/i.test(s)?'short':/FY\d{4}|annual|full.year|^20\d{2}$/i.test(s.trim())?'annual':/^20\d{2}$/.test(m.period_label||'')?'annual':'other';}
function evidenceLabel(cl){
 const types=cl.source_ids.map(id=>sources[id].source_type);
 if(cl.source_ids.length&&cl.source_ids.every(id=>sources[id].retrieval_status==='unverified'))return 'Inherited evidence · not reverified';
 if(cl.source_ids.length&&cl.source_ids.every(id=>sources[id].retrieval_status==='summary_only'))return 'Summary-only evidence · page not reviewed';
 if(cl.evidence_label==='Attributed primary-source evidence'&&types.length&&types.every(type=>type==='database'))return 'Database summary';
 if(cl.evidence_label){const label=title(cl.evidence_label);return ['taskus','appen'].includes(cl.company_id)&&{'Audited filing':'Annual report filing','Audited public company':'Public company annual report'}[label]||label;}
 if(cl.status==='unverified')return 'Not established';
 if(cl.status==='contested')return 'Conflicting reports';
 if(!types.length)return 'No current cited source';
 const reviewedAttributions={
  'trajectory_labs_pbc.claim.customers-0':['trajectory_labs_pbc.source.b_tl3','https://ai.meta.com/static-resource/muse-spark-safety-and-preparedness-report/','Buyer / counterparty evidence'],
  'quesma.claim.customers-0':['quesma.source.b_q7','https://www.prnewswire.com/news-releases/hydrolix-adds-quesma-gateway-proxy-ip-to-its-portfolio-assuring-continued-kibana-support-302559127.html','Buyer / counterparty evidence'],
  'elorian.claim.headquarters':['elorian.source.elorian-4','https://www.wsgr.com/en/insights/wilson-sonsini-advises-elorian-on-dollar55-million-seed-financing-as-company-emerges-from-stealth.html','Transaction counsel statement'],
  'prolific.claim.founders':['prolific.source.d_pro1','https://innovation.ox.ac.uk/wp-content/uploads/2017/03/170301-Prolific-PR-FINAL.pdf','University incubator statement'],
  'rws_trainai.claim.founders':['rws_trainai.source.d_rws8','https://www.rws.com/media/images/Admission_Document-11_November_2003_tcm228-184244.pdf','Company admission document'],
 };
 const reviewed=Object.hasOwn(reviewedAttributions,cl.id)?reviewedAttributions[cl.id]:null;
 if(reviewed&&cl.status==='supported'&&cl.confidence==='A'&&cl.source_ids.length===1&&cl.source_ids[0]===reviewed[0]&&types[0]==='other'&&sources[reviewed[0]].url===reviewed[1])return reviewed[2];
 if(cl.confidence==='A'&&types.includes('customer'))return 'Buyer / counterparty evidence';
 if(cl.confidence==='A'&&types.includes('filing'))return 'Filed disclosure';
 if(cl.confidence==='C')return 'Indirect or secondary reporting';
 if(types.every(type=>type==='investor'))return 'Investor-reported';
 if(cl.confidence==='A'&&types.every(type=>type==='company'))return 'Company-reported';
 return cl.confidence==='B'?'Attributed primary statement':'Independent reporting';
}
let evidenceDescriptionSequence=0;
// Evidence dates read as "14 Oct 2026" when the profile date helper is loaded; dates repeat, so each is formatted once.
const EVIDENCE_DATES=new Map();
const evidenceDate=value=>{if(typeof profileDate!=='function')return value;if(!EVIDENCE_DATES.has(value))EVIDENCE_DATES.set(value,profileDate(value));return EVIDENCE_DATES.get(value);};
const evidenceRecordTopics=new Map();
const evidenceMetricScopes=new Map();
for(const metric of DATA.metrics){
 const detail=publicText(metric.scope_detail);
 if(detail&&!['company','ai_data','research','other_segment'].includes(metric.scope_detail)){if(!evidenceMetricScopes.has(metric.claim_id))evidenceMetricScopes.set(metric.claim_id,new Set());evidenceMetricScopes.get(metric.claim_id).add(detail);}
}
for(const [rows,topic]of[[DATA.metrics,row=>row.label||metricLabels[row.kind]],[DATA.products,row=>row.name],[DATA.customer_evidence,row=>row.organization],[DATA.funding_rounds,row=>row.round_name],[DATA.company_people,row=>people[row.person_id]?.name],[DATA.company_investors||[],row=>investors[row.investor_id]?.name]]){
 for(const row of rows||[]){const text=publicText(topic(row));if(row.claim_id&&text&&text.length<=100&&!evidenceRecordTopics.has(row.claim_id))evidenceRecordTopics.set(row.claim_id,text);}
}
function evidenceAccess(ids,label,topicHint=''){
 const selected=[...new Set(ids||[])].map(id=>claims[id]).filter(Boolean);
 if(!selected.length)return{attributes:'',description:''};
 const subjects={'financial metrics':'Financial figure','growth metrics':'Growth measure','worker opportunities':'Work opportunity','operating metric':'Operating figure','public application availability':'Application availability','customers':'Relationship evidence','funding rounds':'Financing event','total funding':'Financing total','founders':'Founders and leadership'};
 const gate=selected[0].subject.match(/^ai data gate ([PCRO])$/i),criterion=gate?DATA.rubric.dimensions.find(d=>d.id===gate[1].toUpperCase())?.label:'';
 const topic=publicText(topicHint)||evidenceRecordTopics.get(selected[0].id)||criterion||subjects[selected[0].subject]||title(selected[0].subject.replace(/\s+\d+$/,''));
 const companyNames=[...new Set(selected.map(cl=>companies[cl.company_id]?.name).filter(Boolean))];
 const dates=[...new Set(selected.map(cl=>evidenceContextClaimPeriod(cl,cl.as_of&&cl.as_of!=='undated'?cl.as_of:'not stated')))];
 const name=label+' for '+companyNames.join(' and ')+': '+topic+'. Date'+(dates.length>1?'s':'')+' of the evidence: '+dates.map(evidenceDate).join('; ')+'.';
 const description=selected.map(cl=>{
  const statement=publicText(cl.statement),caveat=publicText(cl.caveat);
  const details=[...(evidenceMetricScopes.get(cl.id)||[])];
  const originalScope=scopeText(cl.segment_scope,cl.company_id),scope=evidenceContextScopeLabel(cl,originalScope),context=evidenceContextClaimDescription(cl);
  return[cl.status!=='supported'?'Status: '+title(cl.status)+'.':'','Evidence label: '+evidenceLabel(cl)+'.','Business covered: '+scope+'.',scope!==originalScope?'Original dataset scope: '+originalScope+'.':'',details.length?'Metric scope detail: '+details.join('; ')+'.':'',context,context?'Original dataset statement: '+statement:statement,caveat&&!statement.includes(caveat)?caveat:''].filter(Boolean).join(' ');
 }).join(' ');
 const descriptionId='evidence-description-'+(++evidenceDescriptionSequence);
 return{attributes:`aria-label="${esc(name)}" aria-describedby="${descriptionId}" aria-haspopup="dialog" aria-controls="evidence-dialog"`,description:`<span id="${descriptionId}" data-evidence-description hidden style="display:none">${esc(description)}</span>`};
}
const claimButton=(id,label='Evidence',topic='')=>{const access=evidenceAccess([id],label,topic);return `<button class="evidence-action" data-claim="${esc(id)}" ${access.attributes}>${esc(label)}</button>${access.description}`;};
const numberButton=m=>{const label=metricValue(m),access=evidenceAccess([m.claim_id],label,metricEvidenceTopic(m,m.label||metricLabels[m.kind]));return `<button class="number-button" data-claim="${esc(m.claim_id)}" ${access.attributes}>${esc(label)}</button>${access.description}`;};
const sourceLinks=cl=>cl.source_ids.map(id=>external(sources[id].url,sources[id].publisher)).join(' ');
const provenance=cl=>`<div class="record-meta">${cl.status!=='supported'?`<b>${esc(title(cl.status))}</b>`:''}<span>${esc(evidenceContextArchiveDate(cl,dateText(cl.as_of)))}</span><span>· ${esc(evidenceContextOriginalScope(cl,scopeText(cl.segment_scope,cl.company_id)))}</span><span>· ${esc(evidenceLabel(cl))}</span>${claimButton(cl.id)}</div>`;
function metricMeta(m){const accounting=metricCurrentBasis(m,['revenue','annualized_revenue_run_rate','arr'].includes(m.kind)?m.gross_vs_net==='unspecified'?'Gross or net revenue not stated':title(m.gross_vs_net)+' basis':'');return `${m.currency?m.currency+' · ':''}${metricContextMetaPeriod(m,m.kind==='revenue'?m.period_label||m.as_of:dateText(m.as_of))} · ${m.scope_detail&&m.scope_detail!=='company'&&m.scope_detail!=='ai_data'?m.scope_detail:scopeText(m.segment_scope,m.company_id)}${accounting?' · '+accounting:''}`;}
function eligibleMetrics(id,kind){return DATA.metrics.filter(m=>(!id||m.company_id===id)&&(!kind||m.kind===kind)&&m.preferred_for_comparison!==false&&claims[m.claim_id].status==='supported'&&(!m.observation_status||m.observation_status==='reported')).sort(byRecent);}
function metricFor(id,kind){return eligibleMetrics(id,kind)[0];}
// Keep headline views on the same reviewed records; earlier observations remain in the archive.
const FINANCIAL_HEADLINES={mercor:'mercor.metric.oct14-major-financial-2',surge_ai:'surge_ai.metric.oct14-major-financial-0',handshake_ai:'handshake_ai.metric.major-growth_metrics-0',turing:'turing.metric.major-growth_metrics-1'};
function preferredFinancial(id){const reviewed=FINANCIAL_HEADLINES[id];if(reviewed){const metric=eligibleMetrics(id).find(m=>m.id===reviewed);if(metric)return metric;}const explicit=assessmentFor(id)?.headline_metric_id;if(explicit){const metric=eligibleMetrics(id).find(m=>m.id===explicit);if(metric)return metric;}const all=eligibleMetrics(id),scope=['handshake_ai','taskus'].includes(id)?'ai_data':all.some(m=>['revenue','arr','annualized_revenue_run_rate'].includes(m.kind)&&m.segment_scope==='company')?'company':all.some(m=>['revenue','arr','annualized_revenue_run_rate'].includes(m.kind)&&m.segment_scope==='ai_data')?'ai_data':null;const scoped=all.filter(m=>!scope||m.segment_scope===scope),kind=k=>scoped.filter(m=>m.kind===k),actual=kind('revenue').filter(m=>['annual','half','ttm'].includes(financialPeriod(m))).sort((a,b)=>dateRank(b.as_of).localeCompare(dateRank(a.as_of))||({ttm:3,annual:2,half:1}[financialPeriod(b)]||0)-({ttm:3,annual:2,half:1}[financialPeriod(a)]||0)||byRecent(a,b));return actual[0]||kind('annualized_revenue_run_rate')[0]||kind('arr').find(m=>dateRank(m.as_of)>='2025')||kind('revenue')[0];}
function assessmentFor(id,scope){return DATA.assessments.find(a=>a.company_id===id&&a.segment_scope===(scope||'ai_data'))||(!scope?DATA.assessments.find(a=>a.company_id===id):undefined);}
function stageFor(id,scope){if(companies[id].entity_type==='adjacent_research')return 'not_applicable';if(DATA.rubric.status!=='final')return 'pending';const a=assessmentFor(id,scope);if(!a)return 'pending';return DATA.rubric.stages.find(s=>Object.entries(s.minimums).every(([d,n])=>a.gates[d].level!=='U'&&Number(a.gates[d].level)>=Number(n)))?.id||'insufficient_public_evidence';}
const stageLabels={established_commercial_evidence:'Established',repeatable_commercial_evidence:'Repeat business',demonstrated_delivery:'Demonstrated delivery',visible_operating_offer:'Offer visible',insufficient_public_evidence:'Evidence incomplete',not_applicable:'Research organization',pending:'Assessment pending'};
const stageLabel=id=>stageLabels[id]||id;
const businessHeadline=id=>assessmentFor(id)?.business_headline||'';
const publicAssessmentLabel=id=>businessHeadline(id)||stageLabel(stageFor(id));
function stageConfidence(id,scope){const a=assessmentFor(id,scope),s=DATA.rubric.stages.find(s=>s.id===stageFor(id,scope));if(!s||!Object.keys(s.minimums).length)return 'unclassified';const relevant=Object.keys(s.minimums).flatMap(k=>a.gates[k].claim_ids.map(id=>claims[id]));if(a.material_conflict||relevant.some(c=>['C','U'].includes(c.confidence)))return 'low_provisional';if(a.stale_source_caveat)return 'medium';const direct=['C','R'].filter(k=>k in s.minimums).flatMap(k=>a.gates[k].claim_ids.map(id=>claims[id])).some(c=>c.confidence==='A'&&c.source_ids.some(s=>['customer','filing'].includes(sources[s].source_type)));return direct?'high':'medium';}
const modelFor=id=>window.EDITORIAL?.entries.find(e=>e.company_id===id)?.summary||editorialFor(id)?.segment||companies[id].description;
// Navigation taxonomy is editorial grouping, not a maturity or quality score.
const MODEL_GROUPS=Object.fromEntries(["Expert data & evaluation", "Managed AI & data services", "Frontier data & RL environments", "AI software & analytics", "AI evaluation & safety", "Compute & model research", "Nonprofit research"].map(name=>[name,(window.EDITORIAL?.entries||[]).filter(e=>e.primary_offering===name).map(e=>e.company_id)]));
const modelGroup=id=>Object.entries(MODEL_GROUPS).find(([,ids])=>ids.includes(id))?.[0]||'Other';
const WORK_TYPES={'Employment':'Jobs','Expert & contractor projects':'Contract and task work','Research fellowship':'Research fellowships','Contributor bounties':'Bounties for contributions'};
const workClaims=id=>currentClaims(id).filter(c=>c.subject==='worker opportunities');
function workRouteSummary(id){
 const rows=typeof workRoutesFor==='function'?workRoutesFor(id):[];
 return {rows,...(typeof w4RouteGroups==='function'?w4RouteGroups(rows):{primary:[],careers:[],other:rows})};
}
function workType(id){
 const {rows,primary,careers}=workRouteSummary(id);
 if(primary.length)return [...new Set(primary.map(r=>WORK_TYPES[r.group]||r.group||'Paid work listings'))].join(' · ');
 if(careers.length)return 'Career page only';
 return rows.length?'No confirmed paid listing':'Paid work not reviewed yet';
}
const hasWorkRoute=id=>{const {primary,careers}=workRouteSummary(id);return Boolean(primary.length||careers.length);};
const unknownFor=id=>currentClaims(id).filter(c=>c.subject==='unknowns').sort((a,b)=>Number(b.id.includes('audit'))-Number(a.id.includes('audit')))[0];

function financialSignal(id){const m=preferredFinancial(id);return m?`${numberButton(m)}<span class="sub">${esc(metricLabels[m.kind])}${m.gross_vs_net==='gross'?' · '+esc(metricCurrentBasis(m,'gross basis')):''}</span><span class="sub">${esc(m.currency||'')} · ${esc(metricCurrentPeriod(m,dateText(m.as_of)))} · ${esc(scopeText(m.segment_scope,id))}</span><span class="sub">${esc(metricCurrentAttribution(m,evidenceLabel(claims[m.claim_id])))}</span>`:`<strong style="font-size:15px">${companies[id].entity_type==='adjacent_research'?'Commercial revenue not applicable':'Revenue not publicly established'}</strong><span class="sub">${claimButton((currentClaims(id).find(c=>c.subject==='growth metrics')||claims[companies[id].identity_claim_id]).id,'See reviewed evidence')}</span>`;}
function compareCheck(id){return `<label class="compare-check"><input type="checkbox" data-compare="${esc(id)}" aria-label="Compare ${attr(companies[id]?.name||id)}" ${state.selected.includes(id)?'checked':''}> Compare</label>`;}
function filtered(){
 const tokens=state.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
 // Match literal term prefixes at word starts; keep letters, numbers and combining marks together.
 const prefixes=tokens.map(token=>new RegExp('(?:^|[^\\p{L}\\p{N}\\p{M}])'+token.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'u'));
 return DATA.companies.filter(c=>{
  const products=DATA.products.filter(p=>p.company_id===c.id).flatMap(p=>[p.name,p.work_performed]);
  const offerings=typeof profileProducts==='function'?profileProducts(c.id).flatMap(p=>[p.name,p.description,...(p.aliases||[])]):[];
  const searchable=[c.name,...(c.aliases||[]),c.description,modelFor(c.id),...products,...offerings].filter(Boolean).join(' ').toLowerCase();
  return prefixes.every(prefix=>prefix.test(searchable))&&(!state.category||modelGroup(c.id)===state.category)&&(!state.stage||stageFor(c.id)===state.stage)&&(!state.financial||preferredFinancial(c.id))&&(!state.work||hasWorkRoute(c.id));
 }).sort((a,b)=>(state.sort==='name-desc'?-1:1)*a.name.localeCompare(b.name));
}

function latestByScope(rows){const seen=new Set();return rows.sort(byRecent).filter(m=>{const key=m.company_id+'|'+m.segment_scope+'|'+(['company','ai_data','research','other_segment'].includes(m.scope_detail)?'':m.scope_detail||'');if(seen.has(key))return false;seen.add(key);return true;});}
function chartRows(rows,dots=false){if(!rows.length)return '<p class="empty-chart">No eligible observations for this period and currency. Missing values are not zero.</p>';const max=Math.max(...rows.map(m=>m.value));return rows.sort((a,b)=>b.value-a.value).map(m=>`<div class="chart-row" data-chart-metric="${esc(m.id)}"><div class="chart-line"><a href="#company/${esc(m.company_id)}">${esc(companies[m.company_id].name)}</a>${numberButton(m)}</div><p class="chart-meta">${esc(metricMeta(m))}<br>${esc(metricCurrentAttribution(m,evidenceLabel(claims[m.claim_id])))}</p>${dots?`<div class="dot-track" aria-hidden="true"><span class="dot" style="left:${Math.max(0,Math.min(100,m.value/max*100))}%"></span></div>`:`<div class="bar-track" aria-hidden="true"><span class="bar ${['at_least','greater_than'].includes(m.qualifier)?'bound':''}" style="width:${m.value/max*100}%"></span></div>`}</div>`).join('')+`<div class="axis" aria-hidden="true"><span>0</span><span>${rows[0].currency} ${compact(max)}${rows.some(r=>['at_least','greater_than'].includes(r.qualifier))?' (bound)':''}</span></div>`;}
function renderCharts(){const actual=latestByScope(eligibleMetrics(null,'revenue').filter(m=>m.currency===state.revenueCurrency&&financialPeriod(m)===state.revenuePeriod));const groups=[...new Set(actual.map(m=>m.gross_vs_net))];$('revenue-chart').innerHTML=groups.length?groups.map(b=>`<section class="chart-group"><h4 class="chart-group-title">${b==='unspecified'?'Gross or net revenue not stated':title(b)+' basis'}</h4>${chartRows(actual.filter(m=>m.gross_vs_net===b))}</section>`).join(''):chartRows([]);const run=latestByScope(eligibleMetrics(null,'annualized_revenue_run_rate').filter(m=>m.currency==='USD'&&dateRank(m.as_of)!=='0000'&&m.as_of!=='undated'));$('runrate-chart').innerHTML=['gross','unspecified','net'].map(b=>{let rows=run.filter(m=>m.gross_vs_net===b).sort((a,b)=>b.value-a.value);if(!rows.length)return '';const count=rows.length;if(!state.runratesExpanded)rows=rows.slice(0,b==='gross'?3:5);return `<section class="chart-group"><h4 class="chart-group-title">${b==='unspecified'?'Gross or net revenue not stated':title(b)+' billings / revenue'}</h4>${chartRows(rows,true)}${count>rows.length?`<p class="chart-more">${count-rows.length} more observations available</p>`:''}</section>`;}).join('')+`<button class="quiet chart-more" data-runrates>${state.runratesExpanded?'Show fewer':'Show all run-rate observations'}</button>`;}

function historicalSourceHTML(cl){const ids=cl.historical_source_ids||[];return ids.length?`<details class="historical-citations"><summary>Previous citations</summary><p class="sub">Retained for provenance. Their current content does not support this claim.</p><ul>${ids.map(id=>`<li>${external(sources[id].url,sources[id].title)}<p class="sub">${esc(sources[id].notes||'Historical citation')}</p></li>`).join('')}</ul></details>`:'';}
function claimRecord(c){const clarified=Boolean(evidenceContextStatementHeading(c));return `<article class="record" data-claim-record="${esc(c.id)}">${clarified?evidenceContextClaimHTML(c.id)+evidenceContextStatementHeadingHTML(c):''}<p>${esc(c.statement)}</p>${clarified?'':evidenceContextClaimHTML(c.id)}${profileProvenance(c)}${c.caveat&&!publicText(c.statement).includes(publicText(c.caveat))?`<p class="sub">${esc(c.caveat)}</p>`:''}<div class="source-links">${sourceLinks(c)}</div>${historicalSourceHTML(c)}</article>`;}

// These filters describe the reviewed public route, never individual eligibility.
const US_LISTING_IDS=new Set(['scale_ai','g2i','elorian','terac','appen','rws_trainai','prolific','abundant_ai','toloka']);
// Additional routes are tied to specific reviewed claims, not inferred from company size.
const ADDITIONAL_WORK_TYPES={
 'Research fellowship':['surge_ai.claim.worker_opportunities-1'],
 'Employment':['afterquery.claim.worker_opportunities-2','bespoke_labs.claim.worker_opportunities-2','proximal.claim.worker_opportunities-1','trajectory_labs_pbc.claim.worker_opportunities-1','datacurve.claim.worker_opportunities-1','surge_ai.claim.worker_opportunities-2']
};
function workTerms(id){
 const cs=workClaims(id),text=cs.map(c=>c.statement).join(' '),sentences=cs.flatMap(c=>c.statement.split(/(?<=[.!?])\s+/).map(text=>({text,claim_id:c.id}))),pay=sentences.filter(s=>/[$£€]\s?[\d]/.test(s.text));
 const group=/No .*verified|No current paid/.test(workType(id))?'Unverified route':/fellowship/i.test(workType(id))?'Research fellowship':/employment|careers/i.test(workType(id))?'Employment':/bounties/i.test(workType(id))?'Contributor bounties':'Expert & contractor projects';
 const groups=[...new Set([group,...Object.entries(ADDITIONAL_WORK_TYPES).filter(([,ids])=>cs.some(c=>ids.includes(c.id))).map(([name])=>name)])];
 return {cs,groups,pay,eligibility:US_LISTING_IDS.has(id)?'US listing evidence':id==='aixi'?'Worldwide wording':'Check project / unverified',requirements:sentences.filter(s=>/eligib|requir|degree|PhD|geograph|residen|remote|on.site|hybrid|experience|US |US-|worldwide|anywhere/i.test(s.text))};
}
function workAction(s){const u=s.url.toLowerCase();if(/fellowship|frontierswe.com\/contribute/.test(u))return 'View fellowship';if(/\/careers|workatastartup|ycombinator.com/.test(u))return 'View careers';if(/ashbyhq|greenhouse|workable|lever.co|alignerr.com\/jobs/.test(u))return 'View role listing';if(/worker_signup|\/apply\/|harbest|\/join|become-an-expert/.test(u))return 'View application route';if(/terms|privacy|payment|help\.|participant-help/.test(u))return 'Read terms / eligibility';if(/software-engineering/.test(u))return 'Read program background';if(/expert|fellowship|surgehq.ai\/swe|mindrift.ai\/project|crowdgen|trainai-community|tai.rws.com/.test(u))return 'View contributor program';return 'Read route evidence';}
function workLinks(id){const unique=new Map();for(const c of workClaims(id))for(const sid of c.source_ids){const src=sources[sid];if(!unique.has(src.url))unique.set(src.url,src);}return `<div class="work-actions">${[...unique.values()].map(s=>external(s.url,workAction(s))).join('')}</div>`;}
function workSummary(id){const t=workTerms(id);return `${t.cs.some(c=>c.status!=='supported')?'<p class="audit-note">Some route evidence is historical or has not been rechecked. Current intake and terms may differ.</p>':''}<dl class="work-terms"><div><dt>Work type</dt><dd>${esc([...new Set([...t.groups,workType(id)])].join(' · '))}</dd></div><div><dt>Advertised pay</dt><dd>${t.pay.length?t.pay.map(p=>`<p>${esc(p.text)} ${claimButton(p.claim_id,'Pay source')}</p>`).join(''):'No numeric rate established in the reviewed route.'}</dd></div><div><dt>Geographic evidence & requirements</dt><dd><b>${esc(t.eligibility)}</b>${id==='toloka'?'<p class="audit-note">Texas US-remote listing checked October 12, 2026. Current intake is not verified open.</p>':''}${t.requirements.slice(0,2).map(p=>`<p>${esc(p.text)} ${claimButton(p.claim_id,'Requirements source')}</p>`).join('')||'<p>Check the source for current project requirements.</p>'}</dd></div></dl>${workLinks(id)}`;}
function workPaySummary(t){
 const rate=/(?:average pay (?:over )?|up to |approximately |top experts earn |over )?[$£€][\d,]+[Kk]?(?:[–-]\s*[$£€]?[\d,]+[Kk]?)?\+?(?:\/(?:hour|week|month)|\s+(?:per approved hour|per hour(?: equivalent)?|hourly rates|salary|base))/gi;
 const seen=new Set(),items=[];
 for(const p of t.pay){const matches=p.text.match(rate)||[];for(const match of matches){let label=match.trim();const statement=claims[p.claim_id].statement;if(/historical|no longer accepting/i.test(statement))label='Historical: '+label;if(/per completed task/i.test(statement))label+=' · paid per task';if(/equivalent/i.test(statement)&&!label.includes('equivalent'))label+=' equivalent';if(/pay-range inconsistency/i.test(statement))label+=' · conflicting listing rates';if(!seen.has(label)){seen.add(label);items.push(claimButton(p.claim_id,label));}}}
 return items.length?items.join('<span class="pay-separator"> / </span>'):'No numeric rate established';
}
function primaryWorkSource(id){const unique=new Map();for(const cl of workClaims(id))for(const sid of cl.source_ids){const source=sources[sid];if(!unique.has(source.url))unique.set(source.url,source);}const rank=source=>{const action=workAction(source);return action==='View role listing'?0:action==='View application route'?1:action==='View fellowship'?2:action==='View contributor program'?3:action==='View careers'?4:action==='Read route evidence'?5:6;};return [...unique.values()].sort((a,b)=>rank(a)-rank(b))[0];}
function workCard(c){const t=workTerms(c.id),primary=primaryWorkSource(c.id);return `<article class="work-card" data-work-company="${esc(c.id)}"><div class="card-head"><div><h3><a href="#company/${esc(c.id)}/work">${esc(c.name)}</a></h3><span class="sub">${esc([...new Set(t.groups)].join(' · '))} · ${esc(t.eligibility)}</span></div>${compareCheck(c.id)}</div><div class="work-overview"><div class="work-pay-summary"><span class="sub">Advertised pay</span>${workPaySummary(t)}</div><div class="work-primary-route">${primary?external(primary.url,workAction(primary)):`<a href="#company/${esc(c.id)}/work">View route evidence</a>`}<span class="sub">Checked ${esc(DATA.meta.as_of)}</span></div></div><details class="work-requirements"><summary>Requirements & full terms</summary>${t.requirements.length?t.requirements.map(p=>`<p>${esc(p.text)} ${claimButton(p.claim_id,'Source')}</p>`).join(''):'<p>Check current requirements with the provider.</p>'}${workLinks(c.id)}<details><summary>Full route evidence</summary>${workClaims(c.id).map(claimRecord).join('')}</details><p class="sub">Current intake must be confirmed with the provider.</p></details></article>`;}
function filteredWork(){return DATA.companies.filter(c=>{const t=workTerms(c.id);return t.cs.length&&`${c.name} ${workType(c.id)} ${t.cs.map(c=>c.statement).join(' ')}`.toLowerCase().includes(state.workQuery.toLowerCase())&&(!state.workGroup||t.groups.includes(state.workGroup))&&(!state.workPay||(state.workPay==='numeric')===Boolean(t.pay.length))&&(!state.workEligibility||t.eligibility===state.workEligibility);}).sort((a,b)=>a.name.localeCompare(b.name));}
function renderWork(){const rows=filteredWork();$('work-count').textContent=`${rows.length} ${rows.length===1?'organization':'organizations'} with reviewed route evidence`;$('work-cards').innerHTML=rows.map(workCard).join('')||'<p>No routes match these filters. Clear a filter to widen the selection.</p>';syncSelection();}

function unconfirmedValuation(m){return m.kind==='valuation'&&(claims[m.claim_id].status!=='supported'||(m.observation_status&&m.observation_status!=='reported'));}
// Estimates never read "Reported".
function metricStatusLabel(m){const status=m.observation_status||'reported';if(m.reported_vs_estimated==='estimated')return status==='reported'?'Estimate':'Estimate · '+title(status);return status==='reported'?'Reported':title(status);}
function metricTile(m){return `<article class="metric-tile ${unconfirmedValuation(m)?'unconfirmed-metric':''}" data-metric="${esc(m.id)}"><h3>${unconfirmedValuation(m)?'Unconfirmed valuation · '+esc(title(m.observation_status||claims[m.claim_id].status)):esc(metricLabels[m.kind])}</h3>${profileNumberButton(m)}<span class="sub">${esc(profileSentenceCase(metricPresentationLabel(m,m.label)))}</span><span class="sub">${esc(readableDate(metricMeta(m)))}</span><span class="sub">${esc([metricStatusLabel(m),profileMetricHistory(m),metricCurrentAttribution(m,profileEvidenceLabel(claims[m.claim_id]))].filter(Boolean).join(' · '))}</span><div class="source-links">${sourceLinks(claims[m.claim_id])}</div>${m.duplicate_records?.length?`<details><summary>More sources for this figure</summary>${m.duplicate_records.map(d=>`<div data-metric="${esc(d.id)}">${claimButton(d.claim_id,'Source')} ${sourceLinks(claims[d.claim_id])}</div>`).join('')}</details>`:''}</article>`;}
function fundingRows(id){return DATA.funding_rounds.filter(r=>r.company_id===id).sort(byRecent);}
function fundingSummary(id){const ms=['funding_total_reported','funding_total_calculated'].map(k=>metricFor(id,k)).filter(Boolean);if(ms.length)return ms.map(m=>`<p>${numberButton(m)}<span class="sub">${esc(id==='handshake_ai'&&m.kind==='funding_total_reported'?'Derived reported cumulative total':metricLabels[m.kind])} · ${esc(profileDate(m.as_of))} · ${esc(scopeText(m.segment_scope,id))}</span>${claimButton(m.claim_id,'Funding basis')}${id==='handshake_ai'?'<span class="sub">$235.5M previously reported cumulative + $200M Series F. Listed event amounts total $434M.</span>':''}</p>`).join('');const r=fundingRows(id).find(r=>'amount'in r&&['closed','announced'].includes(r.status));return r?`<p><strong>${esc(metricValue({value:r.amount,qualifier:r.qualifier,currency:r.currency,unit:'currency'}))}</strong><span class="sub">${esc(r.round_name)} · ${esc(r.status)} · ${esc(profileCapitalContext(r).dateLabel||'Announced')} ${esc(profileDate(r.announced_on))} · ${esc(scopeText(r.segment_scope,id))}</span>${claimButton(r.claim_id,'Source')}</p><p class="sub">Complete lifetime financing is not established.</p>`:`<p class="sub">${companies[id].entity_type==='adjacent_research'?'Commercial financing is not applicable.':['appen','rws_trainai'].includes(id)?'Public-company financing; no comparable private-round total reconstructed.':'Complete financing total not established in reviewed sources.'}</p>`;}
function disclosedPrimarySummary(id){const groups=new Map();for(const r of fundingRows(id).filter(r=>r.include_in_disclosed_primary_sum&&claims[r.claim_id].status==='supported')){if(!groups.has(r.currency))groups.set(r.currency,[]);groups.get(r.currency).push(r);}return [...groups.entries()].map(([currency,rows])=>`<p class="disclosed-sum"><b>${esc(metricValue({value:rows.reduce((n,r)=>n+r.amount,0),currency,unit:'currency',qualifier:'exact'}))}</b><span class="sub">Sum of new money from ${rows.length} disclosed ${rows.length===1?'round':'rounds'}, in ${esc(currency)}. It includes announced rounds that may not have closed. It may not cover every round.</span>${rows.map(r=>claimButton(r.claim_id,r.round_name)).join(' · ')}</p>`).join('');}
function financingDetails(r){const fields=[['first_sale_on','First sale'],['filing_on','Filing date'],['offering_ceiling','Offering ceiling'],['remaining_unsold_at_filing','Unsold at filing'],['primary_component','New company funding'],['secondary_component','Existing shares sold']];return fields.filter(([key])=>r[key]!==undefined).map(([key,label])=>`<span class="sub">${label}: ${esc(typeof r[key]==='number'?metricValue({value:r[key],unit:'currency',currency:r.currency,qualifier:'exact'}):r[key])}</span>`).join('');}
function financingEvent(r){return `<article class="record" data-funding="${esc(r.id)}"><h3>${esc(r.round_name)} · ${'amount'in r?esc(metricValue({value:r.amount,unit:'currency',currency:r.currency,qualifier:r.qualifier})):'Amount not disclosed'}</h3><p class="sub">${esc(profileDate(r.announced_on))} · ${esc(title(r.status))} · ${esc(title(r.capital_type))} · ${esc(scopeText(r.segment_scope,r.company_id))}</p><p>${esc(claims[r.claim_id].statement)}</p><p class="sub">Investors: ${DATA.round_investors.filter(x=>x.round_id===r.id).map(x=>`${esc(investors[x.investor_id].name)} (${esc(x.role)})`).join(', ')||'See the financing statement above; names are not separately structured.'}</p>${profileProvenance(claims[r.claim_id])}${financingDetails(r)}<details><summary>How this amount is counted</summary><p class="sub">${esc(title(r.amount_basis))} · ${esc(r.inclusion_reason)}${r.closed_on?` Closed ${esc(profileDate(r.closed_on))}.`:''}</p></details></article>`;}
function customerRecord(r){const cl=claims[r.claim_id];return `<article class="record" data-customer="${esc(r.id)}">${evidenceContextStatementHeading(cl)?evidenceContextClaimHTML(cl.id)+evidenceContextStatementHeadingHTML(cl):''}<h3>${esc(r.organization)}</h3><p class="sub">${esc(r.relationship_detail||title(r.relationship))} · ${r.disclosure==='customer_confirmed'?'Counterparty-confirmed':esc(title(r.disclosure))} · ${r.paid_status==='unknown'?'Payment not publicly established':esc(title(r.paid_status))}</p><p>${esc(r.use_case||cl.statement)}</p>${profileProvenance(cl)}<div class="source-links">${sourceLinks(cl)}</div></article>`;}
function narrativeSection(cl){const s=cl.subject.toLowerCase();if(/worker opportun/.test(s))return 'work';if(/founder|leadership|founding year|headquarters|legal identity|company profile/.test(s))return 'people';if(/funding|financing|valuation|investor|financial disclosure/.test(s))return 'finance';if(/growth|operating signal|financial scope|financial metrics|financial interpretation|metric|revenue/.test(s))return 'traction';if(/customer|commercial proof/.test(s))return 'customers';if(/product|operating process|business model/.test(s))return 'products';if(/gate|commercial maturity|editorial readout|category/.test(s))return 'method';return 'questions';}
// Dataset 2.5.0 holds some figures twice: a later research pass re-read a page that an
// earlier record already cites. Each key is listed under the figure it repeats, as another
// source. Drop an entry once the research release retires that record.
const SAME_OBSERVATION={
 'abundant_ai.metric.oct14-2-expert-network':'abundant_ai.metric.audit-abundant-network',
 'afterquery.claim.growth_metrics-0.metric-0':'afterquery.metric.round2-financial-2',
 'afterquery.metric.oct14-1-expert-network':'afterquery.claim.growth_metrics-0.metric-1',
 'afterquery.metric.oct14-5-benchmark-domain-coverage':'afterquery.metric.round2-legora-areas',
 'bespoke_labs.metric.oct14-0-open-source-adoption':'bespoke_labs.metric.specialist-1',
 'mercor.metric.major-growth_metrics-0':'mercor.metric.oct14-major-financial-2',
 'proximal.metric.specialist-3':'proximal.metric.oct14-0-revenue-run-rate',
 'surge_ai.claim.growth_metrics-0.metric-0':'surge_ai.metric.oct14-major-financial-0',
 'terac.metric.oct14-0-registered-expert-pool':'terac.claim.growth_metrics-0.metric-0',
 'terac.metric.oct14-1-worker-payout':'terac.metric.audit-terac-payout',
 'toloka.metric.major-growth_metrics-3':'toloka.metric.oct14-0-expert-and-annotator-pool'
};
function uniqueMetrics(id){
 const groups=new Map(),key=m=>[m.kind,m.segment_scope,m.scope_detail||'',m.as_of,m.value,m.qualifier,m.observation_status,m.currency].join('|');
 const rows=DATA.metrics.filter(m=>m.company_id===id&&claims[m.claim_id].status!=='superseded').sort((a,b)=>a.kind.localeCompare(b.kind)||byRecent(a,b));
 // A repeat folds into its figure only while that figure is shown and is not itself a repeat.
 const shown=new Set(rows.map(m=>m.id)),target=m=>{const t=SAME_OBSERVATION[m.id];return t&&shown.has(t)&&!SAME_OBSERVATION[t]?t:null;};
 for(const m of rows.filter(m=>!target(m))){const k=key(m);if(groups.has(k))groups.get(k).duplicate_records.push(m);else groups.set(k,{...m,duplicate_records:[]});}
 const owner=new Map([...groups.values()].flatMap(g=>[[g.id,g],...g.duplicate_records.map(d=>[d.id,g])]));
 for(const m of rows.filter(target)){const g=owner.get(target(m));if(g)g.duplicate_records.push(m);else groups.set('repeat|'+m.id,{...m,duplicate_records:[]});}
 return [...groups.values()];
}
const REVIEWED_TRENDS={
 appen:{ids:['appen.metric.major-financial_metrics-0','appen.metric.major-financial_metrics-1','appen.metric.major-financial_metrics-2'],note:'Whole-company revenue in US dollars for full financial years. These are reported totals. They include the effect of losing the Google business.'},
 taskus:{ids:['taskus.metric.expansion-4','taskus.metric.expansion-3','taskus.metric.expansion-2'],note:'Revenue of the AI Services line of TaskUs, in US dollars, for full financial years. Whole-company, half-year and trailing 12-month figures are left out.'}
};
function growthHTML(id){const config=REVIEWED_TRENDS[id],rows=config?config.ids.map(mid=>DATA.metrics.find(m=>m.id===mid)).filter(Boolean):[],changes=eligibleMetrics(id,'growth_rate'),max=Math.max(1,...rows.map(m=>m.value));return (rows.length>1?`<div class="growth-trend" data-growth-trend="${esc(id)}"><h3>Comparable annual revenue</h3><p class="sub">${esc(config.note)}</p>${rows.map(m=>`<div class="chart-row"><div class="chart-line"><span>${esc(m.period_label)}</span>${numberButton(m)}</div><div class="bar-track" aria-hidden="true"><span class="bar" style="width:${m.value/max*100}%"></span></div><span class="sub">${esc(evidenceLabel(claims[m.claim_id]))}</span></div>`).join('')}<p class="sub">Linear bars start at zero. Missing periods are not filled.</p></div>`:'<p class="muted">No reviewed like-for-like time series is charted. Dated observations retain their own periods and bases below.</p>')+changes.map(m=>`<article class="record" data-growth="${esc(m.id)}"><h3>${esc(m.label)} · ${numberButton(m)}</h3>${provenance(claims[m.claim_id])}<p>${esc(m.basis)}</p>${claims[m.claim_id].caveat?`<p class="sub">${esc(claims[m.claim_id].caveat)}</p>`:''}</article>`).join('');}
/* Presentation-only profile replacement. Canonical data is never changed. */
function profileSection(name,label,html){
  return `<section class="profile-section" id="profile-${name}" data-profile-section="${name}"><h2>${esc(label)}</h2>${html||'<p class="muted">Not established in the reviewed sources.</p>'}</section>`;
}

// Ignore hash queries and letter case; decode company and compare parts once. Malformed escapes stay unknown.
function routeParts(hash=location.hash){
  const parts=String(hash||'').replace(/^#/,'').split('?')[0].split('/');parts[0]=parts[0].toLowerCase();return parts.map((part,index)=>{
    try{part=index&&['company','compare'].includes(parts[0])?decodeURIComponent(part):part;}catch{}
    return parts[0]==='company'&&index===2?part.toLowerCase():part;
  });
}
function isCompanyId(id){return typeof id==='string'&&Object.hasOwn(companies,id);}

const PROFILE_ROUTE_SECTIONS=new Set(['business','products','customers','risks','traction','growth','people','finance','capital','work','method','questions','sources','observations','financing']);
function profileRouteSection(value){return PROFILE_ROUTE_SECTIONS.has(value)?value==='capital'?'finance':value:'';}
function profileRouteDestination(value){
  const section=profileRouteSection(value);if(!section)return null;
  const primary=['business','traction','people','work'].includes(section);
  return document.querySelector(primary?'[data-profile-pane="'+section+'"]':'[data-profile-section="'+section+'"]');
}

function profileTabFor(section){
  if(['traction','growth'].includes(section))return 'traction';
  if(['people','finance','capital'].includes(section))return 'people';
  if(section==='work')return 'work';
  return 'business';
}
// Tabs switch in place; replaceState keeps Back history clean. The rendered id covers case-variant links.
function activateProfileTab(tab){
  const id=profileRouteCompany(document.querySelector('#profile-view .profile-v2')?.dataset?.profileCompany||routeParts()[1]);
  if(!id||!['business','traction','people','work'].includes(tab))return;
  history.replaceState(history.state??null,'','#company/'+id+'/'+tab);
  renderCompanyProfile(id);
  const bar=document.querySelector('.profile-tabs');
  if(bar&&typeof getComputedStyle==='function'&&bar.getBoundingClientRect().top<=parseFloat(getComputedStyle(bar).top)+1)bar.scrollIntoView({block:'start',behavior:'instant'});
}
function profileDisclosure(label,html,open=false){return `<details class="profile-disclosure"${open?' open':''}><summary>${label}</summary>${html}</details>`;}
function profileGrowth(id){
  const config=REVIEWED_TRENDS[id];if(!config)return '';
  const rows=config.ids.map(mid=>DATA.metrics.find(m=>m.id===mid)).filter(Boolean),max=Math.max(1,...rows.map(m=>m.value));
  return `<section id="profile-growth" class="profile-growth" data-profile-section="growth"><h2>Revenue over time</h2><p class="sub">${esc(config.note)}</p><div data-growth-trend="${esc(id)}">${rows.map(m=>`<div class="chart-row"><div class="chart-line"><span>${esc(readableDate(metricCurrentPeriod(m,m.period_label||m.as_of)))}</span>${numberButton(m)}</div><div class="bar-track" aria-hidden="true"><span class="bar" style="width:${m.value/max*100}%"></span></div></div>`).join('')}</div></section>`;
}

function renderAssessment(a){
  return `<details data-formal-minimum="${esc(a.company_id)}"><summary>Assessment rules · ${esc(a.scope_label||scopeText(a.segment_scope,a.company_id))}</summary><article class="record"><h3>Evidence level supported: ${esc(stageLabel(stageFor(a.company_id,a.segment_scope)))}</h3><p class="sub">Assessed ${esc(profileDate(a.as_of))} · ${esc(title(stageConfidence(a.company_id,a.segment_scope)))} evidence confidence</p>${evidenceContextAssessmentHTML(a)}<p>${esc(a.stage_limitations)}</p>${a.stage_use?`<p class="sub">${esc(a.stage_use)}</p>`:''}${a.scope_exclusions?.length?`<ul>${a.scope_exclusions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${Object.entries(a.gates).map(([key,g])=>`<div class="record"><h4>${esc(DATA.rubric.dimensions.find(d=>d.id===key).label)} · ${g.level==='U'?'Unknown':esc(g.level)}</h4>${evidenceContextCriterionHTML(a,key)}<p>${esc(g.rationale)}</p>${g.claim_ids.map(id=>claimButton(id,'Criterion source')).join(' ')}</div>`).join('')}</article></details>`;
}

// The live profile template is profileHTML() in profiles-v2.js.

function compactCapitalQualification(record){
 if(!record)return '';
 const context=[record.basis,record.round_name,claims[record.claim_id]?.statement,claims[record.claim_id]?.caveat].filter(Boolean).join(' ');
 if(record.amount_basis==='mixed_transaction')return 'Includes existing shares sold by shareholders. The total is not all new company funding.';
 if(record.capital_type==='secondary')return 'Existing shareholders sold shares. The company raised no new money in this deal.';
 if(record.capital_type==='mixed'&&/credit/i.test(context))return 'Includes equity and credit. Component amounts and credit drawdown are undisclosed.';
 if(/mixed primary[\s/]+secondary|primary and secondary/i.test(context))return 'Includes primary financing and sales of existing shares; this is not a pure new-capital total.';
 return '';
}
// Rounds announced as one raise. They are summed only when a round record states the combined total.
const COMPARE_RAISES={appen:{rounds:['appen.round.major-8','appen.round.major-9'],label:'Placement and share purchase plan'}};
function compareRaise(id){const plan=Object.hasOwn(COMPARE_RAISES,id)?COMPARE_RAISES[id]:null,rows=(plan?.rounds||[]).map(rid=>DATA.funding_rounds.find(r=>r.id===rid));if(!rows.length||rows.some(r=>!r||r.company_id!==id||r.status!=='closed'||r.amount_basis!=='new_capital'||!(r.amount>0)||r.currency!==rows[0].currency||claims[r.claim_id]?.status!=='supported'))return null;const total=rows.reduce((n,r)=>n+r.amount,0),stated=rows.find(r=>/combined[^.]*?raise\s+\D{0,3}[\d.]+\s?M\b/i.test(claims[r.claim_id].caveat||''));const value=Number((claims[stated?.claim_id]?.caveat||'').match(/combined[^.]*?raise\s+\D{0,3}([\d.]+)\s?M\b/i)?.[1]);return stated&&value*1e6===total?{rows,total,label:plan.label,claim:stated.claim_id}:null;}
function compactFundingSummary(id){const m=metricFor(id,'funding_total_reported')||metricFor(id,'funding_total_calculated');if(id==='handshake_ai'&&m?.id==='handshake_ai.metric.major-total_funding')return `<p>${numberButton(m)}<span class="sub">Derived parent financing total · ${esc(readableDates(m.as_of))}</span></p><p class="sub">$235.5M prior total + $200M Series F. Listed rounds sum to $434M; the $1.5M difference is unexplained.</p>`;const raise=!m&&compareRaise(id);if(raise){const label=metricValue({value:raise.total,unit:'currency',currency:raise.rows[0].currency,qualifier:'exact'}),access=evidenceAccess([raise.claim],label,raise.label);return `<p><button class="number-button" data-claim="${esc(raise.claim)}" ${access.attributes}>${esc(label)}</button>${access.description}<span class="sub">Raised ${esc(monthSpan(raise.rows.map(r=>r.announced_on)))} · ${esc(raise.label)} · ${esc(scopeText(raise.rows[0].segment_scope,id))}</span></p><p class="sub">Complete lifetime financing is not established.</p>`;}const r=m||fundingRows(id).find(r=>'amount'in r&&['closed','announced'].includes(r.status)),qualification=compactCapitalQualification(r);
 // A total reported before a later transformative deal says so, with the deal's month from its round record.
 const before=m&&/\bpre-Meta\b/i.test(m.basis||'')?fundingRows(id).find(x=>/\bMeta\b/.test(x.round_name||'')&&dateRank(x.announced_on)>=dateRank(m.as_of)):null,label=before?`Reported financing before Meta’s ${readableDates(String(before.announced_on).slice(0,7))} deal`:m&&metricLabels[m.kind];
 return (m?`<p>${numberButton(m)}<span class="sub">${esc(label)} · ${esc(readableDates(dateText(m.as_of)))} · ${esc(scopeText(m.segment_scope,id))}</span></p>`:fundingSummary(id))+(qualification?`<p class="sub capital-scope">${esc(qualification)}</p>`:'');}

function comparisonRows(){return [
 ['Main offering',id=>`<span class="category-label">${esc(groupLabel(modelGroup(id)))}</span><p>${esc(modelFor(id))}</p>`],
 ['Products',id=>`<p>${DATA.products.filter(p=>p.company_id===id&&p.id.includes('oct14')).slice(0,3).map(p=>esc(p.name)).join('<br>')||esc(brief(DATA.products.find(p=>p.company_id===id)?.work_performed||companies[id].description))}</p><a href="#company/${esc(id)}/products">Product evidence ${iconHTML('right')}</a>`],
 ['Customer evidence',id=>{const rows=DATA.customer_evidence.filter(r=>r.company_id===id);return rows.slice(0,2).map(r=>`<p>${esc(r.organization)} <span class="sub">${esc(title(r.relationship))} · ${claimButton(r.claim_id,'Source')}</span></p>`).join('')+`<a href="#company/${esc(id)}/customers">All relationship evidence ${iconHTML('right')}</a>`;}],
 ['Published revenue figure',comparisonRevenue],
 ['Growth',id=>{const g=STORY_GROWTH.find(g=>g.id===id);if(!g)return '<p class="sub">No reviewed full-year growth series for this company.</p>';const [a,b]=g.ids.map(id=>DATA.metrics.find(m=>m.id===id)),pct=(b.value/a.value-1)*100;return `<p>≈ ${pct>0?'+':'−'}${Math.abs(pct).toFixed(1)}% · FY2024 to FY2025</p><p class="sub">${g.scope} · USD actual revenue</p><a href="#company/${id}/growth">See yearly figures ${iconHTML('right')}</a>`;}],
 ['People',id=>{const rows=DATA.company_people.filter(p=>p.company_id===id);return `<p>${rows.slice(0,3).map(p=>`${esc(people[p.person_id].name)} <span class="sub">${esc(title(p.role))}</span>`).join('<br>')||'Not established'}</p><a href="#company/${id}/people">People & roles ${iconHTML('right')}</a>`;}],
 ['Funding & investors',id=>compactFundingSummary(id)+`<a href="#company/${id}/finance">${companies[id].entity_type==='adjacent_research'?'Research support':'Rounds & investors'} ${iconHTML('right')}</a>`],
 ['Paid work',id=>`<p>${esc(workType(id))}</p><a href="#company/${id}/work">Pay & requirements ${iconHTML('right')}</a>`],
 ['Explore',id=>`<a href="#company/${id}">Full profile & sources ${iconHTML('right')}</a>`]
 ];}
// Like with like: when another column shows a 12-month figure, a half-year or quarter
// headline gives way to the same scope's latest full year and moves to a second line.
function comparisonRevenue(id){if(financialObservationFor(id))return financialSummaryHTML(id);const m=preferredFinancial(id),period=m&&financialPeriod(m);if(!m||m.kind!=='revenue'||!['half','short'].includes(period))return compactSignal(id);const months=period==='half'?6:m.period_type==='quarter'||/quarter|three months|\bQ[1-4]\b/i.test(m.period_label||'')?3:0,span=months?months+' months':'',peers=compareIds().filter(x=>x!==id).map(x=>preferredFinancial(x)).filter(Boolean),twelve=peers.some(o=>['annualized_revenue_run_rate','arr'].includes(o.kind)||(o.kind==='revenue'&&['annual','ttm'].includes(financialPeriod(o))));const year=twelve?eligibleMetrics(id,'revenue').filter(x=>financialPeriod(x)==='annual'&&x.segment_scope===m.segment_scope&&(x.scope_detail||'')===(m.scope_detail||'')&&x.currency===m.currency).sort((a,b)=>dateRank(b.as_of).localeCompare(dateRank(a.as_of)))[0]:null;return year?signalFor(id,year)+`<p class="comparison-later"><span class="comparison-later-label">Latest ${esc(span||'shorter period')}</span>${numberButton(m)}<span class="row-period">${esc(readableDates(shortPeriod(m)))} · ${esc(compactMetricScope(m))}</span></p>`:signalFor(id,m,span);}
const MOBILE_COMPARE_PAIRS=[[0,1],[0,2],[1,2]];
function comparePairOptions(ids){return MOBILE_COMPARE_PAIRS.filter(pair=>pair.every(i=>i<ids.length));}
let comparisonFocus=null,evidenceReturnFocus=null,pendingComparisonResize=false;
document.addEventListener('focusin',event=>{comparisonFocus=$('compare-content').contains(event.target)?event.target:null;});
document.addEventListener('pointerdown',event=>{if(!$('compare-content').contains(event.target))comparisonFocus=null;});
function resizeComparison(returnFocus=null){
 const container=$('compare-content');
 // Keep the citation's opener connected until the modal closes. Its column may
 // become hidden at the new width, so restore the matching replacement then.
 if($('evidence-dialog').open&&evidenceReturnFocus?.isConnected&&container.contains(evidenceReturnFocus)){pendingComparisonResize=true;return;}
 const active=returnFocus?.isConnected?returnFocus:document.activeElement===document.body&&comparisonFocus?.isConnected?comparisonFocus:document.activeElement;
 if(!container.contains(active)){renderCompare();return;}
 const cell=active.closest('[data-comparison-company]'),row=active.closest('[data-comparison-row]'),header=active.closest('thead th'),company=cell?.dataset.comparisonCompany||active.dataset.remove||header?.querySelector('a[href^="#company/"]')?.getAttribute('href').split('/')[1];
 const identity={tag:active.tagName,claim:active.dataset.claim,remove:active.dataset.remove,href:active.getAttribute('href'),pair:active.dataset.mobileCompare,summary:active.tagName==='SUMMARY',company,row:row?.dataset.comparisonRow};
 const ids=state.selected.length?state.selected:['taskus','appen','scale_ai'],index=ids.indexOf(company),pairs=comparePairOptions(ids);
 if(window.innerWidth<=700&&index>=0&&!pairs[state.mobileCompare]?.includes(index))state.mobileCompare=pairs.findIndex(pair=>pair.includes(index));
 renderCompare();
 const scope=identity.row?[...container.querySelectorAll('[data-comparison-row]')].find(n=>n.dataset.comparisonRow===identity.row):container.querySelector('thead');
 const candidates=[...(scope||container).querySelectorAll('a,button,summary')];
 const restored=candidates.find(n=>n.getClientRects().length&&n.tagName===identity.tag&&(identity.claim?n.dataset.claim===identity.claim:identity.remove?n.dataset.remove===identity.remove:identity.href?n.getAttribute('href')===identity.href:identity.pair!==undefined?n.dataset.mobileCompare===identity.pair:identity.summary&&n.tagName==='SUMMARY'));
 const pairSummary=container.querySelector('.mobile-column-options summary');(restored||(pairSummary?.getClientRects().length?pairSummary:null)||$('compare-preset')).focus({preventScroll:true});
 const focused=document.activeElement,box=focused.getBoundingClientRect();if(box.top<0||box.bottom>window.innerHeight)focused.scrollIntoView({block:'nearest',behavior:'instant'});
}
function syncComparisonPreset(){const presets={scale:['taskus','appen','scale_ai'],work:['surge_ai','toloka','labelbox']},match=Object.keys(presets).find(key=>presets[key].join('|')===state.selected.join('|'));$('compare-preset').value=match||'';const placeholder=$('compare-preset').querySelector?.('option[value=""]');if(placeholder)placeholder.textContent=state.selected.length&&!match?'Custom selection':'Choose an example';}
// #compare/<id>/<id>/<id> names an explicit selection,
// so a comparison survives reloads, Back and Forward, and can be shared.
const COMPARE_EXAMPLE=['taskus','appen','scale_ai'];
function compareIds(){return state.selected.filter(id=>companies[id]);}
let comparisonExpanded=false;
function onCompareRoute(){return String(routeParts()[0]||'').toLowerCase()==='compare';}
function compareHash(){return '#compare'+state.selected.map(id=>'/'+id).join('');}
function compareRouteId(value){let id=String(value||'');try{id=decodeURIComponent(id);}catch{}id=id.trim().toLowerCase();const aliases=window.RESEARCH_ALIASES;return isCompanyId(id)?id:aliases&&Object.hasOwn(aliases,id)&&isCompanyId(aliases[id])?aliases[id]:'';}
// Also reads the comma form (#compare/a,b) and rewrites it to the slash form.
function syncCompareRoute(){if(!onCompareRoute())return;const parts=routeParts().slice(1).flatMap(part=>String(part).split(',')).filter(Boolean);if(parts.length){const ids=[...new Set(parts.map(compareRouteId).filter(Boolean))].slice(0,3);if(ids.length&&ids.join('|')!==state.selected.join('|')){state.selected=ids;state.mobileCompare=0;syncSelection();renderTray();}}if(location.hash!==compareHash())history.replaceState(history.state,'',compareHash());document.title=(state.selected.length?listText(state.selected.map(id=>companies[id].name))+' · ':'')+VIEW_TITLES.compare;}
function syncCompareAdd(){const select=$('compare-add'),full=state.selected.length>=3;if(!select)return;select.innerHTML=`<option value="">${full?'Remove one to add another':'Choose a company'}</option>`+[...DATA.companies].sort((a,b)=>a.name.localeCompare(b.name)).map(c=>`<option value="${esc(c.id)}"${full||state.selected.includes(c.id)?' disabled':''}>${esc(c.name)}</option>`).join('');select.value='';const add=$('compare-add-button');if(add)add.hidden=true;}
function renderCompare(){
 syncCompareRoute();syncComparisonPreset();syncCompareAdd();const ids=compareIds(),names=listText(ids.map(id=>companies[id].name));
 if(!ids.length){
  $('compare-content').innerHTML='<div class="comparison-empty"><span class="eyebrow">Build your comparison</span><h2>Which companies are you considering?</h2><p>Add up to three companies above, or start with a selection.</p><div class="comparison-starts"><button type="button" data-preset="scale">TaskUs, Appen & Scale AI</button><button type="button" data-preset="work">Surge AI, Toloka & Labelbox</button></div><p class="sub">Every figure keeps its reporting period, business scope and source.</p></div>';
  $('compare-status').textContent='No companies selected.';return;
 }
 const pairs=comparePairOptions(ids);state.mobileCompare=Math.min(state.mobileCompare,Math.max(0,pairs.length-1));const visiblePair=pairs[state.mobileCompare]||[0];
 const labels={'Main offering':'Business','Published revenue figure':'Revenue','Growth':'Revenue change'},core=['Main offering','Published revenue figure','Growth','Paid work','Explore'],extra=['Funding & investors','Products','Relationships','People'];
 const all=comparisonRows(),renderRows=order=>order.map(label=>all.find(row=>row[0]===label)).filter(Boolean).map(([label,render])=>`<tr data-comparison-row="${esc(label)}"><th scope="row">${esc(labels[label]||label)}</th>${ids.map((id,i)=>`<td data-comparison-company="${esc(id)}" class="${!visiblePair.includes(i)?'mobile-hidden':''}">${render(id)}</td>`).join('')}</tr>`).join('');
 const metrics=ids.map(preferredFinancial).filter(Boolean),bases=new Set(metrics.map(m=>[m.kind,financialPeriod(m),m.currency,m.segment_scope,m.scope_detail,m.as_of,m.gross_vs_net].join('|')));
 const context=metrics.length>1&&bases.size>1?'Reporting dates, business scopes or revenue definitions differ. Read the labels before comparing amounts.':'Figures retain the reporting period and business scope stated by their sources.';
 $('compare-content').innerHTML=`<div class="comparison-mode"><p>${ids.length} of 3 companies selected</p><button type="button" class="text-link" data-copy-compare>Copy comparison link</button></div><p class="comparison-context">${context}</p>${ids.length>2?'<p class="comparison-swipe">On small screens, use Change pair to switch companies.</p>':''}<div class="comparison-scroll"><table class="comparison-table" data-company-count="${ids.length}"><caption class="sr-only">Comparison of ${esc(names)}</caption><thead><tr><th scope="col">At a glance</th>${ids.map((id,i)=>`<th scope="col" class="${!visiblePair.includes(i)?'mobile-hidden':''}"><div class="card-head"><a href="#company/${esc(id)}">${esc(companies[id].name)}</a><button type="button" data-remove="${esc(id)}" aria-label="Remove ${esc(companies[id].name)}">${iconHTML('close')}</button></div>${i===visiblePair.at(-1)&&ids.length>2?`<details class="mobile-column-options"><summary>Change pair</summary><div class="mobile-compare-pager" role="group" aria-label="Choose companies to compare">${pairs.map((pair,i)=>`<button type="button" data-mobile-compare="${i}" aria-pressed="${i===state.mobileCompare}">${esc(companies[ids[pair[0]]].name)} + ${esc(companies[ids[pair[1]]].name)}</button>`).join('')}</div></details>`:''}</th>`).join('')}</tr></thead><tbody>${renderRows(core)}</tbody><tbody id="comparison-extra"${comparisonExpanded?'':' hidden'}>${renderRows(extra)}</tbody></table></div><button type="button" class="comparison-more" data-compare-extra aria-expanded="${comparisonExpanded}" aria-controls="comparison-extra">${comparisonExpanded?'Hide additional details':'Show funding, products, relationships & people'}</button>`;
 $('compare-status').textContent=`Comparing ${names}.`;comparisonScrollRegion();
}
// The table box becomes a focusable, named region only while it really scrolls sideways.
// The stylesheet lets the table wrap, so today it never does and keyboard users skip it.
function comparisonScrollRegion(){const box=document.querySelector('#compare-content .comparison-scroll');if(!box)return;const scrolls=typeof getComputedStyle==='function'&&/auto|scroll/.test(getComputedStyle(box).overflowX)&&box.scrollWidth>box.clientWidth+1;if(scrolls){box.setAttribute('tabindex','0');box.setAttribute('role','region');box.setAttribute('aria-label','Comparison table, scroll for more fields');}else for(const name of ['tabindex','role','aria-label'])box.removeAttribute(name);}
function copyCompareLink(button){const done=copied=>{$('compare-status').textContent=copied?'Link copied.':'Copy the address from your browser bar.';button.textContent=copied?'Link copied':'Copy link';},clip=typeof navigator==='undefined'?null:navigator.clipboard;if(!clip?.writeText)return done(false);clip.writeText(location.href).then(()=>done(true),()=>done(false));}

function evidenceMetricStatus(m){
 const estimated=m.reported_vs_estimated==='estimated',status=m.observation_status||'reported';
 if(status==='reported')return estimated?'Estimate':'Reported figure';
 if(status==='talks')return(estimated?'Estimated ':'Reported ')+(m.kind==='valuation'?'valuation talks':'talks');
 return(estimated?'Estimated ':'Reported ')+status;
}
function evidenceMetricContextHTML(m){
 const kind=m.kind==='revenue'?'Period revenue':m.kind==='other'?'':metricLabels[m.kind];
 const accounting=metricCurrentBasis(m,['revenue','annualized_revenue_run_rate','arr'].includes(m.kind)?m.gross_vs_net==='unspecified'?'Gross or net revenue not stated':title(m.gross_vs_net)+' revenue basis':'');
 const value=profileMetricValue(m)+(m.unit==='currency'&&m.currency?' '+m.currency:m.unit==='people'?' people':'');
 const scope=m.scope_detail&&!['company','ai_data','research','other_segment'].includes(m.scope_detail)?m.scope_detail:scopeText(m.segment_scope,m.company_id);
 return `<div class="evidence-metric-context" data-evidence-metric="${esc(m.id)}"><div class="evidence-metric-heading"><strong>${esc(profileSentenceCase(metricPresentationLabel(m,m.label||metricLabels[m.kind])))}</strong><span class="evidence-metric-value">${esc(value)}</span></div><p>${[kind,evidenceMetricStatus(m),profileMetricHistory(m),scope,profileMetricDate(m),accounting].filter(Boolean).map(esc).join(' · ')}</p></div>`;
}
// Grade meanings, as the Method page states them.
const CONFIDENCE_GRADES={A:'Independent or buyer-side evidence, such as a filing or a customer who confirms the work.',B:'The company, an investor or another named first-hand source says it.',C:'Reporting by others, an estimate, or indirect evidence.',U:'Not confirmed. The fact may be undisclosed or still unresolved.'};
function claimConfidenceHTML(cl){
 const inheritedIndependentReason='Independent or buyer-side evidence. Research label: researcher-assigned evidence grade.';
 const attribution=evidenceLabel(cl);
 let reason=cl.confidence_reason;
 if(cl.confidence==='A'&&reason===inheritedIndependentReason){
  if(['Company-reported','Investor-reported'].includes(attribution))reason=attribution+' evidence. The research confidence grade is retained from the compiled snapshot.';
  else if(!cl.evidence_label&&['Transaction counsel statement','University incubator statement','Company admission document'].includes(attribution))reason=attribution+'. The research confidence grade is retained from the compiled snapshot.';
 }
 // Drop the researcher-only "Research label" note; show the reason only when it adds to the grade.
 reason=String(reason||'').replace(/\s*Research label:[^.]*\.?\s*$/,'').trim();
 const meaning=CONFIDENCE_GRADES[cl.confidence]||'',plain=text=>publicText(text).replace(/[.\s]+$/,'').toLowerCase();
 return `<div class="claim-confidence"><strong>Confidence grade</strong>${esc(cl.confidence)}${meaning?`<span class="sub">${esc(meaning)}</span>`:''}${reason&&!plain(meaning).startsWith(plain(reason))?`<details><summary>Why this grade</summary><p class="sub">${esc(reason)}</p></details>`:''}</div>`;
}
// Display wording for common research date notes (records unchanged).
const EVIDENCE_DATE_NOTES={
 'Date label preserved from research; access dates are not substituted.':'This date comes from the source. We did not swap in the date we checked it.',
 'The observation date is October 14. An undated page is not assigned a synthetic publication date.':'We read this source on 14 Oct 2026. When a page shows no date, we do not make one up.',
 'Review date is not substituted for an unknown publication, closing or milestone date.':'When a publication, closing or milestone date is unknown, we leave it unknown. We do not use the date we checked the source.'
};
let evidenceRecordHash='',evidenceReturnHash='';
// Record links: #company/<id>/claim/<claim-id> opens the profile with this dialog.
function evidenceRecordLink(cl){return '#company/'+encodeURIComponent(cl.company_id)+'/claim/'+encodeURIComponent(cl.id);}
function showEvidence(id,group=[]){
 const cl=claims[id];if(!cl)return;
 const dialog=$('evidence-dialog');if(!dialog.open){evidenceReturnFocus=document.activeElement;evidenceReturnHash='';evidenceRecordHash='';}
 const ms=DATA.metrics.filter(m=>m.claim_id===id),scope=[...new Set([scopeText(cl.segment_scope,cl.company_id),...(evidenceMetricScopes.get(id)||[])])].join(' · '),link=evidenceRecordLink(cl),others=group.filter(other=>other!==id&&claims[other]);
 $('evidence-content').innerHTML=`${ms.map(evidenceMetricContextHTML).join('')}${typeof sourceUpdateClaimHTML==='function'?sourceUpdateClaimHTML(id):''}${evidenceContextClaimHTML(id)}${evidenceContextStatementHeadingHTML(cl)}<p class="evidence-statement" id="evidence-statement">${esc(cl.statement)}</p><h3>Sources</h3><ol class="sources-list">${cl.source_ids.map(sid=>{const s=sources[sid];return `<li>${external(s.url,s.title)}<p class="sub">${esc(profileSourceMeta(s))}</p>${s.notes?`<p class="sub">${esc(readableDate(publicText(s.notes.replaceAll('_',' '))))}</p>`:''}</li>`;}).join('')}</ol>${!cl.source_ids.length?'<p>No current source is linked to this claim.</p>':''}${historicalSourceHTML(cl)}<div class="evidence-data"><div><strong>${esc(evidenceContextDateHeading(cl))}</strong>${esc(profileDate(cl.as_of))}</div><div><strong>Checked</strong>${esc(profileDate(cl.observed_on))}</div>${evidenceContextScopeHTML(cl,scope)}<div><strong>Evidence label</strong>${esc(profileEvidenceLabel(cl))}</div><div><strong>Status</strong>${esc(title(cl.status))}</div>${claimConfidenceHTML(cl)}</div>${cl.date_note?`<p class="sub">${esc(EVIDENCE_DATE_NOTES[cl.date_note]||cl.date_note)}</p>`:''}${[...new Set([cl.caveat,...ms.map(m=>m.basis)].map(publicText))].filter(t=>t&&!publicText(cl.statement).includes(t)).map(t=>`<p class="sub">${esc(t)}</p>`).join('')}${others.length?`<h3>Other claims for this item</h3><ul class="evidence-related">${others.map(other=>`<li><button type="button" class="evidence-action" data-profile-evidence="${attr([other,...group.filter(x=>x!==other)].join('|'))}">Claim ${group.indexOf(other)+1} of ${group.length}: ${esc(profileEvidenceLabel(claims[other]))}</button></li>`).join('')}</ul>`:''}<div class="evidence-actions"><button type="button" class="evidence-copy" data-copy-record="${attr(link)}">${iconHTML('link')} Copy link to this record</button><p class="sub" id="evidence-copy-status" role="status"></p><p class="evidence-correction">Something wrong here? <a href="#corrections">Request a correction ${iconHTML('right')}</a></p></div>`;
 // On the claim's profile the address bar shows the record link while open.
 const parts=routeParts(),company=String(parts[0]).toLowerCase()==='company'?profileRouteCompany(parts[1]):'';
 if(company&&company===cl.company_id&&!$('profile-view').hidden){if(!evidenceReturnHash)evidenceReturnHash=parts[2]==='claim'?profileTabHash(company):location.hash;if(location.hash!==link)history.replaceState(history.state??null,'',link);evidenceRecordHash=link;}
 if(!dialog.open)dialog.showModal();dialog.scrollTop=0;$('close-evidence').focus({preventScroll:true});
}
$('evidence-dialog').addEventListener('close',()=>{
 const opener=evidenceReturnFocus,resize=pendingComparisonResize,record=evidenceRecordHash,back=evidenceReturnHash;
 evidenceReturnFocus=null;pendingComparisonResize=false;evidenceRecordHash='';evidenceReturnHash='';
 // Restore the profile address unless navigation closed the dialog.
 if(record&&location.hash===record){history.replaceState(history.state??null,'',back);if(!opener?.isConnected||opener===document.body){const heading=document.querySelector('#profile-view:not([hidden]) h1');heading?.setAttribute('tabindex','-1');heading?.focus({preventScroll:true});}}
 if(resize&&onCompareRoute()&&!$('compare-view').hidden)resizeComparison(opener);
});

function storyUnknown(id){const original=unknownFor(id)?.statement||assessmentFor(id)?.stage_limitations||'Current commercial economics are not publicly established.',current=typeof sourceUpdateUnknownText==='function'?sourceUpdateUnknownText(id,original):original,text=publicText(current).split(/[.;]/)[0];const words=text.split(/\s+/);return words.slice(0,18).join(' ')+(words.length>18?'…':'.');}
const SELECTION_OFFERING_COPY={
 datacurve:{name:'RL environments',record:'datacurve.product.oct14-0',claim:'datacurve.claim.oct14-product-0',source:'datacurve.source.oct14-a5da84956a24',url:'https://datacurve.ai/products'},
 abundant_ai:{name:'Custom RL environments and datasets',record:'abundant_ai.product.oct14-0',claim:'abundant_ai.claim.oct14-product-0',source:'abundant_ai.source.oct14-8fcc746dfc96',url:'https://www.abundant.ai/'}
};
function selectionOfferingName(id,product){
 const expected=Object.hasOwn(SELECTION_OFFERING_COPY,id)?SELECTION_OFFERING_COPY[id]:null;
 if(!expected||product.name!==expected.name||product.record_ids?.length!==1||product.record_ids[0]!==expected.record||product.claim_ids?.length!==1||product.claim_ids[0]!==expected.claim)return product.name;
 const record=DATA.products.find(row=>row.id===expected.record),claim=claims[expected.claim],source=sources[expected.source];
 if(record?.company_id!==id||record.name!==expected.name||record.claim_id!==expected.claim||claim?.company_id!==id||claim.status!=='supported'||claim.source_ids?.length!==1||claim.source_ids[0]!==expected.source||source?.company_id!==id||source.url!==expected.url)return product.name;
 return publicOfferingName(product.name);
}
function selectionFact(id){
 if(preferredFinancial(id))return compactSignal(id);
 const supported=ids=>(ids||[]).filter(cid=>claims[cid]?.status==='supported');
 const reference=(ids,label)=>typeof profileReferences==='function'?profileReferences(ids,label,label):claimButton(ids[0],label,label);
 const rows=typeof profileRelationships==='function'?profileRelationships(id):DATA.customer_evidence.filter(r=>r.company_id===id).map(r=>({name:r.organization,relationship:r.relationship,claim_ids:[r.claim_id]}));
 const relationship=rows.find(r=>r.name&&r.name.length<=75&&!/[:;]|unnamed|undisclosed|anonymous|no named|not (?:named|disclosed|established)|no verified|unverified customer/i.test(r.name)&&supported(r.claim_ids).length);
 if(relationship){const ids=supported(relationship.claim_ids),cl=claims[ids[0]],label=typeof profileRelationshipLabel==='function'?profileRelationshipLabel(id,relationship):typeof relationshipLabel==='function'?relationshipLabel(relationship.relationship):title(relationship.relationship);return `<div class="row-number">${reference(ids,relationship.name)}</div><span class="row-period">${esc(label)} · ${esc(dateText(cl.as_of))} · ${esc(evidenceContextScopeLabel(cl,scopeText(cl.segment_scope,id)))}</span>`;}
 const products=typeof profileProducts==='function'?profileProducts(id):DATA.products.filter(p=>p.company_id===id).map(p=>({name:p.name,claim_ids:[p.claim_id]}));
 const product=products.find(p=>p.name&&supported(p.claim_ids).length);
 if(product){
  const label=companies[id].entity_type==='adjacent_research'?'Research offering':'Offering';
  if(product.source_updates?.length)return `<div class="row-number">${productSourceHTML(product,product.name)}</div><span class="row-period">${label}${product.status?' · '+esc(title(product.status)):''}</span>`;
  const ids=supported(product.claim_ids),cl=claims[ids[0]];return `<div class="row-number">${reference(ids,selectionOfferingName(id,product))}</div><span class="row-period">${label}${product.status?' · '+esc(title(product.status)):''} · ${esc(dateText(cl.as_of))} · ${esc(scopeText(cl.segment_scope,id))}</span>`;
 }
 return compactSignal(id);
}
function openCompanyStory(id){if(!isCompanyId(id))return;const c=companies[id];const ed=editorialFor(id);$('company-story').innerHTML=`<p class="eyebrow">${esc(groupLabel(modelGroup(id)))}</p><h2 id="company-story-title">${esc(c.name)}</h2><p class="selection-description">${esc(modelFor(id))}</p><div class="selection-metric">${selectionFact(id)}</div><p class="selection-unknown"><span>Still unclear</span>${esc(storyUnknown(id))}</p><div class="selection-actions">${claimButton(ed?.claim_id||c.identity_claim_id,'Sources')}<a class="full-profile-link" href="#company/${esc(id)}" data-full-profile>Full profile ${iconHTML('right')}</a></div>`;$('company-dialog').showModal();}

function renderTray(){const n=state.selected.length;$('compare-tray').hidden=!n||onCompareRoute();$('tray-text').textContent=n?`${n} of 3 selected: ${listText(state.selected.map(id=>companies[id].name))}`:'';$('nav-count').textContent=n?`(${n})`:'';document.querySelectorAll('[data-nav="compare"],#compare-tray a[href^="#compare"]').forEach(a=>a.setAttribute('href',compareHash()));}
function syncSelection(){document.querySelectorAll('[data-compare]').forEach(el=>el.checked=state.selected.includes(el.dataset.compare));}
// On the compare page the URL follows the selection; replaceState keeps Back history short.
function setSelection(ids){state.selected=[...new Set(ids)].filter(isCompanyId).slice(0,3);state.mobileCompare=Math.min(state.mobileCompare,Math.max(0,comparePairOptions(state.selected).length-1));syncSelection();renderTray();if(onCompareRoute()&&location.hash!==compareHash())history.replaceState(history.state,'',compareHash());renderCompare();}
function chooseCompare(id,on){if(on&&!state.selected.includes(id)&&state.selected.length>=3){syncSelection();$('tray-text').textContent='Three selected. Remove one to add another.';return;}setSelection(on?[...state.selected,id]:state.selected.filter(x=>x!==id));}
function reset(){Object.assign(state,{query:'',category:'',stage:'',financial:false,work:false,sort:'name'});$('search').value='';$('category').value='';$('stage').value='';$('financial-only').checked=false;$('work-only').checked=false;$('sort').value='name';renderDirectory();writeDirectoryRoute();$('search').focus({preventScroll:true});}

// previousSection is set after a section link such as #venture, so the next plain view link starts at the top.
let previousRoute='',previousSection='';const viewScroll={};
let companyReturnFocus=null;
// Hashes that name a place inside a page. route() shows that page, then brings the element to the top with focus.
const VIEW_ANCHORS={venture:'market',about:'method',labels:'method',corrections:'method',coverage:'method',downloads:'method'};
function viewAnchorId(hash=location.hash){const id=String(routeParts(hash)[0]||'').toLowerCase();return Object.hasOwn(VIEW_ANCHORS,id)?id:'';}
function showViewAnchor(target){
 if(!target)return;
 for(let node=target;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
 if(!target.matches?.('a[href],button,input,select,textarea,summary'))target.setAttribute('tabindex','-1');
 target.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'instant'});
}
// Back and Forward return each history entry to where the reader left it. The Navigation API
// says which entry is which and when a move is a traversal; other browsers keep the old behavior.
const entryScroll=new Map();let routeTraversal=false;
const historyKey=()=>window.navigation?.currentEntry?.key;
if(window.navigation&&'scrollRestoration' in history)history.scrollRestoration='manual';
// A reload, or Back to this page from another site, also returns to the same place: the entry keeps
// its scroll position as Navigation API state, which route() reads on its first run.
let entryScrollTimer=0;
const keepEntryScroll=()=>{clearTimeout(entryScrollTimer);try{window.navigation.updateCurrentEntry({state:{scrollY:window.scrollY}});}catch{}};
if(window.navigation)window.addEventListener('scroll',()=>{clearTimeout(entryScrollTimer);entryScrollTimer=setTimeout(keepEntryScroll,300);},{passive:true});
// Without the Navigation API, history.state carries the same scroll position so a reload can restore it.
if(!window.navigation)window.addEventListener('scroll',()=>{clearTimeout(entryScrollTimer);entryScrollTimer=setTimeout(()=>{try{history.replaceState({...(history.state||{}),scrollY:window.scrollY},'');}catch{}},300);},{passive:true});
// An in-page link saves the position at once, before the new entry exists. So an entry the reader left by a link
// always has one, and a new entry has none until the reader scrolls it (profiles-v2.js reads that).
if(!window.navigation)document.addEventListener('click',e=>{if(!e.target?.closest?.('a[href^="#"]'))return;clearTimeout(entryScrollTimer);try{history.replaceState({...(history.state||{}),scrollY:window.scrollY},'');}catch{}},true);
// history.replaceState() from any page script clears that state, so keep the position again afterwards.
window.navigation?.addEventListener('currententrychange',event=>{if(event.navigationType==='replace')keepEntryScroll();});
window.navigation?.addEventListener('navigate',event=>{if(event.navigationType==='replace')return;keepEntryScroll();const key=historyKey();if(key)entryScroll.set(key,window.scrollY);routeTraversal=event.destination.sameDocument&&event.navigationType==='traverse';});
// Hidden pages are set up the first time they open; idle time fills in their filters and method
// text. The overview and the company cards render on first visit only. The Node test stub has no
// requestIdleCallback or requestAnimationFrame, so there initialize() sets everything up at once,
// in the original order.
const PAGE_SETUP={};let directoryShown=false;
function preparePage(view){const steps=PAGE_SETUP[view];while(steps?.length)steps.shift()();}
function showDirectory(){if(!directoryShown)renderDirectory();}
function normalSelfLinkActivation(event,link){
 return Boolean(link&&!event.defaultPrevented&&!event.metaKey&&!event.ctrlKey&&!event.shiftKey&&!event.altKey&&(event.button===undefined||event.button===0)&&!link.hasAttribute('download')&&(!link.getAttribute('target')||link.getAttribute('target')==='_self'));
}
function rememberCompanyOrigin(event){
 if(event.defaultPrevented||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||(event.button!==undefined&&event.button!==0))return;
 const origin=event.target.closest?.('#company-cards a[href^="#company/"],#company-cards [data-open-company]');
 if(!origin||(origin.tagName==='A'&&!normalSelfLinkActivation(event,origin)))return;
 // The logo link is out of the tab order, so Back returns focus to the card's name link instead.
 companyReturnFocus=origin.matches('.company-brand')?origin.closest('[data-company-card]')?.querySelector('h3 a')||origin:origin;
}
function companyReturnFocusTarget(){
 const origin=companyReturnFocus;
 if(!origin?.isConnected||origin.closest('[hidden]')||!origin.getClientRects().length){companyReturnFocus=null;return null;}
 const box=origin.getBoundingClientRect();
 if(box.bottom<=0||box.top>=window.innerHeight||box.right<=0||box.left>=window.innerWidth){companyReturnFocus=null;return null;}
 return origin;
}
function focusRouteDestination(hash){
 const anchorId=viewAnchorId(hash);if(anchorId){showViewAnchor($(anchorId));return;}
 const parts=routeParts(hash),section=profileRouteSection(parts[2]),primary=['business','traction','people','work'].includes(section);
 const companyOrigin=String(parts[0]||'').toLowerCase()==='companies'?companyReturnFocusTarget():null;
 if(companyOrigin){companyOrigin.focus({preventScroll:true});return;}
 const workLink=parts[0]==='work'&&typeof workReturnFocusTarget==='function'?workReturnFocusTarget():null;
 if(workLink){workLink.focus({preventScroll:true});return;}
 const destination=parts[0]==='company'&&isCompanyId(parts[1])?profileRouteDestination(section):null;
 const target=destination?.tagName==='DETAILS'?destination.querySelector('summary'):destination||document.querySelector('.view:not([hidden]) h1');
 for(let node=destination;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
 if(target&&target.tagName!=='SUMMARY')target.setAttribute('tabindex','-1');
 target?.focus({preventScroll:true});
 (destination&&primary?document.querySelector('.profile-tabs'):destination||target)?.scrollIntoView({block:'start',behavior:'instant'});
}
function repeatCompanyRoute(event){
 if(event.defaultPrevented||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||(event.button!==undefined&&event.button!==0))return;
 const link=event.target.closest?.('a[href]'),hash=link?.getAttribute('href');
 if(!hash?.startsWith('#company/')||hash!==location.hash||link.hasAttribute('download')||(link.getAttribute('target')&&link.getAttribute('target')!=='_self'))return;
 if(link.hasAttribute('data-full-profile'))$('company-dialog').close();
 event.preventDefault();route({type:'hashchange'});
}
function repeatMainRoute(event){
 const link=event.target.closest?.('a[href]'),hash=link?.getAttribute('href');
 const sameView=['#companies','#compare'].includes(hash)&&'#'+String(routeParts()[0]||'').toLowerCase()===hash;
 if(!normalSelfLinkActivation(event,link)||(hash!==location.hash&&!sameView))return;
 const anchorId=viewAnchorId(hash);if(anchorId){event.preventDefault();showViewAnchor($(anchorId));return;}
 if(!['market','companies','compare','work','method'].includes(routeParts(hash)[0]))return;
 event.preventDefault();
 if(hash==='#companies')companyReturnFocus=null;
 if(hash==='#work'&&typeof workReturnFocus!=='undefined')workReturnFocus=null;
 const heading=document.querySelector('.view:not([hidden]) h1');
 if(heading){heading.setAttribute('tabindex','-1');heading.focus({preventScroll:true});heading.scrollIntoView({block:'start',behavior:'instant'});}
}
document.addEventListener('click',rememberCompanyOrigin);
document.addEventListener('click',repeatCompanyRoute);
document.addEventListener('click',repeatMainRoute);
// Grouped profile citations can also appear in a quick summary. Close that
// modal before the profile module opens its evidence dialog.
document.addEventListener('click',event=>{if(event.target.closest?.('[data-profile-evidence]')&&$('company-dialog').open)$('company-dialog').close();});
function route(event){document.documentElement?.removeAttribute?.('data-route');document.documentElement?.style?.removeProperty?.('scroll-behavior');const key=historyKey(),kept=previousRoute===''?(window.navigation?window.navigation.currentEntry?.getState?.()?.scrollY:history.state?.scrollY):null,saved=typeof kept==='number'?kept:null,restore=routeTraversal&&entryScroll.has(key)?entryScroll.get(key):saved;routeTraversal=false;const closingDialog=event?.type==='hashchange'&&['company-dialog','evidence-dialog'].some(id=>$(id).open);if(event?.type==='hashchange')for(const id of ['company-dialog','evidence-dialog'])if($(id).open)$(id).close();const parts=routeParts(),aliases=window.RESEARCH_ALIASES;parts[0]=String(parts[0]||'').toLowerCase();if(parts[0]==='company'&&parts[1]){const lower=String(parts[1]).toLowerCase();if(lower!==parts[1]&&(isCompanyId(lower)||(aliases&&Object.hasOwn(aliases,lower))))parts[1]=lower;}if(parts[0]==='company'&&aliases&&Object.hasOwn(aliases,parts[1])&&isCompanyId(aliases[parts[1]]))parts[1]=aliases[parts[1]];if(parts[0]==='company'&&isCompanyId(parts[1])){const hash='#'+parts.map(encodeURIComponent).join('/');if(location.hash.split('?')[0]!==hash)history.replaceState(history.state,'',hash+(location.hash.match(/\?.*$/)?.[0]||''));}const anchorId=Object.hasOwn(VIEW_ANCHORS,parts[0])?parts[0]:'',view=anchorId?VIEW_ANCHORS[anchorId]:['market','companies','work','compare','method','company'].includes(parts[0])?parts[0]:'market';if(parts[0]&&parts[0]!=='market'&&view==='market'&&!anchorId)history.replaceState(null,'','#market');if(view!=='company')preparePage(view);if(previousRoute&&view!==previousRoute)viewScroll[previousRoute]=window.scrollY;for(const name of ['market','companies','work','compare','method','profile'])$(name+'-view').hidden=(name!==(view==='company'?'profile':view));document.querySelectorAll('[data-nav]').forEach(a=>{if(a.dataset.nav===(view==='company'?'companies':view))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});if(view==='company'){if(isCompanyId(parts[1])){renderCompanyProfile(parts[1]);document.title=companies[parts[1]].name+' · ScienceToStartup';}else{document.title='Profile not found · ScienceToStartup';$('profile-view').innerHTML='<div class="page-heading"><h1>Profile not found</h1><p>No company in this guide uses that address.</p><a href="#companies">Browse the companies</a></div>';}}
 else{document.title=VIEW_TITLES[view];if(view==='companies'){if(typeof syncDirectoryRoute==='function')syncDirectoryRoute(parts.slice(1));showDirectory();}if(view==='method')showDirectory();if(view==='work'&&!workViewRendered)renderWork();if(view==='compare')renderCompare();}
 renderTray();const section=profileRouteSection(parts[2]),anchor=view==='company'&&section?$('profile-'+section):null;if(anchorId)showViewAnchor($(anchorId));if(restore!==null){const back=()=>window.scrollTo({left:0,top:restore,behavior:'instant'});back();queueMicrotask(back);}else if(!anchorId){if(anchor){let p=anchor;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}anchor.scrollIntoView({block:'start',behavior:'instant'});}else if(previousRoute&&(view!==previousRoute||previousSection))window.scrollTo({left:0,top:view!==previousRoute&&['market','companies','work'].includes(view)?viewScroll[view]||0:0,behavior:'instant'});}previousRoute=view;previousSection=anchorId;if(closingDialog){const hash=location.hash;requestAnimationFrame(()=>{if(location.hash!==hash)return;focusRouteDestination(hash);});}}
function download(name,body,type){const url=URL.createObjectURL(new Blob([body],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csvCell(v){let s=String(v??'');if(/^[\t\r\n]/.test(s)||/^\s*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
// The CSV starts with a byte order mark, so spreadsheet software such as Excel reads it as UTF-8.
function exportCsv(){const head=['company_id','company','business_model','delivery_evidence','assessment_scope','financial_metric','financial_value','financial_qualifier','financial_display','upper_value','observation_status','currency','metric_date','metric_period','metric_scope','scope_detail','accounting_basis','financial_source_urls','work_route','readout','snapshot_as_of'];const rows=filtered().map(c=>{const m=preferredFinancial(c.id);return[c.id,c.name,modelFor(c.id),stageLabel(stageFor(c.id)),assessmentFor(c.id)?.segment_scope||'',m?.kind||'',m?.value??'',m?.qualifier||'',m?metricValue(m):'',m?.upper_value??'',m?.observation_status||'',m?.currency||'',m?.as_of||'',m?.period_label||'',m?.segment_scope||'',m?.scope_detail||'',m?.gross_vs_net||'',m?claims[m.claim_id].source_ids.map(id=>sources[id].url).join(' | '):'',workType(c.id),publicText(editorialFor(c.id)?.readout||''),DATA.meta.as_of];});download('observatory-company-comparison.csv','﻿'+[head,...rows].map(r=>r.map(csvCell).join(',')).join('\r\n')+'\r\n','text/csv;charset=utf-8');}

// Editorial views of existing reviewed records; no research data is modified.
const STORY_GROWTH=[
 {id:'taskus',name:'TaskUs',scope:'AI Services',ids:['taskus.metric.expansion-3','taskus.metric.expansion-2'],color:'var(--green)'},
 {id:'appen',name:'Appen',scope:'Whole company',ids:['appen.metric.major-financial_metrics-1','appen.metric.major-financial_metrics-2'],color:'var(--muted)'}
];
const STORY_MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],STORY_NUMBER_WORDS=['No','One','Two','Three','Four','Five','Six','Seven','Eight','Nine','Ten'];
// Reader-facing dates: 2026-06 becomes Jun 2026 and 2026-10-12 becomes 12 Oct 2026.
function storyDate(value){return String(value??'').replace(/\b(\d{4})-(\d{2})(?:-(\d{2}))?\b/g,(all,y,m,d)=>STORY_MONTHS[m-1]?`${d?Number(d)+' ':''}${STORY_MONTHS[m-1]} ${y}`:all);}
// "on 15 Oct 2026", "on 16 and 17 Oct 2026" or "between 12 and 15 Oct 2026", from ISO dates.
function storyDateRange(values){const dates=[...new Set(values.filter(Boolean))].sort(),first=dates[0],last=dates.at(-1);if(!first)return '';const a=storyDate(first),b=storyDate(last);if(first===last)return 'on '+b;const word=dates.length===2?'on':'between';return a.split(' ').slice(1).join(' ')===b.split(' ').slice(1).join(' ')?`${word} ${a.split(' ')[0]} and ${b}`:`${word} ${a} and ${b}`;}
function shortPeriod(m){const corrected=metricCurrentPeriod(m);if(corrected)return corrected;const s=m.period_label||m.as_of;return /FY ended (\d{4})/.test(s)?'FY'+s.match(/FY ended (\d{4})/)[1]:storyDate(s);}
// Paid work on the overview: counts, freshness and a safety line. It names no single listing.
// The paid work listings follow the Paid work page: its contract and job buckets when they exist, otherwise its main group.
// Cards keep their own availability labels, so the count does not call these listings open.
function storyWorkRows(){const rows=typeof workRouteRows==='function'?workRouteRows():[];if(typeof w4Bucket==='function'){const paid=rows.filter(r=>['contract','jobs'].includes(w4Bucket(r)));if(paid.length)return paid;}return typeof w4RouteGroups==='function'?w4RouteGroups(rows).primary:[];}
function renderStoryWork(){const rows=storyWorkRows(),box=$('overview-work');if(!box||!rows.length)return;const count=new Set(rows.map(r=>r.company_id)).size,paid=rows.filter(r=>r.numeric_pay).length,contract=rows.filter(r=>typeof w4Bucket==='function'?w4Bucket(r)==='contract':['Expert & contractor projects','Contributor bounties'].includes(r.group)).length,jobs=rows.filter(r=>typeof w4Bucket==='function'?w4Bucket(r)==='jobs':['Employment','Research fellowship'].includes(r.group)).length,range=storyDateRange(rows.map(r=>[r.reviewed_on,typeof w4Checked==='function'?w4Checked(r):null].filter(Boolean).sort().at(-1)));
 $('hero-work-count').textContent=rows.length;$('hero-work-stat')?.removeAttribute('data-pending');
 box.innerHTML=`<p class="overview-stats"><span><b>${rows.length}</b> paid work listings</span><span><b>${count}</b> companies</span><span><b>${paid}</b> show a pay amount</span></p><p>${contract+jobs===rows.length?`Of these, ${contract} are contract or task work and ${jobs} are jobs or fellowships. `:''}${range?`We reviewed every listing ${range}.`:''}</p><p class="overview-safety"><strong>Before you apply:</strong> never pay to get work, and be careful with job offers that come out of the blue from a stranger. <a href="https://consumer.ftc.gov/articles/job-scams" target="_blank" rel="noopener noreferrer">How to spot a job scam ${iconHTML('external')}<span class="sr-only"> (opens in a new tab)</span></a></p>`;
}
// How we check: grade mix, source mix and later corrections, all counted from the loaded data.
function renderStoryCheck(){const box=$('overview-check');if(!box)return;const current=DATA.claims.filter(c=>c.status!=='superseded'),grades=['A','B','C','U'].map(g=>[g,current.filter(c=>c.confidence===g).length]),open=current.filter(c=>c.subject==='unknowns'&&c.confidence==='U').length,own=DATA.sources.filter(s=>s.source_type==='company').length,pages=new Set(DATA.sources.map(s=>s.url)).size,updates=window.SOURCE_UPDATES||{},fixes=[...(updates.updates||[]).map(u=>[u.company_id,u.source?.observed_on]),...(updates.evidence_context?.corrections||[]).map(u=>[u.company_id,u.reviewed_on])],when=storyDateRange(fixes.map(f=>f[1])),n=v=>v.toLocaleString('en-US');
 box.innerHTML=`<div class="check-item"><h3>Confidence grades</h3><p><b>${n(current.length)}</b> current claims, by grade</p><div class="grade-bar" aria-hidden="true">${grades.map(([g,c])=>`<span data-grade="${g}" style="flex-grow:${c}"></span>`).join('')}</div><ul class="grade-counts">${grades.map(([g,c])=>`<li><span class="story-grade" data-grade="${g}"><span class="sr-only">Grade </span>${g}</span> ${n(c)}<span class="sr-only"> claims</span></li>`).join('')}</ul><p class="sub">U includes ${n(open)} open questions, such as figures a company has not disclosed. ${n(DATA.claims.length-current.length)} earlier versions stay on file.</p></div><div class="check-item"><h3>Sources</h3><p><b>${n(DATA.sources.length)}</b> source records point to <b>${n(pages)}</b> distinct web pages. <b>${n(own)}</b> of the records come from the companies themselves.</p><p><a href="#downloads">Download the data ${iconHTML('right')}</a></p></div><div class="check-item"><h3>Corrections</h3><p>${fixes.length?`<b>${n((updates.updates||[]).length)}</b> corrections from later sources${(updates.evidence_context?.corrections||[]).length?` and <b>${n(updates.evidence_context.corrections.length)}</b> clarifications of existing records`:''} ${when}, for <b>${n(new Set(fixes.map(f=>f[0])).size)}</b> companies. `:''}We review reported errors within seven days.</p><p><a href="#corrections">Request a correction ${iconHTML('right')}</a></p></div>`;
}
function renderStory(){$('organization-count').textContent=DATA.companies.length;$('group-count').textContent=Object.keys(MODEL_GROUPS).length;document.querySelectorAll('[data-company-count]').forEach(node=>{node.textContent=DATA.companies.length;});const nonprofit=(MODEL_GROUPS['Nonprofit research']||[]).length;if($('nonprofit-count'))$('nonprofit-count').textContent=STORY_NUMBER_WORDS[nonprofit]||nonprofit;$('hero-snapshot').textContent=window.BUSINESS_HEALTH?.source_checks?.checked_on?'Selected sources checked '+storyDate(window.BUSINESS_HEALTH.source_checks.checked_on):compiledSnapshotLabel(DATA.meta.as_of);if(!DATA.companies.some(c=>Object.values(MODEL_GROUPS).flat().includes(c.id)))return;const mercor=preferredFinancial('mercor'),sentence=s=>s&&!/[.!?]$/.test(s)?s+'.':s;if(mercor)$('venture-mercor').textContent=[`The latest is ${metricValue(mercor)} for ${metricCurrentPeriod(mercor,storyDate(dateText(mercor.as_of)))}.`,sentence(metricCurrentAttribution(mercor,evidenceLabel(claims[mercor.claim_id]))),metricCurrentBasisDescription(mercor,'')].filter(Boolean).join(' ');if(window.BusinessHealth)window.BusinessHealth.render();renderModelMap();renderStoryWork();renderStoryCheck();}

function compactMetricScope(m){
 if(m.company_id==='imerit'&&m.scope_detail==='iMerit standalone acquired business')return 'iMerit standalone business';
 return m.company_id==='taskus'?'AI Services':scopeText(m.segment_scope,m.company_id);
}
const SHORT_MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
// Dates in running text read "17 May 2022" or "Jun 2026". Other text is left as it is.
function readableDates(text){return String(text??'').replace(/\b((?:19|20)\d{2})-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?\b(?![-\d])/g,(all,year,month,day)=>(day?Number(day)+' ':'')+SHORT_MONTHS[month-1]+' '+year);}
function monthSpan(dates){const months=[...new Set(dates.map(d=>String(d).slice(0,7)))].sort(),first=months[0],last=months.at(-1);return first===last?readableDates(first):first.slice(0,4)===last.slice(0,4)?SHORT_MONTHS[first.slice(5)-1]+'–'+SHORT_MONTHS[last.slice(5)-1]+' '+first.slice(0,4):readableDates(first)+' to '+readableDates(last);}
function listText(names){return names.length<3?names.join(' and '):names.slice(0,-1).join(', ')+' and '+names.at(-1);}
// The same supplemental observation drives cards, profiles and Compare.
function financialObservationFor(id){
 const health=window.BUSINESS_HEALTH;if(!health)return null;
 const candidates=(health.observations||[]).filter(o=>o.company_id===id&&o.signal==='revenue'&&['period_revenue','annualized_revenue'].includes(o.measure)&&typeof o.value==='number'&&Number.isFinite(o.value)&&!o.is_context&&o.evidence_type==='reported');
 const scopes=['company','ai_data','other_segment','parent'];
 const end=o=>o.period?.end||(String(o.as_of||'').match(/\d{4}(?:-\d{2}){0,2}/)||[''])[0];
 const scopeRank=o=>{const rank=scopes.indexOf(o.scope);return rank<0?scopes.length:rank;};
 const recent=candidates.filter(o=>end(o)>='2025-10-28');
 return (recent.length?recent:candidates).sort((a,b)=>scopeRank(a)-scopeRank(b)||Number(b.measure==='period_revenue')-Number(a.measure==='period_revenue')||end(b).localeCompare(end(a)))[0]||null;
}
function financialSummaryHTML(id){
 const o=financialObservationFor(id);if(!o)return signalFor(id,preferredFinancial(id));
 const health=window.BUSINESS_HEALTH,record=(health.sources||[]).find(s=>o.source_ids.includes(s.id))||sources[o.source_ids[0]],fresh=(health.fresh_claims||[]).find(c=>o.claim_ids.includes(c.id));
 const value=window.BusinessHealth?.valueText(o)||String(o.value),period=o.period?.label||o.as_of,scope=o.scope_label||scopeText(o.scope,id),basis=o.accounting_basis==='gross'?'Gross revenue':o.accounting_basis==='net'?'Net revenue':o.measure==='annualized_revenue'?'Gross/net not disclosed':'',type=o.measure==='annualized_revenue'?'Annualized pace':'Revenue';
 const checked=fresh?.observed_on||(health.source_checks?.entries||[]).find(e=>o.source_ids.includes(e.source_id)&&e.status==='content_checked')?.checked_on;
 const end=o.period?.end||(String(o.as_of||'').match(/\d{4}(?:-\d{2}){0,2}/)||[''])[0],old=!end||end<'2025-10-28';
 const citation=record?external(record.url,record.publisher||'Original source'):'';
 const quote=o.original_text||fresh?.excerpt||'';
 const failed=o.refresh_status==='source_unavailable'||(health.source_checks?.entries||[]).some(e=>o.source_ids.includes(e.source_id)&&e.status==='unavailable');
 const warning=failed?'<p class="financial-source-warning">Original citation could not be rechecked. Historical source attribution retained.</p>':'';
 const observationAttr=String(o.id).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const content=`<div class="financial-summary" data-financial-observation="${observationAttr}"><div class="row-number"><strong>${esc(value)}</strong><span>${esc(type)}</span></div><span class="row-period">${esc(readableDates(period))} · ${esc(o.currency||'')} · ${esc(scope)}${basis?' · '+esc(basis):''}</span><div class="financial-citation">${citation}<span>${esc(o.evidence_assurance||'Attributed source')}</span></div>${warning}<details class="financial-source-details"><summary>Figure details</summary><p>${esc(o.limitations||'')}</p>${quote?`<blockquote>${esc(quote)}</blockquote>`:''}${checked?`<p>Source content checked ${esc(readableDates(checked))}. The figure covers ${esc(readableDates(period))}.</p>`:''}</details></div>`;
 return old?`<span class="signal-label">No recent revenue figure</span><details class="historical-signal"><summary>Historical figure · ${esc(readableDates(period))}</summary>${content}</details>`:content;
}
function compactSignal(id){return financialSummaryHTML(id);}
// Recency describes the observation period, not when an old source was fetched again.
const FINANCIAL_RECENCY_REVIEW='2026-10-28';
function financialObservationAge(m){
 if(!m||!['revenue','annualized_revenue_run_rate','arr'].includes(m.kind))return 'current';
 const rank=dateRank(m.as_of);if(rank==='0000')return 'undated';
 // A year-only reporting period is treated as ending in December; do not invent a precise date.
 const end=rank.length===4?rank+'-12-31':rank.length===7?rank+'-31':rank;
 return end<`${Number(FINANCIAL_RECENCY_REVIEW.slice(0,4))-1}${FINANCIAL_RECENCY_REVIEW.slice(4)}`?'historical':'current';
}
function signalFor(id,m,span=''){if(!m)return `<span class="unavailable">${companies[id].entity_type==='adjacent_research'?'Research organization':'Not disclosed'}</span>`;const kind={revenue:'Revenue',annualized_revenue_run_rate:'Annualized pace',arr:'Yearly recurring subscription revenue'}[m.kind]||metricLabels[m.kind];const rank=dateRank(m.as_of),year=rank==='0000'?null:Number(rank.slice(0,4)),historical=year&&year<Number(DATA.meta.as_of.slice(0,4))-1;const html=`${historical?`<span class="signal-history">Historical · ${year}</span>`:''}<div class="row-number ${historical?'is-historical':''}">${numberButton(m)}<span>${esc(kind)}${m.gross_vs_net==='gross'?' · '+esc(metricCurrentBasis(m,'gross')):''}</span></div><span class="row-period">${esc(readableDates(shortPeriod(m)))}${span?' · '+esc(span):''} · ${esc(m.currency||'')} · ${esc(compactMetricScope(m))}${m.gross_vs_net==='net'?' · net':m.gross_vs_net!=='gross'?' · gross or net not stated':''}</span><span class="signal-attribution">${esc(typeof profileMetricAttribution==='function'?profileMetricAttribution(m):evidenceLabel(claims[m.claim_id]))}</span>`;const age=financialObservationAge(m);return age==='current'?html:`<span class="signal-label">${age==='undated'?'No dated revenue figure':'No recent revenue figure'}</span><details class="historical-signal"><summary>${age==='undated'?'Undated financial claim':'Historical figure · '+esc(readableDates(shortPeriod(m)))}</summary>${html}</details>`;}
function renderDirectory(){
 companyReturnFocus=null;
 const rows=filtered(),query=state.query.trim(),secondaryCount=[state.stage,state.financial,state.work,state.sort!=='name'].filter(Boolean).length;
 const summary=document.querySelector('.more-filters>summary');if(summary)summary.textContent=secondaryCount?`More filters (${secondaryCount})`:'More filters';
 $('download-csv').textContent=`Current company results · ${rows.length} ${rows.length===1?'row':'rows'} · CSV (a table format for spreadsheet software)`;$('reset').hidden=!(query||state.category||secondaryCount);$('company-cards').innerHTML=rows.map(card).join('');$('result-count').textContent=`Showing ${rows.length} of ${DATA.companies.length} companies`;$('empty-state').hidden=rows.length>0;
 $('active-filters').innerHTML=[query&&`Search: ${query}`,state.category&&groupLabel(state.category),state.stage&&`Delivery evidence: ${stageLabel(state.stage)}`,state.financial&&'Revenue figures',state.work&&'Has paid work or a career page',state.sort==='name-desc'&&'Name Z–A'].filter(Boolean).map(x=>`<span class="active-filter">${esc(x)}</span>`).join('');syncSelection();
}

// Shared <select> option helper for page filters.
function addOptions(id,rows){$(id).innerHTML+=[...rows].map(([v,l])=>`<option value="${esc(v)}">${esc(l)}</option>`).join('');}

// Company index: apply a #companies/<group-slug> route to the filters.
// A new group shows the whole group; a bare #companies keeps the visitor's filters.
// Either way the URL then names the selected group, so it can be shared.
// An address that names no group (#companies/no-such-group) clears the filters, shows the full list and becomes #companies.
function syncDirectoryRoute(rest){const slug=String(rest?.[0]||'').toLowerCase(),key=slug?Object.keys(MODEL_GROUPS).find(k=>groupSlug(k)===slug)||'':state.category,narrowed=state.query||state.stage||state.financial||state.work;if(key!==state.category||(slug&&!key&&narrowed)){Object.assign(state,{query:'',category:key,stage:'',financial:false,work:false});$('search').value='';$('category').value=key;$('stage').value='';$('financial-only').checked=false;$('work-only').checked=false;renderDirectory();viewScroll.companies=0;}writeDirectoryRoute();}
function writeDirectoryRoute(){if(String(routeParts()[0]||'').toLowerCase()!=='companies')return;const hash='#companies'+(state.category?'/'+groupSlug(state.category):'');if(location.hash!==hash)history.replaceState(history.state,'',hash);document.title=(state.category?groupLabel(state.category)+' · ':'')+VIEW_TITLES.companies;}

// Company index: filter options and controls.
function initDirectory(){addOptions('category',Object.keys(MODEL_GROUPS).map(x=>[x,groupLabel(x)]));const presentStages=new Set(Object.keys(companies).map(id=>stageFor(id)));addOptions('stage',[...DATA.rubric.stages.map(s=>[s.id,stageLabel(s.id)]),['not_applicable','Research organizations'],['pending','Assessment pending']].filter(([id])=>presentStages.has(id)));const nonprofits=(MODEL_GROUPS['Nonprofit research']||[]).length;$('directory-nonprofits').textContent=nonprofits?` ${['One','Two','Three','Four','Five'][nonprofits-1]||nonprofits} of the ${DATA.companies.length} ${nonprofits===1?'is a nonprofit research group':'are nonprofit research groups'}.`:'';$('search').addEventListener('input',e=>{state.query=e.target.value;renderDirectory();});$('category').addEventListener('change',e=>{state.category=e.target.value;renderDirectory();writeDirectoryRoute();});$('stage').addEventListener('change',e=>{state.stage=e.target.value;renderDirectory();});$('sort').addEventListener('change',e=>{state.sort=e.target.value;renderDirectory();});$('financial-only').addEventListener('change',e=>{state.financial=e.target.checked;renderDirectory();});$('work-only').addEventListener('change',e=>{state.work=e.target.checked;renderDirectory();});$('reset').addEventListener('click',reset);}

// Work page: filter options and controls. Typing redraws the list after a 180 ms pause, so each keystroke
// paints at once on slow phones; input sent by the site search (not typed) redraws at once.
function initWork(){state.workSort=state.workSort||'';const groups=new Set(DATA.companies.filter(c=>workClaims(c.id).length).flatMap(c=>workTerms(c.id).groups));addOptions('work-group',[...Object.keys(W4_TYPE_LABELS).filter(x=>groups.has(x)),...[...groups].filter(x=>!(x in W4_TYPE_LABELS)).sort()].map(x=>[x,W4_TYPE_LABELS[x]||x]));$('work-safety').innerHTML=workSafetyHTML(workRouteRows());$('work-search').addEventListener('input',e=>{state.workQuery=e.target.value;if(e.isTrusted)w4QueueRender();else renderWork();});for(const [id,key] of [['work-group','workGroup'],['work-pay','workPay'],['work-eligibility','workEligibility'],['work-sort','workSort']])$(id).addEventListener('change',e=>{state[key]=e.target.value;renderWork();});$('work-reset').addEventListener('click',()=>{resetWorkFilters();});}

// Compare page: selection controls and the narrow-screen layout switch.
function initCompare(){$('clear-compare').addEventListener('click',()=>{setSelection([]);$('compare-preset').value='';});$('compare-preset').addEventListener('change',event=>{if(!event.target.value){syncComparisonPreset();return;}state.mobileCompare=0;setSelection(event.target.value==='scale'?['taskus','appen','scale_ai']:['surge_ai','toloka','labelbox']);});
 // Add a company: a pick with a pointer adds it at once. With the keyboard, arrow keys only
 // browse the list; Enter or the Add button adds the company that is showing.
 const add=$('compare-add'),addButton=$('compare-add-button');let picked=false;const addChosen=()=>{const id=add.value;if(!isCompanyId(id)||state.selected.includes(id))return;add.focus?.({preventScroll:true});state.mobileCompare=Math.max(0,comparePairOptions([...state.selected,id]).findIndex(pair=>pair.includes(state.selected.length)));chooseCompare(id,true);};
 add.addEventListener('pointerdown',()=>{picked=true;});add.addEventListener('keydown',event=>{if(event.key!=='Enter'){picked=false;return;}if(add.value){event.preventDefault();addChosen();}});add.addEventListener('change',()=>{if(picked){picked=false;addChosen();}else addButton.hidden=!add.value;});addButton.addEventListener('click',addChosen);
 document.addEventListener('click',event=>{const button=event.target.closest?.('[data-copy-compare]');if(button)copyCompareLink(button);const more=event.target.closest?.('[data-compare-extra]');if(more){comparisonExpanded=!comparisonExpanded;const extra=$('comparison-extra');if(extra)extra.hidden=!comparisonExpanded;more.setAttribute('aria-expanded',String(comparisonExpanded));more.textContent=comparisonExpanded?'Hide additional details':'Show funding, products, relationships & people';}});
 let compareNarrow=window.innerWidth<=700;window.addEventListener('resize',()=>{const next=window.innerWidth<=700;if(next!==compareNarrow){compareNarrow=next;resizeComparison();}comparisonScrollRegion();});}

// Method page: evidence labels, research coverage and downloads.
function initMethod(){
 document.querySelectorAll('.download-list>li').forEach(item=>item.insertAdjacentHTML('afterbegin',iconHTML('download')));
 // Every count is computed from the data. Hand-written copy is inserted as is; data strings go through esc().
 const count=n=>String(n).replace(/\B(?=(\d{3})+(?!\d))/g,','),plural=(n,one,many)=>`${count(n)} ${n===1?one:many}`,numberWord=n=>['No','One','Two','Three','Four','Five','Six','Seven','Eight','Nine'][n]||count(n);
 const grades={},levels={},research=DATA.companies.filter(c=>c.entity_type==='adjacent_research').length,dims=DATA.rubric.dimensions;let current=0,open=0;
 for(const c of DATA.claims){if(c.status==='superseded')continue;current++;grades[c.confidence]=(grades[c.confidence]||0)+1;if(c.status==='unverified'||c.status==='contested')open++;}for(const c of DATA.companies){const s=stageFor(c.id);levels[s]=(levels[s]||0)+1;}
 document.querySelectorAll('.grade-list>div').forEach(row=>row.insertAdjacentHTML('beforeend',`<dd class="grade-count">${plural(grades[row.querySelector('dt')?.textContent.trim()]||0,'claim','claims')}</dd>`));
 $('grade-note').textContent=`Counts cover all ${count(current)} current claims. Tap or click a figure on a company page or in Compare to see its sources and grade.`;
 const meanings={established_commercial_evidence:'A buyer, a filing or another independent record confirms a named project, and sales have lasted at least two years. The offer and how it is delivered are documented.',repeatable_commercial_evidence:'A named customer project, plus signs of repeat business such as a renewal. The offer and how it is delivered are documented.',demonstrated_delivery:'A documented offer and at least one named customer project, described in detail.',visible_operating_offer:'A clear current offer, run by a named team with a documented delivery process.',insufficient_public_evidence:'The public evidence we reviewed does not reach a higher level.'};
 const areas={P:'product (an offer someone can buy or use)',C:'customer evidence (signs that buyers use the offer)',R:'commercial continuity (sales that repeat over time)',O:'operating readiness (the team and process that deliver the work)'};
 $('rubric-content').innerHTML=`<dl class="level-list">${DATA.rubric.stages.map(s=>`<div><dt>${esc(stageLabel(s.id))}</dt><dd>${meanings[s.id]||esc(s.definition)}</dd><dd class="level-count">${plural(levels[s.id]||0,'company','companies')}</dd></div>`).join('')}</dl><details class="rubric-exact-rules"><summary>Exact assessment rules</summary><p>${dims.map(d=>`${esc(d.id)}: ${areas[d.id]||esc(d.label)}.`).join(' ')}</p><table class="rubric-table"><caption>Lowest level needed in each area</caption><thead><tr><th scope="col">Level</th>${dims.map(d=>`<th scope="col"><span aria-hidden="true">${esc(d.id)}</span><span class="sr-only">${esc(d.label)}</span></th>`).join('')}</tr></thead><tbody>${DATA.rubric.stages.map(s=>`<tr><th scope="row">${esc(stageLabel(s.id))}</th>${Object.keys(s.minimums).length?dims.map(d=>s.minimums[d.id]?`<td>${esc(s.minimums[d.id])}</td>`:'<td class="rubric-any">Any</td>').join(''):`<td colspan="${dims.length}" class="rubric-any">No rule above is met</td>`}</tr>`).join('')}</tbody></table>${dims.map(d=>`<details><summary>${esc(d.id)} · ${esc(d.label)}</summary>${Object.entries(d.levels).map(([n,desc])=>`<p>Level ${esc(n)}: ${esc(desc)}</p>`).join('')}</details>`).join('')}</details><p>Each company gets the highest level its evidence supports. Missing evidence stays marked as unknown, and funding or valuation never counts.${research?` The ${numberWord(research).toLowerCase()} nonprofit research ${research===1?'group gets no level and shows':'groups get no level and show'} ${esc(stageLabel('not_applicable'))} instead.`:''}</p><p class="method-note">Levels reflect public proof only. They are not guarantees or judgments of honesty. Private companies publish less, so their level can understate them. Proof about a whole company does not prove the same for its AI data work.</p>`;
 $('coverage-notes').innerHTML=`<ul class="coverage-stats"><li><strong>${count(DATA.companies.length)}</strong> companies profiled.${research?` ${numberWord(research)} ${research===1?'is a nonprofit research group':'are nonprofit research groups'}.`:''}</li><li><strong>${count(DATA.sources.length)}</strong> source records, pointing to ${count(new Set(DATA.sources.map(s=>s.url)).size)} distinct web pages.</li><li><strong>${count(current)}</strong> current claims. ${count(DATA.claims.length-current)} earlier versions stay on file.</li><li><strong>${count(open)}</strong> claims are unverified or disputed. Each one is labeled.</li></ul><p>We chose these companies, so the guide does not cover the whole market. On 14 Oct 2026 we rechecked what each company offers. Older claims keep their original dates and grades, and we have not rechecked every older source.</p>`;
 const [year,month,day]=String(DATA.meta.as_of).split('-').map(Number);$('download-version').textContent=`Dataset v${DATA.dataset_version} · research compiled ${day} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]} ${year}`;
 $('download-json').addEventListener('click',()=>download('observatory-research.json',JSON.stringify(DATA,null,2)+'\n','application/json'));$('download-csv').addEventListener('click',exportCsv);
}

function initialize(){$('snapshot').textContent=compiledSnapshotLabel(DATA.meta.as_of);$('footer-version').textContent=`Dataset v${DATA.dataset_version}`;
 const renderCards=renderDirectory;renderDirectory=function(){directoryShown=true;return renderCards.apply(this,arguments);};
 Object.assign(PAGE_SETUP,{companies:[initDirectory],method:[initMethod],work:[initWork],market:[renderStory]});
 const later=typeof requestIdleCallback==='function'?task=>requestIdleCallback(task,{timeout:1000}):typeof requestAnimationFrame==='function'?task=>setTimeout(task,50):null;
 if(!later){for(const view of ['companies','method','work'])preparePage(view);renderDirectory();preparePage('market');}
 route();initCompare();if(typeof initSiteNav==='function')initSiteNav();
 $('close-company').addEventListener('click',()=>$('company-dialog').close());$('close-evidence').addEventListener('click',()=>$('evidence-dialog').close());
 document.addEventListener('change',e=>{if(e.target.matches('[data-compare]'))chooseCompare(e.target.dataset.compare,e.target.checked);});document.addEventListener('click',e=>{const link=e.target.closest('[data-open-company]');if(link){if(link.tagName==='A'&&(e.metaKey||e.ctrlKey||e.shiftKey||e.altKey||e.button))return;e.preventDefault();openCompanyStory(link.dataset.openCompany);return;}const fullProfile=e.target.closest('[data-full-profile]');if(normalSelfLinkActivation(e,fullProfile))$('company-dialog').close();const b=e.target.closest('button');if(!b)return;if(b.dataset.profileTab){activateProfileTab(b.dataset.profileTab);return;}if(b.dataset.claim){$('company-dialog').close();showEvidence(b.dataset.claim);}if(b.hasAttribute('data-clear'))reset();if(b.hasAttribute('data-clear-compare')){setSelection([]);const view=document.querySelector('.view:not([hidden])'),target=view?.querySelector('input[type=search]')||view?.querySelector('.profile-links [data-compare]')||view?.querySelector('h1');if(target){if(target.tagName==='H1')target.setAttribute('tabindex','-1');target.focus();}}if(b.dataset.remove){chooseCompare(b.dataset.remove,false);const surviving=[...document.querySelectorAll('#compare-content [data-remove]:not([hidden])')].find(node=>node.getClientRects().length);const next=surviving||$('clear-compare');next.focus({preventScroll:true});next.scrollIntoView({block:'nearest',behavior:'instant'});}if(b.dataset.preset){state.mobileCompare=0;setSelection(b.dataset.preset==='scale'?['taskus','appen','scale_ai']:['surge_ai','toloka','labelbox']);}if(b.dataset.mobileCompare!==undefined){state.mobileCompare=Math.min(Number(b.dataset.mobileCompare),Math.max(0,comparePairOptions(state.selected.length?state.selected:['taskus','appen','scale_ai']).length-1));renderCompare();document.querySelector('.mobile-column-options summary')?.focus();}if(b.hasAttribute('data-runrates')){state.runratesExpanded=!state.runratesExpanded;renderCharts();}});window.addEventListener('hashchange',route);
 // On small screens the Filters fields open as a panel under the button. A short screen can leave the whole panel
 // below the fold, so bring it into view when it opens. toggle does not bubble, so listen in the capture phase.
 document.addEventListener('toggle',e=>{const panel=e.target;if(!panel?.open||!panel.matches?.('.responsive-filter-panel,.more-filters'))return;if(panel.matches('.responsive-filter-panel')&&window.innerWidth>900)return;const fields=panel.querySelector('.responsive-filter-fields,.more-filters-panel'),box=fields?.getBoundingClientRect();if(box?.height&&box.bottom>window.innerHeight)fields.scrollIntoView({block:'nearest'});},true);
 if(later)for(const view of ['companies','work','method'])later(()=>preparePage(view));
}

// Native disclosures used as overlays retain predictable dismissal and focus.
// A press of the mouse or a tap moves focus before its click lands. Collapsing the panel then
// would shift the page under the pointer and lose the click, so pointer presses leave closing
// to the outside-click listener; Tab and Escape still close the panel.
const OVERLAY_DETAILS='.responsive-filter-panel,.more-filters,.mobile-column-options';
let overlayPointerFocus=false;
function dismissDisclosure(panel,restoreFocus){
 if(!panel?.open)return;
 panel.open=false;
 const target=restoreFocus?panel.querySelector('summary'):document.activeElement;
 if(restoreFocus)target?.focus({preventScroll:true});
 if(!target||target===document.body||!target.getClientRects().length||target.closest('dialog'))return;
 const header=document.querySelector('.topbar');
 if(header?.contains(target))return;
 const box=target.getBoundingClientRect(),top=(header?.getBoundingClientRect().bottom||0)+8,bottom=window.innerHeight-8;
 if(box.top<top)window.scrollBy({top:box.top-top,behavior:'instant'});
 else if(box.bottom>bottom)window.scrollBy({top:box.bottom-bottom,behavior:'instant'});
}
document.addEventListener('keydown',event=>{overlayPointerFocus=false;if(event.key!=='Escape')return;const panel=event.target.closest?.(OVERLAY_DETAILS);if(panel?.open&&panel.querySelector('summary')?.getClientRects().length){event.preventDefault();dismissDisclosure(panel,true);}});
document.addEventListener('pointerdown',()=>{overlayPointerFocus=true;},true);
document.addEventListener('click',event=>{document.querySelectorAll(OVERLAY_DETAILS).forEach(panel=>{if(panel.open&&!panel.contains(event.target)&&panel.querySelector('summary')?.getClientRects().length)dismissDisclosure(panel,panel.contains(document.activeElement));});});
document.addEventListener('focusin',event=>{if(overlayPointerFocus)return;document.querySelectorAll(OVERLAY_DETAILS).forEach(panel=>{if(panel.open&&!panel.contains(event.target)&&panel.querySelector('summary')?.getClientRects().length)dismissDisclosure(panel,false);});});

// Page titles for each main view.
const VIEW_TITLES={market:'ScienceToStartup · The AI data field guide',companies:'Companies · ScienceToStartup',compare:'Compare · ScienceToStartup',work:'Paid work · ScienceToStartup',method:'Method · ScienceToStartup'};
