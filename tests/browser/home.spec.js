const { test, expect, firefox } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const release = require('../../data/editorial-release.json');
const work = require('../../data/work-routes.json');
const promotionId = release.homepage.work_candidate_route_ids[0];
const promotion = work.routes.find(row => row.id === promotionId);
const approved = promotion.editorial_review.receipts.find(row => row.id === promotion.editorial_review.approved_terms_receipt_id);
const reviewed = Date.parse(approved.checked_at);
const day = 86_400_000;
const expires = reviewed + release.publication_policy.homepage_work_max_age_days * day;
const recordedProgram = '[data-recorded-program="snorkel_ai.work.expert-community"]';

test('home shows both dated sources before the phone portrait and aligns the desktop records', async ({ page }) => {
  for (const viewport of [{ width: 390, height: 844 }, { width: 1280, height: 720 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const heading = page.getByRole('heading', { level: 1, name: 'Who makes AI training data?', exact: true });
    await expect(heading).toHaveText('Who makes AI training data?');
    const company = page.locator('[data-observation="snorkel_ai.metric.major-growth_metrics-0"]');
    await expect(company).toContainText('$375M annualized revenue run rate');
    await expect(company.locator('.example-pay [aria-hidden="true"]')).toHaveText('>');
    await expect(company.locator('.example-pay .sr-only')).toHaveText('More than');
    await expect(company.locator('time')).toHaveAttribute('datetime', '2026-09-22');
    const companySource = company.getByRole('link', { name: 'Original disclosure' });
    await expect(companySource).toBeInViewport({ ratio: 1 });
    const program = page.locator(recordedProgram);
    await expect(program).toContainText('Pay set by project');
    await expect(program.locator('time')).toHaveAttribute('datetime', '2026-10-28');
    await expect(program.getByRole('link', { name: 'Read recorded terms' }))
      .toHaveAttribute('href', '/company/snorkel_ai/#snorkel_ai.work.expert-community');
    await expect(program.getByRole('link', { name: 'Official program page' })).toBeInViewport({ ratio: 1 });
    await expect(page.locator('.hero-actions a[href="/companies/"]')).toBeInViewport({ ratio: 1 });
    await expect(page.locator('.hero-actions a[href="/work/"]')).toBeInViewport({ ratio: 1 });
    await expect(page.locator('a[href="/research/data/"]')).toHaveCount(1);
    await expect(page.locator('.proof-strip p').first()).toHaveText('55 companies in the directory');

    if (viewport.width === 390) {
      const workBox = await program.boundingBox();
      const portraitBox = await page.locator('.hero-visual').boundingBox();
      expect(portraitBox.y).toBeGreaterThanOrEqual(workBox.y + workBox.height);
    } else {
      expect((await heading.boundingBox()).x).toBeCloseTo((await company.boundingBox()).x, 0);
    }
  }
});

test('both directory actions fit on one row on narrow phones', async ({ page }) => {
  for (const width of [320, 360, 375]) {
    await page.setViewportSize({ width, height: 720 });
    await page.goto('/');
    await page.evaluate(() => document.fonts.ready);
    const actions = page.locator('.hero-actions');
    const companies = actions.getByRole('link', { name: 'Browse companies', exact: true });
    const work = actions.getByRole('link', { name: 'Find paid work', exact: true });
    await expect(work).toHaveAttribute('href', '/work/');
    const first = await companies.boundingBox();
    const second = await work.boundingBox();
    expect(second.y).toBeCloseTo(first.y, 0);
    expect(second.x).toBeGreaterThanOrEqual(first.x + first.width);
    expect(second.x + second.width).toBeLessThanOrEqual(width);
    expect(Math.min(first.height, second.height)).toBeGreaterThanOrEqual(48);
  }
});

test('home promotes only approved current terms and retains all binding conditions', async ({ page }, info) => {
  const example = page.locator('#home-work-example [data-home-route]');
  for (const timestamp of [reviewed, expires - 1]) {
    await page.clock.setFixedTime(new Date(timestamp));
    await page.goto('/');
    await expect(example).toHaveAttribute('data-home-route', promotionId);
  }
  await expect(example.locator('.example-pay')).toHaveText(promotion.pay_label);
  await expect(example.locator('.example-conditions li')).toHaveText([
    'Remote · country rules vary by project', ...promotion.requirements,
    promotion.assessment, promotion.hours, promotion.duration,
  ]);
  await expect(example.locator('time')).toHaveAttribute('datetime', approved.checked_on);
  await expect(example.getByRole('link', { name: /Official program page/ })).toHaveAttribute('href', promotion.url);
  await expect(page.locator('.example-grid article')).toHaveCount(2);
  await expect(page.locator('.hero').getByRole('link', { name: 'Browse companies' })).toBeVisible();
  await expect(page.locator('.hero').getByRole('link', { name: 'Find paid work', exact: true })).toBeVisible();
  await info.attach(`home-entry-${info.project.name}.png`, {
    body: await page.screenshot({ fullPage: false, animations: 'disabled', scale: 'css' }), contentType: 'image/png',
  });
});

test('three-day expiry withdraws stale examples and preserves evergreen browse', async ({ page }) => {
  await page.clock.setFixedTime(new Date(expires));
  await page.goto('/');
  await expect(page.locator('#home-work-example [data-home-route]')).toHaveCount(0);
  await expect(page.locator('#home-work-example').getByRole('link', { name: 'Browse paid work' })).toBeVisible();
  await expect(page.locator('.example-grid article')).toHaveCount(2);
});

test('expiry moves focus from the promotion to the native Work link', async ({ page }) => {
  await page.clock.install({ time: new Date(expires - day) });
  await page.clock.pauseAt(new Date(expires - 1_000));
  await page.goto('/');
  const slot = page.locator('#home-work-example');
  const focused = slot.getByRole('link', { name: /original listing|official program page/i });
  await focused.focus();
  await expect(focused).toBeFocused();
  await page.clock.fastForward(60_000);
  const fallback = slot.getByRole('link', { name: 'Browse paid work' });
  await expect(fallback).toBeFocused();
  await expect(fallback).toBeInViewport();
  await expect(page.locator(recordedProgram)).toBeVisible();
});

test('without JavaScript the homepage offers its menu and native browse links', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto('/');
  await expect(page.locator('#home-work-example [data-home-route]')).toHaveCount(0);
  await expect(page.locator('#home-work-example').getByRole('link', { name: 'Browse paid work' })).toHaveAttribute('href', '/work/');
  await expect(page.locator('.hero').getByRole('link', { name: 'Browse companies' })).toHaveAttribute('href', '/companies/');
  await expect(page.locator('.example-grid article')).toHaveCount(2);
  await page.locator('.home-menu summary').press('Enter');
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Daily scan' })).toBeVisible();
  await page.locator('.home-menu summary').press('Enter');
  await page.locator('#home-search-open').press('Enter');
  await expect(page).toHaveURL(/#browse-guide$/);
  await expect(page.getByRole('region', { name: 'Browse the guide' }).getByRole('link', { name: 'Browse companies' }))
    .toHaveAttribute('href', '/companies/');
  await context.close();
});

test('homepage Search loads only its small component and index when invoked', async ({ page }) => {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  await page.goto('/');
  await expect(page.locator('#home-search')).not.toBeVisible();
  expect(requests.some(url => /home-search\.js|presentation\/search\.|\/js\/(app|data)\.|research\.json/.test(url))).toBe(false);
  await page.locator('#home-search-open').click();
  await expect(page.getByRole('dialog', { name: 'Search the guide' })).toBeVisible();
  await expect(page.locator('#home-search-message')).not.toContainText('Loading');
  expect(requests.some(url => /home-search\.js/.test(url))).toBe(true);
  expect(requests.some(url => /presentation\/search\./.test(url))).toBe(true);
  expect(requests.some(url => /\/js\/(app|data)\.|presentation\/(archive|company-|summary)\.|research\.json/.test(url))).toBe(false);
  await page.locator('#home-search-input').fill('C++');
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations.filter(row => ['serious', 'critical'].includes(row.impact))).toEqual([]);
  const action = page.locator('#home-search-results a').filter({ hasText: 'Find paid work matching' });
  await expect(action).toHaveAttribute('href', '/work/?q=C%2B%2B');
  await page.locator('#home-search-close').click();
  await expect(page.locator('#home-search-open')).toBeFocused();
});

test('keyboard paging keeps its focused button and outline inside the short dialog at a 28px Firefox minimum', async ({ browserName, baseURL }) => {
  test.skip(browserName !== 'firefox', 'Uses a Firefox text preference');
  const browser = await firefox.launch({ firefoxUserPrefs: { 'font.minimum-size.x-western': 28 } });
  try {
    const page = await browser.newPage({ baseURL });
    const opener = page.getByRole('link', { name: 'Search the guide' });
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const more = dialog.getByRole('button', { name: 'Show 7 more', exact: true });
    const outlineFits = button => {
      const { top, bottom } = button.getBoundingClientRect();
      const dialog = button.closest('dialog');
      const dialogBox = dialog.getBoundingClientRect();
      const { outlineStyle, outlineWidth, outlineOffset } = getComputedStyle(button);
      const outset = parseFloat(outlineWidth) + parseFloat(outlineOffset);
      const innerTop = dialogBox.top + dialog.clientTop;
      return outlineStyle === 'solid' && top - outset >= Math.max(0, innerTop)
        && bottom + outset <= Math.min(innerHeight, innerTop + dialog.clientHeight);
    };

    for (const height of [360, 373]) {
      await page.setViewportSize({ width: 621, height });
      await page.goto('/');
      await opener.press('Enter');
      await dialog.getByRole('combobox').fill('feedback');
      await expect(more).toBeVisible();
      await page.keyboard.press('Tab');
      await expect(dialog.getByRole('button', { name: 'Close search' })).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(more).toBeFocused();
      await expect.poll(() => more.evaluate(outlineFits)).toBe(true);
      await page.keyboard.press('Enter');
      await expect(dialog.getByRole('option')).toHaveCount(15);
      await expect(more).toBeFocused();
      await expect.poll(() => more.evaluate(outlineFits)).toBe(true);
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();
      await expect(opener).toBeFocused();
    }
  } finally {
    await browser.close();
  }
});

test('failed homepage search keeps usable browse actions and a retry', async ({ page }) => {
  await page.route('**/presentation/search.*.json', route => route.abort());
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('.site-search-fallback').getByRole('link', { name: 'Browse companies' })).toHaveAttribute('href', '/companies/');
  await page.locator('#home-search-input').fill('RLHF  jobs');
  await expect(page.getByRole('link', { name: 'Search paid work for this query' })).toHaveAttribute('href', '/work/?q=RLHF++jobs');
  await page.locator('#home-search-close').click();
  await page.unroute('**/presentation/search.*.json');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).not.toContainText('could not load');
});

