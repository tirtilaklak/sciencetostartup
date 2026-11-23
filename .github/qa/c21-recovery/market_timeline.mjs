import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';

const product = process.env.PRODUCT_DIR;
const origin = process.env.QA_BASE_URL;
const output = process.env.MARKET_TIMELINE_OUT;
const count = Number(process.env.MARKET_TRIALS || '20');
const require = createRequire(`${product}/package.json`);
const { firefox } = require('playwright');
const browser = await firefox.launch();
const cases = [];

function instrumentMarket() {
  if (!location.pathname.startsWith('/explore')) return;
  const id = Math.random().toString(36).slice(2, 9);
  const identify = element => element?.id || element?.tagName || '';
  function record(label, detail) {
    const state = history.state;
    const nav = window.navigation;
    const current = nav?.currentEntry;
    console.debug('__MARKET_TIMELINE__' + JSON.stringify({
      id, label, detail, t: Math.round(performance.now() * 10) / 10,
      kind: performance.getEntriesByType('navigation')[0]?.type,
      activation: nav?.activation?.navigationType,
      y: scrollY, h: state?.scrollY, n: current?.getState?.()?.scrollY,
      key: current?.key || state?.stsEntryKey, mode: history.scrollRestoration,
      ready: document.readyState, view: document.documentElement?.dataset.viewState,
      focus: identify(document.activeElement)
    }));
  }
  record('init');
  for (const label of ['scroll', 'pagehide', 'pageshow', 'load', 'popstate', 'hashchange']) {
    window.addEventListener(label, event => {
      record(label, event.persisted);
      if (label === 'pageshow' || label === 'load' || label === 'pagehide') {
        queueMicrotask(() => record(label + ':microtask'));
        if (label !== 'pagehide') {
          requestAnimationFrame(() => record(label + ':frame'));
          setTimeout(() => record(label + ':late'), 350);
        }
      }
    }, { capture: true, passive: true });
  }
  document.addEventListener('focusin', event => record('focusin', identify(event.target)), true);
  for (const [object, method] of [[window,'scrollTo'],[window,'scrollBy'],
      [Element.prototype,'scrollIntoView'],[HTMLElement.prototype,'focus'],
      [history,'replaceState']]) {
    const call = object[method];
    object[method] = function (...args) {
      const detail = method === 'replaceState'
        ? {scrollY: args[0]?.scrollY, key: args[0]?.stsEntryKey, url: args[2]}
        : {target: identify(this), args};
      record(method + ':before', detail);
      const result = Reflect.apply(call, this, args);
      record(method + ':after', detail);
      return result;
    };
  }
  const nav = window.navigation;
  if (nav?.updateCurrentEntry) {
    const update = nav.updateCurrentEntry;
    nav.updateCurrentEntry = function (arg) {
      record('updateCurrentEntry:before', arg?.state?.scrollY);
      const result = Reflect.apply(update, this, [arg]);
      record('updateCurrentEntry:after', arg?.state?.scrollY);
      return result;
    };
    nav.addEventListener('currententrychange', event => record('entrychange', event.navigationType));
    nav.addEventListener('navigate', event => record('navigate', event.navigationType));
  }
}

try {
  for (let iteration = 1; iteration <= count; iteration++) {
    const page = await browser.newPage({viewport:{width:1280,height:720}});
    const entry = { iteration, events: [], phases: {} };
    cases.push(entry);
    page.on('console', message => {
      const line = message.text();
      if (line.startsWith('__MARKET_TIMELINE__')) entry.events.push(JSON.parse(line.slice('__MARKET_TIMELINE__'.length)));
    });
    await page.addInitScript(instrumentMarket);
    const check = async (phase, wanted) => {
      await page.waitForFunction(() => document.documentElement.dataset.viewState === 'ready');
      await page.waitForLoadState('load');
      const state = () => page.evaluate(() => ({
        url: location.pathname + location.hash, y: scrollY,
        h: history.state?.scrollY, n: window.navigation?.currentEntry?.getState?.()?.scrollY,
        height: document.scrollingElement.scrollHeight, kind: performance.getEntriesByType('navigation')[0]?.type,
        anchor: document.getElementById('business-health')?.getBoundingClientRect().top,
      }));
      let snapshot;
      const deadline = Date.now() + 8000;
      do {
        snapshot = await state();
        if (snapshot.y === wanted) break;
        await new Promise(resolve => setTimeout(resolve, 100));
      } while (Date.now() < deadline);
      entry.phases[phase] = { expected: wanted, ...snapshot, passed: snapshot.y === wanted };
    };

    try {
      await page.goto(origin + '/explore/#business-health');
      await page.locator('#business-health-heading').waitFor({state:'visible'});
      await page.waitForFunction(() => {
        const heading = document.getElementById('business-health-heading');
        const box = heading.getBoundingClientRect();
        return box.top >= 0 && box.bottom <= innerHeight;
      });
      entry.saved = await page.evaluate(() => {
        scrollBy({top:680,behavior:'instant'});
        return scrollY;
      });
      await page.waitForFunction(wanted => {
        const state = window.navigation ? window.navigation.currentEntry.getState() : history.state;
        return state?.scrollY === wanted;
      }, entry.saved);
      await page.reload();
      await check('reload', entry.saved);
      // Preserve both phases. A failed reload should not feed the wrong position into Back.
      if (!entry.phases.reload.passed) {
        await page.evaluate(y => scrollTo({top:y,behavior:'instant'}), entry.saved);
        await page.waitForFunction(wanted => {
          const state = window.navigation ? window.navigation.currentEntry.getState() : history.state;
          return state?.scrollY === wanted;
        }, entry.saved);
      }
      await page.goto(origin + '/companies/');
      await page.goBack();
      await check('back', entry.saved);
    } catch (error) {
      entry.error = String(error);
    } finally {
      await page.context().close();
      console.log(JSON.stringify({iteration:entry.iteration, saved:entry.saved, phases:entry.phases, error:entry.error}));
    }
  }
} finally {
  await browser.close();
  writeFileSync(output, JSON.stringify({origin, cases}, null, 2));
  const failures = cases.filter(item => item.error || Object.values(item.phases).some(phase => !phase.passed));
  console.log('TIMELINE SUMMARY', JSON.stringify({count:cases.length, failures:failures.length}));
  for (const item of failures) {
    const relevant = item.events.filter(event =>
      ['init','pagehide','pageshow','pageshow:frame','pageshow:late','load','scroll','focus:before','scrollTo:before','scrollIntoView:before','replaceState:before'].includes(event.label));
    console.log('TIMELINE FAIL', JSON.stringify({iteration:item.iteration, events:relevant.slice(-70)}));
  }
}
