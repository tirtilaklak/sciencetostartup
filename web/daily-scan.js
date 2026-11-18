/* The complete reading list and archive remain available without JavaScript. */
(() => {
  'use strict';
  const root = document.querySelector('.daily-scan');
  if (!root) return;
  const search = document.getElementById('scan-search');
  const topic = document.getElementById('scan-topic');
  const kind = document.getElementById('scan-kind');
  const date = document.getElementById('scan-date');
  const reset = document.getElementById('scan-reset');
  const rows = [...root.querySelectorAll('.scan-item')];
  const rowById = new Map(rows.map(row => [row.id, row]));
  const readingKey = 's2sDailyReading';
  const maxPosition = 10000000;
  let restoration = 0;
  const position = value => Number.isFinite(value) && value >= 0 && value <= maxPosition;
  function savedReading() {
    const state = history.state?.[readingKey];
    if (!state || state.url !== location.href || state.edition !== root.dataset.edition ||
        !position(state.x) || !position(state.y) || !Array.isArray(state.open) ||
        state.open.length > rows.length || !state.open.every(id => rowById.has(id)) ||
        (state.anchor !== null && (!rowById.has(state.anchor) ||
          !Number.isFinite(state.top) || Math.abs(state.top) > maxPosition))) return null;
    return state;
  }
  function saveReading() {
    restoration++;
    // Keep another component's state intact, including non-object state.
    const state = history.state;
    if (state !== null && Object.prototype.toString.call(state) !== '[object Object]') return;
    const anchor = rows.find(row => !row.hidden && row.getBoundingClientRect().bottom > 0 &&
      row.getBoundingClientRect().top < innerHeight);
    const reading = { url: location.href, edition: root.dataset.edition,
      x: Math.max(0, Math.min(maxPosition, scrollX)), y: Math.max(0, Math.min(maxPosition, scrollY)),
      open: rows.filter(row => row.querySelector('details').open).map(row => row.id),
      anchor: anchor?.id || null, top: anchor?.getBoundingClientRect().top || 0 };
    try {
      history.replaceState({ ...state, [readingKey]: reading }, '', location.href);
      history.scrollRestoration = 'manual';
    }
    catch (_) { /* Native history remains available when state cannot be saved. */ }
  }
  function restoreReading(scroll = true) {
    const saved = savedReading();
    if (!saved) return false;
    // Recreated documents lose native disclosure state. Restore their layout
    // before restoring the reading position; a stale fragment must not win.
    for (const row of rows) row.querySelector('details').open = saved.open.includes(row.id);
    try { history.scrollRestoration = 'manual'; } catch (_) { /* Restore below. */ }
    const generation = ++restoration;
    if (scroll) requestAnimationFrame(() => {
      if (generation !== restoration || !savedReading()) return;
      const anchor = rowById.get(saved.anchor);
      const y = anchor && !anchor.hidden ? scrollY + anchor.getBoundingClientRect().top - saved.top : saved.y;
      scrollTo({ left: saved.x, top: Math.max(0, Math.min(maxPosition, y)), behavior: 'instant' });
    });
    return true;
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
      try { history.replaceState(history.state, '', url); } catch (_) { /* Filtering still works. */ }
    }
    for (const link of root.querySelectorAll('a.scan-day-step')) {
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
  date.addEventListener('change', () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date.value)) return;
    saveReading();
    location.assign('/daily/' + date.value + '/' + location.search);
  });
  root.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href]');
    if (link && !link.hasAttribute('download') && (!link.target || link.target === '_self') &&
        new URL(link.href).origin === location.origin) saveReading();
  });
  addEventListener('pagehide', saveReading);
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
  root.querySelector('.scan-controls').hidden = false;
  document.documentElement.removeAttribute('data-daily-pending');
  // A fresh fragment reveals its target. A saved return first restores its
  // disclosures, then pageshow restores the position in that same layout.
  const navigation = globalThis.performance?.getEntriesByType?.('navigation')?.[0];
  if (!restoreReading(false) && navigation?.type !== 'back_forward') revealHash();
})();
