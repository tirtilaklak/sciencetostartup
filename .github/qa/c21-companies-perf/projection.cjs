const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash, webcrypto } = require('node:crypto');
const { gzipSync } = require('node:zlib');

const dist = process.argv[2];
const base = process.argv[3];
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const read = (root, name) => fs.readFileSync(path.join(root, name.replace(/^\//, '')));
const manifest = root => JSON.parse(read(root, 'manifest.json'));
const measure = bytes => ({ bytes: bytes.length, gzipBytes: gzipSync(bytes, { level: 9 }).length, sha256: digest(bytes) });
const current = manifest(dist);
const baseline = manifest(base);
function asset(root, release, name) {
  const bytes = read(root, name);
  assert.equal(digest(bytes), release.sha256[name.replace(/^\//, '')], name);
  return bytes;
}
const html = asset(dist, current, 'explore/index.html').toString();
const baselineHtml = asset(base, baseline, 'explore/index.html').toString();
const fullPath = html.match(/const full="(\/js\/data\.[a-f0-9]+\.js)"/)[1];
const directoryPath = html.match(/,directory="(\/js\/companies-data\.[a-f0-9]+\.js)"/)[1];
const baselinePath = baselineHtml.match(/href="(\/js\/data\.[a-f0-9]+\.js)"/)[1];
const full = asset(dist, current, fullPath);
const thin = asset(dist, current, directoryPath);
const old = asset(base, baseline, baselinePath);
const summary = asset(dist, current, current.summary.href);
const summaryData = JSON.parse(summary);
const realRoutes = summaryData.work;
assert.equal(realRoutes.routes.length, 136);
const decode = bytes => {
  const isolated = { window: {} };
  vm.runInNewContext(bytes.toString(), isolated);
  return isolated.window;
};
const plain = value => JSON.parse(JSON.stringify(value));
assert.deepEqual(plain(decode(full).WORK_ROUTES), realRoutes);
assert.deepEqual(plain(decode(old).WORK_ROUTES), realRoutes);
assert.equal(Object.hasOwn(decode(thin), 'WORK_ROUTES'), false);
assert.equal(decode(thin).EXPLORE_DEFER_WORK, true);
assert.deepEqual(plain(decode(thin).SUMMARY_INDEX), plain(decode(full).SUMMARY_INDEX));

const boot = html.match(/<script>(\(\(\)=>\{const full=.*?\}\)\(\);)<\/script>/)[1];
for (const [hash, expected] of [
  ['#companies', directoryPath], ['#COMPANIES/nonprofit-research?x=1', directoryPath],
  ['#work?kind=named', fullPath], ['#business-health', fullPath], ['#compare', fullPath],
  ['#company/mercor/work', fullPath], ['', fullPath], ['#companiesunknown', fullPath],
]) {
  const links = [];
  const context = { window: {}, location: { hash }, document: {
    createElement: () => ({}), head: { append: node => links.push(node.href) },
  }};
  vm.runInNewContext(boot, context);
  assert.deepEqual(links, [expected]);
  assert.equal(context.window.EXPLORE_SCRIPTS[0], expected);
}
const startup = fs.readFileSync(path.join(process.cwd(), 'web/data-runtime.js'), 'utf8')
  .replace('/* APP_BUILD_ID */null', JSON.stringify(current.build_id));

function buildContext(bytes, fetch) {
  const window = decode(bytes);
  const empty = { addEventListener() {} };
  return vm.createContext({
    window, route() {}, showEvidence() {}, openCompanyStory() {}, renderStory() {}, workRouteRows() {
      return window.WORK_ROUTES?.routes || [];
    },
    $() { return empty; }, document: { ...empty, documentElement: { dataset: { buildId: current.build_id } } },
    DATA: { dataset_version: current.dataset_version },
    fetch, crypto: webcrypto, TextDecoder, AbortController, setTimeout, clearTimeout,
  });
}

(async () => {
  const eager = buildContext(full, () => { throw Error('Unexpected Work request on eager startup'); });
  vm.runInContext(startup, eager);
  await vm.runInContext('ensureExploreWork()', eager);
  assert.deepEqual(plain(eager.window.WORK_ROUTES), realRoutes);

  const outcomes = ['offline', 'digest', 'ready'];
  const deferred = buildContext(thin, async requested => {
    assert.equal(requested, current.summary.href);
    const result = outcomes.shift();
    if (result === 'offline') throw Error('offline');
    if (result === 'digest') return { ok: true, arrayBuffer: async () => Buffer.from('wrong release') };
    assert.equal(result, 'ready');
    return { ok: true, arrayBuffer: async () => summary };
  });
  vm.runInContext(startup, deferred);
  assert.equal(vm.runInContext('exploreWorkPending()', deferred), true);
  await assert.rejects(vm.runInContext('ensureExploreWork()', deferred), /offline/);
  assert.equal(deferred.window.WORK_ROUTES, undefined);
  await assert.rejects(vm.runInContext('ensureExploreWork()', deferred), /integrity mismatch/);
  assert.equal(deferred.window.WORK_ROUTES, undefined);
  const pending = vm.runInContext('ensureExploreWork()', deferred);
  assert.equal(vm.runInContext('ensureExploreWork()', deferred), pending);
  await pending;
  assert.equal(vm.runInContext('exploreWorkPending()', deferred), false);
  assert.deepEqual(plain(deferred.window.WORK_ROUTES), realRoutes);
  assert.equal(outcomes.length, 0);

  const overlay = buildContext(thin, async () => ({ ok: true, arrayBuffer: async () => summary }));
  const detail = JSON.parse(asset(dist, current, summaryData.companyDetails.appen.href));
  const actualDetail = detail.workRoutes.routes.find(row => realRoutes.routes.some(base => base.id === row.id));
  const expectedOrder = realRoutes.routes.map(row => row.id);
  overlay.window.WORK_ROUTES = { routes: [actualDetail] };
  vm.runInContext(startup, overlay);
  await vm.runInContext('ensureExploreWork()', overlay);
  assert.deepEqual(plain(overlay.window.WORK_ROUTES.routes.map(row => row.id)), expectedOrder);
  assert.deepEqual(plain(overlay.window.WORK_ROUTES.routes.find(row => row.id === actualDetail.id)), actualDetail);

  console.log(JSON.stringify({
    baseline: { build: baseline.build_id, manifest: digest(read(base,'manifest.json')), data: measure(old) },
    candidate: { build: current.build_id, manifest: digest(read(dist,'manifest.json')), full: measure(full), thin: measure(thin), lateWorkSummary: measure(summary) },
    work: { orderedRecords: realRoutes.routes.length, ids: expectedOrder, matchesNativeProjection: true, matchesExistingEagerRows: true, preservedExactDetail: actualDetail.id },
    probes: ['eight route-specific boot choices', 'legacy eager Work without a summary request', 'late Work offline retry', 'late Work invalid digest retry', 'concurrent load deduplication', 'exact ordered Work identity with a preloaded company detail'],
  }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
