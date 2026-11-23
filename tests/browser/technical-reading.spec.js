const { test, expect, firefox } = require('@playwright/test');

const chapter = '/research/state-of-ai-data-labs/chapters/technical-landscape/';
const datedChapter = '/research/editions/2026-11-12/chapters/technical-landscape/';
const paragraphSelector = '.r-reader-chapter-content[aria-labelledby="technical-landscape"] > .r-paragraph';
const lastSentence = 'Difficulty selection changes what an absolute score represents.';
const touchCitations = [
  {
    name: 'IFEval',
    phrase: 'GPT-4 prompt-level strict accuracy of 76.89%',
    assertionId: 'assertion-cohort6.claim.ifeval.gpt4-result',
    sourceId: 'source-cohort6.source.ifeval.gpt4-result',
    sourceShard: 'f',
  },
  {
    name: 'GPQA',
    phrase: '39.7% on the 448-question main split',
    assertionId: 'assertion-cohort6.claim.gpqa.gpt4-result',
    sourceId: 'source-cohort6.source.gpqa.gpt4-result',
    sourceShard: '6',
  },
  {
    name: 'OSWorld',
    phrase: 'do not efficiently detect latent unnecessary damaging side effects',
    assertionId: 'assertion-cohort4.claim.osworld.side-effect-gap',
    sourceId: 'source-cohort4.source.osworld.side-effect-gap',
    sourceShard: 'd',
  },
];

// Exercise native reading behavior with the optional application scripts off.
// DOM snapshots of this complete chapter are large; keep diagnostic screenshots.
test.use({ javaScriptEnabled: false,
  trace: { mode: 'retain-on-failure', snapshots: false, screenshots: true, sources: true } });

async function verifyCitationHistory(page) {
  const response = await page.goto(chapter);
  expect(response.ok()).toBeTruthy();
  expect(await response.text()).toContain(lastSentence);
  await expect(page.locator(paragraphSelector)).toHaveCount(527);
  const finalCitation = page.locator(paragraphSelector).last().locator('.r-paragraph-citations a').first();
  const href = await finalCitation.getAttribute('href');
  expect(href).toMatch(/^\/research\/data\/assertions\/[0-9a-f]\/#assertion-/);
  await finalCitation.focus();
  await expect(finalCitation).toBeFocused();
  await expect(finalCitation).toBeInViewport();
  const focusedLayout = await page.locator(paragraphSelector).evaluateAll(nodes => ({
    supported: CSS.supports('content-visibility', 'auto'),
    deferred: nodes.filter(node => getComputedStyle(node).contentVisibility !== 'visible').length,
  }));
  if (focusedLayout.supported) expect(focusedLayout.deferred).toBe(0);
  await finalCitation.press('Enter');
  await expect(page).toHaveURL(new URL(href, page.url()).href);
  await expect(page.locator('[id=' + JSON.stringify(decodeURIComponent(href.split('#')[1])) + ']')).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(chapter + '$'));
  await expect(page.locator(paragraphSelector)).toHaveCount(527);
  await expect(finalCitation).toBeInViewport();
  await page.goForward();
  await expect(page).toHaveURL(new URL(href, page.url()).href);
}

async function verifyPassageHistory(page, path) {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(path);
  const destination = page.locator('#scalable-oversight-result');
  const shortcut = page.getByRole('navigation', { name: 'Reading shortcuts' })
    .locator('a[href="#scalable-oversight-result"]');
  await shortcut.focus();
  await expect(shortcut).toBeInViewport();
  const originalURL = page.url();
  const originalScroll = await page.evaluate(() => scrollY);
  const destinationURL = new URL(await shortcut.getAttribute('href'), originalURL).href;
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(destinationURL);
  await expect(destination).toBeFocused();
  await expect(destination).toBeInViewport();

  await page.goBack();
  await expect(page).toHaveURL(originalURL);
  await expect(shortcut).toBeFocused();
  await expect(shortcut).toBeInViewport();
  expect(await page.evaluate(() => scrollY)).toBeCloseTo(originalScroll, 0);
  await page.keyboard.press('Tab');
  const next = page.locator('.r-reader-book-title a');
  await expect(next).toBeFocused();
  await expect(next).toBeInViewport();

  await page.goForward();
  await expect(page).toHaveURL(destinationURL);
  await expect(destination).toBeFocused();
  await expect(destination).toBeInViewport();
}

async function citationTapPoint(citation) {
  return citation.evaluate(anchor => {
    // An inline link can wrap. Its bounding box can include text from another link.
    for (const rect of Array.from(anchor.getClientRects()).reverse()) {
      if (rect.left < 0 || rect.right > innerWidth || rect.top < 0 || rect.bottom > innerHeight) continue;
      const x = Math.round((rect.left + rect.right) / 2);
      const y = Math.round((rect.top + rect.bottom) / 2);
      if (document.elementFromPoint(x, y)?.closest('a') === anchor) return { x, y };
    }
    return null;
  });
}

