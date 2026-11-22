const { chromium, firefox, test, expect } = require('@playwright/test');

const roleId = 'afterquery.work.world-models';
const work = '/work/?pay=hourly&sort=hourly&reader=%20A%2Bb%20';
const profile = '/company/afterquery/#' + roleId;

function controls(page) {
  const card = page.locator(`[data-work-route="${roleId}"]`);
  return {
    opener: card.getByRole('link', { name: 'AfterQuery · World Models Machine Learning Expert', exact: true }),
    application: card.locator('.work-listing-action a'),
    terms: card.locator('details.work-terms'),
  };
}

async function observeHistory(page, cold) {
  await page.addInitScript(cold => {
    addEventListener('pageshow', event => { window.workReturnPersisted = event.persisted; });
    if (cold && location.pathname === '/work/') addEventListener('unload', () => {});
  }, cold);
}

async function matchingRecords(page) {
  await expect(page.locator('[data-work-filters] [name=pay]')).toHaveValue('hourly');
  await expect(page.locator('[data-work-filters] [name=sort]')).toHaveValue('hourly');
  return page.locator('[data-work-route]:visible').evaluateAll(cards => cards.map(card => card.dataset.workRoute));
}

async function activateProfile(page) {
  await expect(page.locator('[data-work-compare]')).toBeVisible();
  const savedURL = page.url();
  const ids = await matchingRecords(page);
  expect(ids).toHaveLength(17);
  expect(ids[0]).toBe(roleId);
  const { opener, application, terms } = controls(page);
  await terms.locator('summary').press('Enter');
  await expect(terms).toHaveJSProperty('open', true);
  await expect(terms.locator('a[href="https://experts.afterquery.com/apply/world-models-ml-experts"]')).toBeVisible();
  await page.keyboard.press('Shift+Tab');
  await expect(application).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(opener).toBeFocused();
  const position = await opener.evaluate(link => ({ scroll: scrollY, top: link.getBoundingClientRect().top }));
  await opener.press('Enter');
  await expect(page).toHaveURL(profile);
  await expect(page.locator(':target')).toHaveAttribute('id', roleId);
  return { savedURL, ids, position };
}

async function expectProfileReturn(page, departure, cached) {
  const { opener, application, terms } = controls(page);
  await expect(page).toHaveURL(departure.savedURL);
  await expect(opener).toBeFocused();
  await expect(terms).toHaveJSProperty('open', true);
  await expect.poll(() => page.evaluate(() => window.workReturnPersisted)).toBe(cached);
  if (!cached) expect(await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type)).toBe('back_forward');
  expect(await matchingRecords(page)).toEqual(departure.ids);
  await expect(opener).toBeInViewport({ ratio: 1 });
  await expect.poll(() => opener.evaluate((link, previous) => Math.max(
    Math.abs(scrollY - previous.scroll), Math.abs(link.getBoundingClientRect().top - previous.top)
  ), departure.position)).toBeLessThan(3);
  await page.keyboard.press('Tab');
  await expect(application).toBeFocused();
}

async function expectNormalWorkLanding(page, departure) {
  await expect(page).toHaveURL(departure.savedURL);
  await expect(page.locator('[data-work-compare]')).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.workReturnPersisted)).toBe(false);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve)))));
  await expect(page.locator('body')).toBeFocused();
  await expect(controls(page).terms).toHaveJSProperty('open', false);
  expect(await matchingRecords(page)).toEqual(departure.ids);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
}

test.describe('Work company-profile handoff', () => {
  test.use({ viewport: { width: 1024, height: 600 } });
  test.skip(({ isMobile }) => isMobile, 'Use the audited desktop keyboard layout');

  for (const hash of ['', '#' + roleId]) {
    test(`cold Back restores the company link${hash ? ' on a bookmarked Work entry' : ''}`, async ({ page }) => {
      await observeHistory(page, true);
      await page.goto(work + hash);
      await expect(page).toHaveURL(work + hash);
      const departure = await activateProfile(page);
      await page.goBack({ waitUntil: 'commit' });
      await expectProfileReturn(page, departure, false);
    });
  }

  test('a duplicate profile address and direct Work visits use normal focus', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Exercise an adjacent direct visit in the audited browser');
    await observeHistory(page, true);
    await page.goto(work);
    const departure = await activateProfile(page);
    await page.goBack({ waitUntil: 'commit' });
    await expect(controls(page).opener).toBeFocused();
    await page.goForward({ waitUntil: 'commit' });
    await expect(page).toHaveURL(profile);
    await page.goBack({ waitUntil: 'commit' });
    await expect(controls(page).opener).toBeFocused();
    await expect(controls(page).terms).toHaveJSProperty('open', true);

    await page.goto(profile);
    await page.goBack({ waitUntil: 'commit' });
    await expectNormalWorkLanding(page, departure);
    await page.goForward({ waitUntil: 'commit' });
    await expect(page).toHaveURL(profile);
    await page.goto(work);
    await expectNormalWorkLanding(page, departure);
  });

  test('cached Back keeps browser-managed Terms, focus and scroll', async ({ baseURL, browserName }) => {
    test.skip(browserName !== 'chromium', 'Enable the audited browser’s back-forward cache');
    const browser = await chromium.launch({ channel: 'chromium', ignoreDefaultArgs: ['--disable-back-forward-cache'] });
    try {
      const page = await browser.newPage({ baseURL, viewport: { width: 1024, height: 600 } });
      await observeHistory(page, false);
      await page.goto(work);
      const departure = await activateProfile(page);
      await page.goBack({ waitUntil: 'commit' });
      await expectProfileReturn(page, departure, true);
    } finally {
      await browser.close();
    }
  });
});

const legacy = test.extend({
  browser: [async ({}, use) => {
    const browser = await firefox.launch({ firefoxUserPrefs: {
      'dom.navigation.webidl.enabled': false,
      'browser.sessionhistory.max_total_viewers': 0,
    } });
    try {
      await use(browser);
    } finally {
      await browser.close();
    }
  }, { scope: 'worker' }],
});

legacy.describe('Work profile Back with legacy History', () => {
  legacy.skip(({ browserName }) => browserName !== 'firefox', 'Use Firefox with the Navigation API disabled');
  legacy.use({ viewport: { width: 1024, height: 600 } });

  legacy('the oldest Work entry restores its exact profile opener', async ({ page }) => {
    await observeHistory(page, true);
    await page.goto(work);
    expect(await page.evaluate(() => [Boolean(window.navigation), history.length])).toEqual([false, 1]);
    const departure = await activateProfile(page);
    await page.goBack({ waitUntil: 'commit' });
    await expect(controls(page).opener).toBeFocused();
    await page.goForward({ waitUntil: 'commit' });
    await expect(page).toHaveURL(profile);
    await page.goBack({ waitUntil: 'commit' });
    await expectProfileReturn(page, departure, false);
  });

  legacy('a Work entry with earlier history keeps normal focus on ambiguous traversals', async ({ page }) => {
    await observeHistory(page, true);
    const prior = '/research/editions/2026-11-12/';
    await page.goto(prior);
    await page.goto(work);
    const departure = await activateProfile(page);
    await Promise.all([page.waitForURL(prior), page.evaluate(() => setTimeout(() => history.go(-2), 0))]);
    await page.goForward({ waitUntil: 'commit' });
    await expectNormalWorkLanding(page, departure);
    await activateProfile(page);
    await page.goBack({ waitUntil: 'commit' });
    await expectNormalWorkLanding(page, departure);
  });
});
