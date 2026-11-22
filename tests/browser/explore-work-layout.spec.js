const { test, expect } = require('@playwright/test');

test('Explore Work keeps the result count and controls readable at narrow widths', async ({ page }) => {
  const widths = [320, 360, 390, 480, 540, 600, 700, 844];
  for (const [fragment, label] of [['work', /^\d+ records/], ['work?q=India', 'No recorded matches']]) {
    await page.goto('/explore/#' + fragment);
    await expect(page.locator('#work-count')).toHaveText(label);
    for (const width of widths) {
      await page.setViewportSize({ width, height: 844 });
      const problems = await page.locator('#work-view .w4-results-bar').evaluate(bar => {
        const bounds = bar.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(bar.querySelector('#work-count'));
        const count = [...range.getClientRects()];
        const actions = [...bar.querySelectorAll('.w4-results-actions :is(a,button), #work-sort')];
        const overlaps = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
        const errors = [];
        if (count.length < 1 || count.length > 2) errors.push(`Count occupies ${count.length} lines`);
        for (const action of actions) {
          const box = action.getBoundingClientRect();
          if (box.width < 44 || box.height < 44) errors.push(`${action.id} target is too small`);
          if (box.left < bounds.left || box.right > bounds.right + 1) errors.push(`${action.id} extends outside the bar`);
          if (count.some(text => overlaps(text, box))) errors.push(`${action.id} overlaps the count`);
        }
        return errors;
      });
      expect(problems, `${fragment} at ${width}px`).toEqual([]);
    }
    await page.setViewportSize({ width: 320, height: 844 });
    await page.getByRole('combobox', { name: 'Sort', exact: true }).selectOption('hourly');
    await expect(page).toHaveURL(/sort=hourly$/);
    await expect(page.locator('#work-sort')).toHaveValue('hourly');
  }
});
