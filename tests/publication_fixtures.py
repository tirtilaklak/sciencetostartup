"""TEST-ONLY source roots use the same required owned inputs as real packages."""
from pathlib import Path
import atexit
import copy
from functools import lru_cache
import hashlib
import json
import tempfile

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _public_font_inputs():
    """Only licensed static fonts, authenticated by the public package pins."""
    import research_edition_replay as replay
    from research_citations import REPRODUCTION_INPUTS
    selector = replay._path(ROOT, replay.SOURCE_SELECTOR)
    if not selector.exists():
        return {}
    source = replay._json(selector.read_bytes())
    selected = replay._selection(ROOT, source['current_release_id'])
    package = replay._path(ROOT, selected['path'])
    manifest_bytes = (package / 'MANIFEST.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != selected['manifest_sha256']:
        raise ValueError('TEST-ONLY public font manifest differs from source-selected pins')
    manifest = replay._json(manifest_bytes)
    fonts = {}
    for name, relative in REPRODUCTION_INPUTS.items():
        if relative.startswith('data/research/fonts/'):
            blob = replay._path(package, name).read_bytes()
            pin = manifest['files'][name]
            if hashlib.sha256(blob).hexdigest() != pin['sha256'] or len(blob) != pin['bytes']:
                raise ValueError('TEST-ONLY public font differs from its manifest')
            fonts[name] = blob
    return fonts


def populate_owned_inputs(destination):
    from research_citations import REPRODUCTION_INPUTS
    destination = Path(destination)
    if destination.resolve() == ROOT:
        raise ValueError('TEST-ONLY owned inputs require an isolated source root')
    public_fonts = _public_font_inputs()
    # Empty synthetic graphs have no real admissions or locator repairs. Never
    # read the private authoring sidecars, even when a developer has them locally.
    synthetic = {
        'audit-admissions.json': {'schema_version': '1.0.0', 'admissions': {}},
        'source-manifestations.json': {
            'schema_version': 'source-manifestations-1',
            'extractor_archive_member': 'research_manifestations.py',
            'raw_source_bodies_redistributed': False,
            'extraction_is_not_source_review': True,
            'sources': [], 'assertion_bindings': []},
    }
    for name, relative in REPRODUCTION_INPUTS.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if name in synthetic:
            target.write_text(json.dumps(synthetic[name], sort_keys=True, indent=2) + '\n')
        elif name in public_fonts:
            target.write_bytes(public_fonts[name])
        else:
            target.write_bytes((ROOT / relative).read_bytes())


def isolated_owned_input_root():
    """Keep every default synthetic context off the actual source checkout."""
    temporary = tempfile.TemporaryDirectory(prefix='TEST-ONLY-owned-inputs-')
    try:
        populate_owned_inputs(temporary.name)
    except BaseException:
        temporary.cleanup()
        raise
    # Contexts can outlive a helper call; clean them after the test process ends.
    atexit.register(temporary.cleanup)
    return temporary.name


def legacy_context_fixture(context, version, *, files=None, reservation=True):
    """TEST-ONLY historical envelope, never the fresh publication API.

    The synthetic empty-graph fixtures use a declared, pinned legacy projection
    recipe. No historical research package or production recipe is rewritten.
    """
    import research_citations as citations
    if type(version) is not int or version not in {1, 2, 3, 4, 5}:
        raise ValueError('TEST-ONLY legacy context version required')
    value = citations._research_source_context(context, reservation=reservation,
        version=version, frozen_graph_version='1.0.0' if version >= 2 else None)
    if version >= 2:
        owned = copy.deepcopy(files if files is not None else
                              citations.reproduction_files(context, version=version))
        code = owned['research_graph.py'].decode()
        marker = 'PUBLIC_PROJECTION_VERSION = "1.2.0"'
        if version < 5 and marker in code:
            code = code.replace(marker, 'PUBLIC_PROJECTION_VERSION = "1.0.0"', 1)
        owned['research_graph.py'] = code.encode()
        schema = json.loads(owned['publication-projection.schema.json'])
        if version < 5:
            schema['properties']['projection_version']['const'] = '1.0.0'
            owned['publication-projection.schema.json'] = citations.json_bytes(schema)
        if files is not None:
            files.update({name: owned[name] for name in citations._reproduction_inputs(version)})
        value['package_context'] = {'context_contract_version': version,
            'graph_projection': 'approved-historical-report-v2' if version >= 5 else 'approved-historical-report-v1' if version >= 3 else 'approved-historical-v1',
            'reproduction_inputs': {name: {'sha256': citations.sha256(owned[name]), 'bytes': len(owned[name])}
                                   for name in sorted(citations._reproduction_inputs(version))}}
        if version >= 5:
            value['package_context']['graph_projection_version'] = '1.2.0'
    return value
