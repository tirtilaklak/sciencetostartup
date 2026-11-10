"""Privacy, deterministic archives and lossless public export equivalence."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations


def context_fixture():
    return {"graph": {"schema_version": "1.0.0", "release_id": "test.1", "as_of": "2026-11-09T00:00:00Z",
                       "canonical_dataset_version": "2.5.0", "canonical_sha256": "a" * 64,
                       "entities": [], "sources": [], "assertions": [], "reviews": [],
                       "coverage": {"frozen_core": {"entity_ids": [], "frozen_on": None, "source_cutoff": None, "sha256": None},
                                    "quality_audit": None, "screening_audit": None, "notes": []}},
            "report": {"title": "Research preparation", "release_id": "test.1", "updated_on": "2026-11-09",
                       "status": "prelaunch", "archive": {"status": "not_published"},
                       "sections": [{"id": "scope", "title": "Scope & limits", "paragraphs": [
                           {"text": "An explicit gap <script>unsafe</script>.", "kind": "research_gap", "claim_ids": []}]}]},
            "gate": {"ready": False, "archival_ready": False, "status": "prelaunch", "reasons": ["Coverage is incomplete."], "coverage": {"papers": 0}},
            "identity": {"publisher": {"name": "Musa Ozdem"}},
            "policy": {"mode": "prepare_only"}}


class ProjectionTests(unittest.TestCase):
    def test_clean_projection_removes_legacy_email_without_changing_canonical(self):
        path = ROOT / "data/canonical.json"
        before = path.read_bytes()
        canonical = json.loads(before)
        original = copy.deepcopy(canonical)
        projection = citations.public_projection(context_fixture(), canonical)
        blob = citations.json_bytes(projection)
        self.assertIsNone(citations.EMAIL.search(blob.decode()))
        self.assertNotIn(b"xiangyi@benchflow.ai", blob)
        self.assertNotIn("raw_inputs", projection["canonical"])
        self.assertEqual(canonical, original)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(projection["projection_version"], "1.0.0")

    def test_nested_contacts_raw_text_and_quotes_are_excluded(self):
        value = {"items": [{"EMAIL": "private@example.org", "statement": "Ask name@example.org now.",
                            "source_quote": "third-party quote", "raw_response": "entire page", "count": 0}], "raw_inputs": []}
        clean = citations.privacy_filter(value)
        self.assertEqual(clean, {"items": [{"statement": "Ask [contact removed] now.", "count": 0}]})

    def test_json_csv_sqlite_round_trip_preserves_types_empty_arrays_and_unicode(self):
        projection = {"schema_version": 1, "canonical": {"dataset_version": "2.5.0", "empty": [],
                      "items": [{"x": "τ\ncomma,quote\"", "zero": 0, "flag": False, "null": None}]}, "graph": {"entities": []}}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            citations.write_projection(projection, output)
            with (output / "clean-dataset.csv").open(newline="") as stream:
                rows = list(csv.reader(stream))[1:]
            with sqlite3.connect(output / "clean-dataset.sqlite") as database:
                sql_rows = database.execute("SELECT collection, position, kind, value_json FROM projection_rows ORDER BY collection, position").fetchall()
            self.assertEqual(citations.projection_from_rows(rows), projection)
            self.assertEqual(citations.projection_from_rows(sql_rows), projection)
            first = {path.name: path.read_bytes() for path in output.iterdir()}
            citations.write_projection(projection, output)
            self.assertEqual(first, {path.name: path.read_bytes() for path in output.iterdir()})


class CitationTests(unittest.TestCase):
    def test_person_names_preserve_the_disclosed_individual_in_citation_formats(self):
        context = context_fixture()
        context["identity"]["publisher"].update(type="Person", given_names="Musa", family_names="Ozdem")
        metadata = citations.publication_metadata(context)
        self.assertEqual(metadata["author_person"], {"given": "Musa", "family": "Ozdem"})
        formats = citations.citation_formats(metadata)
        self.assertEqual(json.loads(formats["CITATION.cff"])["authors"], [{"given-names": "Musa", "family-names": "Ozdem"}])
        self.assertEqual(json.loads(formats["citation.csl.json"])["author"], [{"given": "Musa", "family": "Ozdem"}])
        self.assertIn(b"author = {Musa Ozdem}", formats["citation.bib"])
        self.assertNotIn(b"author = {{", formats["citation.bib"])
        self.assertIn(b"AU  - Ozdem, Musa", formats["citation.ris"])

    def test_organization_fallback_retains_literal_citation_names(self):
        context = context_fixture()
        context["identity"]["publisher"] = {"name": "ScienceToStartup", "type": "Organization"}
        formats = citations.citation_formats(citations.publication_metadata(context))
        self.assertEqual(json.loads(formats["CITATION.cff"])["authors"], [{"name": "ScienceToStartup"}])
        self.assertEqual(json.loads(formats["citation.csl.json"])["author"], [{"literal": "ScienceToStartup"}])
        self.assertIn(b"author = {{ScienceToStartup}}", formats["citation.bib"])

    def test_prelaunch_and_reserved_doi_never_become_published_citations(self):
        context = context_fixture()
        context["report"]["archive"] = {"status": "reserved", "doi": "10.1234/reserved", "record_url": "https://example.org/draft", "confirmed_on": "2026-11-09"}
        metadata = citations.publication_metadata(context)
        self.assertEqual(metadata["status"], "prelaunch")
        self.assertEqual(metadata["author"], "Musa Ozdem")
        self.assertNotIn("doi", metadata)
        formats = citations.citation_formats(metadata)
        for blob in formats.values():
            self.assertNotIn(b"10.1234/reserved", blob)
        self.assertNotIn("issued", json.loads(formats["citation.csl.json"]))
        self.assertNotIn("date-released", json.loads(formats["CITATION.cff"]))
        self.assertNotIn(b"PY  -", formats["citation.ris"])

    def test_only_gate_confirmed_archive_can_supply_doi_and_actual_publication_date(self):
        context = context_fixture()
        context["gate"]["ready"] = True
        context["report"]["archive"] = {"status": "published", "doi": "10.1234/actual", "record_url": "https://example.org/record",
            "confirmed_on": "2026-11-12", "published_on": "2026-11-10", "artifact_sha256": "a" * 64, "release_id": "test.1"}
        metadata = citations.publication_metadata(context)
        self.assertEqual(metadata["status"], "published")
        formats = citations.citation_formats(metadata)
        self.assertEqual(json.loads(formats["citation.csl.json"])["issued"], {"date-parts": [[2026, 11, 10]]})
        context["report"]["archive"].pop("published_on")
        formats = citations.citation_formats(citations.publication_metadata(context))
        self.assertNotIn("issued", json.loads(formats["citation.csl.json"]))

    def test_offline_report_escapes_markup_and_preserves_all_paragraphs(self):
        context = context_fixture()
        html = citations.offline_html(context).decode()
        self.assertIn("&lt;script&gt;unsafe&lt;/script&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("Coverage is incomplete.", html)
        self.assertIn("research_gap", html)

    def test_archive_deterministic_manifest_bound_and_no_network(self):
        context = context_fixture()
        projection = citations.public_projection(context, {"dataset_version": "2.5.0", "companies": []})
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            context["root"] = first  # This synthetic publication has no prepared real-report PDF.
            with patch.object(citations, "public_projection", return_value=projection), patch("urllib.request.urlopen", side_effect=AssertionError("network in build")):
                a = citations.write_publication_assets(context, first)
                b = citations.write_publication_assets(context, second)
            self.assertEqual(a, b)
            for name in a:
                self.assertEqual((Path(first) / name).read_bytes(), (Path(second) / name).read_bytes(), name)
            package = Path(first) / "publication"
            manifest = json.loads((package / "MANIFEST.json").read_text())
            self.assertTrue({"zenodo-metadata.json", "huggingface-README.md"} <= set(manifest["files"]))
            with zipfile.ZipFile(package / "research-archive.zip") as archive:
                self.assertEqual(set(archive.namelist()), set(manifest["files"]) | {"MANIFEST.json"})
                for name, descriptor in manifest["files"].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), descriptor["sha256"])
                    self.assertEqual(archive.getinfo(name).date_time, (1980, 1, 1, 0, 0, 0))
            status = json.loads((package / "package-status.json").read_text())
            self.assertEqual(status["archive"], "not-published")
            self.assertFalse(status["publication_ready"])
            self.assertEqual(status["pdf"], "requires-preparation")

    def test_stale_precomputed_pdf_fails_closed(self):
        context = context_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            context["root"] = temporary
            output = Path(temporary) / "data/research"
            output.mkdir(parents=True)
            (output / "report.pdf").write_bytes(b"unit-test-bytes")
            (output / "report-pdf.json").write_bytes(citations.json_bytes({"sha256": citations.sha256(b"unit-test-bytes"), "context_sha256": "stale"}))
            with self.assertRaisesRegex(ValueError, "does not match"):
                citations.verified_pdf(context)


if __name__ == "__main__":
    unittest.main()
