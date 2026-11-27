"""Current company facts retain company scope and dated, pinned evidence."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from company_updates import CompanyUpdatesValidationError, validate_profile_current_facts


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

    def test_additional_registry_ids_are_explicit_and_canonical_scope_stays_strict(self):
        content = example()
        content["entries"][0]["company_id"] = "org.reviewed"
        original = copy.deepcopy((content, self.data))
        with self.assertRaisesRegex(CompanyUpdatesValidationError, "known company"):
            validate_profile_current_facts(content, self.data)
        self.assertIs(validate_profile_current_facts(content, self.data, additional_company_ids={"org.reviewed"}), content)
        with self.assertRaisesRegex(CompanyUpdatesValidationError, "known company"):
            validate_profile_current_facts(content, self.data, additional_company_ids={"org.other"})
        with self.assertRaisesRegex(CompanyUpdatesValidationError, "validated organization IDs"):
            validate_profile_current_facts(content, self.data, additional_company_ids={"unreviewed"})
        self.assertEqual((content, self.data), original)

    def test_explicit_registry_review_ceiling_does_not_refresh_fact_dates(self):
        content = example()
        validate_profile_current_facts(content, self.data, reviewed_through="2026-11-16")
        with self.assertRaisesRegex(CompanyUpdatesValidationError, "after the registry review"):
            validate_profile_current_facts(content, self.data, reviewed_through="2026-11-15")
        self.assertEqual(content["entries"][0]["current_facts"]["reviewed_on"], "2026-11-16")

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

    def test_later_update_retains_an_earlier_field_review(self):
        content = example()
        facts = content["entries"][0]["current_facts"]
        original_row = copy.deepcopy(facts["rows"][0])
        facts["rows"][0]["reviewed_on"] = facts["reviewed_on"]
        facts["reviewed_on"] = "2026-11-27"
        newer = copy.deepcopy(facts["sources"][0])
        newer["observed_on"] = "2026-11-27"
        facts["sources"].append(newer)
        facts["rows"].append({"label": "New observation", "value": "Separate field", "source_indexes": [1]})
        validate_profile_current_facts(content, self.data)
        self.assertEqual(facts["rows"][0], {**original_row, "reviewed_on": "2026-11-16"})
        self.assertEqual(facts["sources"][0]["observed_on"], "2026-11-16")

    def test_field_review_cannot_precede_its_evidence_or_follow_its_block(self):
        self.rejects(lambda entry: entry["current_facts"]["rows"][0].update(reviewed_on="2026-11-15"), "source observation is after the row review")
        self.rejects(lambda entry: entry["current_facts"]["rows"][0].update(reviewed_on="2026-11-17"), "after the block review")
        self.rejects(lambda entry: entry["current_facts"]["rows"][0].update(reviewed_on="2026-02-30"), "calendar date")

    def test_native_fact_dates_show_the_retained_field_review(self):
        from static_pages import current_facts_html
        entry = example()["entries"][0]
        entry["current_facts"]["rows"][0]["reviewed_on"] = "2026-11-16"
        entry["current_facts"]["reviewed_on"] = "2026-11-27"
        html = current_facts_html(entry)
        self.assertIn('Updates checked 27 Nov 2026', html)
        self.assertIn('<time datetime="2026-11-16">16 Nov 2026</time>', html)
        self.assertIn('31 Jul 2026', html)
        self.assertNotIn('current-fact-review', current_facts_html(example()["entries"][0]))


if __name__ == "__main__":
    unittest.main()
