"""Verify the browser donor against the frozen source and serialize an independent export."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

root = Path.cwd()
bundle = Path(__file__).resolve().parent
expected = json.loads((bundle / 'expected.json').read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads((root / path).read_bytes())


def records(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''), strict=True)
    rows = list(reader)
    assert reader.fieldnames == expected['column_names']
    assert len(rows) == expected['row_count']
    assert all(len(row) == expected['column_count'] and None not in row and None not in row.values() for row in rows)
    ids = [row['route_id'] for row in rows]
    assert len(ids) == len(set(ids))
    return ids, dict(zip(ids, rows))


manifest_bytes = (root / 'dist/manifest.json').read_bytes()
manifest = json.loads(manifest_bytes)
assert digest(manifest_bytes) == expected['manifest_sha256']
assert manifest['build_id'] == expected['build']
assert manifest['editorial_release_id'] == expected['editorial_release_id']
assert read('data/editorial-release.json')['release_id'] == expected['editorial_release_id']
for file, sha in expected['exact_source_sha256'].items():
    assert digest((root / file).read_bytes()) == sha, file

sys.path.insert(0, str(root / 'scripts'))
from presentation import contact_safe_research, encoded, work_export_rows
from static_pages import Research

work = read('data/work-routes.json')
canonical = read('data/canonical.json')
projected = work_export_rows(work, Research(contact_safe_research(canonical)))
formatter = (root / 'web/work-core.js').read_text() + "\nconst rows=JSON.parse(require('node:fs').readFileSync(0,'utf8')); process.stdout.write(S2SWork.csvFor(rows,{}));"
oracle = subprocess.check_output(['node', '-e', formatter], input=encoded(projected))
donor = (bundle / 'signed-native.csv').read_bytes()
assert digest(oracle) == expected['canonical_csv_sha256']
assert digest(donor) == expected['donor_sha256']
source_ids = [row['id'] for row in work['routes']]
oracle_ids, oracle_rows = records(oracle)
donor_ids, donor_rows = records(donor)
assert len(source_ids) == len(set(source_ids)) == len(oracle_ids) == expected['row_count']
assert set(source_ids) == set(oracle_ids)
assert donor_ids == expected['ordered_ids'] and donor_rows == oracle_rows
hourly = {row['id'] for row in work['routes'] if row['pay_terms']['hourly_comparable']}
assert len(hourly) == len(expected['hourly_ids']) == 18
assert hourly == set(expected['hourly_ids'])
print(json.dumps({'rows': len(source_ids), 'columns': expected['column_count'], 'canonical_csv_sha256': digest(oracle), 'independent_csv_sha256': digest(donor)}))
