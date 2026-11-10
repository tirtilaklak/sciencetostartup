"""Classic globals, ordered overrides, semantic fixtures and pinned build tooling."""
import json
import base64
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from frontend_packaging import ESBUILD_VERSION, minify_css, minify_javascript, package_frontend
from observatory import INITIAL_PRESENTATION_JS, PRESENTATION_JS, build, presentation_preload_config, write_business_health_module
from test_static_pages import APP_RULES


class FrontendPackagingTests(unittest.TestCase):
    def test_pinned_dependency_is_installed_and_output_is_deterministic(self):
        self.assertEqual(json.loads((ROOT / "package.json").read_text())["devDependencies"]["esbuild"], ESBUILD_VERSION)
        self.assertEqual(json.loads((ROOT / "package-lock.json").read_text())["packages"]["node_modules/esbuild"]["version"], ESBUILD_VERSION)
        source = 'function route(value) { return value + 1; } const state = {ready: true};'
        first = minify_javascript(source)
        self.assertEqual(first, minify_javascript(source))
        self.assertIn('function route(', first)
        self.assertIn('const state=', first)

    def test_missing_node_reports_the_install_step(self):
        with patch('frontend_packaging.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, r'Node.js 22.*npm ci'):
                package_frontend(javascript={"app": 'const state = {};'} )

    def test_package_pin_mismatch_fails_before_transforming(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts/frontend_packaging.mjs", folder / "scripts/frontend_packaging.mjs")
            (folder / "package.json").write_text(json.dumps({"devDependencies": {"esbuild": "0.0.0"}}))
            (folder / "package-lock.json").write_text(json.dumps({"packages": {"node_modules/esbuild": {"version": ESBUILD_VERSION}}}))
            result = subprocess.run([shutil.which('node'), str(folder / "scripts/frontend_packaging.mjs")], input='{}', text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('exactly esbuild ' + ESBUILD_VERSION, result.stderr)
            self.assertIn('npm ci', result.stderr)

    def test_following_classic_script_sees_globals_and_override_order(self):
        source = '''const state={value:7};var events=[];
function route(){events.push('base');return state.value}
const editorialBase=route;route=function(){events.push('editorial');return editorialBase()};
const runtimeBase=route;route=function(){events.push('runtime');return runtimeBase()};
function showEvidence(){return 'source'}
function initialize(){events.push('init');return route()}'''
        probe = "JSON.stringify({result:initialize(),events,route:typeof route,state:state.value,evidence:showEvidence(),init:typeof initialize,name:initialize.name})"
        runner = "const fs=require('node:fs'),vm=require('node:vm');const context=vm.createContext({});vm.runInContext(fs.readFileSync(0,'utf8'),context);process.stdout.write(vm.runInContext(process.argv[1],context));"
        result = subprocess.run(['node', '-e', runner, probe], input=minify_javascript(source), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), {"result": 7, "events": ['init', 'runtime', 'editorial', 'base'], "route": 'function', "state": 7, "evidence": 'source', "init": 'function', "name": 'initialize'})

    def test_actual_classic_modules_keep_public_bindings_and_semantic_fixtures(self):
        modules = ['web/app.js', 'web/editorial.js', 'web/work-v3.js'] + ['web/' + name for name in PRESENTATION_JS] + ['web/data-runtime.js']
        source = '\n'.join((ROOT / name).read_text() for name in modules)
        # Same minimal DOM harness as the independent source/data parity tests.
        prefix = APP_RULES.split("vm.runInContext(JSON.parse(modules).map(read).join('\\n'),context);")[0]
        prefix += "window.SUMMARY_INDEX={schemaVersion:'1.0.0',buildId:null,datasetVersion:'2.5.0',companyDetails:{},statistics:{}};window.SEARCH_INDEX={};document.documentElement={dataset:{buildId:null}};"
        runner = prefix + "vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),context);process.stdout.write(vm.runInContext(`JSON.stringify({types:[typeof route,typeof state,typeof showEvidence,typeof initialize,typeof profileProducts,typeof renderCompare],globals:[typeof globalThis.route,typeof globalThis.showEvidence,typeof globalThis.initialize],stateIsProperty:Object.hasOwn(globalThis,'state'),overrides:[route!==synchronousRoute,synchronousRoute!==originalRoute,showEvidence!==synchronousEvidence,comparisonRows!==profileComparisonRows,renderCompare!==originalRenderCompare],products:profileProducts('snorkel_ai').map(p=>[p.name,p.description]),work:workSummary('appen'),search:siteSearchIndex().map(r=>[r.type,r.id,r.name,r.href])})`,context));"
        with tempfile.TemporaryDirectory() as temporary:
            values = []
            for name, code in [('source', source), ('minified', minify_javascript(source))]:
                path = Path(temporary) / (name + '.js')
                path.write_text(code)
                result = subprocess.run(['node', '-e', runner, str(ROOT), json.dumps(modules), str(path)], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                values.append(json.loads(result.stdout))
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[1]['types'], ['function', 'object', 'function', 'function', 'function', 'function'])
        self.assertEqual(values[1]['globals'], ['function'] * 3)
        self.assertFalse(values[1]['stateIsProperty'])
        self.assertTrue(all(values[1]['overrides']))

    def test_css_whitespace_packaging_keeps_cascade_and_values(self):
        source = '.x { color: yellow; margin: 0px; } @media (width < 30em) { .x { color: blue; } }'
        result = minify_css(source)
        self.assertEqual(result, '.x{color:yellow;margin:0px}@media(width<30em){.x{color:blue}}\n')

    def test_deferred_health_factory_is_inert_checksummed_and_scope_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            descriptor = write_business_health_module(folder, 'factory-test')
            path = folder / descriptor['href'].lstrip('/')
            content = path.read_bytes()
            digest = hashlib.sha256(content)
            self.assertEqual(descriptor['sha256'], digest.hexdigest())
            self.assertEqual(descriptor['integrity'], 'sha256-' + base64.b64encode(digest.digest()).decode('ascii'))
            self.assertEqual(descriptor['bytes'], len(content))
            self.assertEqual(path.name, 'health.' + digest.hexdigest()[:12] + '.js')
            runner = r'''const fs=require('node:fs'),vm=require('node:vm');
const window={};Object.defineProperty(window,'BUSINESS_HEALTH',{get(){throw Error('Factory read data before initialization')}});
const document=new Proxy({},{get(){throw Error('Factory touched the DOM before initialization')}});
const context=vm.createContext({window,document});const before=Object.keys(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
process.stdout.write(JSON.stringify({build:window.SCIENCE_HEALTH_MODULE.buildId,initialize:typeof window.SCIENCE_HEALTH_MODULE.initialize,health:typeof window.BusinessHealth,extraGlobals:Object.keys(context).filter(k=>!before.includes(k))}));'''
            result = subprocess.run(['node', '-e', runner, str(path)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'build': 'factory-test', 'initialize': 'function', 'health': 'undefined', 'extraGlobals': []})

    def test_build_packages_the_initial_and_deferred_sources_with_provenance(self):
        initial = tuple(name for name in PRESENTATION_JS if name not in {'detail-views.js', 'source-update-details.js', 'profile-details.js', 'business-health.js'})
        self.assertEqual(INITIAL_PRESENTATION_JS, initial)
        self.assertEqual(PRESENTATION_JS[-1], 'business-health.js')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            build(json.loads((ROOT / 'data/canonical.json').read_text()), folder)
            manifest = json.loads((folder / 'manifest.json').read_text())
            summary = json.loads((folder / manifest['summary']['href'].lstrip('/')).read_text())
            descriptor = summary['modules']['businessHealth']
            content = (folder / descriptor['href'].lstrip('/')).read_bytes()
            self.assertEqual(manifest['sha256'][descriptor['href'].lstrip('/')], hashlib.sha256(content).hexdigest())
            self.assertEqual(manifest['source_sha256']['web/business-health.js'], hashlib.sha256((ROOT / 'web/business-health.js').read_bytes()).hexdigest())
            self.assertEqual(manifest['source_sha256']['web/profile-details.js'], hashlib.sha256((ROOT / 'web/profile-details.js').read_bytes()).hexdigest())
            self.assertEqual(manifest['source_sha256']['web/detail-views.js'], hashlib.sha256((ROOT / 'web/detail-views.js').read_bytes()).hexdigest())
            self.assertEqual(manifest['source_sha256']['web/source-update-details.js'], hashlib.sha256((ROOT / 'web/source-update-details.js').read_bytes()).hexdigest())
            html = (folder / 'explore/index.html').read_text()
            app_href = re.search(r'href="(/js/app\.[^"]+\.js)"', html).group(1)
            template = (ROOT / 'web/index.html').read_text()
            source = re.search(r'<script data-bundle="app">(.*?)</script>', template, re.S).group(1)
            source = source.replace('/* OBSERVATORY_JS */', (ROOT / 'web/link-health.js').read_text() + '\n' + (ROOT / 'web/app.js').read_text())
            source = source.replace('/* EDITORIAL_JS */', (ROOT / 'web/editorial.js').read_text())
            source = source.replace('/* WORK_V3_JS */', (ROOT / 'web/work-v3.js').read_text() + ''.join((ROOT / 'web' / name).read_text() for name in initial))
            source = source.replace('/* DATA_RUNTIME_JS */', (ROOT / 'web/data-runtime.js').read_text().replace('/* APP_BUILD_ID */null', json.dumps(manifest['build_id'])))
            self.assertEqual((folder / app_href.lstrip('/')).read_text(), minify_javascript(source))
            # The runtime descriptor is the same one referenced by the summary,
            # not a second unbound factory URL embedded only in the page.
            data_href = re.search(r'href="(/js/data\.[^"]+\.js)"', html).group(1)
            data_code = (folder / data_href.lstrip('/')).read_text()
            self.assertIn(descriptor['href'], data_code)
            prefetch_source = (ROOT / 'web/presentation-prefetch.js').read_text()
            prefetch = ';(()=>{' + minify_javascript(prefetch_source) + '})();</script>'
            self.assertIn(prefetch, html)
            self.assertNotIn('PRESENTATION_PRELOAD_CONFIG', data_code)
            marker = 'window.PRESENTATION_PRELOAD_CONFIG='
            config_start = html.index(marker) + len(marker)
            config, _ = json.JSONDecoder().raw_decode(html[config_start:])
            aliases = json.loads((ROOT / 'docs/research-id-crosswalk.json').read_text())
            self.assertEqual(config, presentation_preload_config(summary, aliases))
            self.assertLess(config_start, html.index('<style'))
            self.assertLess(html.index('rel="preload" as="script"'), config_start)
            self.assertEqual(manifest['source_sha256']['web/presentation-prefetch.js'], hashlib.sha256((ROOT / 'web/presentation-prefetch.js').read_bytes()).hexdigest())
            self.assertTrue(all(descriptor['href'] not in tag for tag in re.findall(r'<link[^>]*rel="preload"[^>]*>', html)))

    def test_head_discovery_config_contains_only_bound_descriptors(self):
        summary = {'buildId': 'bound-build', 'companyDetails': {'company': {'href': '/company.json', 'sha256': 'company-sha', 'narrative': 'must not ship in head'}}, 'overview': {'href': '/overview.json', 'sha256': 'overview-sha', 'data': 'not in head'}, 'archive': {'href': '/archive.json', 'sha256': 'archive-sha', 'claims': 'not in head'}, 'modules': {'businessHealth': {'href': '/health.js', 'integrity': 'sha256-bound', 'bytes': 100, 'sha256': 'health-sha'}}}
        config = presentation_preload_config(summary, {'alias': 'company', 'record-alias': 'company.claim'})
        self.assertEqual(set(config), {'buildId', 'companyDetails', 'overview', 'archive', 'modules', 'aliases'})
        self.assertEqual(config['companyDetails'], {'company': {'href': '/company.json', 'sha256': 'company-sha'}})
        self.assertEqual(config['overview'], {'href': '/overview.json', 'sha256': 'overview-sha'})
        self.assertEqual(config['archive'], {'href': '/archive.json', 'sha256': 'archive-sha'})
        self.assertEqual(config['modules'], {'businessHealth': {'href': '/health.js', 'integrity': 'sha256-bound'}})
        self.assertEqual(config['aliases'], {'alias': 'company'})


if __name__ == '__main__':
    unittest.main()
