const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const { createRequire } = require('node:module');
const path = require('node:path');
const { after, before, test } = require('node:test');

const repoRequire = createRequire(path.resolve(__dirname, '../../sciencetostartup/package.json'));
const { chromium } = process.env.QA_PLAYWRIGHT_MODULE
  ? require(process.env.QA_PLAYWRIGHT_MODULE)
  : repoRequire('playwright');
const baseURL = process.env.QA_BASE_URL || 'https://sciencetostartup.com';
const wait = 8_000;
let browser;

before(async () => {
  browser = await chromium.launch({
    executablePath: process.env.QA_BROWSER_EXECUTABLE || undefined,
    proxy: process.env.QA_PROXY ? { server: process.env.QA_PROXY } : undefined,
    headless: true,
  });
});

after(async () => browser?.close());

function check(name, callback) {
  test(name, { timeout: 30_000 }, async () => {
    const page = await browser.newPage({
      baseURL,
      acceptDownloads: true,
      ignoreHTTPSErrors: process.env.QA_IGNORE_HTTPS_ERRORS === '1',
    });
    page.setDefaultTimeout(wait);
    try {
      await callback(page);
    } finally {
      await page.close();
    }
  });
}

async function visit(page, pathname) {
  const response = await page.goto(pathname, { waitUntil: 'domcontentloaded' });
  assert.ok(response?.ok(), `${pathname} returned ${response?.status()}`);
}

function csvRouteIds(source) {
  const rows = [];
  let row = [];
  for (const [, cell, delimiter] of source.replace(/^\uFEFF/u, '').matchAll(/("(?:[^"]|"")*"|[^,\r\n]*)(,|\r?\n|$)/gu)) {
    if (!cell && !delimiter && !row.length) break;
    row.push(cell.startsWith('"') ? cell.slice(1, -1).replaceAll('""', '"') : cell);
    if (delimiter !== ',') {
      rows.push(row);
      row = [];
    }
  }
  const [header, ...records] = rows;
  const field = header?.indexOf('route_id') ?? -1;
  assert.ok(field >= 0, 'Downloaded CSV has a route_id column');
  assert.ok(records.every(fields => fields.length === header.length), 'Every CSV record matches the header width');
  return records.map(fields => fields[field]).sort();
}

async function workCsvControl(page) {
  const name = /(?:download|export).*\bcsv\b/i;
  const control = page.getByRole('button', { name, includeHidden: true })
    .or(page.getByRole('link', { name, includeHidden: true }));
  if (await control.count() === 0) {
    await page.getByRole('link', { name: /compare pay and download results/i }).click();
    await page.locator('#work-view').waitFor({ state: 'visible' });
  }
  const exportControl = control.first();
  await exportControl.waitFor({ state: 'attached' });
  if (!(await exportControl.isVisible())) {
    const details = exportControl.locator('xpath=ancestor::details[1]');
    if (await details.count()) await details.locator(':scope > summary').click();
  }
  return exportControl;
}

for (const sample of [
  { label: 'Snorkel remote program', filters: { q: 'Snorkel', kind: 'programs', arrangement: 'remote' } },
  { label: 'career-page bucket', filters: { kind: 'boards' } },
]) {
  check(`Work CSV preserves the native selection for the ${sample.label}`, async page => {
    await visit(page, `/work/?${new URLSearchParams(sample.filters)}`);
    const form = page.locator('[data-work-filters]');
    await form.waitFor({ state: 'visible' });
    for (const [filter, value] of Object.entries(sample.filters)) {
      assert.equal(await form.locator(`[name="${filter}"]`).inputValue(), value);
    }
    const selection = await page.locator('[data-work-route]:visible').evaluateAll(rows => rows.map(row => ({
      id: row.dataset.workRoute,
      kind: row.closest('[data-work-group]')?.dataset.workGroup,
    })));
    assert.ok(selection.length && selection.every(row => row.kind === sample.filters.kind),
      'Visible native records belong to the selected listing type');
    const expected = selection.map(row => row.id).sort();

    const control = await workCsvControl(page);
    const [download] = await Promise.all([page.waitForEvent('download'), control.click()]);
    const actual = csvRouteIds(await readFile(await download.path(), 'utf8'));
    const missing = expected.filter(id => !actual.includes(id));
    const extra = actual.filter(id => !expected.includes(id));
    assert.ok(actual.length === expected.length && missing.length === 0 && extra.length === 0,
      `Native selection has ${expected.length} IDs, CSV has ${actual.length}. Missing ${missing.slice(0, 5).join(', ') || 'none'}. Unexpected ${extra.slice(0, 5).join(', ') || 'none'}.`);
  });
}

