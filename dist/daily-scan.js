/* The complete reading list and archive remain available without JavaScript. */
(() => {
  'use strict';
  const root = document.querySelector('.daily-scan');
  if (!root) return;
  const search = document.getElementById('scan-search');
  const topic = document.getElementById('scan-topic');
  const kind = document.getElementById('scan-kind');
  const date = document.getElementById('scan-date');
  const dateForm = date.form;
  const dateGo = document.getElementById('scan-date-go');
  const archiveContent = root.querySelector('.scan-archive');
  const archive = archiveContent.closest('details');
  const archiveLinks = new Map([...archiveContent.querySelectorAll('a')].map(link => [new URL(link.href).pathname, link]));
  const editionLinks = root.querySelectorAll('a.scan-day-step, .scan-archive a');
  const reset = document.getElementById('scan-reset');
  const rows = [...root.querySelectorAll('.scan-item')];
  const rowById = new Map(rows.map(row => [row.id, row]));
  const readingKey = 's2sDailyReading';
  const maxPosition = 10000000;
  const navigationAPI = globalThis.navigation;
  const navigationState = typeof navigationAPI?.currentEntry?.getState === 'function' &&
    typeof navigationAPI.updateCurrentEntry === 'function' && typeof navigationAPI.addEventListener === 'function';
  let restoration = 0;
  const position = value => Number.isFinite(value) && value >= 0 && value <= maxPosition;
  function savedReading() {
    let entry;
    try { if (navigationState) entry = navigationAPI.currentEntry.getState(); } catch (_) {}
    for (const state of [entry?.[readingKey], history.state?.[readingKey]]) {
      if (!state || state.url !== location.href || state.edition !== root.dataset.edition ||
          !position(state.x) || !position(state.y) || !Array.isArray(state.open) ||
          state.open.length > rows.length || !state.open.every(id => rowById.has(id)) ||
          (state.anchor !== null && (!rowById.has(state.anchor) ||
            !Number.isFinite(state.top) || Math.abs(state.top) > maxPosition))) continue;
      return state;
    }
    return null;
  }
  function saveReading() {
    restoration++;
    // Navigation state is independent of classic History state. Updating it
    // saves this entry without starting another navigation during traversal.
    let state;
    try { state = navigationState ? navigationAPI.currentEntry.getState() : history.state; }
    catch (_) { return; }
    if (state != null && Object.prototype.toString.call(state) !== '[object Object]') return;
    const anchor = rows.find(row => !row.hidden && row.getBoundingClientRect().bottom > 0 &&
      row.getBoundingClientRect().top < innerHeight);
    const active = document.activeElement;
    const reading = { url: location.href, edition: root.dataset.edition,
      x: Math.max(0, Math.min(maxPosition, scrollX)), y: Math.max(0, Math.min(maxPosition, scrollY)),
      open: rows.filter(row => row.querySelector('details').open).map(row => row.id),
      anchor: anchor?.id || null, top: anchor?.getBoundingClientRect().top || 0,
      archiveOpen: archive.open,
      returnToArchive: active?.matches('.scan-archive a') ? new URL(active.href).pathname : null,
      returnToDateGo: active === dateGo };
    try {
      if (navigationState) navigationAPI.updateCurrentEntry({ state: { ...state, [readingKey]: reading } });
      else history.replaceState({ ...state, [readingKey]: reading }, '', location.href);
      history.scrollRestoration = 'manual';
    }
    catch (_) { /* Native history remains available when state cannot be saved. */ }
  }
  function restoreReading(scroll = true) {
    const saved = savedReading();
    const generation = ++restoration;
    function apply(current) {
      // Recreated documents lose native disclosure state. Layout and position
      // must be restored together after the browser finishes its traversal.
      for (const row of rows) row.querySelector('details').open = current.open.includes(row.id);
      if (typeof current.archiveOpen === 'boolean') archive.open = current.archiveOpen;
      try { history.scrollRestoration = 'manual'; } catch (_) { /* Restore below. */ }
      if (scroll) {
        const anchor = rowById.get(current.anchor);
        const y = anchor && !anchor.hidden ? scrollY + anchor.getBoundingClientRect().top - current.top : current.y;
        scrollTo({ left: current.x, top: Math.max(0, Math.min(maxPosition, y)), behavior: 'instant' });
        if (document.activeElement === document.body) {
          const archiveLink = archive.open ? archiveLinks.get(current.returnToArchive) : null;
          const returnFocus = current.returnToDateGo === true ? dateGo : archiveLink;
          returnFocus?.focus({ preventScroll: true });
        }
      }
      if (current.returnToDateGo === true) date.value = root.dataset.edition;
    }
    if (!scroll) { if (saved) apply(saved); }
    else setTimeout(() => {
      if (generation !== restoration) return;
      requestAnimationFrame(() => {
        if (generation !== restoration) return;
        // pageshow can precede history.state restoration. Read it in the later
        // task instead of abandoning the return when its early value is null.
        const current = savedReading();
        if (current) apply(current);
      });
    }, 0);
    return Boolean(saved);
  }
  const fold = value => value.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  const wordsIn = value => fold(value).match(/[\p{L}\p{N}]+/gu) || [];
  const text = new Map(rows.map(row => [row, wordsIn(
    [...row.querySelectorAll('h2,p,dd,.scan-meta span,.scan-topic-label')]
      .map(element => element.textContent).join(' ')
  )]));
  const params = new URLSearchParams(location.search);
  search.value = params.get('q') || '';
  for (const [control, key] of [[topic, 'topic'], [kind, 'type']]) {
    const value = params.get(key);
    if ([...control.options].some(option => option.value === value)) control.value = value;
  }
  function filter(updateURL = true) {
    const words = wordsIn(search.value);
    let visible = 0;
    for (const row of rows) {
      row.hidden = !words.every(word => text.get(row).some(candidate => candidate.startsWith(word))) ||
        Boolean(topic.value && !row.dataset.topics.split('|').includes(topic.value)) ||
        Boolean(kind.value && row.dataset.kind !== kind.value);
      if (!row.hidden) visible++;
    }
    document.getElementById('scan-count').textContent = `${visible} of ${rows.length} selections`;
    document.getElementById('scan-empty').hidden = visible !== 0;
    reset.hidden = !search.value && !topic.value && !kind.value;
    if (updateURL) {
      restoration++;
      const url = new URL(location.href);
      for (const [key, value] of [['q', search.value], ['topic', topic.value], ['type', kind.value]]) {
        if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
      }
      try {
        // replaceState resets Navigation state, including other components'
        // fields. Carry that independent state across this URL-only change.
        const entry = navigationState ? navigationAPI.currentEntry.getState() : undefined;
        history.replaceState(history.state, '', url);
        if (navigationState) navigationAPI.updateCurrentEntry({ state: entry });
      } catch (_) { /* Filtering still works. */ }
    }
    for (const link of editionLinks) {
      const target = new URL(link.href);
      target.search = location.search;
      link.href = target.href;
    }
  }
  function clear() { search.value = ''; topic.value = ''; kind.value = ''; filter(); search.focus(); }
  search.addEventListener('input', () => filter());
  topic.addEventListener('change', () => filter());
  kind.addEventListener('change', () => filter());
  reset.addEventListener('click', clear);
  document.getElementById('scan-empty-reset').addEventListener('click', clear);
  dateForm?.addEventListener('submit', event => {
    event.preventDefault();
    const selected = date.selectedOptions[0];
    if (!selected || selected.disabled || !/^\d{4}-\d{2}-\d{2}$/.test(selected.value)) return;
    const target = new URL('/daily/' + selected.value + '/', location.origin);
    target.search = location.search;
    if (target.href === location.href) return;
    dateGo?.focus({ preventScroll: true });
    saveReading();
    location.assign(target);
  });
  root.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href]');
    if (link && !link.hasAttribute('download') && (!link.target || link.target === '_self') &&
        new URL(link.href).origin === location.origin) saveReading();
  });
  if (navigationState) navigationAPI.addEventListener('navigate', event => {
    if (event.navigationType !== 'replace') saveReading();
  });
  // During pagehide WebKit can already expose the destination entry. Never
  // write History or Navigation state here; only cancel pending restoration.
  addEventListener('pagehide', () => { restoration++; });
  addEventListener('pageshow', () => restoreReading());
  addEventListener('popstate', () => restoreReading());
  function revealHash() {
    restoration++;
    const target = document.getElementById(location.hash.slice(1));
    if (target && target.classList.contains('scan-item')) {
      if (target.hidden) { search.value = ''; topic.value = ''; kind.value = ''; filter(); }
      target.querySelector('details').open = true;
      target.scrollIntoView({block: 'start'});
    }
  }
  addEventListener('hashchange', () => { if (!restoreReading()) revealHash(); });
  filter(false);
  if (dateForm) dateForm.hidden = false;
  root.querySelector('.scan-controls').hidden = false;
  document.documentElement.removeAttribute('data-daily-pending');
  // A fresh fragment reveals its target. A saved return first restores its
  // disclosures, then pageshow restores the position in that same layout.
  const timing = globalThis.performance?.getEntriesByType?.('navigation')?.[0];
  if (!restoreReading(false) && timing?.type !== 'back_forward') revealHash();
})();
