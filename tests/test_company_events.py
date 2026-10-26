"""The dated company events sidecar: strict validation, build embedding and the Risks and disputes section."""
import html
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import observatory
from observatory import ValidationError, build, load_company_events, validate_company_events
from fixtures import fixture
from static_pages import EVENTS_NOTE, clean, date_rank, load_copy_edits, public_wording

EMPTY = {"version": "1.0.0", "events": []}


def embedded(dist, name):
    """Run the built data bundle (dist/js/data.<hash>.js) as the page does and return one window value."""
    bundle = dist / re.search(r'"(js/data[.][0-9a-f]+[.]js)"', (dist / "index.html").read_text()).group(1)
    script = "const fs=require('fs'),vm=require('vm'),window={};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,JSON});process.stdout.write(JSON.stringify(window[process.argv[2]]??null));"
    return json.loads(subprocess.run(["node", "-e", script, str(bundle), name], capture_output=True, text=True, check=True).stdout)


def sample():
    source = {"url": "https://example.org/docket", "title": "Test docket", "publisher": "Test Court", "published_on": "2025-09-03", "source_type": "court_record"}
    return {"version": "1.0.0", "reviewed_on": "2026-10-23", "note": "Test fixture only. Not research.", "events": [
        {"id": "scale_ai.event.test-complaint", "company_id": "scale_ai", "related_company_ids": ["mercor"], "kind": "lawsuit", "date": "2025-09-03", "date_basis": "filed", "title": "Test complaint & reply", "detail": "Test detail for a filed complaint.", "status": "Pending", "status_checked_on": "2026-10-23", "sources": [source]},
        {"id": "scale_ai.event.test-pause", "company_id": "scale_ai", "related_company_ids": [], "kind": "customer_change", "date": "2025-06", "date_basis": "reported", "title": "Test customer pause", "detail": "Test detail for a month date.", "status": "Reported", "status_checked_on": "2026-10-23", "sources": [dict(source, url="https://example.org/report", publisher="Test Wire", published_on=None, source_type="news")]},
    ]}


class CompanyEventsValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data = json.loads((ROOT / "data/canonical.json").read_text())

    def rejects(self, message, change):
        events = sample()
        change(events)
        with self.assertRaisesRegex(ValidationError, message): validate_company_events(events, self.data)

    def event(self, field, value):
        return lambda events: events["events"][0].__setitem__(field, value)

    def source(self, field, value):
        return lambda events: events["events"][0]["sources"][0].__setitem__(field, value)

    def test_accepts_the_shared_format(self):
        events = sample()
        self.assertIs(validate_company_events(events, self.data), events)
        self.assertEqual(validate_company_events(dict(sample(), events=[]), self.data)["events"], [])
        events = sample()
        events["events"][0].update(date="2026-10-23", title="T" * 110, detail="D" * 320, status="S" * 40)
        validate_company_events(events, self.data)

    def test_rejects_unexpected_shape(self):
        self.rejects("root must hold exactly", lambda e: e.update(extra=1))
        self.rejects("root must hold exactly", lambda e: e.pop("note"))
        self.rejects("unsupported version", lambda e: e.update(version="2.0.0"))
        self.rejects("events is not a list", lambda e: e.update(events={}))
        self.rejects("each event must hold exactly", lambda e: e["events"][0].update(url="https://example.org"))
        self.rejects("each event must hold exactly", lambda e: e["events"][0].pop("detail"))
        self.rejects("each source must hold exactly", lambda e: e["events"][0]["sources"][0].pop("published_on"))
        self.rejects("sources must be a non-empty list", self.event("sources", []))

    def test_rejects_bad_ids_and_references(self):
        for value in ["Scale_ai.event.test", "scale_ai.events.test", "scale_ai.event.Test_slug", "scale-ai.event.test", "scale_ai.event.", 7]:
            self.rejects("invalid event id", self.event("id", value))
        self.rejects("duplicate event id", lambda e: e["events"][1].update(id=e["events"][0]["id"]))
        self.rejects("unknown company_id", self.event("company_id", "not_profiled"))
        self.rejects("unknown company_id", self.event("company_id", ["scale_ai"]))
        self.rejects("related_company_ids must list known company IDs", self.event("related_company_ids", ["not_profiled"]))
        self.rejects("related_company_ids must list known company IDs", self.event("related_company_ids", "mercor"))
        self.rejects("must start with its company_id", self.event("id", "mercor.event.test-complaint"))
        self.rejects("related_company_ids must not repeat", self.event("related_company_ids", ["scale_ai"]))
        self.rejects("related_company_ids must not repeat", self.event("related_company_ids", ["mercor", "mercor"]))

    def test_rejects_unsupported_vocabulary(self):
        self.rejects("unsupported kind", self.event("kind", "verdict"))
        self.rejects("unsupported date_basis", self.event("date_basis", "ruled"))
        self.rejects("unsupported source_type", self.source("source_type", "blog"))

    def test_rejects_bad_and_future_dates(self):
        for value in ["2025/09/03", "2025", "2025-9-3", "Sep 2025", "２０２５-09-03", None]:
            self.rejects("date must be YYYY-MM-DD or YYYY-MM", self.event("date", value))
        for value in ["2025-02-30", "2025-13"]:
            self.rejects("date is not a calendar date", self.event("date", value))
        for value in ["2026-10-24", "2026-11"]:
            self.rejects("date is after reviewed_on", self.event("date", value))
        self.rejects("reviewed_on must be YYYY-MM-DD", lambda e: e.update(reviewed_on="23 Oct 2026"))
        self.rejects("status_checked_on must be YYYY-MM-DD", self.event("status_checked_on", "2026-10"))
        self.rejects("published_on must be YYYY-MM-DD", self.source("published_on", "2025-09"))
        self.rejects("status_checked_on is after reviewed_on", self.event("status_checked_on", "2026-10-24"))
        self.rejects("published_on is after reviewed_on", self.source("published_on", "2026-10-24"))

    def test_rejects_long_markup_and_control_text(self):
        self.rejects("title is longer than 110", self.event("title", "T" * 111))
        self.rejects("detail is longer than 320", self.event("detail", "D" * 321))
        self.rejects("status is longer than 40", self.event("status", "S" * 41))
        for value in ["<b>Bold</b>", "a > b", "Line\nbreak", "Tab\tstop", "Delete\x7f"]:
            self.rejects("title must be plain text", self.event("title", value))
            self.rejects("source publisher must be plain text", self.source("publisher", value))
        for value in ["Next\x85line", "Escape\x9b", "Line\u2028separator", "Override\u202e", "Isolate\u2066", "Mark\u200f"]:
            self.rejects("title must be plain text", self.event("title", value))
            self.rejects("detail must be plain text", self.event("detail", value))
            self.rejects("status must be plain text", self.event("status", value))
            self.rejects("source publisher must be plain text", self.source("publisher", value))
        self.rejects("note must be plain text", lambda e: e.update(note="<script>"))
        self.rejects("source title must be plain text", self.source("title", "a<b"))
        for value in ["", "   ", None]:
            self.rejects("status must be non-empty text", self.event("status", value))

    def test_rejects_unsafe_source_urls(self):
        for value in ["http://example.org/case", "https://user:secret@example.org/case", "https://user@example.org/case", "https:///case", "javascript:alert(1)", "https://example.org/a b", "https://example.org:99999/case", "ftp://example.org/case", 42]:
            self.rejects("source url must be https with a hostname and no credentials", self.source("url", value))

    def test_loader_defaults_when_missing_or_for_other_datasets(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "company-events.json"
            self.assertEqual(load_company_events(path, self.data), EMPTY)
            path.write_text(json.dumps(sample()))
            self.assertEqual(load_company_events(path, self.data), sample())
            self.assertEqual(load_company_events(path, fixture()), EMPTY)
            path.write_text(json.dumps(dict(sample(), version="9")))
            with self.assertRaises(ValidationError): load_company_events(path, self.data)


class CompanyEventsBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data/canonical.json").read_text())
        cls.temp = tempfile.TemporaryDirectory(prefix="company-events-")
        root, cls.dist = Path(cls.temp.name) / "root", Path(cls.temp.name) / "dist"
        (root / "data").mkdir(parents=True)
        for name in ("web", "docs", "schema"): (root / name).symlink_to(ROOT / name)
        for path in (ROOT / "data").iterdir():
            if path.name != "company-events.json": (root / "data" / path.name).symlink_to(path)
        (root / "data/company-events.json").write_text(json.dumps(sample()))
        with mock.patch.object(observatory, "ROOT", root): build(cls.data, cls.dist)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def page(self, cid): return (self.dist / "company" / cid / "index.html").read_text()

    def test_build_embeds_and_copies_the_sidecar(self):
        # The sidecar ships in the data bundle, which the page runs before the app bundle that reads it.
        files = json.loads(re.search(r"const files=(\[[^\]]*\])", (self.dist / "index.html").read_text()).group(1))
        self.assertEqual([name.split(".")[0] for name in files], ["js/data", "js/app"])
        self.assertEqual(embedded(self.dist, "COMPANY_EVENTS"), sample())
        self.assertEqual(json.loads((self.dist / "company-events.json").read_text()), sample())
        self.assertIn("company-events.json", json.loads((self.dist / "manifest.json").read_text())["sha256"])

    def test_fixture_build_embeds_the_empty_default(self):
        with tempfile.TemporaryDirectory() as folder:
            build(fixture(), Path(folder))
            self.assertEqual(embedded(Path(folder), "COMPANY_EVENTS"), EMPTY)

    def test_dated_events_render_newest_first_with_publisher_links(self):
        text = self.page("scale_ai")
        self.assertLess(text.index('<h2 id="figures">Key figures</h2>'), text.index('<h2 id="risks">Risks and disputes</h2>'))
        self.assertLess(text.index('<h2 id="risks">Risks and disputes</h2>'), text.index('<h2 id="work">'))
        self.assertLess(text.index("Test complaint &amp; reply"), text.index("Test customer pause"))
        for fragment in ["<h3>Dated events</h3>", '<td class="date" data-label="Date">Sep 2025<span class="sub">Lawsuit</span></td>', '<td class="date" data-label="Date">Jun 2025<span class="sub">Customer change</span></td>', '<td data-label="Status">Pending</td>', '<a class="ext" href="https://example.org/docket">Test Court</a>', '<a class="ext" href="https://example.org/report">Test Wire</a>', f'<p class="muted">{EVENTS_NOTE} Statuses were checked on 23 Oct 2026.</p>']:
            self.assertIn(fragment, text)
        related = self.page("mercor")
        self.assertIn("Test complaint &amp; reply", related)
        self.assertNotIn("Test customer pause", related)
        self.assertNotIn("<h3>Dated events</h3>", self.page("prolific"))
        self.assertIn("<h3>Risks named in the evidence</h3>", self.page("appen"))
        self.assertNotIn(EVENTS_NOTE, self.page("appen"), "the lawsuit note goes with dated events only")

    def test_supported_risk_claims_render_newest_first(self):
        risks = [c for c in self.data["claims"] if c["subject"] == "risks"]
        say = public_wording(self.data, load_copy_edits())
        shown = lambda claim: html.escape(clean(say(claim["statement"])))  # static pages print the app's public wording
        for company in self.data["companies"]:
            text, cid = self.page(company["id"]), company["id"]
            own = [c for c in risks if c["company_id"] == cid]
            supported = [c for c in own if c["status"] == "supported"]
            self.assertEqual("<h3>Risks named in the evidence</h3>" in text, bool(supported), cid)
            ranks = [date_rank(c["as_of"]) for c in sorted(supported, key=lambda c: text.index(shown(c)))]
            self.assertEqual(ranks, sorted(ranks, reverse=True), cid)
            for claim in own:
                if claim["status"] != "supported": self.assertNotIn(shown(claim), text, claim["id"])

    def test_section_is_hidden_when_empty(self):
        quiet = [c["id"] for c in self.data["companies"] if c["id"] not in ("scale_ai", "mercor") and not any(x["company_id"] == c["id"] and x["subject"] == "risks" and x["status"] == "supported" for x in self.data["claims"])]
        self.assertTrue(quiet)
        for cid in quiet:
            text = self.page(cid)
            self.assertNotIn("Risks and disputes", text, cid)
            self.assertNotIn(EVENTS_NOTE, text, cid)


if __name__ == "__main__":
    unittest.main()
