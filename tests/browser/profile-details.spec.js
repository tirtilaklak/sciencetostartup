const { test, expect } = require('@playwright/test');

const renderers = ['profileProductGrid', 'profileCase', 'profileRelationshipGrid', 'profileRisks',
  'profilePeople', 'profileCapital', 'profileTraction', 'profileArchive'];

test('company and work browsing keep the detailed renderer factory unloaded', async ({ page }) => {
  const moduleRequests = [];
  page.on('request', request => {
    if (/\/js\/health\.[^/]+\.js$/.test(new URL(request.url()).pathname)) moduleRequests.push(request.url());
  });
  await page.goto('/explore/#companies');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('[data-company-card]')).toHaveCount(39);
  expect(await page.evaluate(() => window.ScienceProfileDetails)).toBeUndefined();
  expect(await page.evaluate(() => window.ScienceDetailViews)).toBeUndefined();
  await page.goto('/explore/#work');
  await expect(page.locator('#work-cards')).toContainText('Named listings');
  await page.locator('#work-search').fill('Python');
  await expect(page.locator('#work-count')).not.toContainText('Loading');
  await expect(page.locator('#work-cards')).toContainText(/Python/i);
  expect(moduleRequests).toEqual([]);
  expect(await page.evaluate(() => window.ScienceProfileDetails)).toBeUndefined();
  expect(await page.evaluate(() => window.ScienceDetailViews)).toBeUndefined();
});

test('the sourced introduction survives a pending factory and all profile panes use its renderers', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/js/health.*.js*', async route => { await gate; await route.continue(); });
  await page.goto('/explore/#company/mercor/work', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
  await expect(page.locator('.profile-introduction h1')).toHaveText('Mercor');
  await expect(page.locator('.profile-summary')).not.toBeEmpty();
  expect(await page.evaluate(() => window.ScienceProfileDetails)).toBeUndefined();
  await page.locator('.profile-introduction').evaluate(node => { node.dataset.testRetainedIntroduction = 'yes'; });
  release();
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expect(page.locator('.profile-introduction')).toHaveAttribute('data-test-retained-introduction', 'yes');
  expect(await page.evaluate(names => ({ buildId: window.ScienceProfileDetails.buildId,
    expected: window.APP_BUILD_ID, functions: names.every(name => typeof window.ScienceProfileDetails[name] === 'function') }), renderers))
    .toMatchObject({ functions: true });
  expect(await page.evaluate(() => window.ScienceProfileDetails.buildId)).toBe(await page.evaluate(() => window.APP_BUILD_ID));

  await page.getByRole('tab', { name: 'Paid work', exact: true }).focus();
  await page.keyboard.press('Home');
  await expect(page.locator('#profile-pane-business .offering-card').first()).toBeVisible();
  await expect(page.locator('#profile-pane-business [data-claim]').first()).toBeAttached();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#profile-pane-traction .profile-scale-observation').first()).toBeVisible();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#profile-pane-people .capital-event').first()).toBeVisible();
  await expect(page.locator('#profile-pane-people .leadership-card').first()).toBeVisible();
  await page.keyboard.press('End');
  await expect(page.locator('#profile-pane-work')).toBeVisible();

  await page.locator('.profile-evidence > summary').click();
  await expect(page.locator('.profile-archive')).toBeVisible();
  const expected = await page.evaluate(() => ({ claims: companyClaims('mercor').length, sources: companySources('mercor').length }));
  await expect(page.locator('#profile-questions [data-claim-record]')).toHaveCount(expected.claims);
  await expect(page.locator('#profile-sources [data-source]')).toHaveCount(expected.sources);
  await page.locator('#profile-questions').locator('..').locator('summary').click();
  await expect(page.locator('#profile-questions [data-claim-record]').first()).toBeVisible();
});

