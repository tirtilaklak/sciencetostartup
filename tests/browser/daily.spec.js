const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const { readFileSync, readdirSync } = require('node:fs');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '../..');
const artifact = path.resolve(process.env.QA_DIST || path.join(root, 'dist'));
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const manifestBytes = readFileSync(path.join(artifact, 'manifest.json'));
const manifest = JSON.parse(manifestBytes);
const sourceDirectory = path.join(root, 'data/daily-scan');
const sourceFiles = readdirSync(sourceDirectory).filter(name => /^\d{4}-\d{2}-\d{2}\.json$/.test(name)).sort();
const editions = sourceFiles.map(name => JSON.parse(readFileSync(path.join(sourceDirectory, name))));
if (!editions.length) throw new Error('Daily browser checks require actual committed source snapshots');
const latest = editions.at(-1);
const previous = editions.at(-2) || latest;
const oldest = editions[0];
// Sample at most three real dates inside fixed tests; adding a day adds no cases.
const sampled = [...new Map([latest, previous, oldest].map(edition => [edition.date, edition])).values()];
const contentRoutes = [{ route: '/daily/', edition: latest }, ...sampled.map(edition => ({
  route: `/daily/${edition.date}/`, edition,
}))];
const readingRoutes = [{ route: '/daily/', edition: latest }, ...sampled.filter(edition => edition !== latest)
  .map(edition => ({ route: `/daily/${edition.date}/`, edition }))];
const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim();
const sourceTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], { cwd: root, encoding: 'utf8' }).trim();
const sourceHashes = Object.fromEntries(sampled.map(edition => [edition.date,
  digest(readFileSync(path.join(sourceDirectory, edition.date + '.json')))]));

async function verifiedResponse(request, route, filename) {
  const response = await request.get(route);
  expect(response.ok(), route).toBeTruthy();
  const bytes = await response.body();
  expect(manifest.sha256[filename], 'Frozen artifact must bind ' + filename).toMatch(/^[a-f0-9]{64}$/);
  expect(digest(bytes), 'Exact frozen response: ' + route).toBe(manifest.sha256[filename]);
  return bytes;
}

test.beforeEach(async ({ page, request }, info) => {
  const response = await request.get('/manifest.json');
  expect(response.ok()).toBeTruthy();
  const actual = await response.body();
  expect(digest(actual), 'Server must serve this checkout\'s complete frozen manifest').toBe(digest(manifestBytes));
  expect(JSON.parse(actual)).toEqual(manifest);
  await info.attach('daily-source-artifact-identity.json', {
    body: Buffer.from(JSON.stringify({ sourceCommit, sourceTree, sourceSnapshots: sourceHashes,
      buildId: manifest.build_id, editorialReleaseId: manifest.editorial_release_id,
      manifestSHA256: digest(manifestBytes), sampledDates: sampled.map(edition => edition.date) })),
    contentType: 'application/json',
  });
  info._dailyRuntimeErrors = [];
  page.on('pageerror', error => info._dailyRuntimeErrors.push(error.message));
});

test.afterEach(async ({ page }, info) => {
  if (info.status !== info.expectedStatus) {
    let evidence;
    try {
      evidence = await page.evaluate(() => ({ url: location.href, readyState: document.readyState,
        edition: document.querySelector('.daily-scan')?.dataset.edition || null,
        navigationType: performance.getEntriesByType('navigation')[0]?.type || null,
        readingState: history.state?.s2sDailyReading ?? null, unrelatedState: history.state?.dailyTest ?? null,
        scrollRestoration: history.scrollRestoration, scrollX, scrollY,
        openIDs: [...document.querySelectorAll('.scan-item')].filter(row => row.querySelector('details').open).map(row => row.id) }));
    } catch (error) { evidence = { url: page.url(), diagnosticError: error.message }; }
    await info.attach('daily-history-failure.json', { body: Buffer.from(JSON.stringify(evidence)), contentType: 'application/json' });
  }
  expect(info._dailyRuntimeErrors || [], 'Unexpected Daily runtime errors').toEqual([]);
});

