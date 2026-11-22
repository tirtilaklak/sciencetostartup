const { test, expect, firefox } = require('@playwright/test');

test('the Method correction address and actions fit at Firefox minimum font sizes', async ({ browserName, baseURL }, info) => {
  test.skip(browserName !== 'firefox', 'Firefox provides a minimum font preference');
  test.setTimeout(120_000);
  const viewport = { width: 320, height: 720 };
  const actionNames = ['Submit a correction on GitHub', 'Email a correction', 'Read the accepted correction log'];

  for (const minimum of [0, 28, 32]) {
    await test.step(minimum ? `${minimum}px minimum font` : 'Default font', async () => {
      const browser = await firefox.launch({ firefoxUserPrefs: {
        'font.minimum-size.x-western': minimum,
        'font.minimum-size.x-unicode': minimum,
      } });
      try {
        const page = await browser.newPage({ baseURL, viewport });
        await page.goto('/method/#corrections');
        await page.evaluate(async () => { await document.fonts.ready; });

        const contact = page.getByRole('complementary', { name: 'Corrections' });
        const actions = actionNames.map(name => contact.getByRole('link', { name, exact: true }));
        const destination = new URL(await actions[1].getAttribute('href'));
        const address = await contact.locator('.method-contact > p > span').evaluate(element => {
          const range = document.createRange();
          range.selectNodeContents(element);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          const selected = selection.toString();
          selection.removeAllRanges();
          return {
            text: element.textContent,
            selected,
            userSelect: getComputedStyle(element).userSelect,
            lines: Array.from(range.getClientRects(), rect => rect.toJSON()),
            documentWidth: document.scrollingElement.scrollWidth,
          };
        });
        const boxes = await Promise.all(actions.map(async (action, index) => ({
          name: actionNames[index],
          bounds: await action.boundingBox(),
        })));
        await info.attach(`minimum-font-${minimum}`, {
          body: JSON.stringify({ browser: browser.version(), viewport, minimum, address, actions: boxes }, null, 2),
          contentType: 'application/json',
        });

        expect(destination.protocol).toBe('mailto:');
        expect(destination.searchParams.get('subject')).toBe('ScienceToStartup correction');
        expect(address.text).toBe(destination.pathname);
        expect(address.selected).toBe(address.text);
        expect(address.userSelect).not.toBe('none');
        expect.soft(address.documentWidth, 'The page fits without horizontal panning').toBe(viewport.width);
        expect(address.lines.length).toBeGreaterThan(0);
        for (const line of address.lines) {
          expect(line.height).toBeGreaterThanOrEqual(minimum || 1);
          expect.soft(line.left).toBeGreaterThanOrEqual(0);
          expect.soft(line.right).toBeLessThanOrEqual(viewport.width);
          expect.soft(line.top).toBeGreaterThanOrEqual(0);
          expect.soft(line.bottom).toBeLessThanOrEqual(viewport.height);
        }
        for (const [index, action] of actions.entries()) {
          await expect.soft(action, boxes[index].name).toBeInViewport({ ratio: 1 });
        }
      } finally {
        await browser.close();
      }
    });
  }
});
