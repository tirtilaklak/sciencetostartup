import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {gzipSync} from 'node:zlib';
import {archiveLeak, checkPayloadBudgets, compressedSizes, extractBootstrapScripts,
  loadArtifactManifest, readBudgets, resourceReferences, sha256, stableJSON} from '../scripts/payload_budgets.mjs';
import {median, mobileHeroRequests, summarizeRoutes, verifyServedArtifact} from '../scripts/performance_audit.mjs';

const {policy, sha256: policySha256} = await readBudgets();

async function fixture(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'field-guide-budget-'));
  t.after(() => rm(directory, {recursive: true, force: true}));
  const webp = Buffer.alloc(32);
  webp.write('RIFF', 0); webp.writeUInt32LE(24, 4); webp.write('WEBP', 8);
  const files = {
    'index.html': '<!doctype html><picture><source srcset="/assets/human-depth-portrait-400.webp 400w, /assets/human-depth-portrait-600.webp 600w"><img src="/assets/human-depth-portrait-400.webp"></picture><script src="/home-runtime.js"></script>',
    'explore/index.html': '<!doctype html><script id="research-data" type="application/json">{"claims":[],"sources":[],"raw_inputs":[]}</script><script src="/js/data.12345678.js"></script><script src="/js/app.87654321.js"></script>',
    'work/index.html': '<!doctype html><p>Browse work</p>',
    'home-runtime.js': 'console.log("small runtime");',
    'js/data.12345678.js': 'window.guide={raw_inputs:[]};',
    'js/app.87654321.js': 'console.log("small app");',
    'assets/human-depth-portrait-400.webp': webp,
    'assets/human-depth-portrait-600.webp': webp,
    'research.json': JSON.stringify({claims: [{id: 'claim-a'}], sources: [{id: 'source-a'}], raw_inputs: [{full: 'archive'}]}),
  };
  async function save() {
    const inventory = {};
    for (const [name, content] of Object.entries(files)) {
      await mkdir(path.dirname(path.join(directory, name)), {recursive: true});
      await writeFile(path.join(directory, name), content);
      inventory[name] = sha256(content);
    }
    await writeFile(path.join(directory, 'manifest.json'), JSON.stringify({
      build_id: 'test-build', editorial_release_id: 'test-editorial', dataset_version: '2.5.0', sha256: inventory,
    }));
  }
  await save();
  return {directory, files, save};
}

test('fixed gates retain the approved limits and require all five routes', () => {
  assert.equal(policy.performance.lighthouseVersion, '13.6.0');
  assert.equal(policy.performance.playwrightVersion, '1.65.0');
  assert.equal(policy.performance.minimumRunsPerRoute, 3);
  assert.deepEqual(policy.performance.routes, ['/', '/explore/#companies', '/explore/#work', '/explore/#company/mercor/work', '/work/']);
  assert.deepEqual(Object.values(policy.performance.medianLimits).map(limit => limit.maximum), [2500, 200, 0.05]);
  assert.equal(policy.payload.bootstrap.maximumBrotliBytes, 300 * 1024);
  assert.equal(policy.payload.bootstrap.maximumGzipBytes, 360 * 1024);
  assert.equal(policy.payload.home.maximumGzipBytes, 12 * 1024);
  assert.equal(policy.payload.home.maximumRuntimeGzipBytes, 5 * 1024);
  assert.deepEqual(policy.payload.home.heroVariants.map(row => row.maximumBytes), [150000, 250000]);
});

test('median does not convert missing or invalid measurements to passing zeros', () => {
  assert.equal(median([9, 1, 3]), 3);
  assert.equal(median([2, 4]), 3);
  for (const values of [[], [null, 2], [NaN], [Infinity]]) assert.equal(median(values), null);
});

test('route gates require three complete samples and use inclusive median thresholds', () => {
  const configuration = {...policy.performance, routes: ['/']};
  const results = [1, 2, 3].map(run => ({route: '/', run, valid: true, metrics: {
    'largest-contentful-paint': [1000, 2500, 9000][run - 1],
    'total-blocking-time': 200, 'cumulative-layout-shift': 0.05,
  }}));
  assert.equal(summarizeRoutes(results, configuration, 3)[0].passed, true);
  assert.equal(summarizeRoutes(results.slice(0, 2), configuration, 2)[0].passed, false);
  const missing = structuredClone(results); missing[0].metrics['total-blocking-time'] = null;
  assert.equal(summarizeRoutes(missing, configuration, 3)[0].medians['total-blocking-time'], null);
  const invalid = structuredClone(results); invalid[2].valid = false;
  assert.equal(summarizeRoutes(invalid, configuration, 3)[0].complete, false);
  const slow = structuredClone(results); slow[0].metrics['largest-contentful-paint'] = 2501;
  slow[1].metrics['largest-contentful-paint'] = 2501;
  assert.equal(summarizeRoutes(slow, configuration, 3)[0].passed, false);
});

test('settings identity is stable across object key order while arrays remain ordered', () => {
  assert.equal(stableJSON({b: 2, a: {d: 4, c: 3}}), stableJSON({a: {c: 3, d: 4}, b: 2}));
  assert.notEqual(stableJSON([1, 2]), stableJSON([2, 1]));
});

