"""ALL-SYNTHETIC publication selection; no actual science or publication credit.

Invented frozen receipts exercise historical trust boundaries only. The public
checkout has no private authoring graph, report, policy, audit or review files.
No current audit, operational/SUT output, raw source, credential or Gold is read.
Full-site fixtures bind the unchanged already-public legacy canonical input;
all research, audit and publication records remain invented synthetic controls.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations
import research_edition_replay as replay
import research_graph as graph_module
import research_report as report_module
from test_research_edition_replay import fixture, reseal, copy_public_site_inputs


def selection(root, entries, current):
    value = {"schema_version": replay.SOURCE_VERSION, "current_release_id": current, "editions": entries}
    (root / replay.SOURCE_SELECTOR).write_bytes(citations.json_bytes(value))
    return value


class PublicResearchSourceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        parent = Path(cls.temporary.name)
        cls.canonical_bytes = (ROOT / "data/canonical.json").read_bytes()
        cls.root, cls.package, cls.current, cls.private_fixture = fixture(
            parent / "current", launch=False, release_id="SYNTHETIC.current.v1",
            legacy_company_id="snorkel_ai", deposition_id=111111112, canonical_bytes=cls.canonical_bytes)
        old_root, old_package, cls.old, _ = fixture(parent / "old", canonical_bytes=cls.canonical_bytes)
        shutil.copytree(old_package, cls.root / old_package.relative_to(old_root))
        registry = json.loads((cls.root / citations.PREPARED_REGISTRY).read_bytes())
        registry["packages"] += json.loads((old_root / citations.PREPARED_REGISTRY).read_bytes())["packages"]
        (cls.root / citations.PREPARED_REGISTRY).write_bytes(citations.json_bytes(registry))
        cls.entries = []
        for descriptor in (cls.current, cls.old):
            path = cls.root / "data/research/editions" / (descriptor["release_id"] + ".json")
            receipt = replay.export_published_edition(cls.root, descriptor["release_id"],
                descriptor["archive_receipt"], path)
            cls.entries.append({"release_id": descriptor["release_id"], "status": "published",
                "snapshot_path": path.relative_to(cls.root / "data/research").as_posix(),
                "snapshot_sha256": receipt["snapshot_sha256"]})
        # Only public packages, descriptors and their source selection survive.
        for path in (cls.root / "data/research").iterdir():
            if path.name not in {"releases", "editions", "prepared-packages.json"}:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        cls.selector = selection(cls.root, cls.entries, cls.current["release_id"])

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def copy_source(self, directory):
        root = Path(directory) / "public-source"
        shutil.copytree(self.root, root)
        return root

    def public_checkout(self, directory):
        return copy_public_site_inputs(self.copy_source(directory))

    def forbid_private(self):
        return (patch.object(graph_module, "load_graph", side_effect=AssertionError("No private graph")),
                patch.object(report_module, "load_report", side_effect=AssertionError("No private report")),
                patch.object(report_module, "publication_gate", side_effect=AssertionError("No fresh gate")))

    def test_unpatched_context_selects_explicit_current_with_private_inputs_absent(self):
        before = {str(p.relative_to(self.root)): p.read_bytes()
                  for p in (self.root / "data/research/releases").rglob("*") if p.is_file()}
        for select_prepared in (True, False):
            graph, report, gate = self.forbid_private()
            with graph, report, gate, patch("urllib.request.urlopen", side_effect=AssertionError("No network")):
                context = report_module.build_context(self.root, select_prepared=select_prepared)
                self.assertEqual(replay.edition_entries(context), self.entries)
                replay.read_replay_package(context)
            self.assertEqual(context["report"]["release_id"], self.current["release_id"])
            self.assertEqual(context["report"]["editions"], [])
            self.assertEqual(set(context["edition_snapshots"]), {self.current["release_id"], self.old["release_id"]})
            self.assertEqual(context["policy"]["mode"], "replay_only")
            self.assertEqual(context["gate"]["status"], "published_frozen_replay")
            self.assertTrue(context["gate"]["ready"])
            self.assertFalse(context["gate"]["archival_ready"])
            self.assertFalse(context["replay_verification"]["current_input_readiness_revalidated"])
            self.assertFalse(context["replay_verification"]["raw_sources_revalidated"])
            self.assertFalse(context["replay_verification"]["live_private_withheld_records_revalidated"])
            self.assertNotEqual(report_module.canonical_hash(context["graph"]),
                context["replay_verification"]["original_scientific_graph_sha256"])
            self.assertEqual(context["replay_verification"]["original_scientific_graph_sha256"],
                report_module.canonical_hash(self.private_fixture["graph"]))
            self.assertTrue(all(a["status"] in {"approved", "historical"} for a in context["graph"]["assertions"]))
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
            for p in (self.root / "data/research/releases").rglob("*") if p.is_file()})

    def test_absent_selector_preserves_private_authoring_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(graph_module, "load_graph", side_effect=RuntimeError("ordinary private loader")) as load:
                with self.assertRaisesRegex(RuntimeError, "ordinary private loader"):
                    report_module.build_context(Path(temporary))
                load.assert_called_once()

    def test_selector_shape_identity_duplicate_and_inline_override_controls(self):
        cases = [None, [], {}, {**self.selector, "schema_version": 1},
                 {**self.selector, "current_release_id": "SYNTHETIC.missing"},
                 {**self.selector, "current_release_id": True},
                 {**self.selector, "gate": {"ready": True}},
                 {**self.selector, "editions": []},
                 {**self.selector, "editions": self.entries + [self.entries[0]]}]
        for field, value in (("status", "prepared"), ("snapshot_sha256", "a" * 63),
                             ("snapshot_sha256", "a" * 64), ("revision", True), ("revision", 0),
                             ("graph", {}), ("report", {}), ("archive_receipt", {}),
                             ("snapshot_path", "/tmp/descriptor.json"),
                             ("snapshot_path", "editions/../releases/descriptor.json"),
                             ("snapshot_path", "editions//descriptor.json")):
            entries = copy.deepcopy(self.entries)
            entries[0][field] = value
            cases.append({**self.selector, "editions": entries})
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_source(temporary)
            for value in cases:
                with self.subTest(value=value):
                    (root / replay.SOURCE_SELECTOR).write_bytes(citations.json_bytes(value))
                    graph, report, gate = self.forbid_private()
                    with graph, report, gate, self.assertRaises(ValueError):
                        report_module.build_context(root, select_prepared=False)
            (root / replay.SOURCE_SELECTOR).write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                report_module.build_context(root)

    def test_selector_and_descriptor_symlinks_directories_and_changed_bytes_hold(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_source(temporary)
            path = root / replay.SOURCE_SELECTOR
            path.unlink()
            path.symlink_to(root / "missing-selector.json")
            with self.assertRaisesRegex(ValueError, "symlink"):
                report_module.build_context(root)
            path.unlink()
            path.mkdir()
            with self.assertRaisesRegex(ValueError, "regular JSON"):
                report_module.build_context(root)
            path.rmdir()
            selection(root, self.entries, self.current["release_id"])
            descriptor = root / "data/research" / self.entries[0]["snapshot_path"]
            descriptor.write_bytes(descriptor.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "digest differs"):
                report_module.build_context(root)
            descriptor.unlink()
            descriptor.symlink_to(root / "missing-descriptor.json")
            with self.assertRaisesRegex(ValueError, "symlink"):
                report_module.build_context(root)

    def test_public_ledger_and_hydrated_facts_cannot_be_mutated_for_rendering(self):
        context = report_module.build_context(self.root)
        for field in (replay.SOURCE_MARKER, replay.SOURCE_LEDGER, "edition_snapshots", "report", "gate"):
            with self.subTest(field=field):
                changed = copy.deepcopy(context)
                changed[field] = {} if isinstance(changed[field], dict) else []
                with self.assertRaises((ValueError, KeyError)):
                    replay.edition_entries(changed)

    def test_deleting_both_public_context_keys_cannot_hide_physical_source_history(self):
        import research_pages as pages

        context = report_module.build_context(self.root)
        del context[replay.SOURCE_MARKER]
        del context[replay.SOURCE_LEDGER]
        # The coherent frozen current core still verifies on its own. The
        # physical source selector nevertheless requires its complete ledger.
        replay.read_replay_package(context)
        with patch.object(report_module, "publication_gate", side_effect=AssertionError("No fresh gate")):
            for read in (replay.edition_entries, pages._published_editions):
                with self.subTest(read=read), self.assertRaisesRegex(ValueError, "selection or verified edition ledger"):
                    read(context)

    def test_valid_historical_core_cannot_replace_explicit_source_current(self):
        import research_pages as pages

        context = report_module.build_context(self.root)
        changed = copy.deepcopy(context)
        historical = context["edition_snapshots"][self.old["release_id"]]
        changed.update(copy.deepcopy(historical))
        self.assertEqual(changed[replay.SOURCE_MARKER], context[replay.SOURCE_MARKER])
        self.assertEqual(changed[replay.SOURCE_LEDGER], context[replay.SOURCE_LEDGER])
        self.assertEqual(changed["edition_snapshots"], context["edition_snapshots"])
        self.assertNotEqual(changed["report"]["release_id"], context["report"]["release_id"])
        # This is a valid historical capsule, not a corrupted or invented one.
        replay.read_replay_package(changed)
        with patch.object(report_module, "publication_gate", side_effect=AssertionError("No fresh gate")):
            for read in (replay.edition_entries, pages._published_editions):
                with self.subTest(read=read), self.assertRaisesRegex(ValueError, "selection or verified edition ledger"):
                    read(changed)

    def test_no_selector_allows_private_ledger_or_verified_standalone_replay_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_source(temporary)
            (root / replay.SOURCE_SELECTOR).unlink()
            private_entries = [{"release_id": "SYNTHETIC.authoring-history", "status": "prepared"}]
            private = {"root": root, "policy": {"mode": "prepare_only"}, "report": {"editions": private_entries}}
            self.assertEqual(replay.edition_entries(private), private_entries)
            standalone = replay.load_published_edition(root, self.current)
            with patch.object(report_module, "publication_gate", side_effect=AssertionError("No fresh gate")):
                self.assertEqual(replay.edition_entries(standalone), [])
                for field in (replay.MARKER, "replay_verification", "policy"):
                    broken = copy.deepcopy(standalone)
                    broken.pop(field)
                    with self.subTest(field=field), self.assertRaises(ValueError):
                        replay.edition_entries(broken)
            source_context = report_module.build_context(self.root)
            source_context["root"] = root
            with self.assertRaisesRegex(ValueError, "selection or verified edition ledger"):
                replay.edition_entries(source_context)

    def test_explicit_current_is_independent_of_ledger_order_or_latest_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_source(temporary)
            selection(root, list(reversed(self.entries)), self.old["release_id"])
            context = report_module.build_context(root)
            self.assertEqual(context["report"]["release_id"], self.old["release_id"])
            self.assertEqual(context["report"]["edition_date"], "2026-11-12")

    def test_distinct_verified_releases_cannot_claim_one_immutable_route(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_source(temporary)
            other_root, package, descriptor, _ = fixture(Path(temporary) / "collision", launch=False,
                release_id="SYNTHETIC.colliding.v1", deposition_id=111111113, canonical_bytes=self.canonical_bytes)
            shutil.copytree(package, root / package.relative_to(other_root))
            registry = json.loads((root / citations.PREPARED_REGISTRY).read_bytes())
            registry["packages"] += json.loads((other_root / citations.PREPARED_REGISTRY).read_bytes())["packages"]
            (root / citations.PREPARED_REGISTRY).write_bytes(citations.json_bytes(registry))
            path = root / "data/research/editions/collision.json"
            receipt = replay.export_published_edition(root, descriptor["release_id"], descriptor["archive_receipt"], path)
            entry = {"release_id": descriptor["release_id"], "status": "published",
                "snapshot_path": "editions/collision.json", "snapshot_sha256": receipt["snapshot_sha256"]}
            selection(root, self.entries + [entry], self.current["release_id"])
            with self.assertRaisesRegex(ValueError, "immutable URL"):
                report_module.build_context(root)

    def test_normal_source_selection_does_not_bypass_receipt_registry_or_acceptance(self):
        mutations = [lambda d: d.update(extra="unapproved descriptor override"),
                     lambda d: d["archive_receipt"].update(verified=False),
                     lambda d: d["archive_receipt"].update(environment="sandbox"),
                     lambda d: d["archive_receipt"].update(artifact_sha256="a" * 64)]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_source(temporary)
                descriptor = copy.deepcopy(self.current)
                mutate(descriptor)
                entry = copy.deepcopy(self.entries[0])
                path = root / "data/research" / entry["snapshot_path"]
                path.write_bytes(citations.json_bytes(descriptor))
                entry["snapshot_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                selection(root, [entry, self.entries[1]], self.current["release_id"])
                with self.assertRaises(ValueError):
                    report_module.build_context(root)
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_source(temporary)
            (root / citations.PREPARED_REGISTRY).unlink()
            with self.assertRaisesRegex(ValueError, "registry"):
                report_module.build_context(root)
        for mutate in (lambda s, f: s["gate"].update(archival_ready=False),
                       lambda s, f: s["gate"]["thresholds"].update(reviewed_papers=0),
                       lambda s, f: s["graph"]["assertions"][0].update(status="candidate")):
            with self.subTest(acceptance=mutate), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_source(temporary)
                descriptor = copy.deepcopy(self.current)
                package = root / descriptor["package_path"]
                reseal(root, package, descriptor, mutate)
                # reseal's synthetic attacker replaces registry with current only.
                entry = copy.deepcopy(self.entries[0])
                blob = citations.json_bytes(descriptor)
                (root / "data/research" / entry["snapshot_path"]).write_bytes(blob)
                entry["snapshot_sha256"] = citations.sha256(blob)
                selection(root, [entry], descriptor["release_id"])
                with self.assertRaises(ValueError):
                    report_module.build_context(root)

    def test_full_clean_public_checkout_builds_current_history_search_company_and_citations(self):
        """Import actual source from a public-only checkout; do not patch the loader."""
        with tempfile.TemporaryDirectory() as temporary:
            root = self.public_checkout(temporary)
            output = Path(temporary) / "site"
            before = {str(p.relative_to(root)): p.read_bytes()
                      for p in (root / "data/research").rglob("*") if p.is_file()}
            script = textwrap.dedent('''
                import builtins, io, json, os, socket, sys, urllib.request
                from pathlib import Path
                from unittest.mock import patch
                root, output = Path(sys.argv[1]), Path(sys.argv[2])
                sys.path.insert(0, str(root / 'scripts'))
                import observatory, build_public_snapshot, research_report, research_graph, research_citations, research_edition_replay
                research = root / 'data/research'
                original_open, original_io = builtins.open, io.open
                opened = []
                def guarded(original, path, mode='r', *args, **kwargs):
                    if isinstance(path, (str, bytes, os.PathLike)):
                        file = Path(os.fsdecode(path)).absolute()
                        if file.is_relative_to(research):
                            relative = file.relative_to(research)
                            if relative.parts[0] not in {'releases', 'editions', 'prepared-packages.json', 'published-source.json'}:
                                raise AssertionError('Private input opened: ' + str(relative))
                            if any(c in mode for c in 'wax+'):
                                raise AssertionError('Public capsule writer opened: ' + str(relative))
                            opened.append(str(relative))
                    return original(path, mode, *args, **kwargs)
                def forbidden(*args, **kwargs):
                    raise AssertionError('No network, private loader, fresh gate, freeze or publication export')
                with patch('builtins.open', side_effect=lambda *a, **k: guarded(original_open, *a, **k)), \\
                     patch('io.open', side_effect=lambda *a, **k: guarded(original_io, *a, **k)), \\
                     patch.object(urllib.request, 'urlopen', side_effect=forbidden), \\
                     patch.object(socket.socket, 'connect', side_effect=forbidden), \\
                     patch.object(socket, 'create_connection', side_effect=forbidden), \\
                     patch.object(research_graph, 'load_graph', side_effect=forbidden), \\
                     patch.object(research_report, 'load_report', side_effect=forbidden), \\
                     patch.object(research_report, 'publication_gate', side_effect=forbidden), \\
                     patch.object(research_citations, 'freeze_publication_package', side_effect=forbidden), \\
                     patch.object(research_edition_replay, 'export_published_edition', side_effect=forbidden):
                    context = research_report.build_context(root)
                    assert context['report']['editions'] == []
                    sys.argv = ['build_public_snapshot.py', '--output', str(output)]
                    build_public_snapshot.main()
                print(json.dumps({'capsule_reads': len(opened), 'private_input_opens': 0,
                                  'network_calls': 0, 'capsule_writes': 0}))
            ''')
            done = subprocess.run([sys.executable, "-c", script, str(root), str(output)], cwd=root,
                capture_output=True, text=True, timeout=180,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertGreater(json.loads(done.stdout.splitlines()[-1])["capsule_reads"], 0)
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes()
                for p in (root / "data/research").rglob("*") if p.is_file()})
            current = report_module.build_context(root)
            self.assertEqual(json.loads((output / "CITATION.cff").read_bytes())["doi"], self.current["archive_receipt"]["doi"])
            self.assertEqual((output / "publication/CITATION.cff").read_bytes(), (root / self.current["package_path"] / "CITATION.cff").read_bytes())
            for name, blob in replay.read_replay_package(current).items():
                self.assertEqual((output / "publication" / name).read_bytes(), blob, name)
            routes = []
            for base, snapshot in [("/research/state-of-ai-data-labs/", current)] + [
                    ("/research/editions/" + context["report"]["edition_date"] + "/", context)
                    for context in current["edition_snapshots"].values()]:
                for index, chapter in enumerate(snapshot["report"]["sections"]):
                    route = base if index == 0 else base + "chapters/" + chapter["id"] + "/"
                    text = (output / route.lstrip("/") / "index.html").read_text()
                    self.assertIn(chapter["paragraphs"][0]["text"], text)
                    if base.startswith("/research/editions/"):
                        self.assertIn(snapshot["report"]["archive"]["record_url"], text)
                    self.assertIn('href="https://sciencetostartup.com' + route + '"', text)
                    routes.append(route)
                self.assertEqual(len(snapshot["report"]["sections"]), 12)
            self.assertEqual(len(routes), 36)
            for name, tag in (("feed.xml", "item"), ("atom.xml", "{http://www.w3.org/2005/Atom}entry")):
                feed = ET.parse(output / "research" / name)
                self.assertEqual(len(feed.findall(".//" + tag)), 2)
                for descriptor in (self.current, self.old):
                    self.assertIn(descriptor["release_id"], (output / "research" / name).read_text())
            manifest = json.loads((output / "manifest.json").read_text())
            summary = json.loads((output / manifest["summary"]["href"].lstrip("/")).read_text())
            search = json.loads((output / summary["homeSearch"]["href"].lstrip("/")).read_text())
            for route in routes[:12]:
                self.assertTrue(any(row["href"] == route for row in search["entries"]), route)
            self.assertIn(self.current["release_id"], (output / "research/index.html").read_text())
            self.assertIn(self.old["release_id"], (output / "research/index.html").read_text())
            self.assertIn("/research/", (output / "index.html").read_text())
            bridge = (output / "company/snorkel_ai/index.html").read_text()
            self.assertIn('id="new-research-evidence"', bridge)
            self.assertIn("Synthetic fixture observation, never research or review evidence.", bridge)
            sitemap = (output / "sitemap.xml").read_text()
            for route in routes + ["/company/snorkel_ai/"]:
                self.assertIn("https://sciencetostartup.com" + route, sitemap)
            self.assertEqual((root / "data/canonical.json").read_bytes(), (ROOT / "data/canonical.json").read_bytes())

    def test_public_cli_rejects_raw_canonical_whitespace_drift_after_capsule_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.public_checkout(temporary)
            # The source-owned capsule is valid before and after this edit.
            before = report_module.build_context(root)
            self.assertEqual(before["graph"]["canonical_sha256"], citations.sha256(self.canonical_bytes))
            canonical = root / "data/canonical.json"
            canonical.write_bytes(self.canonical_bytes + b" \n")
            self.assertEqual(json.loads(canonical.read_bytes()), json.loads(self.canonical_bytes))
            self.assertEqual(report_module.build_context(root)["report"], before["report"])
            output = Path(temporary) / "held-site"
            done = subprocess.run([sys.executable, str(root / "scripts/build_public_snapshot.py"),
                "--output", str(output)], cwd=root, capture_output=True, text=True, timeout=180,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertNotEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("Research graph canonical bytes or dataset version differ", done.stderr)
            self.assertFalse((output / "manifest.json").exists())
            self.assertFalse((output / "presentation").exists())
            self.assertFalse((output / "research").exists())


if __name__ == "__main__":
    unittest.main()
