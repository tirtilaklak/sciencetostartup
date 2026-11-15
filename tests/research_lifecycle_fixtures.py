"""TEST-ONLY rendering copies must never inherit a real publication receipt."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile


def isolated_render_context(baseline):
    """Keep source evidence while resetting publication state before mutation.

    Rendering tests edit graph/report content. A real receipt, frozen-package
    selection or historical replay belongs only to its exact reviewed inputs.
    """
    from research_report import publication_gate

    context = copy.deepcopy(baseline)
    context['report'].update(status='prelaunch', archive={'status': 'not_published', 'doi': None}, editions=[])
    context['edition_snapshots'] = {}
    for key in ('prepared_package', 'prepared_package_expected',
                'published_edition_replay', 'replay_verification',
                'published_source_selection', 'public_edition_ledger'):
        context.pop(key, None)
    context['policy']['mode'] = 'prepare_only'
    # A mutable rendering fixture cannot reuse frozen/private audit acceptance
    # or the real initial-launch authorization as fresh candidate authority.
    for key in ('audits', 'audit_inputs', 'audit_admissions', 'initial_launch_authorization'):
        context['policy'].pop(key, None)
    context['gate'] = publication_gate(context['graph'], context['report'], context['policy'])
    return context


@contextmanager
def isolated_render_preparation(baseline, *, canonical_bytes):
    """TEST-ONLY held preparation, including a public-only owned recipe root.

    Private authoring tests keep their original root. Verified public replay may
    supply only its authenticated owned package members; no private input or
    alternate recipe is discovered to make a preparation pass.
    """
    if baseline.get('published_edition_replay') is None:
        yield isolated_render_context(baseline)
        return

    import research_citations as citations
    from research_edition_replay import read_replay_package

    files = read_replay_package(baseline)
    prepared = json.loads(files['PREPARED.json'])
    if prepared.get('context_contract_version') != citations.CONTEXT_CONTRACT_VERSION:
        raise ValueError('TEST-ONLY preparation requires a compatible current public owned recipe')
    current_root = Path(__file__).resolve().parents[1]
    for name, relative in citations.REPRODUCTION_INPUTS.items():
        if name not in files or not isinstance(files[name], bytes):
            raise ValueError('Missing verified public owned input: ' + name)
        # Mutable data/font inputs come only from the verified public capsule.
        # Required static code/schema/docs/licenses must also match the current
        # reviewed recipe; archived Python is compared as bytes, never executed.
        # REUSE.md is a non-executed historical guide with a current erratum.
        # Keep its authenticated frozen bytes below instead of substituting it.
        if not relative.startswith('data/'):
            current = current_root / relative
            if (not current.is_file()
                    or (name != 'REUSE.md' and current.read_bytes() != files[name])):
                raise ValueError('Incompatible current public owned input: ' + name)
    if not isinstance(canonical_bytes, bytes):
        raise ValueError('Exact already-public canonical bytes are required')

    with tempfile.TemporaryDirectory(prefix='TEST-ONLY-public-render-recipe-') as temporary:
        root = Path(temporary)
        for name, relative in citations.REPRODUCTION_INPUTS.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(files[name])
        canonical = root / 'data/canonical.json'
        canonical.parent.mkdir(parents=True, exist_ok=True)
        canonical.write_bytes(canonical_bytes)
        # The copied public admission provenance is not fresh authority for a
        # mutable fixture. Its explicit empty registry matches the held policy.
        (root / citations.REPRODUCTION_INPUTS['audit-admissions.json']).write_bytes(
            citations.json_bytes({'schema_version': '1.0.0', 'admissions': {}}))
        context = isolated_render_context(baseline)
        context['root'] = root
        yield context
