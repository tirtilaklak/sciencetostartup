"""Check literal word-prefix company search using the current composed modules.

run_checks accepts an app source string for a bounded in-memory proposal review.
Normal execution tests the integrated source. No browser or source writes occur.
"""
import ast
import csv
import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "web/app.js").is_file() and (parent / "data/canonical.json").is_file())
CHECKS = r'''
(async()=>{
run('initialize()');
const original=run('JSON.stringify(DATA)'),sidecars=JSON.stringify([window.PROFILE_CONTENT,window.SOURCE_UPDATES,window.EDITORIAL]);
const sentence='Analyzes voice conversations as they happen to reduce manual note-taking by support workers.';
assert.ok(run(`profileProducts('taskus')`).some(product=>product.description===sentence),'Retain the TaskUs offering sentence');
const results=query=>{run(`Object.assign(state,{query:${JSON.stringify(query)},category:'',stage:'',financial:false,work:false,sort:'name'});renderDirectory()`);return plain(run('filtered().map(company=>company.id)'));};
const cases=[];
function exact(query,expected){const actual=results(query);assert.deepEqual(actual,expected,query);assert.equal(node('result-count').textContent,`Showing ${expected.length} of 39 companies`);cases.push({query,ids:actual});}
for(const query of ['Appen','APPEN',' \t appen \n','Appen Appen'])exact(query,['appen']);
for(const query of ['happen','TaskUs happen','happen TASKUS'])exact(query,['taskus']);
assert.ok(results('App').includes('appen'),'Company prefixes must remain searchable');
assert.ok(results('Appen annot').includes('appen'),'Product word prefixes must remain searchable');
for(const query of ['A.Team','a.team','A•Team','ATeams Inc.'])assert.ok(results(query).includes('a-team'),query+' company punctuation/alias');
for(const query of ['CrowdGen','ASX: APX','Appen Limited'])assert.ok(results(query).includes('appen'),query+' company alias');
for(const query of ['Labelbox WorldSim','WorldSim LABELBOX'])exact(query,['labelbox']);
exact('TaskUs happen unknown-prefix-sentinel',[]);
let identities=0;
for(const company of data.companies)for(const name of [company.name,...company.aliases]){assert.ok(results(name).includes(company.id),company.id+' identity '+name);identities++;}
for(const query of ['',' ','\t\r\n','\u00a0'])assert.equal(results(query).length,39);

// Isolated searchable-field fixtures distinguish leading prefixes from internal
// substrings. Restore every field before checking the original records.
const company=plain(run("companies['laude']")),product=plain(run("DATA.products.find(product=>product.company_id==='laude')"));
const editorial=window.EDITORIAL.entries.find(entry=>entry.company_id==='laude'),summary=editorial.summary;
const profile=window.PROFILE_CONTENT.entries.find(entry=>entry.company_id==='laude'),offerings=profile.products;
const casesBefore=cases.length;
try{
 run(`companies.laude.name='NamePrefixSentinel';companies.laude.aliases.push('AliasPrefixSentinel');companies.laude.description+=' DescriptionPrefixSentinel cafézulu e\\u0301appen [literal] C++Sentinel a.*sentinel A(B)sentinel work?sentinel unit|sentinel cost$sentinel slash\\\\sentinel';`);
 editorial.summary='ModelPrefixSentinel';profile.products=[{name:'OfferingPrefixSentinel',description:'OfferingDescriptionSentinel',aliases:['OfferingAliasSentinel'],record_ids:[],claim_ids:[]}];
 run(`DATA.products.find(product=>product.id===${JSON.stringify(product.id)}).name='ProductPrefixSentinel';DATA.products.find(product=>product.id===${JSON.stringify(product.id)}).work_performed='WorkPerformedSentinel';`);
 for(const query of ['nameprefix','aliasprefix','descriptionprefix','modelprefix','productprefix','workperformed','offeringprefix','offeringdescription','offeringalias'])exact(query,['laude']);
 exact('nameprefix offeringalias workperformed',['laude']);
 for(const query of ['CAFÉZULU','café','[literal]','C++Sentinel','a.*sentinel','A(B)sentinel','work?sentinel','unit|sentinel','cost$sentinel','slash\\sentinel'])exact(query,['laude']);
 for(const query of ['afézulu','zulu','refixsentinel','aZZsentinel','AxxBsentinel','workXsentinel'])exact(query,[]);
 exact('Appen',['appen']); // A combining mark before appen remains inside a word.
 for(const query of ['[','(',')','+','*','?','|','$','\\'])results(query); // Literal metacharacters never become regex syntax.
}finally{
 editorial.summary=summary;profile.products=offerings;
 run(`{const target=companies.laude;Object.keys(target).forEach(key=>delete target[key]);Object.assign(target,${JSON.stringify(company)});const row=DATA.products.find(product=>product.id===${JSON.stringify(product.id)});Object.keys(row).forEach(key=>delete row[key]);Object.assign(row,${JSON.stringify(product)});}`);
}
const unicodeAndLiteralCases=cases.length-casesBefore;
const selection=['trajectory_labs_pbc','quesma','rws_trainai'];run(`setSelection(${JSON.stringify(selection)})`);
node('search').callbacks.input({target:{value:'Appen'}});
assert.deepEqual(plain(run('filtered().map(company=>company.id)')),['appen']);assert.deepEqual(plain(run('state.selected')),selection);
assert.ok(node('download-csv').textContent.includes('Current company results · 1 row'));
run('exportCsv()');const csv=await downloadedBlob.text();
node('reset').callbacks.click();assert.equal(run('state.query'),'');assert.equal(run('filtered().length'),39);
assert.equal(run('JSON.stringify(DATA)'),original,'Search fixtures or rendering changed research');
assert.equal(JSON.stringify([window.PROFILE_CONTENT,window.SOURCE_UPDATES,window.EDITORIAL]),sidecars,'Search changed presentation data');
assert.ok(run(`profileProducts('taskus')`).some(product=>product.description===sentence),'TaskUs copy changed');
console.log(JSON.stringify({status:'passed',cases,identities,unicodeAndLiteralCases,csv,canonicalAndSidecarsUnchanged:true,taskusCopyUnchanged:true,selectionAndResetPreserved:true,browserVerified:false}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


def run_checks(app_source=None):
    protected = [ROOT / name for name in (
        "data/canonical.json", "data/source-updates.json", "data/profile-content.json",
        "data/profile-afterquery.json", "data/editorial.json", "web/app.js",
    )]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
    stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
    prefix = stub.split("(async()=>{", 1)[0]
    if app_source is not None:
        loader = "fs.readFileSync(path.join(root,f),'utf8')"
        assert prefix.count(loader) == 1
        prefix = prefix.replace(loader, "(f==='web/app.js'?" + json.dumps(app_source) + ":" + loader + ")")
    result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-",
                             str(ROOT / "data/canonical.json"), str(ROOT)],
                            input=prefix + CHECKS, text=True, cwd=ROOT, capture_output=True)
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected} == before
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    report = json.loads(result.stdout)
    rows = list(csv.reader(io.StringIO(report.pop("csv"))))
    assert rows[0][0] == "company_id" and [row[0] for row in rows[1:]] == ["appen"]
    report["filteredCsvIds"] = [row[0] for row in rows[1:]]
    report["sourceMode"] = "in-memory proposal" if app_source is not None else "current production files"
    return report


if __name__ == "__main__":
    print(json.dumps(run_checks()))
