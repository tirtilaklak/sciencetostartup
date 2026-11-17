"""Current directory additions preserve entity scope and frozen research bytes."""
import copy
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import current_companies as cc
import static_pages as sp


def example():
    return {"schema_version": "1.0.0", "reviewed_on": "2026-11-16", "entries": [{
        "entity_id": "org.example", "name": "Example", "website": "https://example.org/", "group": "Managed AI & data services",
        "wikipedia": {"title": "Example", "article_url": "https://en.wikipedia.org/wiki/Example",
            "revision_url": "https://en.wikipedia.org/w/index.php?title=Example&oldid=123",
            "history_url": "https://en.wikipedia.org/w/index.php?title=Example&action=history",
            "page_id": 1, "revision_id": 123, "revision_timestamp": "2026-11-15T12:00:00Z", "observed_on": "2026-11-16",
            "response_sha256": "a" * 64, "content_kind": "mediawiki_revision_wikitext",
            "description": "Example is a company providing data services.", "license_url": cc.LICENSE, "change_note": cc.CHANGE_NOTE},
        "offerings": [{"label": "Data annotation", "source_indexes": [0]}],
        "sources": [{"url": "https://example.org/services", "title": "Official services", "published_on": None,
            "observed_on": "2026-11-16", "response_sha256": "b" * 64, "locator": "Data annotation section", "content_kind": "raw_http_body"},
            {"url": "https://example.org/about", "title": "Official identity", "published_on": None,
            "observed_on": "2026-11-16", "response_sha256": "c" * 64, "locator": "Company name and website", "content_kind": "raw_http_body"}]
    }]}


def context():
    return {"graph": {"entities": [{"id": "org.example", "name": "Example", "kind": "supplier", "status": "approved", "identifiers": {"website": "https://www.example.org/"}}],
        "assertions": [{"id": "claim.example", "subject_id": "org.example", "status": "approved"}]}}


def current_identity(scope="current_only"):
    return {"scope": scope, "name": "Example", "aliases": ["Example Incorporated"],
            "website": "https://example.org/", "source_indexes": [1]}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.links, self.cards, self.current, self.text, self.meta, self.scripts = [], [], [], [], {}, []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a": self.links.append(attrs.get("href"))
        if "directory-company" in attrs.get("class", "").split(): self.cards.append(attrs)
        if "data-current-company" in attrs: self.current.append(attrs["data-current-company"])
        if tag == "meta": self.meta[attrs.get("name") or attrs.get("property")] = attrs.get("content")
        if tag == "script": self.scripts.append(attrs)

    def handle_data(self, text):
        self.text.append(text)


