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
      const url = new URL(location.href);
      for (const [key, value] of [['q', search.value], ['topic', topic.value], ['type', kind.value]]) {
        if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
      }
      try { history.replaceState(null, '', url); } catch (_) { /* Filtering still works. */ }
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
    location.assign('/daily/' + date.value + '/' + location.search);
  });
  function revealHash() {
    const target = document.getElementById(location.hash.slice(1));
    if (target && target.classList.contains('scan-item')) {
      if (target.hidden) { search.value = ''; topic.value = ''; kind.value = ''; filter(); }
      target.querySelector('details').open = true;
      target.scrollIntoView({block: 'start'});
    }
  }
  addEventListener('hashchange', revealHash);
  filter(false);
  root.querySelector('.scan-controls').hidden = false;
  document.documentElement.removeAttribute('data-daily-pending');
  // A history reload must leave scroll restoration to the browser, just as a
  // cached page does. A fresh visit (or later hash change) reveals its target.
  const navigation = globalThis.performance?.getEntriesByType?.('navigation')?.[0];
  if (navigation?.type !== 'back_forward') revealHash();
})();
