"""Invented offline fixtures ONLY; no DOI, reviewer or publication is real.

Simulated accepted admissions reach semantic negative controls. These temporary
packages are never source research, real audit executions, or publishable work.
No current research graph, audit, admission, checker output or source is read.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import research_citations as citations
import research_edition_replay as replay
import research_graph as rg
import research_pages as pages
import research_report as report_module
from test_reference_audit_v3 import fixture as reference_fixture, simulated_trust
from test_screening_audit_v2 import fixture as screening_fixture, simulated_admitted
from test_research_graph import entity


def fixture(directory, *, reference_version=3, screening_version=3, launch=True, reference_original_differs=False,
            routing_literals=False, release_id=None, legacy_company_id=None, deposition_id=111111111,
            canonical_bytes=None):
    """Construct independent synthetic science with the real unchanged floors."""
    if reference_version == 4:
        from test_reference_audit_v4 import fixture_only, simulated_trust as trust
        reference, graph, _, _ = fixture_only()
    else:
        reference, graph = reference_fixture()
        trust = simulated_trust
    canonical = {"dataset_version": "2.5.0", "companies": []}
    if canonical_bytes is not None:
        # Only the already-public legacy input is real. Bind it before any
        # synthetic audit, synthesis review or frozen-package commitments.
        canonical = json.loads(canonical_bytes)
        graph["canonical_sha256"] = citations.sha256(canonical_bytes)
        graph["canonical_dataset_version"] = canonical["dataset_version"]
    if release_id is not None:
        graph["release_id"] = reference["release_id"] = release_id
    graph["as_of"] = "2026-11-16T18:00:00Z"
    if routing_literals:
        graph['sources'][0].update(url='https://example.org/research/data/frozen-source',
                                   title='Literal /research/data/#quoted-source-title')
    template = copy.deepcopy(graph["assertions"][0])
    for kind, count in (("supplier", 60), ("paper", 149), ("dataset_family", 60), ("benchmark_family", 20)):
        for i in range(count):
            identifier = f"SYNTHETIC.{kind}.{i}"
            claim = copy.deepcopy(template)
            claim.update(id=identifier + ".claim", subject_id=identifier, review_ids=[])
            claim["predicate"] = "has_capability" if kind == "supplier" else "documents"
            claim["value"]["value"] = "Synthetic fixture observation, never research or review evidence."
            graph["assertions"].append(claim)
            options = {"assertion_ids": [claim["id"]], "identifiers": {}, "eligible_core": True}
            if kind == "supplier" and i < 39:
                options["legacy_id"] = legacy_company_id if i == 0 and legacy_company_id else "synthetic-legacy-" + str(i)
            if kind.endswith("family"):
                options["family_id"] = identifier
            if kind == "paper":
                options["identifiers"] = {"arxiv": f"2601.{i + 10000}"}
            graph["entities"].append(entity(identifier, kind=kind, **options))
            for role in sorted(rg.REVIEW_ROLES):
                rid = identifier + "." + role
                claim["review_ids"].append(rid)
                graph["reviews"].append({"id": rid, "assertion_ids": [claim["id"]], "role": role,
                    "reviewer": "SYNTHETIC invented fixture", "reviewer_type": "ai", "invocation_id": rid,
                    "reviewed_on": "2026-11-08T13:00:00Z", "verdict": "pass", "method": "source_content_review",
                    "source_ids": ["source"], "note": "Synthetic controls only; never a real reviewer.",
                    "assertion_sha256": {claim["id"]: rg.assertion_digest(claim)}})
    # Original withheld wording remains only in this valid private baseline.
    # Explicit local-path contamination is exercised as a held negative below.
    core = sorted(row["id"] for row in graph["entities"] if row["eligible_core"])
    graph["coverage"]["frozen_core"] = {"entity_ids": core,
        "frozen_on": "2026-11-08T15:00:00Z", "source_cutoff": "2026-11-08T14:00:00Z",
        "sha256": rg.digest(rg.stable_json(core))}
    if not reference_original_differs:
        reference["method"].update(input_graph_sha256=report_module.canonical_hash(graph),
            input_graph_bytes_sha256=citations.sha256(citations.json_bytes(graph)),
            output_graph_sha256=report_module.canonical_hash(rg.public_graph(graph)))
    rb, rr, ra = trust(reference)
    if screening_version == 3:
        from test_screening_audit_v3 import fixture as screening_fixture3, simulated
        screening, _ = screening_fixture3()
        screening["release_id"] = graph["release_id"]
        screening["graph_sha256"] = report_module.canonical_hash(graph)
        sb, sr, sa = simulated(screening, graph)
    else:
        screening, _ = screening_fixture()
        screening["release_id"] = graph["release_id"]
        screening["graph_sha256"] = report_module.canonical_hash(graph)
        sb, sr, sa = simulated_admitted(screening, graph)
    day = "2026-11-12" if launch else "2026-11-16"
    cutoff = "2026-11-12T18:00:00Z" if launch else "2026-11-14T01:00:00Z"
    report = {"title": "SYNTHETIC fixture - never an actual publication", "release_id": graph["release_id"],
        "updated_on": day, "edition_date": day, "edition_kind": "launch" if launch else "weekly",
        "source_cutoff": cutoff, "status": "prepared", "editions": [],
        "archive": {"reserved_doi": "10.5281/zenodo." + str(deposition_id), "deposition_id": deposition_id,
                    "api_origin": "https://zenodo.org", "environment": "production"},
        "sections": [{"id": chapter, "title": "Synthetic " + chapter, "paragraphs": [{
            "text": "Synthetic fixture only, never actual reviewed science.", "kind": "sourced_fact",
            "claim_ids": [template["id"]]}]} for chapter in report_module.CHAPTER_IDS],
        "weekly_comparison": {"status": "first_edition"},
        "executive_findings": [{"id": "SYNTHETIC.finding." + str(i), "text": "Synthetic fixture judgment.",
            "buyer_implication": "Synthetic fixture only.", "limitations": "No real publication or review.",
            "confidence": "Synthetic fixture.", "reasoning": "Invented fixture.",
            "what_would_change": "Real evidence.", "claim_ids": [template["id"]]} for i in range(5)]}
    policy = {"mode": "publish_enabled", "launch_floors": dict(report_module.FLOORS),
        "audit_inputs": {"reference": {"audit_json": rb.decode(), "validation_receipt_json": rr.decode()},
                         "screening": {"audit_json": sb.decode(), "validation_receipt_json": sr.decode()}},
        "audits": {"reference": json.loads(rb), "screening": json.loads(sb)},
        "audit_admissions": {"reference": ra, "screening": sa},
        "report_reviews": [{"role": role, "fixture": False, "decision": "pass", "method": "report_content_review",
            "reviewer_type": "ai", "reviewer": "SYNTHETIC invented reviewer, never real",
            "invocation_id": "SYNTHETIC.synthesis." + role, "reviewed_on": "2026-11-16T19:00:00Z",
            "report_sha256": report_module.report_review_digest(report),
            "graph_sha256": report_module.canonical_hash(graph)} for role in ("evidence_auditor", "adversarial")]}
    if launch:
        policy["initial_launch_authorization"] = {"authorization_id": "user-2026-11-11-initial-launch-as-ready",
            "one_time": True, "release_id": report["release_id"], "source_cutoff": cutoff,
            "recorded_on": "2026-11-11T18:00:00Z", "imported_on": "2026-11-12T18:00:00Z",
            "recorded_in_commit": "a" * 40, "recording_path": "docs/research/CONTRACT.md",
            "provenance": "SYNTHETIC provenance fixture only; no actual user authorization is represented."}
    coverage = rg.coverage_summary(rg.public_graph(graph))
    context = {"graph": graph, "report": report, "policy": policy, "identity": {"publisher": {
        "name": "SYNTHETIC invented publisher, never an actual identity",
        "url": "https://example.invalid/SYNTHETIC-publisher"}}, "roles": {}, "corrections": [],
        "gate": {"ready": False, "status": "prelaunch", "archival_ready": True, "report_review_ready": True,
                 "reasons": ["Synthetic archive missing"], "archive_reasons": ["Synthetic archive missing"],
                 "coverage": coverage, "thresholds": dict(report_module.FLOORS), "source_cutoff": cutoff}}
    root = Path(directory) / "source"
    context["root"] = root
    if canonical_bytes is not None:
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "data/canonical.json").write_bytes(canonical_bytes)
    for name, relative in citations.REPRODUCTION_INPUTS.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == "audit-admissions.json":
            target.write_bytes(citations.json_bytes({"schema_version": "1.0.0", "admissions": policy["audit_admissions"]}))
        elif name == "source-manifestations.json":
            target.write_bytes(b'{"synthetic_fixture_only":true}\n')
        else:
            shutil.copyfile(ROOT / relative, target)
    package = root / "data/research/releases" / report["release_id"] / "publication"
    projection = citations.public_projection(context, canonical)
    with patch.object(citations, "public_projection", return_value=projection), \
            patch.object(citations, "verified_pdf", return_value=b"SYNTHETIC PDF fixture - never a research publication"):
        citations.freeze_publication_package(context, package, archive_compression="deflate")
    contract = json.loads((package / "PREPARED.json").read_bytes())
    selection = {"release_id": report["release_id"], "path": package.relative_to(root).as_posix(),
                 **{k: contract[k] for k in replay.PIN_FIELDS}}
    registry = root / citations.PREPARED_REGISTRY
    registry.write_bytes(citations.json_bytes({"schema_version": 1, "packages": [selection]}))
    receipt = {"status": "published", "verified": True, "anonymous_verified": True,
        "api_origin": "https://zenodo.org", "environment": "production", "record_id": deposition_id,
        "deposition_id": deposition_id, "doi": "10.5281/zenodo." + str(deposition_id), "concept_doi": "10.5281/zenodo.222222222",
        "reserved_doi": "10.5281/zenodo." + str(deposition_id), "record_url": "https://zenodo.org/records/" + str(deposition_id),
        "confirmed_on": "2026-11-16T20:00:00Z", "release_id": report["release_id"],
        "artifact_sha256": contract["archive_sha256"]}
    descriptor = {"schema_version": replay.VERSION, "release_id": report["release_id"],
        "package_path": selection["path"], **{k: selection[k] for k in replay.PIN_FIELDS}, "archive_receipt": receipt}
    return root, package, descriptor, context


def reseal(root, package, descriptor, mutate):
    """TEST-ONLY coherent attacker: update every cache pin, including registry.

    Semantic checks must still reject bad frozen acceptance or payloads.
    """
    files = {p.name: p.read_bytes() for p in package.iterdir() if p.name not in citations.LIVE_PACKAGE_FILES}
    source = json.loads(files["source-context.json"])
    mutate(source, files)
    files["source-context.json"] = citations._context_json_bytes(source, descriptor["context_contract_version"])
    members = {k: v for k, v in files.items() if k not in {"MANIFEST.json", "PREPARED.json", "research-archive.zip"}}
    manifest = json.loads(files["MANIFEST.json"])
    manifest.update(context_sha256=citations.sha256(files["source-context.json"]), files={
        k: {"sha256": citations.sha256(v), "bytes": len(v)} for k, v in sorted(members.items())})
    members["MANIFEST.json"] = citations.json_bytes(manifest)
    archive = citations.deterministic_zip(members, compression="deflate")
    contract = json.loads(files["PREPARED.json"])
    contract.update(context_sha256=manifest["context_sha256"], manifest_sha256=citations.sha256(members["MANIFEST.json"]),
                    archive_sha256=citations.sha256(archive), archive_bytes=len(archive))
    files = {**members, "PREPARED.json": citations.json_bytes(contract), "research-archive.zip": archive}
    for name, blob in files.items():
        (package / name).write_bytes(blob)
    descriptor.update({k: contract[k] for k in replay.PIN_FIELDS})
    descriptor["archive_receipt"]["artifact_sha256"] = contract["archive_sha256"]
    entry = {"release_id": descriptor["release_id"], "path": descriptor["package_path"], **{k: descriptor[k] for k in replay.PIN_FIELDS}}
    (root / citations.PREPARED_REGISTRY).write_bytes(citations.json_bytes({"schema_version": 1, "packages": [entry]}))


def copy_public_site_inputs(root):
    """Copy public nonresearch inputs/code only, never the authoring data tree."""
    for name in ("scripts", "web", "release-assets"):
        shutil.copytree(ROOT / name, root / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for path in (ROOT / "data").iterdir():
        if path.is_file():
            shutil.copyfile(path, root / "data" / path.name)
    for relative in ("docs/research-id-crosswalk.json", "schema/database.sql", "package.json", "package-lock.json"):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (root / "node_modules").symlink_to((ROOT / "node_modules").resolve(), target_is_directory=True)
    return root


class ReplayTextPrivacyBoundaryControls(unittest.TestCase):
    """Synthetic text only; no actual scientific or private values copied."""

    def test_scientific_text_identifiers_and_JSON_escapes_remain_public(self):
        cases = {
            "taxonomy": {"labels": ["public/private/customer-data"]},
            "disposition": {"note": "Compare public/private/pretraining groups."},
            "review_prose": {"note": "Reviewed public/private/institutional cohorts."},
            "hyphenated_prose": {"note": "No customer-private/private-training claims."},
            "reviewer_task": {"reviewer": "model-task:/root/synthetic_reviewer"},
            "metric_threshold": {"note": "precision@95model-test1.803PR"},
            "semantic_version": {"note": "metric@v1.2.3"},
            "TeX_commands": {"note": r"Equation \\frac{a}{b} and \\alpha"},
            "TeX_rows": {"note": r"Matrix a & b \\ c & d"},
            "public_URL_path": {"note": "https://example.invalid/private/table"},
            "harmless_identifier": {"note": "harness-skill-sk-stability-long-identifier"},
            "JSON_TeX": {"note": json.dumps({"note": r"Equation \\frac{a}{b}"})},
            "JSON_quoted_TeX": {"note": json.dumps(r"Equation \\alpha")},
            "JSON_nested": {"note": json.dumps({"note": json.dumps({"note": "public/private/scope"})})},
            "JSON_percent_in_string": {"note": json.dumps({"note": "public%22quoted%22text"})},
            "ordinary_brackets": {"note": "[Scientific prose without JSON syntax]"},
            "public_authorization": {"policy": {"initial_launch_authorization": {
                "authorization_id": "SYNTHETIC-public-nonsecret"}}},
        }
        for name, value in cases.items():
            with self.subTest(case=name):
                replay._public(value)

    def test_private_values_still_fail_in_prose_keys_and_encoded_JSON(self):
        unc = r"\\server\share\private"
        cases = {
            "POSIX": {"note": "/Users/SYNTHETIC/private"},
            "inline_POSIX": {"note": "See /Users/SYNTHETIC/private"},
            "double_slash_POSIX": {"note": "//home/SYNTHETIC/private"},
            "triple_slash_POSIX": {"note": "///tmp/SYNTHETIC/private"},
            "encoded_POSIX": {"note": "%2Ftmp%2FSYNTHETIC%2Fprivate"},
            "drive": {"note": r"C:\Users\SYNTHETIC\private"},
            "inline_drive": {"note": r"See C:\Users\SYNTHETIC\private"},
            "UNC": {"note": unc},
            "Unicode_UNC_server": {"note": r"\\服务器\share\private"},
            "Unicode_UNC_share": {"note": r"\\server\共享\private"},
            "UNC_mixed_separator": {"note": r"\\server/share/private"},
            "device": {"note": r"\\?\C:\SYNTHETIC\private"},
            "contact": {"note": "person@example.invalid"},
            "encoded_contact": {"note": "person%40example.invalid"},
            "credential": {"note": "sk-" + "x" * 24},
            "encoded_credential": {"note": "%73k-" + "x" * 24},
            "GitHub_credential": {"note": "ghp_" + "x" * 24},
            "PEM_marker": {"note": "-----BEGIN RSA PRIVATE KEY-----"},
            "Bearer": {"note": "Bearer SYNTHETIC-NONSECRET"},
            "encoded_Bearer": {"note": "%42earer SYNTHETIC-NONSECRET"},
            "URL_userinfo": {"note": "https://user:password@example.invalid/public"},
            "encoded_URL_userinfo": {"note": "https://user%3Apassword%40example.invalid/public"},
            "URL_query": {"note": "https://example.invalid/public?token=SYNTHETIC"},
            "encoded_URL_query": {"note": "https://example.invalid/public?api%5Fkey=SYNTHETIC"},
            "empty_URL_query": {"note": "https://example.invalid/public?password="},
            "URL_embedded_file_URI": {"note": "https://example.invalid/?next=file:///Users/SYNTHETIC/private"},
            "dynamic_path_key": {"%2FUsers%2FSYNTHETIC%2Fprivate": "value"},
            "dynamic_contact_key": {"person%40example.invalid": "value"},
            "misplaced_authorization": {"note": {"authorization_id": "SYNTHETIC"}},
            "JSON_private_field": {"note": '{"api_key":"SYNTHETIC"}'},
            "JSON_path": {"note": json.dumps({"note": "/Users/SYNTHETIC/private"})},
            "JSON_unicode_contact": {"note": '{"note":"person\\u0040example.invalid"}'},
            "JSON_nested_contact": {"note": json.dumps({"note": '{"note":"person\\u0040example.invalid"}'})},
            "JSON_scalar_UNC": {"note": json.dumps(unc)},
            "encoded_JSON_scalar_UNC": {"note": quote(json.dumps(unc), safe="")},
            "encoded_JSON_object_UNC": {"note": quote(json.dumps({"note": unc}), safe="")},
            "JSON_duplicate_key": {"note": '{"note":"safe","note":"other"}'},
            "JSON_nonfinite": {"note": '{"value":NaN}'},
        }
        for name, value in cases.items():
            with self.subTest(case=name), self.assertRaises(ValueError):
                replay._public(value)


class PublishedEditionReplayControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root, cls.package, cls.descriptor, cls.context = fixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def copy_fixture(self, directory):
        root = Path(directory) / "source"
        shutil.copytree(self.root, root)
        return root, root / self.package.relative_to(self.root), copy.deepcopy(self.descriptor)

    def test_frozen_public_replay_without_private_inputs_keeps_exact_original_commitments_and_bytes(self):
        before = {p.name: p.read_bytes() for p in self.package.iterdir() if p.name not in citations.LIVE_PACKAGE_FILES}
        with patch("research_report.publication_gate", side_effect=AssertionError("No fake fresh-input gate")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("No network")), \
                patch.object(citations, "reproduction_files", side_effect=AssertionError("No current recipe")), \
                patch.object(citations, "deterministic_zip", side_effect=AssertionError("No archive rewrite")):
            context = replay.load_published_edition(self.root, self.descriptor)
            self.assertEqual(replay.read_replay_package(context), before)
        self.assertEqual(context["policy"]["mode"], "replay_only")
        self.assertFalse(context["gate"]["archival_ready"])
        self.assertTrue(context["gate"]["ready"])
        self.assertFalse(context["replay_verification"]["current_input_readiness_revalidated"])
        pretty_private = citations.sha256(citations.json_bytes(self.context["graph"]))
        canonical_private = report_module.canonical_hash(self.context["graph"])
        canonical_public = report_module.canonical_hash(context["graph"])
        self.assertEqual(context["replay_verification"]["input_commitments"]["graph_sha256"], pretty_private)
        self.assertEqual(context["replay_verification"]["original_scientific_graph_sha256"], canonical_private)
        self.assertEqual(len({pretty_private, canonical_private, canonical_public}), 3,
                         "Pretty private bytes, canonical private science and public projection must stay distinct")
        self.assertNotIn(b"/Users/SYNTHETIC", citations.json_bytes({k: v for k, v in context.items() if k != "root"}))
        self.assertEqual({p.name: p.read_bytes() for p in self.package.iterdir() if p.name not in citations.LIVE_PACKAGE_FILES}, before)

    def test_published_replay_metadata_and_citations_bind_the_verified_synthetic_receipt(self):
        from jsonschema import Draft202012Validator
        frozen = replay.load_published_edition(self.root, self.descriptor)
        metadata = citations.publication_metadata(frozen)
        schema = json.loads((ROOT / 'schema/publication-metadata.schema.json').read_text())
        Draft202012Validator(schema).validate(metadata)
        receipt = self.descriptor['archive_receipt']
        self.assertEqual(metadata['status'], 'published')
        self.assertEqual(metadata['doi'], receipt['doi'])
        self.assertEqual(metadata['url'], receipt['record_url'])
        self.assertEqual(metadata['version'], self.descriptor['release_id'])
        self.assertIn('SYNTHETIC', metadata['title'])
        formats = citations.citation_formats(metadata)
        cff = json.loads(formats['CITATION.cff'])
        self.assertEqual(cff['doi'], receipt['doi'])
        self.assertEqual(cff['url'], receipt['record_url'])
        self.assertNotIn('date-released', cff, 'Confirmation is not a claimed publication date')
        for name in ('citation.bib', 'citation.ris', 'citation.csl.json'):
            self.assertIn(receipt['doi'], formats[name].decode(), name)

    def test_full_site_root_citation_uses_published_overlay_without_rewriting_frozen_citation(self):
        import observatory
        with tempfile.TemporaryDirectory() as temporary:
            canonical_bytes = (ROOT / 'data/canonical.json').read_bytes()
            root, package, descriptor, _ = fixture(Path(temporary) / 'canonical-bound', canonical_bytes=canonical_bytes)
            copy_public_site_inputs(root)
            frozen = replay.load_published_edition(root, descriptor)
            original = (package / 'CITATION.cff').read_bytes()
            original_guide = (package / 'REUSE.md').read_bytes()
            original_zip = (package / 'research-archive.zip').read_bytes()
            corrected_guide = b'# SYNTHETIC current guide\nUse the subject_id field.\n'
            (root / 'docs/research/reuse.md').write_bytes(corrected_guide)
            self.assertNotIn('doi', json.loads(original))
            destination = Path(temporary) / 'site'
            # The entire research publication is the explicitly synthetic frozen
            # fixture above; no real audit or publication state is manufactured.
            with patch.object(report_module, 'build_context', return_value=frozen), patch.object(observatory, 'ROOT', root):
                observatory.build(json.loads(canonical_bytes), destination)
            current = (destination / 'publication/current-CITATION.cff').read_bytes()
            self.assertEqual((destination / 'CITATION.cff').read_bytes(), current)
            self.assertEqual(json.loads(current)['doi'], descriptor['archive_receipt']['doi'])
            self.assertEqual((destination / 'publication/CITATION.cff').read_bytes(), original)
            self.assertEqual((package / 'CITATION.cff').read_bytes(), original)
            self.assertEqual((destination / 'publication/current-REUSE.md').read_bytes(), corrected_guide)
            self.assertEqual((destination / 'publication/REUSE.md').read_bytes(), original_guide)
            self.assertEqual((package / 'research-archive.zip').read_bytes(), original_zip)
            hub = (destination / 'research/data/index.html').read_text()
            self.assertIn('href="/publication/current-REUSE.md"', hub)
            self.assertIn('href="/publication/REUSE.md"', hub)

    def test_mutable_render_fixture_discards_published_receipt_history_and_package_pins(self):
        from research_lifecycle_fixtures import isolated_render_context
        baseline = replay.load_published_edition(self.root, self.descriptor)
        rid = baseline['report']['release_id']
        baseline['report']['editions'] = [{'release_id': rid, 'status': 'published'}]
        baseline['edition_snapshots'] = {rid: replay.load_published_edition(self.root, self.descriptor)}
        baseline['prepared_package'] = str(self.package)
        baseline['prepared_package_expected'] = {key: self.descriptor[key] for key in replay.PIN_FIELDS}
        before = copy.deepcopy(baseline)
        context = isolated_render_context(baseline)
        self.assertEqual(baseline, before, 'Isolation must not rewrite the published input')
        self.assertEqual(context['report']['status'], 'prelaunch')
        self.assertEqual(context['report']['archive'], {'status': 'not_published', 'doi': None})
        self.assertEqual(context['report']['editions'], [])
        self.assertEqual(context['edition_snapshots'], {})
        for key in ('prepared_package', 'prepared_package_expected', 'published_edition_replay', 'replay_verification'):
            self.assertNotIn(key, context)
        self.assertEqual(context['gate'], report_module.publication_gate(
            context['graph'], context['report'], context['policy']))
        self.assertFalse(context['gate']['ready'])
        self.assertTrue(context['gate']['archive_reasons'])
        self.assertEqual(pages._published_editions(context), [])
        context['gate']['ready'] = True  # Even an invented UI flag cannot restore a receipt.
        metadata = citations.publication_metadata(context)
        self.assertNotEqual(metadata['status'], 'published')
        self.assertNotIn('doi', metadata)
        self.assertNotIn('published_on', metadata)

    def test_native_archived_book_uses_frozen_replay_for_every_chapter_and_evidence_link(self):
        """A real test-only frozen package exercises routing without publishing source data."""
        from test_research_pages import Facts, ReaderTree
        frozen = replay.load_published_edition(self.root, self.descriptor)
        before = {path.name: path.read_bytes() for path in self.package.iterdir() if path.is_file()}
        current = copy.deepcopy(self.context)
        current['identity']['publisher']['url'] = 'https://example.invalid/SYNTHETIC-publisher'
        current['report']['updated_on'] = '2026-11-23'
        current['report']['sections'][0]['paragraphs'][0]['text'] = 'SYNTHETIC later live prose only.'
        current['report']['editions'] = [{'release_id': frozen['report']['release_id'], 'status': 'published'}]
        current['edition_snapshots'] = {frozen['report']['release_id']: frozen}
        base = '/research/editions/2026-11-12/'
        routes = [base if index == 0 else base + 'chapters/' + section['id'] + '/'
                  for index, section in enumerate(frozen['report']['sections'])]
        with tempfile.TemporaryDirectory() as temporary, \
                patch('research_report.publication_gate', side_effect=AssertionError('No fake fresh-input gate')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('No network')):
            output = Path(temporary)
            records = {record['path']: record for record in pages.write_research_pages(output, current)}
            for index, (section, route) in enumerate(zip(frozen['report']['sections'], routes)):
                text = (output / route.lstrip('/') / 'index.html').read_text()
                facts, tree = Facts(text), ReaderTree(text)
                self.assertEqual(facts.canonicals, [pages.sp.ORIGIN + route])
                self.assertNotIn('SYNTHETIC later live prose only.', text)
                self.assertIn(section['paragraphs'][0]['text'], text)
                self.assertTrue(set(routes) <= set(facts.links))
                self.assertFalse(any(link.startswith('/research/data/') for link in facts.links))
                reader_navigation = tree.with_class('r-reader-toc') + tree.with_class('r-reader-pagination') + tree.with_class('r-reader-book-title')
                for item in reader_navigation:
                    self.assertFalse(any(href.startswith(pages.REPORT_PATH) for href in ReaderTree.links(item)))
                citations_in_page = [child['attrs']['href'] for node in tree.with_class('r-paragraph-citations')
                                     for child in node['children'] if isinstance(child, dict) and child['tag'] == 'a']
                self.assertGreater(len(citations_in_page), 0)
                for href in citations_in_page:
                    destination, anchor = href.split('#', 1)
                    self.assertTrue(destination.startswith(base + 'data/'))
                    self.assertIn(anchor, Facts((output / destination.lstrip('/') / 'index.html').read_text()).ids)
                node = json.loads(next(ReaderTree.text(item) for item in tree.elements
                                       if item['tag'] == 'script' and item['attrs'].get('type') == 'application/ld+json'))
                self.assertEqual(node['dateModified'], records[route]['lastmod'])
                self.assertNotEqual(node['dateModified'], '2026-11-23')
                if index:
                    self.assertEqual(node['isPartOf']['@id'], pages.sp.ORIGIN + base)
                    self.assertEqual(node['position'], index + 1)
                else:
                    self.assertEqual([part['url'] for part in node['hasPart']],
                                     [pages.sp.ORIGIN + path + ('#executive-assessment' if i == 0 else '')
                                      for i, path in enumerate(routes)])
                for relation, other in [('prev', index - 1), ('next', index + 1)]:
                    self.assertEqual([item['attrs']['href'] for item in tree.elements
                                      if item['tag'] == 'a' and item['attrs'].get('rel') == relation],
                                     [routes[other]] if 0 <= other < len(routes) else [])
                self.assertIn(frozen['report']['archive']['record_url'], facts.links)
                self.assertFalse(any(link.startswith('/publication/') for link in facts.links))
            self.assertEqual(len(routes), 12)
        self.assertEqual({path.name: path.read_bytes() for path in self.package.iterdir() if path.is_file()}, before)

    def test_next_week_preserves_committed_raw_descriptor_digest_and_verified_history(self):
        from research_schedule import prepare_candidate, resolve_edition_reference
        with tempfile.TemporaryDirectory() as temporary:
            root, package, descriptor = self.copy_fixture(temporary)
            target = root / 'data/research/editions/SYNTHETIC-published-edition.json'
            exported = replay.export_published_edition(root, descriptor['release_id'],
                descriptor['archive_receipt'], target)
            entry = {'release_id': descriptor['release_id'], 'status': 'published',
                'snapshot_path': target.relative_to(root / 'data/research').as_posix(),
                'snapshot_sha256': exported['snapshot_sha256']}
            current = copy.deepcopy(self.context)
            current['root'] = root
            current['report'].update(status='published', archive=descriptor['archive_receipt'], editions=[entry])
            state = Path(temporary) / 'scheduler-state'
            staged = prepare_candidate(current, state, '2026-11-23', '2026-11-21T20:00:00Z')
            retained = staged['snapshot']['report']['editions']
            self.assertEqual(retained, [entry])
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), entry['snapshot_sha256'])
            self.assertEqual(list(state.glob('snapshots/' + entry['snapshot_sha256'] + '.json')), [])
            history = report_module.load_edition_snapshots(root, staged['snapshot']['report'])
            old = history[entry['release_id']]
            self.assertTrue(old['gate']['ready'])
            self.assertEqual(old['published_edition_replay']['archive_sha256'], descriptor['archive_sha256'])
            self.assertNotEqual(old['report']['release_id'], staged['snapshot']['report']['release_id'])
            with self.assertRaisesRegex(ValueError, 'source-checkout edition loader'):
                resolve_edition_reference(state, entry)
            target.write_bytes(target.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'snapshot digest differs'):
                report_module.load_edition_snapshots(root, staged['snapshot']['report'])

    def test_public_replay_cannot_stage_a_new_week_even_if_its_marker_is_removed(self):
        from research_schedule import prepare_candidate
        frozen = replay.load_published_edition(self.root, self.descriptor)
        for context in (frozen, {k: v for k, v in frozen.items() if k != 'published_edition_replay'}):
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, 'cannot stage a fresh edition'):
                    prepare_candidate(context, temporary, '2026-11-23', '2026-11-21T20:00:00Z')
                self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_export_retry_is_deterministic_and_existing_different_output_is_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "SYNTHETIC-published.json"
            first = replay.export_published_edition(self.root, self.descriptor["release_id"], self.descriptor["archive_receipt"], output)
            blob = output.read_bytes()
            self.assertEqual(first["snapshot_sha256"], hashlib.sha256(blob).hexdigest())
            self.assertEqual(first, replay.export_published_edition(self.root, self.descriptor["release_id"], self.descriptor["archive_receipt"], output))
            self.assertEqual(blob, output.read_bytes())
            self.assertEqual(json.loads(blob), self.descriptor)
            local_receipt = {**self.descriptor["archive_receipt"], "bundle_path": "/Users/SYNTHETIC/private-publication-state"}
            second = Path(temporary) / "SYNTHETIC-receipt-with-private-operation-path.json"
            replay.export_published_edition(self.root, self.descriptor["release_id"], local_receipt, second)
            self.assertEqual(json.loads(second.read_bytes()), self.descriptor)
            self.assertIn("bundle_path", local_receipt)
            output.write_text("SYNTHETIC existing different bytes")
            with self.assertRaisesRegex(ValueError, "overwritten"):
                replay.export_published_edition(self.root, self.descriptor["release_id"], self.descriptor["archive_receipt"], output)

    def test_all_supported_actual_method_pairs_and_weekly_calendar_use_separate_replay_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, descriptor, _ = fixture(Path(temporary), reference_version=4, screening_version=2, launch=False)
            context = replay.load_published_edition(root, descriptor)
            self.assertEqual(replay.edition_route_date(context, context["report"]["archive"]), "2026-11-16")
            self.assertEqual(set(context["replay_verification"]["audit_verification"]["audits"]), {"reference", "screening"})

    def test_descriptor_and_registry_pins_cannot_retarget_or_claim_a_cached_gate(self):
        for change in ({"archive_sha256": "0" * 64}, {"context_sha256": "0" * 64}, {"manifest_sha256": "0" * 64},
                       {"release_id": "SYNTHETIC-other"}, {"ready": True}, {"gate": {"ready": True}}, {"context_contract_version": 7}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay.load_published_edition(self.root, {**self.descriptor, **change})

    def test_unverified_sandbox_bad_doi_release_identity_and_reservation_receipts_hold(self):
        for change in ({"anonymous_verified": False}, {"verified": False}, {"environment": "sandbox"},
                       {"api_origin": "https://sandbox.zenodo.org"}, {"status": "reserved"}, {"doi": "10.5281/zenodo.333333333"},
                       {"release_id": "SYNTHETIC-other"}, {"artifact_sha256": "0" * 64}, {"deposition_id": "111111111"},
                       {"deposition_id": 333333333}, {"confirmed_on": "2026-11-10T00:00:00Z"}, {"confirmed_on": "2026-11-16"}):
            descriptor = copy.deepcopy(self.descriptor)
            descriptor["archive_receipt"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay.load_published_edition(self.root, descriptor)

    def test_arbitrary_external_paths_traversal_aliases_and_symlinks_hold(self):
        for value in ("../publication", "/tmp/publication", "data/research/releases/other/publication",
                      self.descriptor["package_path"] + "/../publication", self.descriptor["package_path"].replace("/publication", "//publication")):
            with self.subTest(path=value), self.assertRaises(ValueError):
                replay.load_published_edition(self.root, {**self.descriptor, "package_path": value})
        for target in ("member", "parent", "registry"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root, package, descriptor = self.copy_fixture(temporary)
                path = package / "report.html" if target == "member" else package.parent if target == "parent" else root / citations.PREPARED_REGISTRY
                moved = Path(temporary) / "SYNTHETIC-moved"
                path.rename(moved)
                path.symlink_to(moved, target_is_directory=moved.is_dir())
                with self.assertRaisesRegex(ValueError, "symlink|unsafe"):
                    replay.load_published_edition(root, descriptor)

    def test_missing_registry_duplicates_and_unselected_packages_fail_closed(self):
        for mutation in ("missing", "duplicate", "empty"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, _, descriptor = self.copy_fixture(temporary)
                registry = root / citations.PREPARED_REGISTRY
                if mutation == "missing": registry.unlink()
                elif mutation == "empty": registry.write_text('{"schema_version":1,"packages":[]}')
                else: registry.write_text('{"schema_version":1,"schema_version":1,"packages":[]}')
                with self.assertRaises(ValueError): replay.load_published_edition(root, descriptor)

    def test_changed_manifest_members_archive_and_source_bytes_hold_without_resealing(self):
        for member in ("report.html", "report.pdf", "source-context.json", "MANIFEST.json", "research-archive.zip", "PREPARED.json"):
            with self.subTest(member=member), tempfile.TemporaryDirectory() as temporary:
                root, package, descriptor = self.copy_fixture(temporary)
                path = package / member
                path.write_bytes(path.read_bytes() + b"\nSYNTHETIC tamper\n")
                with self.assertRaises((ValueError, KeyError)): replay.load_published_edition(root, descriptor)

    def test_coherently_resealed_bad_acceptance_admission_floor_and_withholds_still_hold(self):
        def rejected_admission(source, files):
            source["policy"]["audit_admissions"]["screening"]["status"] = "rejected"
            blob = citations.json_bytes({"schema_version": "1.0.0", "admissions": source["policy"]["audit_admissions"]})
            files["audit-admissions.json"] = blob
            source["package_context"]["reproduction_inputs"]["audit-admissions.json"] = {
                "sha256": citations.sha256(blob), "bytes": len(blob)}
        def pretty_hash_cannot_replace_scientific_reviews(source, files):
            for review in source["policy"]["report_reviews"]:
                review["graph_sha256"] = source["input_commitments"]["graph_sha256"]
        mutations = {
            "forged_gate": lambda s, f: s["gate"].update(archival_ready=False, ready=True),
            "held_reason": lambda s, f: s["gate"].update(reasons=["SYNTHETIC held research"]),
            "withholds": lambda s, f: s["publication_withholds"].update(paragraphs=1),
            "floor": lambda s, f: s["policy"]["launch_floors"].update(reviewed_papers=1),
            "graph_commitment": lambda s, f: s["input_commitments"].update(graph_sha256="not-an-opaque-hash"),
            "private_path": lambda s, f: s["report"].update(private_path="/Users/SYNTHETIC/private"),
            "private_dynamic_key": lambda s, f: s["report"].update({"%2FUsers%2FSYNTHETIC%2Fprivate": "SYNTHETIC forbidden path"}),
            "private_prose": lambda s, f: s["report"].update(note="SYNTHETIC local /Users/SYNTHETIC/private"),
            "admission": rejected_admission,
            "review": lambda s, f: s["policy"]["report_reviews"][0].update(graph_sha256="0" * 64),
            "review_pretty_commitment": pretty_hash_cannot_replace_scientific_reviews,
            "report": lambda s, f: s["report"]["sections"][0]["paragraphs"][0].update(text="SYNTHETIC changed report"),
            "launch": lambda s, f: s["policy"]["initial_launch_authorization"].update(one_time=False),
            "authorization_shape": lambda s, f: s["policy"]["initial_launch_authorization"].update(extra="SYNTHETIC unexpected"),
            "authorization_secret": lambda s, f: s["policy"]["initial_launch_authorization"].update(provenance="Bearer SYNTHETIC-SECRET"),
        }
        for name, mutation in mutations.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as temporary:
                root, package, descriptor = self.copy_fixture(temporary)
                reseal(root, package, descriptor, mutation)
                with self.assertRaises(ValueError): replay.load_published_edition(root, descriptor)

    def test_graph_retarget_and_formerly_withheld_records_cannot_borrow_frozen_receipts(self):
        for mutation in ("retarget", "withheld"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root, package, descriptor = self.copy_fixture(temporary)
                def change(source, files):
                    projection = json.loads(files["clean-dataset.json"])
                    if mutation == "retarget": projection["graph"]["assertions"][0]["value"]["value"] += " SYNTHETIC altered science"
                    else: projection["graph"]["assertions"].append(copy.deepcopy(next(a for a in self.context["graph"]["assertions"] if a["status"] == "candidate")))
                    files["clean-dataset.json"] = citations.json_bytes(projection)
                    source["graph"] = projection["graph"]
                reseal(root, package, descriptor, change)
                with self.assertRaises(ValueError): replay.load_published_edition(root, descriptor)

    def test_hydrated_context_mutations_cannot_copy_frozen_assets(self):
        context = replay.load_published_edition(self.root, self.descriptor)
        for key in ("graph", "report", "gate", "policy", "identity", "replay_verification"):
            bad = copy.deepcopy(context)
            bad[key]["SYNTHETIC.changed"] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "changed"):
                replay.read_replay_package(bad)

    def test_source_edition_descriptor_hash_release_and_symlink_are_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _, descriptor = self.copy_fixture(temporary)
            output = root / "data/research/editions/SYNTHETIC-published.json"
            receipt = replay.export_published_edition(root, descriptor["release_id"], descriptor["archive_receipt"], output)
            entry = {"snapshot_path": "editions/" + output.name, "snapshot_sha256": receipt["snapshot_sha256"],
                     "release_id": descriptor["release_id"], "status": "published"}
            self.assertTrue(replay.resolve_edition_entry(root, entry)["gate"]["ready"])
            for changed in ({"snapshot_sha256": "0" * 64}, {"release_id": "SYNTHETIC-other"},
                            {"snapshot_path": "editions/../policy.json"}):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    replay.resolve_edition_entry(root, {**entry, **changed})
            moved = Path(temporary) / "SYNTHETIC-moved-descriptor.json"
            output.rename(moved)
            output.symlink_to(moved)
            with self.assertRaisesRegex(ValueError, "symlink"):
                replay.resolve_edition_entry(root, entry)

    def test_history_does_not_fall_back_to_current_graph_or_report(self):
        context = replay.load_published_edition(self.root, self.descriptor)
        self.assertEqual(context["report"]["editions"], [])
        with tempfile.TemporaryDirectory() as temporary:
            root, package, descriptor = self.copy_fixture(temporary)
            (root / "data/research/graph.json").write_text("SYNTHETIC later private input deliberately unreadable")
            (root / "data/research/report.json").write_text("SYNTHETIC next weekly report deliberately unreadable")
            for name, relative in citations.REPRODUCTION_INPUTS.items():
                (root / relative).unlink()
            historical = replay.load_published_edition(root, descriptor)
            self.assertEqual(historical["graph"], context["graph"])
            self.assertEqual(historical["report"], context["report"])
            self.assertEqual(replay.read_replay_package(historical)["research-archive.zip"], (package / "research-archive.zip").read_bytes())


if __name__ == "__main__":
    unittest.main()
