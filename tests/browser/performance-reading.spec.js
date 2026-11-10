const { test, expect } = require('@playwright/test');
const { evidenceURL, token } = require('./research-ledger');
const selector = id => '[id=' + JSON.stringify(id) + ']';

// Full-ledger DOM trace snapshots obscure native navigation timing; screenshots,
// source and network traces remain available when a functional check fails.
test.use({ trace: { mode: 'retain-on-failure', snapshots: false, screenshots: true, sources: true } });

// These checks exercise browser-native revelation of the complete HTML ledger.
// They also run with scripting disabled and with each configured browser engine.
test.describe('native ledger rendering', () => {
  test.use({ javaScriptEnabled: false });

  for (const kind of ['assertion', 'source']) {
    test(`all ${kind} records remain complete in their no-JavaScript ledger parts`, async ({ page, request }) => {
      const response = await request.get('/research/exports/research-graph.json');
      expect(response.ok()).toBeTruthy();
      const graph = await response.json();
      await page.goto('/research/data/');
      await expect(page.locator('.r-assertion,.r-source')).toHaveCount(0);
      const links = page.locator('section[aria-labelledby="' + (kind === 'source' ? 'sources' : 'assertions') + '"] .r-ledger-parts a');
      await expect(links).toHaveCount(16);
      const paths = await links.evaluateAll(links => links.map(link => link.getAttribute('href')));
      expect(paths).toEqual([... '0123456789abcdef'].map(bucket => '/research/data/' + (kind === 'source' ? 'sources' : 'assertions') + '/' + bucket + '/'));
      const observed = [];
      const metadataOnly = [];
      for (const path of paths) {
        await page.goto(path);
        await expect(page.locator('h1')).toContainText(kind === 'source' ? 'Source ledger' : 'Assertion ledger');
        await expect(page.locator('script:not([type="application/ld+json"])')).toHaveCount(0);
        if (kind === 'assertion') {
          await expect(page.locator('.r-assertion:not([data-status="approved"]):not([data-status="historical"]) .r-assertion-text')).toHaveCount(0);
          observed.push(...await page.locator('.r-assertion[data-status="approved"],.r-assertion[data-status="historical"]').evaluateAll(rows => rows.map(row => row.id)));
          metadataOnly.push(...await page.locator('.r-assertion:not([data-status="approved"]):not([data-status="historical"])').evaluateAll(rows => rows.map(row => row.id)));
        } else {
          observed.push(...await page.locator('.r-source').evaluateAll(rows => rows.map(row => row.id)));
        }
      }
      const expected = (kind === 'source' ? graph.sources : graph.assertions.filter(row => ['approved', 'historical'].includes(row.status)))
        .map(row => kind + '-' + row.id).sort();
      expect(observed.sort()).toEqual(expected);
      expect(new Set(observed).size).toBe(observed.length);
      if (kind === 'assertion') {
        const correctionResponse = await request.get('/publication/corrections.json');
        expect(correctionResponse.ok()).toBeTruthy();
        const correctionData = await correctionResponse.json();
        expect(Array.isArray(correctionData.corrections), 'The correction registry must retain its complete record array').toBe(true);
        for (const row of correctionData.corrections) {
          const retained = 'assertion-' + row.claim_id;
          if (!expected.includes(retained)) expect(metadataOnly, 'Retained correction identifier ' + row.claim_id).toContain(retained);
        }
      }
    });
  }

  test('legacy fragments lead natively to complete source records, find, keyboard focus and print', async ({ page, request, browserName }) => {
    const response = await request.get('/research/exports/research-graph.json');
    expect(response.ok()).toBeTruthy();
    const graph = await response.json();
    const sourceRow = [...graph.sources].sort((a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0).at(-1);
    const id = 'source-' + sourceRow.id;
    const destination = evidenceURL('source', sourceRow.id);
    await page.goto('/research/data/#' + token(id));
    const alias = page.locator(selector(id));
    await expect(alias).toBeVisible();
    const nativeLink = alias;
    await expect(nativeLink).toHaveRole('link');
    await expect(nativeLink).toHaveAccessibleName('Open source record: ' + sourceRow.id);
    await expect(nativeLink).toHaveAttribute('href', destination);
    await nativeLink.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(destination.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
    const last = page.locator('article.r-source' + selector(id));
    const title = (await last.locator('h3 a').textContent()).trim();
    await expect(last.getByRole('link', { name: title, exact: true })).toBeAttached();
    await expect(last.locator('h3')).toBeInViewport();
    await expect(last.locator('dt').filter({ hasText: /^Locator$/ })).toBeVisible();
    await expect(last.locator('h3 a')).toHaveAttribute('href', /^https?:\/\//);
    await page.goBack();
    await expect(alias).toBeVisible();
    await page.goForward();
    await expect(last.locator('h3')).toBeInViewport();

    const path = destination.split('#')[0];
    await page.goto(path);
    const found = await page.evaluate(text => {
      if (typeof window.find !== 'function') return null;
      return window.find(text, false, true);
    }, title);
    if (found !== null) {
      expect(found).toBe(true);
      await expect(last.locator('h3')).toBeInViewport();
    }
    await page.goto(path);
    await last.locator('h3 a').focus();
    await expect(last.locator('h3 a')).toBeFocused();
    await expect(last.locator('h3')).toBeInViewport();
    await page.keyboard.press(browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab');
    expect(await last.evaluate(node => node.contains(document.activeElement))).toBe(true);

    await page.emulateMedia({ media: 'print' });
    const assertionRow = graph.assertions.filter(row => row.status === 'approved').at(-1);
    for (const [printPath, recordSelector] of [[path, '.r-source'], [evidenceURL('assertion', assertionRow.id).split('#')[0], '.r-assertion']]) {
      await page.goto(printPath);
      const styles = await page.locator(recordSelector).evaluateAll(nodes => nodes.map(node => ({
        visibility: getComputedStyle(node).contentVisibility, containment: getComputedStyle(node).contain })));
      expect(styles.length).toBeGreaterThan(0);
      for (const style of styles) expect(style).toEqual({ visibility: 'visible', containment: 'none' });
    }
  });

  test('late assertion citations reveal their source and preserve native history', async ({ page, request }) => {
    const response = await request.get('/research/exports/research-graph.json');
    expect(response.ok()).toBeTruthy();
    const graph = await response.json();
    const row = graph.assertions.filter(row => row.status === 'approved').at(-1);
    const id = 'assertion-' + row.id;
    await page.goto('/research/data/#' + token(id));
    const alias = page.locator(selector(id));
    await expect(alias).toHaveRole('link');
    await expect(alias).toHaveAttribute('href', evidenceURL('assertion', row.id));
    await alias.focus();
    await page.keyboard.press('Enter');
    const assertion = page.locator('article.r-assertion' + selector(id));
    await expect(assertion.locator('.r-assertion-text')).toBeInViewport();
    const citation = assertion.locator('a[href*="#source-"]').first();
    const href = await citation.getAttribute('href');
    await citation.focus();
    await page.keyboard.press('Enter');
    const source = page.locator('[id=' + JSON.stringify(decodeURIComponent(href.split('#')[1])) + ']');
    await expect(source.locator('h3')).toBeInViewport();
    await page.goBack();
    await expect(page).toHaveURL(new RegExp('#' + id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
    await expect(citation).toBeInViewport();
    await page.goForward();
    await expect(source.locator('h3')).toBeInViewport();
  });
});

test('a direct profile initializes other view controls when their route opens', async ({ page }) => {
  await page.goto('/explore/#company/mercor/work');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.getByRole('tab', { name: 'Paid work', exact: true })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#category option')).toHaveCount(1);
  await expect(page.locator('#work-safety')).toBeEmpty();
  await page.getByRole('tab', { name: 'Paid work', exact: true }).focus();
  await page.keyboard.press('Home');
  await expect(page.getByRole('tab', { name: 'Business', exact: true })).toBeFocused();
  await expect(page.locator('#profile-products')).toBeVisible();
  await page.locator('.topbar a[data-nav="companies"]').click();
  await expect(page.locator('#category option').nth(1)).toBeAttached();
  await expect(page.locator('[data-company-card]')).toHaveCount(39);
  await page.locator('.topbar a[data-nav="work"]').click();
  await expect(page.locator('#work-safety')).toContainText('Before you apply');
  await expect(page.locator('#work-group option').nth(1)).toBeAttached();
  await expect(page.locator('#work-cards')).toContainText('Named listings');
  await page.goBack();
  await expect(page.locator('[data-company-card]')).toHaveCount(39);
});
