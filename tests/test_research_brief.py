"""Briefing evidence/review/privacy rules; fixtures are not research results."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_brief import executive_brief_assets


def fixture():
    return ({'report': {'executive_findings': [{
        'id': 'test-only-finding', 'text': 'SYNTHETIC finding <script>danger</script>.',
        'buyer_implication': 'SYNTHETIC implication.', 'confidence': 'Fixture only.',
        'limitations': 'SYNTHETIC limitation.', 'claim_ids': ['test-only-claim']} ]},
        'graph': {'assertions': [{'id': 'test-only-claim', 'status': 'approved'}]},
        'gate': {'report_review_ready': True, 'coverage': {'reviewed_papers': 0}}},
        {'title': 'TEST ONLY report', 'version': 'test-only.1', 'updated_on': '2026-11-10',
         'status': 'prelaunch', 'note': 'Not a published edition.', 'author': 'Test fixture'})


class BriefTests(unittest.TestCase):
    def test_independent_review_gate_withholds_draft_judgments(self):
        context, metadata = fixture()
        context['gate']['report_review_ready'] = False
        for blob in executive_brief_assets(context, metadata).values():
            self.assertNotIn(b'SYNTHETIC finding', blob)
            self.assertIn(b'awaiting separate', blob)

    def test_unapproved_or_duplicate_evidence_cannot_be_promoted_by_brief(self):
        context, metadata = fixture()
        context['graph']['assertions'][0]['status'] = 'candidate'
        self.assertNotIn(b'SYNTHETIC finding', executive_brief_assets(context, metadata)['executive-brief.html'])
        context, metadata = fixture()
        context['report']['executive_findings'] *= 2
        self.assertNotIn(b'SYNTHETIC finding', executive_brief_assets(context, metadata)['executive-brief.html'])

    def test_citations_are_local_and_scientific_qualifications_survive(self):
        context, metadata = fixture()
        before = copy.deepcopy(context)
        files = executive_brief_assets(context, metadata)
        self.assertEqual(files, executive_brief_assets(context, metadata))
        self.assertEqual(context, before)
        page = files['executive-brief.html'].decode()
        self.assertIn('SYNTHETIC limitation.', page)
        self.assertIn('Fixture only.', page)
        self.assertIn('evidence.html#assertion-test-only-claim', page)
        self.assertIn('report.html#finding-test-only-finding', page)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)

    def test_contacts_are_filtered_in_both_brief_formats(self):
        context, metadata = fixture()
        context['report']['executive_findings'][0]['text'] += ' private-fixture@example.org'
        metadata['author'] = 'private-fixture@example.org'
        for blob in executive_brief_assets(context, metadata).values():
            self.assertNotIn(b'private-fixture@example.org', blob)
            self.assertIn(b'contact removed', blob)


if __name__ == '__main__':
    unittest.main()
