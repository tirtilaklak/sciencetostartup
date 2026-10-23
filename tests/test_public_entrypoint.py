"""Public crawler exports and lossless embedded data in the built dashboard."""
import hashlib
import json
import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://sciencetostartup.com"


class HeadLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.canonicals = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonicals.append(attrs.get("href"))


class PublicEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dist = ROOT / "dist"
        cls.html = (cls.dist / "index.html").read_text()

    def test_embedded_data_matches_preserved_downloads(self):
        for element, source in (("research-data", "data/canonical.json"),):
            match = re.search(r'<script\b[^>]*\bid="' + element +
                              r'"[^>]*>(.*?)</script>', self.html, re.S)
            self.assertIsNotNone(match, element)
            self.assertEqual(json.loads(match.group(1)),
                             json.loads((ROOT / source).read_text()), element)
        self.assertNotIn('id="outreach-data"', self.html,
                         "The alumni directory must not ship in the public page")
        self.assertNotIn("mailto:", self.html.split("<footer>")[0].split('id="method-view"')[0],
                         "No personal mailto links outside the About panel")
        self.assertEqual((self.dist / "research.json").read_bytes(),
                         (ROOT / "data/canonical.json").read_bytes())
        self.assertLess(len(self.html.encode("utf-8")), 4 * 1024 * 1024,
                        "Entrypoint exceeds the observed 4 MiB web-fetch limit")

    def test_real_crawler_files_identify_the_canonical_document(self):
        self.assertEqual(HeadLinks(self.html).canonicals, [ORIGIN + "/"])
        robots = (self.dist / "robots.txt").read_text()
        directives = [line.strip() for line in robots.splitlines() if line.strip()]
        self.assertEqual(directives,
                         ["User-agent: *", "Allow: /", "Sitemap: " + ORIGIN + "/sitemap.xml"])
        root = ET.parse(self.dist / "sitemap.xml").getroot()
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        self.assertEqual(root.tag, namespace + "urlset")
        locs = [node.text for node in root.iter(namespace + "loc")]
        companies = json.loads((ROOT / "data/canonical.json").read_text())["companies"]
        self.assertEqual(locs[0], ORIGIN + "/", "The app document stays first")
        for page in ("/companies/", "/work/", "/method/"): self.assertIn(ORIGIN + page, locs)
        self.assertEqual(len(locs), 4 + len(companies), "One static page per company plus the company list, paid work and method pages")
        for company in companies:
            self.assertIn(ORIGIN + "/company/" + company["id"] + "/", locs)
            self.assertTrue((self.dist / "company" / company["id"] / "index.html").is_file(), company["id"])
        self.assertEqual(len(list(root.iter(namespace + "lastmod"))), len(locs), "Every URL carries lastmod")
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        robots_raw = (self.dist / "robots.txt").read_bytes()
        self.assertEqual(robots_raw, (ROOT / "web/robots.txt").read_bytes())
        for name in ("robots.txt", "sitemap.xml", "favicon.ico", "404.html"):
            self.assertEqual(hashlib.sha256((self.dist / name).read_bytes()).hexdigest(), manifest[name])
        self.assertEqual((self.dist / "favicon.ico").read_bytes(), (ROOT / "web/favicon.ico").read_bytes())


if __name__ == "__main__":
    unittest.main()
