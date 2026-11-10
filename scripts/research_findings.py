"""Shared, fail-closed selection of evidence-bound executive judgments."""
from collections import Counter
import re

FINDING_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
JUDGMENT_FIELDS = (("buyer_implication", "Buyer implication"), ("limitations", "Limitations"),
                   ("confidence", "Confidence"), ("reasoning", "Reasoning"),
                   ("what_would_change", "What would change this assessment"))
WITHHELD = "A proposed executive finding is withheld because its identifier, required fields or approved evidence are incomplete."
WITHHELD_PARAGRAPH = "A proposed finding is withheld because its evidence is not approved for publication."


def paragraph_supported(context, paragraph):
    """Apply the same evidence rule to live, offline and PDF report blocks."""
    ids = paragraph.get("claim_ids", [])
    claims = {row["id"]: row for row in context["graph"].get("assertions", [])}
    valid = all(claims.get(cid, {}).get("status") == "approved" or
                (claims.get(cid, {}).get("status") == "historical" and
                 paragraph.get("historical") is True) for cid in ids)
    return valid and (paragraph.get("kind") != "sourced_fact" or bool(ids))


def field_text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "; ".join(item.strip() for item in value if item.strip())
    return ""


def finding_anchor(finding):
    return "finding-" + finding["id"]


def executive_findings(context):
    """Return (supported findings, withheld count), never unsupported wording.

    This supplements, rather than replaces, graph validation and publication gates.
    Duplicate identifiers withhold every affected finding so links stay unique.
    """
    rows = context["report"].get("executive_findings", [])
    if not isinstance(rows, list):
        return [], 1
    if context.get('gate', {}).get('report_review_ready') is False:
        return [], len(rows)
    counts = Counter(row.get("id") for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str))
    claims = {row["id"]: row for row in context["graph"].get("assertions", [])}
    approved = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid, ids = row.get("id"), row.get("claim_ids")
        if (not isinstance(fid, str) or not FINDING_ID.fullmatch(fid) or counts[fid] != 1
                or not all(field_text(row.get(key)) for key in ("text", "buyer_implication", "limitations"))
                or not isinstance(ids, list) or not ids or any(not isinstance(cid, str) for cid in ids)
                or len(ids) != len(set(ids))
                or any(claims.get(cid, {}).get("status") != "approved" for cid in ids)):
            continue
        approved.append({**row, "claim_ids": list(ids)})
    return approved, len(rows) - len(approved)