for (const registry of ['ScienceProfileDetails', 'ScienceDetailViews']) for (const mode of ['missing', 'stale']) {
  test(`a ${mode} ${registry} registration fails visibly and recovers through the existing retry`, async ({ page }) => {
    // The actual SRI-checked factory still loads. Inject only the post-initialization
    // registration fault so the loader's registry validation is exercised directly.
    await page.addInitScript(({fault, registry}) => {
      window.testRendererFault = fault;
      let factory;
      Object.defineProperty(window, 'SCIENCE_HEALTH_MODULE', {
        configurable: true,
        get() { return factory; },
        set(value) {
          const initialize = value.initialize;
          value.initialize = function () {
            initialize.call(this);
            if (window.testRendererFault === 'missing') delete window[registry];
            if (window.testRendererFault === 'stale') window[registry] = { ...window[registry], buildId: 'older-profile-release' };
          };
          factory = value;
        },
      });
    }, {fault: mode, registry});
    await page.goto('/explore/#company/mercor/work');
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'failed');
    await expect(page).toHaveTitle('Mercor · ScienceToStartup');
    await expect(page.getByRole('heading', { name: 'Evidence for Mercor could not load.' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Read the plain paid work section' })).toHaveAttribute('href', '/company/mercor/#work');
    expect(await page.evaluate(() => window.APP_HEALTH_READY)).toBeUndefined();
    await page.evaluate(() => { window.testRendererFault = ''; });
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    await expect(page.locator('#profile-pane-work')).toBeFocused();
    expect(await page.evaluate(() => window.ScienceProfileDetails.buildId)).toBe(await page.evaluate(() => window.APP_BUILD_ID));
    await page.getByRole('tab', { name: 'Business', exact: true }).click();
    await expect(page.locator('#profile-pane-business .offering-card').first()).toBeVisible();
  });
}

test('a comparison keeps its exact peer request and retries the missing evidence', async ({ page }) => {
  const requested = [];
  let refused = true;
  await page.route('**/presentation/company-*.json', route => {
    const id = new URL(route.request().url()).pathname.split('/').at(-1).split('.')[0].replace('company-', '');
    requested.push(id);
    return id === 'taskus' || id === 'appen' || id === 'scale_ai' && refused ? route.abort() : route.continue();
  });
  const pair = '/explore/#compare/snorkel_ai/scale_ai?reader=keep';
  await page.goto(pair);
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'failed');
  await expect(page).toHaveTitle('Snorkel AI and Scale AI · Compare · ScienceToStartup');
  await expect(page.locator('#compare-content')).not.toContainText('TaskUs');
  expect(requested.toSorted()).toEqual(['scale_ai', 'snorkel_ai']);

  refused = false;
  await page.getByRole('button', { name: 'Try again' }).press('Enter');
  await expect(page).toHaveURL(new RegExp(pair.replace('?', '\\?') + '$'));
  await expect(page.locator('#compare-content thead a')).toHaveText(['Snorkel AI', 'Scale AI']);
  await expect(page.locator('#compare-view h1')).toBeFocused();
});

const fundingClaim = 'a-team.claim.total_funding';
const fundingBookmark = '/explore/#company/a-team/claim/' + fundingClaim;
const fundingCorrection = '#corrections?company=a-team&claim=' + fundingClaim;
const correctionLink = page => page.locator('#evidence-dialog').getByRole('link', { name: 'Request a correction' });

async function expectFundingCorrectionDrafts(page) {
  await expect(page.locator('#corrections')).toBeFocused();
  for (const [label, parameter] of [
    ['Email a correction for this record', 'body'],
    ['Start a public GitHub correction', 'target'],
  ]) {
    const draft = new URL(await page.getByRole('link', { name: label }).getAttribute('href'));
    expect(draft.searchParams.get(parameter)).toContain('https://sciencetostartup.com' + fundingBookmark);
    expect(draft.searchParams.get(parameter)).toContain(fundingClaim);
  }
}

test('a refused claim bookmark reopens the exact sources on keyboard retry', async ({ page }) => {
  let refused = true;
  await page.route('**/presentation/company-a-team.*.json', route => refused ? route.abort() : route.continue());
  await page.goto(fundingBookmark, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'A.Team', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Read the plain company sources' })).toHaveAttribute('href', '/company/a-team/#sources');

  refused = false;
  await page.getByRole('button', { name: 'Try again' }).press('Enter');
  await expect(page.locator('#evidence-dialog')).toBeVisible();
  await expect(page.locator('#close-evidence')).toBeFocused();
  await expect(page.locator('#evidence-dialog [data-source-id]')).toHaveCount(3);
  await expect(page.locator('#evidence-dialog .evidence-data')).toContainText('Source checked');
  expect(new URL(page.url()).pathname + new URL(page.url()).hash).toBe(fundingBookmark);

  await expect(correctionLink(page)).toHaveAttribute('href', fundingCorrection);
  await correctionLink(page).press('Enter');
  await expectFundingCorrectionDrafts(page);
  await page.goBack();
  await expect(page.locator('#close-evidence')).toBeFocused();
  expect(new URL(page.url()).hash).toBe(new URL(fundingBookmark, page.url()).hash);
  await page.goForward();
  await expectFundingCorrectionDrafts(page);
});

test('the correction address restores the exact claim drafts in a fresh tab and on reload', async ({ page, context, browserName, isMobile }) => {
  await page.goto(fundingBookmark, { waitUntil: 'domcontentloaded' });
  const correction = correctionLink(page);
  await expect(correction).toHaveAttribute('href', fundingCorrection);
  let coldTab;
  if (browserName === 'chromium' && !isMobile) {
    [coldTab] = await Promise.all([context.waitForEvent('page'), correction.click({ modifiers: ['ControlOrMeta'] })]);
  } else {
    coldTab = await context.newPage();
    await coldTab.goto(new URL(await correction.getAttribute('href'), page.url()).href, { waitUntil: 'domcontentloaded' });
  }
  await expectFundingCorrectionDrafts(coldTab);
  await coldTab.reload({ waitUntil: 'domcontentloaded' });
  await expectFundingCorrectionDrafts(coldTab);
  await coldTab.goto('/explore/#corrections?company=mercor&claim=' + fundingClaim);
  await expect(coldTab.getByRole('link', { name: 'Email a correction for this record' })).toHaveCount(0);
  const genericIssue = new URL(await coldTab.getByRole('link', { name: 'Start a public GitHub correction' }).getAttribute('href'));
  expect(genericIssue.searchParams.get('target')).toBeNull();
});

const imeritLedger = '/explore/#company/imerit/sources';
const imeritImage = '/assets/products/imerit-exl-visual.png';

async function openNativeSourceLedger(page, baseURL) {
  await page.goto('/company/imerit/');
  await page.locator('summary#sources, #sources > summary').press('Enter');
  const ledger = page.getByRole('link', { name: 'Source ledger', exact: true });
  await expect(ledger).toHaveAttribute('href', 'https://sciencetostartup.com' + imeritLedger);
  // Map the public origin to the QA host while leaving the link activation native.
  await ledger.evaluate((link, destination) => { link.href = destination; }, new URL(imeritLedger, baseURL).href);
  await ledger.press('Enter');
  await expect(page).toHaveURL(new URL(imeritLedger, baseURL).href);
}

async function expectSourceHeadingInView(heading) {
  await expect.poll(() => heading.evaluate(node => {
    const { top, bottom } = node.getBoundingClientRect();
    const masthead = document.querySelector('.topbar').getBoundingClientRect();
    const tabs = document.querySelector('.profile-tabs').getBoundingClientRect();
    return top >= Math.max(masthead.bottom, tabs.bottom) && bottom <= innerHeight;
  })).toBe(true);
}

test('the native Source ledger lands at All sources and Tabs into its sources before images load', async ({ page, baseURL }) => {
  let releaseImage;
  const imageGate = new Promise(resolve => { releaseImage = resolve; });
  let imageRequested = false;
  // Browsers can skip a lazy image already above the newly scrolled viewport.
  // Start its request so the regression is exercised in every engine.
  await page.addInitScript(path => {
    const observer = new MutationObserver(() => {
      const image = document.querySelector(`.profile-v2 img[src="${path}"]`);
      if (!image) return;
      image.loading = 'eager';
      observer.disconnect();
    });
    observer.observe(document, { childList: true, subtree: true });
  }, imeritImage);
  await page.route('**' + imeritImage, async route => {
    if (new URL(page.url()).pathname === '/explore/') {
      imageRequested = true;
      await imageGate;
    }
    await route.continue();
  });
  try {
    await openNativeSourceLedger(page, baseURL);
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    const heading = page.getByRole('heading', { name: 'All sources', exact: true });
    const source = page.locator('#profile-sources .sources-list a').first();
    const image = page.locator(`.profile-v2 img[src="${imeritImage}"]`);
    await expectSourceHeadingInView(heading);
    await expect(heading).toBeFocused();
    await expect.poll(() => imageRequested).toBe(true);
    expect(await image.evaluate(node => node.complete)).toBe(false);

    await page.keyboard.press('Tab');
    await expect(source).toBeFocused();
    releaseImage();
    await expect.poll(() => image.evaluate(node => node.complete)).toBe(true);
    await expect(source).toBeFocused();
    await expectSourceHeadingInView(heading);

    // Native Tab focus scrolls smoothly; finish that motion before measuring
    // the user's new position for the exact Back/Forward restoration check.
    await page.evaluate(() => new Promise(resolve => {
      let previous = scrollY;
      let stableFrames = 0;
      const sample = () => {
        const current = scrollY;
        stableFrames = current === previous ? stableFrames + 1 : 0;
        previous = current;
        if (stableFrames === 4) resolve();
        else requestAnimationFrame(sample);
      };
      requestAnimationFrame(sample);
    }));
    const position = await page.evaluate(() => {
      window.scrollBy({ top: 400, behavior: 'instant' });
      return scrollY;
    });
    await page.goBack({ waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(new URL('/company/imerit/', baseURL).href);
    await page.goForward({ waitUntil: 'domcontentloaded' });
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    await expect(heading).not.toBeFocused();
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(position);
  } finally {
    releaseImage();
  }
});

test('an initial section route respects keyboard focus established while its evidence loads', async ({ page, baseURL }) => {
  let releaseEvidence;
  const evidenceGate = new Promise(resolve => { releaseEvidence = resolve; });
  await page.route('**/presentation/company-imerit.*.json', async route => {
    await evidenceGate;
    await route.continue();
  });
  try {
    await openNativeSourceLedger(page, baseURL);
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'loading');
    await page.keyboard.press('Tab');
    const skip = page.getByRole('link', { name: 'Skip to content', exact: true });
    await expect(skip).toBeFocused();
    const position = await page.evaluate(() => scrollY);
    releaseEvidence();
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    await expect(skip).toBeFocused();
    expect(await page.evaluate(() => scrollY)).toBe(position);
  } finally {
    releaseEvidence();
  }
});

test('a fresh profile bookmark scrolls to the source heading without setting focus', async ({ page }) => {
  await page.goto(imeritLedger);
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  await expectSourceHeadingInView(page.getByRole('heading', { name: 'All sources', exact: true }));
  await expect(page.locator('body')).toBeFocused();
});
