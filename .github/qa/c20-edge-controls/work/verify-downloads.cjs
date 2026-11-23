/* Verify the three real Work downloads against the source and exact native donor. */
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const { createRequire } = require('node:module');
const path = require('node:path');

const { chromium } = createRequire(path.resolve('package.json'))('@playwright/test');
const expected = require('./expected.json');
const output = path.resolve(process.argv[2] || 'output/c20-controls/work-downloads');
const site = new URL(process.env.QA_BASE_URL);
assert.equal(site.href, site.origin + '/');
const manifest = readFileSync('dist/manifest.json');
const donor = readFileSync(path.join(__dirname, 'signed-native.csv'));
const dist = JSON.parse(manifest);
const digest = value => createHash('sha256').update(value).digest('hex');
const downloads = [];
mkdirSync(output, { recursive: true });

function boundary() {
  const bytes = execFileSync('curl', [
    '--fail', '--silent', '--show-error', '--max-time', '25',
    '--header', 'Accept-Encoding: identity', '--header', 'Cache-Control: no-cache',
    '--user-agent', 'ScienceToStartup-ReleaseVerification/1.0', site.origin + '/manifest.json',
  ]);
  const checksum = digest(bytes);
  assert.equal(checksum, expected.manifest_sha256);
  assert.ok(bytes.equals(manifest), 'Edge and checkout manifest bytes');
  return checksum;
}

async function recordIds(locator, property) {
  return locator.evaluateAll((nodes, id) => nodes.map(node => node.dataset[id]), property);
}

async function expand(page, selector) {
  // Opening one group changes the selector, so keep the original DOM handles.
  const summaries = await page.locator(selector).elementHandles();
  for (const summary of summaries) {
    if (await summary.isVisible()) await summary.press('Enter');
  }
}

async function download(page, control, ids, scope) {
  assert.deepEqual(ids, expected.ordered_ids, scope + ' visible record order');
  const [artifact] = await Promise.all([
    page.waitForEvent('download', { timeout: 45000 }),
    page.locator(control).press('Enter'),
  ]);
  assert.equal(artifact.suggestedFilename(), 'sciencetostartup-current-work-results.csv');
  const body = readFileSync(await artifact.path());
  assert.equal(digest(body), expected.donor_sha256, scope + ' CSV hash');
  assert.ok(body.equals(donor), scope + ' exact CSV bytes');
  writeFileSync(path.join(output, 'work-all-' + scope + '.csv'), body);
  downloads.push({
    scope, download_sha256: digest(body), rows: expected.row_count, columns: expected.column_count, ordered_ids: ids,
  });
}

async function journey(browser) {
  const page = await browser.newPage({ baseURL: site.origin, acceptDownloads: true });
  page.setDefaultTimeout(45000);
  const response = await page.goto('/work/', { waitUntil: 'domcontentloaded' });
  assert.equal(response?.status(), 200, 'Native Work HTTP response');
  await page.waitForFunction(() => !!document.querySelector('[data-work-export]') &&
    !document.documentElement.hasAttribute('data-work-load'));
  await expand(page, '.work-page-list details[data-work-group]:not([open]):not([hidden]) > summary');
  await download(page, '[data-work-export]',
    await recordIds(page.locator('.work-page-list [data-work-route]:visible'), 'workRoute'), 'native');
  await page.locator('[data-work-compare]').click();
  const rows = page.locator('[data-compare-route]:visible');
  await rows.first().waitFor();
  await download(page, '[data-work-export]', await recordIds(rows, 'compareRoute'), 'compare');
  await page.goBack({ waitUntil: 'domcontentloaded' });
  await page.locator('[data-work-explore]').click();
  await page.locator('#work-cards [data-work-route]').first().waitFor();
  await expand(page, '#work-cards details.w4-route-group:not([open]) > summary');
  await page.waitForFunction(() => !document.querySelector('#work-cards .w4-route-group[open] [data-w4-routes]'));
  await download(page, '#work-export',
    await recordIds(page.locator('#work-cards [data-work-route]:visible'), 'workRoute'), 'explore');
}

function launchOptions() {
  const proxyUrl = process.env.HTTPS_PROXY || process.env.https_proxy;
  if (site.protocol !== 'https:' || !proxyUrl) return {};
  const address = new URL(proxyUrl);
  const proxy = { server: address.origin };
  if (address.username) proxy.username = decodeURIComponent(address.username);
  if (address.password) proxy.password = decodeURIComponent(address.password);
  return { proxy };
}

(async () => {
  let before = null, after = null, oracle, problem;
  try {
    assert.equal(digest(manifest), expected.manifest_sha256);
    assert.equal(dist.build_id, expected.build);
    oracle = JSON.parse(execFileSync('python3', ['-B', path.join(__dirname, 'check-source.py')], { encoding: 'utf8' }));
    before = boundary();
    const browser = await chromium.launch(launchOptions());
    try {
      await journey(browser);
    } finally {
      await browser.close();
    }
  } catch (error) {
    problem = error.message;
  }
  if (before) {
    try {
      after = boundary();
    } catch (error) {
      problem = [problem, 'Manifest after: ' + error.message].filter(Boolean).join('\n');
    }
  }
  const summary = {
    passed: !problem && downloads.length === 3, before, after, build: dist.build_id,
    canonical_row_count: oracle?.rows, canonical_csv_sha256: oracle?.canonical_csv_sha256,
    independent_csv_sha256: oracle?.independent_csv_sha256, downloads, error: problem,
  };
  writeFileSync(path.join(output, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
  console.log(JSON.stringify({ passed: summary.passed, build: summary.build, scopes: downloads.map(row => row.scope), error: problem }));
  process.exitCode = summary.passed ? 0 : 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
