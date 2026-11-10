"""Pinned approval intake; every source and review here is a synthetic fixture."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_graph as rg
from test_research_graph import entity, fixture


class ResearchPartitionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.research = self.root / "data/research"
        self.research.mkdir(parents=True)
        self.approved = self.research / "approved"
        self.canonical = rg.stable_json({"dataset_version": "2.5.0", "companies": []}).encode()
        (self.root / "data/canonical.json").write_bytes(self.canonical)
        self.graph = fixture()
        self.graph["canonical_sha256"] = rg.digest(self.canonical)
        self.write_base(self.graph)

    def write_base(self, graph):
        (self.research / "graph.json").write_text(rg.stable_json(graph), encoding="utf-8")

    def write_index(self, entries):
        self.approved.mkdir(parents=True, exist_ok=True)
        (self.approved / "index.json").write_text(rg.stable_json({
            "schema_version": "1.0.0", "partitions": entries}), encoding="utf-8")

    def install(self, parts):
        entries = []
        for name, value in parts:
            target = self.approved / name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = rg.stable_json(value).encode()
            target.write_bytes(content)
            entries.append({"path": name, "sha256": rg.digest(content)})
        self.write_index(entries)

    def split(self, graph=None):
        graph = copy.deepcopy(graph if graph is not None else self.graph)
        base = copy.deepcopy(graph)
        for table in ("assertions", "sources", "reviews"):
            base[table] = []
        self.write_base(base)
        self.install([(name, {"schema_version": "1.0.0", table: graph[table]})
                      for name, table in (("01-assertions.json", "assertions"),
                                          ("02-reviews.json", "reviews"),
                                          ("03-sources.json", "sources"))])
        return graph

    def test_absent_index_preserves_graph_and_all_export_bytes(self):
        loaded = rg.load_graph(self.root)
        self.assertEqual(loaded, self.graph)
        self.assertEqual(rg.load_partition_records(self.root), {
            "entities": [], "sources": [], "assertions": [], "reviews": []})
        left, right = self.root / "before", self.root / "after"
        names = rg.write_exports(self.graph, left)
        self.assertEqual(rg.write_exports(loaded, right), names)
        for name in names:
            self.assertEqual((left / name).read_bytes(), (right / name).read_bytes(), name)

    def test_empty_index_and_unlisted_candidate_files_do_not_add_records(self):
        self.write_index([])
        (self.approved / "unlisted.json").write_text('{"status":"candidate"}')
        output = self.root / "output/research-candidates"
        output.mkdir(parents=True)
        (output / "candidate.json").write_text('{"status":"candidate"}')
        self.assertEqual(rg.load_graph(self.root), self.graph)

    def test_base_registry_and_forward_cross_partition_references_merge_before_validation(self):
        expected = self.split()
        loaded = rg.load_graph(self.root)
        self.assertEqual(loaded, expected)
        self.assertEqual(rg.coverage_summary(loaded)["reviewed_papers"], 1)
        self.assertEqual(loaded["entities"][0]["assertion_ids"], ["claim"])
        self.assertEqual(set(loaded), rg.ROOT_FIELDS)

    def test_partition_entities_append_and_source_root_metadata_stays_authoritative(self):
        expected = self.split()
        workflow = entity("workflow", "workflow", assertion_ids=[])
        self.install([
            ("01-assertions.json", {"schema_version": "1.0.0", "assertions": expected["assertions"]}),
            ("02-entities.json", {"schema_version": "1.0.0", "entities": [workflow]}),
            ("03-reviews.json", {"schema_version": "1.0.0", "reviews": expected["reviews"]}),
            ("04-sources.json", {"schema_version": "1.0.0", "sources": expected["sources"]}),
        ])
        loaded = rg.load_graph(self.root)
        self.assertEqual(loaded["entities"], expected["entities"] + [workflow])
        for field in rg.ROOT_FIELDS - set(rg.PARTITION_TABLES):
            self.assertEqual(loaded[field], expected[field], field)

    def test_optional_delivery_and_purpose_facets_survive_partition_merge_and_export(self):
        self.assertEqual(set(self.graph["entities"][0]["taxonomy"]), rg.FACETS)
        rg.load_graph(self.root)
        for facets in ({"delivery_model": ["managed_service"]},
                       {"data_purpose": ["training", "evaluation"]},
                       {"delivery_model": [], "data_purpose": []}):
            with self.subTest(facets=facets):
                graph = copy.deepcopy(self.graph)
                graph["entities"][0]["taxonomy"].update(facets)
                base = copy.deepcopy(graph)
                base["entities"] = []
                self.write_base(base)
                self.install([("01-entities.json", {"schema_version": "1.0.0", "entities": graph["entities"]})])
                loaded = rg.load_graph(self.root)
                self.assertEqual(loaded["entities"][0]["taxonomy"], graph["entities"][0]["taxonomy"])
                projected = rg.public_graph(loaded)
                self.assertEqual(projected["entities"][0]["taxonomy"], graph["entities"][0]["taxonomy"])

    def test_optional_facets_do_not_relax_required_names_or_string_list_types(self):
        for name in ("delivery_model", "data_purpose"):
            for value in (None, "training", [1], [True], [""], [" "], ["same", "same"]):
                with self.subTest(facet=name, value=value):
                    graph = copy.deepcopy(self.graph)
                    graph["entities"][0]["taxonomy"][name] = value
                    self.write_base(graph)
                    with self.assertRaisesRegex(rg.GraphValidationError, "taxonomy/" + name):
                        rg.load_graph(self.root)
        graph = copy.deepcopy(self.graph)
        graph["entities"][0]["taxonomy"].update(delivery_model=[], data_purpose=[])
        for name in rg.FACETS:
            changed = copy.deepcopy(graph)
            del changed["entities"][0]["taxonomy"][name]
            self.write_base(changed)
            with self.subTest(required=name), self.assertRaisesRegex(rg.GraphValidationError, "fields must be exactly"):
                rg.load_graph(self.root)
        graph["entities"][0]["taxonomy"]["unrecognized_facet"] = []
        self.write_base(graph)
        with self.assertRaisesRegex(rg.GraphValidationError, "fields must be exactly"):
            rg.load_graph(self.root)

    def test_merged_export_is_deterministic_and_loads_without_partition_files(self):
        self.split()
        first, second = self.root / "first", self.root / "second"
        names = rg.write_exports(rg.load_graph(self.root), first)
        rg.write_exports(rg.load_graph(self.root), second)
        for name in names:
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)
        standalone = self.root / "standalone"
        (standalone / "data/research").mkdir(parents=True)
        exported = (first / "research-graph.json").read_bytes()
        (standalone / "data/research/graph.json").write_bytes(exported)
        (standalone / "data/canonical.json").write_bytes(self.canonical)
        self.assertEqual(rg.load_graph(standalone), json.loads(exported))
        self.assertEqual(len(rg.load_graph(standalone)["reviews"]), 3)

    def test_nonapproved_assertions_are_rejected_even_with_three_passing_receipts(self):
        for status in ("candidate", "quarantined", "rejected", "historical"):
            with self.subTest(status=status):
                graph = copy.deepcopy(self.graph)
                graph["assertions"][0]["status"] = status
                self.split(graph)
                with self.assertRaisesRegex(rg.GraphValidationError, "only approved assertions"):
                    rg.load_graph(self.root)

    def test_partitioning_preserves_exact_review_and_source_gates(self):
        for change, message in (("wording", "reviewed assertion content changed"),
                                ("missing_role", "approval requires actual"),
                                ("same_invocation", "one invocation"),
                                ("chronology", "review precedes"),
                                ("metadata", "approved assertion cannot use metadata")):
            with self.subTest(change=change):
                graph = copy.deepcopy(self.graph)
                if change == "wording":
                    graph["assertions"][0]["value"]["value"] += " Unreviewed change."
                elif change == "missing_role":
                    graph["assertions"][0]["review_ids"].remove("adversarial")
                    graph["reviews"] = [r for r in graph["reviews"] if r["role"] != "adversarial"]
                elif change == "same_invocation":
                    for review in graph["reviews"]:
                        review["invocation_id"] = "synthetic-single-invocation"
                elif change == "chronology":
                    graph["reviews"][0]["reviewed_on"] = "2026-11-01T00:00:00Z"
                else:
                    graph["sources"][0].update(status="metadata_only", source_type="metadata")
                self.split(graph)
                with self.assertRaisesRegex(rg.GraphValidationError, message):
                    rg.load_graph(self.root)

    def test_unknown_references_and_canonical_byte_drift_still_fail(self):
        graph = copy.deepcopy(self.graph)
        graph["assertions"][0]["subject_id"] = "missing-work"
        self.split(graph)
        with self.assertRaisesRegex(rg.GraphValidationError, "unknown subject"):
            rg.load_graph(self.root)
        self.split()
        (self.root / "data/canonical.json").write_bytes(self.canonical + b"\n")
        with self.assertRaisesRegex(rg.GraphValidationError, "canonical bytes"):
            rg.load_graph(self.root)

    def test_duplicate_ids_fail_within_parts_between_parts_and_against_base(self):
        source = self.graph["sources"][0]
        for parts in ([
            ("01.json", {"schema_version": "1.0.0", "sources": [source, source]})], [
            ("01.json", {"schema_version": "1.0.0", "sources": [source]}),
            ("02.json", {"schema_version": "1.0.0", "sources": [source]})], [
            ("01.json", {"schema_version": "1.0.0", "sources": [source]})]):
            with self.subTest(parts=len(parts), rows=len(parts[0][1]["sources"])):
                self.install(parts)
                with self.assertRaisesRegex(rg.GraphValidationError, "duplicate id"):
                    rg.load_graph(self.root)
        same_id = copy.deepcopy(source)
        same_id["id"] = "paper"
        self.install([("01.json", {"schema_version": "1.0.0", "sources": [same_id]})])
        with self.assertRaisesRegex(rg.GraphValidationError, "duplicate id paper"):
            rg.load_graph(self.root)

    def test_partition_index_and_rows_require_explicit_deterministic_order(self):
        self.install([("02.json", {"schema_version": "1.0.0"}),
                      ("01.json", {"schema_version": "1.0.0"})])
        with self.assertRaisesRegex(rg.GraphValidationError, "paths must be unique and strictly sorted"):
            rg.load_graph(self.root)
        self.install([("01.json", {"schema_version": "1.0.0", "entities": [
            entity("z-workflow", "workflow", assertion_ids=[]),
            entity("a-workflow", "workflow", assertion_ids=[])]})])
        with self.assertRaisesRegex(rg.GraphValidationError, "strictly sorted by stable id"):
            rg.load_graph(self.root)
        content = {"schema_version": "1.0.0"}
        self.install([("01.json", content), ("01.json", content)])
        with self.assertRaisesRegex(rg.GraphValidationError, "paths must be unique"):
            rg.load_graph(self.root)

    def test_exact_pinned_bytes_missing_files_and_invalid_digests_fail(self):
        self.split()
        path = self.approved / "01-assertions.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(rg.GraphValidationError, "pinned SHA256 mismatch"):
            rg.load_graph(self.root)
        for expected in (None, "f" * 63, "F" * 64):
            with self.subTest(digest=expected):
                self.write_index([{"path": "missing.json", "sha256": expected}])
                with self.assertRaisesRegex(rg.GraphValidationError, "invalid exact SHA256"):
                    rg.load_graph(self.root)
        self.write_index([{"path": "missing.json", "sha256": "f" * 64}])
        with self.assertRaisesRegex(rg.GraphValidationError, "expected file inside"):
            rg.load_graph(self.root)

    def test_path_escape_and_ambiguous_paths_are_rejected(self):
        outside = self.research / "outside.json"
        outside.write_text('{"schema_version":"1.0.0"}')
        for name in ("../outside.json", str(outside), "./outside.json", "nested//part.json",
                     "nested/../outside.json", "nested\\part.json"):
            with self.subTest(path=name):
                self.write_index([{"path": name, "sha256": rg.digest(outside.read_bytes())}])
                with self.assertRaisesRegex(rg.GraphValidationError, "canonical relative POSIX path"):
                    rg.load_graph(self.root)

    def test_symlinked_partition_parent_index_and_approved_directory_are_rejected(self):
        target = self.research / "outside.json"
        target.write_text('{"schema_version":"1.0.0"}')
        self.approved.mkdir()
        (self.approved / "link.json").symlink_to(target)
        self.write_index([{"path": "link.json", "sha256": rg.digest(target.read_bytes())}])
        with self.assertRaisesRegex(rg.GraphValidationError, "symlinks forbidden"):
            rg.load_graph(self.root)
        (self.approved / "nested").symlink_to(self.research, target_is_directory=True)
        self.write_index([{"path": "nested/outside.json", "sha256": rg.digest(target.read_bytes())}])
        with self.assertRaisesRegex(rg.GraphValidationError, "symlinks forbidden"):
            rg.load_graph(self.root)
        index = self.approved / "index.json"
        external_index = self.research / "external-index.json"
        index.rename(external_index)
        index.symlink_to(external_index)
        with self.assertRaisesRegex(rg.GraphValidationError, "symlinks forbidden"):
            rg.load_graph(self.root)
        index.unlink()
        external_index.write_text(rg.stable_json({"schema_version": "1.0.0", "partitions": []}))
        external_index.rename(index)
        destination = self.research / "other-approved"
        self.approved.rename(destination)
        self.approved.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(rg.GraphValidationError, "symlinks forbidden"):
            rg.load_graph(self.root)

    def test_unknown_fields_and_unsupported_schemas_fail_at_all_input_levels(self):
        self.write_index([])
        index = self.approved / "index.json"
        for value in ({"schema_version": "1.0.0", "partitions": [], "release_id": "override"},
                      {"schema_version": 1, "partitions": []},
                      {"schema_version": "1.0.0", "partitions": [{"path": "x", "sha256": "f" * 64, "extra": True}]}):
            with self.subTest(index=value):
                index.write_text(rg.stable_json(value))
                with self.assertRaises(rg.GraphValidationError):
                    rg.load_graph(self.root)
        for value in ({"schema_version": "1.0.0", "coverage": {}},
                      {"schema_version": "1.0.0", "release_id": "override"},
                      {"schema_version": "2.0.0"}, {"entities": []},
                      {"schema_version": "1.0.0", "sources": None}):
            with self.subTest(partition=value):
                self.install([("01.json", value)])
                with self.assertRaises(rg.GraphValidationError):
                    rg.load_graph(self.root)
        for table in rg.PARTITION_TABLES:
            row = copy.deepcopy(self.graph[table][0])
            row["extra"] = "not in the contract"
            self.install([("01.json", {"schema_version": "1.0.0", table: [row]})])
            with self.subTest(table=table), self.assertRaisesRegex(rg.GraphValidationError, "fields must be exactly"):
                rg.load_graph(self.root)

    def test_malformed_json_duplicate_keys_and_nonfinite_values_fail_closed(self):
        for content in (b'{"schema_version":"1.0.0",',
                        b'{"schema_version":"bad","schema_version":"1.0.0"}',
                        b'{"schema_version":"1.0.0","assertions":NaN}', b"\xff"):
            with self.subTest(content=content):
                self.approved.mkdir(exist_ok=True)
                (self.approved / "01.json").write_bytes(content)
                self.write_index([{"path": "01.json", "sha256": rg.digest(content)}])
                with self.assertRaisesRegex(rg.GraphValidationError, "invalid JSON"):
                    rg.load_graph(self.root)


if __name__ == "__main__":
    unittest.main()
