// Visit the exact authored and directly linked Explore destinations.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require(path.join(process.cwd(), 'node_modules', 'playwright'));

const base = 'http://127.0.0.1:19011';
const inventory = JSON.parse(fs.readFileSync(process.env.QA_EXPLORE_INVENTORY));
const digest = buffer => crypto.createHash('sha256').update(buffer).digest('hex');
const signed = fs.readFileSync('dist/manifest.json');
if (inventory.head !== process.env.C21_HEAD || inventory.manifest !== digest(signed)) {
  throw Error('Explore inventory does not identify this exact artifact.');
}
const phone = process.env.QA_VIEWPORT === 'phone';
const viewport = phone ? { width: 390, height: 844 } : { width: 1280, height: 900 };
const routes = new Map(Object.entries(inventory.routes));
const prior = process.env.QA_EXPLORE_PRIOR ? JSON.parse(fs.readFileSync(process.env.QA_EXPLORE_PRIOR)) : null;
if (prior) {
  if (prior.head !== process.env.QA_PREVIOUS_PROOF_HEAD || prior.manifest !== inventory.manifest ||
      !prior.passed || prior.before.sha256 !== inventory.manifest || prior.after.sha256 !== inventory.manifest ||
      prior.viewport.width !== viewport.width || prior.viewport.height !== viewport.height ||
      !prior.results.every(row => row.passed)) throw Error('Previous route proof does not identify these signed bytes.');
  for (const row of prior.results) if (!routes.has(row.fragment)) routes.set(row.fragment, row.linkedFrom);
}
const aliases = { 'business-health': 'market', venture: 'market', about: 'method',
  labels: 'method', corrections: 'method', coverage: 'method', downloads: 'method' };
const views = new Set(['market', 'companies', 'work', 'compare', 'method', 'company', ...Object.keys(aliases)]);
const primaryPanes = ['business', 'traction', 'people', 'work'];
const sections = ['business', 'products', 'customers', 'risks', 'traction', 'growth',
  'people', 'finance', 'capital', 'work', 'method', 'questions', 'sources', 'observations', 'financing'];

async function observe(context, edge) {
  const response = await context.request.get(base + '/manifest.json');
  const body = await response.body();
  if (response.status() !== 200 || !body.equals(signed)) throw Error('Explore manifest changed at ' + edge);
  return { edge, http: response.status(), sha256: digest(body), utc: new Date().toISOString() };
}

function contract(fragment) {
  const at = fragment.indexOf('?');
  const route = at < 0 ? fragment : fragment.slice(0, at);
  const query = new URLSearchParams(at < 0 ? '' : fragment.slice(at + 1));
  const parts = route.split('/').map((part, index) => {
    if (!index) return part.toLowerCase();
    try { return decodeURIComponent(part); } catch { return part; }
  });
  const [key, id, section, claim] = parts;
  return {
    key, view: key === 'company' ? 'profile' : aliases[key] || key,
    anchor: aliases[key] ? key : null, id, section, claim,
    primaryPanes, sections, correction: key === 'corrections' ? query.get('claim') : null,
  };
}

