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

  await action.press('Enter');
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
  await expect(action).toBeFocused();
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
  await expect(results.getByRole('link', { name: 'TransPerfect / DataForce' })).toHaveAttribute('href', /\/company\/org\.dataforce\/$/);
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

const shortlistTest = test.extend({
  launchOptions: [async ({ launchOptions, browserName }, use) => {
    await use(browserName === 'firefox' ? {
      ...launchOptions,
      firefoxUserPrefs: {
        ...launchOptions.firefoxUserPrefs,
        'font.minimum-size.x-western': 28,
        'font.minimum-size.x-unicode': 28,
      },
    } : launchOptions);
  }, { scope: 'worker' }],
});

const shortlist = [
  { id: 'trajectory_labs_pbc', name: 'Trajectory Labs, PBC' },
  { id: 'laude', name: 'Laude Institute / Terminal-Bench' },
  { id: 'invisible', name: 'Invisible Technologies' },
];
const fourthName = 'Handshake AI';
const originalIds = shortlist.map(company => company.id);
const compareHash = ids => '#compare/' + ids.join('/');

async function fillShortlist(page, hasTouch, browserName) {
  if (browserName === 'firefox') await page.setViewportSize({ width: 320, height: 720 });
  const activate = (control, key = 'Enter') => hasTouch ? control.tap() : control.press(key);
  await page.goto('/explore/#companies', { waitUntil: 'domcontentloaded' });
  const search = page.getByRole('searchbox', { name: 'Search', exact: true });
  const checkbox = name => page.getByRole('checkbox', { name: `Compare ${name}`, exact: true });
  for (const { name } of shortlist) {
    await search.fill(name);
    await activate(checkbox(name), 'Space');
    await expect(checkbox(name)).toBeChecked();
  }
  await search.fill(fourthName);
  const fourth = checkbox(fourthName);
  await expect(fourth).toBeVisible();
  const tray = page.getByRole('complementary', { name: 'Comparison shortlist' });
  const compare = tray.getByRole('link', { name: /^Compare\b/ });
  const clear = tray.getByRole('button', { name: /^Clear\b/ });
  await expect(compare).toHaveAttribute('href', compareHash(originalIds));
  return { activate, search, fourth, tray, compare, clear };
}

async function expectReachable(control) {
  await expect(control).toBeInViewport({ ratio: 1 });
  await expect.poll(() => control.evaluate(element => {
    const { x, y, width, height } = element.getBoundingClientRect();
    return element.contains(document.elementFromPoint(x + width / 2, y + height / 2));
  }), { message: 'A reader can hit the control without scrolling' }).toBe(true);
}

async function expectReadableText(locator, text) {
  await expect.poll(() => locator.evaluate((element, phrase) => {
    const content = element.textContent;
    const start = content.indexOf(phrase ?? content);
    const end = start + (phrase ?? content).length;
    if (start < 0 || !content.trim()) return ['Missing text'];

    const clips = [];
    for (let parent = element; parent; parent = parent.parentElement) {
      const { overflowX, overflowY } = getComputedStyle(parent);
      const clipsOverflow = overflow => ['auto', 'scroll', 'hidden', 'clip'].includes(overflow);
      if (!clipsOverflow(overflowX) && !clipsOverflow(overflowY)) continue;
      const box = parent.getBoundingClientRect();
      const left = box.left + parent.clientLeft;
      const top = box.top + parent.clientTop;
      clips.push({
        left: clipsOverflow(overflowX) ? left : -Infinity,
        right: clipsOverflow(overflowX) ? left + parent.clientWidth : Infinity,
        top: clipsOverflow(overflowY) ? top : -Infinity,
        bottom: clipsOverflow(overflowY) ? top + parent.clientHeight : Infinity,
      });
    }
    clips.push({ left: 0, right: innerWidth, top: 0, bottom: innerHeight });

    // A status can have a viewport intersection while its final line is clipped.
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    const hidden = [];
    let offset = 0;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      let index = 0;
      for (const character of node.data) {
        const position = offset + index;
        const next = index + character.length;
        if (/\S/u.test(character) && position >= start && position < end) {
          range.setStart(node, index);
          range.setEnd(node, next);
          const box = range.getBoundingClientRect();
          const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
          const clipped = clips.some(clip => box.left < clip.left - 0.5 || box.right > clip.right + 0.5
            || box.top < clip.top - 0.5 || box.bottom > clip.bottom + 0.5);
          if (!box.width || !box.height || clipped || !element.contains(hit)) hidden.push(character);
        }
        index = next;
      }
      offset += node.length;
    }
    return hidden;
  }, text), { message: `All characters in ${text ?? 'the shortlist notice'} can be read` }).toEqual([]);
}