async function assertContent(page, edition) {
  await expect(page.locator('.daily-scan')).toHaveAttribute('data-edition', edition.date);
  const actual = await page.locator('.scan-item').evaluateAll(rows => rows.map(row => {
    const text = element => {
      const copy = element.cloneNode(true);
      copy.querySelectorAll('[aria-hidden="true"]').forEach(node => node.remove());
      return copy.textContent.trim();
    };
    const field = label => [...row.querySelectorAll('dl > div')]
      .find(pair => pair.querySelector('dt').textContent === label).querySelector('dd').textContent;
    return { id: row.id, rank: Number(row.querySelector('.scan-rank').textContent),
      kind: row.dataset.kind, topics: row.dataset.topics.split('|'),
      publisher: row.querySelector('.scan-meta > span:nth-child(2)').textContent,
      publishedOn: row.querySelector('time').getAttribute('datetime'),
      title: text(row.querySelector('h2 a')), primaryURL: row.querySelector('h2 a').getAttribute('href'),
      explanation: row.querySelector('.scan-explanation').textContent,
      focus: field('Focus'), finding: field('Finding'), caveat: field('Limits'),
      readScope: field('Read scope'), dateBasis: field('Source date').split(' · ').slice(1).join(' · '),
      sources: [...row.querySelectorAll('.scan-sources a')].map(link => ({
        url: link.getAttribute('href'), label: text(link),
      })), permalink: row.querySelector('.scan-permalink').getAttribute('href') };
  }));
  expect(actual).toEqual(edition.items.map((item, index) => ({
    id: item.id, rank: index + 1, kind: item.kind, topics: item.topics, publisher: item.publisher,
    publishedOn: item.published_on, title: item.title, primaryURL: item.sources[0].url,
    explanation: item.explanation.map(sentence => sentence.trim()).join(' '),
    focus: item.focus, finding: item.finding, caveat: item.caveat, readScope: item.read_scope,
    dateBasis: item.date_basis, sources: item.sources.map(({ url, label }) => ({ url, label })),
    permalink: `/daily/${edition.date}/#${item.id}`,
  })));
  await expect(page.locator('.scan-explanation:visible')).toHaveCount(edition.items.length);
}

async function assertSelections(page, items, total = latest.items.length) {
  expect(await page.locator('.scan-item:visible').evaluateAll(rows => rows.map(row => row.id)))
    .toEqual(items.map(item => item.id));
  await expect(page.locator('#scan-count')).toHaveText(`${items.length} of ${total} selections`);
}

function distinctiveSearch() {
  const fold = text => text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  for (const item of latest.items) {
    for (const word of item.title.match(/[\p{L}\p{N}]{7,}/gu) || []) {
      const query = fold(word).slice(0, -1);
      if (latest.items.every(other => other === item || !fold(JSON.stringify(other)).includes(query))) {
        return { item, query };
      }
    }
  }
  throw new Error('Real Daily source must supply a distinctive title prefix for search coverage');
}

test('Daily latest and bounded archives match complete committed snapshots and frozen responses', async ({ page, request }) => {
  for (const { route, edition } of contentRoutes) {
    await verifiedResponse(request, route, route.slice(1) + 'index.html');
    const snapshotPath = `daily/${edition.date}/snapshot.json`;
    expect(digest(await verifiedResponse(request, '/' + snapshotPath, snapshotPath))).toBe(sourceHashes[edition.date]);
    await page.goto(route);
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://sciencetostartup.com' + route);
    await expect(page).toHaveTitle(new RegExp(edition.date.slice(0, 4)));
    await expect(page.locator('link[rel="alternate"][type="application/rss+xml"]')).toHaveAttribute('href', '/daily/feed.xml');
    await expect(page.locator('link[rel="alternate"][type="application/feed+json"]')).toHaveAttribute('href', '/daily/feed.json');
    await expect(page.getByRole('navigation', { name: 'Follow Daily scan' }).getByRole('link', { name: 'RSS', exact: true })).toBeVisible();
    await expect(page.locator('.scan-controls')).toBeVisible();
    await assertContent(page, edition);
    expect(await page.locator('#scan-date option').evaluateAll(options => options.map(option => option.value)))
      .toEqual(editions.map(entry => entry.date).reverse());
  }
});

