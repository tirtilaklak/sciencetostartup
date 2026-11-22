const { execFileSync } = require('node:child_process');
const { expect, test } = require('@playwright/test');

test.use({ viewport: { width: 390, height: 844 } });

const isIndex = url => /\/presentation\/full-search\.[^/]+\.json$/.test(new URL(url).pathname);
const query = '  MerCor  ';
const group = 'Expert data & evaluation';
const groupSlug = 'expert-data-evaluation';
const stage = 'repeatable_commercial_evidence';

const search = page => page.getByRole('searchbox', { name: 'Search', exact: true });
const cards = page => page.locator('#company-cards');
const count = page => page.locator('#result-count');
const compareATeam = page => cards(page).getByRole('checkbox', { name: 'Compare A.Team', exact: true });
const retry = page => cards(page).getByRole('button', { name: 'Try again', exact: true });
const fallback = page => cards(page).getByRole('link', { name: 'browse the plain company list' });
const clear = page => page.getByRole('button', { name: 'Clear', exact: true });
const exportButton = page => page.locator('#download-csv');

async function holdFirstIndexRequest(page, unavailable) {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let requests = 0;
  await page.route(isIndex, async route => {
    const attempt = ++requests;
    if (attempt === 1) await gate;
    if (unavailable(attempt)) await route.fulfill({ status: 503 });
    else await route.continue();
  });
  return { release, requests: () => requests };
}

async function openCompanies(page) {
  await page.goto('/explore/#companies');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
}

