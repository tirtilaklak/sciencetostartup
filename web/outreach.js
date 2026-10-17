/* Public professional directory. No messages, tracking or browser persistence. */
(() => {
  'use strict';
  const root = document.getElementById('outreach-view');
  if (!root) return;
  const data = JSON.parse(document.getElementById('outreach-data').textContent);
  const $ = id => document.getElementById(id);
  const text = value => String(value ?? '');
  const escape = value => text(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize = value => text(value).replace(/[ıİ]/g, 'i').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const words = value => text(value).replace(/_/g, ' ');
  const safeUrl = value => { try { const u = new URL(value); return u.protocol === 'https:' || u.protocol === 'http:' ? u.href : ''; } catch { return ''; } };
  const urlLabel = url => { try { return new URL(url).hostname.replace(/^www\./,''); } catch { return 'Source'; } };
  const link = (url, label) => {const safe = safeUrl(url);return safe ? `<a href="${escape(safe)}" target="_blank" rel="noopener noreferrer">${escape(label || urlLabel(safe))} ${iconHTML('external')}</a>${typeof window.linkAvailabilityHTML==='function'?window.linkAvailabilityHTML(safe):''}` : escape(label || 'Source unavailable');};
  const isAdult = p => p.verification?.adultEligible === true && Boolean(p.verification?.identityEvidence) && p.verification?.identitySourceUrls?.some(safeUrl) && p.verification?.adultEvidenceUrls?.some(safeUrl);
  const currentEmail = p => isAdult(p) && p.contact?.email?.status === 'current_public' && p.contact.email.href === 'mailto:' + p.contact.email.address && /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(p.contact.email.address || '') ? p.contact.email : null;
  const currentLinkedin = p => {
    const u = safeUrl(p.contact?.linkedin?.url);
    if (!isAdult(p) || p.contact?.linkedin?.status !== 'matched_public_profile' || p.contact?.linkedin?.matchConfidence !== 'high' || !u) return null;
    const parsed = new URL(u);
    return /(^|\.)linkedin\.com$/.test(parsed.hostname) && parsed.pathname.startsWith('/in/') ? p.contact.linkedin : null;
  };
  const isReady = p => Boolean(currentEmail(p) || currentLinkedin(p));
  const isTurkiye = p => p.representedTurkey === true;
  const emailHref = p => {
    const email = currentEmail(p); if (!email) return '';
    const name = p.professionalName || p.name;
    return `${email.href}?subject=${encodeURIComponent('Hello, '+name)}&body=${encodeURIComponent('Hello '+name+',\r\n\r\n')}`;
  };
  const competitions = p => (p.competitions || []).map(c => typeof c === 'string' ? c : c.name || c.competition || '').filter(Boolean);
  const competitionNames = {
    IMO:'International Mathematical Olympiad',
    EGMO:'European Girls’ Mathematical Olympiad',
    BMO:'Balkan Mathematical Olympiad',
    JBMO:'Junior Balkan Mathematical Olympiad',
    PAMO:'Pan African Mathematics Olympiad'
  };
  const competitionLabel = code => competitionNames[code] ? `${code} · ${competitionNames[code]}` : code;
  const state = {query:'',cohort:'',contact:'',competition:''};
  const records = [...data.people].sort((a,b) => a.name.localeCompare(b.name, 'tr'));
  const searchText = p => normalize([p.name,p.professionalName,p.representedCountry,p.role,p.organization,...competitions(p),...(p.otherAwards || []).map(a=>typeof a==='string'?a:JSON.stringify(a))].join(' '));
  function filtered() {
    const tokens = normalize(state.query).split(/\s+/).filter(Boolean);
    return records.filter(p => (!tokens.length || tokens.every(t => searchText(p).includes(t))) &&
      isReady(p) &&
      (!state.cohort || (state.cohort === 'turkiye' ? isTurkiye(p) : !isTurkiye(p))) &&
      (!state.contact || (state.contact === 'email' ? currentEmail(p) : state.contact === 'linkedin' ? currentLinkedin(p) : state.contact === 'missing-email' ? !currentEmail(p) : state.contact === 'missing-linkedin' ? !currentLinkedin(p) : currentEmail(p) && currentLinkedin(p))) &&
      (!state.competition || competitions(p).includes(state.competition)));
  }
  function sourceList(sources) {
    return [...new Map((sources || []).map(s=>typeof s==='string'?{url:s}:s).filter(Boolean).map(s=>[s.url || s.sourceUrl,s])).values()]
      .filter(s=>safeUrl(s.url || s.sourceUrl)).map(s=>`<li>${link(s.url || s.sourceUrl,s.title || s.label || urlLabel(s.url || s.sourceUrl))}${s.supports?.length?` <span>· ${escape(s.supports.join(', '))}</span>`:''}${s.note?` <span>${escape(s.note)}</span>`:''}</li>`).join('');
  }
  function medalChips(p) {
    const summary = p.medalCounts || {};
    return ['gold','silver','bronze'].filter(kind=>Number(summary[kind])>0).map(kind=>`<span class="medal-chip ${kind}">${Number(summary[kind])} ${kind}</span>`).join('');
  }
  function awardText(a) { return typeof a === 'string' ? a : [a.year,a.competition,a.name || a.award || a.prize || a.title].filter(Boolean).join(' · '); }
  function evidence(p) {
    const v = p.verification || {}, c = p.contact || {};
    const adultSources = sourceList(v.adultEvidenceUrls || []), identitySources = sourceList(v.identitySourceUrls || []);
    const medalHistory = (p.medals || []).map(m=>`<li>${escape([m.year,m.competition,m.medal || m.award].filter(Boolean).join(' · '))}${m.sourceUrl?' · '+link(m.sourceUrl,'Result'):''}${m.sourceCaveat?`<p class="medal-caveat">${escape(m.sourceCaveat)}</p>`:''}</li>`).join('');
    const personalEmail = currentEmail(p), linkedin = currentLinkedin(p);

    const contacts = personalEmail ? `<p>Professional email: ${escape(personalEmail.address)}. ${escape(personalEmail.detail || words(personalEmail.status))}. Email delivery has not been tested.</p>${personalEmail.sourceUrl?`<p>${link(personalEmail.sourceUrl,'Email source')}</p>`:''}` : '<p class="missing-contact">No current professional email verified.</p>';
    const linkedinEvidence = linkedin ? `<p>LinkedIn: ${escape(words(linkedin.status))}${linkedin.matchConfidence?' · '+escape(words(linkedin.matchConfidence)):''}.</p>${link(linkedin.url,'Matched professional profile')}` : '<p class="missing-contact">No matched LinkedIn profile verified.</p>';
    const historical = isAdult(p) && c.historicalEmail ? `<p class="historical-contact"><strong>Historical email (compose link disabled):</strong> ${escape(c.historicalEmail.address)}. ${escape(words(c.historicalEmail.status))}. ${c.historicalEmail.sourceUrl?link(c.historicalEmail.sourceUrl,'Historical source'):''}</p>` : '';
    const organization = isAdult(p) && c.organizationEmail ? `<p><strong>Shared organization inbox:</strong> ${escape(c.organizationEmail.address)}. ${c.organizationEmail.sourceUrl?link(c.organizationEmail.sourceUrl,'Organization source'):''}</p>` : '';
    const sources = sourceList(p.sources || []);
    return `<div class="evidence-details"><section><h4>Professional context</h4><p>${escape([p.role,p.organization].filter(Boolean).join(' · '))}</p><h4>Identity and adult status</h4><p>${isAdult(p)?'Adult status is supported by the linked sources.':'Adult status remains unverified.'}</p><p>${escape(v.identityEvidence || 'The linked sources support this identity.')} ${escape(v.adultEligibilityNote || '')}</p>${adultSources?`<ul>${adultSources}</ul>`:''}${identitySources?`<ul>${identitySources}</ul>`:''}<p>Checked ${escape(v.checkedDate || 'date unavailable')}.</p></section><section><h4>Contact evidence</h4>${contacts}${linkedinEvidence}${historical}${organization}<p>These contact details were public when checked. They may change.</p></section><section class="evidence-wide"><h4>Competition history</h4>${medalHistory?`<ul class="medal-history">${medalHistory}</ul>`:'<p>Detailed medal history unavailable.</p>'}${(p.otherAwards||[]).length?`<h4>Other awards · separate from medal totals</h4><ul>${p.otherAwards.map(a=>`<li>${escape(awardText(a))}${a.sourceUrl?' · '+link(a.sourceUrl,'Award source'):''}</li>`).join('')}</ul>`:''}</section>${sources?`<section class="evidence-wide"><h4>Sources</h4><ul>${sources}</ul></section>`:''}${p.notes?.length?`<section class="evidence-wide"><h4>Research notes</h4><p>${escape(Array.isArray(p.notes)?p.notes.join(' '):p.notes)}</p></section>`:''}</div>`;
  }
  function shortOrganization(value) {
    const organization = String(value || '');
    let parentheses = 0;
    for (let i = 0; i < organization.length; i++) {
      if (organization[i] === '(') parentheses++;
      else if (organization[i] === ')') parentheses = Math.max(0, parentheses - 1);
      else if (organization[i] === ',' && parentheses === 0) return organization.slice(0, i);
    }
    return organization;
  }
  function personCard(p) {
    const email = currentEmail(p), linkedin = currentLinkedin(p), ready = isReady(p);
    const namesDiffer = p.professionalName && normalize(p.professionalName) !== normalize(p.name);
    const organization=shortOrganization(p.organization);const role = [p.role,organization&&!normalize(p.role).includes(normalize(organization))?organization:''].filter(Boolean).join(' · ');
    const roleQualifier = p.roleStatus && /historical|unverified|unknown|self_reported/i.test(p.roleStatus)
      ? (p.roleStatus==='current_self_reported'?'self-reported role':p.roleStatus==='current_affiliation_self_reported'?'self-reported affiliation':words(p.roleStatus)) : '';
    return `<article class="medalist" data-medalist-id="${escape(p.id)}" data-outreach-ready="${ready}" aria-labelledby="medalist-${escape(p.id)}">
      <div class="medalist-main">
        <div class="medalist-identity">
          <h2 class="medalist-name" id="medalist-${escape(p.id)}">${escape(p.name)}</h2>
          ${namesDiffer?`<p class="medalist-alias">Professional profile: ${escape(p.professionalName)}</p>`:''}
          <p class="medalist-role">${escape(role || 'Current professional role not verified')}${roleQualifier?` <span>(${escape(roleQualifier)})</span>`:''}</p>
          <p class="medalist-representation">Represented ${escape(p.representedCountry || 'country not established')}</p>
        </div>
        <div class="medalist-record">
          <strong>${Number(p.medalCount)||0} ${(Number(p.medalCount)||0)===1?'medal':'medals'} · ${escape(competitions(p).join(' / ') || 'Competition unrecorded')}</strong>
          <div class="medal-line">${medalChips(p)}</div>
          ${(p.otherAwards||[]).length?`<p class="medalist-awards">+ ${p.otherAwards.length} separate ${p.otherAwards.length===1?'prize':'prizes'}</p>`:''}
        </div>
        <div class="medalist-contact"><div class="medalist-actions">
          ${email?`<a class="email-action" href="${escape(emailHref(p))}" aria-label="Compose email to ${escape(p.professionalName || p.name)}">Email <span aria-hidden="true">${iconHTML('external')}</span></a>`:''}
          ${linkedin?`<a class="linkedin-action" href="${escape(safeUrl(linkedin.url))}" target="_blank" rel="noopener noreferrer" aria-label="Open LinkedIn profile for ${escape(p.professionalName || p.name)}">LinkedIn <span aria-hidden="true">${iconHTML('external')}</span></a>`:''}
        </div></div>
      </div>
      <details class="medalist-evidence"><summary>Sources &amp; verification<span class="sr-only"> for ${escape(p.name)}</span></summary>${evidence(p)}</details>
    </article>`;
  }
  let rendered = false;
  function render() {
    rendered = true;
    const rows = filtered();
    const filterCount = [state.cohort,state.contact,state.competition].filter(Boolean).length;
    const summary = root.querySelector('.responsive-filter-panel>summary');
    if (summary) summary.textContent = filterCount ? `Filter people (${filterCount})` : 'Filter people';
    $('outreach-list').innerHTML = rows.map(personCard).join('');
    $('outreach-empty').hidden = rows.length > 0;
    $('outreach-count').textContent = `${rows.length} of ${records.filter(isReady).length} verified adults${rows.length===0?' match these filters':''}`;
  }
  function reset() {
    Object.assign(state,{query:'',cohort:'',contact:'',competition:''});
    for (const key of ['search','cohort','contact','competition']) $('outreach-'+key).value = '';
    render();
  }
  const ready = records.filter(isReady), emails = ready.filter(currentEmail), linkedin = ready.filter(currentLinkedin);
  const totalMedals = records.reduce((n,p)=>n+(Number(p.medalCount)||0),0), totalAwards = records.reduce((n,p)=>n+(p.otherAwards?.length||0),0);
  $('outreach-stats').innerHTML = [[ready.length,'Verified adults'],[emails.length,'Professional emails'],[linkedin.length,'LinkedIn profiles']].map(([n,label])=>`<div class="outreach-stat"><strong>${n}</strong><span>${escape(label)}</span></div>`).join('');
  const dates = [...new Set(records.map(p=>p.verification?.checkedDate).filter(Boolean))].sort();
  const checkedDate = data.metadata?.sourceCheckedDate || dates.at(-1);
  const checkedLabel = /^\d{4}-\d{2}-\d{2}$/.test(checkedDate || '')
    ? new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(checkedDate+'T00:00:00Z'))
    : 'date unavailable';
  $('outreach-checked').textContent = `Contacts checked ${checkedLabel} · Directory v${data.metadata?.sourceVersion || 2}`;
  $('outreach-competition').innerHTML += [...new Set(records.flatMap(competitions))].sort().map(c=>`<option value="${escape(c)}">${escape(competitionLabel(c))}</option>`).join('');
  $('outreach-method-content').innerHTML = `<p><strong>${records.length} verified adults are included here.</strong> Their records include ${totalMedals} competition medals and ${totalAwards} separate ${totalAwards===1?'prize':'prizes'}. The full source directory contains ${data.metadata.sourceDirectoryCounts.people} people. It records ${data.metadata.sourceDirectoryCounts.medalRecords} medals and ${data.metadata.sourceDirectoryCounts.otherAwardRecords} separate prizes.</p><p>Each listed person has evidence supporting their identity and adult status. At least one public professional contact is verified. ${ready.filter(p=>currentEmail(p)&&currentLinkedin(p)).length} people have both email and LinkedIn. ${ready.filter(isTurkiye).length} represented Türkiye; ${ready.filter(p=>!isTurkiye(p)).length} represented other countries.</p><p>${escape(data.metadata.coverageNote)}</p><p>${escape(data.metadata.contactMeaning)} ${escape(data.metadata.freshnessNote)}</p><p>Unverified fields are labeled. Historical records keep their dates. Only current email addresses have compose links. Shared organization inboxes are identified. A missing link means no contact was verified in this research.</p><p>Competition representation does not establish citizenship. Each profile includes the sources used to check identity and adult status.</p><p>This directory sends no messages and saves no outreach activity. Links open your email app or LinkedIn.</p>`;
  const principles = root.querySelector('.outreach-principles');
  if (principles) $('outreach-method-content').append(principles);
  $('outreach-search').addEventListener('input',e=>{state.query=e.target.value;render();});
  for(const key of ['cohort','contact','competition']) $('outreach-'+key).addEventListener('change',e=>{state[key]=e.target.value;render();});
  $('outreach-reset').addEventListener('click',reset);
  $('outreach-empty-reset').addEventListener('click',()=>{reset();$('outreach-search').focus();});
  document.querySelector('.skip')?.addEventListener('click',e=>{e.preventDefault();$('main').focus();$('main').scrollIntoView({block:'start'});});
  const ensureRendered = () => { if (!rendered) render(); };
  window.MedalistOutreach = {data,state,filtered,isReady,isAdult,isTurkiye,currentEmail,currentLinkedin,emailHref,normalize,safeUrl,render,reset,ensureRendered,isRendered:()=>rendered};
  if (!root.hidden) ensureRendered();
})();