class CurrentCompanyValidationTests(unittest.TestCase):
    def reject(self, change, message):
        value = example()
        change(value["entries"][0])
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, message):
            cc.validate_current_companies(value, {"companies": []}, context())

    def test_validation_preserves_input_objects(self):
        value, data, graph = example(), {"companies": [{"id": "frozen"}]}, context()
        originals = copy.deepcopy((value, data, graph))
        self.assertIs(cc.validate_current_companies(value, data, graph), value)
        self.assertEqual((value, data, graph), originals)

    def test_entity_cannot_replace_core_or_unapproved_research(self):
        value = example()
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "canonical companies"):
            cc.validate_current_companies(value, {"companies": [{"id": "org.example"}]}, context())
        for change in (lambda e: e.update(entity_id="org.missing"), lambda e: e.update(name="Different Company"), lambda e: e.update(website="https://unrelated.org/")):
            self.reject(change, "existing approved|reviewed entity")
        for field, value in (("status", "candidate"), ("kind", "paper"), ("legacy_id", "example")):
            graph = context()
            graph["graph"]["entities"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "existing approved"):
                cc.validate_current_companies(example(), {"companies": []}, graph)
        graph = context()
        graph["graph"]["assertions"][0]["status"] = "candidate"
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "existing approved"):
            cc.validate_current_companies(example(), {"companies": []}, graph)

    def test_wikipedia_provenance_requires_matching_pinned_article(self):
        changes = [
            ("title", "Other", "Wikipedia title"),
            ("article_url", "https://en.wikipedia.org/wiki/Other", "article URL"),
            ("article_url", "https://en.wikipedia.org.evil.example/wiki/Example", "en.wikipedia.org"),
            ("revision_url", "https://en.wikipedia.org/wiki/Example", "must pin"),
            ("revision_url", "https://en.wikipedia.org/w/index.php?title=Example&oldid=124", "must pin"),
            ("revision_url", "https://en.wikipedia.org/w/index.php?title=Other&oldid=123", "must pin"),
            ("history_url", "https://en.wikipedia.org/w/index.php?title=Other&action=history", "history URL"),
            ("page_id", True, "positive integer"),
            ("response_sha256", "a" * 63, "SHA-256"),
            ("content_kind", "search_snippet", "revision content"),
            ("license_url", "https://creativecommons.org/licenses/by/4.0/", "license"),
            ("change_note", "Excerpt unchanged.", "modification attribution"),
            ("description", "An incomplete sentence", "complete Wikipedia sentences"),
            ("description", "<script>bad</script>.", "plain text"),
        ]
        for field, value, error in changes:
            with self.subTest(field=field, value=value):
                self.reject(lambda e: e["wikipedia"].update({field: value}), error)

    def test_dates_and_sources_cannot_fabricate_review_scope(self):
        self.reject(lambda e: e["wikipedia"].update(observed_on="2026-11-17"), "after review")
        self.reject(lambda e: e["wikipedia"].update(revision_timestamp="2026-11-17T12:00:00Z"), "after observation")
        self.reject(lambda e: e["wikipedia"].update(revision_timestamp="2026-02-30T12:00:00Z"), "invalid Wikipedia")
        self.reject(lambda e: e["sources"][0].update(published_on="2026-11-17"), "after observation")
        self.reject(lambda e: e["sources"][0].update(response_sha256="madeup"), "SHA-256")
        for indexes in ([], [2], [True], [0, 0]):
            self.reject(lambda e: e["offerings"][0].update(source_indexes=indexes), "source index")
        self.reject(lambda e: e.update(sources=[]), "sources must be non-empty")

    def test_duplicates_fail_before_directory_or_search_can_double_count(self):
        value = example()
        value["entries"].append(copy.deepcopy(value["entries"][0]))
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "duplicate entity"):
            cc.validate_current_companies(value, {"companies": []}, context())

    def test_parent_article_requires_explicit_narrow_binding(self):
        self.reject(lambda e: e["wikipedia"].update(article_scope="parent_company"), "DataForce")
        value, graph = example(), context()
        e, entity = value["entries"][0], graph["graph"]["entities"][0]
        e.update(entity_id="org.dataforce", name="TransPerfect / DataForce", parent_company={"name": "TransPerfect", "source_indexes": [0]})
        entity.update(id="org.dataforce", name="DataForce by TransPerfect")
        graph["graph"]["assertions"][0]["subject_id"] = "org.dataforce"
        e["wikipedia"].update(article_scope="parent_company", title="TransPerfect", article_url="https://en.wikipedia.org/wiki/TransPerfect", revision_url="https://en.wikipedia.org/w/index.php?title=TransPerfect&oldid=123", history_url="https://en.wikipedia.org/w/index.php?title=TransPerfect&action=history")
        cc.validate_current_companies(value, {"companies": []}, graph)
        rendered = Page(cc.current_company_html(e, value["reviewed_on"]))
        self.assertIn("Parent company: TransPerfect", " ".join(rendered.text))
        self.assertIn("DataForce by TransPerfect", rendered.text)


