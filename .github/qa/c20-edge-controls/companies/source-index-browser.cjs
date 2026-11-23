'use strict';

const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {readFileSync} = require('node:fs');

const {origin, assets, cases, repo} = JSON.parse(readFileSync(0, 'utf8'));
const {chromium} = require(require.resolve('playwright', {paths: [repo]}));
const beacon = /<script type="module" src="https:\/\/static\.cloudflareinsights\.com\/beacon\.min\.js\/v[0-9a-f]+" integrity="sha512-[A-Za-z0-9+/]{86}==" data-cf-beacon='\{"version":"[0-9]+\.[0-9]+\.[0-9]+","token":"[0-9a-f]{32}","r":1,"spa":2\}' crossorigin="anonymous"><\/script>\n(?=<\/body>\n?<\/html>\n$)/;
const sha = value => createHash('sha256').update(value).digest('hex');

async function checked(response, url, asset) {
  assert(response && response.status() === 200 && response.url() === url, url);
  const bytes = await response.body();
  const original = sha(bytes);
  const signed = assets[asset];
  const body = original === signed ? bytes : Buffer.from(bytes.toString().replace(beacon, ''));
  assert.equal(sha(body), signed, url);
  return {receivedSha256: original, manifestSha256: signed, cloudflareAnalyticsBytes: bytes.length - body.length};
}

async function check() {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({javaScriptEnabled: false, viewport: {width: 390, height: 844}});
    await context.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const rows = [];
    for (const info of cases) {
      const dossierURL = origin + info.dossierRoute;
      const sourceURL = origin + info.indexRoute;
      const dossier = await page.goto(dossierURL, {waitUntil: 'domcontentloaded'});
      const nativeHttp = await checked(dossier, dossierURL, info.profileAsset);
      const summary = page.locator('summary[data-native-sources]');
      const sourceCount = Object.keys(info.workSources).length;
      const indexLink = summary.locator('..').getByRole('link', {name: `${sourceCount} paid work sources`, exact: true});
      assert(await indexLink.isHidden());
      await summary.focus();
      await page.keyboard.press('Enter');
      await indexLink.waitFor({state: 'visible'});
      assert.equal(await indexLink.getAttribute('href'), info.indexRoute);
      assert(await summary.evaluate(node => node === document.activeElement));
      await page.keyboard.press('Tab');
      assert(await indexLink.evaluate(node => node === document.activeElement));
      const catalog = await page.locator('ol[data-native-source-list] li[data-native-source]').evaluateAll(items =>
        Object.fromEntries(items.map(item => [item.dataset.nativeSource, item.querySelector('a').getAttribute('href')])));
      assert.deepEqual(catalog, info.generalSources);

      const [index] = await Promise.all([page.waitForNavigation({url: sourceURL, waitUntil: 'domcontentloaded'}), page.keyboard.press('Enter')]);
      const indexHttp = await checked(index, sourceURL, info.indexAsset);
      const heading = page.locator('main h1');
      await heading.waitFor({state: 'visible'});
      const indexed = await page.locator('ol[data-native-source-list] li[data-native-source]').evaluateAll(items => items.map(item =>
        ({id: item.id, sourceId: item.dataset.nativeSource, href: item.querySelector('a').getAttribute('href')})));
      assert.equal(indexed.length, sourceCount);
      assert(indexed.every(row => row.id === row.sourceId));
      assert.deepEqual(Object.fromEntries(indexed.map(row => [row.id, row.href])), info.workSources);
      for (const row of [indexed[0], indexed.at(-1)]) {
        const targetURL = `${sourceURL}#${row.id}`;
        await page.goto(targetURL, {waitUntil: 'commit'});
        assert.equal(page.url(), targetURL);
        assert.equal(await page.locator(':target a').getAttribute('href'), row.href);
      }
      rows.push({company: info.company, browser: browser.version(), javaScript: false,
                 sourceDisclosureActivatedByKeyboard: true, linkReachedByTabCount: 1,
                 linkActivatedByKeyboard: true, destination: sourceURL, heading: await heading.innerText(),
                 nativeHttp, indexHttp, generalSources: Object.keys(catalog).length, workSources: indexed.length,
                 sampledSourceFragments: [indexed[0].id, indexed.at(-1).id]});
    }
    process.stdout.write(JSON.stringify(rows));
  } finally {
    await browser.close();
  }
}

check().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
