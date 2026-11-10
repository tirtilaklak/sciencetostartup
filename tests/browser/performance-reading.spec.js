const { test, expect } = require('@playwright/test');

// Full-ledger DOM trace snapshots obscure native navigation timing; screenshots,
// source and network traces remain available when a functional check fails.
test.use({ trace: { mode: 'retain-on-failure', snapshots: false, screenshots: true, sources: true } });

// These checks exercise browser-native revelation of the complete HTML ledger.
// They also run with scripting disabled and with each configured browser engine.
test.describe('native ledger rendering', () => {
  test.use({ javaScriptEnabled: false });

  test('all records remain accessible through fragments, find, keyboard focus and print', async ({ page, request, browserName }) => {
    const response = await request.get('/research/exports/research-graph.json');
    expect(response.ok()).toBeTruthy();
    const graph = await response.json();
    await page.goto('/research/data/');
    await expect(page.locator('.r-assertion[data-status="approved"],.r-assertion[data-status="historical"]')).toHaveCount(graph.assertions.filter(row => ['approved', 'historical'].includes(row.status)).length);
    // Quarantined identifiers remain correction-only placeholders. They are
    // outside the approved export and must never be sampled as findings.
    await expect(page.locator('.r-assertion[data-status="candidate"] .r-assertion-text')).toHaveCount(0);
    await expect(page.locator('.r-source')).toHaveCount(graph.sources.length);
    const last = page.locator('.r-source').last();
    const id = await last.getAttribute('id');
    const title = (await last.locator('h3 a').textContent()).trim();
    // The role lookup includes offscreen content in the accessibility tree.
    await expect(last.getByRole('link', { name: title, exact: true })).toBeAttached();
    await page.goto('/research/data/#' + id);
    await expect(last.locator('h3')).toBeInViewport();
    await expect(last.locator('dt').filter({ hasText: /^Locator$/ })).toBeVisible();
    await expect(last.locator('h3 a')).toHaveAttribute('href', /^https?:\/\//);

    await page.goto('/research/data/');
    // window.find invokes the browser's native document search, including skipped records.
    const found = await page.evaluate(text => {
      if (typeof window.find !== 'function') return null;
      return window.find(text, false, true);
    }, title);
    if (found !== null) {
      expect(found).toBe(true);
      await expect(last.locator('h3')).toBeInViewport();
    }
    await page.goto('/research/data/');
    await last.locator('h3 a').focus();
    await expect(last.locator('h3 a')).toBeFocused();
    await expect(last.locator('h3')).toBeInViewport();
    // Native Tab navigation reaches the next source action inside the revealed record.
    await page.keyboard.press(browserName === 'webkit' && process.platform === 'darwin' ? 'Alt+Tab' : 'Tab');
    expect(await last.evaluate(node => node.contains(document.activeElement))).toBe(true);

    await page.emulateMedia({ media: 'print' });
    for (const selector of ['.r-assertion', '.r-source']) {
      expect(await page.locator(selector).last().evaluate(node => ({
        visibility: getComputedStyle(node).contentVisibility,
        containment: getComputedStyle(node).contain,
      }))).toEqual({ visibility: 'visible', containment: 'none' });
    }
  });

  test('late assertion citations reveal their source and preserve native history', async ({ page }) => {
    await page.goto('/research/data/');
    const assertion = page.locator('.r-assertion[data-status="approved"]').last();
    const id = await assertion.getAttribute('id');
    await page.goto('/research/data/#' + id);
    await expect(assertion.locator('.r-assertion-text')).toBeInViewport();
    const citation = assertion.locator('a[href*="#source-"]').first();
    const href = await citation.getAttribute('href');
    await citation.focus();
    await page.keyboard.press('Enter');
    const source = page.locator('[id=' + JSON.stringify(href.split('#')[1]) + ']');
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
