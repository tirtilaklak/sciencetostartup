"""Proposed version dispatch; the central publication gate does not call it yet.

Exact public bytes and independently reviewed trust rows are explicit inputs.
No candidate document can choose its own trust registry entry or fallback reader.
"""
from __future__ import annotations

from screening_audit_v2 import VERSION as SCREENING_VERSION, load_exact, validate_public_screening_audit


def validate_audit(kind, audit_bytes, graph, thresholds, *, validation_receipt_bytes=None,
                   trusted_admission=None, legacy_reader=None, reference_reader=None):
    if kind not in {"reference", "screening"}:
        return ["Unknown audit kind"], {}
    if audit_bytes is None:
        return [f"Actual {kind} audit has not been supplied."], {}
    try:
        audit = load_exact(audit_bytes)
        if not isinstance(audit, dict) or audit.get("kind") != kind:
            return ["Audit kind differs from its authoritative gate slot"], {}
        version = audit.get("schema_version")
        if "schema_version" not in audit:
            if legacy_reader is None:
                return ["Legacy audit reader was not supplied"], {}
            return legacy_reader(audit, kind, graph, thresholds)
        if version == SCREENING_VERSION and kind == "screening":
            if validation_receipt_bytes is None:
                return ["Separate actual private-validation receipt is required"], {}
            return validate_public_screening_audit(audit_bytes, graph, validation_receipt_bytes,
                trusted_admission=trusted_admission, thresholds=thresholds)
        if version == "screening-audit-v3" and kind == "screening":
            if validation_receipt_bytes is None:
                return ["Separate actual private-validation receipt is required"], {}
            from screening_audit_v3 import validate_public_screening_audit as validate_repeat
            return validate_repeat(audit_bytes, graph, validation_receipt_bytes,
                trusted_admission=trusted_admission, thresholds=thresholds)
        if version == "reference-audit-v2" and kind == "reference":
            if validation_receipt_bytes is None:
                return ["Separate actual private-validation receipt is required"], {}
            # The reviewed reference proposal is not copied or implicitly
            # adopted by importing this module. Future integration must install
            # the exact reviewed reader, or explicitly inject it.
            if reference_reader is None:
                try:
                    from reference_audit_receipt import validate_public_reference_receipt
                except ImportError:
                    return ["The reviewed public reference reader has not been installed"], {}
                reference_reader = validate_public_reference_receipt
            return reference_reader(audit_bytes, graph, validation_receipt_bytes,
                trusted_admission=trusted_admission, thresholds=thresholds)
        if version == "reference-audit-v3" and kind == "reference":
            if validation_receipt_bytes is None:
                return ["Separate actual private-validation receipt is required"], {}
            from reference_audit_v3 import validate_public_reference_v3
            return validate_public_reference_v3(audit_bytes,graph,validation_receipt_bytes,
                trusted_admission=trusted_admission,thresholds=thresholds)
        if version == "reference-audit-v4" and kind == "reference":
            if validation_receipt_bytes is None:
                return ["Separate actual private-validation receipt is required"], {}
            from reference_audit_v4 import validate_public_reference_v4
            return validate_public_reference_v4(audit_bytes, graph, validation_receipt_bytes,
                trusted_admission=trusted_admission, thresholds=thresholds)
        return [f"Unsupported {kind} audit version; no legacy fallback permitted"], {}
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as error:
        return [f"Invalid audit document ({type(error).__name__})"], {}