shortlistTest('Explore shortlist keeps the fourth-selection instruction and actions readable', async ({ page, hasTouch, browserName }) => {
  const { activate, fourth, tray, compare, clear } = await fillShortlist(page, hasTouch, browserName);
  await activate(fourth, 'Space');
  await expect(fourth).not.toBeChecked();
  await expect(compare).toHaveAttribute('href', compareHash(originalIds));
  const names = tray.getByRole('status').filter({ hasText: shortlist[0].name });
  const notice = tray.getByRole('status').filter({ hasText: /remove\b/i });
  await expect(notice).toBeVisible();
  await expectReachable(compare);
  await expectReachable(clear);
  await expectReadableText(notice);
  for (const { name } of shortlist) await expectReadableText(names, name);

  if (browserName === 'firefox') {
    // A shorter window forces the names to scroll while the notice and actions stay put.
    await page.setViewportSize({ width: 320, height: 540 });
    await expect.poll(() => names.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
    await compare.focus();
    await page.keyboard.press('Shift+Tab');
    await expect(names).toBeFocused();
    await page.keyboard.press('End');
    await expectReadableText(names, shortlist.at(-1).name);
    await expectReadableText(notice);
    await page.keyboard.press('Tab');
    await expect(compare).toBeFocused();
    await expectReachable(compare);
    await expectReachable(clear);
  }
});

shortlistTest('Explore shortlist restores the initiating Compare after editing and reloading the comparison', async ({ page, hasTouch, browserName }) => {
  const { activate, search, fourth, tray, compare, clear } = await fillShortlist(page, hasTouch, browserName);
  await activate(fourth, 'Space');
  await expect(fourth).not.toBeChecked();
  const directoryURL = page.url();
  await fourth.evaluate(element => element.closest('[data-company-card]').scrollIntoView({ block: 'start', behavior: 'instant' }));
  const origin = await page.evaluate(() => ({ y: scrollY, height: innerHeight }));
  expect(origin.y).toBeGreaterThan(origin.height / 10);

  const columns = page.locator('#compare-content thead [data-remove]');
  async function expectComparison(ids) {
    await expect(page).toHaveURL(url => url.hash === compareHash(ids));
    await expect.poll(() => columns.evaluateAll(nodes => nodes.map(node => node.dataset.remove))).toEqual(ids);
  }

  await activate(compare);
  await expectComparison(originalIds);
  const [first, removed, last] = shortlist;
  await activate(page.getByRole('button', { name: `Remove ${removed.name}`, exact: true }));
  await expectComparison([first.id, last.id]);
  await page.getByRole('combobox', { name: 'Add a company' }).selectOption('appen');
  await activate(page.getByRole('button', { name: 'Add', exact: true }));
  const editedIds = [first.id, last.id, 'appen'];
  await expectComparison(editedIds);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expectComparison(editedIds);

  await page.goBack({ waitUntil: 'commit' });
  await expect(page).toHaveURL(directoryURL);
  await expect(search).toHaveValue(fourthName);
  await expect(fourth).toBeVisible();
  await expect(fourth).not.toBeChecked();
  await expect(compare).toHaveAttribute('href', compareHash(originalIds));
  await expect(compare).toBeFocused();
  await expectReachable(compare);
  const scrollDelta = () => page.evaluate(y => Math.abs(scrollY - y), origin.y);
  await expect.poll(scrollDelta, { message: 'Back keeps the directory scroll position' }).toBeLessThan(origin.height / 20);

  await page.keyboard.press('Tab');
  await expect(clear).toBeFocused();
  await expectReachable(clear);
  await expect.poll(scrollDelta, { message: 'Tab stays near the initiating Compare action' }).toBeLessThan(origin.height / 20);

  await page.goForward({ waitUntil: 'commit' });
  await expectComparison(editedIds);
  await page.goBack({ waitUntil: 'commit' });
  await expect(compare).toHaveAttribute('href', compareHash(originalIds));
  await activate(clear);
  await expect(tray).toBeHidden();
  await expect(search).toHaveValue(fourthName);
});
