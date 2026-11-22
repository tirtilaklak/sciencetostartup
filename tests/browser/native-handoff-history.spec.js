const { chromium, firefox, test, expect } = require('@playwright/test');

const directoryGroup = 'expert-data-evaluation';
const compareResult = '[data-company=mercor] .directory-compare';
const firstMercorSource = '[data-company=mercor] .selected-evidence a[href*="felicis.com"]';

async function trackDocument(page, cold) {
  await page.addInitScript(cold => {
    addEventListener('pageshow', event => { window.nativeHandoffCached = event.persisted; });
    if (cold && ['/companies/', '/work/'].includes(location.pathname)) addEventListener('unload', () => {});
  }, cold);
}

async function activate(link) {
  await expect(link).toBeVisible();
  const position = await link.evaluate(anchor => {
    anchor.scrollIntoView({ block: 'center', behavior: 'instant' });
    anchor.focus({ preventScroll: true });
    return { scroll: scrollY, top: anchor.getBoundingClientRect().top };
  });
  await link.press('Enter');
  return position;
}

async function expectReturn(page, source, following, position, cached = false) {
  await expect.poll(() => page.evaluate(() => window.nativeHandoffCached)).toBe(cached);
  await expect(source).toBeFocused();
  await expect(source).toBeInViewport({ ratio: 1 });
  await expect.poll(() => source.evaluate((anchor, previous) => Math.max(
    Math.abs(scrollY - previous.scroll), Math.abs(anchor.getBoundingClientRect().top - previous.top)
  ), position)).toBeLessThan(3);
  if (!cached) expect(await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type)).toBe('back_forward');
  await page.keyboard.press('Tab');
  await expect(following).toBeFocused();
}

const companyHandoffs = [
  {
    name: 'Compare Mercor', query: 'Mercor', source: compareResult, following: firstMercorSource,
    href: '/explore/#compare/mercor', result: '#compare-content [data-remove=mercor]',
  },
  {
    name: 'Compare A.Team via its alias', query: 'A Team', group: 'managed-ai-data-services', source: '[data-company=a-team] .directory-compare',
    following: '[data-company=a-team] .selected-archive summary',
    href: '/explore/#compare/a-team', result: '#compare-content [data-remove=a-team]',
  },
  {
    name: 'all original profiles', query: 'evaluation', source: '.directory-results-bar .directory-compare',
    href: '/explore/#compare', result: '#compare-view',
  },
  {
    name: 'the Mercor dossier', query: 'Mercor', source: '[data-company=mercor] h3 a', following: compareResult,
    href: 'https://sciencetostartup.com/company/mercor/', result: '.company-dossier',
  },
  {
    name: 'full guide search', query: '  Humans in the Loop  ', source: '[data-full-guide-search]',
    following: '.directory-scope summary', href: '/?search=++Humans+in+the+Loop++#browse-guide',
    result: '[data-result-type=Company][href="/company/org.humans_in_the_loop/"]',
  },
];

for (const handoff of companyHandoffs) {
  test(`native Companies restores ${handoff.name} on cold Back`, async ({ page, baseURL }) => {
    await trackDocument(page, true);
    await page.setViewportSize({ width: 390, height: 844 });
    if (handoff.result === '.company-dossier') {
      await page.route('https://sciencetostartup.com/**', async route => {
        const { pathname, search } = new URL(route.request().url());
        const response = await route.fetch({ url: new URL(pathname + search, baseURL).href });
        await route.fulfill({ response });
      });
    }
    const group = handoff.group ?? directoryGroup;
    await page.goto(`/companies/?group=${group}&reader=keep`);
    const search = page.getByRole('searchbox', { name: 'Search companies' });
    const source = page.locator(handoff.source);
    await search.fill(handoff.query);
    await expect(source).toHaveAttribute('href', handoff.href);
    const orderedCompanies = () => page.locator('[data-company]:visible').evaluateAll(cards => cards.map(card => card.dataset.company));
    const before = await orderedCompanies();
    if (!handoff.following) expect(before.length).toBeGreaterThan(1);
    const origin = page.url();
    expect(Object.fromEntries(new URL(origin).searchParams)).toEqual({ group, reader: 'keep', q: handoff.query.trim() });
    const position = await activate(source);
    await expect(page.locator(handoff.result)).toBeVisible();
    if (handoff.source === '[data-full-guide-search]') await expect(page.locator('#home-search-input')).toHaveValue(handoff.query);

    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(origin);
    await expect(search).toHaveValue(handoff.query);
    await expect(page.getByRole('combobox', { name: 'Business group' })).toHaveValue(group);
    await expect(source).toHaveAttribute('href', handoff.href);
    expect(await orderedCompanies()).toEqual(before);
    const following = handoff.following ? page.locator(handoff.following) : page.locator('[data-company]:visible h3 a').first();
    await expectReturn(page, source, following, position);
  });
}

