/* Loaded only when homepage Search is invoked; no application or archive download. */
(() => {
  'use strict';
  if (typeof window.openHomeSearch === 'function') return;
  const $ = id => document.getElementById(id), dialog = $('home-search'), input = $('home-search-input'), results = $('home-search-results'), message = $('home-search-message');
  const config = JSON.parse($('home-config').textContent), search = globalThis.S2SSearch;
  const pageSize = 7, historyField = 's2sHomeSearchReturn';
  let entries = null, pending = null, active = -1, shown = pageSize, generation = 0;
  let exactIdentifiers = false, workTitles = new Set(), returnState = null;
  const fallback = dialog.querySelector('.site-search-fallback');
  const workRecovery = $('home-search-work-recovery') || fallback?.querySelector('a[href^="/work/"]');
  let more = $('home-search-more');
  if (!more) {
    more = document.createElement('button'); more.id = 'home-search-more'; more.className = 'site-search-more'; more.type = 'button'; more.hidden = true;
    results.after(more);
  }
  const escape = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  function say(value) {
    message.textContent = value;
    const status = $('home-search-status');
    if (status) status.textContent = value;
  }
  const options = () => [...results.querySelectorAll('[role=option]')];
  function updateFallback() {
    if (workRecovery) {
      workRecovery.href = search.workUrl(input.value);
      workRecovery.textContent = input.value.trim() ? 'Search paid work for this query' : 'Browse paid work';
    }
  }
  function clearResults() {
    results.replaceChildren(); results.hidden = true; more.hidden = true; active = -1;
    input.removeAttribute('aria-activedescendant'); input.setAttribute('aria-expanded', 'false');
  }
  async function load() {
    if (entries) return entries;
    if (pending) return pending;
    say('Loading the search index…'); clearResults();
    const controller = new AbortController(), deadline = setTimeout(() => controller.abort(), 15000);
    pending = fetch(config.search.href, { signal: controller.signal, cache: 'no-cache' }).then(async response => {
      if (!response.ok) throw new Error('Search unavailable');
      const bytes = await response.arrayBuffer();
      if (globalThis.crypto?.subtle) {
        const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(byte => byte.toString(16).padStart(2, '0')).join('');
        if (digest !== config.search.sha256) throw new Error('Search integrity mismatch');
      }
      const data = JSON.parse(new TextDecoder().decode(bytes));
      for (const key of ['schemaVersion', 'buildId', 'editorialReleaseId', 'datasetVersion']) if (data[key] !== config[key]) throw new Error('Search release mismatch');
      const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string');
      const optionalStrings = value => value === undefined || strings(value);
      const validRow = row => row && typeof row.name === 'string' && typeof row.summary === 'string'
        && typeof row.group === 'string' && strings(row.products) && typeof row.href === 'string'
        && /^\/(?!\/)[^\s\\]*$/u.test(row.href) && optionalStrings(row.aliases) && optionalStrings(row.identifiers);
      if (!Array.isArray(data.entries) || !data.entries.every(validRow) || !optionalStrings(data.workTitles)) throw new Error('Invalid search index');
      entries = data.entries.map(search.compile);
      exactIdentifiers = entries.some(entry => entry.identifiers.length);
      workTitles = new Set((data.workTitles || []).map(search.normalize));
      return entries;
    }).finally(() => { clearTimeout(deadline); pending = null; });
    return pending;
  }
  function setActive(index) {
    const rows = options();
    active = index;
    rows.forEach((node, position) => node.setAttribute('aria-selected', String(position === active)));
    if (active >= 0 && rows[active]) {
      input.setAttribute('aria-activedescendant', rows[active].id); rows[active].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }
  function resultType(row) {
    if (row.href.startsWith('/company/')) return 'Company';
    if (row.group === 'paper') return row.recordKind === 'paper_version' ? 'Paper source version' : 'Paper';
    return { dataset: 'Dataset', benchmark: 'Benchmark', report: 'Research report', workflow: 'Workflow', daily: 'Daily scan', data: 'Research data', review: 'Review log', market: 'Market' }[row.group] || 'Research';
  }
  function option({ name, summary, href, type }, index) {
    return `<a id="home-result-${index}" class="site-search-option" role="option" aria-selected="false" tabindex="-1" data-result-type="${escape(type)}" href="${escape(href)}"><strong>${escape(name)}</strong><span>${escape(type + ' · ' + summary)}</span></a>`;
  }
  function render(paging = false) {
    const raw = input.value, key = search.normalize(raw);
    const exact = exactIdentifiers ? search.identifier(raw) : '';
    const selected = paging ? results.querySelector('[aria-selected=true]')?.getAttribute('href') : null;
    const matches = exact ? entries.filter(entry => entry.identifiers.includes(exact))
      : key ? entries.map(entry => ({ ...entry, rank: search.rank(entry, raw) })).filter(entry => entry.rank >= 0).sort((a, b) => a.rank - b.rank || search.compare(a.row, b.row)) : entries.slice(0, pageSize);
    if (fallback) fallback.hidden = Boolean(exact || matches.length);
    if (workRecovery) workRecovery.hidden = true;
    if (exact && !matches.length) {
      clearResults(); say('No matching research record for this identifier.'); return;
    }
    const visible = matches.slice(0, shown);
    const rendered = visible.map(entry => {
      const { row } = entry, alias = row.href.startsWith('/company/') ? search.matchedAlias(entry, raw) : '';
      return { ...row, type: resultType(row), summary: alias ? 'Recorded alias: ' + alias + '. ' + row.summary : row.summary };
    });
    if (!exact) {
      const work = { name: key ? 'Find paid work matching “' + raw.trim() + '”' : 'Browse paid work', summary: 'Public listings, expert networks and requirements', type: 'Work search', href: search.workUrl(raw) };
      if (search.isWorkQuery(raw, workTitles)) rendered.unshift(work);
      else rendered.push(work);
    }
    results.innerHTML = rendered.map(option).join('');
    results.hidden = false; input.setAttribute('aria-expanded', 'true');
    const index = selected ? options().findIndex(node => node.getAttribute('href') === selected) : -1;
    setActive(index);
    more.hidden = !key || visible.length >= matches.length;
    more.textContent = `Show ${Math.min(pageSize, matches.length - visible.length)} more`;
    if (exact) say(`Showing ${visible.length} of ${matches.length} matching research ${matches.length === 1 ? 'record' : 'records'}.`);
    else if (!key) say('Search research, companies and their offerings, or continue to paid work.');
    else if (matches.length) say(`Showing ${visible.length} of ${matches.length} matching guide records. Paid work uses its own listing filters.`);
    else say('No recorded guide matches. You can search paid work or browse all companies.');
    if (paging && more.hidden) input.focus();
  }
  function restore(snapshot) {
    const rows = options();
    const index = rows.findIndex(node => node.getAttribute('href') === snapshot.resultHref);
    if (index >= 0) setActive(index);
    if (index >= 0 && snapshot.focus === 'result') rows[index].focus({ preventScroll: true });
    else input.focus({ preventScroll: true });
    results.scrollTop = snapshot.resultsScroll;
  }
  window.openHomeSearch = async snapshot => {
    const request = ++generation;
    if (!dialog.open) dialog.showModal();
    $('home-search-open').setAttribute('aria-expanded', 'true'); input.focus();
    if (snapshot && typeof snapshot.query === 'string') {
      returnState = snapshot;
      input.value = snapshot.query;
      if (Number.isInteger(snapshot.shown)) shown = Math.max(pageSize, snapshot.shown);
    }
    updateFallback();
    try {
      await load();
      if (request !== generation || !dialog.open) return;
      render();
      if (returnState) { restore(returnState); returnState = null; }
    } catch {
      if (request !== generation || !dialog.open) return;
      clearResults();
      say('Search could not load. Retry or browse the native pages.');
      message.innerHTML = 'Search could not load. <button type="button" data-home-search-retry>Try again</button>';
      if (fallback) fallback.hidden = false;
      if (workRecovery) workRecovery.hidden = false;
    }
  };
  dialog.addEventListener('click', event => {
    const link = event.target.closest('#home-search-results a[role=option]');
    if (!link || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey || link.origin !== location.origin) return;
    try {
      history.replaceState({ ...history.state, [historyField]: {
        query: input.value, resultHref: link.getAttribute('href'), shown,
        resultsScroll: results.scrollTop,
        focus: document.activeElement === link || event.pointerType === 'touch' ? 'result' : 'input'
      } }, '');
    } catch {}
  });
  message.addEventListener('click', event => { if (event.target.closest('[data-home-search-retry]')) window.openHomeSearch(); });
  dialog.addEventListener('close', () => {
    generation++; returnState = null;
    if (history.state?.[historyField]) {
      const remaining = { ...history.state }; delete remaining[historyField];
      try { history.replaceState(remaining, ''); } catch {}
    }
  });
  function edited(event) {
    if (event.isComposing) return;
    shown = pageSize; returnState = null; updateFallback();
    if (entries) render();
  }
  input.addEventListener('input', edited);
  input.addEventListener('compositionend', edited);
  const revealMore = () => more.scrollIntoView({ block: 'nearest' });
  more.addEventListener('focus', revealMore);
  more.addEventListener('click', () => {
    shown += pageSize;
    render(true);
    if (document.activeElement === more) revealMore();
  });
  input.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === 'Escape') { event.preventDefault(); dialog.close(); return; }
    if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    const rows = options(); if (!rows.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const forward = event.key === 'ArrowDown';
      const next = active < 0 ? (forward ? 0 : rows.length - 1) : (active + (forward ? 1 : rows.length - 1)) % rows.length;
      setActive(next);
    }
    if (event.key === 'Enter') { event.preventDefault(); rows[Math.max(active, 0)].click(); }
  });
})();