class CurrentCompanyRenderingTests(unittest.TestCase):
    def test_directory_cards_and_provenance_are_available_without_javascript(self):
        registry = example()
        research = SimpleNamespace(as_of="2026-10-28", data={"dataset_version": "2.5.0"})
        text = sp.render_index(research, [], {}, {}, 0, registry["reviewed_on"], current_entries=registry["entries"], current_reviewed_on=registry["reviewed_on"])
        page, entry = Page(text), registry["entries"][0]
        self.assertEqual([card["data-company"] for card in page.cards], ["org.example"])
        self.assertIn("Data annotation", page.cards[0]["data-search"])
        self.assertIn("1 profiles", " ".join(page.text))
        self.assertIn("0 original profiles + 1 current additions", " ".join(page.text))
        self.assertIn(sp.ORIGIN + cc.company_path(entry), page.links)
        for url in [entry["wikipedia"][key] for key in ("article_url", "revision_url", "history_url", "license_url")] + [source["url"] for source in entry["sources"]]:
            self.assertIn(url, page.links)
        self.assertIn(entry["wikipedia"]["description"], page.text)
        self.assertIn(cc.CHANGE_NOTE, " ".join(page.text))
        self.assertIn("16 Nov 2026", " ".join(page.text))
        self.assertIn('<details class="company-current-facts">', text)
        node = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S).group(1))
        self.assertEqual(node["mainEntity"]["numberOfItems"], 1)
        self.assertEqual(node["mainEntity"]["itemListElement"][0]["url"], sp.ORIGIN + cc.company_path(entry))

    def test_profile_updates_current_metadata_and_preserves_archived_bytes(self):
        registry, research = example(), SimpleNamespace(as_of="2026-10-28", data={"dataset_version": "2.5.0"})
        entry = registry["entries"][0]
        canonical = sp.ORIGIN + cc.company_path(entry)
        historic = '<details id="approved-findings"><summary>Findings</summary><p>Original approved finding and qualification.</p></details>'
        original = sp.document(research, "Example", "Original description.", canonical, '<article class="company-dossier"><header></header><div class="company-record">' + historic + '</div></article>', sp.page_node("WebPage", "Example", "Original description.", canonical, "2026-10-28", []))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / cc.company_path(entry).strip('/') / "index.html"
            target.parent.mkdir(parents=True)
            target.write_text(original)
            archive = root / 'research/editions/2026-11-12/index.html'
            archive.parent.mkdir(parents=True)
            archive.write_bytes(original.encode())
            frozen = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(cc.write_current_company_supplements(root, registry), [{"path": cc.company_path(entry), "lastmod": "2026-11-16"}])
            text = target.read_text()
            page = Page(text)
            self.assertEqual(page.current, [entry["entity_id"]])
            self.assertIn(historic, text)
            self.assertIn(entry["wikipedia"]["description"], page.text)
            for key in ("description", "og:description", "twitter:description"):
                self.assertEqual(page.meta[key], entry["wikipedia"]["description"])
            self.assertIn('"dateModified":"2026-11-16"', text)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), frozen)
            self.assertEqual(page.scripts, [{"type": "application/ld+json"}, {"src": "/native-details.js", "defer": None}])
            with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "already written"):
                cc.write_current_company_supplements(root, registry)

    def test_search_uses_one_stable_profile_result_and_preserves_non_wikipedia_copy(self):
        registry = example()
        existing = [{"url": "/research/", "title": "Research", "summary": "Frozen"}, {"url": "/company/org.example/", "title": "Example", "summary": "Old"}]
        original = copy.deepcopy(existing)
        result = cc.search_entries(existing, registry["entries"])
        self.assertEqual(existing, original)
        self.assertEqual(len(result), len(existing))
        self.assertEqual(sum(row["url"] == "/company/org.example/" for row in result), 1)
        self.assertEqual(result[1]["summary"], existing[1]["summary"])
        self.assertEqual(result[1]["kind"], "company")
        self.assertNotIn(registry["entries"][0]["wikipedia"]["description"], json.dumps(result))
        self.assertIn("Data annotation", result[1]["keywords"])
        self.assertEqual(result[0], existing[0])
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "existing research search result"):
            cc.search_entries(existing[:1], registry["entries"])


