"""Synthetic operational fixtures ONLY; no real publication or research claims.

The replay-verification boundary is explicitly mocked. These tiny contexts and
opaque report/archive bytes contain no research counts, audits or live inputs.
"""
import copy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_edition_replay as replay
import research_operating_status as operating

NOW = datetime(2026, 11, 16, 18, tzinfo=timezone.utc)


def synthetic_context(root):
    receipt = {"status": "published", "verified": True, "anonymous_verified": True,
        "api_origin": "https://zenodo.org", "environment": "production", "record_id": 999999999,
        "doi": "10.5281/zenodo.999999999", "concept_doi": "10.5281/zenodo.888888888",
        "record_url": "https://zenodo.org/records/999999999", "confirmed_on": "2026-11-12T20:00:00Z",
        "artifact_sha256": "b" * 64, "release_id": "SYNTHETIC-NEVER-PUBLISHED"}
    return {"root": Path(root),
        "report": {"release_id": receipt["release_id"], "status": "published",
                   "edition_date": "2026-11-12", "archive": receipt, "editions": [],
                   "updated_on": "2026-11-12", "reviewed_on": "2026-11-11T19:00:00Z"},
        "gate": {"ready": True, "archival_ready": False, "status": "published_frozen_replay"},
        replay.MARKER: {"release_id": receipt["release_id"], "archive_receipt": copy.deepcopy(receipt)},
        replay.SOURCE_MARKER: {"schema_version": replay.SOURCE_VERSION, "sha256": "a" * 64},
        replay.SOURCE_LEDGER: [{"release_id": receipt["release_id"], "status": "published"}]}


def synthetic_status(**changes):
    value = {"schema_version": operating.VERSION, "state": "held",
        "observed_on": "2026-11-16T17:10:00Z", "published_source_sha256": "a" * 64,
        "current_release_id": "SYNTHETIC-NEVER-PUBLISHED", "current_edition_date": "2026-11-12",
        "next_edition_date": "2026-11-16", "reason_codes": ["research_review"]}
    return {**value, **changes}


