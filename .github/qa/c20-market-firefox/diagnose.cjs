const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { firefox } = require('playwright');

const sources = [
  {
    name: 'Worker 47',
    origin: 'https://9884a3b2-sciencetostartup.musaeminozdem.workers.dev',
    build: 'fdcd18d9bc1267ed17c6',
    manifest: '89bc2008e7b3a869f0752c9e0b813c307174f5ca9c2d5366aa8e355d58aa91e7',
  },
  {
    name: 'Worker 48',
    origin: 'https://2382dd9e-sciencetostartup.musaeminozdem.workers.dev',
    build: 'e4ead044f5b3419c667b',
    manifest: '1fe217bab088009c4fb30ca3b00987bc3291361808823d9c523729fb648015fc',
  },
];
const folder = path.resolve('output/c20-market-firefox');
const git = (...args) => execFileSync('git', args, { encoding: 'utf8' }).trim();
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const current = '8ab0452e5f0576ee9da472b79587607315c12d01';
const diagnosticFiles = [
  '.github/qa/c20-market-firefox/diagnose.cjs',
  '.github/workflows/c20-market-firefox-timeline.yml',
];

async function signedManifest(source, edge) {
  const url = source.origin + '/manifest.json';
  const response = await fetch(url, {
    redirect: 'error',
    signal: AbortSignal.timeout(20000),
    headers: { 'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity' },
  });
  assert.equal(response.status, 200);
  assert.equal(response.url, url);
  const body = Buffer.from(await response.arrayBuffer());
  assert.equal(sha256(body), source.manifest);
  assert.equal(JSON.parse(body).build_id, source.build);
  const file = source.build + '-' + edge + '-manifest.json';
  fs.writeFileSync(path.join(folder, file), body);
  return { http: response.status, url, file, digest: source.manifest, utc: new Date().toISOString() };
}

async function observe(page) {
  await page.addInitScript(() => {
    const timeline = window.auditMarketTimeline = [];
    function mark(event, detail) {
      if (timeline.length >= 180) return;
      const active = document.activeElement;
      const state = window.navigation ? window.navigation.currentEntry?.getState() : history.state;
      const root = document.documentElement;
      timeline.push({
        event, detail, ms: performance.now(), y: scrollY, saved: state?.scrollY,
        bookmark: Boolean(document.getElementById('business-health')),
        active: active?.id || active?.tagName, ready: document.readyState,
        app: root?.dataset.app, view: root?.dataset.viewState,
      });
    }
    mark('initial');
    for (const name of ['DOMContentLoaded', 'load', 'pageshow', 'pagehide', 'popstate', 'hashchange', 'scroll', 'focusin']) {
      addEventListener(name, event => {
        mark(name, name === 'focusin' ? event.target?.id || event.target?.tagName : undefined);
        if (name === 'pageshow') {
          requestAnimationFrame(() => {
            mark('first-frame-after-pageshow');
            requestAnimationFrame(() => mark('second-frame-after-pageshow'));
          });
        }
      }, { capture: true, passive: true });
    }
    const scrollTo = window.scrollTo;
    window.scrollTo = function (options, y) {
      mark('script-scrollTo', typeof options === 'object' ? options?.top : y);
      return scrollTo.apply(this, arguments);
    };
    const focus = HTMLElement.prototype.focus;
    HTMLElement.prototype.focus = function (options) {
      mark('script-focus', { id: this.id || this.tagName, preventScroll: Boolean(options?.preventScroll) });
      return focus.apply(this, arguments);
    };
    const scrollIntoView = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function () {
      mark('script-scrollIntoView', this.id || this.tagName);
      return scrollIntoView.apply(this, arguments);
    };
    const replaceState = history.replaceState;
    history.replaceState = function (state) {
      mark('history-replaceState', state?.scrollY);
      return replaceState.apply(this, arguments);
    };
    if (window.navigation) {
      const update = navigation.updateCurrentEntry;
      navigation.updateCurrentEntry = function (entry) {
        mark('navigation-updateCurrentEntry', entry?.state?.scrollY);
        return update.apply(this, arguments);
      };
    }
  });
}

