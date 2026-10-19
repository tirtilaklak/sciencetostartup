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
        self.assertEqual([node.text for node in root.iter(namespace + "loc")],
                         [ORIGIN + "/"], "Hash views share one public document")
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        for name in ("robots.txt", "sitemap.xml"):
            raw = (self.dist / name).read_bytes()
            self.assertEqual(raw, (ROOT / "web" / name).read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest[name])


if __name__ == "__main__":
    unittest.main()