test('Daily feeds bind immutable editions without invented publication times', async ({ page, request }) => {
  const expected = editions.slice(-30).reverse();
  const json = JSON.parse(await verifiedResponse(request, '/daily/feed.json', 'daily/feed.json'));
  expect(json.version).toBe('https://jsonfeed.org/version/1.1');
  expect(json.items.map(item => item.id)).toEqual(expected.map(edition => `https://sciencetostartup.com/daily/${edition.date}/`));
  for (const [index, item] of json.items.entries()) {
    expect(item.url).toBe(item.id);
    expect(item.date_published).toBeUndefined();
    expect(item.date_modified).toBeUndefined();
    expect(item.content_text).toContain(expected[index].items[0].title);
    expect(item.content_text).toContain(expected[index].items[0].caveat);
    expect(item.content_text).toContain(`/daily/${expected[index].date}/#${expected[index].items[0].id}`);
  }
  const rss = (await verifiedResponse(request, '/daily/feed.xml', 'daily/feed.xml')).toString('utf8');
  const parsed = await page.evaluate(xml => {
    const document = new DOMParser().parseFromString(xml, 'application/xml');
    return { error: Boolean(document.querySelector('parsererror')),
      ids: [...document.querySelectorAll('item guid')].map(node => node.textContent),
      timestamps: document.querySelectorAll('pubDate,lastBuildDate').length };
  }, rss);
  expect(parsed).toEqual({ error: false, ids: json.items.map(item => item.id), timestamps: 0 });
});

test('Daily topic and type controls select exactly the source-backed items and update URLs', async ({ page }) => {
  await page.goto('/daily/');
  const topics = await page.locator('#scan-topic option').evaluateAll(options => options.map(option => option.value).filter(Boolean));
  expect(topics).toEqual(['RLHF', 'Data', 'Evaluation', 'Companies']);
  for (const topic of topics) {
    await page.getByLabel('Topic', { exact: true }).selectOption(topic);
    await assertSelections(page, latest.items.filter(item => item.topics.includes(topic)));
    expect(new URL(page.url()).searchParams.get('topic')).toBe(topic);
  }
  await page.getByLabel('Topic', { exact: true }).selectOption('');
  const kinds = await page.locator('#scan-kind option').evaluateAll(options => options.map(option => option.value).filter(Boolean));
  expect(kinds).toEqual(['Paper', 'Dataset', 'Release', 'Company news']);
  for (const kind of kinds) {
    await page.getByLabel('Type', { exact: true }).selectOption(kind);
    await assertSelections(page, latest.items.filter(item => item.kind === kind));
    expect(new URL(page.url()).searchParams.get('type')).toBe(kind);
  }
});

test('Daily prefix search combines filters, restores URLs, and resets empty results accessibly', async ({ page }) => {
  const { item, query } = distinctiveSearch();
  const params = new URLSearchParams({ q: query, topic: item.topics[0], type: item.kind });
  await page.goto('/daily/?' + params);
  await assertSelections(page, [item]);
  await expect(page.getByLabel('Search', { exact: true })).toHaveValue(query);
  await expect(page.getByLabel('Topic', { exact: true })).toHaveValue(item.topics[0]);
  await expect(page.getByLabel('Type', { exact: true })).toHaveValue(item.kind);
  await page.reload();
  await assertSelections(page, [item]);
  await page.getByLabel('Search', { exact: true }).fill('daily-no-such-selection-987654321');
  await assertSelections(page, []);
  await expect(page.locator('#scan-empty')).toBeVisible();
  await page.locator('#scan-empty-reset').focus();
  await page.keyboard.press('Enter');
  await assertSelections(page, latest.items);
  await expect(page.getByLabel('Search', { exact: true })).toBeFocused();
  await expect(page.locator('#scan-empty')).toBeHidden();
  await expect(page.locator('#scan-reset')).toBeHidden();
  for (const key of ['q', 'topic', 'type']) expect(new URL(page.url()).searchParams.has(key)).toBe(false);
  await page.getByLabel('Search', { exact: true }).fill(query);
  await page.locator('#scan-reset').click();
  await assertSelections(page, latest.items);
});

