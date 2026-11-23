"""Current company facts retain company scope and dated, pinned evidence."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from company_updates import CompanyUpdatesValidationError, validate_profile_current_facts
from static_pages import current_facts_html


def example():
    return {"entries": [{"company_id": "sample", "current_facts": {
        "reviewed_on": "2026-11-16",
        "rows": [{"label": "Legal closing", "value": "31 Jul 2026", "source_indexes": [0]}],
        "sources": [{"url": "https://example.org/filing", "title": "Quarterly filing", "published_on": "2026-10-27", "observed_on": "2026-11-16", "response_sha256": "a" * 64, "locator": "Note 10, Business combinations"}]
    }}]}


class CurrentCompanyFactsTests(unittest.TestCase):
    data = {"companies": [{"id": "sample"}]}

    def rejects(self, modify, message):
        content = example()
        modify(content["entries"][0])
        with self.assertRaisesRegex(CompanyUpdatesValidationError, message):
            validate_profile_current_facts(content, self.data)

    def test_optional_content_and_input_identity(self):
        content = {"entries": [{"company_id": "historical", "notes": []}]}
        self.assertIs(validate_profile_current_facts(content, self.data), content)
        content = example()
        original = copy.deepcopy(content)
        self.assertIs(validate_profile_current_facts(content, self.data), content)
        self.assertEqual(content, original)

    def test_company_scope_and_duplicates(self):
        self.rejects(lambda entry: entry.update(company_id="other"), "known company")
        content = example()
        content["entries"].append(copy.deepcopy(content["entries"][0]))
        with self.assertRaisesRegex(CompanyUpdatesValidationError, "duplicate current facts"):
            validate_profile_current_facts(content, self.data)

    def test_source_dates_are_distinct_and_calendar_valid(self):
        for field, value, message in [
            ("published_on", "2026-11-17", "after observation"),
            ("published_on", "2026-02-30", "calendar date"),
            ("observed_on", "2026-11-17", "after the review"),
            ("observed_on", "2026-11", "YYYY-MM-DD"),
        ]:
            with self.subTest(field=field, value=value):
                self.rejects(lambda entry: entry["current_facts"]["sources"][0].update({field: value}), message)
        self.rejects(lambda entry: entry["current_facts"].update(reviewed_on="2026-02-30"), "calendar date")
        content = example()
        content["entries"][0]["current_facts"]["sources"][0]["published_on"] = None
        validate_profile_current_facts(content, self.data)

    def test_sources_require_pinned_safe_receipts(self):
        for url in ["http://example.org/a", "https://user:password@example.org/a", "https://example.org/a\nb", "https://[bad/a"]:
            with self.subTest(url=url):
                self.rejects(lambda entry: entry["current_facts"]["sources"][0].update(url=url), "HTTPS")
        for sha in ["", "x" * 64, "A" * 64, "a" * 63]:
            with self.subTest(sha=sha):
                self.rejects(lambda entry: entry["current_facts"]["sources"][0].update(response_sha256=sha), "SHA-256")
        self.rejects(lambda entry: entry["current_facts"]["sources"][0].update(locator=""), "non-empty")
        self.rejects(lambda entry: entry["current_facts"]["sources"][0].update(locator="<script>"), "plain text")

    def test_rows_require_valid_source_references(self):
        for references in [[], [1], [-1], [True], [0, 0], "0"]:
            with self.subTest(references=references):
                self.rejects(lambda entry: entry["current_facts"]["rows"][0].update(source_indexes=references), "source_indexes")
        self.rejects(lambda entry: entry["current_facts"].update(rows=[]), "rows must be non-empty")
        self.rejects(lambda entry: entry["current_facts"].update(sources=[]), "sources must be non-empty")
        self.rejects(lambda entry: entry["current_facts"]["rows"][0].update(value=""), "non-empty")

    def test_unknown_current_fact_fields_fail(self):
        self.rejects(lambda entry: entry["current_facts"].update(description="new narrative"), "must contain")
        self.rejects(lambda entry: entry["current_facts"]["sources"][0].update(private_note="private"), "unsupported source fields")
        self.rejects(lambda entry: entry["current_facts"]["rows"][0].update(description="new narrative"), "must contain")

    def test_extracted_primary_content_is_explicit(self):
        content = example()
        content["entries"][0]["current_facts"]["sources"][0]["content_kind"] = "web_tool_text_excerpt"
        validate_profile_current_facts(content, self.data)
        self.rejects(lambda entry: entry["current_facts"]["sources"][0].update(content_kind="raw_page_inferred"), "content_kind is unsupported")

    def test_rws_disclosures_distinguish_group_expectation_and_completed_acquisition(self):
        profiles = json.loads((ROOT / "data/profile-content.json").read_bytes())
        canonical = json.loads((ROOT / "data/canonical.json").read_bytes())
        validate_profile_current_facts(profiles, canonical)
        entry = next(row for row in profiles["entries"] if row["company_id"] == "rws_trainai")
        facts = entry["current_facts"]
        trading, acquisition = facts["rows"]
        self.assertIn("Unaudited", trading["label"])
        self.assertIn("expected about £700 million in group revenue", trading["value"])
        self.assertEqual(trading["source_indexes"], [0])
        self.assertIn("completed its acquisition of Acogroup", acquisition["value"])
        self.assertEqual(acquisition["source_indexes"], [1, 2])
        self.assertEqual([source["published_on"] for source in facts["sources"]],
                         ["2026-10-27", "2026-11-02", "2026-11-02"])
        markup = current_facts_html(entry)
        for source in facts["sources"]:
            self.assertIn(f'href="{source["url"]}"', markup)


if __name__ == "__main__":
    unittest.main()
