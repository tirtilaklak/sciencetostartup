"""FIXTURE ONLY: public metadata projection never changes exposure or metrics."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import reference_audit_v4 as ref
from test_reference_audit_v4 import fixture_only, blob, reseal


class ExposureProjectionTests(unittest.TestCase):
    def private_fixture(self):
        audit, graph, payloads, sources = fixture_only()
        exposure = json.loads(payloads['exposure_registry'])
        exposure.update({key: {'note': 'SYNTHETIC retained private provenance only'}
                         for key in ref.EXPOSURE_PRIVATE_METADATA_FIELDS})
        payloads['exposure_registry'] = blob(exposure)
        review = json.loads(payloads['original_population_review'])
        review['review']['input_commitments']['exposure_registry_sha256'] = ref.byte_hash(payloads['exposure_registry'])
        payloads['original_population_review'] = blob(review)
        envelope = json.loads(payloads['population_semantic_review'])
        envelope['input_commitments'] = copy.deepcopy(review['review']['input_commitments'])
        envelope['review_refs'][0]['entry_sha256'] = ref.canonical_hash(review['review'])
        payloads['population_semantic_review'] = blob(envelope)
        audit['method']['population_review_sha256'] = ref.byte_hash(payloads['population_semantic_review'])
        audit['artifacts'] = {key: ref.byte_hash(value) for key, value in payloads.items()}
        audit['exposure_registry'] = ref.public_exposure_registry(exposure)
        return reseal(audit), graph, payloads, sources

    def validate_private(self, audit, graph, payloads, sources):
        return json.loads(ref.validate_private_reference_v4(blob(audit), graph,
            expected_artifact_hashes=audit['artifacts'], artifact_payloads=payloads,
            source_payloads=sources, invocation_id='SYNTHETIC.metadata-projection-validator',
            reviewer='SYNTHETIC fixture-only validator', fixture=True))

    def test_all_original_private_bytes_authenticate_with_exact_six_public_fields(self):
        original, _, _, _ = fixture_only()
        audit, graph, payloads, sources = self.private_fixture()
        self.assertEqual(audit['exposure_registry'], original['exposure_registry'])
        self.assertEqual(ref.recompute_reference(audit), ref.recompute_reference(original))
        receipt = self.validate_private(audit, graph, payloads, sources)
        self.assertEqual(receipt['validation_errors'], [])
        self.assertTrue(receipt['validation_run']['fixture'])
        self.assertNotIn('private provenance', json.dumps(audit))

    def test_public_scientific_exposure_change_cannot_hide_behind_metadata_projection(self):
        audit, graph, payloads, sources = self.private_fixture()
        for field in sorted(ref.EXPOSURE_PUBLIC_FIELDS):
            with self.subTest(field=field):
                changed = copy.deepcopy(audit)
                original = changed['exposure_registry'][field]
                changed['exposure_registry'][field] = [] if isinstance(original, list) else {} if isinstance(original, dict) else '0' * 64
                receipt = self.validate_private(changed, graph, payloads, sources)
                self.assertTrue(any('exposure projection differs' in error for error in receipt['validation_errors']))

    def test_changed_private_metadata_still_fails_exact_original_authentication(self):
        audit, graph, payloads, sources = self.private_fixture()
        changed = dict(payloads)
        exposure = json.loads(changed['exposure_registry'])
        exposure['previous_draft_preserved'] = 'SYNTHETIC changed after commitment'
        changed['exposure_registry'] = blob(exposure)
        receipt = self.validate_private(audit, graph, changed, sources)
        self.assertTrue(any('Original artifact authentication failed' in error for error in receipt['validation_errors']))

    def test_unknown_fields_and_missing_scientific_fields_fail_closed_and_inputs_are_immutable(self):
        audit, _, _, _ = fixture_only()
        registry = audit['exposure_registry']
        before = copy.deepcopy(registry)
        projected = ref.public_exposure_registry(registry)
        projected['assertion_ids'].append('SYNTHETIC later edit')
        self.assertEqual(registry, before)
        for changed in ({**registry, 'hidden_exposure_assertion_ids': ['SYNTHETIC']},
                        {key: value for key, value in registry.items() if key != 'lineage_keys'}):
            with self.assertRaisesRegex(ValueError, 'known exposure registry'):
                ref.public_exposure_registry(changed)


if __name__ == '__main__':
    unittest.main()
