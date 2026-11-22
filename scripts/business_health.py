"""Validate the dashboard's evidence layer without changing the canonical audit."""
from datetime import date, datetime
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

from observatory import SIDECAR_DATASET_VERSION

SIGNALS = {'revenue', 'profit', 'customers', 'delivery', 'cash'}
SHA256 = re.compile(r'[a-f0-9]{64}')
FINANCE_DATE_ROLES = {'announcement', 'company_announcement_context', 'period_end',
                      'source_publication', 'source_check', 'undated'}
MERCOR_H1_ESTIMATE = 'mercor.metric.major-growth_metrics-1'
RWS_GENERATE_REVENUE = 'rws_trainai.claim.growth_metrics-1.metric-0'


def profile_finance_claim_context(profile):
    """Project the reviewed date and source attribution for exact claim dialogs."""
    if not profile:
        return {}
    fields = ('record_id', 'label', 'date_label', 'date_role', 'display_date', 'evidence_date', 'source_id', 'source_published_on',
              'source_accessed_on', 'source_checked_on', 'source_status', 'note', 'scope')
    return {cid: {**{field: fact.get(field) for field in fields}, 'attribution': fact['claimant']}
            for fact in (profile['headline'], *profile['native_detail_records']) if fact
            for cid in fact.get('claim_ids', [])}


def _finance_day(value):
    if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def _finance_source_receipt(fact, source, require):
    """Check supplemental publication metadata against its dated content-read receipt."""
    try:
        published = datetime.fromisoformat(fact.get('captured_source_published_at', ''))
        checked = datetime.fromisoformat(fact.get('receipt_checked_at', ''))
    except (TypeError, ValueError):
        require(False, 'publication override requires a dated source receipt')
    require(published.tzinfo and checked.tzinfo and published <= checked
            and checked.date() == _finance_day(fact.get('source_checked_on'))
            and published.date() == _finance_day(fact.get('source_published_on'))
            and not source.get('published_on')
            and isinstance(fact.get('receipt_sha256'), str) and SHA256.fullmatch(fact['receipt_sha256'])
            and fact.get('receipt_locator') and fact.get('receipt_excerpt'),
            'publication override requires a dated source receipt')


def _mercor_current_finance(fact, profile_content, require):
    """Bind the displayed valuation and tender context to the approved current facts."""
    entry = next((entry for entry in profile_content['entries'] if entry['company_id'] == 'mercor'), {})
    current = entry.get('current_facts', {})
    sources = current.get('sources', [])
    require(sources, 'Series D requires the approved current profile source')
    source = sources[0]
    rows = {row['label']: row for row in current.get('rows', []) if 0 in row['source_indexes']}
    valuation = re.fullmatch(r'\$(\d+) billion · company-reported', rows.get('Announced valuation', {}).get('value', ''))
    round_amount = re.fullmatch(r'\$(\d+) million · includes an employee tender', rows.get('Announced round', {}).get('value', ''))
    day = _finance_day(source.get('published_on'))
    require(day and valuation and round_amount
            and rows.get('Funding announced', {}).get('value') == f'{day.day} {day:%b %Y} · Series D',
            'Series D valuation and announced tender must use the same dated company source')
    note = fact.get('note') or ''
    require(fact['record_id'] == 'mercor-series-d'
            and fact.get('source_id') == 'profile-content.json/mercor/current_facts/sources/0'
            and fact.get('source_url') == source['url']
            and fact.get('source_published_on') == fact.get('raw_date') == source['published_on']
            and fact.get('source_accessed_on') == source['observed_on']
            and fact.get('receipt_sha256') == source['response_sha256']
            and (fact.get('amount'), fact.get('currency'), fact.get('qualifier')) == (int(valuation[1]) * 10**9, 'USD', 'exact')
            and isinstance(note, str) and f'${round_amount[1]}M' in note and 'employee tender' in note
            and fact.get('date_role') == 'announcement',
            'Series D display differs from approved profile evidence')