test('complete technical chapter supports its final citation, focus and history without JavaScript', async ({ page }) => {
  await verifyCitationHistory(page);
});

test('the current chapter starts with readable prose and keeps a native chapter index', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(chapter);
  const first = page.locator('#first-paragraph > p').first();
  await expect(first).toContainText('This chapter separates stages');
  await expect(first).toBeInViewport({ ratio: 0.08 });

  const index = page.locator('.r-chapter-index');
  const summary = index.locator('summary');
  await expect(summary).toBeInViewport();
  await expect(index.getByRole('navigation', { name: 'Report chapters' })).toBeHidden();
  await summary.press('Enter');
  const chapters = index.getByRole('navigation', { name: 'Report chapters' }).locator('ol a');
  await expect(chapters).toHaveCount(12);
  await expect(index.locator('[aria-current="page"]')).toHaveAttribute('href', chapter);
  await index.locator('ol a[href$="/chapters/datasets-and-benchmarks/"]').press('Enter');
  await expect(page).toHaveURL(/\/chapters\/datasets-and-benchmarks\/$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/^6\. Dataset and benchmark landscape/);
});

test('Technical passage links open natively and keep their copied fragment in each edition', async ({ page, context }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const path of [chapter, datedChapter]) {
    await page.goto(path);
    await page.getByRole('navigation', { name: 'Reading shortcuts' })
      .locator('a[href="#scalable-oversight-result"]').press('Enter');
    const passage = page.locator('#scalable-oversight-result:target');
    await expect(passage).toBeFocused();
    await expect(passage).toBeInViewport();
    const copied = await context.newPage();
    await copied.goto(page.url());
    await expect(copied.locator('#scalable-oversight-result:target')).toBeInViewport();
    await copied.close();
  }
});

