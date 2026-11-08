"""Retired screens stay out of the UI without breaking old links or current research."""
import ast
import json
import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Navigation(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = set()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))


class SimplifiedNavigationTests(unittest.TestCase):
    def test_removed_screens_and_controls_are_absent_from_delivered_app(self):
        guide = (ROOT / "dist/explore/index.html").read_text()
        facts = Navigation(guide)
        for identifier in ("compare-view", "compare-tray", "compare-content", "compare-preset", "method-view"):
            self.assertNotIn(identifier, facts.ids, identifier)
        self.assertIn("about-view", facts.ids)
        self.assertIn("about", facts.ids)
        self.assertNotRegex(guide, r'<(?:input|button|label)\b[^>]*\bdata-compare\b')
        self.assertIn("https://musaeminozdem.com", facts.links)

    def test_normal_navigation_does_not_advertise_retired_screens(self):
        checked = 0
        for path in (ROOT / "dist").rglob("*.html"):
            text = path.read_text()
            # The method archive may retain its research and structured metadata; ordinary menus may not.
            for block in re.findall(r'<(?:header|footer)\b[^>]*>.*?</(?:header|footer)>', text, re.S):
                for href in Navigation(block).links:
                    url = urlsplit(href)
                    if url.netloc and url.hostname not in ("sciencetostartup.com", "www.sciencetostartup.com"):
                        continue
                    self.assertNotIn(url.fragment.split("/")[0].split("?")[0].lower(),
                                     ("compare", "method", "labels", "coverage"), (path, href))
                    self.assertNotIn(url.path, ("/method/", "/method/index.html"), (path, href))
                checked += 1
        self.assertGreater(checked, 80, "The audit must include generated company headers and footers")

    def test_mobile_layout_keeps_filters_in_flow_and_about_heading_at_its_anchor(self):
        guide = (ROOT / "dist/explore/index.html").read_text()
        rules = re.findall(r"#work-view \.responsive-filter-panel\[open\]>\.responsive-filter-fields\{([^}]+)\}", guide)
        self.assertTrue(rules)
        for declaration in ("position:static", "inset:auto", "width:100%", "box-shadow:none"):
            self.assertIn(declaration, rules[-1])
        self.assertIn(".guide-footer{width:calc(100% - 40px)", guide)
        about = re.search(r'<article[^>]*id="about"[^>]*>(.*?)</article>', guide, re.S).group(1)
        self.assertIn("<h1>About</h1>", about, "The About route should reveal its heading on narrow phones")

    def test_startup_and_legacy_links_work_without_retired_dom_nodes(self):
        tree = ast.parse((ROOT / "tests/js_logic.py").read_text())
        stub = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "STUB" for t in n.targets))
        prefix = stub.split("(async()=>{", 1)[0]
        marker = "// The icon script runs first."
        self.assertEqual(prefix.count(marker), 1)
        prefix = prefix.replace(marker, r"""
const retiredIds=new Set(['compare-view','compare-tray','tray-text','nav-count','compare-add',
 'compare-add-button','compare-preset','clear-compare','compare-status','compare-content',
 'method-view','method-toc-title','labels','coverage','coverage-title','coverage-notes',
 'grade-note','rubric-content']);
document.getElementById=id=>retiredIds.has(id)?null:node(id);
""" + marker)
        checks = r"""
const before=run('JSON.stringify(DATA)');
run('initialize()');
assert.equal(typeof node('search').callbacks.input,'function');
assert.ok(windowCallbacks.hashchange.length);
// Removed comparison markup must also be safe for the document-level focus/pointer listeners.
const interactionTarget={closest:()=>null,matches:()=>false,tagName:'INPUT',type:'search'};
for(const kind of ['focusin','pointerdown'])for(const listener of documentCallbacks[kind]||[])listener({target:interactionTarget,button:0});
run('resizeComparison()');
const routes=[
 ['#compare','companies'],['#COMPARE/mercor/appen','companies'],
 ['#compare/mercor,Handshake_AI,unknown?utm_source=old','companies'],
 ['#compare/%ZZ/__proto__','companies'],['#method','about'],['#METHOD?old=1','about'],
 ['#labels','about'],['#coverage','about'],['#about','about'],
 ['#corrections','about'],['#downloads','about']
];
let routeCases=0;
for(const event of [undefined,{type:'hashchange'}])for(const [hash,target] of routes){
 location.hash=hash;
 run(event?'route({type:"hashchange"})':'route()');
 assert.equal(node(target+'-view').hidden,false,hash);
 const expected=['#corrections','#downloads'].includes(hash)?hash:'#'+target+(hash.match(/\?.*$/)?.[0]||'');
 assert.equal(location.hash,expected,hash+' must recover without losing its query suffix');
 routeCases++;
}
const retired=/^#(?:compare|method|labels|coverage)(?:[/?]|$)/i;
for(const item of run('siteSearchPages()'))assert.ok(!retired.test(item.href),item.href);
for(const c of data.companies){
 assert.equal(run('compareCheck('+JSON.stringify(c.id)+')'),'');
 const html=run('profileHTML('+JSON.stringify(c.id)+')');
 assert.ok(!/\bdata-compare(?:=|\s|>)/.test(html),c.id+' retains a comparison control');
}
assert.equal(run('JSON.stringify(DATA)'),before);
console.log(JSON.stringify({routeCases,companies:data.companies.length,retiredDomAbsent:true,canonicalUnchanged:true}));
"""
        result = subprocess.run(["node", "-", str(ROOT / "data/canonical.json"), str(ROOT)],
                                input=prefix + checks, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["routeCases"], 22)


if __name__ == "__main__":
    unittest.main()
