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
// APTO's data now lists an employment route and a contractor route; the employment route must stay visible.
assert.ok(run('workType("apto")').includes('Jobs'));
// The 12 Oct review added Elorian's listed Model Safety Contractor role; its earlier engineering role is historical.
assert.equal(run('workType("elorian")'),'Contract and task work');
assert.equal(run('hasWorkRoute("elorian")'),true);
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
const revised={...writer,availability_note:'No schedule conflict stated.'};
assert.equal(run(`w4ScheduleNote(${JSON.stringify(revised)})`),'','Do not retain an obsolete conflict after source text changes');
console.log(JSON.stringify({companies_checked:workLabels.length,summary_filter_alignment:true,apto_employment:true,no_route_label:true,writer_card_variants:2,writer_qualifications:true,browser_verified:false}));
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
