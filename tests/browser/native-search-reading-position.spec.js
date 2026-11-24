const { test, expect } = require('@playwright/test');

test.use({ reducedMotion: 'reduce' });

function settledScrollY(page) {
  return page.evaluate(() => new Promise(resolve => {
    let previous = scrollY, stableFrames = 0;
    function check() {
      stableFrames = scrollY === previous ? stableFrames + 1 : 0;
      previous = scrollY;
      if (stableFrames >= 8) resolve(scrollY);
      else requestAnimationFrame(check);
    }
    requestAnimationFrame(check);
  }));
}

test('native Search returns to document focus and preserves its reading position on dismissal', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/research/');
  const opener = page.locator('#home-search-open');
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const close = dialog.getByRole('button', { name: 'Close search' });
  const body = page.locator('body');

  await expect(opener).toHaveAttribute('aria-expanded', 'false');
  await expect(body).toBeFocused();
  await page.keyboard.press('PageDown');
  await settledScrollY(page);
  await page.keyboard.press('PageDown');
  const readingOffset = await settledScrollY(page);
  expect(readingOffset).toBeGreaterThan(600);
  await expect(opener).not.toBeInViewport();

  for (const dismiss of [() => page.keyboard.press('Escape'), () => close.click()]) {
    await page.keyboard.press('Control+k');
    await expect(input).toBeFocused();
    expect(await settledScrollY(page)).toBe(readingOffset);
    await dismiss();
    await expect(dialog).toBeHidden();
    await expect(opener).toHaveAttribute('aria-expanded', 'false');
    await expect(body).toBeFocused();
    expect(await settledScrollY(page)).toBe(readingOffset);
  }

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  expect(await settledScrollY(page)).toBe(readingOffset);

  await page.keyboard.press('Control+k');
  await input.fill('AI data research');
  await dialog.locator('a[role="option"][href="/research/"]').click();
  const title = page.getByRole('heading', { name: 'AI data research', exact: true });
  await expect(dialog).toBeHidden();
  await expect(title).toBeFocused();
  await expect(title).toBeInViewport();

  await opener.click();
  await expect(input).toBeFocused();
  await close.click();
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
  await expect(opener).toBeInViewport();
});
