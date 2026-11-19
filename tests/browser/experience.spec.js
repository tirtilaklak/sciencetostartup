const { test, expect } = require('@playwright/test');
const registry = require('../../data/current-companies.json');
const canonical = require('../../data/canonical.json');

async function datasetNodes(page) {
  return page.locator('script[type="application/ld+json"]').evaluateAll(nodes => nodes.flatMap(node => {
    const value = JSON.parse(node.textContent);
    return Array.isArray(value) ? value : value['@graph'] || [value];
  }).filter(node => node['@type'] === 'Dataset'));
}

async function fitsViewport(locator) {
  const boxes = await locator.evaluateAll(nodes => nodes.map(node => {
    const box = node.getBoundingClientRect();
    return { text: node.textContent.slice(0, 100), left: box.left, right: box.right, width: innerWidth };
  }));
  for (const box of boxes) {
    expect(box.left, box.text).toBeGreaterThanOrEqual(-1);
    expect(box.right, box.text).toBeLessThanOrEqual(box.width + 1);
  }
}

test('current discovery and historical downloads keep distinct identity and working links', async ({ page }) => {
  const count = canonical.companies.length + registry.entries.length;
  await page.goto('/');
  await expect(page.locator('[data-count="companies"]')).toHaveText(String(count));
  const homeDataset = (await datasetNodes(page)).find(node => node['@id'].endsWith('/#dataset'));
  expect(homeDataset.version).toBe(canonical.dataset_version);
  expect(homeDataset.description).toContain('39 AI data companies');
  expect(homeDataset.distribution.map(item => item.contentUrl)).not.toContain('https://sciencetostartup.com/work-routes.json');
  await expect(page.locator('.hero-actions svg')).toHaveCount(2);
  for (const icon of await page.locator('.hero-actions svg').all()) {
    await expect(icon).toHaveAttribute('aria-hidden', 'true');
    await expect(icon).toHaveAttribute('focusable', 'false');
  }
  await page.goto('/method/#downloads');
  await expect(page.getByRole('heading', { name: 'Current supporting data', exact: true })).toBeVisible();
  const dataset = (await datasetNodes(page)).find(node => node['@id'].endsWith('/#dataset'));
  expect(dataset.dateModified).toBe(canonical.meta.as_of);
  const core = dataset.distribution.map(item => item.contentUrl);
  for (const filename of ['work-routes.json', 'source-updates.json', 'profile-content.json', 'editorial.json', 'business-health.json']) {
    const href = 'https://sciencetostartup.com/' + filename;
    await expect(page.locator('#download-files a[href="' + href + '"][download]')).toBeVisible();
    expect(core).not.toContain(href);
  }
  await expect(page.locator('.site-footer-meta')).toHaveText('Historical company dataset v2.5.0 · Snapshot 15 Oct 2026');
  await expect(page.locator('.site-footer').getByRole('link', { name: 'Historical company data', exact: true })).toHaveAttribute('href', /\/method\/#downloads$/);
  await expect(page.locator('.site-footer').getByRole('link', { name: 'Research data', exact: true })).toHaveAttribute('href', /\/research\/data\/$/);
});

test('opened source context and decision-critical metadata reflow at 320 pixels', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 800 });
  let companyViewport;
  const parentScoped = registry.entries.find(entry => entry.parent_company);
  const longTitle = [...registry.entries].sort((a, b) => Math.max(...b.sources.map(source => source.title.length)) - Math.max(...a.sources.map(source => source.title.length)))[0];
  const updated = registry.entries.find(entry => entry.current_facts);
  for (const entry of [...new Set([parentScoped, longTitle, updated].filter(Boolean))]) {
    await page.goto('/companies/?q=' + encodeURIComponent(entry.name));
    await expect(page.locator('#company-query')).toHaveCSS('font-size', '16px');
    await expect(page.locator('#company-group')).toHaveCSS('font-size', '16px');
    const card = page.locator('[data-company="' + entry.entity_id + '"]');
    await expect(card.getByRole('heading', { name: entry.name, exact: true })).toBeVisible();
    await card.locator('.company-current-context > summary').click();
    await card.locator('.company-current-source-receipts > summary').click();
    await expect(card.locator('.company-wikipedia-description')).toHaveText(entry.wikipedia.description);
    for (const source of entry.sources) await expect(card.locator('.company-current-source-receipts')).toContainText(source.locator);
    if (entry.current_facts) {
      const updates = card.locator('.company-current-update-facts');
      await updates.locator(':scope > summary').click();
      for (const row of entry.current_facts.rows) await expect(updates).toContainText(row.value);
    }
    await fitsViewport(card.locator('h3,.company-current-context[open] p,.company-current-context[open] a,.company-current-context[open] li,.company-current-context[open] dd'));
    if (entry === parentScoped) {
      await card.locator('h3').scrollIntoViewIfNeeded();
      companyViewport = await page.screenshot({ fullPage: false, animations: 'disabled', scale: 'css' });
    }
  }
  await page.goto('/company/mercor/');
  await page.locator('#financial-record > summary').click();
  for (const label of await page.locator('.company-fact-label,.company-fact-meta,.company-fact-source,.company-current-fact .sub').all()) {
    await expect(label).toHaveCSS('font-size', '14px');
  }
  await fitsViewport(page.locator('#financial-record p,#financial-record th,#financial-record td,.company-key-facts'));
  await page.goto('/work/?q=Research%20Engineer');
  const conflict = page.locator('[data-work-route="afterquery.work.research-engineer"]');
  await expect(conflict).toContainText('Pay period not stated');
  await expect(conflict.locator('.work-reviewed')).toHaveCSS('font-size', '14px');
  await conflict.locator('.work-terms > summary').click();
  await expect(conflict.locator('.work-terms')).toContainText('$210K');
  await expect(conflict.locator('.work-terms')).toContainText('$250K');
  await fitsViewport(conflict.locator('h3,p,li,blockquote,a'));
  const review = await conflict.locator('.work-reviewed').boundingBox();
  const action = await conflict.locator('.work-listing-action').boundingBox();
  expect(review.y + review.height).toBeLessThanOrEqual(action.y);
  for (const link of await page.locator('.site-footer nav a').all()) {
    const box = await link.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(44);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(321);
  await conflict.locator('h3').scrollIntoViewIfNeeded();
  const workViewport = await page.screenshot({ fullPage: false, animations: 'disabled', scale: 'css' });
  // Attach the captured checkpoints only after the complete functional check passes.
  if (companyViewport) await info.attach(`company-context-320-${info.project.name}.png`, { body: companyViewport, contentType: 'image/png' });
  await info.attach(`work-pay-conflict-320-${info.project.name}.png`, { body: workViewport, contentType: 'image/png' });
});
