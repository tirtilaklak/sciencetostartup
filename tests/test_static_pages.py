"""Crawlable static company pages and the generated sitemap, built into a scratch directory."""
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import build

ORIGIN = "https://sciencetostartup.com"
NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
EMAIL = re.compile(r"@[A-Za-z0-9-]+\.[A-Za-z]{2,}")
PAGE_LIMIT = 120_000


class PageFacts(HTMLParser):
    """Canonical links, h1 headings, title and script tags of a static page."""
    def __init__(self, text):
        super().__init__()
        self.canonicals, self.headings, self.scripts, self.title = [], [], [], ""
        self._capture, self._buffer = None, []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical": self.canonicals.append(attrs.get("href"))
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
        for url in urls: self.assertEqual(url.find(NAMESPACE + "lastmod").text, self.data["meta"]["as_of"], url.find(NAMESPACE + "loc").text)

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

    def test_static_pages_are_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="static-pages-again-") as temp:
            again = Path(temp)
            build(self.data, again)
            for path in self.public_files():
                relative = path.relative_to(self.dist)
                self.assertEqual(path.read_bytes(), (again / relative).read_bytes(), str(relative))


if __name__ == "__main__":
    unittest.main()
