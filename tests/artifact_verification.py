"""Verify editable-source provenance and every deterministic build output."""
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from observatory import build


def verify_undated_research_metadata(directory, url, graph):
    """An absent lastmod is allowed only for a genuinely unreviewed record."""
    path = urlsplit(url).path
    assert re.fullmatch(r'/research/(papers|datasets|benchmarks|workflows)/[^/]+/', path), url
    entity_id = unquote(path.rstrip('/').rsplit('/', 1)[1])
    assert any(row['id'] == entity_id for row in graph['entities']), entity_id
    related = {entity_id} | {row['id'] for row in graph['entities'] if row.get('parent_id') == entity_id}
    assert not any(row.get('status') == 'approved'
                   and (row['subject_id'] in related or row.get('object_id') in related)
                   for row in graph['assertions']), 'Reviewed research record lacks lastmod: ' + url
    html = (Path(directory) / path.lstrip('/') / 'index.html').read_text()
    assert 'No approved assertions are available for this record.' in html, url
    nodes = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert nodes, 'Undated record lacks structured metadata: ' + url
    for node in nodes:
        assert 'dateModified' not in json.loads(node), 'Unknown date was fabricated in structured metadata: ' + url


def verify_artifact(destination, source_paths=()):
    destination = Path(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    for name in source_paths:
        expected = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert manifest["source_sha256"].get(name) == expected, "Build source provenance differs: " + name
    with tempfile.TemporaryDirectory(prefix="verify-frontend-") as temporary:
        fresh = Path(temporary)
        build(json.loads((ROOT / "data/canonical.json").read_text()), fresh)
        expected = json.loads((fresh / "manifest.json").read_text())
        assert manifest == expected, "Built manifest differs from a fresh deterministic build"
        for name, digest in expected["sha256"].items():
            actual = destination / name
            assert actual.is_file() and hashlib.sha256(actual.read_bytes()).hexdigest() == digest, "Built output differs from a fresh deterministic build: " + name
    return manifest
