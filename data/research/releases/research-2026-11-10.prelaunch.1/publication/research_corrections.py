"""Validated public correction metadata; unpublished proposals remain private.

Legacy seven-field records remain valid even when their old claim is no longer
in the current graph. A replacement is optional, but must name a distinct,
currently approved assertion when a correction is accepted or published.
"""
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, unquote, parse_qsl

REQUIRED = {'id', 'edition_id', 'claim_id', 'status', 'summary', 'corrected_on', 'evidence_urls'}
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]*')
EMAIL = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}", re.I)
SECRET = re.compile(r'(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')


def _public_text(value):
    return SECRET.sub('[credential removed]', EMAIL.sub('[contact removed]', value))


def _safe_url(value):
    try:
        parsed = urlsplit(value)
        parsed.port  # Force validation; urlsplit otherwise accepts invalid ports.
        decoded = unquote(value)
        secret_keys = {'token', 'access_token', 'api_key', 'apikey', 'authorization', 'signature', 'x-amz-signature'}
        return (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                and not parsed.password and not re.search(r'[\x00-\x20\\]', value)
                and not EMAIL.search(decoded) and not SECRET.search(decoded)
                and not any(key.lower() in secret_keys for key, _ in parse_qsl(parsed.query)))
    except (TypeError, ValueError):
        return False


def correction_records(context):
    rows = context.get('corrections', [])
    if not isinstance(rows, list):
        raise ValueError('Research corrections must be a list')
    approved = {row['id']: row for row in context.get('graph', {}).get('assertions', []) if row.get('status') == 'approved'}
    reviews = {row['id']: row for row in context.get('graph', {}).get('reviews', [])}
    accepted, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not REQUIRED <= set(row) or set(row) - REQUIRED - {'replacement_claim_id'}:
            raise ValueError('Research correction has unexpected or missing fields')
        for key in ('id', 'edition_id', 'claim_id', *(['replacement_claim_id'] if 'replacement_claim_id' in row else [])):
            if not isinstance(row[key], str) or not IDENTIFIER.fullmatch(row[key]):
                raise ValueError('Research correction requires stable record identifiers')
        if row['id'] in seen:
            raise ValueError('Research correction IDs must be unique')
        seen.add(row['id'])
        if not isinstance(row['status'], str) or row['status'] not in {'accepted', 'published', 'pending', 'rejected'}:
            raise ValueError('Research correction has an unknown status')
        if not isinstance(row['summary'], str) or not row['summary'].strip():
            raise ValueError('Research correction requires a summary')
        try:
            instant = datetime.fromisoformat(row['corrected_on'].replace('Z', '+00:00'))
            if instant.utcoffset() is None:
                raise ValueError('Timezone required')
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError('Research correction requires a timezone-aware corrected_on timestamp') from error
        evidence = row['evidence_urls']
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(url, str) or not _safe_url(url) for url in evidence)
                or len(evidence) != len(set(evidence))):
            raise ValueError('Research correction requires distinct safe HTTPS evidence URLs')
        if row['status'] in {'accepted', 'published'}:
            replacement = row.get('replacement_claim_id')
            if replacement is not None and (replacement == row['claim_id'] or replacement not in approved):
                raise ValueError('Research correction replacement must name a distinct approved assertion')
            if replacement is not None:
                receipts = [reviews.get(rid, {}) for rid in approved[replacement].get('review_ids', [])]
                try:
                    approved_times = [datetime.fromisoformat(receipt['reviewed_on'].replace('Z', '+00:00'))
                                      for receipt in receipts if receipt.get('verdict') == 'pass']
                    if not approved_times or any(value.utcoffset() is None for value in approved_times):
                        raise ValueError('Missing approval timestamp')
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError('Research correction replacement requires passing review timestamps') from error
                if instant < max(approved_times):
                    raise ValueError('Research correction cannot predate its replacement approval')
            public = {**row, 'summary': _public_text(row['summary']),
                      'corrected_on': instant.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'),
                      'evidence_urls': list(evidence)}
            accepted.append({**public, 'instant': instant.astimezone(timezone.utc)})
    return sorted(accepted, key=lambda row: (-row['instant'].timestamp(), row['id']))


def public_corrections(context):
    """JSON-ready allowlisted records, without private proposals or raw paths."""
    return [{key: value for key, value in row.items() if key != 'instant'} for row in correction_records(context)]
