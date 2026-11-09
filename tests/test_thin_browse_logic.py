"""Thin browse state must retain financial, filter, search and comparison behavior."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_site_search import run_stub

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from presentation import build_presentation


class ThinBrowseLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read = lambda name: json.loads((ROOT / "data" / name).read_text())
        profiles = read("profile-content.json")
        profiles["entries"] = [entry for entry in profiles["entries"] if entry["company_id"] != "afterquery"] + [read("profile-afterquery.json")]
        sidecars = {"EDITORIAL": read("editorial.json"), "PROFILE_CONTENT": profiles,
                    "COMPANY_EVENTS": read("company-events.json"), "WORK_ROUTES": read("work-routes.json"),
                    "SOURCE_UPDATES": read("source-updates.json"), "BUSINESS_HEALTH": read("business-health.json")}
        with tempfile.TemporaryDirectory(prefix="thin-browse-behavior-") as directory:
            summary, _ = build_presentation(read("canonical.json"), Path(directory), ROOT, sidecars, read("editorial-release.json"))
            search = json.loads((Path(directory) / summary["fullSearch"]["href"].lstrip("/")).read_text())
        cls.projection = {"bootstrap": summary["bootstrap"], "companySummaries": summary["companySummaries"], "work": summary["work"], "search": search, "statistics": summary["statistics"]}

    def test_financial_cards_filters_exports_and_product_search_survive_empty_detail_arrays(self):
        result = run_stub("const projection=" + json.dumps(self.projection) + ";" + r'''
const baseline=plain(run(`(()=>{
 const summaries=Object.fromEntries(DATA.companies.map(c=>[c.id,{result:currentCompanyResult(c.id),financial:Boolean(preferredFinancial(c.id)),stage:stageFor(c.id),products:profileProducts(c.id)}]));
 state.financial=true;const financialIds=filtered().map(c=>c.id);state.financial=false;
 const companyQueries=Object.fromEntries(['TaskUs','WorldSim','Café','C++','Labelbox WorldSim'].map(q=>{state.query=q;return[q,filtered().map(c=>c.id)];}));state.query='';
 const workQueries=Object.fromEntries(['C++','C#','Python','medical','no experience','café','Sage','AIXI'].map(q=>[q,selectWorkRoutes(workRouteRows(),{q}).map(r=>r.id)]));
 return{summaries,financialIds,companyQueries,workQueries};})()`));
context.projection=projection;
run(`
window.SUMMARY_INDEX={companySummaries:projection.companySummaries};window.COMPANY_CONTEXTS_READY=new Set();
for(const [key,rows]of Object.entries(projection.bootstrap))if(Array.isArray(rows))DATA[key]=rows;
for(const map of [claims,sources,people,investors])for(const key of Object.keys(map))delete map[key];
window.PROFILE_CONTENT={entries:[]};window.SOURCE_UPDATES={updates:[],evidence_context:{corrections:[]}};window.BUSINESS_HEALTH={};window.WORK_ROUTES=projection.work;
refreshResearchIndexes();
`);
for(const [id,expected]of Object.entries(baseline.summaries)){
 assert.deepEqual(plain(run(`currentCompanyResult(${JSON.stringify(id)})`)),expected.result,id+' current export');
 assert.equal(run(`hasFinancialEvidence(${JSON.stringify(id)})`),expected.financial,id+' revenue filter');
 assert.equal(run(`stageFor(${JSON.stringify(id)})`),expected.stage,id+' delivery stage');
 const card=run(`card(companies[${JSON.stringify(id)}])`);
 if(expected.financial){assert.ok(!card.includes('Revenue not disclosed'),id+' lost its selected financial');assert.ok(card.includes(run(`esc(${JSON.stringify(expected.result.display)})`)),id+' value');}
 const first=plain(run(`profileProducts(${JSON.stringify(id)})`));
 assert.equal(first[0]?.name||null,expected.products[0]?.name||null,id+' first offering');
}
run('state.financial=true');assert.deepEqual(plain(run('filtered().map(c=>c.id)')),baseline.financialIds);run('state.financial=false');
location.hash='#companies';const previousCompare=node('compare-content').innerHTML;run(`setSelection(['mercor','taskus'])`);
assert.deepEqual(plain(run('state.selected')),['mercor','taskus']);assert.equal(node('compare-content').innerHTML,previousCompare,'Off-route selection must not render missing comparison details');
run(`window.ensureSearchContext=()=>Promise.resolve(window.SEARCH_INDEX);state.query='WorldSim'`);
assert.throws(()=>run('filtered()'),/search context is not ready/);
assert.throws(()=>run(`selectWorkRoutes(workRouteRows(),{q:'Python'})`),/search context is not ready/);
run('window.SEARCH_INDEX=projection.search');
for(const [q,expected]of Object.entries(baseline.companyQueries)){run(`state.query=${JSON.stringify(q)}`);assert.deepEqual(plain(run('filtered().map(c=>c.id)')),expected,q+' company search');}
for(const [q,expected]of Object.entries(baseline.workQueries))assert.deepEqual(plain(run(`selectWorkRoutes(workRouteRows(),{q:${JSON.stringify(q)}}).map(r=>r.id)`)),expected,q+' work search');
for(const [id,expected]of Object.entries(baseline.summaries))assert.deepEqual(plain(run(`profileProducts(${JSON.stringify(id)})`)),expected.products,id+' searchable products');
const sage=run(`workCard(workRouteRows().find(r=>r.id==='appen.work.sage-media'))`);
for(const text of ['Up to $15 / hour','US residence','MacBook Pro','Qualification tests and identity verification','Read the full research profile and source history','https://crowdgen.com/sage-en-us/'])assert.ok(sage.includes(text),text);
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_work_csv_is_identical_before_and_after_full_context_hydration(self):
        result = run_stub("const projection=" + json.dumps(self.projection) + ";" + r'''
(async()=>{
context.projection=projection;
run(`globalThis.fullWorkForTest=window.WORK_ROUTES;globalThis.fullClaimsForTest={...claims};globalThis.fullSourcesForTest={...sources};
window.WORK_ROUTES=projection.work;for(const key of Object.keys(claims))delete claims[key];for(const key of Object.keys(sources))delete sources[key];
window.SEARCH_INDEX=projection.search;location.hash='#work';applyWorkCriteria({sort:'hourly'});exportWorkCsv();`);
const before=await downloadedBlob.text();
run(`Object.assign(claims,fullClaimsForTest);Object.assign(sources,fullSourcesForTest);window.WORK_ROUTES=fullWorkForTest;exportWorkCsv();`);
const after=await downloadedBlob.text();
assert.equal(before,after,'Profile hydration must not change current-results facts, conditions, metadata or order');
assert.ok(before.includes('field_review_metadata')&&before.includes('full_research_profile_url'));
for(const text of ['Qualification tests and identity verification','US residence','MacBook Pro','Up to $15 / hour','2026-11-08','Recorded US location'])assert.ok(before.includes(text),text);
assert.ok(before.includes('https://sciencetostartup.com/company/appen/'));
})().catch(error=>{console.error(error);process.exitCode=1});
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_overview_research_totals_do_not_change_with_loaded_company_contexts(self):
        result = run_stub("const projection=" + json.dumps(self.projection) + ";" + r'''
run('renderStoryCheck()');const full=node('overview-check').innerHTML;
context.projection=projection;
run(`globalThis.allClaimsForTest=DATA.claims;globalThis.allSourcesForTest=DATA.sources;
window.SUMMARY_INDEX={statistics:projection.statistics};DATA.claims=allClaimsForTest.slice(0,10);DATA.sources=allSourcesForTest.slice(0,10);renderStoryCheck();`);
assert.equal(node('overview-check').innerHTML,full,'Initial overview must report full research counts, not only its loaded records');
run(`DATA.claims=allClaimsForTest.filter(claim=>['mercor','appen'].includes(claim.company_id));DATA.sources=allSourcesForTest.filter(source=>['mercor','appen'].includes(source.company_id));renderStoryCheck();`);
assert.equal(node('overview-check').innerHTML,full,'Opening company contexts must not change overview grades or coverage');
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_company_csv_readouts_load_on_explicit_export_and_remain_identical_after_hydration(self):
        result = run_stub("const projection=" + json.dumps(self.projection) + ";" + r'''
(async()=>{
run(`exportCsv();globalThis.fullDataRowsForTest=Object.fromEntries(Object.entries(DATA).filter(([,value])=>Array.isArray(value)));`);
const full=await downloadedBlob.text();context.projection=projection;
// Read the emitted CSV itself; expected labels come from the source schema, not workType().
const cells=[...full.replace(/^\ufeff/,'').matchAll(/"((?:[^"]|"")*)"(?:,|\r\n|$)/g)].map(match=>match[1].replaceAll('""','"'));
const width=24,header=cells.slice(0,width),workColumn=header.indexOf('work_route'),rows=Array.from({length:(cells.length-width)/width},(_,i)=>cells.slice(width*(i+1),width*(i+2)));
assert.equal(rows.length,39);assert.equal(workColumn,18);
const sourceWork=readJSON('data/work-routes.json').routes,archive=new Set(['historical','closed','contributions','paused','no_route','inquiry','information']);
for(const row of rows){const records=sourceWork.filter(route=>route.company_id===row[0]),primary=records.filter(route=>!archive.has(route.status)&&route.ai_data_work!==false&&['named_listing','network_program'].includes(route.route_kind)),kinds=new Set(primary.map(route=>route.route_kind)),careers=records.some(route=>!archive.has(route.status)&&route.route_kind==='career_page');
 const expected=[kinds.has('named_listing')?'Named listings':'',kinds.has('network_program')?'Networks and programs':''].filter(Boolean).join(' · ')||(careers?'Career page only':records.length?'No confirmed paid listing':'Paid work not reviewed yet');
 assert.equal(row[workColumn],expected,row[0]+' exported opportunity summary must follow approved kinds');
}
run(`window.SUMMARY_INDEX={companySummaries:projection.companySummaries};window.COMPANY_CONTEXTS_READY=new Set();
for(const [key,value]of Object.entries(projection.bootstrap))if(Array.isArray(value))DATA[key]=value;
window.WORK_ROUTES=projection.work;window.ensureSearchContext=()=>Promise.reject(new Error('offline'));`);
await run('exportCsv()');
assert.ok(node('company-export-status').innerHTML.includes('data-retry-company-export'),'Failed explicit export has a nearby retry');
assert.ok(node('company-export-status').innerHTML.includes('/research.json'),'Full research remains available');
assert.equal(node('download-csv').disabled,false);
run(`window.ensureSearchContext=()=>Promise.resolve().then(()=>window.SEARCH_INDEX=projection.search)`);
await run('exportCsv()');const thin=await downloadedBlob.text();
assert.equal(thin,full,'Explicit export must retain every original company readout and column before context hydration');
assert.equal(run('DATA.editorial_readouts.length'),0,'The complete readouts must not be embedded into initial research data');
assert.equal(node('company-export-status').hidden,true);
run(`for(const [key,value]of Object.entries(fullDataRowsForTest))DATA[key]=value;window.COMPANY_CONTEXTS_READY=new Set(DATA.companies.map(company=>company.id));exportCsv();`);
assert.equal(await downloadedBlob.text(),full,'Company hydration must not change current-results CSV bytes');
})().catch(error=>{console.error(error);process.exitCode=1});
''')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
