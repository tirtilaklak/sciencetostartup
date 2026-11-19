const { test, expect } = require('@playwright/test');
const registry = require('../../data/current-companies.json');
const canonical = require('../../data/canonical.json');

function displayDate(value) {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(value + 'T00:00:00Z'));
}

async function checkCurrentFacts(container, entry) {
  const updates = container.locator('details.company-current-update-facts');
  const facts = entry.current_facts;
  await expect(updates).toHaveCount(facts ? 1 : 0);
  if (!facts) return;
  await expect(updates.locator(':scope > summary')).toHaveText('Updates checked ' + displayDate(facts.reviewed_on));
  await updates.locator(':scope > summary').click();
  const rows = updates.locator('dl.current-fact-list > div');
  await expect(rows).toHaveCount(facts.rows.length);
  for (const [index, row] of facts.rows.entries()) {
    const item = rows.nth(index);
    await expect(item.locator('dt')).toHaveText(row.label);
    await expect(item.locator('dd')).toContainText(row.value);
    for (const sourceIndex of row.source_indexes) {
      await expect(item.locator('a[href="' + facts.sources[sourceIndex].url + '"]').first()).toBeVisible();
    }
  }
  const offeringDates = entry.offerings.flatMap(offering => offering.source_indexes.map(index => entry.sources[index].observed_on)).sort();
  for (const date of new Set([offeringDates[0], offeringDates[offeringDates.length - 1]])) {
    await expect(container.locator('.company-research-snapshot')).toContainText(displayDate(date));
  }
}

test('current company additions can be found and linked with their attribution', async ({ page, baseURL }) => {
  for (const entry of registry.entries) {
    await page.goto('/companies/?q=' + encodeURIComponent(entry.name));
    await expect(page.locator('#company-filters')).toBeVisible();
    await expect(page.locator('.directory-company:visible')).toHaveCount(1);
    const card = page.locator('.directory-company[data-company="' + entry.entity_id + '"]');
    await expect(card).toBeVisible();
    await expect(card.getByRole('heading', { level: 3, name: entry.name, exact: true })).toBeVisible();
    const context = card.locator('.company-current-context');
    await expect(context).not.toHaveAttribute('open', '');
    await context.locator(':scope > summary').click();
    await expect(card).toContainText(entry.wikipedia.description);
    await expect(context.locator('.company-wikipedia-description')).toHaveText(entry.wikipedia.description);
    await expect(card.locator('a[href="' + entry.wikipedia.revision_url + '"]')).toBeVisible();
    await expect(card.locator('a[href="' + entry.wikipedia.license_url + '"]')).toBeVisible();
    await checkCurrentFacts(card, entry);
    const path = '/company/' + entry.entity_id + '/';
    await expect(card.locator('a[href$="' + path + '"]')).toHaveAttribute('href', 'https://sciencetostartup.com' + path);
    // Native links declare the public canonical URL; test its exact artifact here.
    await page.goto(path);
    await expect(page).toHaveURL(new URL(path, baseURL).href);
    const supplement = page.locator('[data-current-company="' + entry.entity_id + '"]');
    await expect(supplement).toContainText(entry.wikipedia.description);
    await expect(supplement).toContainText('Wikipedia contributors');
    await checkCurrentFacts(supplement, entry);
    await expect(supplement.locator('.company-current-source-receipts')).toContainText('Observed ' + displayDate(entry.wikipedia.observed_on));
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
      await card.locator('.company-current-context > summary').click();
      const details = card.locator('details.company-current-source-receipts');
      await details.locator('summary').click();
      for (const source of entry.sources) {
        await expect(details.locator('a[href="' + source.url + '"]')).toBeVisible();
      }
      await checkCurrentFacts(card, entry);
    }
    const response = await page.request.get('/current-companies.json');
    expect(response.ok()).toBeTruthy();
    expect(await response.json()).toEqual(registry);
  } finally {
    await context.close();
  }
});
