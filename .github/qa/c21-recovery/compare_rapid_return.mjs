import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';

const require = createRequire(`${process.env.PRODUCT_DIR}/package.json`);
const { chromium, devices } = require('playwright');
const origin = process.env.QA_BASE_URL;
const compare = '/explore/#compare/mercor/a-team/sama';
const destination = '#company/mercor/work';
const opener = '[data-compare-origin="paid-work:mercor"][href="' + destination + '"]';
const browser = await chromium.launch();
const cases = [];

try {
  for (const [phase, delay] of [['entry',0],['entry',1],['entry',4],['entry',8],
      ['hash',0],['hash',1],['hash',4],['hash',8],['stock',0],['stock',0]]) {
    const page = await browser.newPage(devices['Pixel 7']);
    const test = { phase, delay, timeline: [] };
    cases.push(test);
    page.on('console', message => {
      const line = message.text(), prefix = '__COMPARE_HISTORY__';
      if (line.startsWith(prefix)) test.timeline.push(JSON.parse(line.slice(prefix.length)));
    });
    await page.addInitScript(({phase,delay,destination}) => {
      function note(label, meta) {
        const current = navigation.currentEntry;
        console.debug('__COMPARE_HISTORY__' + JSON.stringify({
          label,meta,t:Math.round(performance.now()*100)/100,
          url:location.hash,index:current?.index,key:current?.key,
          documentType:performance.getEntriesByType('navigation')[0]?.type,
          opener:history.state?.exploreReturnOrigin?.compare?.action,
          active:document.activeElement?.dataset.compareOrigin || document.activeElement?.tagName
        }));
      }
      let departed=false;
      function returnEarly() {
        if (departed || location.hash !== destination) return;
        departed=true;
        const goBack = () => { note('request-back'); history.back(); };
        if (delay) setTimeout(goBack,delay);
        else queueMicrotask(goBack);
      }
      navigation.addEventListener('navigate',event => {
        note('navigate',{kind:event.navigationType,url:new URL(event.destination.url).hash,
          sameDocument:event.destination.sameDocument,from:navigation.currentEntry?.key});
      });
      navigation.addEventListener('currententrychange',event => {
        note('entry',{kind:event.navigationType,from:event.from?.key});
        if (phase==='entry') returnEarly();
      });
      addEventListener('hashchange',event => {
        note('hash',{old:new URL(event.oldURL).hash,next:new URL(event.newURL).hash});
        if (phase==='hash') returnEarly();
      });
      document.addEventListener('focusin',event => note('focus',event.target?.dataset.compareOrigin),true);
    },{phase,delay,destination});
    try {
      await page.goto(origin+compare);
      await page.locator(opener).waitFor({state:'visible'});
      test.initialEntry = await page.evaluate(() => ({key:navigation.currentEntry.key,index:navigation.currentEntry.index}));
      await page.goto(origin+compare,{waitUntil:'commit'});
      await page.locator(opener).waitFor({state:'visible'});
      test.returnEntry = await page.evaluate(() => ({key:navigation.currentEntry.key,index:navigation.currentEntry.index}));
      await page.locator(opener).press('Enter');
      if (phase==='stock') {
        await page.waitForURL(origin+'/explore/'+destination);
        await page.goBack({waitUntil:'commit'});
      }
      await page.waitForURL(origin+compare);
      await page.waitForFunction(() => document.documentElement.dataset.viewState==='ready');
      const returned = () => page.evaluate(open => ({
        hash:location.hash,active:document.activeElement?.dataset.compareOrigin || document.activeElement?.tagName,
        opener:history.state?.exploreReturnOrigin?.compare?.action,
        key:navigation.currentEntry.key,index:navigation.currentEntry.index,focused:document.activeElement===document.querySelector(open)
      }),opener);
      const until=Date.now()+3000;
      do {
        test.after=await returned();
        if (test.after.focused) break;
        await new Promise(resolve => setTimeout(resolve,100));
      } while (Date.now()<until);
      test.passed=test.after.focused && test.returnEntry.key===test.after.key;
    } catch (error) {
      test.error=String(error);
      test.passed=false;
    } finally {
      await page.context().close();
      console.log('COMPARE RESULT',JSON.stringify({phase,delay,
        initialEntry:test.initialEntry,returnEntry:test.returnEntry,after:test.after,passed:test.passed,error:test.error}));
      if (!test.passed) console.log('COMPARE EVENTS',JSON.stringify(test.timeline.slice(-32)));
    }
  }
} finally {
  await browser.close();
  writeFileSync(process.env.MARKET_TIMELINE_OUT,JSON.stringify(cases,null,2));
  console.log('COMPARE TOTAL',JSON.stringify({count:cases.length,passes:cases.filter(row=>row.passed).length}));
}