test('native Companies leaves a new-tab Compare and ordinary visits alone', async ({ page, context, browserName, isMobile }) => {
  test.skip(browserName !== 'chromium' || isMobile, 'Exercise the desktop modifier that opens a background tab');
  await trackDocument(page, true);
  await page.goto('/companies/?q=Mercor');
  const origin = page.url();
  const source = page.locator(compareResult);
  const [tab] = await Promise.all([context.waitForEvent('page'), source.click({ modifiers: ['ControlOrMeta'] })]);
  await expect(tab).toHaveURL(/\/explore\/#compare\/mercor$/);
  await expect(page).toHaveURL(origin);
  await tab.close();
  await page.goto('/method/');
  await page.goBack({ waitUntil: 'commit' });
  await expect(page.locator('#company-query')).toHaveValue('Mercor');
  await expect(page.locator('body')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();

  await activate(source);
  await expect(page.locator('#compare-content [data-remove=mercor]')).toBeVisible();
  await page.goBack({ waitUntil: 'commit' });
  await expect(source).toBeFocused();
  await page.goForward({ waitUntil: 'commit' });
  await expect(page.locator('#compare-content [data-remove=mercor]')).toBeVisible();
  await page.goBack({ waitUntil: 'commit' });
  await expect(source).toBeFocused();
  await page.reload();
  await expect(source).not.toBeFocused();
});

for (const compare of [true, false]) {
  test(`native Work restores ${compare ? 'Compare results' : 'its Explore Work handoff'} on cold Back`, async ({ page }) => {
    await trackDocument(page, true);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/work/?q=Snorkel&sort=checked');
    const search = page.getByRole('searchbox', { name: 'Search listings' });
    await expect(search).toHaveValue('Snorkel');
    const source = page.locator(compare ? '[data-work-compare]' : '[data-work-explore]');
    const following = compare ? page.locator('[data-work-export]') : page.locator('.site-footer nav a').first();
    const href = compare ? '/work/?q=Snorkel&sort=checked&view=compare' : '/explore/#work?q=Snorkel&sort=checked';
    await expect(source).toHaveAttribute('href', href);
    const orderedWork = () => page.locator('[data-work-route]:visible').evaluateAll(cards => cards.map(card => card.dataset.workRoute));
    const before = await orderedWork();
    const origin = page.url();
    const position = await activate(source);
    await expect(page).toHaveURL(url => url.pathname + url.search + url.hash === href);
    await expect(page.locator(compare ? '[data-work-comparison]' : '#work-search')).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(origin);
    await expect(search).toHaveValue('Snorkel');
    await expect(source).toHaveAttribute('href', href);
    expect(await orderedWork()).toEqual(before);
    await expectReturn(page, source, following, position);
  });
}

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

legacy.describe('native handoffs without the Navigation API', () => {
  legacy.skip(({ browserName }) => browserName !== 'firefox', 'Use Firefox with the legacy History API');
  legacy.use({ viewport: { width: 390, height: 844 } });
  legacy.describe.configure({ timeout: 90_000 });

  const cases = [
    { from: '/companies/?q=Mercor', opener: compareResult, destination: '#compare-content [data-remove=mercor]', next: firstMercorSource },
    { from: '/work/?q=Snorkel&sort=checked', opener: '[data-work-compare]', destination: '[data-work-comparison]', next: '[data-work-export]' },
    { from: '/work/?q=Snorkel&sort=checked', opener: '[data-work-explore]', destination: '#work-search', next: '.site-footer nav a' },
  ];

  for (const { from, opener, destination, next } of cases) {
    legacy(`${opener} restores on Back after a cold Forward visit`, async ({ page }) => {
      await trackDocument(page, true);
      await page.goto('/method/');
      const previous = page.url();
      await page.goto(from);
      const source = page.locator(opener);
      const origin = page.url();
      const position = await activate(source);
      const target = page.locator(destination);
      await expect(target).toBeVisible();
      const landing = page.url();

      await page.goBack({ waitUntil: 'commit' });
      await expect(page).toHaveURL(origin);
      await expect(source).toBeFocused();
      await page.goForward({ waitUntil: 'commit' });
      await expect(page).toHaveURL(landing);
      await expect(target).toBeVisible();

      await Promise.all([page.waitForURL(previous), page.evaluate(() => setTimeout(() => history.go(-2), 0))]);
      await page.goForward({ waitUntil: 'commit' });
      await expect(page).toHaveURL(origin);
      await expect(source).toBeVisible();
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve)))));
      expect(await page.evaluate(() => ({
        api: Boolean(window.navigation), cached: window.nativeHandoffCached,
        type: performance.getEntriesByType('navigation')[0]?.type,
      }))).toEqual({ api: false, cached: false, type: 'back_forward' });
      await expect(page.locator('body')).toBeFocused();

      await page.goForward({ waitUntil: 'commit' });
      await expect(page).toHaveURL(landing);
      await expect(target).toBeVisible();
      await page.goBack({ waitUntil: 'commit' });
      await expectReturn(page, source, page.locator(next).first(), position);
    });
  }

  legacy('a duplicate directory address and another tab keep their own focus', async ({ page }) => {
    await trackDocument(page, true);
    await page.goto('/companies/?q=Mercor');
    const origin = page.url();
    const source = page.locator(compareResult);
    const position = await activate(source);
    const target = '#compare-content [data-remove=mercor]';
    await expect(page.locator(target)).toBeVisible();

    const duplicate = await page.context().newPage();
    await duplicate.goto(origin);
    await expect(duplicate.locator(compareResult)).toBeVisible();
    await expect(duplicate.locator('body')).toBeFocused();
    expect(await duplicate.evaluate(() => sessionStorage.getItem('s2s.nativeHandoff'))).toBeNull();
    await duplicate.close();

    await page.goto(origin);
    await expect(source).toBeVisible();
    await expect(page.locator('body')).toBeFocused();
    await page.goBack({ waitUntil: 'commit' });
    await expect(page.locator(target)).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(origin);
    await expectReturn(page, source, page.locator(firstMercorSource), position);
  });

  legacy('storage denial leaves native history and filters usable', async ({ page }) => {
    await trackDocument(page, true);
    await page.addInitScript(() => {
      Object.defineProperty(window, 'sessionStorage', {
        get() { throw new DOMException('Storage denied', 'SecurityError'); },
      });
    });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/work/?q=Snorkel&sort=checked');
    const origin = page.url();
    const source = page.locator('[data-work-compare]');
    await activate(source);
    await expect(page.locator('[data-work-comparison]')).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(origin);
    await expect(source).toBeVisible();
    await expect(page.locator('[data-work-filters] [name=q]')).toHaveValue('Snorkel');
    await expect(page.locator('body')).toBeFocused();
    expect(errors).toEqual([]);
  });
});

