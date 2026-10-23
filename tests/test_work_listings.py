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
for(const id of g.closed)assert.ok(['historical','closed','contributions','paused','no_route','inquiry','information'].includes(byId[id].status),id);
for(const id of g.boards)assert.equal(byId[id].status,'careers');
for(const id of g.outside)assert.equal(byId[id].ai_data_work,false);
// Persona fits sit in open blocks, not in closed groups.
for(const id of ['afterquery.work.world-models','surge_ai.work.swe-environments','elorian.work.model-safety','terac.work.ml-scenarios','toloka.work.mindrift-code','terac.work.rl-environment-creation','afterquery.work.fullstack-evaluation'])assert.ok(g.hourly.includes(id),'hourly fit '+id);
for(const id of ['micro1.work.everyday-tasks','rws_trainai.work.community','toloka.work.toloka-work-now-on-mindrift'])assert.ok(g.task.includes(id),'task fit '+id);
assert.ok(g.project.includes('prolific.work.study-participant'));
// Hourly ranges: only labels that state a rate per hour, never a conflict, all read as published.
const ranged=ids('workRouteRows().filter(w4HourlyRange).map(r=>[r.id,w4HourlyRange(r)])');
assert.equal(ranged.length,20);
for(const [id,range] of ranged){assert.match(byId[id].pay_label,/\/\s*(approved\s+)?hour/i,id);assert.notEqual(byId[id].status,'pay_conflict');assert.ok(range.high>=(range.low??0),id);}
assert.deepEqual(plain(run(`w4HourlyRange(${JSON.stringify(byId['scale_ai.work.outlier-statistics'])})`)),{currency:'$',low:null,high:150,open:false});
assert.deepEqual(plain(run(`w4HourlyRange(${JSON.stringify(byId['surge_ai.work.swe-environments'])})`)),{currency:'$',low:100,high:150,open:true});
assert.equal(run(`w4HourlyRange(${JSON.stringify(byId['afterquery.work.college-swe'])})`),null);
// Highest hourly rate: the top of the range never rises down the block; the conflict listing is last.
const sorted=ids(`w4RouteGroups(workRouteRows(),'hourly').hourly.map(r=>r.id)`);
const highs=sorted.map(id=>run(`w4HourlyRange(${JSON.stringify(byId[id])})`)?.high??-1);
for(let i=1;i<highs.length;i++)if(highs[i]>=0)assert.ok(highs[i]<=highs[i-1],'rate order at '+sorted[i]);
assert.equal(sorted.at(-1),'afterquery.work.college-swe');
assert.deepEqual(sorted.slice(0,4),['afterquery.work.world-models','terac.work.finance-experts','surge_ai.work.swe-environments','scale_ai.work.outlier-statistics']);
// A non-USD hourly rate never outranks a USD one and is never compared by amount.
assert.ok(run(`w4RateOrder({...${JSON.stringify(byId['appen.work.sage-media'])}},{...${JSON.stringify(byId['appen.work.sage-media'])},pay_label:'£900 / hour'})`)<0);
// Pay filter values, including the two the old tests use.
const pay=v=>{run(`resetWorkFilters();state.workPay=${JSON.stringify(v)}`);return ids('filteredWork().map(r=>r.id)');};
assert.deepEqual(pay('task').sort(),['datacurve.work.shipd-bounties','micro1.work.everyday-tasks','rws_trainai.work.community','toloka.work.mindrift-code','toloka.work.toloka-work-now-on-mindrift']);
assert.equal(pay('hourly').length,20);assert.equal(pay('monthly').length,6);assert.equal(pay('yearly').length,43);
assert.equal(pay('numeric').length+pay('undisclosed').length,routes.length);
// Where you work: the three new values split every listing; the US value still filters on the research field.
const where=v=>{run(`resetWorkFilters();state.workEligibility=${JSON.stringify(v)}`);return ids('filteredWork().map(r=>r.id)');};
assert.equal(where('remote').length+where('onsite').length+where('varies').length,routes.length);
assert.ok(where('US listing evidence').every(id=>byId[id].eligibility==='US listing evidence'));
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
// Cards: one plain date line, no research codes, named links that open new tabs.
for(const route of routes){
 const card=run(`workCard(${JSON.stringify(route)})`),front=card.split('<details class="w4-details">')[0];
 assert.ok(!/Not yet checked|Undated terms|Pay periods unspecified|public_page_live|information_only_not_verified/.test(card),route.id);
 assert.ok(/Checked \d|Reviewed \d|Link not rechecked/.test(front),route.id+' date line');
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
console.log(JSON.stringify({buckets:Object.fromEntries(Object.entries(g).map(([k,v])=>[k,v.length])),hourlyRanges:ranged.length,profileSafety:safety,status:'passed'}));
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
