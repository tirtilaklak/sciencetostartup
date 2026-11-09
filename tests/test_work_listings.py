"""Paid work listings: buckets, honest hourly sort, pay and place filters, search words, safety note.

Runs the delivered modules in the js_logic.py DOM stub (no browser).
"""
import ast
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = r'''
const routes=window.WORK_ROUTES.routes,byId=Object.fromEntries(routes.map(r=>[r.id,r]));
run('initialize()');
const ids=expr=>plain(run(expr));
// Buckets: every listing lands in exactly one, and contract work comes first.
const g=ids('(()=>{const x=w4RouteGroups(workRouteRows());return Object.fromEntries(["contract","jobs","boards","outside","closed","hourly","task","project"].map(k=>[k,x[k].map(r=>r.id)]))})()');
const total=['contract','jobs','boards','outside','closed'].reduce((n,k)=>n+g[k].length,0);
assert.equal(total,routes.length,'every listing has one bucket');
assert.equal(g.hourly.length+g.task.length+g.project.length,g.contract.length,'pay blocks split contract work');
for(const id of g.closed)assert.ok(['historical','closed','contributions','paused','no_route','inquiry','information'].includes(byId[id].status)||byId[id].route_kind==='other_record',id);
for(const id of g.boards)assert.equal(byId[id].status,'careers');
for(const id of g.outside)assert.equal(byId[id].ai_data_work,false);
// Pay blocks follow each listing's own fields, so the expected blocks are worked out from the data here.
const TASK_PAY=['per_completed_task','task','accepted_task','approved_recording','approved_submission','hour_equivalent'];
const statesHourly=r=>r.numeric_pay&&r.pay_terms.hourly_comparable===true&&r.status!=='pay_conflict'&&r.pay_basis!=='conflicting_hourly'&&/\/\s*(approved\s+)?hour/i.test(r.pay_label||'')&&/[$€£¥]\s*\d/.test(r.pay_label||'');
const open=r=>!['historical','closed','contributions','paused','no_route','inquiry','information','careers'].includes(r.status)&&r.ai_data_work!==false&&['named_listing','network_program'].includes(r.route_kind);
// Engagement is independent of its pay unit.
const contractRoute=r=>open(r)&&['contract','bounty','study','varies','unknown'].includes(r.engagement_type);
assert.deepEqual([...g.contract].sort(),routes.filter(contractRoute).map(r=>r.id).sort(),'contract bucket');
assert.ok(routes.some(r=>r.group==='Employment'&&['hour','one_time'].includes(r.pay_basis)),'fixture lost the Employment listings paid by the hour or by award');
assert.deepEqual([...g.hourly].sort(),routes.filter(r=>contractRoute(r)&&(statesHourly(r)||r.pay_basis==='conflicting_hourly')).map(r=>r.id).sort(),'hourly block');
assert.deepEqual([...g.task].sort(),routes.filter(r=>contractRoute(r)&&!g.hourly.includes(r.id)&&['task','hour_equivalent'].includes(r.pay_terms.unit)).map(r=>r.id).sort(),'task block');
assert.ok(g.hourly.length&&g.task.length&&g.project.length,'fixture lost a pay block');
// The 23 Oct check found the Elorian safety listing removed, so it is closed; G2i's senior SWE training work is listed again.
assert.ok(g.closed.includes('elorian.work.model-safety')&&byId['elorian.work.model-safety'].status==='historical','closed listing elorian.work.model-safety');
assert.ok(g.contract.includes('g2i.work.senior-swe-training')&&byId['g2i.work.senior-swe-training'].status==='listed','listed g2i.work.senior-swe-training');
// Hourly ranges: only labels that state a rate per hour, never a conflict, all read as published.
const ranged=ids('workRouteRows().filter(w4HourlyRange).map(r=>[r.id,w4HourlyRange(r)])');
assert.deepEqual(ranged.map(([id])=>id).sort(),routes.filter(statesHourly).map(r=>r.id).sort(),'hourly ranges');
for(const [id,range] of ranged){assert.match(byId[id].pay_label,/\/\s*(approved\s+)?hour/i,id);assert.notEqual(byId[id].status,'pay_conflict');assert.ok(range.high>=(range.low??0),id);}
assert.deepEqual(plain(run(`w4HourlyRange(${JSON.stringify(byId['scale_ai.work.outlier-statistics'])})`)),{currency:'$',low:null,high:150,open:false});
assert.deepEqual(plain(run(`w4HourlyRange(${JSON.stringify(byId['surge_ai.work.swe-environments'])})`)),{currency:'$',low:100,high:150,open:true});
assert.equal(run(`w4HourlyRange(${JSON.stringify(byId['afterquery.work.college-swe'])})`),null);
// Best match should not promote a higher claimed rate above reviewed, accessible terms.
const reviewed=byId['labelbox.work.mechanical-engineering'],blocked=byId['afterquery.work.world-models'];
assert.ok(reviewed.terms_checked_on&&blocked.last_link_check?.result==='blocked','reviewed/blocked ordering fixture');
assert.ok(run(`w4BestOrder(${JSON.stringify(reviewed)},${JSON.stringify(blocked)})`)<0,'reviewed terms should lead a blocked higher-rate claim');
// Numeric ordering stays within an explicitly stated currency. Bare dollar symbols do not imply USD.
const sorted=ids(`w4RouteGroups(workRouteRows(),'hourly').hourly.map(r=>r.id)`);
const known=sorted.filter(id=>byId[id].pay_terms.currency&&run(`w4HourlyRange(${JSON.stringify(byId[id])})`));
for(const currency of new Set(known.map(id=>byId[id].pay_terms.currency))){const rows=known.filter(id=>byId[id].pay_terms.currency===currency);for(let i=1;i<rows.length;i++)assert.ok(run(`w4HourlyRange(${JSON.stringify(byId[rows[i]])}).high`)<=run(`w4HourlyRange(${JSON.stringify(byId[rows[i-1]])}).high`),currency+' order');}
const base=byId['appen.work.sage-media'];
const usd={...base,pay_label:'$15 / hour',pay_terms:{...base.pay_terms,currency:'USD'}},gbp={...base,pay_label:'£900 / hour',pay_terms:{...base.pay_terms,currency:'GBP'}},unknown={...base,pay_label:'$999 / hour',pay_terms:{...base.pay_terms,currency:null}};
assert.ok(run(`w4RateOrder(${JSON.stringify(usd)},${JSON.stringify(gbp)})`)<0);
assert.ok(run(`w4RateOrder(${JSON.stringify(usd)},${JSON.stringify(unknown)})`)<0,'Unknown currency never outranks stated USD by numeric amount');
assert.equal(run(`w4RateTie(${JSON.stringify(usd)},${JSON.stringify(unknown)})`),0,'Unknown currency amounts are not pooled');
// Pay filter values, including the two the old tests use.
const pay=v=>{run(`resetWorkFilters();state.workPay=${JSON.stringify(v)}`);return ids('filteredWork().map(r=>r.id)');};
assert.deepEqual(pay('task').sort(),routes.filter(r=>['task','hour_equivalent'].includes(r.pay_terms.unit)).map(r=>r.id).sort());
assert.deepEqual(pay('hourly').sort(),routes.filter(statesHourly).map(r=>r.id).sort());
assert.deepEqual(pay('monthly').sort(),routes.filter(r=>r.pay_terms.unit==='month').map(r=>r.id).sort());
assert.deepEqual(pay('yearly').sort(),routes.filter(r=>r.pay_terms.unit==='year').map(r=>r.id).sort());
for(const v of ['task','hourly','monthly','yearly'])assert.ok(pay(v).length>0,'fixture lost '+v+' pay');
assert.equal(pay('numeric').length+pay('undisclosed').length,routes.length);
// Arrangements can overlap when a source supports more than one; unknown stays distinct.
const where=v=>{run(`resetWorkFilters();state.workEligibility=${JSON.stringify(v)}`);return ids('filteredWork().map(r=>r.id)');};
assert.deepEqual([...new Set([...where('remote'),...where('onsite'),...where('varies')])].sort(),routes.map(r=>r.id).sort());
for(const r of routes){assert.equal(where('remote').includes(r.id),r.arrangements.includes('remote'));assert.equal(where('onsite').includes(r.id),r.arrangements.some(x=>['onsite','hybrid'].includes(x)));}
assert.ok(ids("workRouteRows().filter(r=>w4WhereMatches(r,'US listing evidence')).map(r=>r.id)").every(id=>byId[id].eligibility==='US listing evidence'));
assert.ok(where('remote').includes('surge_ai.work.swe-environments'),'remote keeps Surge SWE');
// Search: worker words reach listings; "doctor" skips "doctorate"; phrases and padding behave.
const search=q=>{run(`resetWorkFilters();state.workQuery=${JSON.stringify(q)}`);return ids('filteredWork().map(r=>r.id)');};
assert.ok(search('medical').includes('pareto.work.forte-experts'));
assert.ok(search('physician').includes('pareto.work.forte-experts'));
assert.ok(!search('doctor').includes('scale_ai.work.outlier-statistics'));
assert.ok(search('beginner').includes('rws_trainai.work.community'));
assert.ok(search('no experience').includes('rws_trainai.work.community'));
assert.ok(search('code').length>0&&search('data labeling').length>0);
assert.deepEqual(search('  AIXI \t'),search('AIXI'));assert.ok(search('AIXI').every(id=>byId[id].company_id==='aixi'));
assert.equal(search('india').length,0);
run(`resetWorkFilters();state.workQuery='india';renderWork()`);
const html=node('work-cards').innerHTML;
assert.ok(html.includes('No listing mentions “india”')&&html.includes('data-work-clear="search"'));
assert.ok((html.match(/data-work-route=/g)||[]).length>=15,'india shows networks with per-project country rules');
run(`resetWorkFilters();state.workQuery='AIXI';renderWork()`);assert.ok(!node('work-cards').innerHTML.includes('work-suggested'),'company searches get no suggestions');
run(`resetWorkFilters();state.workPay='monthly';state.workGroup='Contributor bounties';renderWork()`);
assert.ok(node('work-cards').innerHTML.includes('No listing matches these filters.')&&node('work-cards').innerHTML.includes('data-work-clear="filters"'));
run('resetWorkFilters()');
// Counts and labels read the same on every surface (B1, B3, B5).
run('renderWork()');
const companiesReviewed=new Set(routes.map(r=>r.company_id)).size;
assert.equal(node('work-count').textContent,run('workResultsLabel(summarizeWorkResults(workRouteRows()))'));
run(`state.workSort='hourly';renderWork()`);
const sortNote=node('work-sort-note').textContent;
assert.ok(sortNote.includes(`of ${run('w4DiscoveryGroups(workRouteRows()).primary.length')} work routes`)&&!/open listing/.test(sortNote),sortNote);
run('resetWorkFilters()');
for(const r of routes.filter(r=>r.status==='no_route'))assert.equal(run(`w4Status(${JSON.stringify(r)})`),'No confirmed paid listing',r.id);
assert.ok(routes.some(r=>r.status==='no_route'),'fixture lost its no_route record');
// The safety note names the latest link check of the paid work listings, worked out from the data.
const latest=routes.filter(r=>g.contract.includes(r.id)||g.jobs.includes(r.id)).map(r=>[r.availability_checked_on,r.last_route_check?.date].filter(Boolean).sort().at(-1)).filter(Boolean).sort().at(-1);
const safetyLine=run('workSafetyHTML(workRouteRows())');
assert.ok(safetyLine.includes(run(`w4Date(${JSON.stringify(latest)})`)+'.'),'safety note lost the latest check date '+latest);
// Cards: one plain date line, no research codes, named links that open new tabs.
for(const route of routes){
 const card=run(`workCard(${JSON.stringify(route)})`),front=card.split('<details class="w4-details">')[0];
 assert.ok(!/Not yet checked|Undated terms|Pay periods unspecified|public_page_live|information_only_not_verified/.test(card),route.id);
 assert.ok(/Terms checked \d|Pay terms reviewed \d|Page checked \d|Recheck blocked \d|Recorded \d|Terms not rechecked/.test(front),route.id+' date line');
 assert.ok(card.includes('<span class="sr-only">: '+run(`w4Escape(${JSON.stringify(route.role)})`)),route.id+' link context');
 assert.ok(card.includes('(opens in a new tab)')||!/^https?:/.test(route.url),route.id+' new tab note');
}
// Profiles: same labels; safety note wherever a listing or career page is open.
let safety=0;
for(const c of data.companies){const s=run(`workSummary(${JSON.stringify(c.id)})`);if(s.includes('w4-safety'))safety++;assert.ok(!/More listed|Career directories|Other work & research routes|No work route/.test(s),c.id);}
assert.ok(safety>=30,'safety note on profile tabs: '+safety);
// Safety sources are public agency pages over https.
const tips=run('workSafetyHTML(workRouteRows())');
for(const href of tips.match(/href="[^"]+"/g))assert.match(href,/href="https:\/\/(consumer\.ftc\.gov|www\.ic3\.gov|pib\.gov\.in|reportfraud\.ftc\.gov|cybercrime\.gov\.in)\//);
console.log(JSON.stringify({buckets:Object.fromEntries(Object.entries(g).map(([k,v])=>[k,v.length])),hourlyRanges:ranged.length,latestCheck:latest,profileSafety:safety,status:'passed'}));
'''


class WorkListingsTest(unittest.TestCase):
    def test_work_listings_logic(self):
        tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
        stub = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets))
        result = subprocess.run([shutil.which("node") or "node", "-", str(ROOT / "data/canonical.json"), str(ROOT)], input=stub.split("(async()=>{", 1)[0] + CHECKS, text=True, cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
