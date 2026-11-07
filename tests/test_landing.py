"""The simplified homepage stays lightweight while preserving the full current guide."""
import json
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from build_identity import snapshot_dist


class Structure(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.in_main = False
        self.main_count = 0
        self.main_ids = set()
        self.local_references = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "main":
            self.in_main = True
            self.main_count += 1
        if self.in_main and attrs.get("id"):
            self.main_ids.add(attrs["id"])
        if tag == "a" and attrs.get("href"):
            self.local_references.append(attrs["href"])
        if tag in ("img", "script") and attrs.get("src"):
            self.local_references.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.local_references.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "main":
            self.in_main = False


class LandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = (ROOT / "dist/index.html").read_text()
        cls.guide = (ROOT / "dist/explore/index.html").read_text()

    def test_home_has_one_complete_main_and_the_supplied_image(self):
        structure = Structure(self.home)
        self.assertEqual(structure.main_count, 1)
        self.assertTrue({"hero-title", "paths-title", "research-title"} <= structure.main_ids)
        self.assertIn('src="assets/human-depth.png"', self.home)
        self.assertEqual((ROOT / "dist/assets/human-depth.png").read_bytes(),
                         (ROOT / "web/assets/human-depth.png").read_bytes())

    def test_home_is_small_and_loads_no_research_runtime(self):
        self.assertLess(len(self.home.encode("utf-8")), 15_000)
        self.assertNotIn('id="research-data"', self.home)
        self.assertNotIn('data-bundle=', self.home)
        self.assertNotRegex(self.home, r'["\']js/(?:app|data)[.]')
        self.assertNotIn("fetch(", self.home)
        self.assertNotIn("XMLHttpRequest", self.home)

    def test_all_local_home_references_exist(self):
        for link in Structure(self.home).local_references:
            url = urlparse(link)
            if url.scheme or not url.path:
                continue
            with self.subTest(link=link):
                self.assertTrue((ROOT / "dist" / unquote(url.path).lstrip("/")).exists())

    def test_guide_keeps_current_research_and_has_its_own_identity(self):
        embedded = re.search(r'<script id="research-data" type="application/json">(.*?)</script>', self.guide, re.S)
        self.assertIsNotNone(embedded)
        self.assertEqual(json.loads(embedded.group(1)), json.loads((ROOT / "data/canonical.json").read_text()))
        self.assertIn('rel="canonical" href="https://sciencetostartup.com/explore/"', self.guide)
        self.assertIn('name="robots" content="noindex,follow"', self.guide)
        self.assertTrue('class="wordmark" href="/"' in self.guide, 'Guide brand must return to root')
        self.assertIn('id="business-health"', self.guide)
        self.assertIn('id="site-search"', self.guide)
        self.assertTrue(snapshot_dist(ROOT / "dist")["valid"])

    def test_nested_guide_resources_stay_at_site_root(self):
        for link in Structure(self.guide).local_references:
            url = urlparse(link)
            if url.scheme or not url.path:
                continue
            self.assertTrue(url.path.startswith("/"), "Non-rooted guide resource: " + link)
            self.assertTrue((ROOT / "dist" / unquote(url.path).lstrip("/")).exists(), link)
        self.assertTrue('script.src="/"+src' in self.guide, "Runtime bundles must load from site root")
        self.assertTrue('link.href="/"+href' in self.guide, "Bundle preloads must use site root")

    def test_brand_palette_for_home_matches_documented_tokens(self):
        css = (ROOT / "web/landing.css").read_text()
        declared = dict(re.findall(r"--(landing-[\w-]+):([^;}]+)", css))
        tokens = json.loads((ROOT / "design-system/tokens.json").read_text())
        documented = {t["name"]: t["value"] for t in tokens["color"]["tokens"] if t["name"].startswith("landing-")}
        self.assertEqual(declared, documented)

    def test_legacy_hashes_and_search_queries_survive_initial_load_and_hashchange(self):
        script = next(s for s in re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', self.home, re.S)
                      if "redirectLegacyRoute" in s)
        code = r"""
const vm=require('node:vm'), assert=require('node:assert/strict');
const script=JSON.parse(process.argv[1]);
const legacy=['market','companies','work','compare','method','company/mercor',
              'company/mercor/work','compare/mercor,scale_ai','companies/expert-data',
              'venture','about','labels','corrections','coverage','downloads','COMPANY/mercor'];
for (const route of legacy) {
  let actual=null, listener;
  const location={hash:'#'+route,search:'?utm_source=test',replace:value=>actual=value};
  vm.runInNewContext(script,{location,URLSearchParams,window:{addEventListener:(event,fn)=>listener=fn}});
  assert.equal(actual,'explore/?utm_source=test#'+route);
  actual=null; location.hash='#downloads'; listener();
  assert.equal(actual,'explore/?utm_source=test#downloads');
}
for(const search of ['?search','?q=remote+AI','?search=Mercor','?q=remote&other=1']){
  let actual=null;
  const location={hash:'#work',search,replace:value=>actual=value};
  vm.runInNewContext(script,{location,URLSearchParams,window:{addEventListener(){}}});
  assert.equal(actual,'explore/'+search+'#work');
}
for(const hash of ['','#main','#research','#unknown']){
  let actual=null;
  vm.runInNewContext(script,{location:{hash,search:'?utm_source=test',replace:value=>actual=value},
                            URLSearchParams,window:{addEventListener(){}}});
  assert.equal(actual,null);
}
console.log('40 legacy/query/hashchange cases passed');
"""
        result = subprocess.run(["node", "-e", code, json.dumps(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
