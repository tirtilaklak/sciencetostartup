// Bounded diagnostic of an existing cold-history contract. This is not a release gate.
const { webkit, devices } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');

const root = process.cwd();
const output = path.join(root, 'diagnostic-output');
const origin = 'https://sciencetostartup.com';
const arms = [
  { name: 'candidate', base: 'http://127.0.0.1:18775', ref: 'dfb5d3b8b0b20020d2ea3d49a5de3a96bd44382e', manifest: '81a0bd6b3aa6f7da5a0cbd9dc15c6a26f2570acc516977b6c8fe0501391b1851' },
  { name: 'main', base: 'http://127.0.0.1:18776', ref: '000fffba323468a532814fa7c22eb28bd86f2e28', manifest: 'e35718cadd02998eae360574733427606a32bae53c640be20ee5e8b36c8f74f2' },
];
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(label, predicate) {
  const start = Date.now();
  const intervals = [100, 250, 500, 1000];
  let index = 0;
  let last;
  while (Date.now() - start < 8000) {
    last = await predicate();
    if (last === true) return;
    await pause(Math.min(intervals[Math.min(index++, intervals.length - 1)], Math.max(1, 8000 - (Date.now() - start))));
  }
  throw new Error(label + ': 8000ms diagnostic predicate expired; last=' + JSON.stringify(last));
}

function observe() {
  window.nativeHistoryDiagnostic = [];
  window.nativeHandoffCached = null;
  function identity(element) {
    if (!(element instanceof Element)) return null;
    return { tag: element.tagName, id: element.id, href: element.getAttribute('href'), tabindex: element.getAttribute('tabindex') };
  }
  function note(kind, extra = {}) {
    if (location.pathname !== '/method/' || window.nativeHistoryDiagnostic.length >= 800) return;
    window.nativeHistoryDiagnostic.push({ kind, time: performance.now(), ready: document.readyState, scrollX, scrollY,
      active: identity(document.activeElement), coverageOpen: document.getElementById('coverage-notes')?.open,
      saved: history.state?.nativeDisclosureReturn || null, ...extra });
  }
  const stack = () => String(new Error().stack || '').split('\n').slice(2, 8).join('\n');
  for (const type of ['DOMContentLoaded', 'load', 'focusin', 'focusout', 'scroll', 'hashchange']) {
    addEventListener(type, event => note(type, { target: identity(event.target), trusted: event.isTrusted }), { capture: true });
  }
  addEventListener('pageshow', event => { window.nativeHandoffCached = event.persisted; note('pageshow', { persisted: event.persisted }); }, { capture: true });
  const focus = HTMLElement.prototype.focus;
  HTMLElement.prototype.focus = function (...args) { note('focus-before', { target: identity(this), caller: stack() }); const result = Reflect.apply(focus, this, args); note('focus-after', { target: identity(this) }); return result; };
  for (const name of ['scrollTo', 'scrollBy']) {
    const original = window[name];
    window[name] = function (...args) { note(name + '-before', { caller: stack() }); const result = Reflect.apply(original, window, args); note(name + '-after'); return result; };
  }
  const abort = AbortController.prototype.abort;
  AbortController.prototype.abort = function (...args) { note('abort', { caller: stack() }); return Reflect.apply(abort, this, args); };
  const frame = requestAnimationFrame;
  let sequence = 0;
  window.requestAnimationFrame = function (callback) {
    if (typeof callback !== 'function') return Reflect.apply(frame, window, [callback]);
    const key = ++sequence;
    const caller = stack();
    return Reflect.apply(frame, window, [function (...args) { note('raf-before', { key, caller }); try { return Reflect.apply(callback, this, args); } finally { note('raf-after', { key }); } }]);
  };
}

