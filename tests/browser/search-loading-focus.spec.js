const { test, expect } = require('@playwright/test');

async function holdSearchRequest(page, resource) {
  let resume;
  const released = new Promise(resolve => { resume = resolve; });
  await page.route(resource, async route => {
    await released;
    await route.continue();
  });
  return resume;
}

async function openSearchByKeyboard(page, path) {
  await page.goto(path);
  const opener = page.locator('#home-search-open');
  await opener.focus();
  await page.keyboard.press('Enter');

  const dialog = page.locator('#home-search');
  const input = dialog.getByRole('combobox', { name: 'Search the guide' });
  await expect(input).toBeFocused();
  return { dialog, input, opener };
}

for (const path of ['/', '/companies/']) {
  test(`Search script arrival preserves keyboard focus on Close at ${path}`, async ({ page }) => {
    const resume = await holdSearchRequest(page, '**/home-search.js');
    try {
      const { dialog, input, opener } = await openSearchByKeyboard(page, path);
      const close = dialog.getByRole('button', { name: 'Close search' });
      await page.keyboard.press('Tab');
      await expect(close).toBeFocused();

      resume();
      await expect(input).toHaveAttribute('aria-expanded', 'true');
      await expect(close).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(dialog).toBeHidden();
      await expect(opener).toBeFocused();
    } finally {
      resume();
    }
  });
}

for (const { path, label, steps, destination, viewport } of [
  { path: '/', label: 'Browse companies', steps: 2, destination: '/companies/', viewport: { width: 320, height: 178 } },
  { path: '/companies/', label: 'Browse paid work', steps: 3, destination: '/work/' },
]) {
  test(`Search index arrival preserves keyboard focus on ${label}`, async ({ page }) => {
    if (viewport) await page.setViewportSize(viewport);
    const resume = await holdSearchRequest(page, '**/presentation/search.*.json');
    try {
      const { dialog, input } = await openSearchByKeyboard(page, path);
      const fallback = dialog.getByRole('link', { name: label, exact: true });
      for (let step = 0; step < steps; step++) await page.keyboard.press('Tab');
      await expect(fallback).toBeFocused();
      await expect(fallback).toBeInViewport({ ratio: 0.99 });

      resume();
      await expect(input).toHaveAttribute('aria-expanded', 'true');
      await expect(fallback).toBeFocused();
      await expect(fallback).toBeInViewport({ ratio: 0.99 });
      await page.keyboard.press('Enter');
      await expect(page).toHaveURL(new URL(destination, page.url()).href);
    } finally {
      resume();
    }
  });
}
