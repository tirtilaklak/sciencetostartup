const { chromium, firefox, test, expect } = require('@playwright/test');

const directoryGroup = 'expert-data-evaluation';
const compareResult = '[data-company=mercor] .directory-compare';
const mercorDossier = '[data-company=mercor] h3 a';
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

async function routePublishedPages(page, baseURL) {
  await page.route('https://sciencetostartup.com/**', async route => {
    const { pathname, search } = new URL(route.request().url());
    const response = await route.fetch({ url: new URL(pathname + search, baseURL).href });
    await route.fulfill({ response });
  });
}

async function expectReturn(page, source, following, position, cached = false) {
  await expect(source).toBeFocused();
  await expect.poll(() => page.evaluate(() => window.nativeHandoffCached)).toBe(cached);
  await expect(source).toBeInViewport({ ratio: 1 });
  await expect.poll(() => source.evaluate((anchor, previous) => Math.max(
    Math.abs(scrollY - previous.scroll), Math.abs(anchor.getBoundingClientRect().top - previous.top)
  ), position)).toBeLessThan(3);
  if (!cached) expect(await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type)).toBe('back_forward');
  await page.keyboard.press('Tab');
  await expect(following).toBeFocused();
}

async function expectColdStart(page) {
  await expect.poll(() => page.evaluate(() => ({
    api: Boolean(window.navigation), cached: window.nativeHandoffCached,
    type: performance.getEntriesByType('navigation')[0]?.type,
    enhancing: document.documentElement.hasAttribute('data-page-enhancement'),
  }))).toEqual({ api: false, cached: false, type: 'back_forward', enhancing: false });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve)))));
  await expect(page.locator('body')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
}

test.describe('About navigation without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('the About fragment keeps the current masthead visible', async ({ page }) => {
    for (const [width, height] of [[320, 640], [390, 844], [1440, 900]]) {
      await page.setViewportSize({ width, height });
      await page.goto('/method/#about');
      await expect(page.locator('.site-header')).toBeInViewport({ ratio: 1 });
      await expect(page.getByRole('heading', { name: 'About', exact: true })).toBeInViewport();
      await expect(page.locator('.site-header a[aria-current="page"]')).toHaveText(['About', 'About']);
      expect(await page.evaluate(() => scrollY)).toBe(0);
    }
  });
});

test('About reopens Coverage and limits on cold Back from the company directory', async ({ page, baseURL, isMobile }) => {
  await trackDocument(page, false);
  await page.addInitScript(() => {
    if (location.pathname === '/method/') addEventListener('unload', () => {});
  });
  await page.setViewportSize(isMobile ? { width: 390, height: 844 } : { width: 1440, height: 900 });
  await routePublishedPages(page, baseURL);
  const origin = 'https://sciencetostartup.com/method/#about';
  await page.goto(origin);
  const coverage = page.locator('#coverage-notes');
  await coverage.locator('summary').press('Enter');
  const source = coverage.getByRole('link', { name: 'current company directory' });
  const position = await activate(source);
  await expect(page).toHaveURL('https://sciencetostartup.com/companies/');
  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(origin);
  await expect(coverage).toHaveAttribute('open', '');
  await expectReturn(page, source, page.locator('#download-files > summary'), position);
});

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
    name: 'the Mercor dossier', query: 'Mercor', source: mercorDossier, following: compareResult,
    href: 'https://sciencetostartup.com/company/mercor/', result: '.company-dossier',
  },
  {
    name: 'full guide search without the native search shell', query: '  Humans in the Loop  ', source: '[data-full-guide-search]',
    following: '.directory-scope summary', href: '/?search=++Humans+in+the+Loop++#browse-guide',
    result: '[data-result-type=Company][href="/company/org.humans_in_the_loop/"]',
  },
];

