const { expect, test } = require('@playwright/test');

test.use({ viewport: { width: 390, height: 844 } });

async function deferSearchIndex(page) {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/presentation/full-search.*.json', async route => {
    await gate;
    await route.continue();
  });
  await page.goto('/explore/#companies');
  await expect(page.locator('html')).toHaveAttribute('data-view-state', 'ready');
  return release;
}

async function tabTo(page, target) {
  for (let step = 0; step < 30; step++) {
    if (await target.evaluate(node => node === document.activeElement)) return;
    await page.keyboard.press('Tab');
  }
  await expect(target).toBeFocused();
}

async function typePendingQuery(page, query) {
  await tabTo(page, page.locator('#search'));
  await page.keyboard.type(query);
  await expect(page.locator('#company-cards')).toHaveAttribute('aria-busy', 'true');
  const checkbox = page.getByRole('checkbox', { name: 'Compare A.Team', exact: true });
  await tabTo(page, checkbox);
  return checkbox;
}

test('a surviving Compare checkbox keeps focus and completes a Space press across the update', async ({ page, context }) => {
  const release = await deferSearchIndex(page);
  try {
    const sama = page.getByRole('checkbox', { name: 'Compare Sama', exact: true });
    await sama.check();
    await page.locator('#search').focus();
    const checkbox = await typePendingQuery(page, 'A Team');
    await page.keyboard.down('Space');
    release();
    await expect(page.locator('#result-count')).toHaveText(/Showing \d+ of 39 companies/);
    await expect(checkbox).toBeFocused();
    await page.keyboard.up('Space');
    await expect(checkbox).toBeChecked();
    await expect(page.locator('#tray-text')).toHaveText(/2 of 3 selected: Sama and A\.Team/);
    await page.keyboard.press('Space');
    await expect(checkbox).not.toBeChecked();
    await expect(page.locator('#tray-text')).toHaveText('1 of 3 selected: Sama');

    await page.keyboard.press('Tab');
    const work = page.locator('[data-company-card="a-team"]').getByRole('link', { name: 'Work routes' });
    await expect(work).toBeFocused();
    const popup = context.waitForEvent('page');
    await work.click({ modifiers: ['ControlOrMeta'] });
    const opened = await popup;
    await expect(opened).toHaveURL(/#company\/a-team\/work$/);
    await expect(page).toHaveURL(/#companies$/);
    await opened.close();
  } finally {
    release();
  }
});

test('a removed result returns keyboard focus to company search', async ({ page }) => {
  const release = await deferSearchIndex(page);
  try {
    const checkbox = await typePendingQuery(page, 'WorldSim');
    release();
    await expect(page.locator('#result-count')).toHaveText('Showing 1 of 39 companies');
    await expect(checkbox).toHaveCount(0);
    await expect(page.locator('#search')).toBeFocused();
    await expect(page.locator('#search')).toHaveValue('WorldSim');
    await page.keyboard.press('Tab');
    await expect(page.locator('#category')).toBeFocused();
  } finally {
    release();
  }
});

test('a completed search leaves focus in the global search opened by keyboard', async ({ page }) => {
  const release = await deferSearchIndex(page);
  try {
    await typePendingQuery(page, 'A Team');
    await page.keyboard.press('ControlOrMeta+k');
    const globalSearch = page.locator('#site-search-input');
    await expect(globalSearch).toBeFocused();
    release();
    await expect(page.locator('#result-count')).toHaveText(/Showing \d+ of 39 companies/);
    await expect(globalSearch).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.locator('#site-search')).not.toBeVisible();
  } finally {
    release();
  }
});
