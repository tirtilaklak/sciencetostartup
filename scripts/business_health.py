"""Validate the dashboard's evidence layer without changing the canonical audit."""
import json
import math

SIGNALS = {'revenue', 'profit', 'customers', 'delivery', 'cash'}


def load_business_health(path, data):
    # Fixtures and future research versions must never inherit this curated layer.
    if data['dataset_version'] != '2.5.0':
        return None
    health = json.loads(path.read_text())
    if health.get('source_dataset_version') != data['dataset_version']:
        raise ValueError('business-health: source dataset version differs')
    companies = {c['id'] for c in data['companies']}
    claims = {c['id']: c for c in data['claims']}
    metrics = {m['id']: m for m in data['metrics']}
    sources = {s['id']: s for s in data['sources']}
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
