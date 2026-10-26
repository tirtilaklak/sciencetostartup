"""Exercise supported optional-data fallbacks with browser storage unavailable.

This runs actual presentation modules and startup in the existing VM DOM fixture.
It does not corrupt required inline research, simulate browser image failures,
or claim browser rendering/accessibility coverage. No browser or network is used.
"""

import ast
import hashlib
import json
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
prefix = stub.split("(async()=>{", 1)[0]
marker = "// The icon script runs first."
assert prefix.count(marker) == 1
prefix = prefix.replace(
    marker,
    r"""
let storageGetterAttempts=0,networkAttempts=0;
const blockedStorage=()=>{storageGetterAttempts++;throw new Error('Storage denied by browser policy');};
for(const global of [window,context])for(const key of ['localStorage','sessionStorage'])Object.defineProperty(global,key,{configurable:true,get:blockedStorage});
const blockedNetwork=()=>{networkAttempts++;throw new Error('Network unavailable in failure-state fixture');};
window.fetch=context.fetch=blockedNetwork;
window.LINK_HEALTH=readJSON('data/link-health.json');
for(const key of options.missing||[])delete window[key];
if(options.linkHealth!==undefined)window.LINK_HEALTH=options.linkHealth;
""" + marker,
)
assert "'web/icons.js','web/app.js'" in prefix
prefix = prefix.replace("'web/icons.js','web/app.js'", "'web/icons.js','web/link-health.js','web/app.js'")
setup = "function harness(options={}){\n" + prefix + "\nreturn {run,node,context,document,window,history,location,windowCallbacks,getAttempts:()=>({storage:storageGetterAttempts,network:networkAttempts})};}\n"

