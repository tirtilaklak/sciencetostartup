"""Shared discovery selectors, literal query transfer, exports and URL history."""
import unittest

from test_site_search import run_stub


class WorkDiscoveryContractTests(unittest.TestCase):
    def test_literal_search_and_semantic_filters(self):
        result = run_stub(r'''
run('initialize()');
for(const query of ['C++','C#','café','cafe\u0301','研究','Python','remote','medical']){
 const expected=plain(run(`selectWorkRoutes(workRouteRows(),{q:${JSON.stringify(query)}}).map(r=>r.id)`));
 assert.equal(run(`siteSearchWorkCount(${JSON.stringify(query)})`),expected.length,query);
 const globals=plain(run(`siteSearch(${JSON.stringify(query)},{limit:500}).filter(x=>x.type==='work').map(x=>x.id)`));
 assert.ok(globals.every(id=>expected.includes(id)),query+' global results must be in destination selection');
 const action=plain(run(`siteSearchView(${JSON.stringify(query)})`)).flatMap(group=>group.items).find(item=>item.action==='work');
 if(expected.length){assert.equal(action.query,query);assert.equal(new URLSearchParams(action.href.split('?')[1]).get('q'),query);}
}
const fixture={company_id:'mercor',role:'C++ C# café 研究',status:'listed',pay_label:'$32–90 / hour equivalent',pay_basis:'per_completed_task',numeric_pay:true,pay_terms:{unit:'task',hourly_comparable:false},route_kind:'named_listing',engagement_type:'employment',arrangements:['remote','onsite']};
run(`globalThis.discoveryFixture=${JSON.stringify(fixture)}`);
for(const q of ['C++','C#','CAFÉ','cafe\u0301','研究'])assert.equal(run(`selectWorkRoutes([discoveryFixture],{q:${JSON.stringify(q)}}).length`),1,q);
assert.equal(run(`selectWorkRoutes([discoveryFixture],{q:'C++',type:'employment',arrangement:'onsite',pay:'task'}).length`),1);
assert.equal(run(`selectWorkRoutes([discoveryFixture],{pay:'hourly'}).length`),0,'Task equivalents are not actual hourly pay');
assert.equal(run(`selectWorkRoutes([discoveryFixture],{type:'contract'}).length`),0,'Pay never infers engagement');
assert.equal(run(`w4HourlyRange(discoveryFixture)`),null);
for(const id of ['terac.work.ml-scenarios','afterquery.work.senior-software-engineer-security-infrastructure']){const destination=plain(run(`w4Destination(workRouteRows().find(r=>r.id===${JSON.stringify(id)}))`));assert.equal(destination.label,'Browse current company careers');assert.notEqual(destination.url,run(`workRouteRows().find(r=>r.id===${JSON.stringify(id)}).url`));}
const sageFront=run("workCard(workRouteRows().find(r=>r.id==='appen.work.sage-media'))").split('<details class="w4-details">')[0];assert.ok(sageFront.includes('Qualification tests and identity verification'));
const g2iFront=run("workCard(workRouteRows().find(r=>r.id==='g2i.work.senior-swe-training'))").split('<details class="w4-details">')[0];assert.ok(g2iFront.includes('Location sources conflict.'));
const summary=plain(run('summarizeWorkResults(workRouteRows())'));
assert.equal(summary.named,56);assert.equal(summary.programs,22);assert.equal(summary.careers,23);assert.equal(summary.outside,11);
assert.equal(summary.total,135);
assert.equal(summary.named+summary.programs+summary.careers+summary.outside+summary.other+summary.archived,summary.total);
assert.equal(run("w4FreshnessLabel(workRouteRows().find(r=>r.id==='appen.work.sage-media'))"),'Terms checked 8 Nov 2026');
run(`discoveryFixture.editorial_review={classified_on:'2099-01-01',receipts:[{id:'retrieval',approved:false,scope:'retrieval',result:'readable',checked_on:'2099-01-01'}]}`);
assert.equal(run('w4TermsReviewDate(discoveryFixture)'),null,'Classification/retrieval never refreshes terms');
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_complete_url_contract_and_stale_writer_cancellation(self):
        result = run_stub(r'''
run('initialize()');
const value={q:'C++ C# café 研究 /?&=+%',kind:'named',type:'employment',pay:'hourly',arrangement:'onsite',sort:'checked'};
const hash=run(`workHashFor(${JSON.stringify(value)})`);
assert.deepEqual(plain(run(`workCriteriaFromHash(${JSON.stringify(hash)})`)),value);
for(const bad of ['#work?q=%E0%A4%A&kind=bogus&type=__proto__&pay=all&sort=unknown','#work?q=%FF%ZZ'])assert.doesNotThrow(()=>run(`workCriteriaFromHash(${JSON.stringify(bad)})`));
for(const arrangement of ['US listing evidence','unknown']){const hash='#work?arrangement='+encodeURIComponent(arrangement);assert.equal(run(`workCriteriaFromHash(${JSON.stringify(hash)}).arrangement`),'');assert.equal(run(`workHashFor({arrangement:${JSON.stringify(arrangement)}})`),'#work');location.hash=hash;run('syncWorkRoute()');assert.equal(run('state.workEligibility'),'');assert.equal(run('filteredWork().length'),window.WORK_ROUTES.routes.length);assert.equal(location.hash,'#work');}
let pending=[];context.setTimeout=callback=>{pending.push(callback);return pending.length};context.clearTimeout=()=>{};
location.hash='#work';history.state={stsEntryKey:'work-a'};run('syncWorkRoute()');
run(`state.workQuery='C++';state.workKind='named';queueWorkRoute()`);
const delayed=pending.at(-1);
location.hash='#companies';history.state={stsEntryKey:'companies-b'};run('cancelWorkRouteWrite()');delayed();
assert.equal(location.hash,'#companies','Late typing never rewrites the new route');
location.hash='#work';history.state={stsEntryKey:'work-a'};run('syncWorkRoute(true)');
assert.equal(run('state.workQuery'),'C++');assert.equal(run('state.workKind'),'named');
assert.equal(location.hash,'#work?q=C%2B%2B&kind=named');
location.hash='#work';history.state={stsEntryKey:'work-new'};run('syncWorkRoute(false)');
assert.equal(run('state.workQuery'),'','A new bare work link starts unfiltered');
assert.equal(run('state.workKind'),'');
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exports_share_visible_selected_results(self):
        result = run_stub(r'''
(async()=>{
run('initialize()');
const taskus=plain(run("currentCompanyResult('taskus')"));
assert.equal(taskus.id,run("financialObservationFor('taskus').id"));
assert.equal(taskus.value,615121000);assert.equal(taskus.period,'H1 2026');assert.equal(taskus.scope,'company');
assert.equal(taskus.scope_label,'Whole company');assert.ok(taskus.source_urls.includes('taskus'));
location.hash='#work?q=Surge&kind=named';run('syncWorkRoute()');
const count=run('filteredWork().length');run('exportWorkCsv()');
const csv=await downloadedBlob.text();assert.ok(count>0,'Export regression fixture must contain real rows');
assert.equal(csv.trim().split(/\r?\n/).length,count+1);assert.ok(csv.includes('opportunity_kind'));assert.ok(csv.includes('search_query')&&csv.includes('Surge'));
assert.ok(csv.includes('terms_review_scope')&&csv.includes('original_application_url')&&csv.includes('assessment'));
location.hash='#work?q=Sage&kind=named';run('syncWorkRoute();exportWorkCsv()');const sageCsv=await downloadedBlob.text();
for(const value of ['Up to $15 / hour','US residence','MacBook Pro','Qualification tests and identity verification','2026-11-08','key_terms'])assert.ok(sageCsv.includes(value),value+' must remain in the Sage export');
run('state.query="taskus";exportCsv()');const companyCsv=await downloadedBlob.text();
assert.ok(companyCsv.includes('615121000')&&companyCsv.includes('H1 2026')&&companyCsv.includes('Whole company'));
})().catch(error=>{console.error(error);process.exitCode=1});
''')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