test.describe('enhanced technical reading', () => {
  test.use({ javaScriptEnabled: true });

  for (const [edition, path] of [['current', chapter], ['dated', datedChapter]]) {
    test(`${edition} Technical passage keeps keyboard focus with browser Back and Forward`, async ({ page }) => {
      await verifyPassageHistory(page, path);
    });
  }

  test('Firefox at 28px restores a visible passage on Forward and lets a reader scroll away', async ({ browserName, baseURL }) => {
    test.skip(browserName !== 'firefox', 'Firefox provides a real minimum font preference');
    test.setTimeout(60_000);
    const browser = await firefox.launch({ firefoxUserPrefs: { 'font.minimum-size.x-western': 28 } });
    try {
      const page = await browser.newPage({ baseURL });
      await verifyPassageHistory(page, chapter);

      const destinationURL = page.url();
      const destination = page.locator('#scalable-oversight-result');
      const belowPassage = await page.evaluate(() => scrollY + innerHeight);
      await page.evaluate(() => scrollBy({ top: innerHeight * 3, behavior: 'instant' }));
      await expect(destination).not.toBeInViewport();

      await page.goBack();
      await expect(page).toHaveURL(new URL(chapter, destinationURL).href);
      await expect(page.locator('a[href="#scalable-oversight-result"]')).toBeFocused();
      await page.keyboard.press('Tab');
      await page.goForward();
      await expect(page).toHaveURL(destinationURL);
      await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(belowPassage);
      await expect(destination).not.toBeInViewport();
      await expect(destination).not.toBeFocused();
    } finally {
      await browser.close();
    }
  });

  test('final citation restores its reading position with scripts enabled', async ({ page }) => {
    await verifyCitationHistory(page);
  });

  test('End reaches the technical footer while leaving text editing to the browser', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(chapter);
    await expect(page.locator('html')).toHaveAttribute('data-reader-enhanced', '');
    const shortcut = page.getByRole('link', { name: 'First paragraph', exact: true });
    await shortcut.focus();
    await page.keyboard.press('End');
    await expect(page.locator('footer')).toBeInViewport();
    await expect(shortcut).toBeFocused();
    const last = page.locator(paragraphSelector).last();
    if (await page.evaluate(() => CSS.supports('content-visibility', 'auto'))) {
      await expect(last).toHaveCSS('content-visibility', 'auto');
    }

    await page.evaluate(() => {
      const editor = document.createElement('input');
      editor.id = 'reader-typing-test';
      editor.value = 'Preserve the caret';
      document.querySelector('main').prepend(editor);
      editor.focus();
      editor.setSelectionRange(3, 3);
    });
    const editor = page.locator('#reader-typing-test');
    await editor.press('End');
    const caret = await editor.evaluate(input => ({ position: input.selectionStart, length: input.value.length }));
    expect(caret.position).toBe(caret.length);
    await expect(editor).toBeFocused();
    await expect(page.locator('footer')).not.toBeInViewport();
  });

  test('Ctrl+End reaches the exact technical document end outside editors', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', 'The Linux WebKit control does not map Ctrl+End to document scrolling');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.goto(chapter);
      await expect(page.locator('html')).toHaveAttribute('data-reader-enhanced', '');
      await page.keyboard.press('Control+End');
      await expect.poll(() => page.evaluate(() => {
        const root = document.scrollingElement;
        return root.scrollHeight - root.clientHeight - root.scrollTop;
      })).toBeLessThanOrEqual(1);
    }
  });

  test('Ctrl+End keeps native editor and text selection behavior', async ({ page, browserName }) => {
    test.skip(browserName === 'webkit', 'The Linux WebKit control does not map Ctrl+End to document scrolling');
    await page.goto(chapter);
    const html = page.locator('html');
    await expect(html).toHaveAttribute('data-reader-enhanced', '');
    const editor = page.locator('#reader-typing-test');
    await page.evaluate(() => {
      const input = document.createElement('textarea');
      input.id = 'reader-typing-test';
      input.value = 'First line\nSecond line';
      document.querySelector('main').prepend(input);
      input.focus();
      input.setSelectionRange(0, 0);
    });
    await editor.press('Control+End');
    expect(await editor.evaluate(input => input.selectionStart)).toBe('First line\nSecond line'.length);
    await expect(editor).toBeFocused();
    await expect(html).toHaveAttribute('data-reader-enhanced', '');

    await editor.evaluate(input => input.remove());
    const richEditor = page.locator('#reader-rich-typing-test');
    await page.evaluate(() => {
      const editable = document.createElement('div');
      editable.id = 'reader-rich-typing-test';
      editable.contentEditable = 'true';
      editable.textContent = 'Keep this editable';
      document.querySelector('main').prepend(editable);
      editable.focus();
      getSelection().collapse(editable.firstChild, 0);
    });
    await richEditor.press('Control+End');
    expect(await richEditor.evaluate(editable => {
      const selection = getSelection();
      return selection.isCollapsed && selection.anchorNode === editable.firstChild &&
        selection.anchorOffset === editable.textContent.length;
    })).toBe(true);
    await expect(html).toHaveAttribute('data-reader-enhanced', '');

    await richEditor.evaluate(editable => editable.remove());
    await page.locator(paragraphSelector).first().evaluate(node => {
      const range = document.createRange();
      range.selectNodeContents(node.firstElementChild);
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    });
    expect(await page.evaluate(() => getSelection().isCollapsed)).toBe(false);
    await page.keyboard.press('Control+End');
    await expect(html).toHaveAttribute('data-reader-enhanced', '');
  });

  test('native End remains usable when the reader script is refused', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route('**/native-details.js', route => route.abort());
    await page.goto(chapter);
    await expect(page.locator('html')).not.toHaveAttribute('data-reader-enhanced', '');
    await page.keyboard.press('End');
    await expect(page.locator('footer')).toBeInViewport();
  });
});

test.describe('technical citations after native Find on a phone', () => {
  test.use({ javaScriptEnabled: true, viewport: { width: 390, height: 844 } });
  test.skip(({ browserName, isMobile, hasTouch }) => browserName !== 'chromium' || !isMobile || !hasTouch,
    'Exercise the first physical tap in mobile Chromium');

  const editions = [
    { name: 'current', path: chapter, data: '/research/data' },
    { name: '2026-11-12', path: datedChapter, data: '/research/editions/2026-11-12/data' },
  ];
  for (const edition of editions) {
    for (const { name, phrase, assertionId, sourceId, sourceShard } of touchCitations) {
      test(`${edition.name} Technical ${name} citation opens on the first tap after Find`, async ({ page }) => {
        const verifyLedgerLayout = edition.name === 'current' && name === 'GPQA';
        await page.goto(edition.path);
        const chapterURL = page.url();
        expect(new URL(chapterURL).hash).toBe('');
        await expect(page.locator('html')).toHaveAttribute('data-reader-enhanced', '');
        const selection = await page.evaluate(text => window.find(text) ? getSelection().toString() : null, phrase);
        expect(selection).toBe(phrase);

        const assertionPath = `${edition.data}/assertions/1/#${assertionId}`;
        const assertionURL = new URL(assertionPath, chapterURL).href;
        const citation = page.locator(paragraphSelector).filter({ hasText: phrase })
          .locator(`.r-paragraph-citations a[href="${assertionPath}"]`);
        let point = await citationTapPoint(citation);
        if (!point) {
          await citation.scrollIntoViewIfNeeded();
          point = await citationTapPoint(citation);
        }
        expect(point, 'The citation must be the hit target before tapping').not.toBeNull();
        await page.touchscreen.tap(point.x, point.y);
        await expect(page, 'One tap must open the exact assertion').toHaveURL(assertionURL);

        const assertion = page.locator(`:target[id="${assertionId}"]`);
        await expect(assertion).toBeInViewport();
        if (verifyLedgerLayout) await expect(page.locator('html')).toHaveAttribute('data-ledger-fragment', '');
        const sourcePath = `${edition.data}/sources/${sourceShard}/#${sourceId}`;
        await assertion.locator(`a[href="${sourcePath}"]`).tap();
        await expect(page).toHaveURL(new URL(sourcePath, chapterURL).href);
        await expect(page.locator(`:target[id="${sourceId}"]`)).toBeInViewport();
        if (verifyLedgerLayout) await expect(page.locator('html')).toHaveAttribute('data-ledger-fragment', '');

        await page.goBack();
        await expect(page).toHaveURL(assertionURL);
        if (verifyLedgerLayout) {
          await expect(page.locator('html')).toHaveAttribute('data-ledger-fragment', '');
          await page.evaluate(() => new Promise(resolve => {
            requestAnimationFrame(() => requestAnimationFrame(resolve));
          }));
        }
        await expect(assertion).toBeInViewport();
        await page.goBack();
        await expect(page).toHaveURL(chapterURL);
        await expect.poll(() => citationTapPoint(citation)).not.toBeNull();
      });
    }
  }
});