async function trial(browser, arm, instrumented, index) {
  const label = `${arm.name}-${instrumented ? 'observed' : 'control'}-${index}`;
  const device = { ...devices['iPhone 14'] };
  delete device.defaultBrowserType;
  const context = await browser.newContext({ ...device, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.setDefaultNavigationTimeout(30000);
  const result = { label, arm: arm.name, sourceRef: arm.ref, instrumented, index, errors: [], failedRequests: [], status: 'started' };
  page.on('pageerror', error => result.errors.push(error.message));
  page.on('requestfailed', request => result.failedRequests.push({ url: request.url(), error: request.failure()?.errorText }));
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
  try {
    await page.addInitScript(() => {
      addEventListener('pageshow', event => { window.nativeHandoffCached = event.persisted; });
      if (location.pathname === '/method/') addEventListener('unload', () => {});
    });
    if (instrumented) await page.addInitScript(observe);
    await page.route('https://sciencetostartup.com/**', async route => {
      const { pathname, search } = new URL(route.request().url());
      const response = await route.fetch({ url: new URL(pathname + search, arm.base).href });
      await route.fulfill({ response });
    });
    await page.goto(origin + '/method/#about');
    const coverage = page.locator('#coverage-notes');
    await coverage.locator('summary').press('Enter');
    const source = coverage.getByRole('link', { name: 'current company directory' });
    await source.waitFor({ state: 'visible' });
    result.before = await source.evaluate(anchor => { anchor.scrollIntoView({ block: 'center', behavior: 'instant' }); anchor.focus({ preventScroll: true }); return { scroll: scrollY, top: anchor.getBoundingClientRect().top }; });
    await source.press('Enter');
    await poll('destination', async () => page.url() === origin + '/companies/');
    await page.goBack({ waitUntil: 'commit' });
    await poll('return URL', async () => page.url() === origin + '/method/#about');
    await poll('coverage reopened', async () => (await coverage.getAttribute('open')) === '');
    await poll('source focus', async () => source.evaluate(link => document.activeElement === link));
    await poll('cold page', async () => page.evaluate(() => window.nativeHandoffCached === false));
    await poll('source viewport', async () => source.evaluate(link => { const rect = link.getBoundingClientRect(); return rect.top >= 0 && rect.bottom <= innerHeight; }));
    await poll('return position under3px', async () => source.evaluate((link, before) => Math.max(Math.abs(scrollY - before.scroll), Math.abs(link.getBoundingClientRect().top - before.top)) < 3, result.before));
    await poll('cold navigation type', async () => page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type === 'back_forward'));
    await page.keyboard.press('Tab');
    await poll('following Tab target', async () => page.locator('#download-files > summary').evaluate(node => document.activeElement === node));
    result.status = 'contract-pass';
  } catch (error) {
    result.status = 'contract-fail';
    result.failure = String(error);
  } finally {
    result.final = await page.evaluate(() => ({ url: location.href, scrollY, active: { tag: document.activeElement?.tagName, id: document.activeElement?.id, href: document.activeElement?.getAttribute('href') }, coverageOpen: document.getElementById('coverage-notes')?.open,
      source: [...document.querySelectorAll('#coverage-notes a')].filter(link => link.textContent.trim() === 'current company directory').map(link => ({ top: link.getBoundingClientRect().top, focused: document.activeElement === link })),
      cached: window.nativeHandoffCached, navigation: performance.getEntriesByType('navigation')[0]?.type, events: window.nativeHistoryDiagnostic || [] })).catch(error => ({ evaluationError: String(error) }));
    await page.screenshot({ path: path.join(output, label + '.png'), fullPage: true }).catch(() => {});
    await context.tracing.stop({ path: path.join(output, label + '.zip') });
    await context.close();
    await fs.writeFile(path.join(output, label + '.json'), JSON.stringify(result, null, 2) + '\n');
  }
  console.log(JSON.stringify({ label, status: result.status, failure: result.failure, eventCount: result.final.events?.length }));
  return result;
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  for (const arm of arms) {
    let bytes;
    for (let i = 0; i < 40; i++) { try { const response = await fetch(arm.base + '/manifest.json'); if (response.ok) { bytes = Buffer.from(await response.arrayBuffer()); break; } } catch {} await pause(250); }
    if (!bytes || crypto.createHash('sha256').update(bytes).digest('hex') !== arm.manifest) throw new Error('Wrong diagnostic artifact: ' + arm.name);
  }
  const browser = await webkit.launch();
  const results = [];
  try {
    for (let index = 1; index <= 3; index++) for (const instrumented of [false, true]) for (const arm of arms) results.push(await trial(browser, arm, instrumented, index));
    const summary = { diagnosticOnly: true, releaseGateCertified: false, noProductPatch: true, platform: process.platform, arch: process.arch, playwright: require('playwright/package.json').version, browser: browser.version(), diagnosticCommit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), arms, trialsPerArmPerMode: 3,
      results: results.map(({ label, status, failure, instrumented, arm }) => ({ label, status, failure, instrumented, arm })) };
    await fs.writeFile(path.join(output, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