test('a refused Search component retains the query and retries with a new request', async ({ page }) => {
  await page.route('**/home-search.js', route => route.abort());
  await page.goto('/');
  await page.keyboard.press('Control+k');
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await page.locator('#home-search-input').fill('RLHF  jobs');
  const workRecovery = page.getByRole('link', { name: 'Search paid work for this query' });
  await expect(workRecovery).toHaveCount(1);
  await expect(workRecovery).toHaveAttribute('href', '/work/?q=RLHF++jobs');
  const retried = page.waitForResponse(response => /home-search\.js\?retry=1$/.test(response.url()));
  await page.locator('[data-home-component-retry]').click();
  expect((await retried).ok()).toBe(true);
  await expect(page.locator('#home-search-results')).toBeVisible();
});

test('homepage search times out a stalled index and retries without reporting empty results', async ({ page }) => {
  await page.clock.install({ time: new Date(reviewed + day) });
  const { promise: indexRequest, resolve: holdRequest } = Promise.withResolvers();
  await page.route('**/presentation/search.*.json', route => holdRequest(route));
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Loading');
  const stalled = await indexRequest;
  await page.clock.fastForward(15_001);
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-message')).not.toContainText('No recorded company matches');
  await expect(page.locator('#home-search-work-recovery')).toBeVisible();
  await stalled.abort().catch(() => {});
  await page.unroute('**/presentation/search.*.json');
  await page.locator('[data-home-search-retry]').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
});

test('homepage search rejects stale index bytes and offers a usable retry', async ({ page }) => {
  await page.route('**/presentation/search.*.json', async route => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({ response, json: { ...data, buildId: 'stale-release' } });
  });
  await page.goto('/');
  await page.locator('#home-search-open').click();
  await expect(page.locator('#home-search-message')).toContainText('Search could not load');
  await expect(page.locator('#home-search-results')).not.toBeVisible();
  await page.unroute('**/presentation/search.*.json');
  await page.locator('[data-home-search-retry]').click();
  await expect(page.locator('#home-search-results')).toBeVisible();
});
