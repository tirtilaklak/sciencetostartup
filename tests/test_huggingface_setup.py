"""Synthetic account-scope fixtures, never actual access or publication evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huggingface_setup", ROOT / "tools/publishing/huggingface_setup.py")
hf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hf)


def fixture():
    dataset = {"id": "test-owner/test-dataset", "_id": "a" * 24, "private": True}
    identity = {"name": "test-owner", "type": "user", "email": "PRIVATE-EMAIL-SENTINEL",
                "auth": {"accessToken": {"displayName": "PRIVATE-TOKEN-NAME-SENTINEL", "role": "fineGrained",
                    "fineGrained": {"scoped": [{"entity": {"type": "dataset", "_id": "a" * 24},
                                               "permissions": ["repo.content.read", "repo.content.write"]}]}}}}
    return identity, dataset


class ScopeTests(unittest.TestCase):
    def evidence(self, identity, dataset):
        return hf.scope_evidence(identity, dataset, "test-owner/test-dataset")

    def test_exact_scoped_content_write_is_evidence_only(self):
        result = self.evidence(*fixture())
        self.assertTrue(result["target_write_scope_evidence"])
        self.assertTrue(result["content_only_scope_evidence"])
        self.assertEqual(result["namespace_relation"], "personal-owner")
        self.assertFalse(result["remote_write_verified"])
        self.assertFalse(result["publication_authorized"])

    def test_general_write_token_never_passes_scoped_check(self):
        identity, dataset = fixture()
        identity["auth"]["accessToken"]["role"] = "write"
        self.assertFalse(self.evidence(identity, dataset)["target_write_scope_evidence"])

    def test_read_access_never_claims_write(self):
        identity, dataset = fixture()
        identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]["permissions"] = ["repo.content.read"]
        result = self.evidence(identity, dataset)
        self.assertTrue(result["target_only_scope_evidence"])
        self.assertFalse(result["target_write_scope_evidence"])

    def test_additional_repository_scope_is_rejected(self):
        identity, dataset = fixture()
        scope = identity["auth"]["accessToken"]["fineGrained"]["scoped"]
        scope.append(copy.deepcopy(scope[0]))
        scope[1]["entity"]["_id"] = "b" * 24
        self.assertFalse(self.evidence(identity, dataset)["target_only_scope_evidence"])

    def test_namespace_scope_is_rejected(self):
        identity, dataset = fixture()
        identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]["entity"]["type"] = "user"
        self.assertFalse(self.evidence(identity, dataset)["target_only_scope_evidence"])

    def test_global_and_gated_permissions_are_rejected(self):
        for key, value in (("global", ["post.write"]), ("canReadGatedRepos", True), ("futureGlobalPermission", True)):
            with self.subTest(key=key):
                identity, dataset = fixture()
                identity["auth"]["accessToken"]["fineGrained"][key] = value
                self.assertFalse(self.evidence(identity, dataset)["target_only_scope_evidence"])

    def test_unrelated_permission_is_rejected(self):
        identity, dataset = fixture()
        identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]["permissions"].append("user.tokens.write")
        self.assertFalse(self.evidence(identity, dataset)["target_only_scope_evidence"])

    def test_changed_scope_schema_is_rejected(self):
        for level in ("entry", "entity"):
            with self.subTest(level=level):
                identity, dataset = fixture()
                entry = identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]
                target = entry if level == "entry" else entry["entity"]
                target["futurePermissionExpansion"] = True
                self.assertFalse(self.evidence(identity, dataset)["target_only_scope_evidence"])

    def test_wrong_dataset_id_or_name_is_rejected(self):
        identity, dataset = fixture()
        entry = identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]["entity"]
        entry.update(_id="b" * 24, name="test-owner/test-dataset")
        self.assertFalse(self.evidence(identity, dataset)["target_only_scope_evidence"])
        dataset["id"] = "test-owner/different-dataset"
        self.assertFalse(self.evidence(identity, dataset)["repository_identity_matches"])

    def test_org_membership_is_not_creation_permission(self):
        identity, dataset = fixture()
        identity.update(name="different-user", orgs=[{"name": "test-owner", "roleInOrg": "read"}])
        result = self.evidence(identity, dataset)
        self.assertEqual(result["namespace_relation"], "organization-member")
        self.assertFalse(result["namespace_creation_permission_verified"])

    def test_target_scoped_legacy_repo_write_is_labeled(self):
        identity, dataset = fixture()
        identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]["permissions"] = ["repo.content.read", "repo.access.read", "repo.write"]
        result = self.evidence(identity, dataset)
        self.assertTrue(result["target_write_scope_evidence"])
        self.assertFalse(result["content_only_scope_evidence"])

    def test_malformed_or_missing_schema_fails_closed(self):
        for identity in ({}, {"auth": None}, {"auth": {"accessToken": []}}, {"orgs": None}, None):
            self.assertFalse(self.evidence(identity, {})["target_write_scope_evidence"])

    def test_output_omits_email_and_token_display_name(self):
        result = json.dumps(self.evidence(*fixture()))
        self.assertNotIn("PRIVATE-", result)
        self.assertNotIn("accessToken", result)

    def test_bad_repository_is_rejected(self):
        for repository in ("https://huggingface.co/x/y", "x/y?token=secret", "x/../y", "x/y.git", "x/y#z", None):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                hf.scope_evidence({}, {}, repository)


class DestinationTests(unittest.TestCase):
    def test_existing_destination_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "keep.txt"
            marker.write_text("keep")
            with self.assertRaises(ValueError):
                hf.stage(ROOT, temporary)
            self.assertEqual(marker.read_text(), "keep")

    def test_destination_inside_scientific_checkout_is_rejected(self):
        with self.assertRaises(ValueError):
            hf.stage(ROOT, ROOT / "test-only-hf-staging-must-not-exist")


if __name__ == "__main__":
    unittest.main()