checks = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=process.argv[3],data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const optional=['LOGOS','PROFILE_CONTENT','SOURCE_UPDATES','WORK_ROUTES','RESEARCH_ALIASES','LINK_HEALTH'];
const cases=[{name:'blocked-storage'},{name:'all-supported-optionals-absent',missing:optional},...optional.map(key=>({name:'missing-'+key.toLowerCase(),missing:[key]})),{name:'invalid-optional-link-observations',linkHealth:{entries:[null,{}, {url:'javascript:alert(1)',status:'not_found',checked_on:'2026-10-16'}, {url:'https://example.org/invalid-date',status:'not_found',checked_on:'2026-02-30'}, {url:'https://example.org/unknown-status',status:'constructor',checked_on:'2026-10-16'}, {url:'https://example.org/dated',status:'not_found',checked_on:'2026-10-16'}]}}];
const reports=[];
for(const options of cases){
 const h=harness(options),before=h.run('JSON.stringify(DATA)'),checks=[];
 const check=(name,fn)=>{fn();checks.push(name);};
 check('startup-registers-handlers',()=>{h.run('initialize()');assert.equal(typeof h.node('search').callbacks.input,'function');assert.equal(typeof h.node('compare-preset').callbacks.change,'function');assert.ok(h.windowCallbacks.hashchange?.length);});
 check('all-company-results-remain',()=>{assert.equal(h.run('filtered().length'),39);assert.equal((h.node('company-cards').innerHTML.match(/data-company-card=/g)||[]).length,39);assert.ok(!h.node('company-cards').innerHTML.includes('[object Object]'));});
 check('search-remains-interactive',()=>{h.node('search').callbacks.input({target:{value:'AfterQuery'}});assert.equal(h.run('filtered().length'),1);h.run('reset()');assert.equal(h.run('filtered().length'),39);});
 check('selection-rejects-invalid-ids-and-deduplicates',()=>{h.run('setSelection(["constructor","__proto__","afterquery","afterquery","elorian","appen","taskus"])');assert.equal(h.run('state.selected.join("|")'),'afterquery|elorian|appen');assert.equal(h.node('nav-count').textContent,'(3)');});
 check('selection-limit-and-clear-remain-interactive',()=>{h.run('chooseCompare("taskus",true)');assert.equal(h.run('state.selected.join("|")'),'afterquery|elorian|appen');assert.equal(h.node('tray-text').textContent,'Three selected. Remove one to add another.');h.run('setSelection([])');assert.equal(h.run('state.selected.length'),0);});
 check('unknown-profile-recovers-through-real-navigation-handler',()=>{h.location.hash='#company/constructor/%5D%5B';h.windowCallbacks.hashchange.forEach(fn=>fn({type:'hashchange'}));assert.ok(h.node('profile-view').innerHTML.includes('Profile not found'));h.location.hash='#companies';h.windowCallbacks.hashchange.forEach(fn=>fn({type:'hashchange'}));assert.equal(h.node('companies-view').hidden,false);});
 check('canonical-profile-can-render',()=>{h.location.hash='#company/afterquery';h.run('route()');assert.ok(h.node('profile-view').innerHTML.includes('<h1>AfterQuery</h1>'));});
 check('work-renders-with-supported-optional-fallback',()=>{h.location.hash='#work';h.run('route()');if(options.missing?.includes('WORK_ROUTES')){assert.equal(h.run('workRouteRows().length'),0);assert.ok(h.node('work-cards').innerHTML.includes('No listings are available right now.'));}else{assert.equal(h.run('workRouteRows().length'),135);assert.ok(h.node('work-cards').innerHTML.includes('data-work-route='));}});
 if(options.missing?.includes('LOGOS'))check('missing-logo-provenance-falls-back-to-names',()=>{assert.ok(h.node('company-cards').innerHTML.includes('brand-text'));assert.equal((h.node('company-cards').innerHTML.match(/<img /g)||[]).length,0);});
 if(options.missing?.includes('SOURCE_UPDATES'))check('missing-source-updates-retain-canonical-values',()=>{assert.equal(h.run('sourceUpdatesFor("elorian").length'),0);assert.equal(h.run('sourceUpdateUnknownText("elorian","Original unknown statement.")'),'Original unknown statement.');});
 if(options.missing?.includes('PROFILE_CONTENT'))check('missing-curation-retains-record-backed-products',()=>{assert.equal(h.run('Object.keys(profileContent("afterquery")).length'),0);assert.ok(h.run('profileProducts("afterquery").length')>0);assert.ok(h.run('profileProducts("afterquery").every(p=>p.record_ids.length&&p.claim_ids.length)'));});
 if(options.missing?.includes('RESEARCH_ALIASES'))check('missing-alias-map-keeps-unknown-id-unknown',()=>{h.location.hash='#company/after-query';h.run('route()');assert.ok(h.node('profile-view').innerHTML.includes('Profile not found'));assert.equal(h.location.hash,'#company/after-query');});
 if(options.missing?.includes('LINK_HEALTH'))check('missing-link-observations-add-no-availability-label',()=>assert.equal(h.window.linkAvailabilityHTML('https://example.org/dated'),''));
 if(options.linkHealth)check('malformed-link-observations-are-skipped-with-valid-observations-retained',()=>{assert.equal(h.window.linkAvailabilityHTML('javascript:alert(1)'),'');assert.equal(h.window.linkAvailabilityHTML('https://example.org/invalid-date'),'');assert.equal(h.window.linkAvailabilityHTML('https://example.org/unknown-status'),'');assert.ok(h.window.linkAvailabilityHTML('https://example.org/dated').includes('Page unavailable'));});
 check('research-remains-byte-identical-in-memory',()=>assert.equal(h.run('JSON.stringify(DATA)'),before));
 check('storage-and-network-are-never-accessed',()=>assert.deepEqual(h.getAttempts(),{storage:0,network:0}));
 reports.push({name:options.name,checks,passed:checks.length});
}
console.log(JSON.stringify({cases:reports.length,checks:reports.reduce((total,report)=>total+report.passed,0),reports,browser_verified:false,network_used:false,required_data_corruption_tested:false}));
"""

source_paths = [
    "web/icons.js", "web/link-health.js", "web/app.js", "web/editorial.js",
    "web/work-v3.js", "web/work-v4.js", "web/profiles-v2.js", "web/source-updates.js", "web/site-nav.js",
    "data/canonical.json", "data/editorial.json", "data/logo-provenance.json",
    "data/work-routes.json", "data/profile-content.json", "data/profile-afterquery.json",
    "data/source-updates.json", "data/link-health.json", "docs/research-id-crosswalk.json",
    "tests/js_logic.py",
]
source_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_paths}
result = subprocess.run(
    [shutil.which("node") or "/opt/homebrew/bin/node", "-", str(ROOT / "data/canonical.json"), str(ROOT)],
    input=setup + checks, text=True, capture_output=True, cwd=ROOT,
)
assert source_hashes == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_paths}
if result.returncode:
    print(result.stdout, end="")
    print(result.stderr, end="")
else:
    report = json.loads(result.stdout)
    report["source_sha256"] = source_hashes
    print(json.dumps(report, indent=2))
raise SystemExit(result.returncode)