test('cached Companies and Work Back keep browser-managed focus', async ({ baseURL, browserName, isMobile }) => {
  test.skip(browserName !== 'chromium' || isMobile, 'Enable and verify the Chromium back-forward cache');
  const browser = await chromium.launch({ channel: 'chromium', ignoreDefaultArgs: ['--disable-back-forward-cache'] });
  try {
    const page = await browser.newPage({ baseURL, viewport: { width: 390, height: 844 } });
    await trackDocument(page, false);
    await page.goto('/companies/?q=Mercor');
    const companyLink = page.locator(compareResult);
    const companyPosition = await activate(companyLink);
    await expect(page.locator('#compare-content [data-remove=mercor]')).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expectReturn(page, companyLink, page.locator(firstMercorSource), companyPosition, true);

    await page.goto('/work/?q=Snorkel');
    await expect(page.getByRole('searchbox', { name: 'Search listings' })).toHaveValue('Snorkel');
    const workLink = page.locator('[data-work-explore]');
    const workPosition = await activate(workLink);
    await expect(page.locator('#work-search')).toHaveValue('Snorkel');
    await page.goBack({ waitUntil: 'commit' });
    await expectReturn(page, workLink, page.locator('.site-footer nav a').first(), workPosition, true);
  } finally {
    await browser.close();
  }
});
