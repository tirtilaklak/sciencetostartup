"""Small complete generations test retention without a site build or network."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from presentation import encoded, retain_runtime_generations


class RuntimeRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source'
        self.assets = self.root / 'release-assets'
        self.assets.mkdir(parents=True)
        self.destination = Path(self.temporary.name) / 'destination'
        self.destination.mkdir()
        self.work_script = self.asset('work', b'window.WORK_NATIVE_SELECTION=[{"id":"cached-work"}];', True)
        self.generations = [self.generation('a' * 20, '11111111-1111-4111-8111-111111111111'),
                            self.generation('b' * 20, '22222222-2222-4222-8222-222222222222', work=self.work_script)]
        self.registry()

    def registry(self):
        (self.assets / 'generations.json').write_bytes(encoded({'generations': self.generations}))

    def asset(self, family, value, javascript=False):
        content = value if javascript else encoded(value) + b'\n'
        checksum = hashlib.sha256(content).hexdigest()
        name = ('js/' if javascript else 'presentation/') + family + '.' + checksum[:12 if javascript else 16] + ('.js' if javascript else '.json')
        path = self.assets / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        descriptor = {'href': '/' + name, 'sha256': checksum, 'bytes': len(content)}
        if javascript:
            descriptor['integrity'] = 'sha256-' + base64.b64encode(bytes.fromhex(checksum)).decode()
        return name, descriptor

    def generation(self, build, version, *, mismatch=False, bad_size=False, bad_sri=False, health_build=None, orphan=False,
                   work=None, work_role='nativeWork'):
        identity = dict(schemaVersion='1.0.0', buildId=build, editorialReleaseId='review-fixture', datasetVersion='2.5.0', privacyProjectionVersion='1.0.0')
        overview_name, overview = self.asset('overview', {**identity, 'buildId': 'different' if mismatch else build, 'data': {}})
        health_name, health = self.asset('health', ('(()=>{window.SCIENCE_HEALTH_MODULE={buildId:' + json.dumps(health_build or build) + ',initialize:function(){}};})();').encode(), True)
        app_name, app = self.asset('app', b'window.APP_READY=true;', True)
        if bad_size:
            overview['bytes'] += 1
        if bad_sri:
            health['integrity'] = 'sha256-invalid'
        names = [overview_name, health_name, app_name]
        modules = {'businessHealth': health}
        if work is not None:
            work_name, work_descriptor = work
            names.append(work_name)
            modules[work_role] = work_descriptor
        summary = {**identity, 'publicationAsOf': '2026-11-18T17:43:00Z', 'overview': overview, 'modules': modules, 'bootstrap': {}, 'companies': [], 'work': []}
        summary_name, summary_descriptor = self.asset('summary', summary)
        public_summary = {k: v for k, v in summary.items() if k not in ('bootstrap', 'companies', 'work')}
        public_summary['asset'] = summary_descriptor
        data_name, data = self.asset('data', b'window.SUMMARY_INDEX=' + encoded(public_summary) + b';window.EXTRA=true;', True)
        names.extend((summary_name, data_name))
        result = {'cloudflare_version': version, 'sha256': {name: hashlib.sha256((self.assets / name).read_bytes()).hexdigest() for name in names}}
        if orphan:
            orphan_name, _ = self.asset('orphan', {**identity, 'data': {}})
            result['sha256'][orphan_name] = hashlib.sha256((self.assets / orphan_name).read_bytes()).hexdigest()
        return result

    def rejected_without_copy(self, error=''):
        with self.assertRaisesRegex(ValueError, error):
            retain_runtime_generations(self.root, self.destination)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_two_complete_generations_and_identical_shared_payloads_are_retained(self):
        retain_runtime_generations(self.root, self.destination)
        shared = set(self.generations[0]['sha256']) & set(self.generations[1]['sha256'])
        self.assertTrue(any(name.startswith('js/app.') for name in shared))
        for generation in self.generations:
            for name, checksum in generation['sha256'].items():
                self.assertEqual(hashlib.sha256((self.destination / name).read_bytes()).hexdigest(), checksum)
        work_name, _ = self.work_script
        self.assertNotIn(work_name, self.generations[0]['sha256'])
        self.assertEqual((self.destination / work_name).read_bytes(), (self.assets / work_name).read_bytes())
        retain_runtime_generations(self.root, self.destination)

    def test_retention_requires_two_distinct_versions(self):
        for versions in ([], [self.generations[0]], [self.generations[0], self.generations[0]]):
            (self.assets / 'generations.json').write_bytes(encoded({'generations': versions}))
            self.rejected_without_copy()
        self.generations[0]['cloudflare_version'] = 'not-a-version'
        self.registry()
        self.rejected_without_copy()

    def test_retention_rejects_unsafe_or_nonregular_payloads(self):
        generation = self.generations[1]
        name = next(iter(generation['sha256']))
        path = self.assets / name
        content = path.read_bytes()
        outside = Path(self.temporary.name) / 'outside'
        outside.write_bytes(content)
        path.unlink()
        path.symlink_to(outside)
        self.rejected_without_copy()
        path.unlink()
        os.mkfifo(path)
        self.rejected_without_copy()
        path.unlink()
        path.write_bytes(content)
        generation['sha256']['../outside'] = 'a' * 64
        self.registry()
        self.rejected_without_copy()

    def test_retention_rejects_parent_symlinks(self):
        actual = self.assets / 'original-js'
        (self.assets / 'js').rename(actual)
        (self.assets / 'js').symlink_to(actual, target_is_directory=True)
        self.rejected_without_copy()

    def test_retention_requires_complete_summary_dependency_closure(self):
        generation = self.generations[1]
        name = next(name for name in generation['sha256'] if name.startswith('presentation/overview.'))
        generation['sha256'].pop(name)
        self.registry()
        self.rejected_without_copy()

    def test_retention_rejects_unreferenced_payloads(self):
        self.generations[1] = self.generation('b' * 20, self.generations[1]['cloudflare_version'], orphan=True)
        self.registry()
        self.rejected_without_copy()

    def test_retention_rejects_cross_generation_identity_mismatch(self):
        self.generations[1] = self.generation('b' * 20, self.generations[1]['cloudflare_version'], mismatch=True)
        self.registry()
        self.rejected_without_copy()

    def test_retention_checks_descriptor_size_sri_and_health_identity(self):
        for changes in ({'bad_size': True}, {'bad_sri': True}, {'health_build': 'different'}):
            self.generations[1] = self.generation('b' * 20, self.generations[1]['cloudflare_version'], **changes)
            self.registry()
            self.rejected_without_copy()

    def test_retention_rejects_wrong_native_work_digest_integrity_or_role(self):
        name, descriptor = self.work_script
        version = self.generations[1]['cloudflare_version']
        for role, asset, error in (
            ('nativeWork', {**descriptor, 'sha256': '0' * 64}, 'Retained runtime dependency differs'),
            ('nativeWork', {**descriptor, 'integrity': 'sha256-invalid'}, 'Retained runtime integrity differs'),
            ('work', descriptor, 'Retained native Work module descriptor differs'),
        ):
            with self.subTest(error=error):
                self.generations[1] = self.generation('b' * 20, version, work=(name, asset), work_role=role)
                self.registry()
                self.rejected_without_copy(error)

    def test_retention_rejects_changed_native_work_bytes_or_filename(self):
        name, _ = self.work_script
        path = self.assets / name
        original = path.read_bytes()
        error = r'Retained runtime checksum or filename differs: js/work\.'
        path.write_bytes(b'// changed after registry')
        self.rejected_without_copy(error)

        wrong_name = 'js/work.000000000000.js'
        path.write_bytes(original)
        path.rename(self.assets / wrong_name)
        checksums = self.generations[1]['sha256']
        checksums[wrong_name] = checksums.pop(name)
        self.registry()
        self.rejected_without_copy(error)

    def test_retention_refuses_destination_collision(self):
        name = next(iter(self.generations[1]['sha256']))
        path = self.destination / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b'preexisting different bytes')
        before = {str(p.relative_to(self.destination)): p.read_bytes() for p in self.destination.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'collision'):
            retain_runtime_generations(self.root, self.destination)
        after = {str(p.relative_to(self.destination)): p.read_bytes() for p in self.destination.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_retention_validates_every_generation_before_copying(self):
        name = next(iter(self.generations[1]['sha256']))
        (self.assets / name).write_bytes(b'changed after registry')
        self.rejected_without_copy()

    def test_retention_checks_filename_fingerprint_and_registry_json(self):
        generation = self.generations[1]
        name = next(iter(generation['sha256']))
        wrong = name.replace(name.split('.')[1], '0' * 16)
        (self.assets / name).rename(self.assets / wrong)
        generation['sha256'][wrong] = generation['sha256'].pop(name)
        self.registry()
        self.rejected_without_copy()
        (self.assets / 'generations.json').write_text('{"generations":[],"generations":[]}')
        self.rejected_without_copy()


if __name__ == '__main__':
    unittest.main()