test('bootstrap selection deduplicates preload references and rejects stale bundles', () => {
  const html = '<link href="/js/data.12345678.js"><script src="/js/data.12345678.js"></script><script src="/js/app.87654321.js"></script>';
  assert.deepEqual(extractBootstrapScripts(html), ['js/data.12345678.js', 'js/app.87654321.js']);
  assert.throws(() => extractBootstrapScripts(html + '"/js/app.11111111.js"'), /Expected one current app/);
});

test('empty compatibility archive slots are allowed, nonempty canonical inputs are rejected', () => {
  for (const text of ['{"raw_inputs":[]}', '{"raw_inputs": [ \n ]}', '{"raw_inputs":null}', JSON.stringify('{"raw_inputs":[]}')]) {
    assert.equal(archiveLeak(text), false, text);
  }
  for (const text of ['{"raw_inputs":[{"source":"full archive"}]}', '{"raw_inputs":{}}', JSON.stringify('{"raw_inputs":[{"source":"full archive"}]}')]) {
    assert.equal(archiveLeak(text), true, text);
  }
});

test('resource inventory covers relative styles and responsive sources without counting navigation', () => {
  const refs = resourceReferences('<link rel="stylesheet" href="../site.css"><a href="/work/">Browse</a><source srcset="/a.webp 400w, /b.webp 600w"><img src="https://external.test/a.png"><style>x{background:url(../c.svg)}</style>', 'explore/index.html');
  assert.deepEqual(refs.map(ref => ref.path), ['site.css', 'a.webp', 'b.webp', 'c.svg']);
});

test('payload checks sum independently compressed HTTP files and pass a valid manifested artifact', async t => {
  const f = await fixture(t);
  const report = await checkPayloadBudgets({dist: f.directory, budgets: policy, budgetsSha256: policySha256});
  assert.equal(report.passed, true, JSON.stringify(report.problems));
  const names = ['explore/index.html', 'js/data.12345678.js', 'js/app.87654321.js'];
  const expected = names.map(name => compressedSizes(Buffer.from(f.files[name]), policy.payload.compression));
  assert.equal(report.bootstrap.total.gzipBytes, expected.reduce((sum, row) => sum + row.gzipBytes, 0));
  assert.equal(report.bootstrap.total.brotliBytes, expected.reduce((sum, row) => sum + row.brotliBytes, 0));
  assert.equal(report.budgetsSha256, policySha256);
});

test('manifest validation rejects byte changes and unlisted assets', async t => {
  const f = await fixture(t);
  await writeFile(path.join(f.directory, 'home-runtime.js'), 'changed after build');
  await writeFile(path.join(f.directory, 'unexpected.js'), 'unlisted');
  const artifact = await loadArtifactManifest(f.directory);
  assert(artifact.problems.includes('Digest mismatch: home-runtime.js'));
  assert(artifact.problems.includes('Unmanifested payload: unexpected.js'));
});

test('full canonical graph fails even when its raw input slot is empty', async t => {
  const f = await fixture(t);
  f.files['explore/index.html'] = f.files['explore/index.html'].replace('"claims":[],"sources":[]', '"claims":[{"id":"claim-a"}],"sources":[{"id":"source-a"}]');
  await f.save();
  const report = await checkPayloadBudgets({dist: f.directory, budgets: policy});
  assert.equal(report.passed, false);
  assert(report.problems.includes('Complete canonical claim/source graph is embedded in bootstrap'));
});

test('mobile hero records report the actually selected variant and uncompressed bytes', () => {
  const artifact = {manifest: {sha256: {'assets/human-depth-portrait-600.webp': 'digest'}}};
  const lhr = {audits: {'network-requests': {details: {items: [{
    url: 'http://localhost/assets/human-depth-portrait-600.webp', resourceSize: 102940, transferSize: 103100,
  }]}}}};
  const [hero] = mobileHeroRequests(lhr, artifact, policy.payload.home, 'http://localhost');
  assert.equal(hero.path, 'assets/human-depth-portrait-600.webp');
  assert.equal(hero.manifested, true);
  assert.equal(hero.resourceBytes, 102940);
  assert.equal(hero.maximumBytes, 150000);
});

test('served-artifact preflight compares decoded gzip bytes with the frozen manifest', async t => {
  const f = await fixture(t);
  const artifact = await loadArtifactManifest(f.directory);
  let corrupt = false;
  const server = http.createServer(async (request, response) => {
    const name = request.url.slice(1);
    const bytes = corrupt && name === 'index.html' ? Buffer.from('wrong build') : await readFile(path.join(f.directory, name));
    response.writeHead(200, {'content-encoding': 'gzip', 'content-type': 'application/octet-stream'});
    response.end(gzipSync(bytes));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => {server.closeAllConnections(); await new Promise(resolve => server.close(resolve));});
  const base = 'http://127.0.0.1:' + server.address().port;
  const checked = await verifyServedArtifact(base, artifact, ['index.html']);
  assert.equal(checked[1].sha256, artifact.manifest.sha256['index.html']);
  assert.equal(checked[1].contentEncoding, 'gzip');
  corrupt = true;
  await assert.rejects(verifyServedArtifact(base, artifact, ['index.html']), /Served bytes differ/);
});
