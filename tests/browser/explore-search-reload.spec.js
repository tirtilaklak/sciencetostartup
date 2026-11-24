const { test, expect } = require('@playwright/test');

for (const classicHistory of [false, true]) {
  test(`Back after reloading an Explore Search result with ${classicHistory ? 'classic' : 'default'} history`, async ({ page, isMobile }) => {
    const origin = '/explore/#market';
    const destination = '/explore/#company/mercor/products';
    const query = 'APEX-Agents';
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const input = dialog.getByRole('combobox');
    const result = dialog.getByRole('option', { name: 'APEX-Agents From Mercor', exact: true });
    const product = page.locator('[data-profile-product="APEX-Agents"] h3');
    const products = page.getByRole('heading', { name: 'Products and services', exact: true });
    const reload = async () => {
      await page.reload({ waitUntil: 'domcontentloaded' });
      await expect(page.locator('html')).toHaveAttribute('data-app', 'ready');
      await expect(products).toBeVisible();
    };
    const expectSearchRestored = async () => {
      await expect(page).toHaveURL(origin);
      await expect(input).toBeFocused();
      await expect(input).toHaveValue(query);
      await expect(result).toHaveAttribute('aria-selected', 'true');
      await expect(input).toHaveAttribute('aria-activedescendant', await result.getAttribute('id'));
    };

    if (classicHistory) {
      await page.addInitScript(() => Object.defineProperty(window, 'navigation', { value: undefined }));
    }

    // Leave an older entry for the same product URL before opening it from Search.
    await page.goto(destination);
    await expect(products).toBeVisible();
    await page.evaluate(() => { location.hash = '#market'; });
    await expect(page.locator('#market-view')).toBeVisible();
    await page.locator('#site-search-open').click();
    await input.fill(query);
    await expect(result).toBeVisible();
    if (isMobile) await result.tap();
    else {
      await input.press('ArrowDown');
      await input.press('Enter');
    }
    await expect(page).toHaveURL(destination);
    await expect(product).toBeFocused();
    await reload();
    await expect(dialog).toBeHidden();
    await page.goBack({ waitUntil: 'commit' });
    await expectSearchRestored();

    await page.goBack({ waitUntil: 'commit' });
    await expect(page).toHaveURL(destination);
    await reload();
    await page.goForward({ waitUntil: 'commit' });
    await expect(page.locator('#market-view')).toBeVisible();
    await expect(dialog).toBeHidden();

    await page.goForward({ waitUntil: 'commit' });
    await expect(products).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expectSearchRestored();
    await dialog.getByRole('button', { name: 'Close search' }).click();
    await expect(dialog).toBeHidden();

    await page.goForward({ waitUntil: 'commit' });
    await expect(products).toBeVisible();
    await page.goBack({ waitUntil: 'commit' });
    await expect(page.locator('#market-view')).toBeVisible();
    await expect(dialog).toBeHidden();
  });
}