test('direct final-citation fragment and reload resolve after the complete technical layout', async ({ page }) => {
  await page.goto(chapter + '#cite');
  await expect(page.locator('#cite')).toBeInViewport();
  const visibility = await page.locator(paragraphSelector).evaluateAll(nodes => ({
    supported: CSS.supports('content-visibility', 'auto'),
    values: [...new Set(nodes.map(node => getComputedStyle(node).contentVisibility))],
  }));
  if (visibility.supported) expect(visibility.values).toEqual(['visible']);
  await page.reload();
  await expect(page.locator('#cite')).toBeInViewport();
  await expect(page.locator(paragraphSelector)).toHaveCount(527);
});

test('native find reaches the final technical paragraph when the engine exposes it', async ({ page }) => {
  await page.goto(chapter);
  const supported = await page.evaluate(() => typeof window.find === 'function');
  test.skip(!supported, 'This engine does not expose its native find API to the test runner');
  const found = await page.evaluate(text => window.find(text, false, false, true, false, false, false), lastSentence);
  expect(found).toBe(true);
  const selection = await page.evaluate(() => {
    const selected = window.getSelection();
    const rect = selected.getRangeAt(0).getBoundingClientRect();
    return {text: selected.toString(), top: rect.top, bottom: rect.bottom, viewport: innerHeight};
  });
  expect(selection.text).toBe(lastSentence);
  expect(selection.bottom).toBeGreaterThan(0);
  expect(selection.top).toBeLessThan(selection.viewport);
});

test('printing reveals every technical paragraph with no clipped text', async ({ page }) => {
  await page.goto(chapter);
  await page.emulateMedia({ media: 'print' });
  const layout = await page.locator(paragraphSelector).evaluateAll(nodes => ({
    count: nodes.length,
    supported: CSS.supports('content-visibility', 'auto'),
    hidden: nodes.filter(node => getComputedStyle(node).contentVisibility !== 'visible').length,
    contained: nodes.filter(node => getComputedStyle(node).contain !== 'none').length,
    empty: nodes.filter(node => node.getBoundingClientRect().height <= 0).length,
    clipped: nodes.filter(node => ['hidden', 'clip'].includes(getComputedStyle(node).overflowY)).length,
  }));
  expect(layout.count).toBe(527);
  expect(layout.empty).toBe(0);
  expect(layout.clipped).toBe(0);
  if (layout.supported) {expect(layout.hidden).toBe(0); expect(layout.contained).toBe(0);}
});

test('technical paragraphs preserve readable spacing and fit a 320 pixel screen', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto(chapter);
  const layout = await page.locator(paragraphSelector).evaluateAll(nodes => {
    const first = nodes[0], second = nodes[1];
    return {width: document.documentElement.scrollWidth, viewport: innerWidth,
      paragraphGap: second.getBoundingClientRect().top - first.lastElementChild.getBoundingClientRect().bottom,
      declaredGap: parseFloat(getComputedStyle(first).marginBottom)};
  });
  expect(layout.width).toBeLessThanOrEqual(layout.viewport + 1);
  expect(Math.abs(layout.paragraphGap - layout.declaredGap)).toBeLessThanOrEqual(1);
});
