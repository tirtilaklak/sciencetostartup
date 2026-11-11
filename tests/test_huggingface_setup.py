"""Synthetic account-scope fixtures, never actual access or publication evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import sys
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("huggingface_setup", ROOT / "tools/publishing/huggingface_setup.py")
hf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hf)


def fixture():
    dataset = {"id": "test-owner/test-dataset", "_id": "a" * 24, "private": True}
    identity = {"id": "c" * 24, "name": "test-owner", "type": "user", "email": "PRIVATE-EMAIL-SENTINEL",
                "auth": {"type": "access_token", "accessToken": {"displayName": "PRIVATE-TOKEN-NAME-SENTINEL", "createdAt": "2026-01-01T00:00:00Z", "role": "fineGrained",
                    "fineGrained": {"global": [], "canReadGatedRepos": False, "scoped": [{"entity": {"type": "dataset", "_id": "a" * 24},
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

    def test_owner_descriptor_and_dataset_author_are_not_extra_grants(self):
        identity, dataset = fixture()
        identity["id"] = "c" * 24
        scope = identity["auth"]["accessToken"]["fineGrained"]["scoped"]
        scope[0]["entity"].update(name="test-owner/test-dataset", authorId=identity["id"])
        scope.append({"entity": {"type": "user", "_id": identity["id"], "name": identity["name"]},
                      "permissions": []})
        result = self.evidence(identity, dataset)
        self.assertTrue(result["target_only_scope_evidence"])
        self.assertTrue(result["target_write_scope_evidence"])
        self.assertFalse(result["remote_write_verified"])
        for change in ("owner_name", "owner_id", "owner_grant", "dataset_author", "dataset_name"):
            with self.subTest(change=change):
                altered = copy.deepcopy(identity)
                rows = altered["auth"]["accessToken"]["fineGrained"]["scoped"]
                if change == "owner_name": rows[1]["entity"]["name"] = "someone-else"
                if change == "owner_id": rows[1]["entity"]["_id"] = "d" * 24
                if change == "owner_grant": rows[1]["permissions"] = ["repo.write"]
                if change == "dataset_author": rows[0]["entity"]["authorId"] = "d" * 24
                if change == "dataset_name": rows[0]["entity"]["name"] = "test-owner/other"
                self.assertFalse(self.evidence(altered, dataset)["target_only_scope_evidence"])

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


class HardeningScopeTests(unittest.TestCase):
    def test_unknown_authorization_fields_at_every_container_are_rejected(self):
        for container in ("auth", "accessToken", "fineGrained"):
            with self.subTest(container=container):
                identity, dataset = fixture()
                target = identity["auth"]
                if container != "auth": target = target["accessToken"]
                if container == "fineGrained": target = target["fineGrained"]
                target["futureGlobalGrants"] = ["user.tokens.write"]
                self.assertFalse(hf.scope_evidence(identity, dataset, dataset["id"])["target_only_scope_evidence"])

    def test_missing_or_malformed_authenticated_identity_is_rejected(self):
        for key, value in (("name", None), ("type", None), ("id", None), ("id", "invalid")):
            with self.subTest(key=key, value=value):
                identity, dataset = fixture()
                identity[key] = value
                self.assertFalse(hf.scope_evidence(identity, dataset, dataset["id"])["target_write_scope_evidence"])

    def test_missing_authorization_schema_is_rejected(self):
        for key in ("global", "canReadGatedRepos", "scoped"):
            identity, dataset = fixture()
            del identity["auth"]["accessToken"]["fineGrained"][key]
            self.assertFalse(hf.scope_evidence(identity, dataset, dataset["id"])["target_only_scope_evidence"])
        identity, dataset = fixture()
        del identity["auth"]["type"]
        self.assertFalse(hf.scope_evidence(identity, dataset, dataset["id"])["target_only_scope_evidence"])

    def test_contradictory_api_dataset_identity_is_rejected(self):
        for key, value in (("name", "different/data"), ("author", "different"),
                           ("authorId", "d" * 24), ("name", []), ("authorId", [])):
            with self.subTest(key=key, value=value):
                identity, dataset = fixture()
                dataset[key] = value
                self.assertFalse(hf.scope_evidence(identity, dataset, dataset["id"])["target_only_scope_evidence"])

    def test_missing_api_object_id_cannot_fall_back_to_a_grant_name(self):
        identity, dataset = fixture()
        del dataset["_id"]
        identity["auth"]["accessToken"]["fineGrained"]["scoped"][0]["entity"].update(
            _id="b" * 24, name=dataset["id"])
        self.assertFalse(hf.scope_evidence(identity, dataset, dataset["id"])["target_only_scope_evidence"])

    def test_malformed_identity_has_no_verified_namespace_permission(self):
        identity, dataset = fixture()
        del identity["id"]
        result = hf.scope_evidence(identity, dataset, dataset["id"])
        self.assertFalse(result["namespace_creation_permission_verified"])
        self.assertFalse(result["target_write_scope_evidence"])

    def test_actual_shape_keeps_empty_own_user_descriptor_and_minimal_repo_write(self):
        identity, dataset = fixture()
        dataset.update(name=dataset["id"], author="test-owner", authorId=identity["id"])
        scoped = identity["auth"]["accessToken"]["fineGrained"]["scoped"]
        scoped[0]["entity"].update(name=dataset["id"], authorId=identity["id"])
        scoped[0]["permissions"] = ["repo.content.read", "repo.access.read", "repo.write"]
        scoped.append({"entity": {"type": "user", "_id": identity["id"], "name": identity["name"]}, "permissions": []})
        result = hf.scope_evidence(identity, dataset, dataset["id"])
        self.assertTrue(result["target_only_scope_evidence"])
        self.assertTrue(result["target_write_scope_evidence"])
        self.assertFalse(result["remote_write_verified"])
        self.assertFalse(result["publication_authorized"])


def synthetic_package():
    package = {name: ("SYNTHETIC:" + name).encode() for name in {*hf.MIRROR_FILES.values(), *hf.CITATION_FILES}}
    package["PREPARED.json"] = json.dumps({"release_id": "SYNTHETIC", "context_contract_version": 1,
        "context_sha256": "0" * 64, "manifest_sha256": "1" * 64,
        "archive_sha256": "2" * 64, "archive_bytes": 1}).encode()
    package["metadata.json"] = b'{"status":"synthetic-prelaunch"}'
    return package


class AnchoredStagingTests(unittest.TestCase):
    """Only synthetic readers/bytes; never load a scientific package or token."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "source"
        self.source.mkdir()
        self.parent = self.base / "outside"
        self.parent.mkdir(mode=0o700)
        self.output = self.parent / "staging"
        self.package = synthetic_package()
        self.report = types.ModuleType("research_report")
        self.report.build_context = lambda _: {"prepared_package": "SYNTHETIC", "policy": {"mode": "prepare_only"}}
        self.citations = types.ModuleType("research_citations")
        self.citations.read_prepared_package = lambda *_: self.package
        self.modules = patch.dict(sys.modules, {"research_report": self.report, "research_citations": self.citations})
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        self.temp.cleanup()

    def test_new_destination_contains_exact_private_offline_bytes(self):
        result = hf.stage(self.source, self.output)
        self.assertEqual(result["network_operations"], 0)
        self.assertFalse(result["publication_authorized"])
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        for destination, source in hf.MIRROR_FILES.items():
            path = self.output / "mirror-staging" / destination
            self.assertEqual(path.read_bytes(), self.package[source])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.source.iterdir()), [])

    def test_destination_created_during_verification_is_not_replaced(self):
        def context(_):
            self.output.mkdir()
            return {"prepared_package": "SYNTHETIC"}
        self.report.build_context = context
        with self.assertRaises(ValueError): hf.stage(self.source, self.output)
        self.assertTrue(self.output.is_dir())
        self.assertEqual(list(self.output.iterdir()), [])

    def test_parent_alias_retarget_during_verification_cannot_write_into_source(self):
        alias = self.base / "alias"
        alias.symlink_to(self.parent, target_is_directory=True)
        def context(_):
            alias.unlink()
            alias.symlink_to(self.source, target_is_directory=True)
            return {"prepared_package": "SYNTHETIC"}
        self.report.build_context = context
        with self.assertRaises(ValueError): hf.stage(self.source, alias / "staging")
        self.assertEqual(list(self.source.iterdir()), [])
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_canonical_parent_replacement_cannot_redirect_anchored_writes(self):
        original = self.base / "original-outside"
        def context(_):
            self.parent.rename(original)
            self.parent.symlink_to(self.source, target_is_directory=True)
            return {"prepared_package": "SYNTHETIC"}
        self.report.build_context = context
        with self.assertRaises(ValueError): hf.stage(self.source, self.output)
        self.assertEqual(list(self.source.iterdir()), [])
        self.assertEqual(list(original.iterdir()), [])

    def test_stable_parent_alias_is_canonicalized_before_no_follow_anchoring(self):
        alias = self.base / "alias"
        alias.symlink_to(self.parent, target_is_directory=True)
        result = hf.stage(self.source, alias / "staging")
        self.assertEqual(result["network_operations"], 0)
        self.assertTrue((self.output / "mirror-staging/README.md").is_file())

    def test_actual_source_directory_identity_overrides_lexical_outside_check(self):
        # Simulate a case/bind alias whose lexical ancestry test missed the source.
        with patch.object(Path, "is_relative_to", return_value=False), self.assertRaises(ValueError):
            hf.stage(self.source, self.source / "would-write")
        self.assertEqual(list(self.source.iterdir()), [])

    def test_copy_failure_retains_incomplete_tree_and_refuses_automatic_reuse(self):
        del self.package["clean-dataset.json"]
        with self.assertRaises(KeyError): hf.stage(self.source, self.output)
        self.assertTrue((self.output / "mirror-staging/README.md").is_file())
        self.assertFalse((self.output / "staging-status.json").exists())
        with self.assertRaises(ValueError): hf.stage(self.source, self.output)
        self.assertEqual(list(self.source.iterdir()), [])

    def test_destination_replaced_while_copying_is_not_modified_or_reported_success(self):
        write = hf._write_new_file
        orphan = self.parent / "original-staging"
        def replace_once(fd, name, blob):
            if not orphan.exists():
                self.output.rename(orphan)
                self.output.mkdir()
                (self.output / "keep.txt").write_text("unrelated")
            return write(fd, name, blob)
        with patch.object(hf, "_write_new_file", side_effect=replace_once), self.assertRaises(ValueError):
            hf.stage(self.source, self.output)
        self.assertEqual((self.output / "keep.txt").read_text(), "unrelated")
        self.assertEqual(list(self.output.iterdir()), [self.output / "keep.txt"])
        self.assertEqual(list(self.source.iterdir()), [])


    def test_replaced_file_is_retained_after_copy_failure(self):
        write = hf._write_new_file
        replacement = self.base / "replacement"
        replacement.write_text("unrelated")
        def replace_before_failure(fd, name, blob):
            if name == "research-archive.zip":
                replacement.replace(self.output / "mirror-staging/README.md")
                raise OSError("synthetic copy failure")
            return write(fd, name, blob)
        with patch.object(hf, "_write_new_file", side_effect=replace_before_failure), self.assertRaises(OSError):
            hf.stage(self.source, self.output)
        self.assertEqual((self.output / "mirror-staging/README.md").read_text(), "unrelated")
        self.assertEqual(list(self.source.iterdir()), [])

    def test_staging_parent_must_already_exist_and_be_private(self):
        for mode in (0o755, 0o770, 0o777):
            with self.subTest(mode=oct(mode)):
                self.parent.chmod(mode)
                with self.assertRaises(ValueError): hf.stage(self.source, self.output)
                self.assertFalse(self.output.exists())
        self.parent.chmod(0o700)
        with self.assertRaises(FileNotFoundError):
            hf.stage(self.source, self.base / "missing-parent/staging")
        self.assertFalse((self.base / "missing-parent").exists())

    def test_staging_parent_must_be_owned_by_current_user(self):
        with patch.object(hf.os, "getuid", return_value=os.getuid() + 1), self.assertRaises(ValueError):
            hf.stage(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_real_directory_replacement_between_mkdir_and_open_is_not_populated(self):
        victim = self.parent / "preexisting-unrelated"
        victim.mkdir(mode=0o700)
        (victim / "keep.txt").write_text("unrelated")
        victim_identity = (victim.stat().st_dev, victim.stat().st_ino)
        original_open = os.open
        fired = False
        def interleave(name, flags, *args, **kwargs):
            nonlocal fired
            if not fired and name == self.output.name and flags & os.O_DIRECTORY and "dir_fd" in kwargs:
                fired = True
                self.output.rename(self.parent / "owned-orphan")
                victim.rename(self.output)
            return original_open(name, flags, *args, **kwargs)
        with patch.object(hf.os, "open", side_effect=interleave), self.assertRaises(ValueError):
            hf.stage(self.source, self.output)
        self.assertTrue(fired)
        self.assertEqual((self.output.stat().st_dev, self.output.stat().st_ino), victim_identity)
        self.assertEqual(list(self.output.iterdir()), [self.output / "keep.txt"])
        self.assertEqual((self.output / "keep.txt").read_text(), "unrelated")
        self.assertEqual(list(self.source.iterdir()), [])

    def test_failed_copy_has_no_cleanup_identity_check_or_destructive_call(self):
        # The independent post-check/pre-unlink injection point is removed.
        victim = self.parent / "preexisting-unrelated-file"
        victim.write_text("unrelated")
        del self.package["clean-dataset.json"]
        original_same = hf._same_entry
        fired = False
        def interleave(fd, name, identity):
            nonlocal fired
            same = original_same(fd, name, identity)
            if name == "README.md" and same:
                fired = True
                victim.replace(self.output / "mirror-staging/README.md")
            return same
        with patch.object(hf, "_same_entry", side_effect=interleave), \
             patch.object(hf.os, "unlink", side_effect=AssertionError("cleanup unlink forbidden")), \
             patch.object(hf.os, "rmdir", side_effect=AssertionError("cleanup rmdir forbidden")), \
             self.assertRaises(KeyError):
            hf.stage(self.source, self.output)
        self.assertFalse(fired)
        self.assertEqual(victim.read_text(), "unrelated")
        self.assertEqual((self.output / "mirror-staging/README.md").read_bytes(), self.package["huggingface-README.md"])

    def test_file_write_error_retains_replacement_without_unlink(self):
        victim = self.parent / "preexisting-unrelated-file"
        victim.write_text("unrelated")
        descriptor = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY)
        def fail_sync(_):
            victim.replace(self.parent / "partial.txt")
            raise OSError("synthetic sync failure")
        try:
            with patch.object(hf.os, "fsync", side_effect=fail_sync), \
                 patch.object(hf.os, "unlink", side_effect=AssertionError("cleanup unlink forbidden")), \
                 self.assertRaises(OSError):
                hf._write_new_file(descriptor, "partial.txt", b"SYNTHETIC")
        finally:
            os.close(descriptor)
        self.assertEqual((self.parent / "partial.txt").read_text(), "unrelated")

    def test_child_directory_replacement_is_not_reported_as_success(self):
        write = hf._write_new_file
        orphan = self.parent / "original-mirror"
        def replace_child(fd, name, blob):
            if name == "staging-status.json":
                (self.output / "mirror-staging").rename(orphan)
                (self.output / "mirror-staging").mkdir()
                (self.output / "mirror-staging/keep.txt").write_text("unrelated")
            return write(fd, name, blob)
        with patch.object(hf, "_write_new_file", side_effect=replace_child), self.assertRaises(ValueError):
            hf.stage(self.source, self.output)
        self.assertEqual((self.output / "mirror-staging/keep.txt").read_text(), "unrelated")
        self.assertEqual(list(self.source.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
