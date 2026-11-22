"""Native dossiers stay compact while retaining the source-backed records."""
import json
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import static_pages as sp


class ProfileContent(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.stack = []
        self.visible = []
        self.records = []
        self.ids = []
        self.feed(text)

    def shown(self):
        for index, (tag, attrs) in enumerate(self.stack):
            if tag == "details" and "open" not in attrs:
                if index + 1 >= len(self.stack) or self.stack[index + 1][0] != "summary":
                    return False
        return True

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs: self.ids.append(attrs["id"])
        if any(key in attrs for key in ("data-metric", "data-work-route", "data-risk", "data-event")):
            self.records.append((attrs, self.shown()))
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.stack.append((tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, text):
        if self.shown() and any(tag == "article" and attrs.get("class") == "company-dossier" for tag, attrs in self.stack):
            self.visible.append(text)


class CompanyProfileLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read = lambda name: json.loads((ROOT / "data" / name).read_text())
        cls.data = read("canonical.json")
        cls.work = read("work-routes.json")
        profiles = read("profile-content.json")
        profiles["entries"] = [entry for entry in profiles["entries"] if entry["company_id"] != "afterquery"] + [read("profile-afterquery.json")]
        cls.temp = tempfile.TemporaryDirectory(prefix="company-dossier-")
        destination = Path(cls.temp.name)
        sp.write_static_pages(cls.data, destination, cls.work, profiles, read("editorial.json"), read("company-events.json"), read("link-health.json"), business_health=read("business-health.json"))
        cls.pages = {company["id"]: (destination / "company" / company["id"] / "index.html").read_text() for company in cls.data["companies"]}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_default_dossier_is_short_and_records_are_native_disclosures(self):
        for cid, text in self.pages.items():
            with self.subTest(company=cid):
                content = ProfileContent(text)
                self.assertLessEqual(len(" ".join(content.visible).split()), 220)
                self.assertTrue(content.records)
                self.assertTrue(all(not shown for _, shown in content.records), "Detailed records should open on demand")
                self.assertNotIn("Open the full profile", text)
                self.assertNotIn("The full profile shows", text)
                self.assertEqual(len(content.ids), len(set(content.ids)), "Anchors must remain unique")
                for anchor in ("facts", "figures", "work", "full-profile"):
                    self.assertIn(anchor, content.ids)

    def test_every_work_record_and_critical_event_remains_available(self):
        for cid, text in self.pages.items():
            content = ProfileContent(text)
            routes = [attrs for attrs, _ in content.records if "data-work-route" in attrs]
            actual = [attrs["data-work-route"] for attrs in routes]
            expected = [route["id"] for route in self.work["routes"] if route["company_id"] == cid]
            self.assertCountEqual(actual, expected, cid)
            self.assertTrue(all(attrs.get("id") == attrs["data-work-route"] and attrs.get("tabindex") == "-1" for attrs in routes), cid)
            self.assertIn('<summary id="sources" data-native-sources>', text, cid)
            events = [event for event in sp.company_events(json.loads((ROOT / "data/company-events.json").read_text()), cid) if event.get("kind") in ("lawsuit", "data_incident")]
            if events:
                self.assertIn('class="company-notice"', text, cid)
                self.assertIn('href="#risks"', text, cid)

    def test_reported_facts_keep_their_financial_scope_and_unknown_states(self):
        header = lambda cid: self.pages[cid].split('<article class="company-dossier">', 1)[1].split('<div class="company-record">', 1)[0]
        mercor = header("mercor")
        for value in ("Annualized revenue pace", "Whole company", "Gross/net not disclosed", "Investor-reported"):
            self.assertIn(value, mercor)
        self.assertEqual(mercor.count("Annualized revenue pace"), 1)
        self.assertIn("Jun 2026", mercor)
        self.assertNotIn("2026-06", mercor)
        afterquery = header("afterquery")
        self.assertIn("9 Apr 2026", afterquery)
        self.assertNotIn("2026-04-09", afterquery)
        taskus = header("taskus")
        for value in ("$929.87M", "9M 2026", "Whole company", "Interim company reporting; unaudited"):
            self.assertIn(value, taskus)
        research = [company["id"] for company in self.data["companies"] if company.get("entity_type") == "adjacent_research"]
        self.assertTrue(research)
        for cid in research:
            self.assertIn("Commercial revenue does not apply.", self.pages[cid])
        self.assertNotIn("$0", header("quesma"))


if __name__ == "__main__":
    unittest.main()
