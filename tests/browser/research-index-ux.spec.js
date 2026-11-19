const { test, expect } = require('@playwright/test');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { createHash } = require('node:crypto');
const prior = readFileSync(resolve(__dirname, '../fixtures/research-index/preceding.js'), 'utf8');

async function graph(request) { return (await request.get('/research/exports/research-graph.json')).json(); }
async function openFilters(page) {
  const details = page.locator('[data-index-advanced]');
  if (!await details.evaluate(node => node.open)) await details.locator('summary').click();
  return details;
}

test('candidate versions of approved works remain independently visible and counted', async ({ page, request }) => {
  const data = await graph(request);
  const entities = new Map(data.entities.map(row => [row.id, row]));
  const candidates = data.entities.filter(row => row.kind === 'paper_version' && row.status === 'candidate');
  expect(candidates).toHaveLength(57);
  expect(candidates.every(row => entities.get(row.parent_id)?.status === 'approved')).toBeTruthy();
  await page.goto('/research/papers/?status=candidate&reader=keep#main');
  await expect(page.locator('[data-index-count]')).toHaveText('79 of 456 matching records · 22 paper works · 57 source versions');
  await expect(page.locator('[data-index-row]:visible')).toHaveCount(79);
  await expect(page.locator('[data-index-context]:visible')).toHaveCount(new Set(candidates.map(row => row.parent_id)).size);
  await expect(page.locator('[data-index-context]:visible').first()).toContainText('not counted as a match');
  expect(await page.locator('[data-index-row]').evaluateAll(nodes => nodes.some(node => node.parentElement.closest('[data-index-row]')))).toBeFalsy();
  const target = candidates[0];
  await page.getByLabel('Search records', { exact: true }).fill(target.id);
  const row = page.locator(`[data-record-id=${JSON.stringify(target.id)}]`);
  await expect(row).toBeVisible();
  await expect(row.locator('xpath=ancestor::details[1]')).toHaveAttribute('open', '');
  expect(new URL(page.url()).searchParams.get('reader')).toBe('keep');
  expect(new URL(page.url()).hash).toBe('#main');
});

test('advanced URL state opens, manual close retains it, and outside reset clears with focus', async ({ page }) => {
  await page.goto('/research/papers/?type=paper_version&reader=keep#main');
  const details = page.locator('[data-index-advanced]');
  await expect(details).toHaveAttribute('open', '');
  await expect(details.locator('[data-index-advanced-count]')).toHaveText('1 active');
  await details.locator('summary').click();
  await expect(details).not.toHaveAttribute('open', '');
  await expect(details.locator('select[name=type]')).toHaveValue('paper_version');
  expect(new URL(page.url()).searchParams.get('type')).toBe('paper_version');
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await expect(page.getByLabel('Search records', { exact: true })).toBeFocused();
  await expect(details.locator('select[name=type]')).toHaveValue('');
  expect(new URL(page.url()).search).toBe('?reader=keep');
  expect(new URL(page.url()).hash).toBe('#main');
  for (const name of ['expertise', 'labels', 'oversight']) await expect(page.locator(`select[name=${name}]`)).toHaveCount(0);
});

test('actual preceding script can reach a matching version beneath a hidden approved work', async ({ page }) => {
  expect(createHash('sha256').update(prior).digest('hex')).toBe('64a2ee9f8397275c289d4be3cb9580101c8ceec23045db02bab8738e09d9288b');
  await page.route('**/*', route => new URL(route.request().url()).pathname.includes('research-index')
    && new URL(route.request().url()).pathname.endsWith('.js')
    ? route.fulfill({contentType:'application/javascript', body:prior}) : route.continue());
  await page.goto('/research/papers/?status=candidate');
  await expect(page.locator('[data-index-count]')).toHaveText('79 of 456 records shown');
  const wrapper = page.locator('[data-index-versions]').filter({ has: page.locator('[data-index-row]:not([hidden])') }).first();
  await expect(wrapper.locator('summary')).toBeVisible();
  await expect(wrapper.locator('summary')).toContainText('Work context:');
  const parent = await wrapper.getAttribute('data-parent-record');
  await expect(page.locator(`[data-record-id=${JSON.stringify(parent)}]`)).toBeHidden();
  await wrapper.locator('summary').click();
  await expect(wrapper.locator('[data-index-row]:not([hidden])').first()).toBeVisible();
});

test('tau display and raw spelling reach the same records without overflowing at 320px', async ({ page }) => {
  await page.setViewportSize({width:320, height:780});
  await page.goto('/research/papers/');
  const query = page.getByLabel('Search records', { exact:true });
  await query.fill('τ²');
  const shown = await page.locator('[data-index-row]:not([hidden]) th .r-record-id').allTextContents();
  expect(shown.length).toBeGreaterThan(0);
  await query.fill('$\\tau^2$');
  expect(await page.locator('[data-index-row]:not([hidden]) th .r-record-id').allTextContents()).toEqual(shown);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  const filters = await openFilters(page);
  expect(await query.evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(16);
  expect(await filters.locator('summary').evaluate(node => node.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
});

test('paper filter removal preserves history, unrelated parameters and keyboard focus at 320px', async ({ page }) => {
  await page.setViewportSize({width:320, height:780});
  await page.goto('/research/papers/?status=candidate&type=paper_version&reader=keep#main');
  const applied = page.locator('[data-index-applied]');
  await expect(applied.getByRole('button')).toHaveCount(2);
  await applied.getByRole('button', {name:'Remove Review status: candidate', exact:true}).focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-index-count]')).toHaveText('208 of 456 matching records · 0 paper works · 208 source versions');
  await expect(applied.getByRole('button', {name:'Remove Record type: paper version', exact:true})).toBeFocused();
  expect(new URL(page.url()).searchParams.get('status')).toBeNull();
  expect(new URL(page.url()).searchParams.get('reader')).toBe('keep');
  expect(new URL(page.url()).hash).toBe('#main');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.goBack();
  await expect(applied.getByRole('button')).toHaveCount(2);
  await expect(page.locator('[data-index-count]')).toHaveText('57 of 456 matching records · 0 paper works · 57 source versions');
  await page.goForward();
  await expect(applied.getByRole('button')).toHaveCount(1);
  await applied.getByRole('button').click();
  await expect(applied).toBeHidden();
  await expect(page.getByLabel('Search records', {exact:true})).toBeFocused();
  expect(new URL(page.url()).search).toBe('?reader=keep');
  expect(new URL(page.url()).hash).toBe('#main');
});
