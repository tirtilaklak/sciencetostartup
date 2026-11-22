"""Loading failures must leave a usable path to the plain research pages."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AppBootstrapTests(unittest.TestCase):
    def test_bundle_failures_and_slow_connections_have_recovery(self):
        html = (ROOT / 'web/index.html').read_text()
        script = next(code for code in re.findall(r'<script>(.*?)</script>', html, re.S)
                      if "getElementById('app-reload')" in code)
        script = script.replace('/* BUNDLES */[]', json.dumps(['js/data.test.js', 'js/app.test.js']))
        bundled_init = re.search(r'/\* DATA_RUNTIME_JS \*/(.*?)</script>', html, re.S).group(1)
        checks = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const source=SOURCE,bundledInit=BUNDLED_INIT;
function harness(build='build-test',hash='',navigationApi=false){
 const attrs=new Map([['data-route','other']]),timers=new Map(),scripts=[],attachedScripts=new Set(),frames=[],callbacks={};
 let timerId=0,reloads=0,initializations=0;
 const root={dataset:{buildId:'build-test',get app(){return attrs.get('data-app');}},style:{removeProperty(){}},setAttribute:(k,v)=>attrs.set(k,v),removeAttribute:k=>attrs.delete(k),getAttribute:k=>attrs.get(k)};
 const failure={hidden:true},reload={addEventListener:(name,callback)=>{callbacks[name]=callback;}},skip={addEventListener(){}};
 const views=[{hidden:false},{hidden:true}],dialog={open:true,close(){this.open=false;}};
 const marketSection={id:'',dataset:{fragmentId:'business-health'},removeAttribute(){this.id='';}};
 const document={documentElement:root,
  querySelector:selector=>selector==='#market-view > [data-fragment-id]'?marketSection:selector==='.skip'?skip:null,
  getElementById:id=>id==='app-failure'?failure:reload,querySelectorAll:s=>s==='main>.view'?views:s==='dialog[open]'?[dialog]:[],
  createElement:()=>({remove(){attachedScripts.delete(this);}}),
  body:{append(script){scripts.push(script);attachedScripts.add(script);}}};
 let entryState={scrollY:3017,retained:'reading'};
 const navigation=navigationApi?{currentEntry:{getState:()=>entryState},updateCurrentEntry:({state})=>{entryState=state;}}:null;
 const history={get state(){return entryState;},replaceState(state){entryState=state;}};
 const context=vm.createContext({window:{APP_BUILD_ID:build,navigation},document,history,location:{hash,reload:()=>{reloads++;}},requestAnimationFrame:callback=>frames.push(callback),setTimeout:(callback,delay=0)=>{timers.set(++timerId,{callback,delay});return timerId;},clearTimeout:id=>timers.delete(id)});
 vm.runInContext(source,context);
 assert.equal(marketSection.id,'');
 const fire=delay=>{const pair=[...timers].find(([,timer])=>timer.delay===delay);assert.ok(pair,'Missing timer '+delay);timers.delete(pair[0]);pair[1].callback();};
 const start=()=>fire(1500),initialize=(ready=true)=>{
  context.initialize=()=>{
   initializations++;
   assert.equal(marketSection.id,'business-health');
   if(!ready)throw new Error('Initialize failed');
   root.setAttribute('data-app','ready');failure.hidden=true;
  };
  vm.runInContext(bundledInit,context);
 };
 return {attrs,timers,scripts,attachedScripts,frames,views,failure,dialog,marketSection,start,fire,initialize,
  initializations:()=>initializations,reload:()=>callbacks.click(),reloads:()=>reloads,entryState:()=>entryState};
}
function expectRecovery(page,reason){
 const script=page.scripts.at(-1);
 assert.equal(page.attrs.get('data-app'),'failed');
 assert.equal(page.attrs.get('data-app-reason'),reason);
 assert.equal(page.timers.size,0);
 assert.ok(!page.attachedScripts.has(script));
 assert.equal(script.onload,null);
 assert.equal(script.onerror,null);
 assert.equal(page.failure.hidden,false);
 assert.ok(page.views.every(view=>view.hidden));
 assert.equal(page.dialog.open,false);
 assert.ok(!page.attrs.has('data-route'));
 assert.equal(page.marketSection.id,'');
}
// Explicit Market recovery returns to its bookmark. Other entries retain their reading position.
for(const navigationApi of [false,true]){
 const market=harness('build-test','#business-health',navigationApi);
 market.reload();assert.equal(market.reloads(),1);assert.equal(market.entryState().scrollY,undefined);assert.equal(market.entryState().retained,'reading');
 const other=harness('build-test','#work',navigationApi);
 other.reload();assert.equal(other.entryState().scrollY,3017);
}
// Data must finish before app code runs. A failed data download cannot run the app against missing data.
const network=harness();network.start();assert.equal(network.scripts.length,1);network.scripts[0].onerror();
assert.equal(network.scripts.length,1);expectRecovery(network,'script-network');
network.reload();assert.equal(network.reloads(),1);
// A syntax error or thrown initialize() still fires script.onload; the readiness marker catches it.
const runtime=harness();runtime.start();runtime.scripts[0].onload();assert.equal(runtime.scripts.length,2);
assert.throws(()=>runtime.initialize(false),/Initialize failed/);runtime.scripts[1].onload();
expectRecovery(runtime,'runtime-not-ready');
// Successful initialization clears the watchdog and never shows the recovery notice.
const good=harness();good.start();good.scripts[0].onload();good.initialize();good.scripts[1].onload();
assert.equal(good.attrs.get('data-app'),'ready');assert.equal(good.failure.hidden,true);assert.equal(good.timers.size,0);assert.equal(good.marketSection.id,'business-health');assert.equal(good.attachedScripts.size,2);
const stale=harness('older-build');stale.start();stale.scripts[0].onload();stale.initialize();stale.scripts[1].onload();expectRecovery(stale,'stale-bundle');
// A stalled download leaves recovery visible. Late callbacks and bundle execution cannot dismiss it.
const slowData=harness();slowData.start();const lateData=slowData.scripts[0].onload;
slowData.fire(15000);expectRecovery(slowData,'timeout');lateData();assert.equal(slowData.scripts.length,1);
const slowApp=harness();slowApp.start();slowApp.scripts[0].onload();const lateApp=slowApp.scripts[1].onload;
slowApp.fire(15000);slowApp.initialize();lateApp();expectRecovery(slowApp,'timeout');
assert.equal(slowApp.initializations(),0);assert.equal(slowApp.scripts.length,2);
// Both scheduling paths can call load; the bundles are appended exactly once.
const once=harness();once.start();once.frames[0]();once.fire(0);assert.equal(once.scripts.length,1);
'''.replace('SOURCE', json.dumps(script)).replace('BUNDLED_INIT', json.dumps(bundled_init))
        result = subprocess.run([shutil.which('node') or 'node', '-'], input=checks,
                                text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_recovery_has_static_links_without_app_handlers(self):
        html = (ROOT / 'web/index.html').read_text()
        recovery = re.search(r'<section id="app-failure".*?</section>', html, re.S).group()
        self.assertIn('role="alert"', recovery)
        self.assertIn('id="app-reload"', recovery)
        for page in ('companies', 'work', 'method'):
            self.assertIn(f'href="/{page}/"', recovery)


if __name__ == '__main__':
    unittest.main()
