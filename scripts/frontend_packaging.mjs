/* Build-time classic-script and CSS packaging. Never bundle or select a module format. */
import fs from 'node:fs';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
const PINNED_ESBUILD = '0.28.2';

function packageFrontend(request) {
  if (Number(process.versions.node.split('.')[0]) < 22) {
    throw new Error('Frontend packaging requires Node.js 22 or newer. Install Node.js, then run npm ci.');
  }
  const packageInfo = require('../package.json');
  const lock = require('../package-lock.json');
  if (packageInfo.devDependencies?.esbuild !== PINNED_ESBUILD || lock.packages?.['node_modules/esbuild']?.version !== PINNED_ESBUILD) {
    throw new Error(`Frontend packaging requires exactly esbuild ${PINNED_ESBUILD} in package.json and package-lock.json. Restore the pinned dependency, then run npm ci.`);
  }
  let esbuild;
  try { esbuild = require('esbuild'); }
  catch { throw new Error(`Pinned esbuild ${PINNED_ESBUILD} is missing. Run npm ci in the repository root before building.`); }
  if (esbuild.version !== PINNED_ESBUILD) {
    throw new Error(`Installed esbuild ${esbuild.version} differs from pinned ${PINNED_ESBUILD}. Run npm ci in the repository root.`);
  }
  const result = {version: esbuild.version, javascript: {}, stylesheets: {}};
  for (const [name, source] of Object.entries(request.javascript || {})) {
    if (typeof source !== 'string') throw new Error(`JavaScript input ${name} must be text.`);
    // Omitting format is essential: following classic scripts still access the
    // existing top-level declarations and the ordered presentation overrides.
    result.javascript[name] = esbuild.transformSync(source, {
      loader: 'js', target: 'es2022', minifyWhitespace: true,
      minifySyntax: true, minifyIdentifiers: true,
      treeShaking: false, legalComments: 'inline',
    }).code;
  }
  for (const [name, source] of Object.entries(request.stylesheets || {})) {
    if (typeof source !== 'string') throw new Error(`Stylesheet input ${name} must be text.`);
    result.stylesheets[name] = esbuild.transformSync(source, {
      loader: 'css', minifyWhitespace: true, minifySyntax: false,
      minifyIdentifiers: false, legalComments: 'inline',
    }).code;
  }
  return result;
}

try {
  process.stdout.write(JSON.stringify(packageFrontend(JSON.parse(fs.readFileSync(0, 'utf8')))));
} catch (error) {
  process.stderr.write(`Frontend packaging failed: ${error.message}\n`);
  process.exitCode = 1;
}
