const { expect, test } = require('@playwright/test');

test.use({ reducedMotion: 'reduce' });

async function openExplore(page, fragment) {
  const opener = page.locator('#site-search-open');
  await page.goto(`/explore/${fragment}`);
  await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
  if (fragment === '#market') await expect(page.locator('#bh-ledger .bh-ledger-row').first()).toBeVisible();
  else await expect(page.locator('#profile-view h1')).toHaveText('Mercor');
  return opener;
}

async function settledScroll(page) {
  return page.evaluate(() => new Promise(resolve => {
    let previous = scrollY;
    let stationary = 0;
    function frame() {
      stationary = scrollY === previous ? stationary + 1 : 0;
      previous = scrollY;
      if (stationary >= 8) resolve(scrollY);
      else requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }));
}

async function pageDownTwice(page) {
  let y = await settledScroll(page);
  for (let step = 0; step < 2; step++) {
    await page.keyboard.press('PageDown');
    await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(y);
    y = await settledScroll(page);
  }
  await expect(page.locator('body')).toBeFocused();
  return y;
}

const readingViews = [
  ['#market', 320, 720, 'sticky'],
  ['#company/mercor', 320, 720, 'static'],
  ['#market', 390, 844, 'sticky'],
  ['#company/mercor', 390, 844, 'sticky'],
  ['#market', 390, 480, 'static'],
];

for (const [fragment, width, height, mastheadPosition] of readingViews) {
  test(`Escape preserves the Explore reading position and next Tab at ${width}×${height} on ${fragment}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const opener = await openExplore(page, fragment);
    await expect(page.locator('body > header')).toHaveCSS('position', mastheadPosition);
    const before = await pageDownTwice(page);
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });

    await page.keyboard.press('ControlOrMeta+k');
    await expect(dialog.getByRole('combobox')).toBeFocused();
    expect(await settledScroll(page)).toBe(before);
    await page.keyboard.press('Escape');
    await expect(opener).toHaveAttribute('aria-expanded', 'false');
    await expect(dialog).toBeHidden();
    await expect(page.locator('body')).toBeFocused();
    expect(await settledScroll(page)).toBe(before);

    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
    expect(await settledScroll(page)).toBe(before);
  });
}

test('Explore Search restores a focused link after the shortcut and the masthead after a pointer activation', async ({ page, isMobile }) => {
  await page.setViewportSize({ width: 390, height: 480 });
  const opener = await openExplore(page, '#market');
  const research = page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Research' });
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const close = dialog.getByRole('button', { name: 'Close search' });

  await research.focus();
  await page.keyboard.press('ControlOrMeta+k');
  await expect(input).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(opener).toHaveAttribute('aria-expanded', 'false');
  await expect(research).toBeFocused();

  if (isMobile) await opener.tap();
  else await opener.click();
  await expect(input).toBeFocused();
  if (isMobile) await close.tap();
  else await close.click();
  await expect(opener).toHaveAttribute('aria-expanded', 'false');
  await expect(opener).toBeFocused();
});

test('choosing a product from the Explore shortcut lands on the result and Back resumes Search', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await openExplore(page, '#market');
  await pageDownTwice(page);
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const result = dialog.getByRole('option', { name: 'APEX-Agents From Mercor', exact: true });

  await page.keyboard.press('ControlOrMeta+k');
  await input.fill('APEX-Agents');
  await expect(result).toBeVisible();
  await input.press('ArrowDown');
  await input.press('Enter');
  await expect(page).toHaveURL('/explore/#company/mercor/products');
  await expect(page.locator('[data-profile-product="APEX-Agents"] h3')).toBeFocused();
  await expect(dialog).toBeHidden();

  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL('/explore/#market');
  await expect(input).toBeFocused();
  await expect(input).toHaveValue('APEX-Agents');
  await expect(result).toHaveAttribute('aria-selected', 'true');
});
