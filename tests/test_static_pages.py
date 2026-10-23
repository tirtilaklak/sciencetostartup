"""Crawlable static pages, the figure rules they share with the app, and the generated sitemap, built into a scratch directory."""
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
 r.ids=DATA.metrics.map(m=>m.id).sort((a,b)=>a.localeCompare(b));r.names=DATA.companies.map(c=>c.name).concat(window.WORK_ROUTES.routes.map(w=>w.role)).sort((a,b)=>a.localeCompare(b));
 return r;})())`,context));
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


def plain(fragment):
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).replace("&amp;", "&").replace("&#x27;", "'").split())


class StaticPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.temp = tempfile.TemporaryDirectory(prefix="static-pages-")
        cls.dist = Path(cls.temp.name)
        build(cls.data, cls.dist)
        cls.companies = {c["id"]: c for c in cls.data["companies"]}
        cls.pages = {cid: (cls.dist / "company" / cid / "index.html").read_text() for cid in cls.companies}
        cls.research = sp.Research(cls.data, sp.read_js_object(ROOT / "web/app.js", "FINANCIAL_HEADLINES"), json.loads((ROOT / "data/source-updates.json").read_text()))
        cls.metrics = {m["id"]: m for m in cls.data["metrics"]}
        cls.routes = json.loads((ROOT / "data/work-routes.json").read_text())["routes"]
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

    def figures(self, cid):
        """(metric id, row html) for each Key figures row, and (metric id, item html) for each Not confirmed item."""
        section = self.pages[cid].split('<h2 id="figures">', 1)[1].split('<h2 id="facts"', 1)[0]
        return re.findall(r'<tr data-metric="([^"]+)">(.*?)</tr>', section, re.S), re.findall(r'<li data-metric="([^"]+)">(.*?)</li>', section, re.S)

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
            self.assertTrue(facts.title.startswith(name + ":"), (cid, facts.title))
            self.assertLessEqual(len(facts.title), sp.TITLE_LIMIT, (cid, facts.title))
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
            self.assertEqual([item["item"] for item in structured["breadcrumb"]["itemListElement"]], [ORIGIN + "/", ORIGIN + "/companies/", f"{ORIGIN}/company/{cid}/"], cid)
            self.assertEqual(structured["publisher"]["name"], "Musa Ozdem", cid)
        for name in ("work", "method"):
            self.assertLess(len((self.dist / name / "index.html").read_bytes()), PAGE_LIMIT, name)

    def test_sitemap_lists_every_page_with_lastmod(self):
        root = ET.parse(self.dist / "sitemap.xml").getroot()
        self.assertEqual(root.tag, NAMESPACE + "urlset")
        urls = root.findall(NAMESPACE + "url")
        self.assertEqual(len(urls), 4 + len(self.companies))
        locs = [u.find(NAMESPACE + "loc").text for u in urls]
        self.assertEqual(locs[:2] + locs[-2:], [ORIGIN + "/", ORIGIN + "/companies/", ORIGIN + "/work/", ORIGIN + "/method/"])
        self.assertEqual(sorted(locs[2:-2]), sorted(f"{ORIGIN}/company/{cid}/" for cid in self.companies))
        for url in urls:
            lastmod = url.find(NAMESPACE + "lastmod").text
            self.assertRegex(lastmod, r"^\d{4}-\d{2}-\d{2}$")
            self.assertGreaterEqual(lastmod, self.data["meta"]["as_of"], url.find(NAMESPACE + "loc").text)
            self.assertLessEqual(lastmod, max(sp.SITE_REVISED, self.data["meta"]["as_of"], *(d for r in self.routes for d in sp.route_dates(r) if d)))

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
            self.assertEqual({(l.get("rel"), l.get("href")) for l in facts.links if "icon" in str(l.get("rel"))}, {("icon", "/favicon.ico"), ("icon", "/assets/icon-192.png"), ("apple-touch-icon", "/assets/icon-192.png")}, label)
            self.assertIn(f'href="{ORIGIN}/#corrections"', text, label)
            self.assertNotIn("—", text, label)
            for anchor in facts.anchors:
                href = anchor.get("href", "")
                if href.startswith("http") and not href.startswith(ORIGIN): self.assertEqual(anchor.get("class"), "ext", (label, href))
                if href.startswith(ORIGIN): self.assertNotEqual(anchor.get("class"), "ext", (label, href))
        self.assertIn('aria-current="page">Companies<', (self.dist / "companies/index.html").read_text())
        self.assertIn('aria-current="true">Companies<', self.pages["mercor"])
        self.assertIn('aria-current="page">Paid work<', (self.dist / "work/index.html").read_text())

    def test_share_cards_on_indexable_pages(self):
        for path in [p for p in self.html_files() if p.name != "404.html"] + [self.dist / "index.html"]:
            meta, label = PageFacts(path.read_text()).meta, str(path.relative_to(self.dist))
            self.assertEqual(meta["og:image"], sp.SHARE_IMAGE, label)
            self.assertEqual((meta["og:image:width"], meta["og:image:height"]), ("1200", "630"), label)
            self.assertEqual(meta["twitter:card"], "summary_large_image", label)
            self.assertTrue(meta["og:image:alt"] and meta["twitter:image:alt"] == meta["og:image:alt"], label)
        image = (self.dist / sp.SHARE_IMAGE.replace(ORIGIN + "/", "")).read_bytes()
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", image[16:24]), (1200, 630))
        self.assertLess(len(image), 100_000)
        icon = (self.dist / "assets/icon-192.png").read_bytes()
        self.assertEqual(struct.unpack(">II", icon[16:24]), (192, 192))
        ico = (self.dist / "favicon.ico").read_bytes()
        reserved, kind, count = struct.unpack("<HHH", ico[:6])
        self.assertEqual((reserved, kind), (0, 1))
        for index in range(count):
            width, height, _, _, _, _, size, offset = struct.unpack("<BBBBHHII", ico[6 + 16 * index: 22 + 16 * index])
            self.assertEqual(ico[offset:offset + 8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", ico[offset + 16: offset + 24]), (width or 256, height or 256))

    def test_home_head_names_the_site_and_publisher(self):
        text = (self.dist / "index.html").read_text()
        head = text.split("</head>", 1)[0]
        self.assertEqual(PageFacts(head).canonicals, [ORIGIN + "/"])
        self.assertNotIn("data:image/svg+xml", head.split("<style>", 1)[0])
        website = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', head, re.S).group(1))
        self.assertEqual((website["@type"], website["@id"], website["url"], website["name"]), ("WebSite", ORIGIN + "/#website", ORIGIN + "/", "ScienceToStartup"))
        self.assertEqual(website["publisher"], sp.PUBLISHER)
        self.assertIn(str(len(self.companies)), website["description"])

    def test_no_email_addresses_leak_into_public_pages(self):
        for path in self.public_files():
            self.assertIsNone(EMAIL.search(path.read_text()), str(path.relative_to(self.dist)))

    def test_manifest_covers_the_static_pages(self):
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        for name in ("sitemap.xml", "companies/index.html", "company/mercor/index.html", "work/index.html", "method/index.html", "404.html", "favicon.ico", "assets/icon-192.png", "assets/share/sciencetostartup-1200x630.png"): self.assertIn(name, manifest)
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

    # Figures follow the app's rules (red-team RED-1, RED-2, RED-3, RED-10, RED-11, RED-13 and IA-11)

    def test_static_rules_match_the_app_code_in_node(self):
        node = shutil.which("node")
        if not node: self.skipTest("Node is not installed")
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

    def test_key_figures_hold_only_eligible_figures_led_by_the_app_headline(self):
        for cid in self.companies:
            rows, pending = self.figures(cid)
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
                metric, text = self.metrics[mid], plain(item)
                self.assertNotIn(mid, [m["id"] for m in shown], cid)
                self.assertRegex(text, r"In reported talks|Unverified|Conflicting reports", mid)
            for mid in re.findall(r'data-metric="([^"]+)"', self.pages[cid]):
                self.assertNotIn(self.metrics[mid].get("observation_status"), ("forecast", "target"), mid)

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
                self.assertNotRegex(text, r"\b[a-z]+_[a-z_]+\b", mid)
                self.assertNotRegex(text, r"[$£€]-|\d{4}-\d{2}(?:-\d{2})?", mid)

    def test_red_team_regressions_stay_fixed(self):
        mercor_rows, mercor_pending = self.figures("mercor")
        self.assertEqual(mercor_rows[0][0], "mercor.metric.oct14-major-financial-2")
        self.assertIn("gross (Sacra estimate)", plain(mercor_rows[0][1]))
        self.assertIn("mercor.metric.major-valuation_alternatives", [mid for mid, _ in mercor_pending])
        self.assertNotIn("$20B", "".join(plain(row) for _, row in mercor_rows))
        self.assertEqual(self.figures("turing")[0][0][0], "turing.metric.major-growth_metrics-1")
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

    def test_company_pages_list_their_listings_in_worker_groups(self):
        labels = [label for _, label, _ in sp.WORK_BUCKETS]
        for cid, text in self.pages.items():
            own = [r for r in self.routes if r["company_id"] == cid]
            section = text.split('<h2 id="work">', 1)[1].split("<h2", 1)[0]
            self.assertEqual(sorted(re.findall(r'data-work-route="([^"]+)"', section)), sorted(r["id"] for r in own), cid)
            headings = re.findall(r"<h3>(.*?)</h3>", section)
            self.assertEqual(headings, sorted(headings, key=labels.index), cid)
            if own: self.assertIn("Never pay to get work.", section, cid)
            closed = section.split("<h3>Closed or unpaid links</h3>", 1)[1] if "<h3>Closed or unpaid links</h3>" in section else ""
            self.assertNotIn("Pay: ", closed, cid)

    def test_method_page_describes_the_dataset_without_a_license(self):
        text = (self.dist / "method/index.html").read_text()
        facts = PageFacts(text)
        for anchor in ("about", "figures", "grades", "labels", "coverage", "downloads"): self.assertIn(anchor, facts.ids)
        page, dataset = structured_data(text)
        self.assertEqual(page["@type"], "AboutPage")
        self.assertEqual(dataset["@type"], "Dataset")
        self.assertNotIn("license", dataset)
        self.assertTrue(50 <= len(dataset["description"]) <= 5000)
        self.assertEqual(dataset["version"], self.data["dataset_version"])
        for download in dataset["distribution"]:
            name = download["contentUrl"].replace(ORIGIN + "/", "")
            self.assertTrue((self.dist / name).is_file(), name)
            self.assertIn(f'href="{download["contentUrl"]}"', text)
        self.assertIn("Musa Ozdem", text)
        self.assertIn(str(sum(1 for c in self.data["claims"] if c["status"] in ("unverified", "contested"))), text)

    def test_not_found_page_is_noindex_and_points_home(self):
        text = (self.dist / "404.html").read_text()
        facts = PageFacts(text)
        self.assertEqual(facts.meta.get("robots"), "noindex")
        self.assertEqual(facts.canonicals, [])
        self.assertEqual(facts.headings, ["We could not find that page."])
        for path in ("/", "/companies/", "/work/", "/method/"): self.assertIn(f'href="{ORIGIN}{path}"', text)

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
