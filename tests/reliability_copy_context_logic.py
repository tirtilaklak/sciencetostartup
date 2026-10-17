"""Check compact copy against its dated evidence and preserve source punctuation.

Runs the composed presentation modules with the existing DOM stub. This is a
copy/evidence regression check, not browser interaction or external-source QA.
"""
import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
checks = r'''
const before=run('JSON.stringify(DATA)'),editorialBefore=JSON.stringify(window.EDITORIAL),profilesBefore=JSON.stringify(window.PROFILE_CONTENT);
const visible=html=>html.replace(/<span\b[^>]*data-evidence-description\b[^>]*>[\s\S]*?<\/span>/g,'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim();

// iMerit has documented expansion (R2). Its compact limit must explain the
// missing multi-year public evidence without denying that established work.
const assessment=run("assessmentFor('imerit')");
assert.equal(assessment.gates.R.level,'2');
assert.match(assessment.gates.R.rationale,/two annual financial statements/);
assert.match(assessment.gates.R.rationale,/24-month/);
const imerit=run("storyUnknown('imerit')");
assert.match(imerit,/Public evidence.*multiple years.*incomplete/);
assert.ok(!/\bR3\b/.test(imerit));
assert.ok(visible(run('renderAssessment('+JSON.stringify(assessment)+')')).includes('EXL parent financial statements are excluded.'));

// The ambiguous unknown concerns September's reported financing, while the
// April Series A still has an announced amount and a named lead investor.
const afterquery=run("storyUnknown('afterquery')");
assert.match(afterquery,/reported September 2026 financing/);
for(const term of ['Size','closing date','investors'])assert.ok(afterquery.includes(term));
assert.ok(!/closed|completed/i.test(afterquery));
const september=run("claims['afterquery.claim.funding_rounds-1']");
assert.equal(september.as_of,'2026-09-02');
assert.match(september.statement,/amount and lead investor not disclosed/);
const april=visible(run("profileCapital('afterquery')"));
for(const term of ['$30M','9 Apr 2026','Altos Ventures'])assert.ok(april.includes(term));
run("showEvidence('afterquery.claim.unknowns-0')");
const uncertainty=visible(node('evidence-content').innerHTML);
for(const term of ['cumulative funding','audited revenue and margins','customer concentration','active paid-contributor count','continuity of assignments'])assert.ok(uncertainty.includes(term));

// Strip the implementation instruction, retaining the disclosed-round sum,
// its date and every bound source in both financing records.
for(const id of ['prime_intellect.claim.audit-pi-announced-total','prime_intellect.claim.audit-pi-announced-total-metric']){
 run(`showEvidence(${JSON.stringify(id)})`);
 const html=node('evidence-content').innerHTML,text=visible(html);
 assert.ok(text.includes('Financing amounts are disclosed.'));
 assert.ok(!/Never substitute|source amounts are strings|funding not established/.test(text));
 assert.ok(text.includes('$150.5m')&&text.includes('July 8, 2026'));
 const claim=data.claims.find(claim=>claim.id===id);
 for(const sourceId of claim.source_ids){
  const source=data.sources.find(source=>source.id===sourceId);
  assert.ok(html.includes(run(`esc(${JSON.stringify(source.url)})`)),sourceId+' source lost');
 }
}

// Meta's report describes Complex as a fixed set from a proprietary attacker.
// It does not establish that attacker's implementation as an LLM or non-LLM.
const trajectory=run("profileProductGrid('trajectory_labs_pbc')");
const searchPI=trajectory.match(/<article class="offering-card" data-profile-product="Search-PI Complex">([\s\S]*?)<\/article>/)?.[1];
assert.ok(searchPI,'Search-PI Complex offering missing');
const searchPIText=visible(searchPI);
assert.match(searchPIText,/fixed set of attacks/);
assert.match(searchPIText,/Trajectory Labs’ proprietary attacker/);
assert.ok(!/attacker models|non-LLM|language.model attacker/i.test(searchPIText));
assert.ok(searchPI.includes('data-claim="trajectory_labs_pbc.claim.oct14-product-2"'),'Product source binding changed');

// Real summaries retain their complete supplied text, including its terminal
// punctuation. Exercise other endings so a blanket punctuation replacement
// cannot accidentally turn a question or exclamation into a statement.
let summaries=0;
for(const company of data.companies){
 run(`openCompanyStory(${JSON.stringify(company.id)})`);
 const paragraph=node('company-story').innerHTML.match(/<p class="selection-description">([\s\S]*?)<\/p>/)?.[1];
 assert.equal(paragraph,run(`esc(modelFor(${JSON.stringify(company.id)}))`));
 assert.ok(!paragraph.endsWith('..'),company.id+' duplicate full stop');
 summaries++;
}
assert.equal(summaries,39);
const entry=window.EDITORIAL.entries.find(entry=>entry.company_id==='mercor'),original=entry.summary;
for(const sentence of ['A complete sentence.','A question?','An exclamation!','An unfinished thought…','A quoted ending.”']){
 entry.summary=sentence;run("openCompanyStory('mercor')");
 const paragraph=node('company-story').innerHTML.match(/<p class="selection-description">([\s\S]*?)<\/p>/)[1];
 assert.equal(paragraph,run(`esc(${JSON.stringify(sentence)})`));
}
entry.summary=original;
assert.equal(run('JSON.stringify(DATA)'),before,'Research records mutated');
assert.equal(JSON.stringify(window.EDITORIAL),editorialBefore,'Editorial research mutated');
assert.equal(JSON.stringify(window.PROFILE_CONTENT),profilesBefore,'Profile research mutated');
console.log(JSON.stringify({summaries,contextualUnknowns:2,financingDialogs:2,punctuationCases:5,sourceScopedProductDescriptions:1,researchUnchanged:true,browserVerified:false}));
'''
result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-",
                         str(ROOT / "data/canonical.json"), str(ROOT)],
                        input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT)
raise SystemExit(result.returncode)
