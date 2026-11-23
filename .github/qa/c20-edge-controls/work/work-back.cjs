const { createRequire } = require('node:module');
const { chromium, webkit } = createRequire(process.cwd() + '/package.json')('@playwright/test');
const signed = require('./expected.json');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { mkdirSync, writeFileSync } = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const [origin, expected, output, selection = 'all'] = process.argv.slice(2);
const site = new URL(origin);
assert.equal(site.href, site.origin + '/');
assert.equal(expected, signed.manifest_sha256);
assert(output);
mkdirSync(output, {recursive:true});
const role = 'afterquery.work.world-models';
const filtered = '/work/?pay=hourly&sort=hourly&reader=%20A%2Bb%20';
const selector = `[data-work-route="${role}"] h3 a`;
const employer = 'https://experts.afterquery.com/apply/world-models-ml-experts';
let proxy;
if (site.protocol === 'https:' && (process.env.HTTPS_PROXY || process.env.https_proxy)) {
  const endpoint = new URL(process.env.HTTPS_PROXY || process.env.https_proxy);
  proxy = { server:endpoint.origin };
  if (endpoint.username) proxy.username = decodeURIComponent(endpoint.username);
  if (endpoint.password) proxy.password = decodeURIComponent(endpoint.password);
}

function manifest() {
  const bytes = execFileSync('curl', ['--fail','--silent','--show-error','--max-time','12',
    '--header','Accept-Encoding: identity','--header','Cache-Control: no-cache',
    '--user-agent','ScienceToStartup-ReleaseVerification/1.0',site.origin+'/manifest.json']);
  const hash = createHash('sha256').update(bytes).digest('hex');
  assert.equal(hash,expected);
  return {build:JSON.parse(bytes).build_id,manifest_sha256:hash,time:new Date().toISOString()};
}

async function state(page) {
  return page.evaluate(({ selector, role }) => {
    const node = document.activeElement;
    const link = document.querySelector(selector);
    const card = document.getElementById(role);
    return {
      address:location.pathname+location.search+location.hash,
      navigationType:performance.getEntriesByType('navigation')[0]?.type,
      persisted:window.workProbePersisted ?? null,
      active:{tag:node?.tagName,id:node?.id || null,href:node?.getAttribute('href'),isRoleLink:node===link,isCompare:node?.hasAttribute('data-work-compare')},
      termsOpen:card?.querySelector('details.work-terms')?.open ?? null,
      hasHandoff:Boolean(history.state?.workReturnFocus),
      trustedInput:window.WorkPageResource?.interacted ?? null,
      position:scrollY, openerTop:link?.getBoundingClientRect().top,
      visibleIds:[...document.querySelectorAll('[data-work-route]')].filter(el=>el.getClientRects().length).map(el=>el.dataset.workRoute),
      events:window.workProbeEvents ?? [],
    };
  },{selector,role});
}

