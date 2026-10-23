"""Global search: ranking, reachability and escaping, run on the real data in the JS logic stub."""
import ast
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SiteSearchTests(unittest.TestCase):
    def test_every_company_listing_product_and_page_is_findable(self):
        tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
        stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
        checks = r'''
run('initialize()');
const search=(q,opts={})=>plain(run(`siteSearch(${JSON.stringify(q)},${JSON.stringify(opts)})`));
const view=q=>plain(run(`siteSearchView(${JSON.stringify(q)})`)).flatMap(g=>g.items);
assert.equal(search('').length,0,'An empty query lists nothing');
assert.equal(search('  ').length,0);
// Aliases and brands lead to their company.
for(const [q,id] of [['outlier','scale_ai'],['Remotasks','scale_ai'],['mindrift','toloka'],['alignerr','labelbox'],['DataAnnotation','surge_ai'],['apx','appen'],['Scale AI','scale_ai'],['scale-ai','scale_ai']]){
 const first=search(q)[0];assert.equal(first?.type,'company',q);assert.equal(first.id,id,q);
}
assert.ok(search('outlier')[0].meta.startsWith('Also known as Outlier'),'Alias matches say which name matched');
// Pages answer by name and by plain words.
for(const [q,id] of [['corrections','corrections'],['contact','about'],['musa ozdem','about'],['csv','downloads'],['vs','compare'],['jobs','work'],['method','method'],['grades','labels'],['neolab','venture']]){
 const first=search(q)[0];assert.equal(first?.type,'page',q);assert.equal(first.id,id,q);assert.equal(first.href,'#'+id,q);
}
// One slip still finds the company.
for(const [q,id] of [['mecor','mercor'],['lablebox','labelbox'],['scael','scale_ai']])assert.equal(search(q)[0]?.id,id,q);
// Every company: Enter opens it after at most four letters of its name, and two letters list it in the top five.
let letters=0;
for(const c of data.companies){
 let n=1;while(n<=4&&view(c.name.slice(0,n))[0]?.href!=='#company/'+c.id)n++;
 assert.ok(n<=4,c.name+' needs more than four letters');letters+=n;
 assert.ok(search(c.name.slice(0,2)).filter(r=>r.type==='company').slice(0,5).some(r=>r.id===c.id),c.name+' not in the top five for two letters');
}
// Every listing and product is indexed and found by its own name.
const index=plain(run('siteSearchIndex().map(e=>({type:e.type,id:e.id,name:e.name}))'));
const routes=window.WORK_ROUTES.routes,products=index.filter(e=>e.type==='product');
assert.equal(index.filter(e=>e.type==='work').length,routes.length);
assert.equal(index.filter(e=>e.type==='company').length,data.companies.length);
assert.ok(products.length>=150,'Products are indexed');
for(const r of routes)assert.ok(search(r.role,{types:['work'],limit:200}).some(x=>x.id===r.id),'listing not found by its role: '+r.id);
for(const p of products)assert.ok(search(p.name,{types:['product'],limit:200}).some(x=>x.id===p.id),'product not found by its name: '+p.id);
// Work listings link to the company's work tab; generic filter words offer the full Paid work search first.
assert.ok(search('statistics',{types:['work']}).every(r=>/^#company\/[a-z0-9_-]+\/work$/.test(r.href)));
const remote=view('remote')[0];assert.equal(remote.action,'work');assert.equal(remote.query,'remote');
run(`state.workQuery='remote'`);assert.ok(remote.name.includes(String(run('filteredWork().length'))),'Listing count matches the Paid work page');run(`state.workQuery=''`);
// Results stay grouped by type, and text is escaped before highlighting.
const types=search('ai').map(r=>r.type);assert.equal(types.join(),types.filter((t,i)=>i===0||t!==types[i-1]).flatMap(t=>types.filter(x=>x===t)).join());
assert.equal(run(`siteSearchMark('Scale AI',['sc'])`),'<mark>Sc</mark>ale AI');
assert.ok(!run(`siteSearchMark('<img src=x onerror=alert(1)>',['img'])`).includes('<img'),'Highlighting escapes markup');
console.log(JSON.stringify({companies:data.companies.length,average_letters_until_enter_opens_company:+(letters/data.companies.length).toFixed(2),listings:routes.length,products:products.length,browser_verified:false}));
'''
        result = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-", str(ROOT / "data/canonical.json"), str(ROOT)], input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