def _validate_profile_finance(finances, data, claims, metrics, sources, observations, profile_content):
    if not isinstance(finances, dict):
        raise ValueError('business-health: profile finance must be keyed by company')
    companies = {company['id']: company for company in data['companies']}
    records = {**metrics, **{row['id']: row for row in data.get('funding_rounds', [])}}
    for company, profile in finances.items():
        prefix = 'business-health: profile finance ' + company + ': '

        def require(condition, message):
            if not condition:
                raise ValueError(prefix + message)

        require(company in companies and isinstance(profile, dict), 'known company required')
        headline = profile.get('headline')
        purposes = {'native_evidence_link_only', 'parent_scope'}
        projection = profile.get('compare_projection')
        require(projection in purposes, 'Compare display purpose required')
        archived = profile.get('archived_record')
        kept = profile.get('preserved_metric_rows', [])
        require(isinstance(kept, list) and kept and len(kept) == len(set(kept))
                and all(metrics.get(mid, {}).get('company_id') == company for mid in kept),
                'unique same-company metric history required')
        require(archived is None or archived in kept and profile.get('archived_record_context'),
                'archive must use a preserved metric with source context')
        details = profile.get('native_detail_records')
        require(isinstance(details, list), 'detail records required')
        facts = [fact for fact in (headline, *details) if fact is not None]
        require(facts and all(isinstance(fact, dict) and isinstance(fact.get('record_id'), str) and fact['record_id']
                              for fact in facts)
                and len({fact['record_id'] for fact in facts}) == len(facts), 'unique finance records required')
        for fact in facts:
            record_id = fact['record_id']
            prefix = 'business-health: profile finance ' + record_id + ': '
            require(all(isinstance(fact.get(key), str) and fact[key].strip() for key in
                        ('label', 'claimant', 'display_date', 'date_label', 'scope', 'source_title')),
                    'display label, date role, scope and attribution required')
            amount = fact.get('amount')
            require(type(amount) in (int, float) and math.isfinite(amount) and amount > 0, 'positive finite amount required')
            role = fact.get('date_role')
            require(role in FINANCE_DATE_ROLES, 'invalid evidence date role')
            if company == 'mercor' and record_id == 'mercor-series-d':
                _mercor_current_finance(fact, profile_content, require)
            else:
                record = records.get(record_id, {})
                claim = claims.get(record.get('claim_id'), {})
                sid = fact.get('source_id')
                source = sources.get(sid, {})
                require(record.get('company_id') == company and source.get('company_id') == company
                        and claim.get('status') == 'supported' and claim.get('company_id') == company
                        and fact.get('claim_ids') == [claim.get('id')] and sid in claim.get('source_ids', []),
                        'a cited same-company record, supported claim and source are required')
                require((amount, fact.get('currency'), fact.get('qualifier'), fact.get('raw_date')) ==
                        (record.get('amount', record.get('value')), record.get('currency'), record.get('qualifier'),
                         record.get('announced_on', record.get('as_of'))),
                        'quantity, basis or original date differs from the cited record')
                require(fact.get('source_url') == source['url'] and fact['source_title'] == source['title']
                        and fact.get('source_status') == source['retrieval_status']
                        and fact.get('source_accessed_on') == source.get('accessed_on'),
                        'source link, original review date or original source status differs from the cited source')
                if fact.get('source_published_on') != source.get('published_on') or fact.get('source_checked_on'):
                    _finance_source_receipt(fact, source, require)
            expected_date = fact['raw_date']
            if role == 'source_publication':
                expected_date = fact.get('source_published_on')
            elif role == 'period_end':
                observation = observations.get(record_id, {})
                require(observation.get('measure') == 'period_revenue' and fact['source_id'] in observation.get('source_ids', [])
                        and [observation.get(field) for field in ('value', 'currency', 'qualifier')] ==
                        [amount, fact['currency'], fact['qualifier']],
                        'reporting period must be bound to the selected period revenue observation')
                expected_date = observation['period'].get('end')
            elif role == 'source_check':
                require(not fact.get('source_published_on') and fact['raw_date'] == fact.get('source_accessed_on'),
                        'source-check date must belong to an undated source')
                expected_date = None
            elif role == 'undated':
                require(fact['raw_date'] == 'undated' and not fact.get('source_published_on'), 'undated fact requires an undated record and source')
                expected_date = None
            display_day = _finance_day(expected_date if role != 'source_check' else fact['source_accessed_on'])
            require('evidence_date' in fact and fact['evidence_date'] == expected_date
                    and (display_day and f'{display_day.day} {display_day:%b %Y}' in fact['display_date'] or role == 'undated'),
                    'displayed date must match the date role')
        if projection == 'parent_scope':
            prefix = 'business-health: profile finance ' + company + ': '
            group = (companies[company].get('aliases') or [companies[company]['name']])[0] + ' group'
            require(headline and headline['date_role'] == 'period_end' and headline['scope'] == group
                    and observations[headline['record_id']]['scope'] == 'company'
                    and all(row.get('scope_label') == group and group in row.get('cohort', '')
                            for row in observations.values() if row['company_id'] == company and row['scope'] == 'company'),
                    'parent scope must identify the group in the headline and reported observations')


