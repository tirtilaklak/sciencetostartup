const { chromium, test, expect } = require('@playwright/test');

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
