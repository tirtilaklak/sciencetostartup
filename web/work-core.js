/* Selection, order and data export shared by native Work and Explore. */
const S2SWork = (() => {
  const WORK_ROUTE_ARCHIVE=new Set(['historical','closed','contributions','paused','no_route','inquiry','information']);

  const WORK_TYPE_GROUPS={contract:'Expert & contractor projects',employment:'Employment',fellowship:'Research fellowship',bounty:'Contributor bounties',study:'study',varies:'varies',unknown:'Unverified route'};
  const WORK_FILTER_VALUES={kind:['','named','programs','boards','outside','closed'],type:['',...Object.keys(WORK_TYPE_GROUPS)],pay:['','hourly','task','yearly','monthly','numeric','undisclosed'],arrangement:['','remote','onsite','varies'],sort:['','hourly','checked']};
  function normalizeWorkCriteria(value={}){
    const result={q:String(value.q??'').slice(0,256)};
    for(const key of Object.keys(WORK_FILTER_VALUES)){const raw=String(value[key]??'');result[key]=WORK_FILTER_VALUES[key].includes(raw)?raw:'';}
    return result;
  }

  function w4Text(value){return String(value??'').replace(/\s+/g,' ').trim();}

  function w4Checked(route){return [route.availability_checked_on,route.last_route_check?.date].filter(Boolean).sort().at(-1)||null;}

  function w4ApprovedTermsReceipt(route){
    const review=route.editorial_review,receipt=(review?.receipts||[]).find(item=>item.id===review.approved_terms_receipt_id);
    return receipt?.approved===true&&receipt.scope==='key_terms'&&receipt.result==='readable'&&receipt.approval_basis==='source_content_review'&&/^\d{4}-\d{2}-\d{2}$/.test(receipt.checked_on||'')?receipt:null;
  }
  function w4TermsReviewDate(route){return w4ApprovedTermsReceipt(route)?.checked_on||route.terms_checked_on||null;}

  function w4Uncertain(route){
    if(typeof route.uncertain==='boolean')return route.uncertain;
    if(['unverified','intake_unverified','pay_conflict'].includes(route.status))return true;
    if(['blocked','not_found','unavailable'].includes(route.last_link_check?.result))return true;
    const check=[route.last_route_check?.result,route.last_route_check?.note].filter(Boolean).join(' ');
    return route.research_record?.route?.live_application_verified===false||/HTTP 403|blocked.fetch|JavaScript.only|requires JavaScript|JavaScript shell|not verified open|could not be loaded/i.test(check);
  }
  function w4Status(route){
    if(route.availability_label)return route.availability_label;
    if(route.editorial_review?.disposition?.state==='historical_page_unavailable')return 'Past listing · page unavailable';
    if(route.status==='program'&&/waitlist/i.test(route.availability_note||''))return 'Waitlist may apply';
    const labels={intake_unverified:'Availability unconfirmed',unverified:'Availability unconfirmed',pay_conflict:'Pay conflict',historical:'Historical',closed:'Closed',paused:'Training paused',contributions:'Research contribution',no_route:'No confirmed paid listing',inquiry:'Inquiry only',information:'Information only'};
    if(route.status==='historical'&&['official_role_not_found_redirect','official_role_not_found'].includes(route.last_route_check?.result))return 'Historical · listing unavailable';
    return labels[route.status]||(w4Uncertain(route)?'Availability unconfirmed':'');
  }

  function w4PayQualification(route){
    if(route.pay_terms?.note)return route.pay_terms.note;
    if(route.pay_basis==='advertised_maximum_hourly')return 'Rates vary by expertise, assessment, location and project. Non-core work can pay less.';
    if(!route.pay_basis?.endsWith('salary_period_unspecified'))return '';
    return 'Pay period not stated.'+(/Bonus eligibility and payout terms are undisclosed/i.test(route.availability_note||'')?' Bonus eligibility and payout terms are undisclosed.':'');
  }

  const W4_TASK_PAY=new Set(['per_completed_task','task','accepted_task','approved_recording','approved_submission']);
  const W4_REMOTE=/remote|at home|worldwide|global/i,W4_ONSITE=/San Francisco|Palo Alto|Berkeley|London|Paris|Tokyo|Bangalore|on-?site|hybrid|in.person|office/i;
  function w4OpportunityKind(route){
    if(['named_listing','network_program','career_page','other_record'].includes(route.route_kind))return route.route_kind;
    if(route.status==='careers')return 'career_page';
    if(route.status==='program')return 'network_program';
    return ['information','inquiry','contributions','no_route'].includes(route.status)?'other_record':'named_listing';
  }
  function w4Engagement(route){
    if(['contract','employment','fellowship','bounty','study','varies','unknown'].includes(route.engagement_type))return route.engagement_type;
    return {'Expert & contractor projects':'contract',Employment:'employment','Research fellowship':'fellowship','Contributor bounties':'bounty'}[route.group]||'unknown';
  }

  function w4HourlyRange(route){
    if(!route?.numeric_pay||route.status==='pay_conflict'||route.pay_basis==='conflicting_hourly')return null;
    if(route.pay_terms?route.pay_terms.hourly_comparable!==true:['hour_equivalent','per_completed_task','task','accepted_task','approved_recording','approved_submission'].includes(route.pay_basis))return null;
    const label=w4Text(route.pay_label);
    if(!/\/\s*(?:approved\s+)?hour/i.test(label))return null;
    const match=label.match(/([$€£¥])\s*([\d,]+(?:\.\d+)?)(?:\s*[–-]\s*[$€£¥]?\s*([\d,]+(?:\.\d+)?))?(\+)?/);
    if(!match)return null;
    const number=value=>Number(value.replace(/,/g,''));
    return {currency:match[1],low:/^up to\b/i.test(label)?null:number(match[2]),high:number(match[3]||match[2]),open:Boolean(match[4])};
  }

  function w4PayMatches(route,value){
    if(!value)return true;
    if(value==='numeric'||value==='undisclosed')return (value==='numeric')===Boolean(route.numeric_pay);
    if(value==='hourly')return Boolean(w4HourlyRange(route));
    if(value==='task')return route.pay_terms?['task','hour_equivalent'].includes(route.pay_terms.unit):W4_TASK_PAY.has(route.pay_basis)||route.pay_basis==='hour_equivalent';
    if(value==='monthly')return route.pay_terms?route.pay_terms.unit==='month':['month_stipend','undisclosed_stipend'].includes(route.pay_basis);
    if(value==='yearly')return route.pay_terms?route.pay_terms.unit==='year':/^(?:annual_salary|annual_target_cash)$/.test(route.pay_basis||'');
    return false;
  }
  function w4Arrangements(route){
    if(Array.isArray(route.arrangements))return route.arrangements.filter(value=>['remote','onsite','hybrid'].includes(value));
    const place=route.geography||'';return [...(W4_REMOTE.test(place)?['remote']:[]),...(W4_ONSITE.test(place)?['onsite']:[])];
  }

  function w4WhereMatches(route,value){const values=w4Arrangements(route);return !value||(value==='remote'?values.includes('remote'):value==='onsite'?values.some(item=>['onsite','hybrid'].includes(item)):value==='varies'?!values.length:route.eligibility===value);}

  // Worker words map to the words listings use. Each term must start a word, so "doctor" skips "doctorate".
  const W4_WORD_START='(?:^|[^\\p{L}\\p{N}])',W4_WORD_END='(?![\\p{L}\\p{N}])';
  const W4_SEARCH_GROUPS=[
    {words:['medical','medicine','doctor','doctors','physician','physicians','clinical','clinician','clinicians','health','healthcare','nurse','nurses','nursing'],terms:['medic','clinic','physician','doctors?'+W4_WORD_END,'health','nurs(?:e|es|ing)'+W4_WORD_END]},
    {words:['code','coding','coder','coders','developer','developers','programmer','programmers','programming','swe','software'],terms:['cod(?:e|es|ing|er|ers)'+W4_WORD_END,'software','swe'+W4_WORD_END,'developers?'+W4_WORD_END,'programm']},
    {words:['label','labels','labeling','labelling','labeler','labelers','annotation','annotations','annotate','annotator','annotators'],terms:['label(?:s|ed|er|ers|ing|ling)?'+W4_WORD_END,'annotat']},
    {words:['beginner','beginners','entry','entry-level','novice','junior'],phrases:['no experience','entry level'],terms:['no experience','generalists','general tasks?','general ai','entry[- ]level','beginner']},
    {words:['student','students','college','intern','interns','internship','internships','graduate','graduates','university'],terms:['student','college','intern(?:s|ship|ships)?'+W4_WORD_END,'graduate','universit','no experience','generalists','general tasks?','entry[- ]level']},
    {words:['part-time','parttime','flexible'],phrases:['part time'],terms:['part[- ]?time','flexible','opt-in']},
    {words:['worldwide','global','anywhere','international'],terms:['worldwide','global','anywhere','international']}
  ];
  function w4RegExpEscape(value){return value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');}
  function w4SearchFold(value){return String(value??'').normalize('NFKD').replace(/\p{M}+/gu,'').toLowerCase();}
  function workSearchTerms(query){return globalThis.S2SSearch?.workTerms(query)||query;}
  function w4QueryMatcher(query){
    let text=w4SearchFold(w4Text(query));
    if(!text)return null;
    for(const group of W4_SEARCH_GROUPS)for(const phrase of group.phrases||[])text=text.split(phrase).join(group.words[0]);
    const tokens=text.split(' ').filter(Boolean);
    const tests=tokens.map(token=>{const group=W4_SEARCH_GROUPS.find(g=>g.words.includes(token));return new RegExp(W4_WORD_START+'(?:'+(group?group.terms.join('|'):w4RegExpEscape(token))+')','u');});
    const phrase=tokens.length>1?new RegExp(W4_WORD_START+w4RegExpEscape(tokens.join(' ')),'u'):null;
    return {all:value=>tests.every(test=>test.test(value)),phrase:value=>Boolean(phrase?.test(value))};
  }


  function w4BestRank(route){
    const uncertainty=w4Uncertain(route)?20:0,terms=w4TermsReviewDate(route)?0:route.last_route_check?.result==='listing_content_reviewed'?2:5;
    return uncertainty+terms+(w4HourlyRange(route)&&w4Arrangements(route).includes('remote')?0:10);
  }
  function w4CurrencyCode(route){const code=route.pay_terms?.currency;return /^[A-Z]{3}$/.test(code||'')?code:null;}
  function w4RateTie(a,b){const x=w4HourlyRange(a),y=w4HourlyRange(b),currency=w4CurrencyCode(a);return x&&y&&currency&&currency===w4CurrencyCode(b)?y.high-x.high:0;}
  function w4BestOrder(a,b, companyName = route => route.company_name || route.company_id){return w4BestRank(a)-w4BestRank(b)||(w4Checked(b)||'').localeCompare(w4Checked(a)||'')||w4RateTie(a,b)||companyName(a).localeCompare(companyName(b))||a.role.localeCompare(b.role)||String(a.id || '').localeCompare(String(b.id || ''));}
  // Highest hourly rate: top of the published range, then its low end ("up to" last), then open-ended
  // ranges. Listings without a rate keep best-match order after them. US dollar rates come before other
  // currencies, and unknown currencies retain best-match order without comparing amounts.
  function w4RateOrder(a,b, companyName){
    const x=w4HourlyRange(a),y=w4HourlyRange(b);
    if(!x||!y)return Number(Boolean(y))-Number(Boolean(x))||w4BestOrder(a,b,companyName);
    const currencyA=w4CurrencyCode(a),currencyB=w4CurrencyCode(b);
    if(!currencyA||!currencyB)return Number(Boolean(currencyB))-Number(Boolean(currencyA))||w4BestOrder(a,b,companyName);
    if(currencyA!==currencyB)return Number(currencyB==='USD')-Number(currencyA==='USD')||currencyA.localeCompare(currencyB);
    return y.high-x.high||(y.low??-1)-(x.low??-1)||Number(y.open)-Number(x.open)||w4BestOrder(a,b,companyName);
  }
  function w4CheckedOrder(a,b, companyName){return (w4Checked(b)||'').localeCompare(w4Checked(a)||'')||(b.reviewed_on||'').localeCompare(a.reviewed_on||'')||w4BestOrder(a,b,companyName);}

  const groups = ['named', 'programs', 'boards', 'outside', 'closed'];
  const keys = ['q', 'kind', 'type', 'pay', 'arrangement', 'sort'];

  function bucket(route) {
    if (WORK_ROUTE_ARCHIVE.has(route.status)) return 'closed';
    const kind = w4OpportunityKind(route);
    if (kind === 'career_page') return 'boards';
    if (route.ai_data_work === false) return 'outside';
    return kind === 'named_listing' ? 'named' : kind === 'network_program' ? 'programs' : 'closed';
  }

  function readCriteria(params) {
    const values = Object.fromEntries(keys.map(key => [key, params.get(key) || '']));
    if (!WORK_FILTER_VALUES.type.includes(values.type)) {
      values.type = Object.keys(WORK_TYPE_GROUPS).find(key => WORK_TYPE_GROUPS[key] === values.type) || '';
    }
    return normalizeWorkCriteria(values);
  }

  function writeCriteria(params, criteria) {
    for (const key of keys) {
      if (criteria[key]) params.set(key, criteria[key]);
      else params.delete(key);
    }
    return params;
  }

  function select(rows, criteria, searchText, companyName = route => route.company_name || route.company_id) {
    const { q, kind, type, pay, arrangement } = criteria;
    const eligible = rows.filter(route => (!kind || bucket(route) === kind)
      && (!type || w4Engagement(route) === type) && w4PayMatches(route, pay) && w4WhereMatches(route, arrangement));
    const terms = workSearchTerms(q), matcher = w4QueryMatcher(terms);
    if (!matcher) return eligible;
    if (terms !== q) {
      // Keep a literal employer or role title when a word like “jobs” belongs to its name.
      const title = w4SearchFold(w4Text(q));
      const exact = eligible.filter(route => [companyName(route), route.role].some(name => w4SearchFold(w4Text(name)) === title));
      if (exact.length) return exact;
    }
    const text = new Map(eligible.map(route => [route.id, searchText(route)]));
    const phrase = eligible.filter(route => matcher.phrase(text.get(route.id)));
    return phrase.length ? phrase : eligible.filter(route => matcher.all(text.get(route.id)));
  }

  function groupResults(rows, sort = '', query = '', companyName = route => route.company_name || route.company_id) {
    const grouped = Object.fromEntries(groups.map(key => [key, []]));
    for (const route of rows) grouped[bucket(route)].push(route);
    const order = sort === 'hourly' ? w4RateOrder : sort === 'checked' ? w4CheckedOrder : w4BestOrder;
    const matcher = !sort && w4QueryMatcher(workSearchTerms(query));
    for (const group of groups) {
      const list = grouped[group];
      list.sort((a, b) => order(a, b, companyName));
      if (matcher && (group === 'named' || group === 'programs')) {
        const titleMatch = route => matcher.all(w4SearchFold(`${companyName(route)} ${route.role}`));
        list.sort((a, b) => Number(titleMatch(b)) - Number(titleMatch(a)));
      }
    }
    return grouped;
  }

  const csvHeader = [
    'route_id', 'company', 'role', 'opportunity_kind', 'engagement_type', 'availability', 'advertised_pay',
    'pay_unit', 'hourly_comparable', 'currency', 'arrangements', 'location', 'requirements', 'assessment',
    'commitment', 'duration', 'terms_reviewed_on', 'terms_review_scope', 'original_application_url',
    'current_action_url', 'current_action_label', 'source_urls', 'field_review_metadata',
    'full_research_profile_url', 'search_query', 'opportunity_filter', 'engagement_filter', 'pay_filter',
    'arrangement_filter', 'sort', 'pay_qualification', 'review_evidence', 'original_url_details'
  ];

  function fieldReviews(route) {
    return Object.fromEntries(Object.entries(route.field_reviews || {}).sort(([a], [b]) => a.localeCompare(b)).map(([field, review]) => [
      field, {
        state: review.state, reviewed_on: review.reviewed_on ?? null, source_ids: [...(review.source_ids || [])],
        basis: review.basis, ...(field === 'location' && review.note ? { note: review.note } : {})
      }
    ]));
  }

  function reviewEvidence(route) {
    const { last_link_check: link, last_route_check: page, editorial_review: editorial } = route;
    const review = { status: route.status };
    const add = (key, value) => { if (value != null && value !== '') review[key] = value; };
    add('availability_checked_on', route.availability_checked_on);
    const checkData = ({ date, result, url, final_url, http_status }) => ({
      date, result, ...(url && { url }), ...(final_url && { final_url }), ...(http_status != null && { http_status })
    });
    if (link?.date) add('http_check', checkData(link));
    if (page?.date) add('page_check', checkData(page));
    if (page?.application_check) add('application_check', page.application_check);
    if (page?.application_checks?.length) add('application_checks', page.application_checks);
    add('key_terms_source_id', w4ApprovedTermsReceipt(route)?.source_id);
    const commitment = route.field_reviews?.commitment;
    if (commitment?.note && commitment.source_ids?.length) {
      add('commitment', { note: commitment.note, reviewed_on: commitment.reviewed_on, source_ids: commitment.source_ids });
    }
    const disposition = editorial?.disposition;
    const getSource = id => route.sources?.find(source => source.id === id);
    if (disposition?.approval_basis === 'source_content_review' && disposition.source_ids?.length
        && disposition.source_ids.every(getSource)) {
      const { state, reviewed_on, source_ids } = disposition;
      const checks = (editorial.receipts || []).filter(receipt => receipt.scope === 'retrieval' && source_ids.includes(receipt.source_id))
        .map(({ source_id, checked_on, result, http_status }) => ({
          source_id, url: getSource(source_id).url, date: checked_on, result, ...(http_status != null && { http_status })
        }));
      add('archive_disposition', { state, reviewed_on, source_ids, ...(checks.length ? { checks } : {}) });
    }
    return review;
  }

  function originalUrls(route) {
    const listed = route.research_record?.route;
    const at = url => (route.sources || []).filter(source => url && source.url === url);
    const rolePage = at(listed?.overview_url).length ? listed.overview_url : route.url;
    const form = route.form_available === true ? at(route.url).find(source =>
      source.source_type === 'company' && source.title?.endsWith(' — public application form')
    ) : null;
    const originalAction = route.editorial_review?.actions?.find(action =>
      action.url === route.url && action.purpose === 'application' && at(action.url).some(source => source.id === action.source_id)
    );
    const application = at(listed?.application_url).length ? listed.application_url : form?.url || originalAction?.url;
    const original = { source_url: at(rolePage).length ? rolePage : null, application_url: application || null };
    const purpose = route.editorial_review?.recorded_url_purpose;
    if (purpose || original.source_url === route.url) original.recorded_url_purpose = purpose || (application === route.url ? 'application' : 'source');
    if (original.source_url) original.source_ids = at(rolePage).map(source => source.id);
    if (application) {
      original.application_source_ids = at(application).map(source => source.id);
      if (typeof listed?.live_application_verified === 'boolean' && listed.checked_on) {
        original.application_check = { date: listed.checked_on, verified_in_research: listed.live_application_verified };
      } else if (form?.accessed_on) {
        original.application_check = { date: form.accessed_on, verified_in_research: true };
      }
    }
    return original;
  }

  function csvFor(routes, criteria, destination = route => route.source_actions?.[0] || {}) {
    const rows = routes.map(route => {
      const action = destination(route);
      return [
        route.id, route.company_name || route.company_id, route.role, w4OpportunityKind(route), w4Engagement(route),
        w4Status(route) || 'Recorded listing', route.pay_label, route.pay_terms?.unit,
        route.pay_terms?.hourly_comparable === true, route.pay_terms?.currency, w4Arrangements(route).join(' | '),
        route.geography, (route.requirements || []).join(' | '), route.assessment, route.hours, route.duration,
        w4TermsReviewDate(route), w4ApprovedTermsReceipt(route) ? 'key_terms' : route.terms_checked_on ? 'pay_terms' : '',
        route.url, action.url, action.label, (route.sources || []).map(source => source.url).join(' | '),
        JSON.stringify(fieldReviews(route)), 'https://sciencetostartup.com/company/' + encodeURIComponent(route.company_id) + '/',
        ...keys.map(key => criteria[key]), w4PayQualification(route), JSON.stringify(reviewEvidence(route)),
        JSON.stringify(originalUrls(route))
      ];
    });
    const cell = value => {
      let text = String(value ?? '');
      if (/^[\t\r\n]/.test(text) || /^\s*[=+@-]/.test(text)) text = "'" + text;
      return '"' + text.replaceAll('"', '""') + '"';
    };
    return '\ufeff' + [csvHeader, ...rows].map(row => row.map(cell).join(',')).join('\r\n') + '\r\n';
  }

  const requests = new Map();
  async function fetchExport({ href, sha256 }, ids, criteria) {
    if (!ids.length) return csvFor([], criteria);
    if (!href || !sha256) throw new Error('Work results are unavailable');
    if (!requests.has(href)) {
      const request = (async () => {
        const response = await fetch(href, { cache: 'no-cache', signal: AbortSignal.timeout(15000) });
        if (!response.ok) throw new Error('Work results could not load');
        const bytes = await response.arrayBuffer();
        if (globalThis.crypto?.subtle) {
          const digest = await crypto.subtle.digest('SHA-256', bytes);
          const actual = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
          if (actual !== sha256) throw new Error('Work results integrity mismatch');
        }
        const { routes } = JSON.parse(new TextDecoder().decode(bytes));
        const index = new Map(routes.map(route => [route.id, route]));
        if (index.size !== routes.length) throw new Error('Duplicate work result');
        return index;
      })().catch(error => { requests.delete(href); throw error; });
      requests.set(href, request);
    }
    const index = await requests.get(href);
    const rows = ids.map(id => index.get(id));
    if (rows.some(route => !route)) throw new Error('Missing work result');
    return csvFor(rows, criteria);
  }

  function downloadCsv(body) {
    const url = URL.createObjectURL(new Blob([body], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sciencetostartup-current-work-results.csv';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return Object.freeze({
    archive: WORK_ROUTE_ARCHIVE, types: WORK_TYPE_GROUPS, options: WORK_FILTER_VALUES, keys, groups,
    normalizeCriteria: normalizeWorkCriteria, readCriteria, writeCriteria, select, groupResults, bucket, csvFor, fetchExport, downloadCsv,
    approvedReceipt: w4ApprovedTermsReceipt, termsReviewDate: w4TermsReviewDate, checked: w4Checked, uncertain: w4Uncertain,
    status: w4Status, payQualification: w4PayQualification, opportunityKind: w4OpportunityKind, engagement: w4Engagement,
    hourlyRange: w4HourlyRange, payMatches: w4PayMatches, arrangements: w4Arrangements, whereMatches: w4WhereMatches,
    queryMatcher: query => w4QueryMatcher(workSearchTerms(query)), fold: w4SearchFold, bestOrder: w4BestOrder, rateTie: w4RateTie, rateOrder: w4RateOrder, checkedOrder: w4CheckedOrder
  });
})();
