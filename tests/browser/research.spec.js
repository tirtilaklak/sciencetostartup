const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const reportPath = '/research/state-of-ai-data-labs/';
const publicPages = ['/', '/research/', reportPath, '/research/data/', '/review/', '/company/scale_ai/'];

test.beforeEach(async ({ page, request }, info) => {
  const response = await request.get('/manifest.json');
  expect(response.ok()).toBeTruthy();
  const manifest = await response.json();
  await info.attach('artifact-identity.json', {
    body: Buffer.from(JSON.stringify({ buildId: manifest.build_id, editorialReleaseId: manifest.editorial_release_id, datasetVersion: manifest.dataset_version })),
    contentType: 'application/json',
  });
  const runtimeErrors = [];
  page.on('pageerror', error => runtimeErrors.push(error.message));
  info._researchRuntimeErrors = runtimeErrors;
});

test.afterEach(async ({}, info) => {
  expect(info._researchRuntimeErrors || [], 'Unexpected browser runtime errors').toEqual([]);
});

test.describe('research without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('hub opens a complete twelve-chapter report with working chapter links', async ({ page }) => {
    await page.goto('/research/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('human work');
    await expect(page.locator('.r-chapter-list a')).toHaveCount(12);
    await page.getByRole('link', { name: 'Read the research →', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(reportPath + '$'));
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
    await expect(page.locator('.r-report-body > .r-chapter:not(#cite)')).toHaveCount(12);
    const chapters = await page.locator('.r-toc ol a').evaluateAll(links => links.map(link => ({ href: link.getAttribute('href'), title: link.textContent })));
    expect(chapters).toHaveLength(12);
    for (const chapter of chapters) {
      const section = page.locator('[id=' + JSON.stringify(chapter.href.slice(1)) + ']');
      await expect(section.getByRole('heading', { level: 2 })).toHaveText(chapter.title);
      expect(await section.locator('.r-paragraph p').count(), chapter.title).toBeGreaterThan(0);
    }
    await page.locator('.r-toc ol a').last().click();
    await expect(page).toHaveURL(/#methods-and-appendices$/);
    await expect(page.locator('#methods-and-appendices > h2')).toBeInViewport();
  });

  test('report evidence opens the assertion and its source ledger entry', async ({ page }) => {
    await page.goto(reportPath);
    const evidence = page.locator('.r-paragraph-citations a').first();
    const assertionHref = await evidence.getAttribute('href');
    expect(assertionHref).toMatch(/^\/research\/data\/#assertion-/);
    await evidence.click();
    const assertion = page.locator('[id=' + JSON.stringify(assertionHref.split('#')[1]) + ']');
    await expect(assertion).toBeVisible();
    const sourceLink = assertion.locator('a[href*="#source-"]').first();
    const sourceHref = await sourceLink.getAttribute('href');
    await sourceLink.click();
    const source = page.locator('[id=' + JSON.stringify(sourceHref.split('#')[1]) + ']');
    await expect(source).toBeVisible();
    await expect(source.locator('h3 a')).toHaveAttribute('href', /^https:\/\//);
    for (const label of ['Publisher', 'Published', 'Captured', 'Version', 'Locator']) {
      await expect(source.locator('dt').filter({ hasText: new RegExp('^' + label + '$') })).toBeVisible();
    }
    await expect(source).toContainText('Assertion-specific review is recorded separately');
  });

  test('data page exposes working graph exports and citation downloads', async ({ page, request }) => {
    await page.goto('/research/data/');
    const exports = [
      '/research/exports/research-graph.json',
      '/research/exports/research-graph.sqlite',
      '/research/exports/research-exports-manifest.json',
    ];
    for (const href of exports) {
      const link = page.locator('a[href=' + JSON.stringify(href) + ']');
      await expect(link).toBeVisible();
      const response = await request.get(await link.getAttribute('href'));
      expect(response.ok(), href).toBeTruthy();
      const body = await response.body();
      expect(body.length, href).toBeGreaterThan(100);
      if (href.endsWith('.sqlite')) expect(body.subarray(0, 16).toString()).toBe('SQLite format 3\u0000');
      else expect(() => JSON.parse(body.toString()), href).not.toThrow();
    }
    const formats = [
      ['BibTeX', '/publication/citation.bib', /@\w+\s*\{/],
      ['RIS', '/publication/citation.ris', /^TY\s+-/m],
      ['CSL JSON', '/publication/citation.csl.json', /"title"\s*:/],
      ['CITATION.cff', '/publication/CITATION.cff', /["']?cff-version["']?\s*:/],
    ];
    for (const [name, href, format] of formats) {
      await expect(page.locator('#citation').getByRole('link', { name, exact: true })).toHaveAttribute('href', href);
      const response = await request.get(href);
      expect(response.ok(), name).toBeTruthy();
      const content = await response.text();
      expect(content, name).toMatch(format);
      expect(content, name).toContain('State of AI Data Labs and Human Feedback');
    }
    await expect(page.locator('#sources')).toBeVisible();
    expect(await page.locator('.r-source').count()).toBeGreaterThan(0);
  });
});

test('home search finds human feedback research and opens its native report', async ({ page }) => {
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
  await page.locator('#home-search-input').fill('human feedback');
  const result = page.locator('#home-search-results a[href=' + JSON.stringify(reportPath) + ']');
  await expect(result).toContainText('State of AI Data Labs and Human Feedback');
  await result.click();
  await expect(page).toHaveURL(new RegExp(reportPath + '$'));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
});

test('home search preserves the native static company destination', async ({ page }) => {
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
  await page.locator('#home-search-input').fill('Scale AI');
  const company = page.locator('#home-search-results a[href="/company/scale_ai/"]');
  await expect(company).toContainText('Scale AI');
  await company.click();
  await expect(page).toHaveURL(/\/company\/scale_ai\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Scale AI');
});

test('global search offers a native research link and respects opening it in a new tab', async ({ page, context }) => {
  await page.goto('/explore/#companies');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await page.locator('#site-search-open').click();
  await page.locator('#site-search-input').fill('human feedback');
  const result = page.locator('#site-search-results a[href=' + JSON.stringify(reportPath) + ']');
  await expect(result).toHaveAttribute('role', 'option');
  await expect(result).toContainText('State of AI Data Labs and Human Feedback');
  const opened = context.waitForEvent('page');
  await result.click({ modifiers: ['ControlOrMeta'] });
  const tab = await opened;
  await tab.waitForLoadState();
  await expect(tab).toHaveURL(new RegExp(reportPath + '$'));
  await expect(tab.getByRole('heading', { level: 1 })).toHaveText('State of AI Data Labs and Human Feedback');
  await expect(page).toHaveURL(/\/explore\/#companies$/);
  await expect(page.locator('#site-search')).toBeVisible();
  await tab.close();
  await result.click();
  await expect(page).toHaveURL(new RegExp(reportPath + '$'));
});

test('public pages retain keyboard skip navigation into the main content', async ({ page, browserName }) => {
  // Safari's default keyboard setting visits links with Option-Tab.
  const nextLink = browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab';
  for (const path of publicPages) {
    await page.goto(path);
    await page.keyboard.press(nextLink);
    const skip = page.getByRole('link', { name: 'Skip to content', exact: true });
    await expect(skip, path).toBeFocused();
    await expect(skip, path).toBeInViewport();
    await page.keyboard.press('Enter');
    await expect(page, path).toHaveURL(/#main$/);
    await page.keyboard.press(nextLink);
    expect(await page.evaluate(() => Boolean(document.activeElement.closest('main'))), path + ' skip must move subsequent keyboard focus into main').toBe(true);
  }
});

test('home search supports arrow selection and restores keyboard focus when closed', async ({ page }) => {
  await page.goto('/');
  const opener = page.locator('#home-search-open');
  await opener.focus();
  await page.keyboard.press('Enter');
  const input = page.locator('#home-search-input');
  await expect(input).toBeFocused();
  await expect(page.locator('#home-search-results')).toBeVisible();
  await input.fill('human feedback');
  await input.press('ArrowDown');
  const selected = page.locator('#home-search-results [aria-selected="true"]');
  await expect(selected).toHaveCount(1);
  await expect(input).toHaveAttribute('aria-activedescendant', await selected.getAttribute('id'));
  await page.keyboard.press('Escape');
  await expect(page.locator('#home-search')).not.toBeVisible();
  await expect(opener).toBeFocused();
});

test('at 320 pixels the public header, navigation and page fit without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  for (const path of publicPages) {
    await page.goto(path);
    const header = page.locator('body > header.site-header');
    await expect(header).toBeVisible();
    const nav = header.getByRole('navigation', { name: 'Main', exact: true });
    for (const name of ['Research', 'Companies', 'Paid work', 'About']) {
      const link = nav.getByRole('link', { name, exact: true });
      await expect(link, path).toBeVisible();
      const box = await link.boundingBox();
      expect(box.x, path + ' ' + name).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width, path + ' ' + name).toBeLessThanOrEqual(320.5);
      expect(box.height, path + ' ' + name).toBeGreaterThanOrEqual(43.5);
    }
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
    expect(dimensions.document, path).toBeLessThanOrEqual(dimensions.viewport + 1);
    expect(dimensions.body, path).toBeLessThanOrEqual(dimensions.viewport + 1);
  }
});

for (const path of publicPages) {
  test('no serious or critical accessibility violations on ' + path, async ({ page }) => {
    await page.goto(path);
    const result = await new AxeBuilder({ page }).analyze();
    expect(result.violations.filter(violation => ['serious', 'critical'].includes(violation.impact))).toEqual([]);
  });
}
