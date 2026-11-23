const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { chromium, devices } = require('playwright');

const setup = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const output = process.argv[3];
const origin = setup.origin;
assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
const chapter = '/research/state-of-ai-data-labs/chapters/technical-landscape/';
const recordId = 'assertion-cohort6.claim.gpqa.gpt4-result';
const sourceId = 'source-cohort6.source.gpqa.gpt4-result';
const assertionPath = '/research/data/assertions/1/#' + recordId;
const sourcePath = '/research/data/sources/6/#' + sourceId;
const phrase = '39.7% on the 448-question main split';

async function addTimeline(context) {
  await context.addInitScript(({ recordId }) => {
    if (location.hash !== '#' + recordId) return;
    const timeline = window.__ledgerTimeline = [];
    function record(event, end = false) {
      if (timeline.length > 180) return;
      const target = document.getElementById(recordId);
      const top = end ? target?.getBoundingClientRect().top : undefined;
      timeline.push({ event, top, ms: performance.now(), y: scrollY, target: target?.matches(':target'),
        stable: document.documentElement?.hasAttribute('data-ledger-fragment'),
        navigation: performance.getEntriesByType('navigation')[0]?.type });
    }
    record('init');
    for (const name of ['DOMContentLoaded', 'load', 'pageshow', 'pagehide', 'scroll']) {
      addEventListener(name, event => {
        record(name === 'pageshow' && event.persisted ? 'pageshow-persisted' : name);
        if (name === 'pageshow') requestAnimationFrame(() => record('frame-after-pageshow'));
      }, { passive: true });
    }
    window.__ledgerEnd = () => record('settled', true);
  }, { recordId });
}

async function readingSnapshot(page, id = recordId) {
  return page.evaluate(id => {
    const target = document.getElementById(id);
    const bounds = target?.getBoundingClientRect();
    return {
      y: scrollY, targetTop: bounds?.top, targetBottom: bounds?.bottom, url: location.href,
      visible: Boolean(bounds && bounds.bottom > 0 && bounds.top < innerHeight),
      target: target?.matches(':target'),
      cardVisibility: target && getComputedStyle(target).contentVisibility,
      precedingCardVisibility: target?.previousElementSibling && getComputedStyle(target.previousElementSibling).contentVisibility,
      direction: performance.getEntriesByType('navigation')[0]?.type,
    };
  }, id);
}

async function citationPoint(citation) {
  return citation.evaluate(el => {
    for (const rect of el.getClientRects()) {
      const left = Math.max(0, rect.left), right = Math.min(innerWidth, rect.right);
      const top = Math.max(0, rect.top), bottom = Math.min(innerHeight, rect.bottom);
      const x = (left + right) / 2, y = (top + bottom) / 2;
      if (right > left && bottom > top && el.contains(document.elementFromPoint(x, y))) return { x, y };
    }
    return null;
  });
}

async function test(page, variant, cssDelay, instrumented) {
  const started = await page.goto(origin + chapter);
  assert.equal(started.status(), 200);
  await page.locator('html[data-reader-enhanced]').waitFor();
  assert.equal(await page.evaluate(text => window.find(text) ? getSelection().toString() : null, phrase), phrase);
  const citation = page.locator('.r-reader-chapter-content > .r-paragraph').filter({ hasText: phrase })
    .locator(`.r-paragraph-citations a[href="${assertionPath}"]`);
  let point = await citationPoint(citation);
  if (!point) {
    await citation.scrollIntoViewIfNeeded();
    point = await citationPoint(citation);
  }
  assert.ok(point);
  await page.touchscreen.tap(point.x, point.y);
  await page.waitForURL(origin + assertionPath);
  const firstAssertion = await readingSnapshot(page);
  assert.ok(firstAssertion.visible && firstAssertion.target);
  const assertion = page.locator(`:target[id="${recordId}"]`);
  const sourceLink = assertion.locator(`a[href="${sourcePath}"]`);
  await sourceLink.tap();
  await page.waitForURL(origin + sourcePath);
  const source = await readingSnapshot(page, sourceId);
  assert.ok(source.visible && source.target);
  await page.goBack();
  await page.waitForURL(origin + assertionPath);
  await new Promise(resolve => setTimeout(resolve, 650));
  const settled = await readingSnapshot(page);
  assert.ok(settled.target);
  const timeline = await page.evaluate(() => {
    window.__ledgerEnd?.();
    return window.__ledgerTimeline;
  });
  return { variant, cssDelay, instrumented, firstAssertion, source, settled, timeline };
}

(async () => {
  const manifest = await (await fetch(origin + '/manifest.json')).arrayBuffer();
  const digest = createHash('sha256').update(Buffer.from(manifest)).digest('hex');
  assert.equal(digest, setup.control_manifest);
  const results = [];
  const save = () => fs.writeFileSync(output, JSON.stringify({ setup, results }, null, 2) + '\n');
  const browser = await chromium.launch();
  try {
    const pairs = [
      { cssDelay: 0, instrumented: false },
      { cssDelay: 0, instrumented: true },
      { cssDelay: 40, instrumented: true },
      { cssDelay: 90, instrumented: true },
    ];
    for (const { cssDelay, instrumented } of pairs) {
      for (const variant of ['control', 'stable']) {
        const context = await browser.newContext({
          ...devices['Pixel 7'], viewport: { width: 390, height: 844 },
          extraHTTPHeaders: { 'X-QA-Ledger-Layout': variant, 'X-QA-Stylesheet-Delay-Ms': String(cssDelay) },
        });
        if (instrumented) await addTimeline(context);
        const trace = `browser-${cssDelay}-${instrumented ? 'timeline' : 'ordinary'}-${variant}.zip`;
        await context.tracing.start({ screenshots: true, snapshots: false });
        const page = await context.newPage();
        page.setDefaultTimeout(8000);
        try {
          results.push({ ...await test(page, variant, cssDelay, instrumented), trace });
        } catch (error) {
          results.push({ variant, cssDelay, instrumented, error: error.message, trace });
        } finally {
          await context.tracing.stop({ path: path.join(path.dirname(output), trace) });
          await context.close();
          save();
        }
      }
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify(results.map(row => ({
    variant: row.variant, delay: row.cssDelay, visible: row.settled?.visible, y: row.settled?.y,
    first: row.firstAssertion?.y, error: row.error,
  }))));
  process.exitCode = Number(results.length !== 8 || results.some(row => row.error));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
