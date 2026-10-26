"""Crawlable static pages, the figure rules and wording they share with the app, and the generated sitemap, built into a scratch directory."""
import html
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import PRESENTATION_JS, build
import static_pages as sp

ORIGIN = "https://sciencetostartup.com"
NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
EMAIL = re.compile(r"@[A-Za-z0-9-]+\.[A-Za-z]{2,}")
PAGE_LIMIT = 120_000
REVENUE_KINDS = ("revenue", "annualized_revenue_run_rate", "arr")
ICONS = [("icon", "/assets/favicon.svg"), ("icon", "/assets/favicon-48.png"), ("apple-touch-icon", "/assets/apple-touch-icon.png")]
# eligibleMetrics in web/app.js decides which figure the app compares; the static pages must agree with it.
APP_RULE = "m.preferred_for_comparison!==false&&claims[m.claim_id].status==='supported'&&(!m.observation_status||m.observation_status==='reported')"

# Runs the app's own modules in Node with a minimal DOM stub and prints the choices the static pages must repeat.
APP_RULES = r"""
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const [root,modules]=process.argv.slice(1),read=p=>fs.readFileSync(path.join(root,p),'utf8'),json=p=>JSON.parse(read(p));
const nodes={},node=id=>nodes[id]??={id,textContent:'',innerHTML:'',value:'',hidden:false,dataset:{},addEventListener(){},setAttribute(){},removeAttribute(){},showModal(){},close(){},scrollIntoView(){},focus(){},insertAdjacentHTML(){}};
node('research-data').textContent=read('data/canonical.json');
const profiles=json('data/profile-content.json'),overlay=path.join(root,'data/profile-afterquery.json');
if(fs.existsSync(overlay))profiles.entries=profiles.entries.filter(e=>e.company_id!=='afterquery').concat(JSON.parse(fs.readFileSync(overlay,'utf8')));
const window={scrollY:0,scrollTo(){},addEventListener(){},EDITORIAL:json('data/editorial.json'),LOGOS:json('data/logo-provenance.json'),WORK_ROUTES:json('data/work-routes.json'),PROFILE_CONTENT:profiles,RESEARCH_ALIASES:json('docs/research-id-crosswalk.json'),SOURCE_UPDATES:json('data/source-updates.json')};
const document={getElementById:node,querySelectorAll:()=>[],querySelector:()=>null,createElement:()=>node('created'),addEventListener(){}};
const context=vm.createContext({document,window,location:{hash:'#market',search:''},history:{replaceState(){}},Intl,Set,Map,Date,JSON,URL,queueMicrotask,setTimeout:()=>{},console});
vm.runInContext(read('web/icons.js'),context);context.iconHTML=window.iconHTML;
vm.runInContext(JSON.parse(modules).map(read).join('\n'),context);
process.stdout.write(vm.runInContext(`JSON.stringify((()=>{
 const kinds=[...new Set(DATA.metrics.map(m=>m.kind))],r={headlines:{},eligible:{},metrics:{},financial:FINANCIAL_HEADLINES,groups:GROUP_LABELS,slugs:{}};
 for(const c of DATA.companies){r.headlines[c.id]=preferredFinancial(c.id)?.id||null;r.eligible[c.id]=Object.fromEntries(kinds.map(k=>[k,eligibleMetrics(c.id,k).map(m=>m.id)]));}
 for(const m of DATA.metrics)r.metrics[m.id]={rank:dateRank(m.as_of),period:financialPeriod(m),compact:typeof m.value==='number'?compact(Math.abs(m.value)):null,scope:scopeText(m.segment_scope,m.company_id),currentPeriod:metricCurrentPeriod(m),basis:metricCurrentBasis(m,''),label:metricPresentationLabel(m,'')};
 for(const name of Object.keys(MODEL_GROUPS))r.slugs[name]=groupSlug(name);
 r.work=Object.fromEntries(window.WORK_ROUTES.routes.map(w=>[w.id,{bucket:w4Bucket(w),status:w4Status(w),place:w4Location(w),pay:w4Pay(w)}]));
 r.ids=DATA.metrics.map(m=>m.id).sort((a,b)=>a.localeCompare(b));r.names=DATA.companies.map(c=>c.name).concat(window.WORK_ROUTES.routes.map(w=>w.role)).sort((a,b)=>a.localeCompare(b));
 return r;})())`,context));
"""
# publicText in web/app.js, run on strings read from stdin; the static pages must print the same words.
APP_WORDING = r"""
const fs=require('fs'),vm=require('vm'),app=fs.readFileSync(process.argv[1],'utf8'),DATA=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const start=app.indexOf('const PUBLIC_COPY_EDITS='),body=app.indexOf('function publicTextCompute('),end=app.indexOf('\n}\n',body);
if(start<0||body<0||end<0)throw new Error('web/app.js changed: publicText not found');
const context={DATA};vm.createContext(context);vm.runInContext(app.slice(start,end+3)+';this.publicText=publicText;',context);
console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(context.publicText)));
"""


class PageFacts(HTMLParser):
    """Canonical links, h1 headings, title, script tags, meta tags, links and anchors of a static page."""
    def __init__(self, text):
        super().__init__()
        self.canonicals, self.headings, self.scripts, self.title = [], [], [], ""
        self.meta, self.links, self.anchors, self.ids, self.navs = {}, [], [], set(), []
        self._capture, self._buffer, self._anchor = None, [], None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"): self.ids.add(attrs["id"])
        if tag == "link":
            self.links.append(attrs)
            if attrs.get("rel") == "canonical": self.canonicals.append(attrs.get("href"))
        if tag == "meta" and (attrs.get("name") or attrs.get("property")): self.meta[attrs.get("name") or attrs.get("property")] = attrs.get("content")
        if tag == "script": self.scripts.append(attrs)
        if tag == "nav": self.navs.append(attrs.get("aria-label"))
        if tag == "a": self._anchor = dict(attrs, text=""); self.anchors.append(self._anchor)
        if tag in ("h1", "title"): self._capture, self._buffer = tag, []

    def handle_data(self, data):
        if self._capture: self._buffer.append(data)
        if self._anchor is not None: self._anchor["text"] += data

    def handle_endtag(self, tag):
        if tag == "a": self._anchor = None
        if tag != self._capture: return
        text = "".join(self._buffer)
        if tag == "h1": self.headings.append(text)
        else: self.title = text
        self._capture = None


def structured_data(text):
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S).group(1))


def ld_nodes(text):
    """Every top-level JSON-LD node on a page, from every ld+json block, with lists and @graph flattened."""
    nodes = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        payload = json.loads(block)
        for item in payload if isinstance(payload, list) else [payload]:
            nodes.extend(item["@graph"] if "@graph" in item else [item])
    return nodes


def visible_crumbs(text):
    """The visible breadcrumb trail as (name, url) pairs; the current page has no link, so its url is the canonical one."""
    trail = re.search(r'<nav class="crumbs" aria-label="Breadcrumb"><ol>(.*?)</ol></nav>', text).group(1)
    canonical = PageFacts(text).canonicals[0]
    return [(html.unescape(name), html.unescape(url) if url else canonical) for url, name in re.findall(r'<li>(?:<a href="([^"]+)">|<span aria-current="page">)(.*?)</(?:a|span)></li>', trail)]


def plain(fragment):
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).replace("&amp;", "&").replace("&#x27;", "'").split())


def png_size(data):
    return struct.unpack(">II", data[16:24])


class StaticPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.temp = tempfile.TemporaryDirectory(prefix="static-pages-")
        cls.dist = Path(cls.temp.name)
        build(cls.data, cls.dist)
        cls.companies = {c["id"]: c for c in cls.data["companies"]}
        cls.pages = {cid: (cls.dist / "company" / cid / "index.html").read_text() for cid in cls.companies}
        say = sp.public_wording(cls.data, sp.load_copy_edits())
        cls.say = staticmethod(say)
        cls.research = sp.Research(cls.data, sp.read_js_object(ROOT / "web/app.js", "FINANCIAL_HEADLINES"), json.loads((ROOT / "data/source-updates.json").read_text()), say=say)
        cls.metrics = {m["id"]: m for m in cls.data["metrics"]}
        cls.routes = json.loads((ROOT / "data/work-routes.json").read_text())["routes"]
        cls.events = json.loads((ROOT / "data/company-events.json").read_text())
        cls.editorial = {e["company_id"]: e for e in json.loads((ROOT / "data/editorial.json").read_text())["entries"]}
        profiles = json.loads((ROOT / "data/profile-content.json").read_text())["entries"]
        overlay = ROOT / "data/profile-afterquery.json"
        if overlay.exists(): profiles = [e for e in profiles if e["company_id"] != "afterquery"] + [json.loads(overlay.read_text())]
        cls.contexts = {mid: context for e in profiles for mid, context in (e.get("metric_context") or {}).items()}

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def public_files(self):
        return sorted(self.dist.glob("company/*/index.html")) + [self.dist / name for name in ("companies/index.html", "work/index.html", "method/index.html", "404.html", "sitemap.xml")]

    def html_files(self):
        return [path for path in self.public_files() if path.suffix == ".html"]

    def indexable_files(self):
        return [path for path in self.html_files() if path.name != "404.html"]

    def figures(self, cid):
        """(metric id, html) for each Key figures row, each Not confirmed item and each Other reported figures item."""
        section = self.pages[cid].split('<h2 id="figures">', 1)[1].split('<h2 id="facts"', 1)[0]
        rows = re.findall(r'<tr data-metric="([^"]+)">(.*?)</tr>', section, re.S)
        lists = {key: re.findall(r'<li data-metric="([^"]+)">(.*?)</li>', section.split(f'<h3 id="{key}">', 1)[1].split("</ul>", 1)[0], re.S) if f'<h3 id="{key}">' in section else [] for key in ("unconfirmed", "other-figures")}
        return rows, lists["unconfirmed"], lists["other-figures"]

    def footer(self, path):
        return re.search(r'<footer class="site-footer">.*?</footer>', path.read_text(), re.S).group(0)

    # Pages, links and metadata

    def test_every_company_gets_a_crawlable_page(self):
        self.assertEqual(len(self.companies), 39)
        self.assertEqual(sorted(p.name for p in (self.dist / "company").iterdir()), sorted(self.companies))
        for cid in self.companies: self.assertTrue((self.dist / "company" / cid / "index.html").is_file(), cid)

    def test_pages_declare_canonical_url_title_and_heading(self):
        for cid, text in self.pages.items():
            facts = PageFacts(text)
            name = self.companies[cid]["name"]
            self.assertEqual(facts.canonicals, [f"{ORIGIN}/company/{cid}/"], cid)
            self.assertEqual(facts.headings, [name], cid)
            self.assertTrue(facts.title.startswith(name + ":") or facts.title == name + sp.SUFFIX, (cid, facts.title))
            self.assertLessEqual(len(facts.title), sp.TITLE_LIMIT, (cid, facts.title))
            # Topics go before the brand does: every name short enough to carry " · ScienceToStartup" keeps it.
            if len(name + sp.SUFFIX) <= sp.TITLE_LIMIT: self.assertTrue(facts.title.endswith(sp.SUFFIX), (cid, facts.title))
            self.assertIn(f'href="{ORIGIN}/#company/{cid}"', text, cid)
            self.assertLessEqual(len(facts.meta["description"]), sp.DESCRIPTION_LIMIT, cid)

    def test_pages_stay_lean_without_app_script_or_dataset(self):
        for cid, text in self.pages.items():
            self.assertLess(len(text.encode()), PAGE_LIMIT, cid)
            self.assertEqual([s.get("type") for s in PageFacts(text).scripts], ["application/ld+json"], cid)
            self.assertNotIn('id="research-data"', text, cid)
            structured = structured_data(text)
            self.assertEqual(structured["mainEntity"]["name"], self.companies[cid]["name"], cid)
            self.assertEqual(structured["isPartOf"]["url"], ORIGIN + "/", cid)
            self.assertEqual(structured["about"], {"@id": structured["mainEntity"]["@id"]}, cid)
            # The structured breadcrumb is the visible trail, business group included (coordinator E6).
            items = structured["breadcrumb"]["itemListElement"]
            self.assertEqual([(item["name"], item["item"]) for item in items], visible_crumbs(text), cid)
            self.assertEqual([item["position"] for item in items], list(range(1, len(items) + 1)), cid)
            self.assertEqual([item["item"] for item in items][:2] + [items[-1]["item"]], [ORIGIN + "/", ORIGIN + "/companies/", f"{ORIGIN}/company/{cid}/"], cid)
            self.assertEqual(len(items), 4, cid)
            self.assertEqual(structured["publisher"]["name"], "Musa Ozdem", cid)
        for name in ("work", "method"):
            self.assertLess(len((self.dist / name / "index.html").read_bytes()), PAGE_LIMIT, name)
        for path in self.indexable_files():
            text = path.read_text()
            page = next(node for node in ld_nodes(text) if "breadcrumb" in node)
            self.assertEqual([(i["name"], i["item"]) for i in page["breadcrumb"]["itemListElement"]], visible_crumbs(text), str(path.relative_to(self.dist)))

    def test_legal_names_leave_out_research_notes(self):
        """schema.org legalName and the Legal entity row carry the registered name, not the notes after ';' (coordinator E7)."""
        notes = 0
        for cid, text in self.pages.items():
            stored = self.companies[cid].get("legal_entity_name") or ""
            organization = structured_data(text)["mainEntity"]
            if not stored:
                self.assertNotIn("legalName", organization, cid)
                continue
            expected = sp.clean(stored.split(";", 1)[0])
            notes += ";" in stored
            self.assertEqual(organization["legalName"], expected, cid)
            self.assertNotIn(";", organization["legalName"], cid)
            row = re.search(r"<dt>Legal entity</dt><dd>(.*?)</dd>", text)
            if row: self.assertEqual(html.unescape(row.group(1)), expected, cid)
        self.assertGreaterEqual(notes, 2)
        self.assertEqual(structured_data(self.pages["scale_ai"])["mainEntity"]["legalName"], "Scale AI, Inc.")

    def test_sitemap_lists_every_page_with_lastmod(self):
        root = ET.parse(self.dist / "sitemap.xml").getroot()
        self.assertEqual(root.tag, NAMESPACE + "urlset")
        urls = root.findall(NAMESPACE + "url")
        self.assertEqual(len(urls), 4 + len(self.companies))
        locs = [u.find(NAMESPACE + "loc").text for u in urls]
        self.assertEqual(locs[:2] + locs[-2:], [ORIGIN + "/", ORIGIN + "/companies/", ORIGIN + "/work/", ORIGIN + "/method/"])
        self.assertEqual(sorted(locs[2:-2]), sorted(f"{ORIGIN}/company/{cid}/" for cid in self.companies))
        reviewed = self.events["reviewed_on"]
        newest = max(sp.SITE_REVISED, self.data["meta"]["as_of"], reviewed, *(e.get("reviewed_on") or "" for e in self.editorial.values()), *(d for r in self.routes for d in sp.route_dates(r) if d))
        lastmods = {}
        for url in urls:
            loc, lastmod = url.find(NAMESPACE + "loc").text, url.find(NAMESPACE + "lastmod").text
            lastmods[loc] = lastmod
            self.assertRegex(lastmod, r"^\d{4}-\d{2}-\d{2}$")
            self.assertGreaterEqual(lastmod, self.data["meta"]["as_of"], loc)
            self.assertLessEqual(lastmod, newest, loc)
        # Events reviewed after the dataset change the pages that show them, and dateModified agrees with lastmod.
        for cid in {e["company_id"] for e in self.events["events"]} | {r for e in self.events["events"] for r in e["related_company_ids"]}:
            self.assertGreaterEqual(lastmods[f"{ORIGIN}/company/{cid}/"], reviewed, cid)
        for path in self.indexable_files():
            canonical = PageFacts(path.read_text()).canonicals[0]
            self.assertIn(f'"dateModified":"{lastmods[canonical]}"', path.read_text(), canonical)

    def test_index_page_groups_every_company_and_links_the_app(self):
        text = (self.dist / "companies/index.html").read_text()
        facts = PageFacts(text)
        self.assertEqual(facts.canonicals, [ORIGIN + "/companies/"])
        for cid in self.companies: self.assertIn(f'href="{ORIGIN}/company/{cid}/"', text, cid)
        self.assertIn(f'href="{ORIGIN}/#companies"', text)
        labels = sp.read_js_object(ROOT / "web/editorial.js", "GROUP_LABELS")
        for group in {e["primary_offering"] for e in self.editorial.values()}:
            slug = re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")
            self.assertIn(slug, facts.ids, group)
            self.assertIn(f'<h2 id="{slug}">{labels.get(group, group).replace("&", "&amp;")}</h2>', text)
            self.assertIn(f'href="{ORIGIN}/#companies/{slug}"', text)
        nonprofits = sum(1 for e in self.editorial.values() if e["primary_offering"] == "Nonprofit research")
        self.assertIn(f"{sp.count_word(nonprofits)} of the {len(self.companies)} are nonprofit research groups.", text)

    def test_index_states_coverage_limits(self):
        text = (self.dist / "companies/index.html").read_text()
        self.assertIn("The guide is a selected study of the market. It does not list every company.", text)
        self.assertIn("The guide is a selected study of the market. It does not list every company.", (self.dist / "method/index.html").read_text())
        missing = re.search(r"Firms not yet profiled include ([^<]+)", text).group(1)
        self.assertEqual(missing, "Uber AI Solutions, TELUS Digital, CloudFactory, SuperAnnotate, Encord, Defined.ai, LXT and Welocalize.")
        self.assertTrue(self.footer(self.dist / "companies/index.html").endswith("<p>Company names and logos belong to their owners and identify them here.</p></footer>"))

    def test_company_pages_link_breadcrumbs_group_and_every_peer(self):
        labels = sp.read_js_object(ROOT / "web/editorial.js", "GROUP_LABELS")
        for cid, text in self.pages.items():
            group = self.editorial[cid]["primary_offering"]
            slug = re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")
            crumbs = re.search(r'<nav class="crumbs" aria-label="Breadcrumb">(.*?)</nav>', text).group(1)
            self.assertIn(f'href="{ORIGIN}/companies/#{slug}">{labels.get(group, group).replace("&", "&amp;")}</a>', crumbs, cid)
            peers = [p for p, e in self.editorial.items() if e["primary_offering"] == group and p != cid]
            related = text.split('<h2 id="related">', 1)[1].split("</ul>", 1)[0]
            self.assertEqual(sorted(re.findall(r'/company/([^/]+)/"', related)), sorted(peers), cid)

    def test_header_footer_and_icons_are_shared_by_every_page(self):
        expected_nav = [f"{ORIGIN}/companies/", f"{ORIGIN}/work/", f"{ORIGIN}/#compare", f"{ORIGIN}/method/", f"{ORIGIN}/?search"]
        for path in self.html_files():
            text, label = path.read_text(), str(path.relative_to(self.dist))
            facts = PageFacts(text)
            nav = re.search(r'<nav class="site-nav" aria-label="Site">(.*?)</nav>', text).group(1)
            self.assertEqual(re.findall(r'href="([^"]+)"', nav), expected_nav, label)
            self.assertIn("Site map", facts.navs, label)
            icons = [l for l in facts.links if "icon" in str(l.get("rel"))]
            self.assertEqual([(l.get("rel"), l.get("href")) for l in icons], ICONS, label)
            self.assertEqual(icons[0].get("type"), "image/svg+xml", label)
            self.assertIn(f'href="{ORIGIN}/#corrections"', text, label)
            self.assertNotIn("—", text, label)
            for anchor in facts.anchors:
                href = anchor.get("href", "")
                if href.startswith("http") and not href.startswith(ORIGIN): self.assertEqual(anchor.get("class"), "ext", (label, href))
                if href.startswith(ORIGIN): self.assertNotEqual(anchor.get("class"), "ext", (label, href))
        self.assertIn('aria-current="page">Companies<', (self.dist / "companies/index.html").read_text())
        self.assertIn('aria-current="true">Companies<', self.pages["mercor"])
        self.assertIn('aria-current="page">Paid work<', (self.dist / "work/index.html").read_text())

    def test_footer_links_are_big_enough_to_tap_on_phones(self):
        """Coordinator C5: footer links were 16 px tall on phones; at 700 px and below each one is at least 44 px."""
        phone = re.search(r"@media\(max-width:700px\)\{(.*?)\}\}", sp.STYLE).group(1)
        self.assertIn(".site-footer li a{display:inline-flex;align-items:center;min-height:44px", phone)

    def test_header_main_and_footer_share_one_column(self):
        inset = re.search(r"\.site-header\{[^}]*padding:0 ([^;}]+)", sp.STYLE).group(1)
        self.assertIn(f"main,.site-footer{{margin:0 {inset}}}", sp.STYLE)
        self.assertIn("max(var(--gutter),calc((100% - var(--content))/2))", inset)

    def test_footer_names_publisher_disclosure_and_corrections(self):
        about = re.search(r'<article[^>]*\bid="about"[^>]*>.*?</article>', (ROOT / "web/index.html").read_text(), re.S).group(0)
        disclosure = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<strong>Disclosure\.</strong>\s*(.*?)</p>", about, re.S).group(1))).replace("’", "'")
        publisher = re.search(r"ScienceToStartup is published by [^.]+\.", about).group(0)
        # The paid-work line is About text only, so footers carry the lab disclosure alone wherever the app places that line.
        self.assertEqual(sp.DISCLOSURE, " ".join(disclosure.replace(sp.WORK_DISCLOSURE, "").split()))
        # The owner's one-line disclosure, word for word, in both About texts (the app's About panel and /method/).
        method_about = (self.dist / "method/index.html").read_text().split('<h2 id="about">', 1)[1].split("<h2", 1)[0]
        for label, text in (("web/index.html#about", about), ("method/index.html#about", method_about)):
            self.assertIn(sp.WORK_DISCLOSURE, " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("’", "'").split()), label)
            self.assertEqual(text.count("A.Team"), 1, label)
        for path in self.html_files():
            footer = self.footer(path)
            text = html.unescape(re.sub(r"<[^>]+>", "", footer))
            self.assertIn(publisher, text, path)
            self.assertIn(sp.DISCLOSURE, text, path)
            self.assertIn(f'<a href="{ORIGIN}/#venture">overview page</a>', footer, path)
            self.assertIn(f'<a href="{ORIGIN}/#corrections">Request a correction</a>', footer, path)

    def test_head_tags_make_every_page_share_ready(self):
        for path in self.indexable_files() + [self.dist / "404.html"]:
            facts, label = PageFacts(path.read_text()), str(path.relative_to(self.dist))
            meta = facts.meta
            self.assertLessEqual(len(facts.title), sp.TITLE_LIMIT, label)
            self.assertLess(len(facts.title), 60, label)
            self.assertLessEqual(len(meta["description"]), sp.DESCRIPTION_LIMIT, label)
            self.assertTrue(meta["description"].endswith("."), label)
            self.assertNotIn("…", meta["description"], label)
        for path in self.indexable_files() + [self.dist / "index.html"]:
            meta, label = PageFacts(path.read_text()).meta, str(path.relative_to(self.dist))
            self.assertEqual(meta["og:image"], sp.SHARE_IMAGE, label)
            self.assertEqual((meta["og:image:width"], meta["og:image:height"]), ("1200", "630"), label)
            self.assertEqual(meta["twitter:card"], "summary_large_image", label)
            self.assertTrue(meta["og:image:alt"] and meta["twitter:image:alt"] == meta["og:image:alt"], label)
        for path in self.indexable_files():
            facts, label = PageFacts(path.read_text()), str(path.relative_to(self.dist))
            meta = facts.meta
            self.assertEqual((meta["og:title"], meta["twitter:title"]), (facts.title, facts.title), label)
            self.assertEqual((meta["og:description"], meta["twitter:description"]), (meta["description"], meta["description"]), label)
            self.assertEqual(meta["og:image:alt"], sp.SHARE_ALT, label)

    def test_share_image_and_icons_are_the_right_files(self):
        image = (self.dist / sp.SHARE_IMAGE.replace(ORIGIN + "/", "")).read_bytes()
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png_size(image), (1200, 630))
        self.assertLess(len(image), 100_000)
        self.assertFalse((self.dist / "assets/og").exists(), "the older share card with a typed company count is gone")
        self.assertFalse((self.dist / "assets/icon-192.png").exists())
        self.assertTrue((self.dist / "assets/favicon.svg").read_text().lstrip().startswith("<svg"))
        self.assertEqual(png_size((self.dist / "assets/favicon-48.png").read_bytes()), (48, 48))
        touch = (self.dist / "assets/apple-touch-icon.png").read_bytes()
        self.assertEqual(png_size(touch), (180, 180))
        self.assertIn(touch[25], (0, 2), "the Apple touch icon is opaque")
        ico = (self.dist / "favicon.ico").read_bytes()
        reserved, kind, count = struct.unpack("<HHH", ico[:6])
        self.assertEqual((reserved, kind), (0, 1))
        sizes = []
        for index in range(count):
            width, height, _, _, _, _, size, offset = struct.unpack("<BBBBHHII", ico[6 + 16 * index: 22 + 16 * index])
            self.assertEqual(ico[offset:offset + 8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(png_size(ico[offset:]), (width or 256, height or 256))
            sizes.append(width)
        self.assertEqual(sorted(sizes), [16, 32, 48])

    def test_home_head_names_the_site_and_publisher(self):
        text = (self.dist / "index.html").read_text()
        head = text.split("</head>", 1)[0]
        self.assertEqual(PageFacts(head).canonicals, [ORIGIN + "/"])
        self.assertNotIn("data:image/svg+xml", head.split("<style>", 1)[0])
        nodes = ld_nodes(head)
        website = next(node for node in nodes if node.get("@type") == "WebSite")
        self.assertEqual((website["@type"], website["@id"], website["url"], website["name"]), ("WebSite", ORIGIN + "/#website", ORIGIN + "/", "ScienceToStartup"))
        self.assertIn(str(len(self.companies)), website["description"])
        # One publisher, the Person, defined once on the page; every other node names it by @id.
        people = [node for node in nodes if node.get("@type") == "Person"] + [value for node in nodes for value in node.values() if isinstance(value, dict) and value.get("@type") == "Person"]
        self.assertEqual([(p["@id"], p["name"]) for p in people], [(sp.PUBLISHER["@id"], sp.PUBLISHER_NAME)])
        # One dataset identity (APPLY-BRIEF): the home page's Dataset node, which /method/ describes under the same @id and name.
        datasets = [node for node in nodes if node.get("@type") == "Dataset"]
        self.assertEqual([d["@id"] for d in datasets], [sp.DATASET_ID])
        self.assertEqual((datasets[0]["name"], datasets[0]["license"]), (sp.DATASET_NAME, sp.DATA_LICENSE))
        for node in nodes:
            for key in ("publisher", "creator"):
                if key in node: self.assertEqual(node[key]["@id"], sp.PUBLISHER["@id"], (node.get("@type"), key))
        self.assertNotIn("dated source", json.dumps(nodes), "each figure links to its source; not every source is dated")

    def test_no_email_addresses_leak_into_public_pages(self):
        for path in self.public_files():
            self.assertIsNone(EMAIL.search(path.read_text()), str(path.relative_to(self.dist)))

    def test_manifest_covers_the_static_pages(self):
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        for name in ("sitemap.xml", "companies/index.html", "company/mercor/index.html", "work/index.html", "method/index.html", "404.html", "favicon.ico", "assets/favicon.svg", "assets/favicon-48.png", "assets/apple-touch-icon.png", "assets/share/sciencetostartup-1200x630.png"): self.assertIn(name, manifest)
        self.assertEqual(sum(1 for n in manifest if n.startswith("company/") and n.endswith("/index.html")), 39)

    def test_static_pages_are_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="static-pages-again-") as temp:
            again = Path(temp)
            build(self.data, again)
            for path in self.public_files():
                relative = path.relative_to(self.dist)
                self.assertEqual(path.read_bytes(), (again / relative).read_bytes(), str(relative))

    def test_mobile_tables_keep_their_headers_for_screen_readers(self):
        self.assertNotIn("thead{display:none}", sp.STYLE)
        self.assertIn("td[data-label]::before", sp.STYLE)
        for path in self.html_files():
            for cell in re.findall(r"<td\b[^>]*>", path.read_text()): self.assertIn("data-label=", cell, str(path.relative_to(self.dist)))

    def test_analytics_loader_follows_the_index_meta(self):
        self.assertEqual(sp.analytics_endpoint((ROOT / "web/index.html").read_text()), "")
        self.assertEqual(sp.analytics_endpoint('<meta name="sts-analytics" content="https://sciencetostartup.goatcounter.com/count">'), "https://sciencetostartup.goatcounter.com/count")
        for other in ("https://example.com/count", "javascript:alert(1)", "https://x.goatcounter.com/count?x=1"):
            self.assertEqual(sp.analytics_endpoint(f'<meta name="sts-analytics" content="{other}">'), "", other)
        counting = sp.Research(self.data, analytics="https://sciencetostartup.goatcounter.com/count")
        page = sp.document(counting, "T", "D.", ORIGIN + "/", "", {})
        self.assertIn('<script async src="https://gc.zgo.at/count.js" data-goatcounter="https://sciencetostartup.goatcounter.com/count"></script>\n</head>', page)
        self.assertNotIn("gc.zgo.at", sp.document(counting, "Page not found", "D.", "", "", robots="noindex"), "the 404 page does not count")
        self.assertNotIn("gc.zgo.at", sp.document(sp.Research(self.data), "T", "D.", ORIGIN + "/", "", {}))
        for path in self.html_files(): self.assertNotIn("gc.zgo.at", path.read_text(), "counting is off in web/index.html")

    def test_both_hosts_send_the_same_headers(self):
        """web/_headers (Cloudflare) and vercel.json carry one policy: GoatCounter allowed, hashed scripts cached for a year, SQLite typed."""
        lines = (ROOT / "web/_headers").read_text().splitlines()
        rules, path = {}, None
        for line in lines:
            if line and not line.startswith(" "): path = line.strip(); rules[path] = {}
            elif line.strip(): key, value = line.strip().split(": ", 1); rules[path][key] = value
        vercel = {rule["source"]: {h["key"]: h["value"] for h in rule["headers"]} for rule in json.loads((ROOT / "vercel.json").read_text())["headers"]}
        policy = rules["/*"]["Content-Security-Policy"]
        self.assertEqual(vercel["/(.*)"]["Content-Security-Policy"], policy)
        for host in ("https://gc.zgo.at", "https://sciencetostartup.goatcounter.com", "https://static.cloudflareinsights.com"): self.assertIn(host, policy)
        self.assertEqual(rules["/js/*"]["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(vercel["/js/(.*)"]["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(rules["/*.sqlite"]["Content-Type"], "application/vnd.sqlite3")
        self.assertEqual(vercel["/(.*)\\.sqlite"]["Content-Type"], "application/vnd.sqlite3")
        self.assertEqual((self.dist / "_headers").read_bytes(), (ROOT / "web/_headers").read_bytes())

    # Figures follow the app's rules (red-team RED-1, RED-2, RED-3, RED-10, RED-11, RED-13 and IA-11)

    def test_static_rules_match_the_app_code_in_node(self):
        node = shutil.which("node")
        if not node: self.skipTest("Node is not installed")
        self.assertIn(APP_RULE, (ROOT / "web/app.js").read_text(), "eligibleMetrics changed in web/app.js; update Research.eligible and static_pages.exclusion")
        modules = ["web/app.js", "web/editorial.js", "web/work-v3.js"] + ["web/" + name for name in PRESENTATION_JS]
        result = subprocess.run([node, "-e", APP_RULES, str(ROOT), json.dumps(modules)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        app = json.loads(result.stdout)
        self.assertEqual(sp.read_js_object(ROOT / "web/app.js", "FINANCIAL_HEADLINES"), app["financial"])
        self.assertEqual(sp.read_js_object(ROOT / "web/editorial.js", "GROUP_LABELS"), app["groups"])
        for name, slug in app["slugs"].items(): self.assertEqual(sp.group_slug(name), slug, name)
        self.assertEqual(sorted(self.metrics, key=sp.locale_key), app["ids"])
        self.assertEqual(sorted([c["name"] for c in self.data["companies"]] + [r["role"] for r in self.routes], key=sp.locale_key), app["names"])
        for cid in self.companies:
            headline = self.research.headline(cid)
            self.assertEqual(headline["id"] if headline else None, app["headlines"][cid], cid)
            for kind, ids in app["eligible"][cid].items(): self.assertEqual([m["id"] for m in self.research.ranked(cid, kind)], ids, (cid, kind))
        for mid, expected in app["metrics"].items():
            metric = self.metrics[mid]
            self.assertEqual(sp.date_rank(metric["as_of"]), expected["rank"], mid)
            self.assertEqual(sp.financial_period(metric), expected["period"], mid)
            self.assertEqual(self.research.scope_text(metric["segment_scope"], metric["company_id"]), expected["scope"], mid)
            if expected["compact"] is not None: self.assertEqual(sp.number_text(metric["value"]), expected["compact"], mid)
            for field, key in (("display_basis", "basis"), ("display_label", "label")): self.assertEqual(self.research.correction(metric, field), expected[key], (mid, field))
            if expected["currentPeriod"]: self.assertEqual(self.research.correction(metric, "display_period"), expected["currentPeriod"], mid)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_printed_text_matches_the_app_wording(self):
        """Research fields go through the Python port of publicText; sidecar copy must already be in final form."""
        research = sorted({row[field] for table, fields in sp.REWORDED_FIELDS.items() for row in self.data[table] for field in fields if isinstance(row.get(field), str)})
        load = lambda name: json.loads((ROOT / "data" / name).read_text())
        editorial, profiles, work = load("editorial.json")["entries"], load("profile-content.json")["entries"], load("work-routes.json")["routes"]
        sidecar = {c["name"] for c in self.data["companies"]}
        sidecar |= {e.get(field) for e in editorial for field in ("summary", "primary_offering", "precise_category")}
        sidecar |= {p.get(field) for entry in profiles for p in entry.get("products", []) for field in ("name", "description")}
        sidecar |= {r.get(field) for r in work for field in ("role", "pay_label")}
        sidecar |= {e[field] for e in self.events["events"] for field in ("title", "detail", "status")} | {s["publisher"] for e in self.events["events"] for s in e["sources"]}
        sidecar = sorted(text for text in sidecar if isinstance(text, str) and text)
        strings = research + sidecar
        shown = json.loads(subprocess.run(["node", "-e", APP_WORDING, str(ROOT / "web/app.js"), str(ROOT / "data/canonical.json")], input=json.dumps(strings), check=True, capture_output=True, text=True).stdout)
        self.assertGreater(len(sp.load_copy_edits()), 100)
        for text, app in zip(research, shown): self.assertEqual(self.say(text), app, text)
        for text, app in zip(sidecar, shown[len(research):]): self.assertEqual(text, app, "the app rewords this sidecar text; reword it at the source or pass it through public_wording")

    def test_key_figures_hold_only_eligible_figures_led_by_the_app_headline(self):
        for cid in self.companies:
            rows, pending, others = self.figures(cid)
            shown = [self.metrics[mid] for mid, _ in rows]
            for metric in shown:
                claim = self.research.claims[metric["claim_id"]]
                self.assertEqual(claim["status"], "supported", metric["id"])
                self.assertIn(metric.get("observation_status"), (None, "", "reported"), metric["id"])
                self.assertIsNot(metric.get("preferred_for_comparison"), False, metric["id"])
            headline = self.research.headline(cid)
            if headline: self.assertEqual(shown[0]["id"], headline["id"], cid)
            for kind in REVENUE_KINDS:
                same = [m for m in shown if m["kind"] == kind]
                self.assertLessEqual(len(same), 1, (cid, kind))
                if headline and same and kind == headline["kind"]: self.assertEqual(same[0]["id"], headline["id"], cid)
            for mid, item in pending:
                self.assertNotIn(mid, [m["id"] for m in shown], cid)
                self.assertRegex(plain(item), r"In reported talks|Unverified|Conflicting reports", mid)
            for mid, item in others:
                self.assertNotIn(mid, [m["id"] for m in shown] + [m for m, _ in pending], cid)
                self.assertRegex(plain(item), r"\. (?:Forecast|Target|Older or partial figure)\.", mid)
            # Forecasts and targets never count as key figures (RED-10): they appear only in the list of other reported figures.
            listed = {mid for mid, _ in others}
            for mid in re.findall(r'data-metric="([^"]+)"', self.pages[cid]):
                if self.metrics[mid].get("observation_status") in ("forecast", "target"): self.assertIn(mid, listed, mid)

    def test_excluded_figures_are_listed_with_their_status(self):
        """Nothing reported silently disappears: a newer figure the app excludes is listed with its status in words."""
        eligible = lambda m: m.get("preferred_for_comparison") is not False and self.research.claims[m["claim_id"]]["status"] == "supported" and (not m.get("observation_status") or m["observation_status"] == "reported")
        found, shown = set(), 0
        for cid in self.companies:
            rows, pending, others = self.figures(cid)
            shown += len(rows)
            for mid, item in pending + others:
                self.assertFalse(eligible(self.metrics[mid]), (cid, mid))
                value, status = re.match(r"[^:]+: (.*?)(?: Historical)? · .*?\. ((?:In reported talks|Unverified|Conflicting reports|Forecast|Target|Older or partial figure))\.", plain(item)).groups()
                found.add((cid, value, status))
        self.assertGreater(shown, 100)
        self.assertLessEqual({("scale_ai", "$200M", "Unverified"), ("invisible", "more than $2B", "Unverified"), ("afterquery", "$3.2B", "In reported talks"), ("micro1", "$1B", "Target"), ("labelbox", "$189M", "Older or partial figure"), ("prolific", "$500M", "Forecast")}, found)
        self.assertNotIn("Not preferred", "".join(self.pages.values()))
        self.assertNotIn("DeepSWE pass@1, base", self.pages["afterquery"])

    def test_each_row_states_scope_date_grade_and_status(self):
        for cid in self.companies:
            for mid, row in self.figures(cid)[0]:
                metric, text = self.metrics[mid], plain(row)
                claim = self.research.claims[metric["claim_id"]]
                self.assertIn(sp.figure_scope(self.research, metric, self.contexts.get(mid)), text, mid)
                self.assertEqual("Historical" in text, bool(self.research.historical_year(metric)), mid)
                self.assertEqual("Estimate" in text, metric.get("reported_vs_estimated") == "estimated", mid)
                self.assertIn(f'data-label="Grade">{claim["confidence"]}<', row, mid)
                if metric.get("gross_vs_net") == "gross": self.assertIn("gross", text, mid)
                if metric["kind"] in REVENUE_KINDS and metric.get("gross_vs_net") == "unspecified": self.assertIn("gross or net not stated", text, mid)
                extra = len(claim.get("source_ids", [])) - 1
                if extra > 0: self.assertIn(f"+{extra} more source", text, mid)
                # The source line says when we read the page, in the app's words (B6: the lede promises a checked or recorded date).
                source, _ = sp.latest_source(self.research, metric)
                if source: self.assertIn({"checked": "Checked ", "summary_only": "Summary only, page not reviewed · recorded ", "unverified": "Not checked again · recorded "}[source["retrieval_status"]] + sp.format_date(source["accessed_on"]), text, mid)
                self.assertNotRegex(text, r"\b[a-z]+_[a-z_]+\b", mid)
                self.assertNotRegex(text, r"[$£€]-|\d{4}-\d{2}(?:-\d{2})?", mid)

    def test_rows_name_their_scope_and_revenue_period(self):
        taskus = dict(self.figures("taskus")[0])
        self.assertIn("AI Services service line", plain(taskus["taskus.metric.expansion-2"]))
        self.assertIn("FY2025", plain(taskus["taskus.metric.expansion-2"]))
        self.assertIn("Revenue growth year over year AI Services service line", plain(taskus["taskus.metric.expansion-11"]))
        prolific = dict(self.figures("prolific")[0])
        self.assertIn("One week; exact week-end unspecified", plain(prolific["prolific.metric.audit-1"]))

    def test_scale_leads_with_reported_revenue_not_the_unverified_run_rate(self):
        rows, pending, _ = self.figures("scale_ai")
        self.assertNotIn("$200M", "".join(plain(row) for _, row in rows))
        self.assertRegex(plain(rows[0][1]), r"^Revenue .*\$870M")
        self.assertIn(("scale_ai.claim.growth_metrics-3.metric-0"), dict(pending))
        self.assertIn("Annualized pace: $200M", plain(dict(pending)["scale_ai.claim.growth_metrics-3.metric-0"]))

    def test_red_team_regressions_stay_fixed(self):
        mercor_rows, mercor_pending, _ = self.figures("mercor")
        self.assertEqual(mercor_rows[0][0], "mercor.metric.oct14-major-financial-2")
        self.assertIn("gross (Sacra estimate)", plain(mercor_rows[0][1]))
        self.assertIn("mercor.metric.major-valuation_alternatives", [mid for mid, _ in mercor_pending])
        self.assertNotIn("$20B", "".join(plain(row) for _, row in mercor_rows))
        self.assertEqual(self.figures("turing")[0][0][0], "turing.metric.major-growth_metrics-1")
        toloka = [mid for mid, _ in self.figures("toloka")[0]]
        self.assertIn("toloka.metric.major-growth_metrics-1", toloka)
        self.assertNotIn("toloka.metric.major-growth_metrics-0", toloka)
        taskus = dict(self.figures("taskus")[0])
        self.assertIn("AI Services", plain(taskus["taskus.metric.expansion-2"]))
        appen = dict(self.figures("appen")[0])
        self.assertIn("$119.92M", plain(appen["appen.metric.major-financial_metrics-6"]))
        self.assertIn("appen.metric.major-growth_metrics-5", appen)
        for cid, mid in (("prolific", "prolific.metric.audit-2"), ("labelbox", "labelbox.metric.major-financial_metrics-1"), ("scale_ai", "scale_ai.claim.growth_metrics-3.metric-0"), ("invisible", "invisible.metric.major-valuation"), ("afterquery", "afterquery.metric.round2-financial-3")):
            self.assertNotIn(mid, dict(self.figures(cid)[0]), cid)
        self.assertIn("April 2026 · reported", plain(dict(self.figures("handshake_ai")[0])["handshake_ai.metric.major-growth_metrics-0"]))
        self.assertIn("Historical", plain(dict(self.figures("a-team")[0])["a-team.claim.growth_metrics-2.metric-0"]))
        self.assertIn("12 years", plain(dict(self.figures("a-team")[0])["a-team.metric.oct14-2-experience"]))

    def test_value_and_date_formatting(self):
        cases = {119920000: "119.92M", 2000000000: "2B", 483600000: "483.6M", 63200: "63,200", 0.686: "0.69", 300000: "300K", 1250000000: "1.25B", 12.0: "12"}
        for value, expected in cases.items(): self.assertEqual(sp.number_text(value), expected, value)
        self.assertEqual(sp.value_text({"value": -40100000, "unit": "currency", "currency": "USD", "qualifier": "exact"}), "−$40.1M")
        self.assertEqual(sp.value_text({"value": 175000000, "unit": "currency", "currency": "USD", "qualifier": "greater_than"}), "more than $175M")
        self.assertEqual(sp.value_text({"value": 15000000, "unit": "currency", "currency": "AUD", "qualifier": "exact"}), "AUD 15M")
        self.assertEqual(sp.value_text({"value": 18.0, "unit": "other", "qualifier": "exact", "basis": "Missions; original value: 18 months"}), "18 months")
        self.assertEqual(sp.value_text({"value": 25.5, "unit": "other", "qualifier": "exact", "basis": "original value: 25.5% ±3.6"}), "25.5%")
        periods = {"FY ended 2025-12-31": "FY2025", "2026-06": "Jun 2026", "as of 2026-06-30": "30 Jun 2026", "2026-H1": "H1 2026", "2026 H1": "H1 2026", "2025-Q1": "Q1 2025", "undated": "Date not stated", "2025-end (reported)": "End of 2025 (reported)", "pricing date before 2025-03-06; exact date undisclosed": "Pricing date before 6 Mar 2025; exact date undisclosed"}
        for raw, expected in periods.items(): self.assertEqual(sp.period_text(raw), expected, raw)

    def test_app_constants_are_read_strictly(self):
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "x.js"
            script.write_text("const A={a:'1', 'b c':\"2\",\n  d:'x & y',\n};\nconst B={a:value};\nconst C={};\n")
            self.assertEqual(sp.read_js_object(script, "A"), {"a": "1", "b c": "2", "d": "x & y"})
            for name in ("B", "C", "D"):
                with self.assertRaises(ValueError): sp.read_js_object(script, name)
            script.write_text("const A={a:'1'};\nconst A={a:'2'};\n")
            with self.assertRaises(ValueError): sp.read_js_object(script, "A")

    def test_company_descriptions_are_whole_sentences(self):
        for cid, text in self.pages.items():
            description, name = PageFacts(text).meta["description"], self.companies[cid]["name"]
            self.assertTrue(description.startswith(name + " ") or description.startswith(name + ":"), (cid, description))
            self.assertTrue(description.endswith("."), (cid, description))
            self.assertNotIn("…", description, cid)
            lede = html.unescape(re.search(r'<p class="lede">(.*?)</p>', text).group(1))
            first = sp.sentences(lede)[0]
            self.assertIn(first[1:], description, cid)

    # Risks and disputes, link checks

    def test_risk_statements_read_as_public_sentences(self):
        for cid, sentence, instruction in (
            ("laude", "The $100M philanthropy pledge, Institute grants, Laude Ventures capital and benchmark grant support are not comparable", "Do not compare the $100M"),
            ("pareto", "pareto.ai is unrelated to Pareto Securities", "Do not confuse pareto.ai"),
            ("micro1", "Latest financing was reported without company confirmation, and the participating labs are not named.", "fabricated"),
            ("a-team", "Its full 11,000-builder network is not a count of AI-data contributors, and unnamed RL delivery cases are not named-customer validation.", "or interpret unnamed RL"),
            ("scale_ai", "Meta’s 49% stake raised customer-independence concerns", "Meta ownership triggered"),
        ):
            self.assertIn(html.escape(sentence), self.pages[cid], cid)
            self.assertNotIn(html.escape(instruction), self.pages[cid], cid)
        changed = 0
        for claim in self.data["claims"]:
            if claim.get("subject") != "risks" or claim.get("status") != "supported": continue
            self.assertIn(f'<tr data-risk="{claim["id"]}"><th scope="row">{html.escape(sp.clean(self.say(claim["statement"])))}</th>', self.pages[claim["company_id"]], claim["id"])
            changed += self.say(claim["statement"]) != claim["statement"]
        self.assertGreater(changed, 10)

    def test_risk_section_lists_dated_events_then_risks_newest_first(self):
        for cid, text in self.pages.items():
            dated = sp.company_events(self.events, cid)
            risks = sp.risk_claims(self.research, cid)
            if not dated and not risks:
                self.assertNotIn('id="risks"', text, cid)
                continue
            section = text.split('<h2 id="risks">', 1)[1].split('<h2 id="work">', 1)[0]
            self.assertEqual(re.findall(r'<tr data-event="([^"]+)">', section), [e["id"] for e in dated], cid)
            self.assertEqual(re.findall(r'<tr data-risk="([^"]+)">', section), [c["id"] for c in risks], cid)
            self.assertEqual([e["date"] for e in dated], sorted((e["date"] for e in dated), reverse=True), cid)
            self.assertEqual(sp.EVENTS_NOTE in section, bool(dated), cid)
            self.assertIn(f'href="{ORIGIN}/#company/{cid}/risks"', section, cid)
        mercor = self.pages["mercor"].split("<h3>Risks named in the evidence</h3>", 1)[1].split("</table>", 1)[0]
        self.assertIn('<td class="date" data-label="As of">Jun 2026</td>', mercor)
        self.assertIn('<td class="date" data-label="Date">Source date not stated</td>', mercor)
        self.assertIn("Statuses were checked on 23 Oct 2026.", self.pages["mercor"])
        self.assertIn("@media(min-width:701px){table.events td:last-child a{white-space:nowrap}}", sp.STYLE)

    def test_dead_evidence_links_carry_the_link_check(self):
        self.assertIn('href="https://jobs.ashbyhq.com/elorian-ai-inc/69acef27-d755-4b22-8257-94759edb0efb">', self.pages["elorian"])
        self.assertIn("(page unavailable when checked 23 Oct 2026)", self.pages["elorian"])
        self.assertIn("(page unavailable when checked 23 Oct 2026)", self.pages["labelbox"])
        self.assertNotIn("when checked", self.pages["mercor"])

    # Paid work, method and 404 pages

    def test_work_page_lists_every_listing_once_in_worker_groups(self):
        text = (self.dist / "work/index.html").read_text()
        listed = re.findall(r'<tr data-work-route="([^"]+)">', text)
        self.assertEqual(sorted(listed), sorted(r["id"] for r in self.routes))
        order = [key for key, _, _ in sp.WORK_BUCKETS if any(sp.work_bucket(r) == key for r in self.routes)]
        self.assertEqual(re.findall(r'<h2 id="([a-z]+)">', text), order)
        self.assertIn(f'href="{sp.SCAM_GUIDE}"', text)
        self.assertIn("Never pay to get work.", text)
        self.assertNotIn("JobPosting", text)
        self.assertNotRegex(plain(text), r"\((?:listed|program|intake unverified|careers|no route)\)|\b(?:intake_unverified|no_route|pay_conflict)\b")
        self.assertEqual(structured_data(text)["@type"], "CollectionPage")

    def test_work_groups_match_the_app(self):
        app = (ROOT / "web/work-v4.js").read_text() + (ROOT / "web/work-v3.js").read_text()
        for _, label, note in sp.WORK_BUCKETS:
            self.assertIn(label, app, "static work group label drifted from the app")
            self.assertIn(note, app, "static work group note drifted from the app")
        archive = re.search(r"const WORK_ROUTE_ARCHIVE=new Set\(\[([^\]]*)\]\)", app).group(1)
        self.assertEqual(set(re.findall(r"'([a-z_]+)'", archive)), set(sp.WORK_ARCHIVE))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_every_listing_gets_the_apps_group_status_place_and_pay(self):
        """w4Bucket, w4Status, w4Location and w4Pay in web/work-v4.js, run in Node: the static pages print the same words (B5, B7)."""
        modules = ["web/app.js", "web/editorial.js", "web/work-v3.js"] + ["web/" + name for name in PRESENTATION_JS]
        result = subprocess.run(["node", "-e", APP_RULES, str(ROOT), json.dumps(modules)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        app = json.loads(result.stdout)["work"]
        self.assertEqual(sorted(app), sorted(r["id"] for r in self.routes))
        for route in self.routes:
            static = {"bucket": sp.work_bucket(route), "status": sp.work_status(route), "place": sp.work_location(route), "pay": sp.work_pay(route)}
            self.assertEqual(static, app[route["id"]], route["id"])
        statuses = {r["id"]: sp.work_status(r) for r in self.routes}
        for route in self.routes:
            if route["status"] == "no_route": self.assertEqual(statuses[route["id"]], "No confirmed paid listing", route["id"])
        # An Employment listing paid by the hour or by a one-time award is contract and task work (B7).
        for route in self.routes:
            if route.get("group") == "Employment" and route.get("pay_basis") in ("hour", "one_time") and sp.work_bucket(route) not in ("boards", "closed", "outside"):
                self.assertEqual(sp.work_bucket(route), "contract", route["id"])
        self.assertEqual({sp.work_bucket(r) for r in self.routes if r["id"] in ("afterquery.work.technical-content-writer-contract", "afterquery.work.research-scholar")}, {"contract"})

    def test_listing_counts_come_from_the_data(self):
        """Paid work listings are the contract and jobs groups; company counts follow the brief's wording (B1, B3)."""
        paid = [r for r in self.routes if sp.work_bucket(r) in sp.PAID_OPEN_BUCKETS]
        paid_companies, all_companies = len({r["company_id"] for r in paid}), len({r["company_id"] for r in self.routes})
        work = (self.dist / "work/index.html").read_text()
        facts = PageFacts(work)
        self.assertEqual(facts.title, f"{len(paid)} paid work listings in AI training{sp.SUFFIX}")
        self.assertTrue(facts.meta["description"].startswith(f"{len(paid)} paid work listings in AI training at {paid_companies} AI data companies,"), facts.meta["description"])
        lede = plain(re.search(r'<p class="lede">.*?</p>', work).group(0))
        self.assertTrue(lede.startswith(f"{len(paid)} paid work listings at {paid_companies} AI data companies, out of {len(self.routes)} listings we reviewed at {all_companies} companies."), lede)
        self.assertIn(f"See {len(paid)} paid work listings</a>", (self.dist / "companies/index.html").read_text())
        checked = max(d for r in self.routes for d in (r.get("availability_checked_on"), (r.get("last_route_check") or {}).get("date")) if d)
        self.assertIn(f"links checked up to {sp.format_date(checked)}", work)
        for path in self.html_files():
            self.assertNotRegex(plain(path.read_text()), r"\bopen (?:paid work )?listings?\b", str(path.relative_to(self.dist)))

    def test_company_pages_list_their_listings_in_worker_groups(self):
        labels = [label for _, label, _ in sp.WORK_BUCKETS]
        closed_label = dict((key, label) for key, label, _ in sp.WORK_BUCKETS)["closed"]
        for cid, text in self.pages.items():
            own = [r for r in self.routes if r["company_id"] == cid]
            section = text.split('<h2 id="work">', 1)[1].split("<h2", 1)[0]
            self.assertEqual(sorted(re.findall(r'data-work-route="([^"]+)"', section)), sorted(r["id"] for r in own), cid)
            headings = re.findall(r"<h3>(.*?)</h3>", section)
            self.assertEqual(headings, sorted(headings, key=labels.index), cid)
            if own: self.assertIn("Never pay to get work.", section, cid)
            closed = section.split(f"<h3>{closed_label}</h3>", 1)[1] if f"<h3>{closed_label}</h3>" in section else ""
            self.assertNotIn("Pay: ", closed, cid)
            self.assertNotIn("Where: ", closed, cid)
            # Field names are not repeated: "Pay not listed", never "Pay: Pay not listed" (coordinator E5).
            self.assertNotRegex(section, r"Pay: Pay|Where: Location not listed", cid)
            if not own: continue
            # The count names paid work listings only, and the pay sentence appears only when there is one (B2).
            paid = sum(1 for r in own if sp.work_bucket(r) in sp.PAID_OPEN_BUCKETS)
            lead = plain(re.search(r"<p>(.*?)</p>", section).group(1))
            name = self.companies[cid]["name"]
            if paid: self.assertTrue(lead.startswith(f"{paid} paid work listing{'s' if paid != 1 else ''} at {name}. Pay is quoted"), (cid, lead))
            else: self.assertEqual(lead, f"No confirmed paid listing for {name}. The groups below show what we found.", cid)
        self.assertIn("No confirmed paid listing for Quesma.", self.pages["quesma"])
        self.assertIn("Pay not listed. Where:", self.pages["turing"] + self.pages["prolific"])

    def test_method_page_describes_the_dataset_and_its_license(self):
        """The owner chose CC BY 4.0 with ScienceToStartup as licensor (25 Oct 2026), so this test now requires the license
        it used to forbid. /method/ describes the home page's Dataset node: same @id and name, one Person as publisher."""
        text = (self.dist / "method/index.html").read_text()
        facts = PageFacts(text)
        for anchor in ("about", "figures", "grades", "labels", "coverage", "downloads"): self.assertIn(anchor, facts.ids)
        nodes = ld_nodes(text)
        self.assertEqual([node["@type"] for node in nodes], ["AboutPage", "Dataset"])
        page, dataset = nodes
        self.assertEqual((dataset["@id"], dataset["name"], dataset["license"]), (sp.DATASET_ID, sp.DATASET_NAME, "https://creativecommons.org/licenses/by/4.0/"))
        self.assertEqual((dataset["publisher"], dataset["creator"]), ({"@id": sp.PUBLISHER["@id"]}, {"@id": sp.PUBLISHER["@id"]}))
        self.assertEqual(page["publisher"], sp.PUBLISHER)
        home = [node for node in ld_nodes((self.dist / "index.html").read_text().split("</head>", 1)[0]) if node.get("@type") == "Dataset"]
        self.assertEqual([(node["@id"], node["name"], node["license"]) for node in home], [(dataset["@id"], dataset["name"], dataset["license"])], "one dataset identity")
        downloads = text.split('<h2 id="downloads">', 1)[1].split("<h2", 1)[0]
        license_paragraphs = [p for p in re.findall(r"<p>(.*?)</p>", downloads) if "license" in p]
        self.assertEqual(len(license_paragraphs), 1, "one short license paragraph")
        self.assertIn('<a class="ext" rel="license" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0 license</a>', license_paragraphs[0])
        self.assertTrue(plain(license_paragraphs[0]).startswith("ScienceToStartup licenses this data under the CC BY 4.0 license"))
        self.assertIn("Company names and logos belong to their owners.", license_paragraphs[0])
        self.assertIn("The research data files keep every claim that later research replaced.", downloads)
        self.assertNotIn("every original record", text)
        self.assertIn("Profiles do not show personal contact details.", text)
        rated = {a["company_id"] for a in self.data["assessments"]}
        unrated = [c for c in self.data["companies"] if c["id"] not in rated]
        self.assertTrue(unrated and all(c["entity_type"] == "adjacent_research" for c in unrated))
        self.assertIn(f"{len(rated)} companies with a delivery evidence level", text)
        self.assertIn(f"The {sp.count_word(len(unrated)).lower()} nonprofit research groups get no level.", text)
        self.assertNotIn("delivery evidence rating", text)
        self.assertTrue(50 <= len(dataset["description"]) <= 5000)
        self.assertEqual(dataset["version"], self.data["dataset_version"])
        for download in dataset["distribution"]:
            name = download["contentUrl"].replace(ORIGIN + "/", "")
            self.assertTrue((self.dist / name).is_file(), name)
            self.assertIn(f'href="{download["contentUrl"]}"', text)
        self.assertIn(f"{ORIGIN}/business-health.json", [d["contentUrl"] for d in dataset["distribution"]])
        self.assertIn("Musa Ozdem", text)
        self.assertIn(str(sum(1 for c in self.data["claims"] if c["status"] in ("unverified", "contested"))), text)

    def test_not_found_page_is_noindex_and_points_home(self):
        text = (self.dist / "404.html").read_text()
        facts = PageFacts(text)
        self.assertEqual(facts.meta.get("robots"), "noindex")
        self.assertEqual(facts.canonicals, [])
        self.assertEqual(facts.headings, ["We could not find that page."])
        for path in ("/", "/companies/", "/work/", "/method/", "/#about", "/?search"): self.assertIn(f'href="{ORIGIN}{path}"', text)
        self.assertEqual([(l.get("rel"), l.get("href")) for l in facts.links if "icon" in str(l.get("rel"))], ICONS)
        self.assertIn("--bg:#f8f8f4;--ink:#18231f", sp.STYLE, "the edition palette")
        self.assertFalse((ROOT / "web/404.html").exists(), "404.html is generated by scripts/static_pages.py")

    def test_research_text_cannot_break_out_of_static_pages(self):
        sys.path.insert(0, str(ROOT / "tests"))
        from fixtures import fixture
        data = fixture()
        data["companies"][0]["description"] = '</script><script>window.PWNED=1</script>'
        with tempfile.TemporaryDirectory() as temp:
            build(data, Path(temp))
            for path in Path(temp).rglob("*.html"):
                if path.name != "index.html" or path.parent != Path(temp): self.assertNotIn("<script>window.PWNED", path.read_text(), str(path))


if __name__ == "__main__":
    unittest.main()
