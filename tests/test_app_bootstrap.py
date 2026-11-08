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
        checks = r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const source=SOURCE;
function harness(build='build-test'){
 const attrs=new Map([['data-route','other']]),timers=new Map(),scripts=[],frames=[],callbacks={};let timerId=0,reloads=0;
 const root={dataset:{buildId:'build-test'},style:{removeProperty(){}},setAttribute:(k,v)=>attrs.set(k,v),removeAttribute:k=>attrs.delete(k),getAttribute:k=>attrs.get(k)};
 const failure={hidden:true},reload={addEventListener:(name,callback)=>{callbacks[name]=callback;}};
 const views=[{hidden:false},{hidden:true}],dialog={open:true,close(){this.open=false;}};
 const document={documentElement:root,getElementById:id=>id==='app-failure'?failure:reload,querySelectorAll:s=>s==='main>.view'?views:s==='dialog[open]'?[dialog]:[],createElement:()=>({}),body:{append:script=>scripts.push(script)}};
 vm.runInNewContext(source,{window:{APP_BUILD_ID:build},document,location:{reload:()=>{reloads++;}},requestAnimationFrame:callback=>frames.push(callback),setTimeout:(callback,delay=0)=>{timers.set(++timerId,{callback,delay});return timerId;},clearTimeout:id=>timers.delete(id)});
 const fire=delay=>{const pair=[...timers].find(([,timer])=>timer.delay===delay);assert.ok(pair,'Missing timer '+delay);timers.delete(pair[0]);pair[1].callback();};
 const start=()=>fire(1500),ready=()=>{root.setAttribute('data-app','ready');failure.hidden=true;};
 return {attrs,timers,scripts,frames,views,failure,dialog,start,fire,ready,reload:()=>callbacks.click(),reloads:()=>reloads};
}
// Data must finish before app code runs. A failed data download cannot run the app against missing data.
const network=harness();network.start();assert.equal(network.scripts.length,1);network.scripts[0].onerror();
assert.equal(network.scripts.length,1);assert.equal(network.attrs.get('data-app'),'failed');assert.equal(network.failure.hidden,false);assert.ok(network.views.every(v=>v.hidden));assert.equal(network.dialog.open,false);assert.ok(!network.attrs.has('data-route'));
network.reload();assert.equal(network.reloads(),1);
// A syntax error or thrown initialize() still fires script.onload; the readiness marker catches it.
const runtime=harness();runtime.start();runtime.scripts[0].onload();assert.equal(runtime.scripts.length,2);runtime.scripts[1].onload();
assert.equal(runtime.attrs.get('data-app'),'failed');assert.equal(runtime.failure.hidden,false);
// Successful initialization clears the watchdog and never shows the recovery notice.
const good=harness();good.start();good.scripts[0].onload();good.ready();good.scripts[1].onload();
assert.equal(good.attrs.get('data-app'),'ready');assert.equal(good.failure.hidden,true);assert.equal(good.timers.size,0);
const stale=harness('older-build');stale.start();stale.scripts[0].onload();stale.ready();stale.scripts[1].onload();assert.equal(stale.attrs.get('data-app'),'failed');assert.equal(stale.attrs.get('data-app-reason'),'stale-bundle');
// A stalled connection exposes plain links. It can still finish and recover without duplicate scripts.
const slow=harness();slow.start();slow.fire(15000);assert.equal(slow.failure.hidden,false);
slow.scripts[0].onload();slow.ready();slow.scripts[1].onload();assert.equal(slow.failure.hidden,true);assert.equal(slow.attrs.get('data-app'),'ready');
// Both scheduling paths can call load; the bundles are appended exactly once.
const once=harness();once.start();once.frames[0]();once.fire(0);assert.equal(once.scripts.length,1);
'''.replace('SOURCE', json.dumps(script))
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
