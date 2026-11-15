"""TEST-ONLY source roots use the same required owned inputs as real packages."""
from pathlib import Path
import copy
import json

ROOT = Path(__file__).resolve().parents[1]


def populate_owned_inputs(destination):
    from research_citations import REPRODUCTION_INPUTS
    destination = Path(destination)
    if destination.resolve() == ROOT:
        raise ValueError('TEST-ONLY owned inputs require an isolated source root')
    for relative in REPRODUCTION_INPUTS.values():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    # A synthetic source root has no actual audit admissions. Do not borrow the
    # live repository's separately admitted scientific execution as test data.
    (destination / 'data/research/audit-admissions.json').write_text(
        json.dumps({'schema_version': '1.0.0', 'admissions': {}}, sort_keys=True, indent=2) + '\n')


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
