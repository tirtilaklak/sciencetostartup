const { chromium, firefox, test, expect } = require('@playwright/test');

const roleId = 'afterquery.work.world-models';
const hourlyOrder = [
  roleId,
  'g2i.work.senior-swe-training-7c54f48a',
  'scale_ai.work.outlier-statistics',
  'afterquery.work.fullstack-evaluation',
  'afterquery.work.esl-expert',
  'afterquery.work.technical-content-writer-contract',
  'afterquery.work.content-writer-ai-evaluation-specialist-uk-us',
  'terac.work.ai-evaluator-shopping-assistant',
  'invisible.work.full-stack-trainer',
  'invisible.work.computer-vision',
  'surge_ai.work.swe-environments',
  'terac.work.rl-environment-creation',
  'appen.work.sage-media',
  'g2i.work.senior-swe-training',
  'terac.work.ml-scenarios',
  'rws_trainai.work.polaris-asr',
  'elorian.work.model-safety',
  'pareto.work.investment-analyst',
];
const work = '/work/?pay=hourly&sort=hourly&reader=%20A%2Bb%20';
const profile = '/company/afterquery/#' + roleId;

function controls(page) {
  const card = page.locator(`[data-work-route="${roleId}"]`);
  return {
    card,
    opener: card.getByRole('heading', { name: 'World Models Machine Learning Expert', exact: true })
      .getByRole('link', { name: 'World Models Machine Learning Expert', exact: true }),
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
  expect(ids).toEqual(hourlyOrder);
  const { opener, application, terms } = controls(page);
  await expect(opener).toHaveAccessibleDescription('AfterQuery');
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

function holdWorkFrames() {
  const frame = window.requestAnimationFrame;
  const callbacks = [];
  window.requestAnimationFrame = callback => callbacks.push(callback);
  window.releaseWorkFrames = () => {
    window.requestAnimationFrame = frame;
    for (const callback of callbacks) frame(callback);
  };
}

async function releaseWorkFrames(page) {
  await page.evaluate(() => new Promise(resolve => {
    window.releaseWorkFrames();
    requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }));
}

async function holdWorkReturnLoad(page) {
  const { promise: heldLoad, resolve: releaseLoad } = Promise.withResolvers();
  await page.route('**/work-return-test.png', async route => {
    await heldLoad;
    await route.fulfill({ status: 204 });
  });
  await page.addInitScript(() => {
    if (location.pathname !== '/work/' || performance.getEntriesByType('navigation')[0]?.type !== 'back_forward') return;
    document.addEventListener('DOMContentLoaded', () => {
      const image = new Image();
      image.hidden = true;
      image.src = '/work-return-test.png';
      document.body.append(image);
    }, { once: true });
  });
  return releaseLoad;
}

async function returnWithEarlyBookmarkFocus(page, whileHeld = async () => {}) {
  const releaseLoad = await holdWorkReturnLoad(page);
  await page.addInitScript(`if (location.pathname === '/work/' &&
    performance.getEntriesByType('navigation')[0]?.type === 'back_forward') (${holdWorkFrames})();`);
  await observeHistory(page, true);
  await page.goto(work + '#' + roleId);
  const departure = await activateProfile(page);
  try {
    await page.goBack({ waitUntil: 'commit' });
    await expect(page.locator('[data-work-compare]')).toBeVisible();
    const entry = await page.evaluate(() => ({
      key: navigation.currentEntry.key,
      from: navigation.activation.from.key,
      saved: history.state?.workReturnFocus?.destinationKey,
    }));
    expect(entry.saved).toBe(entry.from);
    // Run Chromium's fragment focus before the restore frame with no reader input.
    await page.evaluate(() => location.replace(location.href));
    await expect(controls(page).card).toBeFocused();
    expect(await page.evaluate(() => ({
      key: navigation.currentEntry.key,
      from: navigation.activation.from.key,
      ready: document.readyState,
      interacted: window.WorkPageResource.interacted,
    }))).toEqual({ key: entry.key, from: entry.from, ready: 'interactive', interacted: false });
    await whileHeld();
  } finally {
    releaseLoad();
  }
  await expect.poll(() => page.evaluate(() => window.workReturnPersisted)).toBe(false);
  await releaseWorkFrames(page);
  return departure;
}

test.describe('Work application and source return', () => {
  test.use({ viewport: { width: 320, height: 720 } });

  for (const fromTerms of [false, true]) {
    const label = fromTerms ? 'source in Terms & sources' : 'primary application link';
    test(`cold Back restores the exact ${label} on a bookmarked Work entry`, async ({ page }) => {
      await observeHistory(page, true);
      const bookmark = '/work/?q=World+Models&pay=hourly#' + roleId;
      const destination = 'https://experts.afterquery.com/apply/world-models-ml-experts';
      await page.route(destination, route => route.fulfill({
        contentType: 'text/html', body: '<!doctype html><title>Application source</title><p>Application source fixture</p>',
      }));
      await page.goto(bookmark);
      const { card, application, terms } = controls(page);
      await expect(card).toBeFocused();
      const summary = terms.locator('summary');
      if (fromTerms) await summary.press('Enter');
      const source = terms.locator(`a[href="${destination}"]`);
      const opener = fromTerms ? source : application;
      await expect(opener).toHaveAttribute('href', destination);
      await opener.scrollIntoViewIfNeeded();
      await opener.focus();
      const top = await opener.evaluate(link => link.getBoundingClientRect().top);
      await opener.press('Enter');
      await expect(page).toHaveURL(destination);

      await page.goBack({ waitUntil: 'commit' });
      await expect(page).toHaveURL(bookmark);
      await expect.poll(() => page.evaluate(() => window.workReturnPersisted)).toBe(false);
      await expect(opener).toBeFocused();
      await expect(terms).toHaveJSProperty('open', fromTerms);
      await expect(opener).toBeInViewport({ ratio: 1 });
      await expect.poll(() => opener.evaluate((link, previous) => Math.abs(link.getBoundingClientRect().top - previous), top)).toBeLessThan(3);
      if (fromTerms) await page.keyboard.press('Shift+Tab');
      else await page.keyboard.press('Tab');
      await expect(summary).toBeFocused();
    });
  }
});

test.describe('Work company-profile handoff', () => {
  test.use({ viewport: { width: 1024, height: 600 } });
  test.skip(({ isMobile }) => isMobile, 'Use the audited desktop keyboard layout');

  for (const hash of ['', '#' + roleId]) {
    test(`cold Back restores the role title link${hash ? ' on a bookmarked Work entry' : ''}`, async ({ page }) => {
      await observeHistory(page, true);
      await page.goto(work + hash);
      await expect(page).toHaveURL(work + hash);
      const departure = await activateProfile(page);
      await page.goBack({ waitUntil: 'commit' });
      await expectProfileReturn(page, departure, false);
    });
  }

  test('deferred bookmark placement preserves keyboard focus on open Terms', async ({ page }) => {
    await page.addInitScript(`if (location.pathname === '/work/') (${holdWorkFrames})();`);
    await page.goto(work + '#' + roleId);
    await expect(page.locator('[data-work-compare]')).toBeVisible();
    const { terms } = controls(page);
    const summary = terms.locator('summary');
    for (let tab = 0; tab < 90 && !await summary.evaluate(node => node === document.activeElement); tab++) {
      await page.keyboard.press('Tab');
    }
    await expect(summary).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(terms).toHaveJSProperty('open', true);
    expect(await page.evaluate(() => window.WorkPageResource.interacted)).toBe(true);
    const scroll = await page.evaluate(() => scrollY);
    await releaseWorkFrames(page);
    await expect(summary).toBeFocused();
    await expect(terms).toHaveJSProperty('open', true);
    expect(await page.evaluate(() => scrollY)).toBe(scroll);
    await page.keyboard.press('Tab');
    await expect(terms.locator('a').first()).toBeFocused();
  });

  for (const readerScroll of [false, true]) {
    test(`cold bookmarked Back ${readerScroll ? 'honors a wheel scroll after pageshow' : 'recovers from a late history scroll'}`, async ({ page, browserName }) => {
      test.skip(browserName !== 'webkit', 'Exercise the reported WebKit timing');
      await observeHistory(page, true);
      await page.addInitScript(`if (location.pathname === '/work/') {
        document.addEventListener('focusin', function openerFocused(event) {
          if (performance.getEntriesByType('navigation')[0]?.type !== 'back_forward') return;
          if (!event.target.matches('[data-work-route="${roleId}"] h3 a')) return;
          document.removeEventListener('focusin', openerFocused);
          (${holdWorkFrames})();
          if (${readerScroll}) return;
          const displace = () => setTimeout(() => {
            // Model WebKit's late native bookmark focus and viewport displacement.
            const bookmark = document.getElementById('${roleId}');
            bookmark.focus({ preventScroll: true });
            window.workLateBookmarkFocused = document.activeElement === bookmark;
            scrollTo(0, document.documentElement.scrollHeight);
            window.workLateScroll = scrollY;
          }, 0);
          if (window.workReturnPersisted === false) displace();
          else addEventListener('pageshow', displace, { once: true });
        });
      }`);
      await page.goto(work + '#' + roleId);
      const departure = await activateProfile(page);
      const { opener, terms } = controls(page);
      await page.goBack({ waitUntil: 'commit' });
      await expect(opener).toBeFocused();
      await expect(terms).toHaveJSProperty('open', true);
      expect(await page.evaluate(() => typeof window.releaseWorkFrames)).toBe('function');
      await expect.poll(() => page.evaluate(() => window.workReturnPersisted)).toBe(false);
      if (readerScroll) {
        await page.mouse.move(700, 350);
        await page.mouse.wheel(0, 900);
        await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(departure.position.scroll + 300);
        expect(await page.evaluate(() => window.WorkPageResource.interacted)).toBe(true);
        await releaseWorkFrames(page);
        expect(await page.evaluate(() => scrollY)).toBeGreaterThan(departure.position.scroll + 300);
        await expect(opener).toBeFocused();
        await expect(terms).toHaveJSProperty('open', true);
      } else {
        await expect.poll(() => page.evaluate(() => window.workLateScroll ?? 0)).toBeGreaterThan(departure.position.scroll + 300);
        expect(await page.evaluate(() => window.workLateBookmarkFocused)).toBe(true);
        await releaseWorkFrames(page);
        await expectProfileReturn(page, departure, false);
      }
    });
  }

  test('cold Back restores the exact opener when Chromium focuses its bookmark first', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Exercise Chromium’s native fragment focus during the held load');
    const departure = await returnWithEarlyBookmarkFocus(page);
    await expectProfileReturn(page, departure, false);
  });

  test('cold Back leaves the bookmark focused after reader input', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Exercise reader input during Chromium’s fragment focus');
    const { card, terms } = controls(page);
    await returnWithEarlyBookmarkFocus(page, async () => {
      await page.keyboard.press('ArrowDown');
      expect(await page.evaluate(() => window.WorkPageResource.interacted)).toBe(true);
    });
    await expect(card).toBeFocused();
    await expect(terms).toHaveJSProperty('open', false);
  });

  test('cold Back leaves focus on another control when focus moves during the hold', async ({ page, browserName }) => {
    test.skip(browserName !== 'chromium', 'Exercise another focus target during Chromium’s fragment focus');
    const compare = page.locator('[data-work-compare]');
    await returnWithEarlyBookmarkFocus(page, () => compare.focus());
    await expect(compare).toBeFocused();
    await expect(controls(page).terms).toHaveJSProperty('open', false);
  });

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

  for (const hash of ['', '#' + roleId]) {
    test(`cached Back keeps browser-managed Terms, focus and scroll${hash ? ' on a bookmarked Work entry' : ''}`, async ({ baseURL, browserName }) => {
      test.skip(browserName !== 'chromium', 'Enable the audited browser’s back-forward cache');
      const browser = await chromium.launch({ channel: 'chromium', ignoreDefaultArgs: ['--disable-back-forward-cache'] });
      try {
        const page = await browser.newPage({ baseURL, viewport: { width: 1024, height: 600 } });
        await observeHistory(page, false);
        await page.goto(work + hash);
        const departure = await activateProfile(page);
        await page.goBack({ waitUntil: 'commit' });
        await expectProfileReturn(page, departure, true);
      } finally {
        await browser.close();
      }
    });
  }
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