class CurrentOnlyCompanyTests(unittest.TestCase):
    def test_source_bound_current_identity_does_not_add_research_entities(self):
        registry, graph = example(), {"graph": {"entities": [], "assertions": []}}
        registry["entries"][0]["current_identity"] = current_identity()
        originals = copy.deepcopy((registry, graph))
        cc.validate_current_companies(registry, {"companies": []}, graph)
        self.assertEqual((registry, graph), originals)

    def test_current_identity_cannot_bypass_approved_entities_or_known_domains(self):
        registry = example()
        registry["entries"][0]["current_identity"] = current_identity("website_supplement")
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "cannot override"):
            cc.validate_current_companies(registry, {"companies": []}, context())
        graph = context()
        graph["graph"]["entities"][0].update(status="candidate", identifiers={})
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "existing approved"):
            cc.validate_current_companies(registry, {"companies": []}, graph)

    def test_current_identity_rejects_unsupported_scope_unbound_source_and_duplicates(self):
        registry, graph = example(), {"graph": {"entities": [], "assertions": []}}
        entry = registry["entries"][0]
        entry["current_identity"] = current_identity()
        entry["current_identity"]["scope"] = "approved_research"
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "explicit current identity scope"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        entry["current_identity"] = current_identity()
        entry["current_identity"]["source_indexes"] = [2]
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "source index"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        entry["current_identity"] = current_identity()
        entry["sources"][1]["url"] = "https://unrelated.org/about"
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "official identity source"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        entry["sources"][1]["url"] = "https://example.org/about"
        graph["graph"]["entities"] = [{"id": "org.other", "name": "Example", "kind": "supplier"}]
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "duplicates an existing organization"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        entry["name"] = entry["current_identity"]["name"] = "Example / New Brand"
        entry["current_identity"]["aliases"] = []
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "duplicates an existing organization"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        graph["graph"]["entities"] = []
        entry["name"] = entry["current_identity"]["name"] = "Example"
        entry["current_identity"]["aliases"] = ["New Brand"]
        duplicate = copy.deepcopy(entry)
        duplicate["entity_id"] = "org.duplicate"
        duplicate["wikipedia"].update(page_id=2)
        duplicate["name"] = duplicate["current_identity"]["name"] = "New Brand"
        duplicate["current_identity"]["aliases"] = ["Example"]
        registry["entries"].append(duplicate)
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "duplicates an existing organization"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        entry["current_identity"].update(name="Primary Brand", aliases=["Example"])
        duplicate["name"] = "Primary Brand"
        duplicate["current_identity"].update(name="Primary Brand", aliases=[])
        duplicate["wikipedia"].update(title="Primary Brand", article_url="https://en.wikipedia.org/wiki/Primary_Brand",
            revision_url="https://en.wikipedia.org/w/index.php?title=Primary_Brand&oldid=123",
            history_url="https://en.wikipedia.org/w/index.php?title=Primary_Brand&action=history")
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "duplicates an existing organization"):
            cc.validate_current_companies(registry, {"companies": []}, graph)

    def test_website_supplement_fills_only_the_missing_approved_organization_binding(self):
        registry, graph = example(), context()
        graph["graph"]["entities"][0]["identifiers"] = {}
        registry["entries"][0]["current_identity"] = current_identity("website_supplement")
        registry["entries"][0]["current_identity"]["aliases"] = []
        cc.validate_current_companies(registry, {"companies": []}, graph)
        registry["entries"][0]["current_identity"]["aliases"] = ["Unrelated"]
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "unrelated aliases"):
            cc.validate_current_companies(registry, {"companies": []}, graph)
        registry["entries"][0]["current_identity"]["aliases"] = []
        registry["entries"][0]["current_identity"]["name"] = "Unrelated"
        with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "supplement must match"):
            cc.validate_current_companies(registry, {"companies": []}, graph)

    def test_current_only_search_has_one_native_result_and_no_unattributed_wikipedia_copy(self):
        registry = example()
        entry = registry["entries"][0]
        entry["current_identity"] = current_identity()
        existing = [{"url": "/research/", "title": "Research", "summary": "Frozen"}]
        result = cc.search_entries(existing, registry["entries"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[-1]["url"], cc.company_path(entry))
        self.assertEqual(result[-1]["summary"], "Data annotation")
        self.assertNotIn(entry["wikipedia"]["description"], json.dumps(result))
        repeated = cc.search_entries(result, registry["entries"])
        self.assertEqual(sum(row["url"] == cc.company_path(entry) for row in repeated), 1)
        self.assertEqual(repeated[-1]["summary"], "Data annotation")

    def test_current_only_profile_is_attributed_and_cannot_overwrite_an_existing_page(self):
        registry = example()
        entry = registry["entries"][0]
        entry["current_identity"] = current_identity()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cc.write_current_company_supplements(root, registry)
            target = root / cc.company_path(entry).strip('/') / 'index.html'
            text = target.read_text()
            page = Page(text)
            self.assertEqual(page.current, [entry["entity_id"]])
            self.assertIn('Current company profile', text)
            self.assertIn(entry["wikipedia"]["description"], page.text)
            self.assertIn(entry["wikipedia"]["license_url"], page.links)
            self.assertIn('"@type":"ProfilePage"', text)
            self.assertNotIn('Research compiled', text)
            with self.assertRaisesRegex(cc.CurrentCompaniesValidationError, "overwrite an existing page"):
                cc.write_current_company_supplements(root, registry)


class ActualCurrentCompanyRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "data/current-companies.json"
        if not path.exists():
            raise unittest.SkipTest("No optional current company registry is selected")
        from research_report import build_context
        cls.context = build_context(ROOT)
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.registry = json.loads(path.read_text())

    def test_actual_registry_is_valid_and_preserves_frozen_inputs(self):
        before = copy.deepcopy((self.registry, self.context["graph"], self.data))
        cc.validate_current_companies(self.registry, self.data, self.context)
        self.assertEqual((self.registry, self.context["graph"], self.data), before)
        self.assertEqual(len(self.data["companies"]), 39)
        self.assertEqual(self.data["dataset_version"], "2.5.0")

    def test_actual_current_cards_keep_every_source_license_and_exact_sentence(self):
        research = sp.Research(self.data, {})
        editorial = {e["company_id"]: e for e in json.loads((ROOT / 'data/editorial.json').read_text())["entries"]}
        text = sp.render_index(research, self.data["companies"], editorial, sp.read_js_object(ROOT / "web/editorial.js", "GROUP_LABELS"), 0, self.registry["reviewed_on"], current_entries=self.registry["entries"], current_reviewed_on=self.registry["reviewed_on"])
        page = Page(text)
        self.assertEqual(len(page.cards), 39 + len(self.registry["entries"]))
        self.assertEqual(set(page.current), {e["entity_id"] for e in self.registry["entries"]})
        for entry in self.registry["entries"]:
            self.assertIn(entry["wikipedia"]["description"], page.text)
            for source in entry["sources"]:
                self.assertIn(source["url"], page.links)
            for key in ("article_url", "revision_url", "history_url", "license_url"):
                self.assertIn(entry["wikipedia"][key], page.links)


if __name__ == "__main__":
    unittest.main()
