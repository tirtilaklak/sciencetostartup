/* Loaded only when homepage Search is invoked; no application or archive download. */
(() => {
  'use strict';
  if (typeof window.openHomeSearch === 'function') return;
  const $ = id => document.getElementById(id), dialog = $('home-search'), input = $('home-search-input'), results = $('home-search-results'), message = $('home-search-message');
  const config = JSON.parse($('home-config').textContent), search = globalThis.S2SSearch;
  let entries = null, pending = null, active = -1, shown = 7, generation = 0;
  let more = $('home-search-more');
  if (!more) {
    more = document.createElement('button'); more.id = 'home-search-more'; more.className = 'site-search-more'; more.type = 'button'; more.hidden = true;
    results.after(more);
  }
  const escape = value => String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const announce = value => { const status = $('home-search-status'); if (status) status.textContent = value; };
  function clearResults() {
    results.replaceChildren(); results.hidden = true; more.hidden = true; active = -1;
    input.removeAttribute('aria-activedescendant'); input.setAttribute('aria-expanded', 'false');
  }
  async function load() {
    if (entries) return entries;
    if (pending) return pending;
    message.textContent = 'Loading the search index…'; clearResults();
    const controller = new AbortController(), deadline = setTimeout(() => controller.abort(), 15000);
    pending = fetch(config.search.href, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('Search unavailable');
      const bytes = await response.arrayBuffer();
      if (globalThis.crypto?.subtle) {
        const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(byte => byte.toString(16).padStart(2, '0')).join('');
        if (digest !== config.search.sha256) throw new Error('Search integrity mismatch');
      }
      const data = JSON.parse(new TextDecoder().decode(bytes));
      for (const key of ['schemaVersion', 'buildId', 'editorialReleaseId', 'datasetVersion']) if (data[key] !== config[key]) throw new Error('Search release mismatch');
      if (!Array.isArray(data.entries) || !data.entries.every(row => typeof row.name === 'string' && typeof row.summary === 'string' && typeof row.group === 'string' && Array.isArray(row.products) && row.products.every(value => typeof value === 'string') && typeof row.href === 'string' && row.href.startsWith('/') && !row.href.startsWith('//') && (row.aliases === undefined || Array.isArray(row.aliases) && row.aliases.every(value => typeof value === 'string')))) throw new Error('Invalid search index');
      entries = data.entries.map(row => ({ row, compiled: search.compile(row) })); return entries;
    }).finally(() => { clearTimeout(deadline); pending = null; });
    return pending;
  }
  function setActive(index) {
    const options = [...results.querySelectorAll('[role=option]')];
    active = index;
    options.forEach((node, position) => node.setAttribute('aria-selected', String(position === active)));
    if (active >= 0 && options[active]) {
      input.setAttribute('aria-activedescendant', options[active].id); options[active].scrollIntoView({ block: 'nearest' });
    } else input.removeAttribute('aria-activedescendant');
  }
  function render(paging = false) {
    const raw = input.value.trim(), key = search.normalize(raw);
    const selected = paging ? results.querySelector('[aria-selected=true]')?.getAttribute('href') : null;
    const matches = key ? entries.map(entry => ({ ...entry, rank: search.rank(entry.compiled, raw) })).filter(entry => entry.rank >= 0).sort((a, b) => a.rank - b.rank || search.compare(a.row, b.row)) : entries.slice(0, 7);
    const visible = matches.slice(0, shown), work = '/work/' + (raw ? '?' + new URLSearchParams({ q: raw }) : '');
    results.innerHTML = visible.map(({ row, compiled }, index) => {
      const alias = search.matchedAlias(compiled, raw);
      return `<a id="home-result-${index}" class="site-search-option" role="option" aria-selected="false" href="${escape(row.href)}"><strong>${escape(row.name)}</strong><span>${escape(alias ? 'Recorded alias: ' + alias + '. ' + row.summary : row.summary)}</span></a>`;
    }).join('') + `<a id="home-result-${visible.length}" class="site-search-option" role="option" aria-selected="false" href="${escape(work)}"><strong>${escape(raw ? 'Find paid work matching “' + raw + '”' : 'Browse paid work')}</strong><span>Public listings, expert networks and requirements</span></a>`;
    results.hidden = false; input.setAttribute('aria-expanded', 'true');
    const index = selected ? [...results.querySelectorAll('[role=option]')].findIndex(node => node.getAttribute('href') === selected) : -1;
    setActive(index);
    more.hidden = !key || visible.length >= matches.length;
    more.textContent = `Show ${Math.min(7, matches.length - visible.length)} more`;
    message.textContent = key ? (matches.length ? `Showing ${visible.length} of ${matches.length} matching guide records. Paid work uses its own listing filters.` : 'No recorded guide matches. You can search paid work or browse all companies.') : 'Search research, companies and their offerings, or continue to paid work.';
    announce(message.textContent);
    if (paging && more.hidden) input.focus();
  }
  window.openHomeSearch = async () => {
    const request = ++generation;
    if (!dialog.open) dialog.showModal();
    $('home-search-open').setAttribute('aria-expanded', 'true'); input.focus();
    try { await load(); if (request === generation && dialog.open) render(); }
    catch (error) {
      if (request !== generation || !dialog.open) return;
      clearResults(); message.innerHTML = 'Search could not load. <button type="button" data-home-search-retry>Try again</button> <a href="/companies/">Browse companies</a> or <a href="/work/">browse paid work</a>.'; announce('Search could not load. Retry or browse the native pages.');
    }
  };
  message.addEventListener('click', event => { if (event.target.closest('[data-home-search-retry]')) window.openHomeSearch(); });
  $('home-search-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { generation++; $('home-search-open').setAttribute('aria-expanded', 'false'); $('home-search-open').focus(); });
  input.addEventListener('input', event => { if (event.isComposing) return; shown = 7; if (entries) render(); });
  input.addEventListener('compositionend', () => { shown = 7; if (entries) render(); });
  more.addEventListener('click', () => { shown += 7; render(true); });
  input.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === 'Escape') { event.preventDefault(); dialog.close(); return; }
    const options = [...results.querySelectorAll('[role=option]')]; if (!options.length) return;
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : active < 0 ? (event.key === 'ArrowUp' ? options.length - 1 : 0) : (active + (event.key === 'ArrowDown' ? 1 : options.length - 1)) % options.length;
      setActive(next);
    }
    if (event.key === 'Enter' && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey) { event.preventDefault(); options[Math.max(active, 0)].click(); }
  });
})();