def _validate_reviewed_revenue(observations, metrics, claims, sources, checks):
    for identifier, sid, evidence_type, bounds in (
            (MERCOR_H1_ESTIMATE, 'mercor.source.audit-m6', 'estimate', ('2026-01-01', '2026-06-30')),
            (RWS_GENERATE_REVENUE, 'rws_trainai.source.d_rws4', 'reported', ('2025-10-01', '2026-03-31'))):
        row = observations.get(identifier, {})
        metric = metrics.get(identifier, {})
        claim = claims.get(metric.get('claim_id'), {})
        check = checks.get(sid, {})
        period = row.get('period', {})
        if (row.get('metric_ids') != [identifier] or row.get('claim_ids') != [claim.get('id')]
                or row.get('source_ids') != [sid] or row.get('measure') != 'period_revenue'
                or (row.get('as_of'), row.get('value'), row.get('unit'), row.get('currency'),
                    row.get('qualifier'), row.get('scope'), row.get('accounting_basis')) !=
                   (metric['as_of'], metric['value'], metric['unit'], metric['currency'],
                    metric['qualifier'], metric['segment_scope'], metric['gross_vs_net'])
                or period.get('type') != 'half_year' or (period.get('start'), period.get('end')) != bounds
                or row.get('evidence_type') != evidence_type or check.get('status') != 'content_checked'
                or check.get('http_status') != 200 or check.get('url') != sources[sid]['url']
                or check.get('checked_on') != row.get('evidence_checked_on')
                or not SHA256.fullmatch(check.get('content_sha256', ''))):
            raise ValueError(f'business-health: {identifier}: reviewed revenue requires its exact metric and checked source')
        if identifier == MERCOR_H1_ESTIMATE and (
                row['period'].get('label') != 'H1 2026' or 'estimate' not in row['label'].lower()
                or 'Sacra estimate' not in row.get('evidence_assurance', '')):
            raise ValueError(f'business-health: {identifier}: the estimate must identify its period and attribution')
        if identifier == RWS_GENERATE_REVENUE and (
                row.get('scope_label') != 'Generate segment'
                or any('Generate segment' not in row.get(field, '') for field in ('cohort', 'cohort_label'))
                or 'TrainAI and Content Technology' not in row.get('scope_detail', '')):
            raise ValueError(f'business-health: {identifier}: the observation must name Generate and its businesses')


def load_business_health(path, data, profile_content=None):
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
    if 'profile_finance' in health:
        if profile_content is None:
            profile_path = path.with_name('profile-content.json')
            if not profile_path.exists():
                profile_path = Path(__file__).resolve().parents[1] / 'data/profile-content.json'
            profile_content = json.loads(profile_path.read_text())
        _validate_profile_finance(health['profile_finance'], data, claims, metrics, sources, observations, profile_content)
        _validate_reviewed_revenue(observations, metrics, claims, sources, checked)
    return health