async function run(browser, scenario) {
  const context=await browser.newContext({baseURL:site.origin,viewport:{width:1024,height:640}});
  await context.tracing.start({snapshots:true,screenshots:true});
  const page=await context.newPage();
  page.setDefaultTimeout(8000);
  const result={scenario:scenario.name,network:[],pageErrors:[]};
  page.on('pageerror',error=>result.pageErrors.push(error.message));
  page.on('response',response=>{
    const url=new URL(response.url());
    if (url.origin===site.origin && (url.pathname==='/work/' || url.pathname==='/company/afterquery/' || /^\/js\/work\./.test(url.pathname))) {
      result.network.push({path:url.pathname,status:response.status()});
    }
  });
  try {
    await page.addInitScript(({selector,hold})=>{
      if (location.pathname!=='/work/') return;
      window.workProbeEvents=[];
      addEventListener('pageshow',event=>{window.workProbePersisted=event.persisted;});
      // Force a cold history traversal. The ordinary probe leaves focus and scrolling untouched.
      addEventListener('unload',()=>{});
      for (const type of ['focusin','focusout']) document.addEventListener(type,event=>{
        const target=event.target;
        if (window.workProbeEvents.length<50) window.workProbeEvents.push({type,time:performance.now(),tag:target.tagName,id:target.id||null,href:target.getAttribute('href'),scroll:scrollY});
      },true);
      if (!hold) return;
      document.addEventListener('focusin',function afterRestore(event){
        if (performance.getEntriesByType('navigation')[0]?.type!=='back_forward' || !event.target.matches(selector)) return;
        document.removeEventListener('focusin',afterRestore);
        const frame=window.requestAnimationFrame;
        const pending=[];
        window.requestAnimationFrame=callback=>pending.push(callback);
        window.releaseWorkProbeFrames=()=>{
          window.requestAnimationFrame=frame;
          for (const callback of pending) frame(callback);
        };
      });
    },{selector,hold:Boolean(scenario.cancel)});
    const work=filtered+(scenario.bookmarked?'#'+role:'');
    const opener=page.locator(selector);
    const terms=page.locator(`[data-work-route="${role}"] details.work-terms`);
    await page.goto(work);
    await page.locator('[data-work-compare]').waitFor({state:'visible'});
    await terms.locator('summary').press('Enter');
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Shift+Tab');
    result.departure=await state(page);
    assert.equal(result.departure.active.isRoleLink,true);
    assert.equal(result.departure.termsOpen,true);
    assert.equal(result.departure.visibleIds[0],role);
    assert.deepEqual(result.departure.visibleIds,signed.hourly_ids);
    await opener.click();
    await page.waitForURL('**/company/afterquery/#'+role);
    assert.equal(await page.locator(':target').getAttribute('id'),role);
    await page.goBack({waitUntil:'commit'});
    result.backCommit=await state(page);
    await page.waitForFunction(query=>document.activeElement===document.querySelector(query),selector);
    await page.waitForFunction(()=>window.workProbePersisted===false);
    if (scenario.cancel) {
      await page.waitForFunction(()=>typeof window.releaseWorkProbeFrames==='function');
      result.held=await state(page);
      assert.equal(result.held.trustedInput,false);
      if (scenario.cancel==='wheel') {
        await page.mouse.move(700,350);
        await page.mouse.wheel(0,900);
        await page.waitForFunction(top=>scrollY>top+250,result.departure.position);
        await page.evaluate(id=>document.getElementById(id).focus({preventScroll:true}),role);
        assert.equal((await state(page)).trustedInput,true);
      } else {
        await page.locator('[data-work-compare]').focus();
        assert.equal((await state(page)).trustedInput,false);
      }
      await page.evaluate(()=>window.releaseWorkProbeFrames());
    }
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))));
    result.returned=await state(page);
    assert.equal(result.returned.address,work);
    assert.equal(result.returned.navigationType,'back_forward');
    assert.equal(result.returned.persisted,false);
    assert.equal(result.returned.termsOpen,true);
    assert.deepEqual(result.returned.visibleIds,result.departure.visibleIds);
    if (scenario.cancel==='wheel') {
      assert.equal(result.returned.active.id,role);
      assert(result.returned.position>result.departure.position+250);
    } else if (scenario.cancel==='other-focus') {
      assert.equal(result.returned.active.isCompare,true);
    } else {
      assert.equal(result.returned.active.isRoleLink,true);
      assert(Math.abs(result.returned.position-result.departure.position)<3);
      assert(Math.abs(result.returned.openerTop-result.departure.openerTop)<3);
      await page.keyboard.press('Tab');
      result.nextTab=await state(page);
      assert.equal(result.nextTab.active.href,employer);
    }
    assert.deepEqual(result.pageErrors,[]);
    result.passed=true;
  } catch (error) {
    result.passed=false;
    result.error={name:error.name,message:error.message};
    if (!page.isClosed()) result.failure=await state(page).catch(()=>null);
  } finally {
    await context.tracing.stop({path:path.join(output,scenario.name+'.zip')});
    await context.close();
    writeFileSync(path.join(output,scenario.name+'.json'),JSON.stringify(result,null,2)+'\n');
  }
  return result;
}

const journeys=[
  {name:'webkit-stock-bookmark',engine:'webkit',bookmarked:true},
  {name:'chromium-stock-unbookmarked',engine:'chromium',bookmarked:false},
  {name:'chromium-wheel-after-restored-focus',engine:'chromium',bookmarked:true,cancel:'wheel'},
  {name:'chromium-other-focus-after-restore',engine:'chromium',bookmarked:true,cancel:'other-focus'},
];

(async()=>{
  let before=null,after=null,error;
  const outcomes=[];
  try {
    assert.equal(createHash('sha256').update(require('node:fs').readFileSync('dist/manifest.json')).digest('hex'),expected);
    before=manifest();
    assert.equal(before.build,signed.build);
    const requested=selection==='all'?journeys:journeys.filter(s=>s.engine===selection || s.name===selection);
    assert(requested.length);
    for (const engine of [...new Set(requested.map(s=>s.engine))]) {
      const browser=await ({chromium,webkit})[engine].launch({proxy});
      try {
        for (const scenario of requested.filter(s=>s.engine===engine)) {
          const result=await run(browser,scenario);
          outcomes.push({scenario:scenario.name,passed:result.passed,result:result.returned?.active,scroll:result.returned?.position,error:result.error});
        }
      } finally {
        await browser.close();
      }
    }
  } catch (fault) {
    error=fault.message;
  }
  if (before) {
    try { after=manifest(); }
    catch (fault) { error=[error,'Manifest after: '+fault.message].filter(Boolean).join('\n'); }
  }
  const summary={origin:site.origin,before,after,outcomes,error,passed:!error&&outcomes.length>0&&outcomes.every(r=>r.passed)};
  writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
  console.log(JSON.stringify(summary));
  process.exitCode=summary.passed?0:1;
})().catch(error=>{console.error(error);process.exitCode=1;});