async function snapshot(page) {
  return page.evaluate(() => {
    const state = window.navigation ? window.navigation.currentEntry?.getState() : history.state;
    return {
      url: location.href, y: scrollY, ready: document.readyState, saved: state?.scrollY,
      viaNavigationAPI: Boolean(window.navigation),
      navigationType: performance.getEntriesByType('navigation')[0]?.type,
      active: document.activeElement?.id || document.activeElement?.tagName,
      timeline: window.auditMarketTimeline,
    };
  });
}

async function ordinaryReload(page, source, instrumented) {
  if (instrumented) await observe(page);
  const url = source.origin + '/explore/#business-health';
  const first = await page.goto(url);
  assert.equal(first.status(), 200);
  await page.waitForFunction(() => {
    const item = document.getElementById('business-health-heading')?.getBoundingClientRect();
    return document.documentElement.dataset.viewState === 'ready' &&
      item && item.bottom > 0 && item.top < innerHeight;
  });
  const initial = await snapshot(page);
  const target = await page.evaluate(() => {
    scrollBy({ top: 680, behavior: 'instant' });
    return scrollY;
  });
  await page.waitForFunction(position => {
    const state = window.navigation ? window.navigation.currentEntry?.getState() : history.state;
    return state?.scrollY === position;
  }, target);
  const outgoing = await snapshot(page);
  const reloaded = await page.reload();
  const reloadHttp = reloaded?.status();
  assert.ok(reloadHttp === 200 || reloadHttp === 304);
  await page.waitForFunction(() => document.documentElement.dataset.viewState === 'ready');
  const ready = await snapshot(page);
  let reachedTarget = true;
  try {
    await page.waitForFunction(position => scrollY === position, target, { timeout: 8000 });
  } catch (error) {
    if (error.name !== 'TimeoutError') throw error;
    reachedTarget = false;
  }
  const firstPosition = await snapshot(page);
  await new Promise(resolve => setTimeout(resolve, 700));
  const settled = await snapshot(page);
  assert.equal(ready.navigationType, 'reload');
  assert.equal(settled.url, url);
  return {
    instrumented, target, initial, outgoing, reloadHttp, ready, firstPosition, settled,
    reachedTarget, preserved: reachedTarget && settled.y === target,
  };
}

async function main() {
  const proofCommit = git('rev-parse', 'HEAD');
  assert.equal(proofCommit, process.env.GITHUB_SHA);
  assert.equal(git('rev-parse', 'HEAD^'), current);
  assert.deepEqual(git('diff', '--name-only', 'HEAD^').split('\n').sort(), diagnosticFiles);
  assert.equal(git('rev-parse', 'HEAD:dist'), git('rev-parse', 'HEAD^:dist'));
  fs.mkdirSync(folder, { recursive: true });
  const receipt = {
    productCommit: current, proofCommit, run: process.env.GITHUB_RUN_ID,
    attempt: process.env.GITHUB_RUN_ATTEMPT, project: 'firefox', results: [],
  };
  const save = () => fs.writeFileSync(path.join(folder, 'timeline.json'), JSON.stringify(receipt, null, 2) + '\n');
  const browser = await firefox.launch();
  receipt.browserVersion = browser.version();
  try {
    for (const source of sources) {
      const record = { ...source, before: await signedManifest(source, 'before'), cases: [] };
      receipt.results.push(record);
      save();
      for (const instrumented of [false, true, false, true]) {
        const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
        try {
          record.cases.push(await ordinaryReload(page, source, instrumented));
        } catch (error) {
          record.cases.push({ instrumented, error: error.message, last: await snapshot(page).catch(() => null) });
        } finally {
          await page.close();
          save();
        }
      }
      record.after = await signedManifest(source, 'after');
      save();
    }
  } finally {
    await browser.close();
  }
  const summary = receipt.results.map(result => ({
    origin: result.origin, cases: result.cases.map(item => ({
      instrumented: item.instrumented, target: item.target, settled: item.settled?.y,
      preserved: item.preserved, error: item.error,
    })),
  }));
  console.log(JSON.stringify(summary));
  process.exitCode = Number(receipt.results.some(row => row.cases.some(item => item.error)));
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
