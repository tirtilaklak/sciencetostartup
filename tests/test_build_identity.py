"""Prevent a successful UI run from being attributed to stale or changing bytes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from build_identity import snapshot_dist, expected_browser_identity, assess_build_identity, extract_research_script


class BuildIdentityTests(unittest.TestCase):
    def fixture(self, folder):
        research = json.dumps({'dataset_version': '2.5.0', 'statement': 'Quoted < evidence'}) + '\n'
        html = '<!doctype html><script id="research-data" type="application/json">' + research.replace('<', '\\u003c') + '</script>'
        (folder / 'research.json').write_text(research)
        (folder / 'index.html').write_text(html)
        digest = lambda name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
        (folder / 'manifest.json').write_text(json.dumps({'dataset_version': '2.5.0', 'sha256': {n: digest(n) for n in ['index.html', 'research.json']}}))
        return snapshot_dist(folder)

    def browser(self, snapshot):
        expected = expected_browser_identity(snapshot)
        state = {'datasetVersion': expected['datasetVersion'], 'researchScriptSha256': expected['researchScriptSha256'], 'liveDataSemanticSha256': 'live-equals-embedded', 'fetchedResearch': {'status': 200, 'sha256': expected['researchFileSha256']}, 'matchesExpected': True, 'errors': []}
        return {'before': copy.deepcopy(state), 'after': copy.deepcopy(state)}

    def test_actual_script_escape_differs_but_semantics_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = self.fixture(Path(tmp))
            self.assertTrue(snapshot['valid'])
            self.assertTrue(snapshot['embeddedResearch']['semanticallyMatchesResearch'])
            self.assertNotEqual(snapshot['embeddedResearch']['sha256'], snapshot['files']['research.json']['sha256'])
            self.assertTrue(assess_build_identity(snapshot, snapshot, self.browser(snapshot))['passed'])

    def test_stale_loaded_script_fails_even_when_disk_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = self.fixture(Path(tmp)); browser = self.browser(snapshot)
            browser['before']['researchScriptSha256'] = 'stale-page'
            self.assertFalse(assess_build_identity(snapshot, snapshot, browser)['passed'])

    def test_disk_change_during_call_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = self.fixture(Path(tmp)); changed = copy.deepcopy(snapshot)
            changed['files']['index.html']['sha256'] = 'changed-index'
            result = assess_build_identity(snapshot, changed, self.browser(snapshot))
            self.assertFalse(result['passed']); self.assertTrue(any('changed during' in e for e in result['errors']))

    def test_missing_final_or_browser_disagreement_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = self.fixture(Path(tmp)); browser = self.browser(snapshot)
            del browser['after']
            self.assertFalse(assess_build_identity(snapshot, snapshot, browser)['passed'])
            browser = self.browser(snapshot); browser['after']['matchesExpected'] = False; browser['after']['errors'] = ['Live DATA differs from embedded script']
            self.assertFalse(assess_build_identity(snapshot, snapshot, browser)['passed'])

    def test_duplicate_script_and_crlf_handling(self):
        self.assertEqual(extract_research_script('<script id="research-data">{\r\n}</script>'), '{\n}')
        with self.assertRaises(ValueError): extract_research_script('<script id="research-data">{}</script><script id="research-data">{}</script>')


if __name__ == '__main__': unittest.main()