async function tabTo(page, target) {
  await expect(target).toBeVisible();
  for (let step = 0; step < 30; step++) {
    if (await target.evaluate(node => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}

async function expectFailedSearch(page) {
  await expect(count(page)).toHaveText('Search could not load.');
  await expect(cards(page)).not.toHaveAttribute('aria-busy', 'true');
  await expect(cards(page).getByRole('alert')).toBeVisible();
}

function failedIndexRequest(page, offline) {
  if (offline) return page.waitForEvent('requestfailed', request => isIndex(request.url()));
  return page.waitForResponse(response => isIndex(response.url()) && response.status() === 503);
}

async function expectResults(page, ids) {
  await expect(count(page)).toHaveText(new RegExp(`^Showing ${ids.length} of \\d+ companies$`));
  const companyCards = cards(page).locator('[data-company-card]:visible');
  expect(await companyCards.evaluateAll(nodes => nodes.map(node => node.dataset.companyCard))).toEqual(ids);
}

for (const offline of [false, true]) {
  test(`${offline ? 'Offline' : 'HTTP 503'} company search keeps keyboard focus through failure and retry`, async ({ page, context }) => {
    const index = await holdFirstIndexRequest(page, attempt => !offline && attempt <= 2);
    try {
      await openCompanies(page);
      await tabTo(page, search(page));
      await page.keyboard.type(query);
      await expect.poll(index.requests).toBe(1);
      await expect(cards(page)).toHaveAttribute('aria-busy', 'true');
      const checkbox = compareATeam(page);
      await tabTo(page, checkbox);

      const first = failedIndexRequest(page, offline);
      if (offline) await context.setOffline(true);
      index.release();
      await first;
      await expectFailedSearch(page);
      await expect(checkbox).toHaveCount(0);
      await expect.soft(search(page)).toBeFocused({ timeout: 1500 });
      await expect(search(page)).toHaveValue(query);

      await tabTo(page, retry(page));
      const second = failedIndexRequest(page, offline);
      await page.keyboard.press('Enter');
      await second;
      await expectFailedSearch(page);
      await expect.soft(retry(page)).toBeFocused({ timeout: 1500 });
      await page.keyboard.press('Tab');
      await expect.soft(fallback(page)).toBeFocused({ timeout: 1500 });

      if (offline) await context.setOffline(false);
      await page.keyboard.press('Shift+Tab');
      await retry(page).press('Enter');
      await expectResults(page, ['mercor']);
      await expect(search(page)).toHaveValue(query);
      await expect(search(page)).toBeFocused();
    } finally {
      index.release();
      if (offline) await context.setOffline(false);
    }
  });
}

test('a failed company search leaves focus in the global search, and Clear works during the outage', async ({ page }) => {
  const index = await holdFirstIndexRequest(page, () => true);
  try {
    await openCompanies(page);
    await search(page).fill(query);
    await expect(cards(page)).toHaveAttribute('aria-busy', 'true');
    await tabTo(page, compareATeam(page));
    await page.keyboard.press('ControlOrMeta+k');
    const globalSearch = page.locator('#site-search-input');
    await expect(globalSearch).toBeFocused();
    index.release();
    await expect(count(page)).toHaveText('Search could not load.');
    await expect(globalSearch).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.locator('#site-search')).not.toBeVisible();

    await tabTo(page, clear(page));
    await page.keyboard.press('Enter');
    await expect(search(page)).toHaveValue('');
    await expect(search(page)).toBeFocused();
    await expect(clear(page)).toBeHidden();
    await expect(compareATeam(page)).toBeVisible();
    expect(index.requests()).toBe(1);
  } finally {
    index.release();
  }
});

async function selectCriteria(page) {
  await page.locator('#category').selectOption(group);
  await page.locator('.more-filters summary').click();
  await page.locator('#stage').selectOption(stage);
  await page.locator('#financial-only').check();
  await page.locator('#work-only').check();
  await page.locator('#sort').selectOption('name-desc');
}

async function expectCriteria(page) {
  await expect(search(page)).toHaveValue(query);
  await expect(page.locator('#category')).toHaveValue(group);
  await expect(page.locator('#stage')).toHaveValue(stage);
  await expect(page.locator('#financial-only')).toBeChecked();
  await expect(page.locator('#work-only')).toBeChecked();
  await expect(page.locator('#sort')).toHaveValue('name-desc');
}

async function downloadedCompanyIds(page) {
  const pending = page.waitForEvent('download');
  await exportButton(page).press('Enter');
  const file = await (await pending).path();
  return JSON.parse(execFileSync('python3', ['-c', [
    'import csv, json, sys',
    'with open(sys.argv[1], encoding="utf-8-sig", newline="") as source:',
    '    print(json.dumps([row["company_id"] for row in csv.DictReader(source)]))',
  ].join('\n'), file], { encoding: 'utf8' }));
}

test('failed filters and CSV reflect the current criteria and recovery exports the matching IDs', async ({ page }) => {
  const index = await holdFirstIndexRequest(page, attempt => attempt === 1);
  try {
    await openCompanies(page);
    await search(page).fill(query);
    await selectCriteria(page);
    const labels = [
      'Search: MerCor',
      'Expert data & AI testing',
      'Delivery evidence: Repeat business',
      'Revenue figures',
      'Has paid work or a career page',
      'Name Z–A',
    ];
    await expect(cards(page)).toHaveAttribute('aria-busy', 'true');
    const chips = page.locator('#active-filters .active-filter');
    expect.soft(await chips.allTextContents()).toEqual(labels);
    index.release();
    await expectFailedSearch(page);
    await expectCriteria(page);
    expect.soft(await chips.allTextContents()).toEqual(labels);
    expect.soft(await clear(page).isVisible()).toBe(true);

    const origin = page.url();
    await page.goto('/explore/#downloads');
    await expect(exportButton(page)).toBeVisible();
    const exportLabel = await exportButton(page).innerText();
    expect.soft(exportLabel).toMatch(/CSV unavailable/i);
    expect.soft(exportLabel).not.toMatch(/\b\d+ rows?\b/);
    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(origin);
    await expectCriteria(page);
    await retry(page).press('Enter');
    await expectResults(page, []);
    await expectCriteria(page);
    await expect(chips).toHaveText(labels);

    await page.goto('/explore/#downloads');
    await expect(exportButton(page)).toContainText('0 rows');
    expect(await downloadedCompanyIds(page)).toEqual([]);

    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(origin);
    if (await page.locator('.more-filters').getAttribute('open') === null) {
      await page.locator('.more-filters summary').click();
    }
    await page.locator('#stage').selectOption('');
    await expectResults(page, ['mercor']);
    await page.goto('/explore/#downloads');
    await expect(exportButton(page)).toContainText('1 row · CSV');
    expect(await downloadedCompanyIds(page)).toEqual(['mercor']);
  } finally {
    index.release();
  }
});

const cold = test.extend({
  launchOptions: [async ({ launchOptions, browserName }, use) => {
    await use(browserName === 'firefox' ? {
      ...launchOptions,
      firefoxUserPrefs: {
        ...launchOptions.firefoxUserPrefs,
        'browser.sessionhistory.max_total_viewers': 0,
        'dom.navigation.webidl.enabled': false,
      },
    } : launchOptions);
  }, { scope: 'worker' }],
});

cold.describe('company search handoff across a fresh document', () => {
  cold.skip(({ browserName, isMobile }) => browserName === 'webkit' || isMobile, 'Use desktop Chromium or Firefox with the history cache disabled');

  for (const recovered of [false, true]) {
    cold(`native Companies receives the query and group and cold Back restores ${recovered ? 'Search' : 'the fallback link'}`, async ({ page }) => {
      const index = await holdFirstIndexRequest(page, attempt => attempt === 1 || !recovered);
      try {
        await openCompanies(page);
        await search(page).fill(query);
        await selectCriteria(page);
        index.release();
        await expectFailedSearch(page);
        const origin = page.url();
        const firstDocument = await page.evaluate(() => performance.timeOrigin);
        await tabTo(page, fallback(page));
        await page.keyboard.press('Enter');

        const nativeSearch = page.getByRole('searchbox', { name: 'Search companies' });
        await expect(nativeSearch).toBeVisible();
        expect(new URL(page.url()).pathname).toBe('/companies/');
        expect.soft(Object.fromEntries(new URL(page.url()).searchParams)).toEqual({ q: query, group: groupSlug });
        expect.soft(await nativeSearch.inputValue()).toBe(query);
        expect.soft(await page.getByRole('combobox', { name: 'Business group' }).inputValue()).toBe(groupSlug);
        expect.soft(await page.locator('#company-count').innerText()).toBe('1 company');
        expect.soft(await page.locator('[data-company]:visible').evaluateAll(nodes => nodes.map(node => node.dataset.company))).toEqual(['mercor']);
        await nativeSearch.fill('Mercor');
        await expect(page).toHaveURL(url => url.searchParams.get('q') === 'Mercor');

        await page.goBack({ waitUntil: 'commit' });
        await expect(page).toHaveURL(origin);
        await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
        expect(await page.evaluate(() => performance.timeOrigin)).not.toBe(firstDocument);
        expect(await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type)).toBe('back_forward');
        await expectCriteria(page);
        if (recovered) {
          await expectResults(page, []);
          await expect(search(page)).toBeFocused();
          await page.keyboard.press('Tab');
          await expect(page.locator('#category')).toBeFocused();
        } else {
          await expectFailedSearch(page);
          await expect(fallback(page)).toBeFocused();
          await page.keyboard.press('Shift+Tab');
          await expect(retry(page)).toBeFocused();
        }
      } finally {
        index.release();
      }
    });
  }
});
