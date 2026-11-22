"""Focused work-summary regressions using the shared JS harness; no browser."""
import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
stub = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets)
)
checks = r'''
const workLabels=plain(run(`DATA.companies.map(company=>{
 const groups=w4RouteGroups(workRoutesFor(company.id));
 return {id:company.id,label:workType(company.id),included:hasWorkRoute(company.id),primary:groups.primary,careers:groups.careers};
})`));
const archived=new Set(['historical','closed','contributions','paused','no_route','inquiry','information']);
for(const row of workLabels){
 const records=window.WORK_ROUTES.routes.filter(route=>route.company_id===row.id),primary=records.filter(route=>!archived.has(route.status)&&route.ai_data_work!==false&&['named_listing','network_program'].includes(route.route_kind)),careers=records.filter(route=>!archived.has(route.status)&&route.route_kind==='career_page');
 const kinds=new Set(primary.map(route=>route.route_kind)),label=[kinds.has('named_listing')?'Named listings':'',kinds.has('network_program')?'Networks and programs':''].filter(Boolean).join(' · ')||(careers.length?'Career page only':records.length?'No confirmed paid listing':'Paid work not reviewed yet');
 assert.equal(row.included,Boolean(primary.length||careers.length),row.id+' filter classification drift');
 assert.equal(row.label,label,row.id+' summary must follow approved opportunity kinds, independent of legacy group/pay/engagement');
 assert.deepEqual(row.primary.map(route=>route.id).sort(),primary.map(route=>route.id).sort(),row.id+' primary membership');
}
assert.equal(run('workType("apto")'),'Networks and programs','The unpublished application no longer counts as a named listing');
assert.equal(run('workType("afterquery")'),'Named listings');
assert.equal(run('workType("mercor")'),'Networks and programs','A varies-engagement network is not labeled employment or contract work');
assert.equal(run('workType("turing")'),'Networks and programs','The ML category page describes the general network intake');
// The 23 Oct listing check found Elorian's Model Safety Contractor posting gone, so it is historical like
// the earlier engineering role. Elorian has no other paid listing or career page.
assert.equal(run('workType("elorian")'),'No confirmed paid listing');
assert.equal(run('hasWorkRoute("elorian")'),false);
// HackerRank keeps only information and past contest pages, so it shows the no-route label.
assert.equal(run('workType("hackerrank")'),'No confirmed paid listing');
assert.equal(run('workType("taskus")'),'Career page only');
assert.equal(run('workType("sama")'),'Career page only');
assert.equal(run('hasWorkRoute("hackerrank")'),false);
assert.equal(run('hasWorkRoute("quesma")'),false);
assert.equal(run('workType("aixi")'),'Named listings');
const writer=plain(run(`workRouteRows().find(route=>route.id==='afterquery.work.technical-content-writer-contract')`));
assert.equal(run(`w4Hours(${JSON.stringify(writer)})`),'10–15 h/week initially, with potential expansion · Six months');
for(const mode of ['', 'compact']){
 const html=run(`workCard(${JSON.stringify(writer)},${JSON.stringify(mode)})`);
 assert.ok(html.includes('10–15 h/week initially, with potential expansion'),'writer hours qualifier '+mode);
 assert.ok(html.includes('Schedule conflict. The description specifies part-time work.'),'writer schedule conflict '+mode);
 assert.ok(html.slice(html.indexOf('<details class="w4-details">')).includes('with potential expansion'),'writer expanded terms qualifier '+mode);
}
// Link check notes: a result code becomes plain words and a result phrase ends with a period.
assert.equal(run(`w4CheckNote({result:'public_page_live',note:'public_page_live 35 open roles listed.'})`),'Public page was live. 35 open roles listed.');
assert.equal(run(`w4CheckNote({result:'Published route observed',note:'Published route observed Five positions listed.'})`),'Published route observed. Five positions listed.');
assert.equal(run(`w4CheckNote({result:'listed',note:'Rolling applications.'})`),'Rolling applications.');
let checkNotes=0;
for(const route of plain(run('workRouteRows()')).filter(route=>route.last_route_check?.note)){
 const note=run(`w4CheckNote(${JSON.stringify(route.last_route_check)})`);checkNotes++;
 assert.ok(!/^[a-z]+_[a-z_]+\b/.test(note)&&!note.includes('public_page_live'),route.id+' check note shows a raw result code: '+note);
 assert.ok(run(`w4Details(${JSON.stringify(route)})`).includes(run(`w4Escape(${JSON.stringify(note)})`)),route.id+' card lost its check note');
}
assert.ok(checkNotes>=17,'Fixture lost the route check notes');
const network=plain(run(`workRouteRows().find(route=>route.id==='snorkel_ai.work.expert-community')`));
const terms=run(`w4Details(${JSON.stringify(network)})`);
assert.equal((terms.match(/href="https:\/\/snorkel\.ai\/expert-community\/"/g)||[]).length,1,'Repeated observations share one outward source link');
assert.match(terms,/review-2026-10-28">[^<]+28 Oct 2026 · Supports [^<]*\bpay\b/);
assert.match(terms,/retrieval-2026-11-08">[^<]+8 Nov 2026 · Retrieval observation/);

const revised={...writer,availability_note:'No schedule conflict stated.',field_reviews:{...writer.field_reviews,commitment:{...writer.field_reviews.commitment,state:'sourced'}}};
assert.equal(run(`w4ScheduleNote(${JSON.stringify(revised)})`),'','Do not retain an obsolete conflict after source text changes');
console.log(JSON.stringify({companies_checked:workLabels.length,summary_filter_alignment:true,approved_opportunity_kinds:true,no_route_label:true,check_notes:checkNotes,writer_card_variants:2,writer_qualifications:true,browser_verified:false}));
'''
node = shutil.which("node") or "/opt/homebrew/bin/node"
result = subprocess.run(
    [node, "-", str(ROOT / "data/canonical.json"), str(ROOT)],
    input=stub.split("(async()=>{", 1)[0] + checks,
    text=True,
    cwd=ROOT,
    check=False,
)
raise SystemExit(result.returncode)
