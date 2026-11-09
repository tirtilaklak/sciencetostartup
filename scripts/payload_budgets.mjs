#!/usr/bin/env node
/** Deterministic limits for the exact built artifact; never rebuild or alter it. */
import {createHash} from 'node:crypto';
import {brotliCompressSync, constants, gzipSync} from 'node:zlib';
import {readFile, readdir, realpath, stat, mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const DEFAULT_BUDGETS = path.join(ROOT, 'quality-budgets.json');
export const sha256 = value => createHash('sha256').update(value).digest('hex');

export function stableJSON(value) {
  if (Array.isArray(value)) return '[' + value.map(stableJSON).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().filter(key => value[key] !== undefined)
      .map(key => JSON.stringify(key) + ':' + stableJSON(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

export async function readBudgets(filename = DEFAULT_BUDGETS) {
  const bytes = await readFile(filename);
  const policy = JSON.parse(bytes.toString('utf8'));
  if (policy.schemaVersion !== '1.0.0') throw new Error('Unsupported quality-budget schema');
  return {policy, sha256: sha256(bytes), filename: path.resolve(filename)};
}

export function compressedSizes(bytes, compression) {
  return {
    rawBytes: bytes.length,
    gzipBytes: gzipSync(bytes, {level: compression.gzipLevel}).length,
    brotliBytes: brotliCompressSync(bytes, {params: {[constants.BROTLI_PARAM_QUALITY]: compression.brotliQuality}}).length,
  };
}

function safeName(name) {
  return typeof name === 'string' && name.length > 0 && !path.isAbsolute(name) &&
    !name.includes('\\') && !name.split('/').includes('..') && !name.startsWith('./');
}

async function inventory(directory, prefix = '') {
  const result = [];
  for (const entry of await readdir(directory, {withFileTypes: true})) {
    const name = prefix + entry.name;
    if (entry.isDirectory()) result.push(...await inventory(path.join(directory, entry.name), name + '/'));
    else if (entry.isFile()) result.push(name);
    else throw new Error('Artifact contains a non-regular payload: ' + name);
  }
  return result.sort();
}

export async function loadArtifactManifest(directory) {
  const dist = await realpath(directory);
  const bytes = await readFile(path.join(dist, 'manifest.json'));
  const manifest = JSON.parse(bytes.toString('utf8'));
  if (!manifest.sha256 || typeof manifest.sha256 !== 'object' || Array.isArray(manifest.sha256)) {
    throw new Error('Artifact manifest has no digest inventory');
  }
  const problems = [];
  for (const [name, digest] of Object.entries(manifest.sha256)) {
    if (!safeName(name) || !/^[a-f0-9]{64}$/.test(digest)) {
      problems.push('Invalid manifest member: ' + name);
      continue;
    }
    try {
      const filename = path.join(dist, name);
      const resolved = await realpath(filename);
      if (!resolved.startsWith(dist + path.sep)) throw new Error('Escapes artifact directory');
      if (!(await stat(resolved)).isFile()) throw new Error('Not a regular file');
      if (sha256(await readFile(resolved)) !== digest) problems.push('Digest mismatch: ' + name);
    } catch (error) {
      problems.push('Missing/invalid payload: ' + name + ' (' + error.message + ')');
    }
  }
  const listed = new Set(Object.keys(manifest.sha256));
  for (const name of await inventory(dist)) {
    if (name !== 'manifest.json' && !listed.has(name)) problems.push('Unmanifested payload: ' + name);
  }
  return {
    dist, manifest, manifestSha256: sha256(bytes), manifestBytes: bytes,
    buildId: manifest.build_id ?? null,
    editorialReleaseId: manifest.editorial_release_id ?? null,
    datasetVersion: manifest.dataset_version ?? null,
    problems,
  };
}

export function extractBootstrapScripts(html, families = ['data', 'app']) {
  const result = [];
  for (const family of families) {
    const pattern = new RegExp('(?:/)?js/' + family + '\\.([a-f0-9]{8,64})\\.js', 'g');
    const found = [...new Set([...html.matchAll(pattern)].map(match => match[0].replace(/^\//, '')))];
    if (found.length !== 1) throw new Error('Expected one current ' + family + ' script; found ' + found.length);
    result.push(found[0]);
  }
  return result;
}

function localReference(value, owner) {
  value = value.replaceAll('&amp;', '&').trim();
  if (!value || /^(?:data:|https?:|\/\/|#|mailto:|tel:)/i.test(value)) return null;
  const clean = value.split(/[?#]/, 1)[0];
  if (!clean) return null;
  return clean.startsWith('/') ? clean.slice(1) : path.posix.normalize(path.posix.join(path.posix.dirname(owner), clean));
}

function attributes(tag) {
  const result = {};
  for (const match of tag.matchAll(/([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g)) {
    result[match[1].toLowerCase()] = match[2] ?? match[3] ?? match[4];
  }
  return result;
}

export function resourceReferences(text, owner) {
  const found = [];
  const add = (value, kind) => {
    const resolved = localReference(value, owner);
    if (resolved) found.push({owner, path: resolved, kind});
  };
  for (const match of text.matchAll(/<(?:script|img|source|link)\b[^>]*>/gi)) {
    const tag = match[0];
    const attrs = attributes(tag);
    const tagName = /^<([a-z]+)/i.exec(tag)[1].toLowerCase();
    if (tagName === 'link' && !/(?:stylesheet|icon|preload|modulepreload)/i.test(attrs.rel || '')) continue;
    if (attrs.src) add(attrs.src, tagName);
    if (attrs.href) add(attrs.href, tagName);
    for (const list of [attrs.srcset, attrs.imagesrcset].filter(Boolean)) {
      if (/^data:/i.test(list)) continue;
      for (const item of list.split(',')) add(item.trim().split(/\s+/)[0], 'srcset');
    }
  }
  for (const match of text.matchAll(/url\(\s*['"]?([^)'"\s]+)['"]?\s*\)/gi)) add(match[1], 'css');
  return found;
}

export function archiveLeak(text) {
  let expanded = text;
  for (let pass = 0; pass < 4; pass++) expanded = expanded.replaceAll('\\"', '"');
  for (const match of expanded.matchAll(/"raw_inputs"\s*:/g)) {
    const value = expanded.slice(match.index + match[0].length).trimStart();
    if (value.startsWith('[') && value.slice(1).trimStart().startsWith(']')) continue;
    if (/^null\b/.test(value)) continue;
    return true;
  }
  return false;
}

export async function checkPayloadBudgets({dist, budgets, budgetsSha256 = null}) {
  const artifact = await loadArtifactManifest(dist);
  const problems = [...artifact.problems];
  const checks = [];
  const check = (id, actual, maximum, unit, detail = {}) => {
    const passed = Number.isFinite(actual) && actual <= maximum;
    checks.push({id, actual, maximum, unit, passed, ...detail});
    if (!passed) problems.push(id + ': ' + actual + ' exceeds ' + maximum + ' ' + unit);
  };
  if (!artifact.buildId || !artifact.editorialReleaseId) problems.push('Artifact lacks current build/editorial identity');
  const read = async name => {
    if (!safeName(name) || !artifact.manifest.sha256[name]) throw new Error('Required payload is not manifested: ' + name);
    return readFile(path.join(artifact.dist, name));
  };
  const configuration = budgets.payload;
  const compression = configuration.compression;
  const entry = configuration.bootstrap.entry;
  const entryBytes = await read(entry);
  const html = entryBytes.toString('utf8');
  const currentScripts = extractBootstrapScripts(html, configuration.bootstrap.currentScriptFamilies);
  const bootstrap = [];
  for (const name of [entry, ...currentScripts]) {
    const bytes = await read(name);
    bootstrap.push({path: name, sha256: sha256(bytes), ...compressedSizes(bytes, compression)});
    if (configuration.bootstrap.forbidCanonicalArchive && archiveLeak(bytes.toString('utf8'))) {
      problems.push('Canonical archive raw_inputs found in bootstrap payload: ' + name);
    }
  }
  const total = bootstrap.reduce((sum, row) => ({rawBytes: sum.rawBytes + row.rawBytes,
    gzipBytes: sum.gzipBytes + row.gzipBytes, brotliBytes: sum.brotliBytes + row.brotliBytes}),
  {rawBytes: 0, gzipBytes: 0, brotliBytes: 0});
  check('bootstrap.brotli', total.brotliBytes, configuration.bootstrap.maximumBrotliBytes, 'bytes');
  check('bootstrap.gzip', total.gzipBytes, configuration.bootstrap.maximumGzipBytes, 'bytes');
  const researchMatch = /<script\b[^>]*id=["']research-data["'][^>]*>([\s\S]*?)<\/script>/i.exec(html);
  if (researchMatch) {
    try {
      const graph = JSON.parse(researchMatch[1]);
      const canonical = JSON.parse((await read('research.json')).toString('utf8'));
      if (Array.isArray(graph.claims) && Array.isArray(canonical.claims) && canonical.claims.length > 0 && graph.claims.length >= canonical.claims.length &&
          Array.isArray(graph.sources) && graph.sources.length >= canonical.sources.length) {
        problems.push('Complete canonical claim/source graph is embedded in bootstrap');
      }
    } catch (error) {
      problems.push('Unable to validate inert bootstrap research graph: ' + error.message);
    }
  }
  const homeBytes = await read(configuration.home.entry);
  const home = homeBytes.toString('utf8');
  const runtimeBytes = await read(configuration.home.runtime);
  check('home.html.gzip', compressedSizes(homeBytes, compression).gzipBytes, configuration.home.maximumGzipBytes, 'bytes');
  check('home.runtime.gzip', compressedSizes(runtimeBytes, compression).gzipBytes, configuration.home.maximumRuntimeGzipBytes, 'bytes');
  const homeReferences = resourceReferences(home, configuration.home.entry);
  const heroes = [];
  for (const variant of configuration.home.heroVariants) {
    const bytes = await read(variant.path);
    const referenced = homeReferences.some(item => item.path === variant.path);
    const webp = bytes.subarray(0, 4).toString() === 'RIFF' && bytes.subarray(8, 12).toString() === 'WEBP';
    check('home.hero.' + variant.role, bytes.length, variant.maximumBytes, 'bytes', {path: variant.path});
    if (!referenced) problems.push('Home does not reference the ' + variant.role + ' hero variant: ' + variant.path);
    if (!webp) problems.push('Hero variant is not a WebP payload: ' + variant.path);
    heroes.push({...variant, actualBytes: bytes.length, referenced, webp});
  }
  let referenceCount = 0;
  for (const name of Object.keys(artifact.manifest.sha256).filter(name => /\.(?:html|css)$/.test(name))) {
    const text = (await read(name)).toString('utf8');
    for (const reference of resourceReferences(text, name)) {
      referenceCount++;
      if (!safeName(reference.path) || !artifact.manifest.sha256[reference.path]) {
        problems.push('Unmanifested resource reference: ' + name + ' → ' + reference.path);
      }
    }
  }
  return {
    schemaVersion: '1.0.0', kind: 'payload-budget-report', passed: problems.length === 0,
    policyId: budgets.policyId, budgetsSha256,
    artifact: {dist: artifact.dist, buildId: artifact.buildId, editorialReleaseId: artifact.editorialReleaseId,
      datasetVersion: artifact.datasetVersion, manifestSha256: artifact.manifestSha256,
      manifestedFiles: Object.keys(artifact.manifest.sha256).length, checkedResourceReferences: referenceCount},
    compression: {...compression, method: 'sum of independently compressed HTTP payloads', node: process.version, zlib: process.versions.zlib},
    bootstrap: {files: bootstrap, total}, heroes, checks, problems,
    note: 'Variant references do not prove responsive selection. The mobile Lighthouse report records the actual requested hero and applies its mobile byte limit.',
  };
}

function parseArguments(args) {
  const result = {output: path.join(ROOT, 'output/performance/payload-budgets.json')};
  for (let index = 0; index < args.length; index++) {
    const key = args[index];
    if (key === '--help') return {help: true};
    if (!['--dist', '--output'].includes(key) || !args[index + 1]) throw new Error('Use --dist <frozen artifact> [--output <report.json>]');
    result[key.slice(2)] = path.resolve(args[++index]);
  }
  if (!result.dist) throw new Error('--dist is required; the checker never builds an artifact');
  if (result.output === result.dist || result.output.startsWith(result.dist + path.sep)) throw new Error('Reports must be outside the frozen artifact');
  return result;
}

export async function main(args = process.argv.slice(2)) {
  const options = parseArguments(args);
  if (options.help) {
    console.log('node scripts/payload_budgets.mjs --dist <frozen artifact> [--output output/performance/payload-budgets.json]');
    return;
  }
  const {policy, sha256: policySha} = await readBudgets();
  const report = await checkPayloadBudgets({dist: options.dist, budgets: policy, budgetsSha256: policySha});
  await mkdir(path.dirname(options.output), {recursive: true});
  await writeFile(options.output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({passed: report.passed, buildId: report.artifact.buildId,
    bootstrap: report.bootstrap.total, report: options.output, problems: report.problems}));
  if (!report.passed) process.exitCode = 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => {console.error(JSON.stringify({passed: false, error: error.message})); process.exitCode = 1;});
}
