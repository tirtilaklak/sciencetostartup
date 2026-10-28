"""Validate the dashboard's evidence layer without changing the canonical audit."""
import json
import math
import re
from urllib.parse import urlsplit

from observatory import SIDECAR_DATASET_VERSION

SIGNALS = {'revenue', 'profit', 'customers', 'delivery', 'cash'}


def load_business_health(path, data):
    # Fixtures and other research versions must never inherit this curated layer. After a
    # SIDECAR_DATASET_VERSION bump the source_dataset_version check below fails loudly until
    # the dashboard is rebaselined, instead of the dashboard silently disappearing.
    if data['dataset_version'] != SIDECAR_DATASET_VERSION:
        return None
    health = json.loads(path.read_text())
    if health.get('source_dataset_version') != data['dataset_version']:
        raise ValueError('business-health: source dataset version differs')
    companies = {c['id'] for c in data['companies']}
    claims = {c['id']: c for c in data['claims']}
    metrics = {m['id']: m for m in data['metrics']}
    sources = {s['id']: s for s in data['sources']}
    # New source reads supplement this dashboard, not the frozen canonical release.
    # Each new claim binds the exact quantity and period to a checked source excerpt.
    checked = {entry['source_id']: entry for entry in health.get('source_checks', {}).get('entries', [])}
    # Supplemental sources may add new primary documents, but must not replace
    # canonical URLs or bypass the successful content-read receipt requirement.
    source_ids = set()
    for source in health.get('sources', []):
        sid = source.get('id')
        if not sid or sid in source_ids:
            raise ValueError('business-health: source IDs must be unique')
        source_ids.add(sid)
        if sid in sources:
            if source.get('url') != sources[sid]['url']:
                raise ValueError('business-health: canonical source URL cannot be overridden')
            continue
        url = source.get('url', '')
        parsed = urlsplit(url)
        check = checked.get(sid, {})
        if (not sid.startswith('refresh.source.') or source.get('company_id') not in companies
                or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or any(ord(char) <= 32 for char in url)
                or not source.get('title') or not source.get('publisher')
                or check.get('url') != url or check.get('status') != 'content_checked'
                or check.get('http_status') != 200
                or not re.fullmatch(r'[a-f0-9]{64}', check.get('content_sha256', ''))):
            raise ValueError('business-health: supplemental source requires a valid checked public document')
        sources[sid] = source
    fresh_ids = set()
    for claim in health.get('fresh_claims', []):
        cid = claim.get('id')
        if not cid or cid in claims or cid in fresh_ids:
            raise ValueError('business-health: fresh claim must have a new unique ID')
        if claim.get('company_id') not in companies or claim.get('status') != 'supported':
            raise ValueError('business-health: fresh claim requires a supported company')
        if not claim.get('statement') or not claim.get('excerpt') or not claim.get('source_locator') or not claim.get('fact'):
            raise ValueError('business-health: fresh claim requires an excerpt, locator and exact fact')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', claim.get('observed_on', '')):
            raise ValueError('business-health: fresh claim requires its actual review date')
        if not claim.get('source_ids'):
            raise ValueError('business-health: fresh claim requires a source')
        for sid in claim['source_ids']:
            check = checked.get(sid, {})
            if (sid not in sources or check.get('url') != sources[sid]['url']
                    or check.get('status') != 'content_checked' or check.get('http_status') != 200
                    or (sources[sid].get('company_id') and sources[sid]['company_id'] != claim['company_id'])
                    or check.get('checked_on') != claim['observed_on']
                    or not re.fullmatch(r'[a-f0-9]{64}', check.get('content_sha256', ''))):
                raise ValueError('business-health: fresh claim requires a successfully checked source')
        claims[cid] = claim
        fresh_ids.add(cid)
    if health.get('universe_count') != len(companies):
        raise ValueError('business-health: company universe changed')
    if {s['id'] for s in health.get('signals', [])} != SIGNALS:
        raise ValueError('business-health: five signal definitions required')
    seen = set()
    for row in health.get('observations', []):
        prefix = 'business-health: ' + str(row.get('id')) + ': '
        if not row.get('id') or row['id'] in seen:
            raise ValueError(prefix + 'unique ID required')
        seen.add(row['id'])
        if row.get('company_id') not in companies or row.get('signal') not in SIGNALS:
            raise ValueError(prefix + 'unknown company or signal')
        value = row.get('value')
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError(prefix + 'finite numeric value required')
        for field in ('measure', 'label', 'unit', 'as_of', 'scope', 'accounting_basis', 'basis', 'limitations', 'original_text'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(prefix + field + ' required')
        if row.get('evidence_type') not in ('reported', 'calculated', 'estimate'):
            raise ValueError(prefix + 'evidence type required')
        if not row.get('period', {}).get('type') or not row['period'].get('label'):
            raise ValueError(prefix + 'period required')
        if not row.get('claim_ids') or not row.get('source_ids'):
            raise ValueError(prefix + 'claim and source required')
        for cid in row['claim_ids']:
            if cid not in claims or claims[cid]['company_id'] != row['company_id'] or claims[cid]['status'] != 'supported':
                raise ValueError(prefix + 'supported same-company claim required')
            if cid in fresh_ids and row['evidence_type'] != 'calculated':
                for field in ('measure', 'value', 'unit', 'currency', 'period', 'scope', 'accounting_basis'):
                    if row.get(field) != claims[cid]['fact'].get(field):
                        raise ValueError(prefix + 'fresh quantity or reporting basis differs from checked claim')
        linked_sources = {sid for cid in row['claim_ids'] for sid in claims[cid]['source_ids']}
        if any(sid not in sources or sid not in linked_sources for sid in row['source_ids']):
            raise ValueError(prefix + 'source must support the cited claim')
        for mid in row.get('metric_ids', []):
            if mid not in metrics or metrics[mid]['company_id'] != row['company_id'] or metrics[mid]['claim_id'] not in row['claim_ids']:
                raise ValueError(prefix + 'metric binding differs from cited claim')
        if row['evidence_type'] == 'calculated' and not row.get('calculation'):
            raise ValueError(prefix + 'calculation required')
    observations = {row['id']: row for row in health['observations']}
    for row in health['observations']:
        if row['evidence_type'] != 'calculated':
            continue
        prefix = 'business-health: ' + row['id'] + ': '
        inputs = row['calculation'].get('input_observation_ids', [])
        if len(inputs) != 2 or any(identifier not in observations for identifier in inputs):
            raise ValueError(prefix + 'two observed calculation inputs required')
        current, baseline = [observations[identifier] for identifier in inputs]
        if any(item['company_id'] != row['company_id'] or item['scope'] != row['scope']
               or item['qualifier'] != 'exact' or item['evidence_type'] != 'reported'
               for item in (current, baseline)):
            raise ValueError(prefix + 'calculation requires exact same-company and same-scope observations')
        if current.get('currency') != baseline.get('currency') or baseline['value'] <= 0:
            raise ValueError(prefix + 'calculation inputs require matching currencies and a positive denominator')
        if row['measure'] == 'revenue_growth_yoy':
            if (current['measure'] != 'period_revenue' or baseline['measure'] != 'period_revenue'
                    or current['accounting_basis'] != baseline['accounting_basis']
                    or current['period']['type'] != baseline['period']['type']
                    or current['period']['year'] != baseline['period']['year'] + 1
                    or any(current['period'][boundary][5:] != baseline['period'][boundary][5:]
                           for boundary in ('start', 'end'))):
                raise ValueError(prefix + 'growth inputs require matching accounting and yearly periods')
            expected = (current['value'] / baseline['value'] - 1) * 100
        elif row['measure'] in ('net_margin', 'adjusted_ebitda_margin'):
            if baseline['measure'] != 'period_revenue' or current['period'] != baseline['period']:
                raise ValueError(prefix + 'margin inputs require the same reporting period')
            expected = current['value'] / baseline['value'] * 100
        else:
            raise ValueError(prefix + 'unknown calculation measure')
        if row['unit'] != 'percent' or not math.isclose(row['value'], expected, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError(prefix + 'calculated value differs from its cited inputs')
    return health