test('Daily date navigation retains filters and restores the open issue on Back', async ({ page }) => {
  const { item, query } = distinctiveSearch();
  const params = new URLSearchParams({ q: query, topic: item.topics[0], type: item.kind, reader: 'keep' });
  await page.goto('/daily/?' + params);
  const navigation = page.getByRole('navigation', { name: 'Snapshots', exact: true });
  const date = page.getByLabel('Snapshot date');
  const go = navigation.getByRole('button', { name: 'Go', exact: true });
  const previousLink = navigation.getByRole('link', { name: /^Previous snapshot · / });
  const nextLink = navigation.getByRole('link', { name: /^Next snapshot · / });
  const datedURL = edition => new URL(`/daily/${edition.date}/?${params}`, page.url()).href;
  const latestURL = page.url();
  await expect(previousLink).toHaveAttribute('href', datedURL(previous));
  await previousLink.click();
  await expect(page).toHaveURL(datedURL(previous));
  await expect(date).toHaveValue(previous.date);
  await expect(page.getByLabel('Search', { exact: true })).toHaveValue(query);
  await expect(page.getByLabel('Topic', { exact: true })).toHaveValue(item.topics[0]);
  await expect(page.getByLabel('Type', { exact: true })).toHaveValue(item.kind);
  await nextLink.click();
  await expect(page).toHaveURL(datedURL(latest));
  const archiveSummary = navigation.getByText('Snapshot archive', { exact: true });
  const openArticle = page.locator('.scan-item:not([hidden]) details').first();
  await openArticle.locator('summary').click();
  await archiveSummary.focus();
  await page.keyboard.press('Enter');
  const oldestLink = navigation.locator('.scan-archive a').last();
  await expect(oldestLink).toHaveAttribute('href', datedURL(oldest));
  await oldestLink.focus();
  const archiveScroll = await page.evaluate(() => scrollY);
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(datedURL(oldest));
  await page.goBack();
  await expect(page).toHaveURL(datedURL(latest));
  await expect(oldestLink).toBeFocused();
  await expect(openArticle).toHaveAttribute('open', '');
  await assertSelections(page, [item]);
  expect(await page.evaluate(wanted => Math.abs(scrollY - wanted), archiveScroll)).toBeLessThanOrEqual(2);
  await page.goForward();
  await expect(page).toHaveURL(datedURL(oldest));
  await page.goto(latestURL);
  const details = page.locator('.scan-item:not([hidden]) details').first();
  await details.locator('summary').click();
  await date.selectOption(previous.date);
  await expect(page).toHaveURL(latestURL);
  await go.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(datedURL(previous));
  await page.goBack();
  await expect(page).toHaveURL(latestURL);
  await expect(date).toHaveValue(latest.date);
  await expect(go).toBeFocused();
  await expect(details).toHaveAttribute('open', '');
  await assertSelections(page, [item]);
  await page.goForward();
  await expect(page).toHaveURL(datedURL(previous));
});

