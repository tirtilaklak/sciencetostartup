"""Substantive revision dates, using small explicitly synthetic graph inputs."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_graph as rg
import research_pages as rp
import static_pages as sp


class RevisionDateTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            'graph': {'as_of': '2026-11-10T12:00:00Z', 'release_id': 'fixture',
                      'entities': [{'id': 'paper.a', 'kind': 'paper', 'name': 'A'},
                                   {'id': 'paper.b', 'kind': 'paper', 'name': 'B'},
                                   {'id': 'paper.unknown', 'kind': 'paper', 'name': 'Unknown'}],
                      'sources': [{'id': 'source.a', 'captured_on': '2026-10-01T12:00:00Z'}],
                      'assertions': [{'id': 'claim.a', 'subject_id': 'paper.a', 'object_id': None,
                                      'status': 'approved', 'as_of': '2026-10-02T12:00:00Z',
                                      'evidence': [{'source_id': 'source.a'}], 'review_ids': ['review.a']},
                                     {'id': 'claim.b', 'subject_id': 'paper.b', 'status': 'approved',
                                      'as_of': '2026-10-03T12:00:00Z', 'review_ids': [], 'evidence': []}],
                      'reviews': []},
            'report': {'updated_on': '2026-11-10', 'release_id': 'fixture'},
            'policy': {}, 'identity': {}, 'gate': {}, 'corrections': []}
        self.review = {'id': 'review.a', 'assertion_ids': ['claim.a'],
                       'assertion_sha256': {'claim.a': rg.assertion_digest(self.context['graph']['assertions'][0])},
                       'reviewed_on': '2026-10-04T12:00:00Z'}
        self.context['graph']['reviews'].append(self.review)
        self.a = '/research/papers/paper.a/'
        self.b = '/research/papers/paper.b/'

    def test_weekly_publication_and_snapshot_dates_do_not_redate_evidence(self):
        before = rp._revision_dates(self.context)
        self.context['graph']['as_of'] = '2026-11-17T12:00:00Z'
        self.context['report']['updated_on'] = '2026-11-17'
        after = rp._revision_dates(self.context)
        for path, day in before.items():
            if path.startswith(('/research/papers/', '/research/data/assertions/', '/research/data/sources/')):
                self.assertEqual(after[path], day, path)
        self.assertEqual(after[self.a], '2026-10-04')

    def test_new_own_review_changes_only_bound_claim_entity_and_parts(self):
        before = rp._revision_dates(self.context)
        self.review['reviewed_on'] = '2026-11-11T12:00:00Z'
        after = rp._revision_dates(self.context)
        self.assertEqual(after[self.a], '2026-11-11')
        self.assertEqual(after[self.b], before[self.b])
        self.assertEqual(after[rp._ledger_path('assertion', rp._ledger_bucket('claim.a'))], '2026-11-11')
        self.assertEqual(after[rp._ledger_path('source', rp._ledger_bucket('source.a'))], '2026-11-11')

    def test_stale_or_unattached_receipts_cannot_supply_dates(self):
        self.review['reviewed_on'] = '2099-01-01T12:00:00Z'
        self.review['assertion_sha256']['claim.a'] = '0' * 64
        self.assertEqual(rp._page_revision(self.context, self.a), '2026-10-02')
        self.review['assertion_sha256']['claim.a'] = rg.assertion_digest(self.context['graph']['assertions'][0])
        self.review['assertion_ids'] = ['another.claim']
        self.assertEqual(rp._page_revision(self.context, self.a), '2026-10-02')

    def test_incoming_and_child_approved_evidence_counts_without_sibling_leakage(self):
        assertion = self.context['graph']['assertions'][1]
        assertion['object_id'] = 'paper.a'
        assertion['as_of'] = '2026-10-06T12:00:00Z'
        self.assertEqual(rp._page_revision(self.context, self.a), '2026-10-06')
        assertion['object_id'] = None
        self.context['graph']['entities'][1]['parent_id'] = 'paper.a'
        self.assertEqual(rp._page_revision(self.context, self.a), '2026-10-06')
        assertion['status'] = 'candidate'
        self.assertEqual(rp._page_revision(self.context, self.a), '2026-10-04')

    def test_unknown_metadata_omits_both_date_fields(self):
        path = '/research/papers/paper.unknown/'
        self.assertEqual(rp._sitemap_record(self.context, path), {'path': path})
        html = rp._render(self.context, 'Unknown', 'Fixture metadata only.', path, '<h1>Unknown</h1>')
        node = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
        self.assertNotIn('dateModified', node)
        sitemap = ET.fromstring(sp.render_sitemap([(sp.ORIGIN + path, None)]))
        self.assertEqual(len(sitemap[0]), 1)

    def test_same_source_feeds_structured_data_and_sitemap(self):
        html = rp._render(self.context, 'A', 'Fixture.', self.a, '<h1>A</h1>')
        node = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
        self.assertEqual(node['dateModified'], rp._sitemap_record(self.context, self.a)['lastmod'])

    def test_frozen_edition_uses_snapshot_dates_and_version_bounded_paths(self):
        frozen = copy.deepcopy(self.context)
        frozen['_page_revisions'] = rp._revision_dates(frozen)
        self.review['reviewed_on'] = '2026-11-11T12:00:00Z'
        live_path = rp._ledger_path('assertion', rp._ledger_bucket('claim.a'))
        edition_path = '/research/editions/2026-11-09.r2/data/' + live_path.removeprefix('/research/data/')
        self.assertEqual(rp._page_revision(frozen, edition_path), '2026-10-04')
        self.assertEqual(rp._page_revision(self.context, live_path), '2026-11-11')

    def test_source_capture_changes_only_its_partition(self):
        before = rp._revision_dates(self.context)
        self.context['graph']['sources'][0]['captured_on'] = '2026-11-12T12:00:00Z'
        after = rp._revision_dates(self.context)
        self.assertEqual(after[rp._ledger_path('source', rp._ledger_bucket('source.a'))], '2026-11-12')
        self.assertEqual(after[self.a], before[self.a])
        self.assertEqual(after[rp._ledger_path('assertion', rp._ledger_bucket('claim.a'))],
                         before[rp._ledger_path('assertion', rp._ledger_bucket('claim.a'))])


if __name__ == '__main__':
    unittest.main()
