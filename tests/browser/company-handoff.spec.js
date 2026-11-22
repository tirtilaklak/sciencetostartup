const { test, expect } = require('@playwright/test');

test('native Companies carries the exact saved search result into Compare', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/companies/?group=expert-data-evaluation&reader=keep');
  const search = page.getByRole('searchbox', { name: 'Search companies' });
  const results = page.locator('[data-company]:visible');
  const action = results.getByRole('link', { name: 'Compare Mercor', exact: true });
  await search.fill('Mercor');
  await expect(results).toHaveCount(1);
  await expect(results).toHaveAttribute('data-company', 'mercor');
  await expect(action).toHaveAttribute('href', '/explore/#compare/mercor');
  await expect(action).toBeInViewport({ ratio: 1 });
  await expect(page.getByRole('link', { name: 'Compare 39 original profiles' })).toBeInViewport({ ratio: 1 });
  const directoryURL = page.url();
  expect(Object.fromEntries(new URL(directoryURL).searchParams)).toEqual({ group: 'expert-data-evaluation', reader: 'keep', q: 'Mercor' });

  await action.click();
  await expect(page).toHaveURL(/\/explore\/#compare\/mercor$/);
  await expect(page.locator('#compare-content [data-remove]')).toHaveAttribute('data-remove', 'mercor');
  const add = page.getByRole('combobox', { name: 'Add a company' });
  await expect(add).toBeInViewport({ ratio: 1 });
  await expect(add.locator('option[value=mercor]')).toBeDisabled();
  await expect(add.locator('option[value=appen]')).toBeEnabled();

  await page.goBack();
  await expect(page).toHaveURL(directoryURL);
  await expect(search).toHaveValue('Mercor');
  await expect(page.getByRole('combobox', { name: 'Business group' })).toHaveValue('expert-data-evaluation');
  await expect(results).toHaveAttribute('data-company', 'mercor');
  await expect(action).toBeInViewport({ ratio: 1 });
  await page.goForward();
  await expect(page.locator('#compare-content [data-remove]')).toHaveAttribute('data-remove', 'mercor');
  await add.selectOption('appen');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page).toHaveURL(/\/explore\/#compare\/mercor\/appen$/);
  await expect(page.getByRole('table', { name: 'Comparison of Mercor and Appen' })).toBeVisible();
});

test('the directory offers historical comparisons and current-only profile links', async ({ page }) => {
  await page.goto('/companies/?q=DataForce+by+TransPerfect');
  const results = page.locator('[data-company]:visible');
  await expect(results).toHaveCount(1);
  await expect(results).toHaveAttribute('data-company', 'org.dataforce');
  await expect(results.getByRole('link', { name: 'DataForce by TransPerfect' })).toHaveAttribute('href', /\/company\/org\.dataforce\/$/);
  await expect(results.locator('.directory-compare')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Compare 39 original profiles' })).toHaveAttribute('href', '/explore/#compare');
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(results).toHaveCount(55);
  const historical = results.locator('.directory-compare');
  await expect(historical).toHaveCount(39);
  expect(await historical.evaluateAll(links => links.every(link =>
    link.getAttribute('href') === '/explore/#compare/' + link.closest('[data-company]').dataset.company
  ))).toBe(true);
});

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });

  test('the native directory retains its profile links and exact Compare destinations', async ({ page }) => {
    await page.goto('/companies/?q=Mercor');
    await expect(page.locator('#company-filters')).toBeHidden();
    await expect(page.locator('[data-company]:visible')).toHaveCount(55);
    await expect(page.getByRole('navigation', { name: 'Business groups' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Mercor', exact: true })).toHaveAttribute('href', /\/company\/mercor\/$/);
    await page.getByRole('link', { name: 'Compare Mercor', exact: true }).click();
    await expect(page).toHaveURL(/\/explore\/#compare\/mercor$/);
    await expect(page.getByRole('link', { name: 'Company list' })).toHaveAttribute('href', '/companies/');
  });
});