test('Daily deep links reveal filtered items and native disclosures support keyboard and history', async ({ page }) => {
  async function settledReading(link) {
    await expect(link).toBeInViewport();
    // Focus and fragment scrolling respect the site's smooth-scroll setting.
    // Save the settled reading position, rather than a frame in that animation.
    return link.evaluate(element => new Promise((resolve, reject) => {
      const started = performance.now();
      let lastY = scrollY, lastTop = element.getBoundingClientRect().top, stable = 0;
      function sample() {
        const top = element.getBoundingClientRect().top;
        stable = Math.abs(scrollY - lastY) <= 0.25 && Math.abs(top - lastTop) <= 0.25 ? stable + 1 : 0;
        lastY = scrollY; lastTop = top;
        if (stable >= 4) resolve({ y: scrollY, top,
          open: [...document.querySelectorAll('.scan-item')].filter(row => row.querySelector('details').open).map(row => row.id) });
        else if (performance.now() - started > 3000) reject(new Error('Daily reading position did not settle'));
        else requestAnimationFrame(sample);
      }
      requestAnimationFrame(sample);
    }));
  }
  async function restoredReading(link, saved) {
    await expect.poll(() => page.locator('.scan-item').evaluateAll(rows => rows
      .filter(row => row.querySelector('details').open).map(row => row.id))).toEqual(saved.open);
    await expect(link).toBeInViewport();
    await expect.poll(async () => Math.abs(await page.evaluate(() => scrollY) - saved.y)).toBeLessThanOrEqual(2);
    await expect.poll(async () => Math.abs(await link.evaluate(element => element.getBoundingClientRect().top) - saved.top)).toBeLessThanOrEqual(2);
    const settled = await settledReading(link);
    expect(Math.abs(settled.y - saved.y)).toBeLessThanOrEqual(2);
    expect(Math.abs(settled.top - saved.top)).toBeLessThanOrEqual(2);
  }
  const first = latest.items[0];
  const last = latest.items.at(-1);
  await page.goto('/daily/?q=daily-no-such-selection-987654321#' + last.id);
  const target = page.locator('.scan-item[id=' + JSON.stringify(last.id) + ']');
  await expect(target).toBeInViewport();
  await expect(target.locator('details')).toHaveAttribute('open', '');
  await assertSelections(page, latest.items);
  expect(new URL(page.url()).searchParams.has('q')).toBe(false);
  const summary = target.locator('summary');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(target.locator('details')).not.toHaveAttribute('open', '');
  await page.keyboard.press('Space');
  await expect(target.locator('details')).toHaveAttribute('open', '');
  await expect(target.locator('dd').filter({ hasText: last.caveat })).toBeVisible();
  const firstRow = page.locator('.scan-item[id=' + JSON.stringify(first.id) + ']');
  await firstRow.locator('summary').focus();
  await page.keyboard.press('Enter');
  await firstRow.locator('.scan-permalink').focus();
  await page.evaluate(() => history.replaceState({ ...history.state, dailyTest: { preserved: true } }, '', location.href));
  // This is where the reader leaves the original entry. Its URL still has
  // #last, but Back restores this reading position rather than a fresh visit.
  const returnReading = await settledReading(firstRow.locator('.scan-permalink'));
  expect(returnReading.open).toEqual([first.id, last.id]);
  const returnURL = page.url();
  await page.keyboard.press('Enter');
  const permanentFirst = page.locator('.scan-item[id=' + JSON.stringify(first.id) + ']');
  await expect(page).toHaveURL(url => url.pathname === `/daily/${latest.date}/` && url.hash === '#' + first.id);
  await expect(permanentFirst).toBeInViewport();
  await expect(permanentFirst.locator('details')).toHaveAttribute('open', '');
  expect(new URL(page.url()).hash).toBe('#' + first.id);
  const forwardReading = await settledReading(permanentFirst.locator('h2 a'));
  expect(forwardReading.open).toEqual([first.id]);
  const forwardURL = page.url();
  await page.goBack();
  await expect(page).toHaveURL(returnURL);
  expect(new URL(page.url()).hash).toBe('#' + last.id);
  await restoredReading(firstRow.locator('.scan-permalink'), returnReading);
  expect(await page.evaluate(() => history.state.dailyTest)).toEqual({ preserved: true });
  await assertSelections(page, latest.items);
  await page.goForward();
  await expect(page).toHaveURL(forwardURL);
  expect(new URL(page.url()).hash).toBe('#' + first.id);
  await restoredReading(permanentFirst.locator('h2 a'), forwardReading);
});

