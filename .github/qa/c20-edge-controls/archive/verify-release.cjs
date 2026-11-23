const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const { createRequire } = require('node:module');
const path = require('node:path');

const checkout = process.cwd();
const artifact = path.resolve(process.env.QA_DIST || 'dist');
const origin = new URL(process.env.QA_BASE_URL).origin;
const { chromium } = createRequire(path.join(checkout, 'package.json'))('playwright');
const archiveFiles = ['report.html', 'executive-brief.html', 'evidence.html'];
const ordinaryNavigation = 25_000;
const appendixTimeout = Number(process.env.ARCHIVE_EVIDENCE_TIMEOUT_MS || 180_000);
assert(Number.isInteger(appendixTimeout) && appendixTimeout >= ordinaryNavigation && appendixTimeout <= 180_000);

// The public site can append this exact analytics script. Immutable origins use raw bytes.
const knownBeacon = new RegExp("<script type=\"module\" src=\"https://static\\.cloudflareinsights\\.com/beacon\\.min\\.js/v[0-9a-f]+\" integrity=\"sha512-[A-Za-z0-9+/]{86}==\" data-cf-beacon=\\'\\{\"version\":\"[0-9]+\\.[0-9]+\\.[0-9]+\",\"token\":\"[0-9a-f]{32}\",\"r\":1,\"spa\":2\\}\\' crossorigin=\"anonymous\"></script>\\n(?=</body>\\n</html>\\n(?![\\s\\S]))");
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const absolute = relative => new URL(relative, origin).href;
const depositedAppendix = destination => new URL(destination, origin).pathname === '/publication/evidence';

async function routes(manifest, custom404, records) {
  async function check(requested, expectedStatus, { location = null, robots, sha } = {}) {
    const timeout = depositedAppendix(requested) && expectedStatus === 200 ? appendixTimeout : 30_000;
    const response = await fetch(absolute(requested), {
      redirect: 'manual', headers: { 'User-Agent': 'ScienceToStartup-ReleaseVerification/1.0' },
      signal: AbortSignal.timeout(timeout),
    });
    const bytes = Buffer.from(await response.arrayBuffer());
    const responseLocation = response.headers.get('location');
    const html = response.headers.get('content-type')?.includes('text/html');
    const normalized = new URL(origin).hostname === 'sciencetostartup.com' && html
      ? Buffer.from(bytes.toString('latin1').replace(knownBeacon, ''), 'latin1') : bytes;
    const record = {
      requested, status: response.status, location: responseLocation,
      robots: response.headers.get('x-robots-tag'), length: bytes.length,
      raw_sha256: digest(bytes), sha256: digest(normalized), timeout_ms: timeout,
    };
    records.push(record);
    assert.equal(record.status, expectedStatus, requested);
    assert.equal(responseLocation && absolute(responseLocation), location && absolute(location), requested);
    if (robots) assert.equal(record.robots, robots, requested);
    if (sha) assert.equal(record.sha256, sha, requested);
  }

  for (const name of archiveFiles) {
    const stem = '/publication/' + name.slice(0, -5);
    await check('/publication/' + name, 307, { location: stem });
    await check(stem + '/?edition=offline', 307, { location: stem + '?edition=offline' });
    await check(stem, 200, { robots: 'noindex', sha: digestFor(manifest, 'publication/' + name) });
  }
  for (const directory of ['/work', '/companies', '/company/afterquery', '/research', '/research/state-of-ai-data-labs']) {
    await check(directory, 307, { location: directory + '/' });
    await check(directory + '/', 200, { sha: digestFor(manifest, directory.slice(1) + '/index.html') });
  }
  for (const missing of ['/company', '/publication/report/evidence.html', '/publication/evidence/evidence.html', '/static/qa-missing.js', '/api/qa-retired']) {
    await check(missing, 404, { sha: custom404 });
  }
  for (const asset of ['report.pdf', 'research-archive.zip']) {
    await check('/publication/' + asset, 200, { sha: digestFor(manifest, 'publication/' + asset) });
  }
}

function digestFor(manifest, name) {
  const value = manifest.sha256[name];
  assert.match(value, /^[a-f0-9]{64}$/, name);
  return value;
}

