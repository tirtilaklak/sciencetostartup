"""Public crawler exports, lossless embedded data and the deployed-dist release check."""
import contextlib
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_public_snapshot import verify
from observatory import build

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
        self.assertIn(ORIGIN + "/companies/", locs)
        self.assertEqual(len(locs), 2 + len(companies), "One static page per company")
        for company in companies:
            self.assertIn(ORIGIN + "/company/" + company["id"] + "/", locs)
            self.assertTrue((self.dist / "company" / company["id"] / "index.html").is_file(), company["id"])
        self.assertEqual(len(list(root.iter(namespace + "lastmod"))), len(locs), "Every URL carries lastmod")
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        robots_raw = (self.dist / "robots.txt").read_bytes()
        self.assertEqual(robots_raw, (ROOT / "web/robots.txt").read_bytes())
        for name in ("robots.txt", "sitemap.xml"):
            self.assertEqual(hashlib.sha256((self.dist / name).read_bytes()).hexdigest(), manifest[name])


class DeployedDistTests(unittest.TestCase):
    """verify() must read the deployed files, not only the rebuilt manifest."""
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="verify-dist-")
        cls.build = Path(cls.temp.name) / "build"
        build(json.loads((ROOT / "data/canonical.json").read_text()), cls.build)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def deployed(self):
        dist = Path(self.temp.name) / self._testMethodName
        shutil.copytree(self.build, dist)
        return dist

    def rejected(self, dist):
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            verify(self.build, dist)
        return str(caught.exception)

    def test_faithful_copy_passes(self):
        with contextlib.redirect_stdout(io.StringIO()) as output: verify(self.build, self.deployed())
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["deployed_files"], result["payloads"] + 1)

    def test_tampered_entrypoint_fails(self):
        dist = self.deployed()
        page = dist / "index.html"
        page.write_text(page.read_text().replace("</body>", '<script src="https://example.com/x.js"></script></body>'))
        self.assertEqual(self.rejected(dist), "Deployed file differs from the manifest: index.html")

    def test_extra_file_fails(self):
        dist = self.deployed()
        (dist / "company/mercor/stray.html").write_text("stray")
        self.assertIn("Extra: company/mercor/stray.html", self.rejected(dist))

    def test_missing_file_fails(self):
        dist = self.deployed()
        (dist / "company/mercor/index.html").unlink()
        self.assertIn("Missing: company/mercor/index.html", self.rejected(dist))


if __name__ == "__main__":
    unittest.main()
