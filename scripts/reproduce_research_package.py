#!/usr/bin/env python3
"""Verify a downloaded research package and reproduce its public tables offline."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3


def verify_frozen_audits(directory, projection):
    """Verify admitted frozen receipts and recompute their finite-panel numbers.

    Deliberately not the live-current-input validator: withheld wording and raw
    third-party source responses are not redistributed in a public archive.
    """
    from screening_audit_v2 import (load_exact, canonical_hash, byte_hash, _shape,
                                    _safe_public, recompute_screening, CODE_FILES as SCREEN_CODE)
    from reference_audit_v3 import (recompute_reference, CODE_FILES as REFERENCE_CODE)
    from research_graph import assertion_digest

    directory = Path(directory)
    context = load_exact((directory / 'source-context.json').read_bytes())
    # These are separate immutable members of the edition manifest. Comparing
    # the public graphs also covers projected group-review notes and scopes;
    # their raw private original review hashes cannot be replayed from an export.
    if 'graph' in context and context['graph'] != projection['graph']:
        raise ValueError('Public export graph differs from its frozen source context')
    policy = context.get('policy', {})
    inputs = policy.get('audit_inputs', {})
    registry = load_exact((directory / 'audit-admissions.json').read_bytes())
    if (set(registry) != {'schema_version', 'admissions'} or registry['schema_version'] != '1.0.0'
            or registry['admissions'] != policy.get('audit_admissions', {})):
        raise ValueError('Frozen independent admission registry differs from its context')
    required = context.get('gate', {}).get('archival_ready') is True
    results = {}
    for kind, version, code_files, scorer in (
            ('reference', 'reference-audit-v3', REFERENCE_CODE, recompute_reference),
            ('screening', 'screening-audit-v2', SCREEN_CODE, recompute_screening)):
        if kind not in inputs:
            if required:
                raise ValueError('Passing archival context lacks actual ' + kind + ' audit')
            results[kind] = {'status': 'not_supplied'}
            continue
        raw = inputs[kind]['audit_json'].encode('utf-8')
        receipt_bytes = inputs[kind]['validation_receipt_json'].encode('utf-8')
        audit, receipt = load_exact(raw), load_exact(receipt_bytes)
        audit_safe = _safe_public
        audit_shape = _shape
        if kind == 'reference' and audit.get('schema_version') == 'reference-audit-v4':
            from reference_audit_v4 import (recompute_reference as recompute_initial,
                                            CODE_FILES as INITIAL_CODE, POPULATION_RULE,
                                            POPULATION_PINS, _safe_public as initial_safe,
                                            _shape as initial_shape, entity_identity)
            audit_safe, audit_shape = initial_safe, initial_shape
            version, code_files, scorer = 'reference-audit-v4', INITIAL_CODE, recompute_initial
            if not isinstance(context.get('graph'), dict):
                raise ValueError('Frozen v4 requires its exact public source context graph')
        if kind == 'screening' and audit.get('schema_version') == 'screening-audit-v3':
            from screening_audit_v3 import (recompute_screening as recompute_repeat,
                                            CODE_FILES as REPEAT_CODE,
                                            _safe_public as repeat_safe, _shape as repeat_shape)
            audit_safe, audit_shape = repeat_safe, repeat_shape
            version, code_files, scorer = 'screening-audit-v3', REPEAT_CODE, recompute_repeat
        admission = registry['admissions'].get(kind)
        if not isinstance(admission, dict):
            raise ValueError('Missing separately reviewed frozen ' + kind + ' admission')
        schema_name = ('reference-audit.v4.schema.json' if version == 'reference-audit-v4' else
                       'reference-audit.v3.schema.json' if kind == 'reference' else
                       'screening-audit.v3.schema.json' if version == 'screening-audit-v3' else
                       'screening-audit.v2.schema.json')
        schema = load_exact((directory / schema_name).read_bytes())
        if (audit_shape(audit, schema) or audit_safe(audit) or audit_safe(receipt) or audit_safe(admission)
                or audit.get('schema_version') != version or audit.get('kind') != kind
                or audit.get('actual_execution') is not True or audit.get('fixture') is not False
                or audit.get('release_id') != projection['graph']['release_id']):
            raise ValueError('Invalid frozen actual ' + kind + ' audit')
        # These exact reviewed original paths map to owned flat archive members.
        # Submitted receipt fields cannot select another code allowlist or path.
        pins = {name: byte_hash((directory / Path(name).name).read_bytes()) for name in code_files}
        if (receipt.get('validator_code_pins') != pins
                or receipt.get('audit_sha256') != byte_hash(raw)
                or receipt.get('method_sha256') != canonical_hash(audit['method'])
                or audit.get('method_sha256') != canonical_hash(audit['method'])
                or receipt.get('validation_errors') != []):
            raise ValueError('Frozen actual validation receipt/code/method has changed or contains holds')
        validation = receipt.get('validation_run', {})
        receipt_version = ('reference-private-validation-v4' if version == 'reference-audit-v4' else
                           'reference-private-validation-v3' if kind == 'reference' else
                           'screening-private-validation-v2' if version == 'screening-audit-v3' else
                           'screening-private-validation-v1')
        admission_version = ('reference-audit-admission-v4' if version == 'reference-audit-v4' else
                             'reference-audit-admission-v3' if kind == 'reference' else
                             'screening-audit-admission-v2' if version == 'screening-audit-v3' else
                             'screening-audit-admission-v1')
        if (validation.get('actual_execution') is not True or validation.get('fixture') is not False
                or receipt.get('schema_version') != receipt_version
                or admission.get('schema_version') != admission_version
                or admission.get('status') != 'accepted' or admission.get('completion_authorized') is not True
                or admission.get('audit_sha256') != byte_hash(raw)
                or admission.get('receipt_sha256') != byte_hash(receipt_bytes)
                or admission.get('validator_capsule_sha256') != canonical_hash(pins)
                or admission.get('method_adoption_sha256') != audit['method']['adoption_sha256']
                or admission.get('validation_invocation_id') != validation.get('invocation_id')
                or not admission.get('independent_review_invocation_id')
                or admission['independent_review_invocation_id'] == validation.get('invocation_id')):
            raise ValueError('Frozen execution lacks its exact separately admitted completion')
        if kind == 'reference':
            if version == 'reference-audit-v4':
                method = audit['method']
                if (method.get('population_rule') != POPULATION_RULE
                        or admission.get('population_rule') != POPULATION_RULE
                        or receipt.get('population_authentication_sha256') != canonical_hash(
                            {field: method[field] for field in POPULATION_PINS})
                        or any(method[field] != audit['artifacts'].get(artifact)
                               for field, artifact in POPULATION_PINS.items())
                        or any(admission.get(field) != method[field] for field in (
                            'population_review_sha256', 'lineage_manifest_sha256', 'metadata_adaptations_sha256'))):
                    raise ValueError('Frozen initial-hypothesis population or independent review bindings differ')
            source_digests = sorted({pin['response_sha256'] for binding in audit['bindings']
                                     for pin in binding['source_pins']})
            if (receipt.get('sample_bindings_sha256') != canonical_hash(audit['bindings'])
                    or receipt.get('artifact_commitments_sha256') != canonical_hash(audit['artifacts'])
                    or admission.get('exposure_review_sha256') != audit['exposure_registry']['semantic_review_sha256']):
                raise ValueError('Frozen reference originals or exposure review differ')
            public = {row['id']: row for row in projection['graph']['assertions']}
            public_sources = {row['id']: row for row in projection['graph']['sources']}
            public_entities = {row['id']: row for row in projection['graph']['entities']}
            public_reviews = {row['id']: row for row in projection['graph']['reviews']}
            for binding in audit['bindings']:
                row = public.get(binding['assertion_id'])
                if binding['observed_positive']:
                    if row is None or assertion_digest(row) != binding['scientific_sha256']:
                        raise ValueError('Public retained finding differs from its admitted scientific binding')
                elif row is not None:
                    raise ValueError('A formerly withheld sampled finding is present in this projection')
                if version == 'reference-audit-v4':
                    if row is not None:
                        if row['status'] != binding['original_status']:
                            raise ValueError('Public retained status differs from its admitted binding')
                        for review_id in binding['original_review_record_sha256']:
                            review = public_reviews.get(review_id)
                            if (review_id not in row['review_ids'] or review is None
                                    or row['id'] not in review['assertion_ids']
                                    or review['assertion_sha256'].get(row['id']) != binding['scientific_sha256']):
                                raise ValueError('Public projected review loses its admitted scientific binding')
                    # Withheld-only sources can be absent from a public export;
                    # every available record still has its exact original pin.
                    for source_id, expected in binding['source_record_sha256'].items():
                        source = public_sources.get(source_id)
                        if (row is not None and source is None) or (source is not None
                                and canonical_hash(source) != expected):
                            raise ValueError('Public source record differs from its admitted binding')
                    for entity_id, expected in binding['entity_identity_sha256'].items():
                        entity = public_entities.get(entity_id)
                        if (row is not None and entity is None) or (entity is not None
                                and canonical_hash(entity_identity(entity)) != expected):
                            raise ValueError('Public entity identity differs from its admitted binding')
        else:
            source_digests = sorted({source['response_sha256'] for source in audit['sources']})
            if receipt.get('private_artifact_pins_sha256') != canonical_hash(audit['artifact_commitments']):
                raise ValueError('Frozen screening original artifact commitments differ')
        if receipt.get('source_authentication_sha256') != canonical_hash(source_digests):
            raise ValueError('Frozen source-response authentication commitment differs')
        metrics = scorer(audit, thresholds=policy.get('launch_floors'))
        if (metrics.get('numerical_thresholds_met') is not True or metrics['critical_false_attributions']
                or metrics['unresolved_critical_attributions']
                or metrics.get('frame_critical_false_attributions', 0)
                or metrics.get('frame_unresolved_conclusive_attributions', 0)
                or (kind == 'reference' and not metrics['observed_withheld'])):
            raise ValueError('Frozen audit misses unchanged quality/completion floors')
        results[kind] = {'status': 'admitted_frozen_receipt_verified', 'metrics': metrics}
    return {'scope': 'admitted_frozen_receipts_and_public_retained_findings',
            'live_private_withheld_records_revalidated': False, 'raw_sources_revalidated': False,
            'audits': results}


def from_rows(rows):
    result, collections = {}, {}
    for collection, position, kind, payload in rows:
        if int(position) == -1:
            collections[collection] = {"kind": kind, "values": {}}
        else:
            collections[collection]["values"][int(position)] = json.loads(payload)
    for collection, item in collections.items():
        values = [item["values"][index] for index in sorted(item["values"])]
        value = values if item["kind"] == "array" else values[0]
        if collection.startswith(("canonical.", "graph.")):
            namespace, name = collection.split(".", 1)
            result.setdefault(namespace, {})[name] = value
        else:
            result[collection] = value
    return result


def verify(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "MANIFEST.json").read_text())
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if directory not in path.parents or not path.is_file():
            raise ValueError("Missing or unsafe package file: " + name)
        blob = path.read_bytes()
        if len(blob) != expected["bytes"] or hashlib.sha256(blob).hexdigest() != expected["sha256"]:
            raise ValueError("Package checksum mismatch: " + name)
    projection = json.loads((directory / "clean-dataset.json").read_text())
    with (directory / "clean-dataset.csv").open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.reader(stream))[1:]
    with sqlite3.connect((directory / "clean-dataset.sqlite").as_uri() + "?mode=ro", uri=True) as database:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        sql_rows = database.execute("SELECT collection, position, kind, value_json FROM projection_rows ORDER BY collection,position").fetchall()
    if from_rows(csv_rows) != projection or from_rows(sql_rows) != projection:
        raise ValueError("JSON, CSV and SQLite disagree")
    # This module is shipped alongside the package. It uses only the standard library.
    from research_graph import validate_graph, coverage_summary
    validate_graph(projection["graph"])
    summary = {"status": "verified", "release_id": manifest["release_id"],
            "files_verified": len(manifest["files"]), "exports_equivalent": True,
            "coverage": coverage_summary(projection["graph"]),
            "provenance": "The public projection is verified. Original private raw inputs are not revalidated."}
    if manifest.get('context_contract_version', 1) >= 4:
        summary['audit_verification'] = verify_frozen_audits(directory, projection)
    return summary, projection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--write-tables", type=Path)
    args = parser.parse_args()
    summary, projection = verify(args.directory)
    if args.write_tables:
        args.write_tables.mkdir(parents=True, exist_ok=True)
        (args.write_tables / "coverage.json").write_text(json.dumps(summary["coverage"], indent=2, sort_keys=True) + "\n")
        with (args.write_tables / "approved-assertions.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["id", "subject", "predicate", "object", "value", "qualifications"])
            for row in sorted(projection["graph"]["assertions"], key=lambda item: item["id"]):
                if row["status"] == "approved":
                    writer.writerow([row["id"], row["subject_id"], row["predicate"], row["object_id"] or "",
                                     json.dumps(row["value"], sort_keys=True), "; ".join(row["qualifications"])])
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
