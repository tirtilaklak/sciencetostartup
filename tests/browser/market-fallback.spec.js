const { test, expect } = require('@playwright/test');

test.describe('Explore without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  for (const fragment of ['', '#work', '#business-health']) {
    test(`${fragment || 'base URL'} starts at the skip link and reaches the plain directory`, async ({ page }) => {
      await page.goto('/explore/' + fragment);

      const fallback = page.locator('noscript .availability-notice');
      await expect(fallback.getByRole('heading', { name: 'ScienceToStartup: the AI data field guide' })).toBeInViewport();
      await page.keyboard.press('Tab');
      const skip = page.getByRole('link', { name: 'Skip to content' });
      await expect(skip).toBeFocused();
      await expect(skip).toBeInViewport();
      if (fragment === '#business-health') await expect(page.locator('#business-health')).toHaveCount(0);
      await page.keyboard.press('Enter');
      await expect(page.locator('#main')).toBeFocused();

      await page.keyboard.press('Tab');
      await expect(fallback.getByRole('link', { name: 'Search the plain guide' })).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(fallback.getByRole('link', { name: 'Company list' })).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(/\/companies\/$/);
    });
  }
});

test('enhanced Market exposes the fragment and focuses the visible heading', async ({ page }) => {
  await page.goto('/explore/#business-health');

  const dashboard = page.locator('#business-health');
  const heading = dashboard.getByRole('heading', { name: 'Revenue & growth.' });
  await expect(heading).toBeFocused();
  await expect(heading).toBeInViewport();
  await expect(dashboard.getByRole('tablist', { name: 'Revenue views' }).getByRole('tab')).toHaveCount(3);
  await page.keyboard.press('Tab');
  await expect(dashboard.locator(':focus')).toBeVisible();
});
