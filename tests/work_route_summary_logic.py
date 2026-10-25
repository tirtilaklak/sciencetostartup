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
for(const row of workLabels){
 assert.equal(row.included,Boolean(row.primary.length||row.careers.length),row.id+' filter classification drift');
 if(row.primary.length){
  for(const group of new Set(row.primary.map(route=>route.group)))assert.ok(row.label.includes(run(`WORK_TYPES[${JSON.stringify(group)}]`)||group||'Paid work listings'),row.id+' missing retained route type '+group);
 }else assert.equal(row.label,row.careers.length?'Career page only':'No confirmed paid listing',row.id+' unsupported current route label');
}
// APTO lists a contractor route and an employment route; both types must stay in its label.
assert.equal(run('workType("apto")'),'Contract and task work · Jobs');
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
assert.ok(run('workType("aixi")').includes('Jobs'));
assert.ok(run('workType("aixi")').includes('Research fellowships'));
const writer=plain(run(`workRouteRows().find(route=>route.id==='afterquery.work.technical-content-writer-contract')`));
assert.equal(run(`w4Hours(${JSON.stringify(writer)})`),'10–15 h/week · Initial commitment; may expand · Six months');
for(const mode of ['', 'compact']){
 const html=run(`workCard(${JSON.stringify(writer)},${JSON.stringify(mode)})`);
 assert.ok(html.includes('Initial commitment; may expand'),'writer hours qualifier '+mode);
 assert.ok(html.includes('Schedule conflict: header says full-time; role body specifies a part-time contract.'),'writer schedule conflict '+mode);
 assert.ok(html.slice(html.indexOf('<details class="w4-details">')).includes('Initial commitment; may expand'),'writer expanded terms qualifier '+mode);
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
const revised={...writer,availability_note:'No schedule conflict stated.'};
assert.equal(run(`w4ScheduleNote(${JSON.stringify(revised)})`),'','Do not retain an obsolete conflict after source text changes');
console.log(JSON.stringify({companies_checked:workLabels.length,summary_filter_alignment:true,apto_employment:true,no_route_label:true,check_notes:checkNotes,writer_card_variants:2,writer_qualifications:true,browser_verified:false}));
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
