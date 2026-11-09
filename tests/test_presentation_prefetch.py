"""Exercise the real early-head prefetch and owner fetch without a browser."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {createHash,webcrypto}=require('node:crypto');
const root=process.argv[1],prefetch=fs.readFileSync(path.join(root,'web/presentation-prefetch.js'),'utf8'),runtime=fs.readFileSync(path.join(root,'web/data-runtime.js'),'utf8');
const start=runtime.indexOf('function validatePresentation('),end=runtime.indexOf('\nfunction ensureHealthModule(',start);
assert(start>=0&&end>start,'Actual owner fetch functions were not found');
const owner=runtime.slice(start,end),digest=b=>createHash('sha256').update(Buffer.from(b)).digest('hex');
const payload=(changes={})=>({schemaVersion:'1.0.0',buildId:'release-a',editorialReleaseId:'editorial-a',datasetVersion:'2.5.0',companyId:'mercor',data:{dataset_version:'2.5.0'},...changes});
const bytes=p=>new TextEncoder().encode(JSON.stringify(p)).buffer;
const descriptor=(b,href='/presentation/company-a.json')=>({href,sha256:digest(b),bytes:b.byteLength});
const response=(b,status=200)=>({ok:status>=200&&status<300,status,arrayBuffer:async()=>b});
function environment({hash='#company/mercor/work',body=bytes(payload()),head=true,transport=null,identityChanges={}}={}){
 const d=descriptor(body),identity={schemaVersion:'1.0.0',buildId:'release-a',editorialReleaseId:'editorial-a',datasetVersion:'2.5.0',companyDetails:{mercor:d},aliases:{alias:'mercor'},archive:{...d,href:'/presentation/archive.json'},overview:{...d,href:'/presentation/overview.json'},modules:{businessHealth:{href:'/js/health.a.js',integrity:'sha256-test'}},...identityChanges};
 const calls=[],links=[],timers=new Map();let timer=0;
 const window=head?{PRESENTATION_PRELOAD_CONFIG:identity}:{SUMMARY_INDEX:identity};
 const context=vm.createContext({window,location:{hash},presentationIdentity:identity,DATA:{dataset_version:'2.5.0'},AbortController,DOMException,TextDecoder,crypto:webcrypto,
  document:{createElement:()=>({}),head:{append:link=>links.push(link)}},
  setTimeout:fn=>{timers.set(++timer,fn);return timer;},clearTimeout:id=>timers.delete(id),
  fetch:(url,options)=>{calls.push({url,options});return transport?transport(url,options):Promise.resolve(response(body));}});
 vm.runInContext(prefetch,context);vm.runInContext(owner,context);
 return {context,window,identity,d,calls,links,timers,fetch:vm.runInContext('fetchPresentation',context)};
}
const results={};
(async()=>{
 {
  const e=environment();assert.equal(e.calls.length,1);assert.equal(e.links.length,1);assert.equal(e.links[0].integrity,'sha256-test');
  assert.equal(e.window.BusinessHealth,undefined);assert.equal(e.window.PRESENTATION_PRELOAD_CONFIG,undefined);
  const out=await e.fetch(e.d,'mercor');assert.equal(out.buildId,'release-a');assert.equal(e.calls.length,1);assert.equal(e.window.PRESENTATION_PREFETCH,undefined);results.matching_reuse=true;
 }
 {
  for(const key of ['href','sha256','buildId']){
   const e=environment();e.window.PRESENTATION_PREFETCH[key]+='-wrong';
   await e.fetch(e.d,'mercor');assert.equal(e.calls.length,2,key+' mismatch must use the ordinary verified fetch');
  }
  results.descriptor_build_bypass=true;
 }
 {
  const e=environment({transport:()=>Promise.resolve(response(new ArrayBuffer(0),404))});
  const early=await e.window.PRESENTATION_PREFETCH.promise;assert.equal(early.error.message,'Evidence request failed (404)');assert.equal(early.bytes,undefined);
  await assert.rejects(e.fetch(e.d,'mercor'),/Evidence request failed \(404\)/);assert.equal(e.calls.length,1);results.failed_prefetch_distinct=true;
 }
 {
  const e=environment({transport:(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}))});
  [...e.timers.values()][0]();const early=await e.window.PRESENTATION_PREFETCH.promise;
  assert.equal(early.error.message,'Evidence request timed out');await assert.rejects(e.fetch(e.d,'mercor'),/Evidence request timed out/);results.deadline_error=true;
 }
 {
  const e=environment({transport:(url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}))});
  const early=e.window.PRESENTATION_PREFETCH,navigation=new AbortController();let installed=false;
  const pending=e.fetch(e.d,'mercor',navigation.signal).then(()=>{installed=true;});navigation.abort();
  await assert.rejects(pending,error=>error.name==='AbortError');assert.equal(early.controller.signal.aborted,true);assert.equal(installed,false);results.abort_no_install=true;
 }
 {
  const e=environment();e.window.PRESENTATION_PREFETCH.promise=Promise.resolve({bytes:bytes(payload({buildId:'tampered'}))});
  await assert.rejects(e.fetch(e.d,'mercor'),/Evidence integrity mismatch/);
  const stale=environment({body:bytes(payload({buildId:'old-release'}))});
  await assert.rejects(stale.fetch(stale.d,'mercor'),/Stale presentation buildId/);results.digest_and_identity=true;
 }
 {
  for(const hash of ['#company/unknown','#company/__proto__','#company/constructor','#company/%','#companies','#work','#compare']){
   const e=environment({hash});assert.equal(e.calls.length,0,hash);assert.equal(e.links.length,0,hash);assert.equal(e.window.PRESENTATION_PREFETCH,undefined,hash);
  }
  results.unknown_prototype_no_fetch=true;
 }
 {
  const head=environment({hash:'#company/alias/work'});assert.equal(head.calls[0].url,head.d.href);await head.fetch(head.d,'mercor');
  const fallback=environment({head:false});assert.equal(fallback.calls[0].url,fallback.d.href);await fallback.fetch(fallback.d,'mercor');
  for(const [hash,expected]of [['#downloads','archive'],['#market','overview']]){const e=environment({hash});assert.equal(e.calls[0].url,e.identity[expected].href);}
  results.head_config_alias_and_fallback=true;
 }
 process.stdout.write(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class PresentationPrefetchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["node", "-e", HARNESS, str(ROOT)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.results = json.loads(result.stdout)

    def test_matching_bytes_are_reused_once_without_initializing_the_health_module(self):
        self.assertTrue(self.results["matching_reuse"])

    def test_wrong_descriptor_or_build_uses_the_normal_verified_fetch(self):
        self.assertTrue(self.results["descriptor_build_bypass"])

    def test_prefetch_failure_is_an_error_not_empty_evidence(self):
        self.assertTrue(self.results["failed_prefetch_distinct"])
        self.assertTrue(self.results["deadline_error"])

    def test_abort_reaches_prefetch_and_prevents_context_installation(self):
        self.assertTrue(self.results["abort_no_install"])

    def test_reused_bytes_still_require_digest_and_release_identity(self):
        self.assertTrue(self.results["digest_and_identity"])

    def test_unknown_and_prototype_company_ids_do_not_fetch(self):
        self.assertTrue(self.results["unknown_prototype_no_fetch"])

    def test_compact_head_registry_aliases_and_summary_fallback(self):
        self.assertTrue(self.results["head_config_alias_and_fallback"])


if __name__ == "__main__":
    unittest.main()
