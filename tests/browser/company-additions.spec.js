const { test, expect } = require('@playwright/test');
const registry = require('../../data/current-companies.json');
const canonical = require('../../data/canonical.json');

test('current company additions can be found and linked with their attribution', async ({ page, baseURL }) => {
  for (const entry of registry.entries) {
    await page.goto('/companies/?q=' + encodeURIComponent(entry.name));
    await expect(page.locator('#company-filters')).toBeVisible();
    await expect(page.locator('.directory-company:visible')).toHaveCount(1);
    const card = page.locator('.directory-company[data-company="' + entry.entity_id + '"]');
    await expect(card).toBeVisible();
    await expect(card).toContainText(entry.wikipedia.description);
    await expect(card.locator('a[href="' + entry.wikipedia.revision_url + '"]')).toBeVisible();
    await expect(card.locator('a[href="' + entry.wikipedia.license_url + '"]')).toBeVisible();
    const path = '/company/' + entry.entity_id + '/';
    await expect(card.locator('a[href$="' + path + '"]')).toHaveAttribute('href', 'https://sciencetostartup.com' + path);
    // Native links declare the public canonical URL; test its exact artifact here.
    await page.goto(path);
    await expect(page).toHaveURL(new URL(path, baseURL).href);
    const supplement = page.locator('[data-current-company="' + entry.entity_id + '"]');
    await expect(supplement).toContainText(entry.wikipedia.description);
    await expect(supplement).toContainText('Wikipedia contributors');
    if (entry.parent_company) {
      await expect(supplement).toContainText('Parent company: ' + entry.parent_company.name);
      await expect(supplement).toContainText('DataForce by TransPerfect');
    }
  }
});

test('current additions and their sources remain available without JavaScript', async ({ browser, baseURL }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL });
  try {
    const page = await context.newPage();
    await page.goto('/companies/');
    await expect(page.locator('.directory-company')).toHaveCount(canonical.companies.length + registry.entries.length);
    await expect(page.locator('#company-filters')).not.toBeVisible();
    for (const entry of registry.entries) {
      const card = page.locator('.directory-company[data-company="' + entry.entity_id + '"]');
      await expect(card).toBeVisible();
      await expect(card).toContainText(entry.wikipedia.description);
      const details = card.locator('details.company-current-facts');
      await details.locator('summary').click();
      for (const source of entry.sources) {
        await expect(details.locator('a[href="' + source.url + '"]')).toBeVisible();
      }
    }
    const response = await page.request.get('/current-companies.json');
    expect(response.ok()).toBeTruthy();
    expect(await response.json()).toEqual(registry);
  } finally {
    await context.close();
  }
});
