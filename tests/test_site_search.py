"""Global search: ranking, reachability, escaping and the search dialog, run on the real data in the JS logic stub."""
import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_stub(checks):
    """Run checks after the JS logic stub has loaded every page script with the real data."""
    tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
    stub = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "STUB" for target in node.targets))
    return subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", "-", str(ROOT / "data/canonical.json"), str(ROOT)], input=stub.split("(async()=>{", 1)[0] + checks, text=True, cwd=ROOT, capture_output=True)


class SiteSearchTests(unittest.TestCase):
    def test_every_company_listing_product_and_page_is_findable(self):
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
        result = run_stub(checks)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())

    def test_results_list_is_not_a_tab_stop(self):
        # The field owns the keyboard (a combobox). A scrolling list without tabindex="-1" becomes a Tab stop
        # where the arrow keys only scroll and Enter does nothing.
        template = (ROOT / "web/index.html").read_text()
        field = re.search(r'<input id="site-search-input"[^>]*>', template).group()
        listbox = re.search(r'<div id="site-search-results"[^>]*>', template).group()
        for attribute in ('role="combobox"', 'aria-controls="site-search-results"', 'aria-expanded="false"', 'aria-autocomplete="list"'):
            self.assertIn(attribute, field)
        for attribute in ('role="listbox"', 'tabindex="-1"', 'aria-label="Search results"', "hidden"):
            self.assertIn(attribute, listbox)

    def test_search_dialog_keyboard(self):
        checks = r'''
run('initialize()');
// A little more DOM than the stub has: options read back from the rendered list, synthetic input events.
context.Event=class{constructor(type,init={}){this.type=type;this.bubbles=Boolean(init.bubbles);this.isTrusted=false;}};
node('work-search').dispatchEvent=function(event){event.target=this;this.callbacks[event.type]?.(event);};
node('site-search-input').select=()=>{};
const options=new Map();
const option=id=>{if(!options.has(id)){const classes=new Set(),el={id,classes,setAttribute(k,v){this[k]=v;},scrollIntoView(){},classList:{toggle:(c,on)=>on?classes.add(c):classes.delete(c),remove:c=>classes.delete(c)}};options.set(id,el);}return options.get(id);};
const rendered=()=>[...node('site-search-results').innerHTML.matchAll(/<div class="[^"]*" id="(site-search-option-\d+)" role="option"/g)].map(m=>m[1]);
const anyAll=document.querySelectorAll;
document.querySelectorAll=s=>s==='#site-search-results [role=option]'?rendered().map(option):anyAll(s);
const dialog=node('site-search'),input=node('site-search-input'),opener=node('site-search-open'),list=node('site-search-results');
const items=()=>plain(run('siteSearchItems'));
const type=q=>{input.value=q;input.callbacks.input({type:'input',target:input});options.clear();};
const press=(key,extra={})=>{let prevented=false;input.callbacks.keydown({key,target:input,isComposing:false,preventDefault(){prevented=true;},...extra});return prevented;};
const active=()=>input['aria-activedescendant'];
const selected=()=>rendered().filter(id=>option(id)['aria-selected']==='true');
const open=()=>{dialog.open=false;opener.callbacks.click();};
const closeEvent=()=>dialog.callbacks.close();

// Opening shows suggestions: one option per item, numbered in order, and the field says the list is open.
open();
assert.equal(dialog.open,true);assert.equal(opener['aria-expanded'],'true');
const suggested=items();
assert.ok(suggested.length>=4,'Search opens with suggestions');
assert.deepEqual(rendered(),suggested.map((_,i)=>'site-search-option-'+i),'One option per item, in order');
assert.equal(input['aria-expanded'],'true');assert.equal(list.hidden,false);assert.equal(active(),undefined);
assert.equal(node('site-search-message').textContent,'Type a name or a role. Press Enter to open the first result.');
// Enter on an empty field opens nothing and keeps the dialog open.
const before=location.hash;
assert.equal(press('Enter'),true);assert.equal(location.hash,before);assert.equal(dialog.open,true);
// A typed query lists its matches; the arrows move through them and wrap at both ends.
type('mercor');
const results=items(),n=results.length;
assert.equal(results[0].href,'#company/mercor');assert.ok(n>=2,'Enough options to wrap');
assert.equal(rendered().length,n);assert.equal(input['aria-expanded'],'true');assert.equal(active(),undefined);
assert.equal(press('ArrowUp'),true);assert.equal(active(),'site-search-option-'+(n-1),'ArrowUp from the field starts at the last option');
assert.deepEqual(selected(),['site-search-option-'+(n-1)]);assert.ok(option('site-search-option-'+(n-1)).classes.has('is-active'));
press('ArrowDown');assert.equal(active(),'site-search-option-0','ArrowDown wraps from the last option to the first');
assert.deepEqual(selected(),['site-search-option-0']);assert.ok(!option('site-search-option-'+(n-1)).classes.has('is-active'));
press('ArrowDown');assert.equal(active(),'site-search-option-1');
press('ArrowUp');press('ArrowUp');assert.equal(active(),'site-search-option-'+(n-1),'ArrowUp wraps from the first option to the last');
press('ArrowDown');assert.equal(active(),'site-search-option-0');
// Typing again starts over with no active option.
type('mercor');assert.equal(active(),undefined);assert.equal(selected().length,0);
// Enter while composing text (an input method editor) is left alone.
assert.equal(press('Enter',{isComposing:true}),false);assert.equal(dialog.open,true);
// Enter opens the active option and closes the dialog; closing hands the expanded state back to the button.
press('ArrowDown');press('ArrowDown');const second=results[1];
assert.equal(press('Enter'),true);assert.equal(dialog.open,false);assert.equal(location.hash,second.href);
closeEvent();assert.equal(opener['aria-expanded'],'false');
// With no active option, Enter opens the first result.
open();type('labelbox');assert.equal(press('Enter'),true);assert.equal(location.hash,'#company/labelbox');assert.equal(dialog.open,false);
// Escape clears a typed query and keeps the dialog open; on an empty field it is left to the dialog, which closes.
open();type('scale');assert.ok(items().length>0);
assert.equal(press('Escape'),true);assert.equal(input.value,'');assert.equal(dialog.open,true);
assert.equal(rendered().length,suggested.length,'Clearing the query brings back the suggestions');
assert.equal(node('site-search-message').textContent,'Type a name or a role. Press Enter to open the first result.');
assert.equal(press('Escape'),false,'Escape on an empty field is not taken from the dialog');
// No match: the message says so, and the list offers ways to browse instead.
type('zzqxv');assert.ok(node('site-search-message').textContent.startsWith('No match for'));
assert.ok(items().length>0&&items().every(i=>i.rank===undefined));assert.equal(input['aria-expanded'],'true');
// "See all N listings" sets up the Paid work page before it hands over the query.
type('remote');const all=items().findIndex(i=>i.action==='work');assert.ok(all>=0,'Paid work action offered');
run(`globalThis.workSetupSaw=null;PAGE_SETUP.work=[()=>{globalThis.workSetupSaw=document.getElementById('work-search').value;}]`);
node('work-search').value='';run(`state.workQuery=''`);
for(let i=0;i<=all;i++)press('ArrowDown');assert.equal(active(),'site-search-option-'+all);
assert.equal(press('Enter'),true);
assert.equal(run('workSetupSaw'),'','The Paid work page is set up before its search field is filled');
assert.equal(run('PAGE_SETUP.work.length'),0);
assert.equal(node('work-search').value,'remote');assert.equal(run('state.workQuery'),'remote');
assert.equal(location.hash,'#work');assert.equal(dialog.open,false);
// The overview's business group links set up the company list before they set its group field.
const key=run('Object.keys(MODEL_GROUPS)[0]');
run(`globalThis.listSetupSaw=null;PAGE_SETUP.companies=[()=>{globalThis.listSetupSaw=document.getElementById('category').value;}]`);
node('category').value='';
const link={tagName:'A',dataset:{categoryJump:key},closest:()=>null,matches:()=>false};
for(const handler of documentCallbacks.click||[])handler({target:{closest:s=>s==='[data-category-jump]'?link:null,matches:()=>false},button:0,defaultPrevented:false});
assert.equal(run('listSetupSaw'),'','The company list is set up before its group field is set');
assert.equal(node('category').value,key);assert.equal(run('state.category'),key);
console.log(JSON.stringify({suggestions:suggested.length,mercor_results:n,browser_verified:false}));
'''
        result = run_stub(checks)
        self.assertEqual(result.returncode, 0, result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
