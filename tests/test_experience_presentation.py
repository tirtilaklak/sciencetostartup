"""Presentation boundaries: current discovery, historical identity and source dates."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import home
import static_pages as sp


def structured_nodes(text):
    nodes = []
    for raw in re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', text, re.S):
        value = json.loads(raw)
        nodes.extend(value if isinstance(value, list) else value.get("@graph", [value]))
    return nodes


class Downloads(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.urls = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "download" in attrs:
            self.urls.append(attrs.get("href"))


class ExperiencePresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads((ROOT / "data/canonical.json").read_text())
        cls.current = json.loads((ROOT / "data/current-companies.json").read_text())

    def test_home_current_count_does_not_change_historical_dataset_identity(self):
        template = (ROOT / "web/landing.html").read_text().replace("{{COMPANY_COUNT}}", str(len(self.canonical["companies"]))).replace("{{DATASET_VERSION}}", self.canonical["dataset_version"])
        sidecars = {"EDITORIAL": {"entries": []}, "WORK_ROUTES": {"routes": []}}
        summary = {"schemaVersion": "test", "buildId": "test", "editorialReleaseId": "test", "datasetVersion": "2.5.0", "homeSearch": {"href": "/test-index.json"}}
        html = home.render_home(template, self.canonical, sidecars, {}, summary, current_companies=self.current)
        count = len(self.canonical["companies"]) + len(self.current["entries"])
        self.assertIn(f'data-count="companies">{count}</strong>', html)
        website = next(node for node in structured_nodes(html) if node.get("@type") == "WebSite")
        dataset = next(node for node in structured_nodes(html) if node.get("@type") == "Dataset")
        self.assertIn(str(count) + " AI data companies", website["description"])
        self.assertIn("39 AI data companies", dataset["description"])
        self.assertEqual(dataset["version"], "2.5.0")
        self.assertEqual(dataset["@id"], sp.DATASET_ID)
        self.assertEqual(dataset["license"], sp.DATA_LICENSE)
        self.assertNotIn("work-routes.json", json.dumps(dataset["distribution"]))
        self.assertNotIn("{{DIRECTORY_COUNT}}", html)
        legacy = home.render_home(template, self.canonical, sidecars, {}, summary)
        self.assertIn('data-count="companies">39</strong>', legacy)

    def test_404_current_count_is_independent_of_historical_research(self):
        research = sp.Research(self.canonical)
        count = len(self.canonical["companies"]) + len(self.current["entries"])
        self.assertIn(f"profiles of all {count} companies", sp.render_not_found(research, count))
        self.assertIn("profiles of all 39 companies", sp.render_not_found(research))

    def test_work_inventory_explains_primary_listing_and_full_record_counts(self):
        work = json.loads((ROOT / "data/work-routes.json").read_text())
        names = {company["id"]: company["name"] for company in self.canonical["companies"]}
        html = sp.render_work(sp.Research(self.canonical), work["routes"], names, "2026-11-18")
        scope = json.loads((ROOT / "data/editorial-release.json").read_text())["counts"]
        self.assertIn(f'{scope["named_listings"]} named listings', html)
        self.assertIn(f'{scope["networks_programs"]} networks and programs', html)
        self.assertIn(f'{scope["providers"]} companies', html)
        self.assertIn(f'{scope["records"]} records, including career pages and past listings', html)
        self.assertIn('data-work-group="boards"', html)
        self.assertIn('data-work-group="closed"', html)
        self.assertNotIn(f'{scope["work_routes"]} current', html)

    def test_mutable_supporting_downloads_keep_links_without_frozen_membership(self):
        core = ["research.json", "observatory.sqlite", "companies.csv", "claims.csv", "classifications.csv"]
        supporting = ["work-routes.json", "source-updates.json", "profile-content.json", "editorial.json", "business-health.json", "unrelated.csv"]
        html = sp.render_method(sp.Research(self.canonical), {name: "1 KiB" for name in core + supporting}, "2026-11-18")
        dataset = next(node for node in structured_nodes(html) if node.get("@type") == "Dataset")
        self.assertEqual(dataset["version"], "2.5.0")
        self.assertEqual(dataset["dateModified"], "2026-10-15")
        self.assertEqual(dataset["license"], sp.DATA_LICENSE)
        self.assertEqual({item["contentUrl"] for item in dataset["distribution"]}, {sp.ORIGIN + "/" + name for name in core})
        self.assertTrue({sp.ORIGIN + "/" + name for name in core + supporting} <= set(Downloads(html).urls))
        self.assertIn("Current supporting data", html)
        self.assertIn("non-superseded claims", dataset["description"])
        for filename in ("web/landing.html", "web/index.html"):
            dataset = next(node for node in structured_nodes((ROOT / filename).read_text()) if node.get("@type") == "Dataset")
            self.assertNotIn("work-routes.json", json.dumps(dataset["distribution"]))
            self.assertIn("Historical public-source research", dataset["description"])

    def test_footer_never_pairs_graph_cutoff_with_canonical_compilation(self):
        canonical = sp.site_footer(sp.Research(self.canonical))
        self.assertIn("Historical company dataset v2.5.0 · Snapshot 15 Oct 2026", canonical)
        context = SimpleNamespace(as_of="2026-11-12", data={"dataset_version": "2.5.0"})
        self.assertNotIn("12 Nov", sp.site_footer(context))
        context.research_release_context = {"release_id": "research-fixture.1", "evidence_as_of": "2026-11-12T17:50:15.040816Z"}
        footer = sp.site_footer(context)
        self.assertIn("Research release research-fixture.1 · Evidence as of 2026-11-12T17:50:15.040816Z", footer)
        self.assertIn("Historical company dataset v2.5.0", footer)
        self.assertNotIn("Research compiled", footer)
        self.assertNotIn("Snapshot", footer)
        empty = sp.site_footer(SimpleNamespace(as_of="2026-11-18", data={}))
        self.assertNotIn('class="site-footer-meta"', empty)
        self.assertNotIn("2026-11-18", empty)

    def test_directory_heading_preserves_full_names_and_recorded_aliases(self):
        company = {**self.canonical["companies"][0], "name": "A deliberately long complete company name", "aliases": ["Recorded contributor brand"]}
        html = sp.render_index(sp.Research(self.canonical), [company], {}, {}, 0, "2026-11-18")
        self.assertIn('<h3><a href="' + sp.ORIGIN + '/company/' + company["id"] + '/">' + company["name"], html)
        self.assertIn("Recorded contributor brand", html)
        self.assertIn('data-search-name="' + company["name"] + '"', html)
        self.assertNotIn(" →", html)

    def test_canonical_bytes_still_match_the_retained_identity(self):
        self.assertEqual(hashlib.sha256((ROOT / "data/canonical.json").read_bytes()).hexdigest(), "948e69229fa24a4a1e6b5eed6d9c11570568a3c05bf9512e442d19611061a061")


if __name__ == "__main__":
    unittest.main()
