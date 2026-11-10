import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from public_identity import load_identity, publisher_node, review_contributions, validate_identity


class PublicIdentityTests(unittest.TestCase):
    def test_single_person_identity_and_unconfirmed_external_access(self):
        identity = load_identity()
        self.assertEqual(publisher_node(identity)["url"], identity["origin"] + "/method/#about")
        self.assertTrue(all(p["status"] != "verified_current" for p in identity["external_profiles"] if p["service"] != "GitHub"))
        self.assertEqual(review_contributions(), [])

    def test_publisher_and_review_claim_drift_is_rejected(self):
        for mutate in (lambda i: i["publisher"].update(type="Organization"),
                       lambda i: i["publisher"].update(url="https://example.com"),
                       lambda i: i["review_policy"].update(automated_review_label="Human peer reviewed"),
                       lambda i: i["contacts"].update(review="javascript:alert(1)")):
            identity = copy.deepcopy(load_identity())
            mutate(identity)
            with self.assertRaises(ValueError):
                validate_identity(identity)

    def test_external_credit_requires_explicit_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            row = {"id": "r1", "edition_id": "2026-11-09", "section_id": "methods", "contribution": "Source correction", "source_url": "https://example.com/review", "reviewer_type": "human", "credit_consent": False}
            path = root / "data/review-contributions.json"
            path.write_text(json.dumps({"schema_version": "1.0.0", "contributions": [row]}))
            with self.assertRaises(ValueError):
                review_contributions(root)
            row["credit_consent"] = True
            path.write_text(json.dumps({"schema_version": "1.0.0", "contributions": [row]}))
            self.assertEqual(len(review_contributions(root)), 1)


if __name__ == "__main__":
    unittest.main()
