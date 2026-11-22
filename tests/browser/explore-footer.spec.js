const { test, expect } = require('@playwright/test');

test('Explore exposes one sitewide footer as the view changes', async ({ page }) => {
  await page.goto('/explore/#work');
  const main = page.getByRole('main');
  const footer = page.getByRole('contentinfo');
  const nav = footer.getByRole('navigation', { name: 'Research and information', exact: true });
  const links = ['About', 'Historical company data', 'Research data', 'Corrections', 'Disclosures'];

  for (const view of ['work', 'compare', 'method', 'work']) {
    await page.evaluate(name => { location.hash = name; }, view);
    await expect(main.locator(`#${view}-view`)).toBeVisible();
    await expect(main).toHaveCount(1);
    await expect(footer).toHaveCount(1);
    await expect(nav.getByRole('link')).toHaveText(links);
  }

  await nav.getByRole('link', { name: 'Research data', exact: true }).press('Tab');
  await expect(nav.getByRole('link', { name: 'Corrections', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/method\/#corrections$/);
  await expect(page.locator('#corrections')).toBeVisible();
});
