"""Frozen-scope controls using invented in-memory admissions, never research."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_graph as graph_module
from reference_audit_v3 import CODE_FILES
from reproduce_research_package import verify_frozen_audits
from test_reference_audit_v3 import fixture, simulated_trust


class FrozenAuditControls(unittest.TestCase):
    def prepare(self, directory, audit=None):
        default_audit, graph = fixture()
        audit = default_audit if audit is None else audit
        raw, receipt, admission = simulated_trust(audit)
        directory = Path(directory)
        for name in CODE_FILES:
            shutil.copyfile(ROOT / name, directory / Path(name).name)
        context = {'gate': {'archival_ready': False}, 'policy': {
            'audit_inputs': {'reference': {'audit_json': raw.decode(),
                                         'validation_receipt_json': receipt.decode()}},
            'audit_admissions': {'reference': admission}}}
        (directory / 'source-context.json').write_text(json.dumps(context))
        (directory / 'audit-admissions.json').write_text(json.dumps({
            'schema_version': '1.0.0', 'admissions': {'reference': admission}}))
        return {'graph': graph_module.public_graph(graph)}, context

    def test_frozen_numbers_and_retained_bindings_do_not_claim_private_revalidation(self):
        with tempfile.TemporaryDirectory() as temporary:
            projection, _ = self.prepare(temporary)
            result = verify_frozen_audits(temporary, projection)
        self.assertFalse(result['live_private_withheld_records_revalidated'])
        self.assertFalse(result['raw_sources_revalidated'])
        self.assertEqual(result['audits']['reference']['status'], 'admitted_frozen_receipt_verified')
        self.assertEqual(result['audits']['screening']['status'], 'not_supplied')

    def test_mutated_retained_or_newly_exposed_withheld_finding_is_rejected(self):
        for mutation in ('retained', 'withheld'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                projection, _ = self.prepare(temporary)
                if mutation == 'retained':
                    projection['graph']['assertions'][0]['value']['value'] = 'Changed synthetic science'
                else:
                    audit, graph = fixture()
                    withheld = next(row for row in graph['assertions'] if row['status'] == 'candidate')
                    projection['graph']['assertions'].append(copy.deepcopy(withheld))
                with self.assertRaisesRegex(ValueError, 'binding|withheld'):
                    verify_frozen_audits(temporary, projection)

    def test_v4_frozen_receipt_preserves_population_commitments_without_private_replay(self):
        from reference_audit_v4 import CODE_FILES as V4_CODE
        from test_reference_audit_v4 import fixture_only, simulated_trust as simulated_v4
        audit, graph, _, _ = fixture_only()
        raw, receipt, admission = simulated_v4(audit)
        context = {'gate': {'archival_ready': False}, 'policy': {
            'audit_inputs': {'reference': {'audit_json': raw.decode(),
                                         'validation_receipt_json': receipt.decode()}},
            'audit_admissions': {'reference': admission}}}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in V4_CODE:
                shutil.copyfile(ROOT / name, directory / Path(name).name)
            projection = {'graph': graph_module.public_graph(graph)}
            context['graph'] = copy.deepcopy(projection['graph'])
            (directory / 'source-context.json').write_text(json.dumps(context))
            registry = {'schema_version': '1.0.0', 'admissions': {'reference': admission}}
            (directory / 'audit-admissions.json').write_text(json.dumps(registry))
            result = verify_frozen_audits(directory, projection)
            self.assertFalse(result['live_private_withheld_records_revalidated'])
            self.assertEqual(result['audits']['reference']['status'], 'admitted_frozen_receipt_verified')
            admission['lineage_manifest_sha256'] = '0' * 64
            (directory / 'source-context.json').write_text(json.dumps(context))
            (directory / 'audit-admissions.json').write_text(json.dumps(registry))
            with self.assertRaisesRegex(ValueError, 'population'):
                verify_frozen_audits(directory, projection)

    def test_candidate_document_cannot_replace_separate_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            projection, context = self.prepare(temporary)
            context['policy']['audit_admissions'] = {}
            (Path(temporary) / 'source-context.json').write_text(json.dumps(context))
            with self.assertRaisesRegex(ValueError, 'registry differs'):
                verify_frozen_audits(temporary, projection)

    def test_v4_public_source_identity_review_and_status_mutations_are_rejected(self):
        from reference_audit_v4 import CODE_FILES as V4_CODE
        from test_reference_audit_v4 import fixture_only, simulated_trust as simulated_v4
        audit, graph, _, _ = fixture_only()
        binding = next(row for row in audit['bindings'] if row['observed_positive'])
        raw, receipt, admission = simulated_v4(audit)
        baseline = graph_module.public_graph(graph)
        for target in ('source', 'entity', 'review', 'status'):
            for synchronized in (False, True) if target in ('source', 'entity', 'status') else (False,):
                with self.subTest(target=target, synchronized=synchronized), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    for name in V4_CODE:
                        shutil.copyfile(ROOT / name, directory / Path(name).name)
                    projection = {'graph': copy.deepcopy(baseline)}
                    context = {'graph': copy.deepcopy(baseline), 'gate': {'archival_ready': False}, 'policy': {
                        'audit_inputs': {'reference': {'audit_json': raw.decode(),
                                                     'validation_receipt_json': receipt.decode()}},
                        'audit_admissions': {'reference': admission}}}
                    if target == 'source':
                        sid = next(iter(binding['source_record_sha256']))
                        next(row for row in projection['graph']['sources'] if row['id'] == sid)['license'] = 'TEST altered license'
                    elif target == 'entity':
                        eid = next(iter(binding['entity_identity_sha256']))
                        next(row for row in projection['graph']['entities'] if row['id'] == eid)['name'] = 'TEST altered identity'
                    elif target == 'review':
                        rid = next(iter(binding['original_review_record_sha256']))
                        next(row for row in projection['graph']['reviews'] if row['id'] == rid)['note'] = 'TEST altered projected review'
                    else:
                        next(row for row in projection['graph']['assertions'] if row['id'] == binding['assertion_id'])['status'] = 'candidate'
                    if synchronized:
                        context['graph'] = copy.deepcopy(projection['graph'])
                    (directory / 'source-context.json').write_text(json.dumps(context))
                    (directory / 'audit-admissions.json').write_text(json.dumps({
                        'schema_version': '1.0.0', 'admissions': {'reference': admission}}))
                    with self.assertRaisesRegex(ValueError, 'context|binding|status'):
                        verify_frozen_audits(directory, projection)

    def test_changed_code_or_receipt_bytes_do_not_borrow_an_admission(self):
        for mutation in ('code', 'receipt'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                projection, context = self.prepare(temporary)
                if mutation == 'code':
                    path = Path(temporary) / 'reference_audit_v3.py'
                    path.write_bytes(path.read_bytes() + b'\n# Synthetic mutation\n')
                else:
                    context['policy']['audit_inputs']['reference']['validation_receipt_json'] += '\n'
                    (Path(temporary) / 'source-context.json').write_text(json.dumps(context))
                with self.assertRaises(ValueError):
                    verify_frozen_audits(temporary, projection)

    def test_numeric_failure_cannot_be_hidden_by_a_simulated_pass_receipt(self):
        audit, _ = fixture()
        for truth in audit['truth']:
            truth['decision'] = 'unknown'
        with tempfile.TemporaryDirectory() as temporary:
            projection, _ = self.prepare(temporary, audit)
            with self.assertRaisesRegex(ValueError, 'quality/completion floors'):
                verify_frozen_audits(temporary, projection)

    def test_passing_archival_context_requires_both_actual_audit_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            projection, context = self.prepare(temporary)
            context['gate']['archival_ready'] = True
            (Path(temporary) / 'source-context.json').write_text(json.dumps(context))
            with self.assertRaisesRegex(ValueError, 'lacks actual screening'):
                verify_frozen_audits(temporary, projection)