const comparePath = '/explore/#compare/snorkel_ai/scale_ai';
const compareColumns = '#compare-content th a:visible';

async function waitForGuide(page) {
  await page.waitForFunction(() => ['ready', 'failed'].includes(document.documentElement.dataset.viewState));
}

check('An explicit invalid comparison never reuses the previous comparison', async page => {
  await visit(page, comparePath);
  await page.locator('#compare-content table').waitFor({ state: 'visible' });
  assert.deepEqual(await page.locator(compareColumns).allTextContents(), ['Snorkel AI', 'Scale AI']);

  await page.evaluate(async () => {
    await new Promise(resolve => {
      window.addEventListener('hashchange', resolve, { once: true });
      window.location.hash = '#compare/no_match';
    });
    await window.APP_ROUTE_READY;
  });
  await waitForGuide(page);
  assert.deepEqual(await page.locator(compareColumns).allTextContents(), [],
    'The same-page invalid URL must not show the previous company columns');
  assert.notEqual(new URL(page.url()).hash, '#compare/snorkel_ai/scale_ai',
    'The invalid URL must not become a link to the previous selection');
  assert.equal(await page.locator('#app-failure').isVisible(), false, 'The guide should handle the invalid selection inline');
});

check('Snorkel AI and Scale AI compare without unrelated TaskUs or Appen evidence', async page => {
  const unrelated = /\/presentation\/company-(?:taskus|appen)\.[0-9a-f]+\.json$/u;
  const requests = [];
  page.on('request', request => {
    if (unrelated.test(new URL(request.url()).pathname)) requests.push(new URL(request.url()).pathname);
  });
  await page.route(url => unrelated.test(url.pathname), route => route.abort());
  await visit(page, comparePath);
  await waitForGuide(page);

  const names = await page.locator(compareColumns).allTextContents();
  assert.deepEqual(names, ['Snorkel AI', 'Scale AI'],
    `Requested comparison should render. Unrelated requests: ${requests.join(', ') || 'none'}. Guide state: ${await page.locator('html').getAttribute('data-view-state')}.`);
  assert.deepEqual(requests, [], 'An explicit comparison should not request default example evidence');
  assert.equal(await page.locator('#app-failure').isVisible(), false);
});

const paper = '/research/papers/paper.arxiv.2203.02155';
const basePaper = `${paper}/`;
const versionPaper = `${paper}v1/`;

for (const [query, destination] of [
  ['arXiv:2203.02155', basePaper],
  ['arXiv:2203.02155v1', versionPaper],
  ['2203.02155', basePaper],
  ['10.48550/arXiv.2203.02155', basePaper],
]) {
  check(`Homepage search opens the exact paper for ${query}`, async page => {
    await visit(page, '/?search');
    const input = page.locator('#home-search-input');
    const first = page.locator('#home-search-results [role=option]').first();
    await input.waitFor({ state: 'visible' });
    await first.waitFor({ state: 'visible' });
    await input.fill(query);
    assert.equal(await first.getAttribute('href'), destination, `Top result for ${query}`);
    await first.click();
    await page.waitForURL(url => url.pathname === destination);
    assert.match(await page.title(), /Training language models to follow instructions with human feedback/i);
  });
}

for (const [query, destination] of [
  ['arXiv:2203.02155', basePaper],
  ['arXiv:2203.02155v1', versionPaper],
]) {
  check(`Papers index URL filter exposes the exact paper for ${query}`, async page => {
    await visit(page, `/research/papers/?${new URLSearchParams({ q: query })}`);
    await page.locator('[data-index-controls]').waitFor({ state: 'visible' });
    const visible = page.locator('[data-index-row]:visible th a');
    const results = await visible.evaluateAll(nodes => nodes.map(node => ({
      href: node.getAttribute('href'),
      label: node.closest('[data-index-row]').innerText,
    })));
    assert.equal(results[0]?.href, destination,
      `Expected ${destination} first. Visible paper records: ${results.map(result => result.href).join(', ') || 'none'}.`);
    const related = destination === versionPaper && results.find(result => result.href === basePaper);
    if (related) assert.match(related.label, /\b(?:related|context)\b|paper[ _-]work/i,
      'A secondary paper work row is labeled as related to the source version');
    await visible.first().click();
    await page.waitForURL(url => url.pathname === destination);
  });
}