async function reach(page, fragment) {
  const expected = contract(fragment);
  await page.goto(base + '/explore/#' + fragment, { waitUntil: 'commit', timeout: 12000 });
  await page.waitForFunction(want => {
    if (!window.SUMMARY_INDEX) return false;
    const shown = selector => {
      const node = typeof selector === 'string' ? document.querySelector(selector) : selector;
      return !!node && !node.hidden && node.getClientRects().length > 0;
    };
    if (!shown(document.getElementById(want.view + '-view')) || shown('#app-failure')) return false;
    const fragment = location.hash.slice(1);
    const family = fragment.split(/[/?]/)[0].toLowerCase();
    if (family !== want.key) return false;
    if (want.anchor && !shown(document.getElementById(want.anchor))) return false;
    if (want.correction && !document.querySelector('#corrections [data-explore-correction-issue] a')?.href
          .includes(encodeURIComponent(want.correction))) return false;
    if (want.key !== 'company') return true;
    const typed = want.id?.toLowerCase();
    const id = window.RESEARCH_ALIASES?.[typed] || typed;
    if (document.querySelector('#profile-view .profile-v2')?.dataset.profileCompany !== id) return false;
    const section = want.section?.toLowerCase();
    if (section === 'claim') {
      let loaded;
      try { loaded = decodeURIComponent(fragment.split('?')[0].split('/')[3]); } catch { return false; }
      return loaded === want.claim && shown('#evidence-dialog[open]');
    }
    if (want.sections.includes(section)) {
      const anchor = section === 'capital' ? 'finance' : section;
      const attr = want.primaryPanes.includes(anchor) ? 'data-profile-pane' : 'data-profile-section';
      return shown('#profile-view [' + attr + '="' + anchor + '"]');
    }
    return true;
  }, expected, { timeout: 4200 });
  return { final: page.url(), title: await page.title() };
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport, isMobile: phone, hasTouch: phone });
  const page = await context.newPage();
  const first = await observe(context, 'before');
  const output = process.env.QA_EXPLORE_OUTPUT;
  const results = prior ? [...prior.results] : [];
  const alreadyTested = new Set(results.map(row => row.fragment));
  let discovery = 0;
  let companiesObserved = 0;
  let tabsObserved = 0;
  let newSections = 0;
  try {
    for (const section of ['market', 'companies', 'work', 'compare', 'method']) {
      await reach(page, section);
      const anchors = await page.locator('#' + section + '-view a[href], header a[href]').evaluateAll(links =>
        links.map(link => link.href));
      for (const address of anchors) {
        const url = new URL(address);
        const route = url.hash.slice(1);
        const family = route.split(/[/?]/)[0].toLowerCase();
        if (route && views.has(family) && url.pathname.replace(/\/$/, '') === '/explore' &&
            [base, 'https://sciencetostartup.com', 'https://www.sciencetostartup.com'].includes(url.origin) &&
            !routes.has(route)) {
          routes.set(route, ['interactive ' + section + ' view']);
          discovery += 1;
        }
      }
    }
    if (prior) {
      await reach(page, 'companies');
      const companies = await page.evaluate(() => Object.keys(window.SUMMARY_INDEX.companyDetails).sort());
      for (const id of companies) {
        const profile = 'company/' + encodeURIComponent(id);
        await reach(page, profile);
        if (!routes.has(profile)) routes.set(profile, ['published company profile']);
        const tabs = await page.locator('#profile-view [data-profile-tab]').evaluateAll(nodes =>
          nodes.map(node => node.dataset.profileTab));
        if (tabs.length !== primaryPanes.length || !primaryPanes.every(tab => tabs.includes(tab))) {
          throw Error('Published profile does not show all primary tabs: ' + id);
        }
        companiesObserved += 1;
        for (const tab of tabs) {
          tabsObserved += 1;
          if (!primaryPanes.includes(tab)) throw Error('Unknown profile tab: ' + tab);
          const destination = profile + '/' + tab;
          if (!routes.has(destination)) {
            routes.set(destination, ['rendered company tab ' + id + '/' + tab]);
            discovery += 1;
          }
          if (process.env.QA_DISCOVER_PROFILE_SECTIONS === '1') {
            await reach(page, destination);
            const landmarks = await page.locator('#profile-view [data-profile-section]').evaluateAll(nodes =>
              nodes.map(node => node.dataset.profileSection));
            for (const section of landmarks) {
              if (!sections.includes(section)) continue;
              const typedRoute = profile + '/' + section;
              if (!routes.has(typedRoute)) {
                routes.set(typedRoute, ['rendered profile section ' + id + '/' + tab]);
                discovery += 1;
                newSections += 1;
              }
            }
          }
        }
      }
    }
    for (const [fragment, linkedFrom] of [...routes.entries()].sort(([a], [b]) => a.localeCompare(b))) {
      if (alreadyTested.has(fragment)) continue;
      try {
        const result = await reach(page, fragment);
        results.push({ fragment, linkedFrom, passed: true, ...result });
      } catch (error) {
        const result = { fragment, linkedFrom, passed: false, url: page.url(),
          error: String(error).split('\n')[0],
          view: await page.locator('main .view:not([hidden])').count().catch(() => -1) };
        results.push(result);
        if (results.filter(row => !row.passed).length <= 2) {
          await page.screenshot({ path: path.join(output, 'failure-' + results.length + '.png') }).catch(() => {});
        }
      }
    }
  } finally {
    const last = await observe(context, 'after');
    const summary = { passed: results.length === routes.size && results.every(result => result.passed),
      head: inventory.head, manifest: inventory.manifest, viewport, before: first, after: last,
      authored: Object.keys(inventory.routes).length, extraVisibleRoutes: discovery, priorPassed: alreadyTested.size,
      companiesObserved, tabsObserved, newSections,
      destinations: routes.size, passedDestinations: results.filter(result => result.passed).length, results };
    fs.writeFileSync(path.join(output, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
    const failures = results.filter(result => !result.passed).map(({ fragment, error }) => ({ fragment, error }));
    console.log(JSON.stringify({ viewport, destinations: routes.size,
      passed: summary.passedDestinations, companiesObserved, tabsObserved, newSections, failures: failures.slice(0, 10) }));
    process.exitCode = summary.passed ? 0 : 1;
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