for (const handoff of companyHandoffs) {
  test(`native Companies restores ${handoff.name} on cold Back`, async ({ page, baseURL }) => {
    await trackDocument(page, true);
    await page.setViewportSize({ width: 390, height: 844 });
    if (handoff.result === '.company-dossier') await routePublishedPages(page, baseURL);
    if (handoff.source === '[data-full-guide-search]') await page.route('**/guide-search-shell.js', route => route.abort());
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
    if (handoff.following) {
      await expectReturn(page, source, page.locator(handoff.following), position);
    } else {
      const revenue = page.getByRole('link', { name: 'Revenue & growth', exact: true });
      await expect(revenue).toHaveAttribute('href', '/explore/#business-health');
      await expectReturn(page, source, revenue, position);
      await page.keyboard.press('Tab');
      await expect(page.locator('[data-company]:visible h3 a').first()).toBeFocused();
    }
  });
}

test.describe('Mercor dossier viewport on cold Back', () => {
  test.skip(({ browserName, isMobile }) => browserName !== 'webkit' || !isMobile, 'Exercise the Mobile WebKit return');

  for (const userScroll of [false, true]) {
    test(userScroll ? 'keeps a reader’s scroll after pageshow' : 'recovers from a late scroll to the top', async ({ page, baseURL }) => {
      await trackDocument(page, true);
      await page.setViewportSize({ width: 390, height: 844 });
      await routePublishedPages(page, baseURL);
      await page.addInitScript(({ selector, userScroll }) => {
        if (location.pathname !== '/companies/') return;
        const viewport = link => ({ scroll: scrollY, top: link.getBoundingClientRect().top, time: performance.now() });
        window.mercorRestoredViewport = new Promise(resolve => {
          if (!userScroll) {
            const listen = window.addEventListener;
            window.addEventListener = function (type, callback, options) {
              const result = Reflect.apply(listen, this, arguments);
              const link = document.activeElement;
              if (this === window && type === 'scroll' && options?.signal && link?.matches(selector) &&
                  window.nativeHandoffCached === false &&
                  performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
                window.addEventListener = listen;
                const guardStarted = performance.now();
                // The opener is already positioned when its guarded scroll listener is installed.
                // Inject on the next microtask so a slow animation frame cannot outlast the guard.
                queueMicrotask(() => {
                  const first = viewport(link);
                  const guardActive = !options.signal.aborted;
                  scrollTo({ top: 0, behavior: 'instant' });
                  resolve({ first, overwrite: viewport(link), guardStarted, guardActive });
                });
              }
              return result;
            };
            return;
          }
          document.addEventListener('focusin', event => {
            const link = event.target;
            if (!link.matches(selector) || window.nativeHandoffCached !== false ||
                performance.getEntriesByType('navigation')[0]?.type !== 'back_forward') return;
            requestAnimationFrame(() => resolve({ first: viewport(link) }));
          });
        });
        if (userScroll) {
          window.mercorReaderInput = new Promise(resolve => {
            addEventListener('keydown', event => {
              if (event.key !== 'Home' || !event.isTrusted) return;
              // Make the reader's scroll instant so key animation cannot mask a correction.
              event.preventDefault();
              const input = viewport(document.activeElement);
              scrollTo({ top: 0, behavior: 'instant' });
              resolve(input);
            });
          });
        }
      }, { selector: mercorDossier, userScroll });

      await page.goto(`/companies/?group=${directoryGroup}&reader=keep`);
      const search = page.getByRole('searchbox', { name: 'Search companies' });
      await search.fill('Mercor');
      const origin = page.url();
      const source = page.locator(mercorDossier);
      const position = await activate(source);
      expect(position.scroll).toBeGreaterThan(0);
      await expect(page.locator('.company-dossier')).toBeVisible();
      await page.goBack({ waitUntil: 'commit' });
      await page.waitForFunction(() => Boolean(window.mercorRestoredViewport));
      const { first, overwrite, guardStarted, guardActive } = await page.evaluate(() => window.mercorRestoredViewport);
      if (userScroll) {
        await page.keyboard.press('Home');
        const input = await page.evaluate(() => window.mercorReaderInput);
        expect(input.time - first.time).toBeLessThan(200);
        expect(Math.abs(input.scroll - position.scroll)).toBeLessThan(3);
        await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
        // Let the short recovery window expire before checking the reader's position.
        await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 300)));
        expect(await page.evaluate(() => scrollY)).toBe(0);
        await expect(source).toBeFocused();
      }
      await expect(page).toHaveURL(origin);
      await expect(search).toHaveValue('Mercor');
      expect(await page.evaluate(() => window.nativeHandoffCached)).toBe(false);
      expect(Math.abs(first.scroll - position.scroll)).toBeLessThan(3);
      expect(Math.abs(first.top - position.top)).toBeLessThan(3);
      if (!userScroll) {
        expect(guardActive).toBe(true);
        expect(overwrite.time - guardStarted).toBeLessThan(250);
        expect(overwrite.scroll).toBe(0);
        expect(overwrite.top - first.top).toBeGreaterThan(0);
        await expectReturn(page, source, page.locator(compareResult), position);
      }
    });
  }
});

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
    legacy(`${opener} restores on cold Back to the oldest entry`, async ({ page }) => {
      await trackDocument(page, true);
      await page.goto(from);
      expect(await page.evaluate(() => history.length)).toBe(1);
      const origin = page.url();
      await page.goto('/method/');
      await page.goBack({ waitUntil: 'commit' });
      await expect(page).toHaveURL(origin);
      await expectColdStart(page);

      const source = page.locator(opener);
      const position = await activate(source);
      const target = page.locator(destination);
      await expect(target).toBeVisible();
      const landing = page.url();

      await page.goBack({ waitUntil: 'commit' });
      await expect(page).toHaveURL(origin);
      await expect(source).toBeFocused(); // Leave the stored opener in place for the repeated return.
      await page.goForward({ waitUntil: 'commit' });
      await expect(page).toHaveURL(landing);
      await expect(target).toBeVisible();
      await page.goBack({ waitUntil: 'commit' });
      await expect(page).toHaveURL(origin);
      await expectReturn(page, source, page.locator(next).first(), position);
    });
  }

  const priors = [
    { name: 'the original edition', path: '/research/editions/2026-11-12/', scriptFree: true },
    { name: 'Method', path: '/method/' },
    { name: 'another origin', path: 'https://history-prior.example/', scriptFree: true },
  ];

  for (const { name, path, scriptFree } of priors) {
    for (const { from, opener, destination } of cases) {
      legacy(`${opener} starts normally on ambiguous cold traversals past ${name}`, async ({ page }) => {
        await trackDocument(page, true);
        if (path.startsWith('https://')) await page.route(path, route => route.fulfill({
          contentType: 'text/html', body: '<!doctype html><title>External page</title><main>Another origin</main>',
        }));

        const companyQuery = from.startsWith('/companies/') ? page.getByRole('searchbox', { name: 'Search companies' }) : null;
        const visibleCompanies = () => page.locator('[data-company]:visible').evaluateAll(cards => cards.map(card => card.dataset.company));
        async function openHandoff() {
          await page.goto(path);
          if (scriptFree) await expect(page.locator('script:not([type="application/ld+json"])')).toHaveCount(0);
          const previous = page.url();
          await page.goto(from);
          const origin = page.url();
          if (companyQuery) {
            await companyQuery.fill('  Mercor  ');
            await expect(page).toHaveURL(origin);
          }
          const results = companyQuery ? await visibleCompanies() : null;
          if (results) expect(results).toContain('mercor');
          await activate(page.locator(opener));
          await expect(page.locator(destination)).toBeVisible();
          return { previous, origin, results };
        }

        async function expectAmbiguousArrival({ origin, results }) {
          await expect(page).toHaveURL(origin);
          await expect(page.locator(opener)).toBeVisible();
          await expectColdStart(page);
          if (companyQuery) {
            await expect(companyQuery).toHaveValue('  Mercor  ');
            expect(await visibleCompanies()).toEqual(results);
          }
        }

        const handoff = await openHandoff();
        await Promise.all([page.waitForURL(handoff.previous), page.evaluate(() => setTimeout(() => history.go(-2), 0))]);
        await page.goForward({ waitUntil: 'commit' });
        await expectAmbiguousArrival(handoff);

        const direct = await openHandoff();
        await page.goBack({ waitUntil: 'commit' });
        await expectAmbiguousArrival(direct);
      });
    }
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
