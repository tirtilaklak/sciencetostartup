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
        cls.app_html = (cls.dist / "explore/index.html").read_text()

    def test_summary_matches_its_full_preserved_archive_and_downloads(self):
        manifest = json.loads((self.dist / "manifest.json").read_text())
        summary = json.loads((self.dist / manifest["summary"]["href"].lstrip("/")).read_text())
        for element in ("research-data",):
            match = re.search(r'<script\b[^>]*\bid="' + element +
                              r'"[^>]*>(.*?)</script>', self.app_html, re.S)
            self.assertIsNotNone(match, element)
            self.assertEqual(json.loads(match.group(1)), summary["bootstrap"], element)
        archive = json.loads((self.dist / summary["archive"]["href"].lstrip("/")).read_text())
        self.assertEqual(archive["data"], json.loads((ROOT / "data/canonical.json").read_text()))
        self.assertEqual(summary["buildId"], manifest["build_id"])
        self.assertEqual(summary["datasetVersion"], "2.5.0")
        self.assertEqual(summary["exports"]["research"]["sha256"], hashlib.sha256((ROOT / "data/canonical.json").read_bytes()).hexdigest())
        self.assertNotIn('id="research-data"', self.html, "The homepage must not load research")
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
        self.assertEqual(len(locs), len(set(locs)), "Every canonical URL appears once")
        research_locs = [loc for loc in locs if "/research/" in loc or loc.endswith("/review/")]
        self.assertGreaterEqual(len(research_locs), 4, "Research hub, report framework, data and review routes are discoverable")
        company_locs = [loc for loc in locs if "/company/" in loc]
        self.assertGreaterEqual(len(company_locs), len(companies))
        self.assertEqual(len(locs), 4 + len(company_locs) + len(research_locs), "Historical profiles, new reviewed profiles and research routes have distinct canonical URLs")
        for company in companies:
            self.assertIn(ORIGIN + "/company/" + company["id"] + "/", locs)
            self.assertTrue((self.dist / "company" / company["id"] / "index.html").is_file(), company["id"])
        from artifact_verification import verify_undated_research_metadata
        from research_graph import load_graph
        graph = load_graph(ROOT)
        for entry in root:
            loc = entry.findtext(namespace + "loc")
            modified = entry.findtext(namespace + "lastmod")
            if modified is None:
                verify_undated_research_metadata(self.dist, loc, graph)
            else:
                self.assertRegex(modified, r'^\d{4}-\d{2}-\d{2}$', loc)
        manifest = json.loads((self.dist / "manifest.json").read_text())["sha256"]
        robots_raw = (self.dist / "robots.txt").read_bytes()
        self.assertEqual(robots_raw, (ROOT / "web/robots.txt").read_bytes())
        for name in ("robots.txt", "sitemap.xml", "favicon.ico", "404.html"):
            self.assertEqual(hashlib.sha256((self.dist / name).read_bytes()).hexdigest(), manifest[name])
        self.assertEqual((self.dist / "favicon.ico").read_bytes(), (ROOT / "web/favicon.ico").read_bytes())


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
