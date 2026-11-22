const { test, expect } = require('@playwright/test');

function compareCell(page, row, company) {
  return page.locator(`[data-comparison-row="${row}"] [data-comparison-company="${company}"]`);
}

test('Back returns to the exact Compare link when two links open the same profile', async ({ page }) => {
  const compare = '/explore/#compare/mercor/a-team/sama';
  await page.goto(compare);
  const header = page.locator('.comparison-table thead').getByRole('link', { name: 'Mercor', exact: true });
  const profile = compareCell(page, 'Explore', 'mercor').getByRole('link', { name: 'Full profile & sources' });
  const work = compareCell(page, 'Paid work', 'mercor').getByRole('link', { name: 'Pay & requirements' });
  await expect(header).toHaveAttribute('href', '#company/mercor');
  await expect(profile).toHaveAttribute('href', '#company/mercor');

  for (const [origin, destination] of [[profile, '#company/mercor'], [header, '#company/mercor'], [work, '#company/mercor/work']]) {
    await origin.scrollIntoViewIfNeeded();
    await origin.press('Enter');
    await expect(page).toHaveURL('/explore/' + destination);
    await expect(page.locator('[data-profile-company="mercor"]')).toBeVisible();
    if (origin === work) await expect(page.locator('#profile-work')).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(compare);
    await expect(origin).toBeFocused();
    await expect(origin).toBeInViewport();
  }
});

test('fresh Back from native financing evidence restores More, the Compare pair and keyboard focus', async ({ page }) => {
  await page.addInitScript(() => {
    addEventListener('unload', () => {});
    window.compareTestDocument = Math.random().toString();
  });
  const compare = '/explore/#compare/a-team/sama/mercor';
  await page.goto(compare);
  const headings = page.locator('.comparison-table thead .card-head a');
  await expect(headings).toHaveText(['A.Team', 'Sama', 'Mercor']);
  const changePair = page.locator('.mobile-column-options summary');
  const mobile = await changePair.isVisible();
  if (mobile) {
    await changePair.press('Enter');
    await page.getByRole('button', { name: 'Sama + Mercor', exact: true }).press('Enter');
  }

  const extra = page.locator('#comparison-extra');
  const more = page.locator('[data-compare-extra]');
  const evidence = compareCell(page, 'Funding & investors', 'mercor').getByRole('link', { name: 'Read Mercor’s financing evidence' });
  await expect(extra).toBeHidden();
  await more.press('Enter');
  await expect(more).toHaveAttribute('aria-expanded', 'true');
  await expect(evidence).toHaveAttribute('href', '/company/mercor/#financial-record');
  await evidence.scrollIntoViewIfNeeded();
  const initialDocument = await page.evaluate(() => window.compareTestDocument);
  await evidence.press('Enter');
  await expect(page).toHaveURL('/company/mercor/#financial-record');
  await expect(page.locator('#financial-record')).toHaveJSProperty('open', true);

  for (let visit = 0; visit < 2; visit++) {
    await page.goBack({ waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(compare);
    expect(await page.evaluate(() => window.compareTestDocument)).not.toBe(initialDocument);
    await expect(headings).toHaveText(['A.Team', 'Sama', 'Mercor']);
    await expect(more).toHaveAttribute('aria-expanded', 'true');
    await expect(extra).toBeVisible();
    if (mobile) await expect(headings.first()).toBeHidden();
    await expect(evidence).toBeFocused();
    await expect(evidence).toBeInViewport();

    await page.goForward({ waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL('/company/mercor/#financial-record');
    await expect(page.locator('#financial-record')).toHaveJSProperty('open', true);
  }
});

test('Compare work links describe career pages, archived records and paid networks accurately', async ({ page }) => {
  await page.goto('/explore/#compare/sama/elorian/mercor');
  const links = ['sama', 'elorian', 'mercor'].map(id => compareCell(page, 'Paid work', id).locator('a'));
  await expect(links[0]).toHaveText('See career links');
  await expect(links[1]).toHaveText('See work records');
  await expect(links[2]).toHaveText('Pay & requirements');
  await expect(compareCell(page, 'Paid work', 'mercor')).toContainText('Networks and programs');

  for (const [index, id, routeId] of [
    [0, 'sama', 'sama.work.company-careers'],
    [1, 'elorian', 'elorian.work.model-safety'],
  ]) {
    const link = links[index];
    await expect(link).toHaveAttribute('href', `#company/${id}/work`);
    await link.press('Enter');
    await expect(page).toHaveURL(`/explore/#company/${id}/work`);
    const work = page.locator('#profile-work');
    await expect(work).toContainText('No confirmed paid listing');
    await expect(work.locator(`[data-work-route="${routeId}"]`)).toBeVisible();
    await page.goBack();
    await expect(link).toBeFocused();
  }
});
