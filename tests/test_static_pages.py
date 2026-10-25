"""Crawlable static company pages and the generated sitemap, built into a scratch directory."""
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import build
from static_pages import METRIC_LIMIT, REWORDED_FIELDS, STYLE, analytics_endpoint, document, headline_metrics, load_copy_edits, public_wording

ORIGIN = "https://sciencetostartup.com"
NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
EMAIL = re.compile(r"@[A-Za-z0-9-]+\.[A-Za-z]{2,}")
PAGE_LIMIT = 120_000
OG_IMAGE = ORIGIN + "/assets/og/sciencetostartup-og-v1.png"
# eligibleMetrics in web/app.js decides which figure the app compares; the static pages must agree with it.
APP_RULE = "m.preferred_for_comparison!==false&&claims[m.claim_id].status==='supported'&&(!m.observation_status||m.observation_status==='reported')"
APP_PICKS = r"""
const fs=require('fs'),app=fs.readFileSync(process.argv[1],'utf8'),DATA=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const claims=Object.fromEntries(DATA.claims.map(c=>[c.id,c])),grab=re=>{const m=app.match(re);if(!m)throw new Error('web/app.js changed: '+re);return m[1]??m[0];};
eval(grab(/function dateRank\(s\)\{.*/));const byRecent=eval(grab(/const byRecent=(.*?);\n/));eval(grab(/function eligibleMetrics\(id,kind\)\{.*/));
const picks={};for(const m of DATA.metrics){const first=eligibleMetrics(m.company_id,m.kind)[0];if(first)picks[m.company_id+'|'+m.kind]=first.id;}
console.log(JSON.stringify(picks));
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
    """Canonical links, h1 headings, title, meta tags, icon links and script tags of a static page."""
    def __init__(self, text):
        super().__init__()
        self.canonicals, self.headings, self.scripts, self.icons, self.meta, self.title = [], [], [], [], {}, ""
        self._capture, self._buffer = None, []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical": self.canonicals.append(attrs.get("href"))
        if tag == "link" and "icon" in attrs.get("rel", ""): self.icons.append(attrs)
        if tag == "meta" and (attrs.get("property") or attrs.get("name")): self.meta[attrs.get("property") or attrs.get("name")] = attrs.get("content")
        if tag == "script": self.scripts.append(attrs)
        if tag in ("h1", "title"): self._capture, self._buffer = tag, []

    def handle_data(self, data):
        if self._capture: self._buffer.append(data)

    def handle_endtag(self, tag):
        if tag != self._capture: return
        text = "".join(self._buffer)
        if tag == "h1": self.headings.append(text)
        else: self.title = text
        self._capture = None


class StaticPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.temp = tempfile.TemporaryDirectory(prefix="static-pages-")
        cls.dist = Path(cls.temp.name)
        build(cls.data, cls.dist)
        cls.companies = {c["id"]: c for c in cls.data["companies"]}
        cls.pages = {cid: (cls.dist / "company" / cid / "index.html").read_text() for cid in cls.companies}

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def public_files(self):
        return sorted(self.dist.glob("company/*/index.html")) + [self.dist / "companies/index.html", self.dist / "sitemap.xml"]

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
            self.assertIn(f'href="{ORIGIN}/#company/{cid}"', text, cid)

    def test_pages_stay_lean_without_app_script_or_dataset(self):
        for cid, text in self.pages.items():
            self.assertLess(len(text.encode()), PAGE_LIMIT, cid)
            self.assertEqual([s.get("type") for s in PageFacts(text).scripts], ["application/ld+json"], cid)
            self.assertNotIn('id="research-data"', text, cid)
            structured = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S).group(1))
            self.assertEqual(structured["mainEntity"]["name"], self.companies[cid]["name"], cid)
            self.assertEqual(structured["isPartOf"]["url"], ORIGIN + "/", cid)

    def test_sitemap_lists_root_index_and_every_company_with_lastmod(self):
        root = ET.parse(self.dist / "sitemap.xml").getroot()
        self.assertEqual(root.tag, NAMESPACE + "urlset")
        urls = root.findall(NAMESPACE + "url")
        self.assertEqual(len(urls), 41)
        locs = [u.find(NAMESPACE + "loc").text for u in urls]
        self.assertEqual(locs[:2], [ORIGIN + "/", ORIGIN + "/companies/"])
        self.assertEqual(sorted(locs[2:]), sorted(f"{ORIGIN}/company/{cid}/" for cid in self.companies))
        reviewed = json.loads((ROOT / "data/company-events.json").read_text())["reviewed_on"]
        modified = max(self.data["meta"]["as_of"], reviewed)  # events reviewed after the dataset change the pages too
        for url in urls: self.assertEqual(url.find(NAMESPACE + "lastmod").text, modified, url.find(NAMESPACE + "loc").text)
        for text in list(self.pages.values()) + [(self.dist / "companies/index.html").read_text()]:
            self.assertIn(f'"dateModified":"{modified}"', text)

    def test_index_page_links_every_company_and_the_app(self):
        text = (self.dist / "companies/index.html").read_text()
        self.assertEqual(PageFacts(text).canonicals, [ORIGIN + "/companies/"])
        for cid in self.companies: self.assertIn(f'href="{ORIGIN}/company/{cid}/"', text, cid)
        self.assertIn(f'href="{ORIGIN}/#companies"', text)

    def test_no_email_addresses_leak_into_public_pages(self):
        for path in self.public_files():
            self.assertIsNone(EMAIL.search(path.read_text()), str(path.relative_to(self.dist)))

    def test_manifest_covers_the_static_pages(self):
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        for name in ("sitemap.xml", "companies/index.html", "company/mercor/index.html"): self.assertIn(name, manifest)
        self.assertEqual(sum(1 for n in manifest if n.startswith("company/") and n.endswith("/index.html")), 39)

    def test_headline_rows_pass_the_app_comparison_rule(self):
        self.assertIn(APP_RULE, (ROOT / "web/app.js").read_text(), "eligibleMetrics changed in web/app.js; update static_pages.exclusion and this port")
        claims, metrics = {c["id"]: c for c in self.data["claims"]}, {m["id"]: m for m in self.data["metrics"]}
        eligible = lambda m: m.get("preferred_for_comparison") is not False and claims[m["claim_id"]]["status"] == "supported" and (not m.get("observation_status") or m["observation_status"] == "reported")
        shown = 0
        for cid in self.companies:
            rows, others = headline_metrics(self.data, cid)
            for row in rows: self.assertTrue(eligible(metrics[row["id"]]), (cid, row["id"]))
            for row in others:
                self.assertFalse(eligible(metrics[row["id"]]), (cid, row["id"]))
                self.assertIn(row["status"], ("unverified", "contested", "talks", "forecast", "target", "not preferred"), (cid, row["id"]))
            shown += len(rows)
        self.assertGreater(shown, 100)
        found = {(cid, row["value"], row["status"]) for cid in self.companies for row in headline_metrics(self.data, cid)[1]}
        self.assertLessEqual({("scale_ai", "$200M", "unverified"), ("invisible", "more than $2B", "unverified"), ("afterquery", "$3.2B", "talks"), ("micro1", "$1B", "target"), ("labelbox", "$189M", "not preferred"), ("prolific", "$500M", "forecast")}, found)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_headline_pick_matches_the_app_code(self):
        picks = json.loads(subprocess.run(["node", "-e", APP_PICKS, str(ROOT / "web/app.js"), str(ROOT / "data/canonical.json")], check=True, capture_output=True, text=True).stdout)
        kinds = {m["id"]: m["kind"] for m in self.data["metrics"]}
        for cid in self.companies:
            expected = {kind: mid for key, mid in picks.items() for company, kind in [key.split("|")] if company == cid}
            rows = headline_metrics(self.data, cid)[0]
            self.assertEqual(len(rows), min(len(expected), METRIC_LIMIT), cid)
            for row in rows: self.assertEqual(row["id"], expected[kinds[row["id"]]], (cid, row["kind"]))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_printed_text_matches_the_app_wording(self):
        """Research fields go through the Python port of publicText; sidecar copy must already be in final form."""
        research = sorted({row[field] for table, fields in REWORDED_FIELDS.items() for row in self.data[table] for field in fields if isinstance(row.get(field), str)})
        load = lambda name: json.loads((ROOT / "data" / name).read_text())
        editorial, profiles, work = load("editorial.json")["entries"], load("profile-content.json")["entries"], load("work-routes.json")["routes"]
        events = load("company-events.json")["events"] if (ROOT / "data/company-events.json").exists() else []
        sidecar = {c["name"] for c in self.data["companies"]}
        sidecar |= {e.get(field) for e in editorial for field in ("summary", "primary_offering", "precise_category")}
        sidecar |= {p.get(field) for entry in profiles for p in entry.get("products", []) for field in ("name", "description")}
        sidecar |= {r.get(field) for r in work for field in ("role", "pay_label")}
        sidecar |= {e[field] for e in events for field in ("title", "detail", "status")} | {s["publisher"] for e in events for s in e["sources"]}
        sidecar = sorted(text for text in sidecar if isinstance(text, str) and text)
        strings = research + sidecar
        shown = json.loads(subprocess.run(["node", "-e", APP_WORDING, str(ROOT / "web/app.js"), str(ROOT / "data/canonical.json")], input=json.dumps(strings), check=True, capture_output=True, text=True).stdout)
        say = public_wording(self.data, load_copy_edits())
        self.assertGreater(len(load_copy_edits()), 100)
        for text, app in zip(research, shown): self.assertEqual(say(text), app, text)
        for text, app in zip(sidecar, shown[len(research):]): self.assertEqual(text, app, "the app rewords this sidecar text; reword it at the source or pass it through public_wording")

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
        say, changed = public_wording(self.data, load_copy_edits()), 0
        for claim in self.data["claims"]:
            if claim.get("subject") != "risks" or claim.get("status") != "supported": continue
            self.assertIn(f"<tr><td>{html.escape(say(claim['statement']))}</td>", self.pages[claim["company_id"]], claim["id"])
            changed += say(claim["statement"]) != claim["statement"]
        self.assertGreater(changed, 10)

    def test_headline_rows_name_their_scope_and_revenue_period(self):
        taskus = self.pages["taskus"]
        self.assertIn("trailing twelve month revenue · AI Services service line</span></td><td class=\"value\">$244.2M", taskus)
        self.assertIn("revenue growth yoy percent · AI Services service line", taskus)
        self.assertIn("CEO-reported revenue week · One week; exact week-end unspecified", self.pages["prolific"])
        self.assertIn("Older or partial figure", self.pages["labelbox"])
        self.assertNotIn("Not preferred", "".join(self.pages.values()))
        self.assertNotIn("DeepSWE pass@1, base", self.pages["afterquery"])

    def test_dead_evidence_links_carry_the_link_check(self):
        self.assertIn('elorian-ai-inc/69acef27-d755-4b22-8257-94759edb0efb" rel="noopener">', self.pages["elorian"])
        self.assertIn("(page unavailable when checked 23 Oct 2026)", self.pages["elorian"])
        self.assertIn("(page unavailable when checked 23 Oct 2026)", self.pages["labelbox"])
        self.assertNotIn("when checked", self.pages["mercor"])

    def test_risk_dates_read_as_months_like_the_app(self):
        mercor = self.pages["mercor"].split("<h3>Risks named in the evidence</h3>", 1)[1].split("</table>", 1)[0]
        self.assertIn('<td class="date asof">Jun 2026</td>', mercor)
        self.assertIn('<td class="date">Source date not stated</td>', mercor)
        self.assertIn("td.asof::before{content:'As of '", STYLE)

    def test_analytics_loader_follows_the_index_meta(self):
        self.assertEqual(analytics_endpoint((ROOT / "web/index.html").read_text()), "")
        self.assertEqual(analytics_endpoint('<meta name="sts-analytics" content="https://sciencetostartup.goatcounter.com/count">'), "https://sciencetostartup.goatcounter.com/count")
        for other in ("https://example.com/count", "javascript:alert(1)", "https://x.goatcounter.com/count?x=1"):
            self.assertEqual(analytics_endpoint(f'<meta name="sts-analytics" content="{other}">'), "", other)
        page = document("T", "D.", ORIGIN + "/", "", {}, analytics="https://sciencetostartup.goatcounter.com/count")
        self.assertIn('<script async src="https://gc.zgo.at/count.js" data-goatcounter="https://sciencetostartup.goatcounter.com/count"></script>\n</head>', page)
        self.assertNotIn("gc.zgo.at", document("T", "D.", ORIGIN + "/", "", {}))

    def test_scale_leads_with_reported_revenue_not_the_unverified_run_rate(self):
        table, rest = self.pages["scale_ai"].split("<h3>Other reported figures, not used for comparison</h3>", 1)
        table = table[table.index("<h2>Headline metrics</h2>"):]
        self.assertNotIn("$200M", table)
        self.assertRegex(re.search(r"<tbody><tr>(.*?)</tr>", table).group(1), r"^<td>Revenue<br>.*\$870M")
        self.assertIn('Annualized revenue run rate: <strong>$200M</strong> <span class="muted">· Unverified</span>', rest.split("</ul>", 1)[0])

    def test_head_tags_make_every_page_share_ready(self):
        for path in self.public_files()[:-1]:
            facts, name = PageFacts(path.read_text()), str(path.relative_to(self.dist))
            meta = facts.meta
            self.assertLess(len(facts.title), 60, name)
            self.assertLessEqual(len(meta["description"]), 155, name)
            self.assertTrue(meta["description"].endswith("."), name)
            self.assertEqual((meta["og:title"], meta["twitter:title"]), (facts.title, facts.title), name)
            self.assertEqual((meta["og:description"], meta["twitter:description"]), (meta["description"], meta["description"]), name)
            self.assertEqual((meta["og:image"], meta["og:image:width"], meta["og:image:height"], meta["og:image:alt"], meta["twitter:card"]), (OG_IMAGE, "1200", "630", "ScienceToStartup, the AI data field guide", "summary_large_image"), name)
            self.assertEqual([(i["rel"], i["href"]) for i in facts.icons], [("icon", "/assets/favicon.svg"), ("icon", "/assets/favicon-48.png"), ("apple-touch-icon", "/assets/apple-touch-icon.png")], name)
            self.assertEqual(facts.icons[0]["type"], "image/svg+xml", name)

    def test_company_descriptions_are_whole_sentences_without_the_summary(self):
        editorial = {e["company_id"]: e for e in json.loads((ROOT / "data/editorial.json").read_text())["entries"]}
        for cid, text in self.pages.items():
            description, name = PageFacts(text).meta["description"], self.companies[cid]["name"]
            self.assertTrue(description.startswith(name + " "), (cid, description))
            self.assertNotIn(editorial[cid]["summary"][:40], description, cid)
            first = re.split(r"(?<=[.!?]) ", " ".join(self.companies[cid]["description"].split()))[0].rstrip(".")
            self.assertIn(first[1:] + ". ", description + " ", cid)

    def test_header_main_and_footer_share_one_column(self):
        widths = re.findall(r"(?<=[{;])max-width:([^;}]+)", STYLE)
        self.assertEqual(widths, ["45rem"])
        self.assertIn("main,header,footer{max-width:45rem;", STYLE)

    def test_footer_names_publisher_disclosure_and_corrections(self):
        about = re.search(r'<article[^>]*\bid="about"[^>]*>.*?</article>', (ROOT / "web/index.html").read_text(), re.S).group(0)
        disclosure = re.sub(r"<[^>]+>", "", re.search(r"<strong>Disclosure\.</strong>\s*(.*?)</p>", about, re.S).group(1)).strip()
        publisher = re.search(r"ScienceToStartup is published by [^.]+\.", about).group(0)
        for path in self.public_files()[:-1]:
            footer = re.search(r"<footer>.*?</footer>", path.read_text(), re.S).group(0)
            plain = html.unescape(re.sub(r"<[^>]+>", "", footer))
            self.assertIn(publisher, plain, path)
            self.assertIn(disclosure, plain, path)
            self.assertIn(f'<a href="{ORIGIN}/#about">Corrections</a>', footer, path)

    def test_index_states_coverage_limits(self):
        text = (self.dist / "companies/index.html").read_text()
        self.assertIn("Coverage is a selected market study of 39 organizations, not an exhaustive census.", text)
        self.assertIn("Coverage is a selected market study, not an exhaustive census.", (ROOT / "web/app.js").read_text())
        missing = re.search(r"Other firms not yet profiled include ([^<]+)", text).group(1)
        self.assertEqual(missing, "Uber AI Solutions, TELUS Digital, CloudFactory, SuperAnnotate, Encord, Defined.ai, LXT and Welocalize.")
        self.assertIn("<p>Company names and logos belong to their owners and identify them here.</p>\n</footer>", text)

    def test_static_pages_are_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="static-pages-again-") as temp:
            again = Path(temp)
            build(self.data, again)
            for path in self.public_files():
                relative = path.relative_to(self.dist)
                self.assertEqual(path.read_bytes(), (again / relative).read_bytes(), str(relative))


if __name__ == "__main__":
    unittest.main()