async function click(page, selector, relative, target = null) {
  const destination = absolute(relative);
  const link = page.locator(selector).first();
  const href = await link.getAttribute('href');
  const resolved = await link.evaluate(anchor => anchor.href);
  const timeout = depositedAppendix(destination) ? appendixTimeout : ordinaryNavigation;
  const started = Date.now();
  console.log(`Chromium ${new URL(page.url()).pathname} → ${relative}`);
  const [navigation] = await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout }),
    link.click({ timeout, noWaitAfter: true }),
  ]);
  assert.equal(page.url(), destination, selector);
  assert.equal(navigation?.status(), 200, selector);
  const actualTarget = await page.evaluate(() => document.querySelector(':target')?.id ?? null);
  assert.equal(actualTarget, target, selector);
  return { href, resolved, destination, status: navigation.status(), target: actualTarget,
    elapsed_ms: Date.now() - started, timeout_ms: timeout };
}

async function browserJourney(records) {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, javaScriptEnabled: false });
    const page = await context.newPage();
    page.setDefaultTimeout(15_000);
    page.setDefaultNavigationTimeout(ordinaryNavigation);
    const reader = await page.goto(absolute('/research/state-of-ai-data-labs/'), { waitUntil: 'domcontentloaded' });
    assert.equal(reader?.status(), 200);
    records.push(await click(page, '.r-reader-downloads a[href="/publication/report.html"]', '/publication/report'));
    records.push(await click(page, 'nav[aria-label="Offline edition"] a[href="executive-brief.html"]', '/publication/executive-brief'));
    const finding = 'finding-delivery-unit-before-provider';
    records.push(await click(page, `a[href="report.html#${finding}"]`, `/publication/report#${finding}`, finding));
    const assertion = 'assertion-cohort4.claim.osworld.side-effect-gap';
    records.push(await click(page, `a[href="evidence.html#${assertion}"]`, `/publication/evidence#${assertion}`, assertion));

    const source = 'source-cohort4.source.osworld.side-effect-gap';
    const sameDocument = page.locator(`a[href="evidence.html#${source}"]`).first();
    const resolved = await sameDocument.evaluate(anchor => anchor.href);
    const destination = absolute(`/publication/evidence#${source}`);
    const started = Date.now();
    console.log(`Chromium evidence self-reference → ${source}`);
    await Promise.all([
      page.waitForURL(destination, { timeout: appendixTimeout }),
      sameDocument.click({ timeout: appendixTimeout, noWaitAfter: true }),
    ]);
    assert.equal(await page.evaluate(() => document.querySelector(':target')?.id), source);
    records.push({ href: `evidence.html#${source}`, resolved, destination, target: source,
      elapsed_ms: Date.now() - started, timeout_ms: appendixTimeout });
    records.push(await click(page, 'a[href="report.html"]', '/publication/report'));

    const bookmark = absolute(`/publication/report/?edition=offline#${finding}`);
    const navigated = await page.goto(bookmark, { waitUntil: 'domcontentloaded' });
    assert.equal(navigated?.status(), 200);
    assert.equal(page.url(), absolute(`/publication/report?edition=offline#${finding}`));
    assert.equal(await page.evaluate(() => document.querySelector(':target')?.id), finding);
    records.push({ incomingBookmark: bookmark, destination: page.url(), status: navigated.status(), target: finding });
    records.push(await click(page, 'nav[aria-label="Offline edition"] a[href="evidence.html"]', '/publication/evidence'));
  } finally {
    await browser.close();
  }
}

async function main() {
  const receipt = { mode: 'auto-trailing-slash', origin, compatibilityDate: null, workerd: null, routes: [], browser: [] };
  let phase = 'inputs';
  try {
    const config = JSON.parse(await fs.readFile(path.join(checkout, 'deployment.json'), 'utf8'));
    assert.equal(config.assets.html_handling, receipt.mode);
    assert.equal(config.assets.not_found_handling, '404-page');
    assert.equal(config.assets.run_worker_first, false);
    receipt.compatibilityDate = config.compatibility_date;
    const manifest = JSON.parse(await fs.readFile(path.join(artifact, 'manifest.json'), 'utf8'));
    const custom404 = digest(await fs.readFile(path.join(artifact, '404.html')));
    assert.equal(custom404, digestFor(manifest, '404.html'));
    phase = 'http';
    await routes(manifest, custom404, receipt.routes);
    phase = 'browser';
    await browserJourney(receipt.browser);
    assert.equal(receipt.routes.length, 26);
    assert.equal(receipt.browser.length, 8);
    console.log(`${receipt.routes.length} HTTP checks and ${receipt.browser.length} Chromium navigation checks passed`);
  } catch (error) {
    receipt.error = { phase, message: error.message };
    throw error;
  } finally {
    await fs.writeFile(process.env.ARCHIVE_RECEIPT, JSON.stringify([receipt], null, 2) + '\n', { flag: 'wx' });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
