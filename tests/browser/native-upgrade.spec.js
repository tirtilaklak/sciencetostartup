const { test, expect } = require('@playwright/test');
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { gunzipSync } = require('node:zlib');

const company = '/company/imerit/';
const chapter = '/research/state-of-ai-data-labs/chapters/technical-landscape/';
const scriptPath = '/native-details.js';
const ledger = '/explore/#company/imerit/sources';
const canonical = 'https://sciencetostartup.com';
const fixture = join(__dirname, '../fixtures/previous-native');
const preceding = require('../fixtures/previous-native/manifest.json');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');

function previousFile(pathname) {
  return preceding.files[pathname.slice(1) + (pathname.endsWith('/') ? 'index.html' : '')];
}

function previous(pathname) {
  const { fixture: name, sha256 } = previousFile(pathname);
  const file = readFileSync(join(fixture, name));
  const bytes = name.endsWith('.gz') ? gunzipSync(file) : file;
  expect(digest(bytes)).toBe(sha256);
  return bytes;
}

const cases = [
  { name: 'preceding document, current script', script: 'current', oldDocument: true },
  { name: 'current document, preceding script', script: 'preceding' },
  { name: 'current document, script unavailable', script: 'unavailable' },
];

test.use({ reducedMotion: 'reduce', trace: { mode: 'retain-on-failure', snapshots: false } });

async function prepare({ context, baseURL }, pathname, variant) {
  const origin = new URL(baseURL).origin;
  const matches = path => url => url.origin === origin && url.pathname === path;
  if (variant.oldDocument) {
    const body = previous(pathname);
    await context.route(matches(pathname), route => route.fulfill({ contentType: 'text/html', body }));
  }
  if (variant.script === 'preceding') {
    const body = previous(scriptPath);
    await context.route(matches(scriptPath), route => route.fulfill({ contentType: 'application/javascript', body }));
  } else if (variant.script === 'unavailable') {
    await context.route(matches(scriptPath), route => route.abort());
  }
}

async function visit(page, pathname, variant, info) {
  const isScript = url => new URL(url).pathname === scriptPath;
  const script = variant.script === 'unavailable'
    ? page.waitForEvent('requestfailed', { predicate: request => isScript(request.url()) })
    : page.waitForResponse(response => isScript(response.url()));
  const document = await page.goto(pathname);
  expect(document.ok()).toBe(true);
  const receipt = { document: { url: document.url(), sha256: digest(await document.body()) } };
  const asset = await script;
  if (variant.oldDocument) expect(receipt.document.sha256).toBe(previousFile(new URL(document.url()).pathname).sha256);
  if (variant.script === 'unavailable') {
    receipt.script = { url: asset.url(), failure: asset.failure().errorText };
  } else {
    expect(asset.ok()).toBe(true);
    receipt.script = { url: asset.url(), sha256: digest(await asset.body()) };
    if (variant.script === 'preceding') expect(receipt.script.sha256).toBe(previousFile(scriptPath).sha256);
  }
  await info.attach('served-document-and-script.json', { body: JSON.stringify(receipt), contentType: 'application/json' });
}

for (const variant of cases) {
  test(`native Research anchors with ${variant.name}`, async ({ page, context, baseURL }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await prepare({ context, baseURL }, chapter, variant);
    await visit(page, chapter, variant, info);
    const source = page.locator('.r-bulk-shortcuts a[href="#scalable-oversight-result"]');
    const destination = page.locator('#scalable-oversight-result');
    const original = page.url();
    const bookmark = new URL(await source.getAttribute('href'), original).href;

    await source.focus();
    const scroll = await page.evaluate(() => scrollY);
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(bookmark);
    await expect(destination).toBeFocused();
    await expect(destination).toBeInViewport();
    await page.goBack();
    await expect(page).toHaveURL(original);
    await expect(source).toBeInViewport();
    expect(await page.evaluate(() => scrollY)).toBeCloseTo(scroll, 0);
    if (variant.script === 'current') await expect(source).toBeFocused();
    await page.goForward();
    await expect(page).toHaveURL(bookmark);
    if (variant.script === 'current') {
      await expect(destination).toBeFocused();
      await expect(destination).toBeInViewport();
    }

    const copied = await context.newPage();
    await copied.goto(bookmark);
    await expect(copied.locator('#scalable-oversight-result:target')).toBeInViewport();
    await copied.close();
  });

  test(`native company anchors with ${variant.name}`, async ({ page, context, baseURL }, info) => {
    // Preserve the production URL and its absolute handoff while serving local artifact bytes.
    await context.route(canonical + '/**', async route => {
      const { pathname, search } = new URL(route.request().url());
      const response = await route.fetch({ url: new URL(pathname + search, baseURL).href });
      await route.fulfill({ response });
    });
    await prepare({ context, baseURL: canonical }, company, variant);
    await context.addInitScript(path => {
      if (location.pathname !== path) return;
      addEventListener('unload', () => {});
      addEventListener('pageshow', event => { window.nativeUpgradePersisted = event.persisted; });
    }, company);
    await visit(page, canonical + company, variant, info);
    const summary = page.locator('summary#sources, #sources > summary');
    const source = page.getByRole('link', { name: 'Source ledger', exact: true });
    const original = page.url();
    await summary.press('Enter');
    await expect(source).toHaveAttribute('href', canonical + ledger);
    await source.press('Enter');
    await expect(page).toHaveURL(canonical + ledger);
    await expect(page.getByRole('heading', { name: 'All sources', exact: true })).toBeInViewport();

    await page.goBack();
    await expect(page).toHaveURL(original);
    await expect.poll(() => page.evaluate(() => window.nativeUpgradePersisted)).toBe(false);
    if (variant.script === 'current') {
      await expect(source).toBeFocused();
      await expect(source).toBeInViewport({ ratio: 1 });
      await page.keyboard.press('Tab');
      await expect(page.getByRole('link', { name: 'Funding and people', exact: true })).toBeFocused();
    } else {
      await expect(summary).toBeVisible();
      await summary.press('Enter');
      await expect(source).toBeVisible();
    }

    await page.locator('.company-hero a[href="#work"]').press('Enter');
    await expect(page).toHaveURL(original + '#work');
    await expect(page.locator('#work:target')).toBeInViewport();

    if (variant.script === 'unavailable') {
      const copied = await context.newPage();
      await copied.goto(page.url());
      await expect(copied.locator('#work:target')).toBeInViewport();
      await copied.close();
    }
  });
}
