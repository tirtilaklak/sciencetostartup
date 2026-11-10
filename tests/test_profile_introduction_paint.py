"""Exercise the actual profile paint wait and async route owner without a browser."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(process.argv[1],'web/data-runtime.js'),'utf8');
const start=source.indexOf('function loadingProfile(id){'),end=source.indexOf("\ndocument.addEventListener('click'",start);
assert(start>=0&&end>start,'Actual profile paint/route owner functions were not found');
const actual=source.slice(start,end);
const flush=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
function environment({visibility='visible',animation=true,transport=null}={}){
 const timers=new Map(),frames=new Map(),calls=[],installed=[],rendered=[],failures=[];let next=0;
 const node=id=>({id,hidden:true,attributes:new Map(),innerHTML:'',setAttribute(k,v){this.attributes.set(k,v);},removeAttribute(k){this.attributes.delete(k);}});
 const nodes=new Map(['profile-view','companies-view','work-view','app-failure'].map(id=>[id,node(id)]));
 const root={dataset:{},removeAttribute(){}};
 const document={visibilityState:visibility,documentElement:root,querySelectorAll(selector){return selector==='main>.view'?[nodes.get('profile-view'),nodes.get('companies-view'),nodes.get('work-view')]:[];}};
 const window={},location={hash:'#company/mercor/work'};
 const context=vm.createContext({window,location,document,AbortController,DOMException,console:{warn:value=>failures.push(value)},
  setTimeout:(callback,delay)=>{const id=++next;timers.set(id,{callback,delay});return id;},clearTimeout:id=>timers.delete(id),
  $:id=>nodes.get(id),attr:value=>String(value),profileIntroductionHTML:id=>'<p class="profile-summary">Sourced introduction '+id+'</p>',
  profileRouteCompany:id=>id,routeParts:()=>location.hash.slice(1).split('/'),
  presentationState:(state,reason='')=>{root.dataset.viewState=state;root.dataset.viewReason=reason;},
  restoreSearchRouteControls(){},synchronousRoute(){rendered.push(location.hash);},
  installResearchContext:payload=>installed.push(payload.companyId),
  companyContext:(id,signal)=>{calls.push({id,signal});return transport?transport(id,signal):Promise.resolve({companyId:id});},
  presentationIdentity:{companyDetails:{}},state:{selected:[],query:''},VIEW_ANCHORS:{},
  workCriteriaFromHash:()=>({q:''}),applyWorkCriteria(){},pendingSearchRoute(){},
  ensureHealthModule:()=>Promise.resolve(),fetchPresentation:()=>Promise.resolve({data:{}})
 });
 if(animation){context.requestAnimationFrame=callback=>{const id=++next;frames.set(id,callback);return id;};context.cancelAnimationFrame=id=>frames.delete(id);}
 vm.runInContext('let navigationGeneration=0,detailController=null;const detailCache=new Map();'+actual,context);
 return {context,document,window,location,nodes,root,timers,frames,calls,installed,rendered,failures,
  route:()=>vm.runInContext('route({type:"hashchange"})',context),
  frame(){const entry=frames.entries().next().value;assert(entry,'No pending animation frame');frames.delete(entry[0]);entry[1]();},
  timer(delay=100){const entry=[...timers].find(([,timer])=>timer.delay===delay);assert(entry,'No pending timer '+delay);timers.delete(entry[0]);entry[1].callback();}
 };
}
const results={};
(async()=>{
 {
  let deliver;const e=environment({transport:()=>new Promise(resolve=>{deliver=resolve;})});let settled=false;
  const ready=e.route();assert.equal(ready,e.window.APP_ROUTE_READY);ready.then(()=>{settled=true;});
  assert.match(e.nodes.get('profile-view').innerHTML,/Sourced introduction mercor/);
  assert.equal(e.nodes.get('profile-view').attributes.get('aria-busy'),'true');
  assert.equal(e.calls.length,0);e.frame();await flush();assert.equal(e.calls.length,0);assert.equal(settled,false);
  e.frame();await flush();assert.equal(e.calls.length,1);assert.equal(settled,false);assert.equal(e.root.dataset.viewState,'loading');
  deliver({companyId:'mercor'});await ready;assert.deepEqual(e.installed,['mercor']);assert.deepEqual(e.rendered,['#company/mercor/work']);
  assert.equal(e.root.dataset.viewState,'ready');assert.equal(e.nodes.get('profile-view').attributes.has('aria-busy'),false);
  assert.equal(e.timers.size,0);assert.equal(e.frames.size,0);results.actual_render_and_ready_order=true;
 }
 {
  const e=environment();const ready=e.route();assert.equal(e.frames.size,1);e.timer();await ready;
  assert.deepEqual(e.installed,['mercor']);assert.equal(e.frames.size,0);assert.equal(e.timers.size,0);results.timeout_cleans_pending_frame=true;
 }
 {
  for(const options of [{visibility:'hidden'},{animation:false}]){
   const e=environment(options);await e.route();assert.deepEqual(e.installed,['mercor']);assert.equal(e.frames.size,0);assert.equal(e.timers.size,0);
  }
  results.hidden_or_no_animation_no_wait=true;
 }
 {
  const e=environment();const ready=e.route();e.frame();e.document.visibilityState='hidden';e.timer();await ready;
  assert.deepEqual(e.installed,['mercor']);assert.equal(e.frames.size,0);assert.equal(e.timers.size,0);results.hidden_after_first_frame_fallback=true;
 }
 {
  const e=environment();const old=e.route();e.location.hash='#companies';e.route();const current=e.window.APP_ROUTE_READY;await current;
  assert.equal(e.window.APP_ROUTE_READY,current);e.timer();await old;
  assert.equal(e.calls.length,0);assert.equal(e.installed.length,0);assert.deepEqual(e.rendered,['#companies']);
  assert.equal(e.window.APP_ROUTE_READY,current);assert.equal(e.root.dataset.viewState,'ready');assert.equal(e.frames.size,0);assert.equal(e.timers.size,0);
  results.navigation_during_wait_never_fetches_or_installs_stale_profile=true;
 }
 {
  const e=environment();const old=e.route();e.location.hash='#companies';await e.route();e.location.hash='#company/mercor/work';const current=e.route();
  while(e.frames.size){e.frame();await flush();}await Promise.all([old,current]);
  assert.equal(e.calls.length,1);assert.deepEqual(e.installed,['mercor']);assert.equal(e.window.APP_ROUTE_READY,current);assert.equal(e.timers.size,0);
  results.same_hash_return_keeps_generation_guard=true;
 }
 {
  let deliver;const e=environment({transport:()=>new Promise(resolve=>{deliver=resolve;})});const old=e.route();e.frame();e.frame();await flush();
  assert.equal(e.calls.length,1);e.location.hash='#companies';e.route();const current=e.window.APP_ROUTE_READY;await current;assert.equal(e.calls[0].signal.aborted,true);
  deliver({companyId:'mercor'});await old;assert.equal(e.installed.length,0);assert.deepEqual(e.rendered,['#companies']);assert.equal(e.window.APP_ROUTE_READY,current);
  results.late_response_after_navigation_never_installs=true;
 }
 {
  const e=environment({transport:()=>Promise.reject(new Error('Evidence request timed out'))});const ready=e.route();e.timer();await ready;
  assert.equal(e.root.dataset.viewState,'failed');assert.equal(e.root.dataset.viewReason,'evidence-timeout');assert.match(e.nodes.get('profile-view').innerHTML,/role="alert"/);
  assert.equal(e.nodes.get('profile-view').attributes.has('aria-busy'),false);assert.equal(e.rendered.length,0);assert.equal(e.installed.length,0);
  assert.equal(e.timers.size,0);assert.equal(e.frames.size,0);assert.equal(e.window.APP_ROUTE_READY,ready);results.failure_settles_readiness_with_recovery=true;
 }
 process.stdout.write(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class ProfileIntroductionPaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["node", "-e", HARNESS, str(ROOT)], text=True,
                                capture_output=True, timeout=15)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.results = json.loads(result.stdout)

    def test_introduction_paints_before_context_and_ready_waits_for_installation(self):
        self.assertTrue(self.results['actual_render_and_ready_order'])

    def test_timeout_cancels_frame_and_clears_timer(self):
        self.assertTrue(self.results['timeout_cleans_pending_frame'])

    def test_hidden_and_missing_animation_paths_complete(self):
        self.assertTrue(self.results['hidden_or_no_animation_no_wait'])
        self.assertTrue(self.results['hidden_after_first_frame_fallback'])

    def test_navigation_during_wait_never_installs_stale_profile(self):
        self.assertTrue(self.results['navigation_during_wait_never_fetches_or_installs_stale_profile'])
        self.assertTrue(self.results['same_hash_return_keeps_generation_guard'])

    def test_late_context_response_cannot_replace_current_route(self):
        self.assertTrue(self.results['late_response_after_navigation_never_installs'])

    def test_failed_context_settles_ready_with_recovery(self):
        self.assertTrue(self.results['failure_settles_readiness_with_recovery'])


if __name__ == '__main__':
    unittest.main()