test('Daily controls, explanations and disclosed sources fit narrow and wide screens', async ({ page }) => {
  for (const width of [320, 390, 600, 601, 701, 768, 1440]) {
    await page.setViewportSize({ width, height: 960 });
    await page.goto('/daily/');
    await expect(page.locator('.scan-controls')).toBeVisible();
    await page.locator('.scan-item summary').first().click();
    await expect(page.locator('.scan-item .scan-explanation:visible')).toHaveCount(latest.items.length);
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth,
      document: document.documentElement.scrollWidth, body: document.body.scrollWidth,
      boxes: [...document.querySelectorAll('.scan-date-form select,.scan-date-form button,.scan-controls input,.scan-controls select,.scan-item h2,.scan-item details[open] .scan-sources')]
        .map(element => { const box = element.getBoundingClientRect(); return { left: box.left, right: box.right }; }) }));
    expect(dimensions.document, String(width)).toBeLessThanOrEqual(width + 1);
    expect(dimensions.body, String(width)).toBeLessThanOrEqual(width + 1);
    for (const box of dimensions.boxes) {
      expect(box.left, String(width)).toBeGreaterThanOrEqual(-1);
      expect(box.right, String(width)).toBeLessThanOrEqual(width + 1);
    }
  }
});

test('Daily latest and bounded archive documents have no serious or critical accessibility violations', async ({ page }, info) => {
  for (const { route, edition } of readingRoutes) {
    await page.goto(route);
    const result = await new AxeBuilder({ page }).analyze();
    await info.attach('daily-axe-' + edition.date + '.json', { body: Buffer.from(JSON.stringify({
      route, fullDocument: true, ruleExclusions: [], nodeCount: await page.locator('*').count(),
      violations: result.violations,
    })), contentType: 'application/json' });
    expect(result.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
  }
});

test.describe('Daily without JavaScript', () => {
  test.use({ javaScriptEnabled: false });
  test('complete explanations, native sources, archive navigation and JSON remain readable', async ({ page, request }) => {
    for (const { route, edition } of readingRoutes) {
      await page.goto(route + '?q=daily-no-such-selection-987654321');
      await expect(page.locator('.scan-controls')).toBeHidden();
      await expect(page.getByLabel('Snapshot date')).toBeHidden();
      await assertContent(page, edition);
      await expect(page.locator('#scan-count')).toHaveText(`${edition.items.length} selections`);
      const row = page.locator('.scan-item').last();
      await row.locator('summary').focus();
      await page.keyboard.press('Enter');
      await expect(row.locator('dd').filter({ hasText: edition.items.at(-1).read_scope })).toBeVisible();
      await row.locator('.scan-sources a').first().focus();
      await expect(row.locator('.scan-sources a').first()).toBeFocused();
      const download = page.getByRole('link', { name: 'Download this snapshot · JSON', exact: true });
      const snapshotPath = `daily/${edition.date}/snapshot.json`;
      await expect(download).toHaveAttribute('href', '/' + snapshotPath);
      expect(JSON.parse(await verifiedResponse(request, '/' + snapshotPath, snapshotPath))).toEqual(edition);
    }
    await page.goto('/daily/');
    const navigation = page.getByRole('navigation', { name: 'Snapshots', exact: true });
    await expect(navigation).toBeVisible();
    expect(await navigation.evaluate(node => Boolean(node.compareDocumentPosition(
      document.querySelector('.scan-item')) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
    await navigation.getByRole('link', { name: /^Previous snapshot · / }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(url => url.pathname === `/daily/${previous.date}/`);
    await navigation.getByRole('link', { name: /^Next snapshot · / }).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(url => url.pathname === `/daily/${latest.date}/`);
    const archive = navigation.locator(`.scan-archive a[href="/daily/${oldest.date}/"]`);
    await expect(archive).toBeVisible();
    await archive.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(url => url.pathname === `/daily/${oldest.date}/`);
    await assertContent(page, oldest);
    await page.goBack();
    await expect(page).toHaveURL(url => url.pathname === `/daily/${latest.date}/`);
    await expect(archive).toBeVisible();
    const archiveSummary = navigation.getByText('Snapshot archive', { exact: true });
    await archiveSummary.focus();
    await page.keyboard.press('Enter');
    await expect(archive).toBeHidden();
    await page.keyboard.press('Enter');
    await expect(archive).toBeVisible();
    const missing = await request.get('/daily/2026-11-15/', { headers: { 'Cache-Control': 'no-cache' } });
    expect(missing.status()).toBe(404);
  });
});
