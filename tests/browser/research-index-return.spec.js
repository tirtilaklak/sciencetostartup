const { test, expect } = require('@playwright/test');

const datasets = '/research/datasets/';
const filtered = datasets + '?q=hh_rlhf';
const record = datasets + 'dataset.hh_rlhf/';

test('cold Back resumes the Research index Tab order only after an activated result', async ({ page, isMobile }) => {
  await page.setViewportSize(isMobile ? { width: 320, height: 740 } : { width: 1440, height: 900 });
  await page.addInitScript(path => {
    if (location.pathname !== path) return;
    addEventListener('unload', () => {});
  }, datasets);

  await page.goto('/research/');
  await page.locator('section[aria-labelledby="browse"] a[href="/research/datasets/"]').press('Enter');
  await expect(page).toHaveURL(datasets);
  const query = page.getByRole('searchbox', { name: 'Search records' });
  const row = page.locator('[data-record-id="dataset.hh_rlhf"]');
  const link = row.getByRole('link', { name: 'HH-RLHF', exact: true });
  const evidence = row.locator('td[data-label="Evidence"] a');
  await query.fill('hh_rlhf');
  await expect(page).toHaveURL(filtered);
  for (let tab = 0; tab < 7; tab++) {
    await page.keyboard.press('Tab');
    if (await link.evaluate(node => node === document.activeElement)) break;
  }
  await expect(link).toBeFocused();
  await expect(link).toBeInViewport({ ratio: 0.98 });
  await page.evaluate(() => document.fonts.ready);
  const top = await link.evaluate(node => node.getBoundingClientRect().top);

  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(record);
  await expect(page.getByRole('heading', { name: 'HH-RLHF', level: 1 })).toBeVisible();

  for (const visit of [1, 2]) {
    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(filtered);
    await expect(query).toHaveValue('hh_rlhf');
    await expect(page.locator('[data-index-count]')).toHaveText('2 of 154 records shown');
    expect(await page.evaluate(() => performance.getEntriesByType('navigation')[0].type)).toBe('back_forward');
    await expect(link).toBeFocused();
    await expect(link).toBeInViewport({ ratio: 0.98 });
    await expect.poll(() => link.evaluate(
      (node, originalTop) => Math.abs(node.getBoundingClientRect().top - originalTop), top
    )).toBeLessThanOrEqual(2);
    if (visit === 1) {
      await page.goForward({ waitUntil: 'commit' });
      await expect(page).toHaveURL(record);
    }
  }
  await page.keyboard.press('Tab');
  await expect(evidence).toBeFocused();

  await page.goto(record);
  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(filtered);
  await expect(query).toHaveValue('hh_rlhf');
  await expect(page.locator('body')).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
});
