"""Regression tests for candidate-only public source checks."""
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_work_sources import FetchObservation, LinkedApplicationObservation, RenderedObservation, check_route


ROLE = 'https://example.test/role'
APPLICATION = ROLE + '/apply'
OTHER_APPLICATION = ROLE + '/apply?track=other'
PUBLIC_ROLE = b'A public role description with eligibility and scope. ' * 4
UNPUBLISHED = 'この求人は現在非公開です。応募することができません。'.encode()
REGISTRATION_ERROR = 'Oops! This URL might not be the one you were looking for.'
EARLIER = '2026-11-22T05:00:00Z'
CONFIRMED = '2026-11-23T05:00:00Z'
LATER = '2026-11-24T05:00:00Z'
CHECK = '2026-11-24T06:00:00Z'


class WorkSourceCheckerTests(unittest.TestCase):
    def observe(self, key, *, previous=None, timestamp=CONFIRMED, failed=True, url=None, source_url=ROLE, final_url=ROLE):
        route = {'id': 'fixture', 'url': ROLE, 'sources': [{'url': APPLICATION}, {'url': OTHER_APPLICATION}]}
        options = {}
        if key == 'application_check':
            primary = PUBLIC_ROLE
            if timestamp is not None:
                url = url or APPLICATION
                response = FetchObservation(403 if failed else 200, url, UNPUBLISHED if failed else PUBLIC_ROLE)
                options['application'] = LinkedApplicationObservation(source_url, url, timestamp, response)
        else:
            primary = b'Enable JavaScript to run'
            if timestamp is not None:
                options['rendered'] = RenderedObservation(url or final_url, timestamp, REGISTRATION_ERROR if failed else 'Create an account')
        return check_route(route, CHECK, previous, lambda _: FetchObservation(200, final_url, primary), **options)

    def test_null_prior_secondary_receipts_are_valid_baselines(self):
        for key, result, reason, signal, digest_field, evidence in (
            ('application_check', 'readable', 'content_changed', 'linked_application_unpublished', 'response_sha256', UNPUBLISHED),
            ('rendered_observation', 'unreadable_shell', 'recheck_failed', 'registration_soft_error',
             'visible_text_sha256', REGISTRATION_ERROR.encode()),
        ):
            with self.subTest(stage=key):
                previous = {**self.observe(key, timestamp=None), key: None}
                observed = self.observe(key, previous=previous)
                self.assertEqual((observed['result'], observed['candidate_reason']), (result, reason))
                self.assertEqual(observed['review_signals'], [signal])
                self.assertEqual(observed[key]['checked_at'], CONFIRMED)
                self.assertEqual(observed[key][digest_field], hashlib.sha256(evidence).hexdigest())
                self.assertFalse(observed['approved'])
                self.assertTrue(observed['editorial_review_required'])
                self.assertIsNone(previous[key])

    def test_stale_and_tied_conflicting_receipts_keep_confirmed_evidence(self):
        for key, unchanged, changed in (
            ('application_check', 'unchanged', 'content_changed'),
            ('rendered_observation', 'unchanged_failure', 'recheck_failed'),
        ):
            for failed in (False, True):
                with self.subTest(stage=key, confirmed_failure=failed):
                    confirmed = self.observe(key, failed=failed)
                    saved = self.observe(key, previous=confirmed, timestamp=None)
                    self.assertEqual(saved[key], {**confirmed[key], 'reobserved': False})

                    for stamp in (EARLIER, CONFIRMED.replace('Z', '.000Z'), CONFIRMED):
                        stale = self.observe(key, previous=saved, timestamp=stamp, failed=not failed)
                        self.assertEqual(stale['candidate_reason'], unchanged, stamp)
                        self.assertEqual(stale[key], saved[key], stamp)
                        self.assertEqual(stale['review_signals'], [], stamp)

                    retry = self.observe(key, previous=saved, failed=failed)
                    self.assertEqual(retry[key], confirmed[key])
                    self.assertEqual(retry['candidate_reason'], unchanged)
                    self.assertEqual(retry['review_signals'], confirmed['review_signals'])

                    newer = self.observe(key, previous=saved, timestamp=LATER, failed=not failed)
                    self.assertEqual(newer[key]['checked_at'], LATER)
                    self.assertNotIn('reobserved', newer[key])
                    self.assertEqual(newer['candidate_reason'], changed)

    def test_invalid_attempt_preserves_history_and_different_bound_url_has_own_timestamp(self):
        for key, invalid_url, alternate_url in (
            ('application_check', ROLE + '/unbound', OTHER_APPLICATION),
            ('rendered_observation', ROLE + '/unrelated', ROLE + '/register'),
        ):
            with self.subTest(stage=key):
                previous = self.observe(key)
                for options in ({'timestamp': '2026-11-25T05:00:00Z'}, {'timestamp': '2026-11-31T05:00:00Z'}, {'url': invalid_url}):
                    rejected = self.observe(key, previous=previous, failed=False, **options)
                    self.assertEqual(rejected[key], {**previous[key], 'reobserved': False}, options)
                    self.assertEqual(rejected['review_signals'], [], options)

                alternate = {'url': alternate_url} if key == 'application_check' else {'final_url': alternate_url}
                observed = self.observe(key, previous=previous, timestamp=EARLIER, failed=False, **alternate)
                self.assertEqual((observed[key]['url'], observed[key]['checked_at']), (alternate_url, EARLIER))

    def test_provider_challenge_and_proxy_errors_are_distinct_from_missing_and_closed(self):
        route = {'id': 'fixture', 'url': ROLE}
        for status, body, result, reason, signals in (
            (404, b'<script src="captcha.js"></script><h1>Not found</h1>', 'not_found', 'http_not_found', []),
            (404, b'<title>Just a moment</title><h1>This listing has closed.</h1>', 'blocked', 'access_restricted', []),
            (407, b'<h1>Proxy Authentication Required</h1>', 'blocked', 'access_restricted', []),
            (502, b'<h1>Bad Gateway</h1>', 'unavailable', 'http_error', []),
            (200, b'<h1>This listing has closed.</h1>', 'readable', 'public_document', ['explicitly_closed']),
        ):
            with self.subTest(status=status, body=body):
                observed = check_route(route, CHECK, fetcher=lambda url: FetchObservation(status, url, body))
                self.assertEqual((observed['result'], observed['retrieval_reason'], observed['review_signals']),
                                 (result, reason, signals))
