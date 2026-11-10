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
  await page.locator('.topbar a[data-nav="work"]').click();
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
    await expect(page.getByRole('heading', { name: 'This company’s evidence could not load.' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Read the plain company page' })).toHaveAttribute('href', '/company/mercor/');
    expect(await page.evaluate(() => window.APP_HEALTH_READY)).toBeUndefined();
    await page.evaluate(() => { window.testRendererFault = ''; });
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
    expect(await page.evaluate(() => window.ScienceProfileDetails.buildId)).toBe(await page.evaluate(() => window.APP_BUILD_ID));
    await page.getByRole('tab', { name: 'Business', exact: true }).click();
    await expect(page.locator('#profile-pane-business .offering-card').first()).toBeVisible();
  });
}
