"""TEST-ONLY storage workload. Never research, review, coverage or launch evidence.

The workload uses 150 paper works, 60 suppliers, 60 dataset families and 20
benchmark families, each with ten source-bound assertions and three synthetic
role receipts per assertion. All text and identities explicitly identify the
fixture. Gate readiness remains false; no audit or publication is invented.
"""
import hashlib
import json


COUNTS = {'paper_work': 150, 'supplier': 60, 'dataset_family': 60, 'benchmark_family': 20}


def scale_pdf_allowance():
    """TEST-ONLY incompressible 1 MiB budget, never an actual reviewed PDF."""
    return b'TEST-ONLY PDF byte allowance, not a research PDF.\n' + b''.join(
        hashlib.sha256(('TEST-ONLY PDF ' + str(index)).encode()).digest() for index in range(32768))


def scale_context(root, *, assertions_per_entity=10):
    from research_graph import assertion_digest
    graph = {'schema_version': '1.0.0', 'release_id': 'TEST-ONLY-scale', 'as_of': '2026-11-09T00:00:00Z',
             'canonical_dataset_version': '2.5.0', 'canonical_sha256': '0' * 64,
             'entities': [], 'sources': [], 'assertions': [], 'reviews': [],
             'coverage': {'frozen_core': {'entity_ids': [], 'frozen_on': None, 'source_cutoff': None, 'sha256': None},
                          'quality_audit': None, 'screening_audit': None, 'notes': ['TEST-ONLY: no actual research or review.']}}
    for kind, count in COUNTS.items():
        for index in range(count):
            eid = f'TEST-ONLY.{kind}.{index:03}'
            source_id = eid + '.source'
            excerpt = 'TEST-ONLY storage fixture; this invented statement is never research evidence.'
            excerpt_hash = hashlib.sha256(excerpt.encode()).hexdigest()
            graph['entities'].append({'id': eid, 'kind': kind, 'name': 'TEST-ONLY ' + kind.replace('_', ' ') + f' {index:03}',
                'status': 'approved', 'review_depth': 'full_source', 'identifiers': {'doi': f'10.0000/TEST-ONLY.{index}'} if kind == 'paper_work' else {},
                'aliases': [], 'legacy_id': None, 'family_id': eid if 'family' in kind else None, 'parent_id': None,
                'taxonomy': {key: ['TEST-ONLY ' + key] for key in ('domain', 'modality', 'workflow', 'expertise', 'origin', 'labels', 'oversight')},
                'disposition': 'included', 'disposition_reason': 'TEST-ONLY schema-valid storage workload, never evidence of research coverage.',
                'assertion_ids': [], 'eligible_core': False})
            graph['sources'].append({'id': source_id, 'url': f'https://example.org/TEST-ONLY/{kind}/{index}',
                'title': 'TEST-ONLY source metadata ' + eid, 'publisher': 'TEST-ONLY storage fixture',
                'source_type': 'paper' if kind == 'paper_work' else 'provider_documentation', 'version': 'TEST-ONLY-1',
                'published_on': '2026-11-01', 'captured_on': '2026-11-08T00:00:00Z', 'status': 'captured',
                'response_sha256': hashlib.sha256(source_id.encode()).hexdigest(), 'excerpt': excerpt,
                'excerpt_sha256': excerpt_hash, 'locator': 'TEST-ONLY generated fixture', 'license': None})
            for number in range(assertions_per_entity):
                aid = eid + f'.claim.{number:02}'
                # Distinct scope/hash fields exercise realistic record structure and
                # entropy without copying third-party source text or making claims.
                basis = {f'TEST-ONLY dimension {field}': hashlib.sha256(f'{aid}.{field}'.encode()).hexdigest() for field in range(6)}
                statement = {'statement': 'TEST-ONLY invented storage statement ' + aid + '; no supplier performance or actual source review is asserted.',
                             'scope': {'product': 'TEST-ONLY generated record', 'provenance_scope': 'TEST-ONLY synthetic data'},
                             'reported_value_and_basis': {'currency': None, 'period_start': '2026-01-01', 'period_end': '2026-12-31',
                                                          'annualized': False, 'conditions': basis}}
                review_ids = [aid + '.' + role for role in ('author', 'source_verifier', 'adversarial')]
                assertion = {'id': aid, 'subject_id': eid, 'predicate': 'documents', 'object_id': None,
                    'value': {'type': 'text', 'value': json.dumps(statement, sort_keys=True)},
                    'evidence': [{'source_id': source_id, 'locator': f'TEST-ONLY fixture record {number}', 'excerpt_sha256': excerpt_hash}],
                    'qualifications': ['TEST-ONLY fixture; no actual review, coverage, capability, price, financial metric, or publication is established.'],
                    'status': 'approved', 'review_ids': review_ids, 'as_of': '2026-11-08', 'provenance_kind': 'first_party'}
                graph['assertions'].append(assertion)
                graph['entities'][-1]['assertion_ids'].append(aid)
                for role, rid in zip(('author', 'source_verifier', 'adversarial'), review_ids):
                    graph['reviews'].append({'id': rid, 'assertion_ids': [aid], 'assertion_sha256': {aid: assertion_digest(assertion)},
                        'role': role, 'reviewer': 'TEST-ONLY invented reviewer', 'reviewer_type': 'ai', 'invocation_id': 'TEST-ONLY.' + role,
                        'reviewed_on': '2026-11-08T01:00:00Z', 'verdict': 'pass', 'method': 'source_content_review', 'source_ids': [source_id],
                        'note': 'TEST-ONLY synthetic receipt to exercise graph serialization; no actual review occurred. ' + basis['TEST-ONLY dimension 0']})
    report = {'title': 'TEST-ONLY weekly storage workload, never a research edition', 'release_id': graph['release_id'],
              'updated_on': '2026-11-09', 'status': 'prelaunch', 'archive': {'status': 'not_published'},
              'sections': [{'id': 'TEST-ONLY-' + str(chapter), 'title': 'TEST-ONLY chapter ' + str(chapter),
                  'paragraphs': [{'kind': 'method', 'claim_ids': [], 'text': 'TEST-ONLY report paragraph; no analytical judgment is made. ' +
                                 ' '.join(hashlib.sha256(f'{chapter}.{paragraph}.{word}'.encode()).hexdigest()[:12] for word in range(150))}
                                 for paragraph in range(20)]} for chapter in range(12)]}
    return {'root': root, 'graph': graph, 'report': report,
            'gate': {'ready': False, 'archival_ready': False, 'status': 'prelaunch',
                     'reasons': ['TEST-ONLY workload; never satisfies research launch requirements.'], 'coverage': {}},
            'identity': {'publisher': {'name': 'TEST-ONLY fixture'}}, 'policy': {'mode': 'prepare_only'}}


if __name__ == '__main__':
    import sys
    import tempfile
    from pathlib import Path
    from unittest.mock import patch
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'scripts'))
    import research_citations as citations
    from research_graph import validate_graph
    context = scale_context(root)
    validate_graph(context['graph'])
    with tempfile.TemporaryDirectory(prefix='TEST-ONLY-publication-scale-') as temporary, patch.object(citations, 'verified_pdf', return_value=scale_pdf_allowance()):
        citations.write_publication_assets(context, temporary, archive_compression='deflate')
        inventory = citations.publication_asset_inventory(Path(temporary) / 'publication')
        print(json.dumps({'TEST_ONLY': True, 'note': 'Synthetic storage workload; no actual research, review or publication.',
                          'entity_counts': COUNTS, 'assertions': len(context['graph']['assertions']),
                          'synthetic_receipts': len(context['graph']['reviews']), **inventory}, indent=2, sort_keys=True))