class VisibleText(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.text = []
        self.tags = []
        self.feed(html)

    def handle_data(self, data):
        self.text.append(data)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


class OperatingStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.context = synthetic_context(self.root)
        self.status_path = self.root / operating.STATUS_PATH
        self.status_path.parent.mkdir(parents=True)

    def write_status(self, value=None):
        self.status_path.write_text(json.dumps(synthetic_status() if value is None else value))

    def validate(self, value=None, *, context=None, now=NOW):
        return operating.validate_operating_status(synthetic_status() if value is None else value,
                                                 self.context if context is None else context, now=now)

    def test_absence_is_exact_noop_without_clock_or_replay_reads(self):
        with patch.object(replay, "edition_entries", side_effect=AssertionError("must not verify")):
            self.assertIsNone(operating.load_operating_status(self.root, self.context))
            self.assertIs(operating.with_operating_status(self.context), self.context)
        self.assertEqual(operating.operating_status_notice(self.context), "")

    def test_frozen_replay_not_fresh_archival_readiness_authorizes_notice(self):
        self.assertFalse(self.context["gate"]["archival_ready"])
        self.write_status()
        with patch.object(replay, "edition_entries", return_value=self.context[replay.SOURCE_LEDGER]) as verify:
            selected = operating.with_operating_status(self.context, now=NOW)
        verify.assert_called_once_with(self.context)
        html = operating.operating_status_notice(selected)
        parsed = VisibleText(html)
        text = " ".join(parsed.text)
        self.assertIn("Next edition delayed", text)
        self.assertIn("November 16, 2026 at 9:00 a.m. Pacific", text)
        self.assertIn("edition shown on this website remains November 12, 2026", text)
        self.assertIn("Status observed", text)
        self.assertNotIn("script", parsed.tags)
        self.assertNotIn("gate", text.lower())
        self.assertNotIn("doi", text.lower())
        self.assertIn('<time datetime="2026-11-16T17:10:00Z">', html)

    def test_notice_leaves_last_published_report_and_archive_bytes_untouched(self):
        frozen = self.root / "SYNTHETIC-frozen-publication"
        frozen.mkdir()
        files = {"report.html": b"SYNTHETIC immutable report bytes; never actual science\n",
                 "report.pdf": b"SYNTHETIC immutable PDF bytes\n",
                 "archive.zip": b"SYNTHETIC opaque archive bytes\n",
                 "source-context.json": b"SYNTHETIC frozen source bytes\n"}
        for name, blob in files.items():
            (frozen / name).write_bytes(blob)
        before_context = copy.deepcopy(self.context)
        before = {name: hashlib.sha256((frozen / name).read_bytes()).hexdigest() for name in files}
        self.write_status()
        with patch.object(replay, "edition_entries", return_value=self.context[replay.SOURCE_LEDGER]):
            selected = operating.with_operating_status(self.context, now=NOW)
            first = operating.operating_status_notice(selected)
            second = operating.operating_status_notice(operating.with_operating_status(
                self.context, now=datetime(2026, 11, 17, 18, tzinfo=timezone.utc)))
        self.assertEqual(first, second)
        self.assertEqual(self.context, before_context)
        self.assertIs(selected["report"], self.context["report"])
        self.assertNotIn(operating.CONTEXT_KEY, self.context)
        self.assertEqual(before, {name: hashlib.sha256((frozen / name).read_bytes()).hexdigest() for name in files})
        self.assertEqual({p.name for p in frozen.iterdir()}, set(files))
        self.assertEqual(selected["report"]["editions"], [])
        self.assertEqual(selected["report"]["reviewed_on"], before_context["report"]["reviewed_on"])

    def test_loader_requires_actual_replay_verification_and_never_falls_back(self):
        self.write_status()
        with patch.object(replay, "edition_entries", side_effect=ValueError("Synthetic missing archive")):
            with self.assertRaisesRegex(ValueError, "missing archive"):
                operating.load_operating_status(self.root, self.context, now=NOW)
        with patch.object(replay, "edition_entries", return_value=[]):
            for marker in (replay.SOURCE_MARKER, replay.SOURCE_LEDGER):
                context = copy.deepcopy(self.context)
                del context[marker]
                with self.subTest(marker=marker), self.assertRaises(ValueError):
                    operating.load_operating_status(self.root, context, now=NOW)

    def test_status_without_a_real_public_selector_cannot_establish_publication(self):
        self.write_status()
        # No selector or capsule exists in this invented root. The real replay
        # boundary refuses the notice, without opening private authoring inputs.
        with self.assertRaisesRegex(ValueError, "selection or verified edition ledger"):
            operating.load_operating_status(self.root, self.context, now=NOW)

    def test_wrong_published_binding_or_prepared_state_cannot_invent_publication(self):
        variants = [synthetic_status(current_release_id="SYNTHETIC-NEW-EDITION"),
                    synthetic_status(current_edition_date="2026-11-16"),
                    synthetic_status(published_source_sha256="c" * 64),
                    synthetic_status(next_edition_date="2026-11-23"),
                    synthetic_status(next_edition_date="2026-11-17")]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(value)
        for field, value in (("status", "prepared"), ("archive", {"status": "reserved"})):
            context = copy.deepcopy(self.context)
            context["report"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(context=context)
        context = copy.deepcopy(self.context)
        context["gate"]["ready"] = 1
        with self.assertRaises(ValueError):
            self.validate(context=context)

    def test_unknown_fields_free_reason_contacts_paths_and_boolean_reasons_refused(self):
        variants = [synthetic_status(reason="Private contact person@example.invalid"),
                    synthetic_status(candidate_release_id="PRIVATE"),
                    synthetic_status(reason_codes=[True]), synthetic_status(reason_codes=True),
                    synthetic_status(reason_codes=["person@example.invalid"]),
                    synthetic_status(reason_codes=["/Users/private/cache"]),
                    synthetic_status(reason_codes=["research_review", "research_review"]),
                    synthetic_status(reason_codes=[]), synthetic_status(state="published"),
                    synthetic_status(state=[]), synthetic_status(current_release_id="<script>")]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(value)
        for value in (True, [], None, {"schema_version": operating.VERSION}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                operating.validate_operating_status(value, self.context, now=NOW)
        with self.assertRaises(ValueError):
            operating.operating_status_notice({operating.CONTEXT_KEY: synthetic_status()})

    def test_explicit_aware_clock_and_actual_observation_required(self):
        for observed in ("2026-11-16", "2026-11-16T17:10:00", "2026-11-16T19:00:00Z",
                         "2026-11-12T19:59:59Z", "2026-02-30T18:00:00Z", True):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                self.validate(synthetic_status(observed_on=observed))
        for now in (None, "2026-11-16T18:00:00Z", datetime(2026, 11, 16, 18)):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.validate(now=now)
        self.assertEqual(self.validate(synthetic_status(observed_on="2026-11-16T09:10:00-08:00")),
                         self.validate())

    def test_preparing_and_held_must_agree_with_target_and_actual_clock(self):
        before = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)
        preparing = synthetic_status(state="preparing", observed_on="2026-11-15T17:00:00Z", reason_codes=[])
        result = self.validate(preparing, now=before)
        html = operating.operating_status_notice({operating.CONTEXT_KEY: result})
        self.assertIn("Next edition preparation", html)
        self.assertIn("the next edition was being prepared for", html)
        self.assertEqual(result, self.validate(preparing))
        self.assertEqual(html, operating.operating_status_notice({
            operating.CONTEXT_KEY: self.validate(preparing)}))
        self.assertIn("At the recorded observation", html)
        with self.assertRaises(ValueError):
            self.validate({**preparing, "reason_codes": ["technical_checks"]}, now=before)
        with self.assertRaises(ValueError):
            self.validate(synthetic_status(observed_on="2026-11-15T17:00:00Z"), now=before)

    def test_target_uses_pacific_calendar_across_dst_and_at_exact_boundary(self):
        context = copy.deepcopy(self.context)
        context["report"]["edition_date"] = "2026-10-29"
        context["report"]["archive"]["confirmed_on"] = "2026-10-29T19:00:00Z"
        context[replay.MARKER]["archive_receipt"] = copy.deepcopy(context["report"]["archive"])
        value = synthetic_status(current_edition_date="2026-10-29", next_edition_date="2026-11-02",
                                 observed_on="2026-11-02T17:00:00Z")
        status = self.validate(value, context=context)
        self.assertIn('datetime="2026-11-02T09:00:00-08:00"',
                      operating.operating_status_notice({operating.CONTEXT_KEY: status}))
        with self.assertRaises(ValueError):
            self.validate({**value, "observed_on": "2026-11-02T16:59:59Z"}, context=context)
        with self.assertRaises(ValueError):
            self.validate({**value, "state": "preparing", "reason_codes": []}, context=context)

    def test_fixed_preparing_source_replays_identically_after_target_without_mutations(self):
        preparing = synthetic_status(state="preparing", observed_on="2026-11-15T17:00:00Z", reason_codes=[])
        self.write_status(preparing)
        files = {"report.html": b"SYNTHETIC frozen report", "report.pdf": b"SYNTHETIC frozen PDF",
                 "archive.zip": b"SYNTHETIC frozen ZIP", "source-context.json": b"SYNTHETIC frozen context"}
        for name, blob in files.items():
            (self.root / name).write_bytes(blob)
        source_bytes = self.status_path.read_bytes()
        context_before = copy.deepcopy(self.context)
        before_target = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)
        after_target = datetime(2026, 12, 15, 18, tzinfo=timezone.utc)
        with patch.object(replay, "edition_entries", return_value=self.context[replay.SOURCE_LEDGER]):
            before = operating.operating_status_notice(operating.with_operating_status(self.context, now=before_target))
            after = operating.operating_status_notice(operating.with_operating_status(self.context, now=after_target))
        self.assertEqual(before.encode(), after.encode())
        self.assertEqual(self.status_path.read_bytes(), source_bytes)
        self.assertEqual(self.context, context_before)
        self.assertEqual({name: (self.root / name).read_bytes() for name in files}, files)
        self.assertIn("November 16, 2026 at 9:00 a.m. Pacific", after)
        self.assertIn("November 15, 2026 at 17:00:00 UTC", after)
        self.assertIn("At the recorded observation", after)
        self.assertNotIn("published on time", after)

    def test_malformed_duplicate_symlink_oversized_and_nonfinite_status_refused(self):
        for blob in (b'{"state":', b'{"state":"held","state":"held"}', b'{"state":NaN}', b'\xff'):
            self.status_path.write_bytes(blob)
            with self.subTest(blob=blob), self.assertRaises(ValueError):
                operating.load_operating_status(self.root, self.context, now=NOW)
        self.status_path.write_bytes(b" " * 8193)
        with self.assertRaises(ValueError):
            operating.load_operating_status(self.root, self.context, now=NOW)
        self.status_path.unlink()
        self.status_path.symlink_to(self.root / "missing.json")
        with self.assertRaises(ValueError):
            operating.load_operating_status(self.root, self.context, now=NOW)

    def test_source_schema_has_same_exact_fields_and_reason_enums(self):
        schema = json.loads((ROOT / "schema/research-operating-status.schema.json").read_text())
        self.assertEqual(set(schema["required"]), operating.FIELDS)
        self.assertEqual(set(schema["properties"]), operating.FIELDS)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["properties"]["reason_codes"]["items"]["enum"]), set(operating.REASONS))


if __name__ == "__main__":
    unittest.main()
