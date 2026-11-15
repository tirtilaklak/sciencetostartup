"""Central reader controls with invented in-memory audit fixtures only."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_report import FLOORS, _evaluate_audit, publication_gate
from test_research_report import empty_graph, test_report
from test_screening_audit_v2 import fixture, simulated_admitted


class AuthoritativeAuditTests(unittest.TestCase):
    def test_initial_hypothesis_v4_uses_explicit_reader_and_separate_fixture_trust(self):
        from test_reference_audit_v4 import fixture_only, simulated_trust
        audit, graph, _, _ = fixture_only()
        raw, receipt, trust = simulated_trust(audit)
        policy = {'audits': {'reference': audit}, 'audit_inputs': {'reference': {
            'audit_json': raw.decode(), 'validation_receipt_json': receipt.decode()}},
            'audit_admissions': {'reference': trust}}
        errors, metrics = _evaluate_audit('reference', graph, FLOORS, policy)
        self.assertEqual(errors, [])
        self.assertTrue(metrics['publication_eligible'])
        policy['audit_admissions'] = {}
        errors, metrics = _evaluate_audit('reference', graph, FLOORS, policy)
        self.assertTrue(errors)
        self.assertFalse(metrics.get('publication_eligible', False))

    def inputs(self):
        audit, graph = fixture()
        raw, receipt, trust = simulated_admitted(audit, graph)
        policy = {'audits': {'screening': audit},
                  'audit_inputs': {'screening': {'audit_json': raw.decode(),
                                                'validation_receipt_json': receipt.decode()}},
                  'audit_admissions': {'screening': trust}}
        return audit, graph, policy

    def test_exact_reader_is_used_with_separately_supplied_fixture_trust(self):
        _, graph, policy = self.inputs()
        errors, metrics = _evaluate_audit('screening', graph, FLOORS, policy)
        self.assertEqual(errors, [])
        self.assertTrue(metrics['publication_eligible'])

    def test_audit_cannot_nominate_its_own_admission(self):
        _, graph, policy = self.inputs()
        trust = policy.pop('audit_admissions')
        policy['audit_inputs']['screening']['trusted_admission'] = trust['screening']
        errors, metrics = _evaluate_audit('screening', graph, FLOORS, policy)
        self.assertTrue(errors)
        self.assertFalse(metrics.get('publication_eligible', False))

    def test_same_parsed_document_cannot_borrow_receipt_for_other_bytes(self):
        _, graph, policy = self.inputs()
        policy['audit_inputs']['screening']['audit_json'] += '\n'
        errors, metrics = _evaluate_audit('screening', graph, FLOORS, policy)
        self.assertTrue(errors)
        self.assertFalse(metrics.get('publication_eligible', False))

    def test_parsed_view_cannot_disagree_with_authoritative_document(self):
        _, graph, policy = self.inputs()
        policy['audits']['screening']['selected_record_ids'].reverse()
        errors, _ = _evaluate_audit('screening', graph, FLOORS, policy)
        self.assertTrue(any('authoritative exact bytes' in error for error in errors))

    def test_new_version_has_no_legacy_or_summary_fallback(self):
        audit = {'schema_version': 'unknown-audit-version', 'kind': 'reference'}
        policy = {'audits': {'reference': audit}, 'audit_inputs': {'reference': {
            'audit_json': json.dumps(audit), 'validation_receipt_json': '{}'}}}
        errors, _ = _evaluate_audit('reference', empty_graph(), FLOORS, policy)
        self.assertTrue(any('no legacy fallback' in error for error in errors))
        policy['audit_inputs'] = {}
        self.assertTrue(_evaluate_audit('reference', empty_graph(), FLOORS, policy)[0])

    def test_unknown_version_rejection_does_not_echo_private_input(self):
        from research_audit_dispatch import validate_audit
        for private in ('sk-' + 'X' * 24, '文sk-' + 'X' * 24,
                        '/Users/test/private.txt', 'private@example.invalid',
                        'https://example.invalid/?access_token=TEST-ONLY'):
            with self.subTest(kind=private[:2]):
                audit = {'schema_version': private, 'kind': 'reference'}
                raw = json.dumps(audit).encode()
                direct, _ = validate_audit('reference', raw, empty_graph(), FLOORS)
                policy = {'audits': {'reference': audit}, 'audit_inputs': {'reference': {
                    'audit_json': raw.decode(), 'validation_receipt_json': '{}'}}}
                central, _ = _evaluate_audit('reference', empty_graph(), FLOORS, policy)
                for errors in (direct, central):
                    self.assertTrue(errors)
                    self.assertNotIn(private, str(errors))
                    self.assertTrue(any('no legacy fallback' in item for item in errors))

    def test_two_slots_cannot_reuse_a_single_actual_sut_invocation(self):
        audit = {'runs': [{'role': 'sut', 'invocation_id': 'SYNTHETIC-REUSED-RUN'}]}
        policy = {'audits': {'reference': copy.deepcopy(audit), 'screening': copy.deepcopy(audit)}}
        gate = publication_gate(empty_graph(), test_report(), policy)
        self.assertTrue(any('separate actual SUT executions' in reason for reason in gate['reasons']))
        policy['audits']['screening']['runs'] = None
        self.assertFalse(publication_gate(empty_graph(), test_report(), policy)['ready'])
