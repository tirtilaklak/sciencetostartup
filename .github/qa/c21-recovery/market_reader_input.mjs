import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';

const origin = process.env.QA_BASE_URL;
const require = createRequire(`${process.env.PRODUCT_DIR}/package.json`);
const { firefox } = require('playwright');
const browser = await firefox.launch();
const cases = [];
const readScroll = page => page.evaluate(() => scrollY);

try {
  for (const navigationType of ['reload','back_forward']) {
    for (const scrollDuringLoad of [false,true]) {
      const page = await browser.newPage({viewport:{width:1280,height:720}});
      let releaseImage;
      const heldImage = new Promise(resolve => { releaseImage = resolve; });
      const row = {navigationType,scrollDuringLoad};
      cases.push(row);
      try {
        await page.route('**/favicon-48.png?market-reader-input=1',async route => {
          await heldImage;
          await route.continue();
        });
        await page.addInitScript(type => {
          if (location.pathname !== '/explore/' || performance.getEntriesByType('navigation')[0]?.type !== type) return;
          const observer = new MutationObserver(() => {
            if (!document.body) return;
            observer.disconnect();
            const image = new Image();
            image.hidden = true;
            image.alt = '';
            image.src = '/assets/favicon-48.png?market-reader-input=1';
            document.body.append(image);
          });
          observer.observe(document,{childList:true,subtree:true});
        },navigationType);
        await page.goto(origin+'/explore/#business-health');
        await page.waitForFunction(() => {
          const heading = document.getElementById('business-health-heading');
          const position = heading.getBoundingClientRect();
          return document.documentElement.dataset.viewState === 'ready' && position.top >= 0 && position.bottom <= innerHeight;
        });
        row.saved = await page.evaluate(() => {
          scrollBy({top:680,behavior:'instant'});
          return scrollY;
        });
        await page.waitForFunction(expected => {
          const saved = window.navigation ? window.navigation.currentEntry.getState() : history.state;
          return saved?.scrollY === expected;
        },row.saved);
        if (navigationType === 'reload') await page.reload({waitUntil:'domcontentloaded'});
        else {
          await page.goto(origin+'/companies/');
          await page.goBack({waitUntil:'domcontentloaded'});
        }
        await page.waitForFunction(() => document.documentElement.dataset.viewState === 'ready');
        await page.waitForFunction(expected => scrollY === expected,row.saved);
        row.before = await page.evaluate(() => ({ready:document.readyState,kind:performance.getEntriesByType('navigation')[0].type}));
        if (row.before.ready!=='interactive' || row.before.kind!==navigationType) throw new Error('The page returned outside the held-load test conditions');
        if (scrollDuringLoad) {
          await page.mouse.move(1070,590);
          await page.mouse.wheel(0,340);
          await page.waitForFunction(previous => scrollY > previous+300,row.saved);
        }
        row.lastReaderPosition = await readScroll(page);
        releaseImage();
        await page.waitForLoadState('load');
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        await new Promise(resolve => setTimeout(resolve,400));
        row.settled = await readScroll(page);
        row.passed = row.settled===row.lastReaderPosition;
      } catch(error) {
        row.error=String(error);
        row.passed=false;
      } finally {
        releaseImage();
        await page.context().close();
        console.log(JSON.stringify(row));
      }
    }
  }
} finally {
  await browser.close();
  writeFileSync(process.env.MARKET_TIMELINE_OUT,JSON.stringify(cases,null,2));
  console.log('USER INPUT SUMMARY',JSON.stringify({total:cases.length,passed:cases.filter(result=>result.passed).length}));
}
