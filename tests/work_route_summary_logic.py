"""Focused work-summary regressions using the shared JS harness; no browser."""
import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from presentation import compact_work

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
const fellow=plain(run(`workRouteRows().find(route=>route.id==='afterquery.work.research-fellow')`));
for(const mode of ['', 'compact']){
 for(const route of [writer,fellow]){
  const html=run(`workCard(${JSON.stringify(route)},${JSON.stringify(mode)})`);
  const details=html.indexOf('<details class="w4-details">');
  const note=run(`w4Escape(${JSON.stringify(route.field_reviews.commitment.note)})`);
  for(const part of [html.slice(0,details),html.slice(details)]){
   assert.equal(part.split(note).length,2,route.id+' schedule wording appears once per section '+mode);
   assert.ok(part.includes(route.duration),route.id+' duration '+mode);
  }
  assert.ok(html.includes('<blockquote>'+route.source_quote+'</blockquote>'),route.id+' exact evidence quote');
 }
}
assert.match(writer.field_reviews.commitment.note,/10–15 hours\/week.+expansion.+full-time/i);
assert.match(fellow.field_reviews.commitment.note,/full-time.+20\+ hours\/week.+prefer.+in-person/i);
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

const historical={
 'aixi.work.research-fellowship':['application destination'],
 'aixi.work.machine-learning-research-scientist':['application destination'],
 'prolific.work.study-participant':['application destination'],
 'toloka.work.mindrift-code':['application destination'],
 'afterquery.work.technical-content-writer-contract':['application destination','pay','location','requirements','commitment','duration'],
};
const projected=JSON.parse(fs.readFileSync(expectedPath,'utf8'));
for(const [id,fields] of Object.entries(historical)){
 const route=projected.routes.find(row=>row.id===id),sourceId=id+'.review-2026-10-28';
 const html=run(`w4Details(${JSON.stringify(route)})`);
 const source=html.split('data-work-source="'+sourceId+'">')[1].split('</small>',1)[0];
 assert.ok(source.includes('Checked 28 Oct 2026'),id+' retains source date');
 const earlier=source.split('Earlier source for ')[1].split(', ');
 for(const field of fields)assert.ok(earlier.includes(field),id+' retains source for '+field);
 const url=route.sources.find(row=>row.id===sourceId).url;
 assert.equal(html.split('w4-detail-block w4-sources')[1].split(`href="${url}"`).length,2,id+' binds observations to one source link');
}
const scholar=projected.routes.find(row=>row.id==='afterquery.work.research-scholar');
const qualification=scholar.pay_terms.note;
assert.equal(run(`w4Details(${JSON.stringify(scholar)})`).split(qualification).length,2,'Scholar payment condition in the disclosure');
assert.equal(run(`w4PayNotes(${JSON.stringify(scholar)})`).split(qualification).length,2,'Scholar payment condition beside the rate');

const search='RLHF  jobs';
const matches=plain(run(`selectWorkRoutes(workRouteRows(),{q:${JSON.stringify(search)}}).map(row=>row.id)`));
assert.deepEqual(matches,['afterquery.work.software-engineer-rl-environments']);
assert.equal(run(`normalizeWorkCriteria({q:' RLHF  jobs '}).q`),' RLHF  jobs ');
const literalTitles=[{id:'literal',role:'Hiring Assistant',status:'listed'},{id:'broader',role:'Assistant',status:'listed'}];
assert.deepEqual(plain(run(`S2SWork.select(${JSON.stringify(literalTitles)},{q:'Hiring Assistant'},row=>S2SWork.fold(row.role)).map(row=>row.id)`)),['literal']);

const revised={...writer,availability_note:'No schedule conflict stated.',field_reviews:{...writer.field_reviews,commitment:{...writer.field_reviews.commitment,state:'sourced'}}};
assert.equal(run(`w4ScheduleNote(${JSON.stringify(revised)})`),'','Do not retain an obsolete conflict after source text changes');
console.log(JSON.stringify({companies_checked:workLabels.length,summary_filter_alignment:true,approved_opportunity_kinds:true,no_route_label:true,check_notes:checkNotes,writer_card_variants:2,writer_qualifications:true,browser_verified:false}));
'''
node = shutil.which("node") or "/opt/homebrew/bin/node"
with tempfile.TemporaryDirectory() as directory:
    projected_path = Path(directory) / "work.json"
    projected_path.write_text(json.dumps(compact_work(json.loads((ROOT / "data/work-routes.json").read_text()))))
    result = subprocess.run(
        [node, "-", str(ROOT / "data/canonical.json"), str(ROOT), str(projected_path)],
        input=stub.split("(async()=>{", 1)[0] + checks,
        text=True,
        cwd=ROOT,
        check=False,
    )
raise SystemExit(result.returncode)
