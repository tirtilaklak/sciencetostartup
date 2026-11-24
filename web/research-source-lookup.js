/* Search the current Research catalog and leave record navigation to the browser. */
(() => {
  'use strict';
  const form = document.querySelector('[data-source-lookup]');
  const search = globalThis.S2SSearch;
  if (!form || !search) return;

  const input = form.elements.source;
  const button = form.querySelector('button');
  const panel = form.closest('section');
  const status = panel.querySelector('[data-source-status]');
  const results = panel.querySelector('[data-source-results]');
  const limit = 24;
  const sourceHref = /^\/research\/data\/sources\/[0-9a-f]\/#source-(?:[A-Za-z0-9._-]|%[A-F0-9]{2})+$/u;
  let index;
  let searchSequence = 0;

  async function readIndex() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(form.dataset.sourceLookup, { signal: controller.signal });
      if (!response.ok) throw new Error('Source index is unavailable');
      const payload = await response.json();
      if (payload.version !== 1 || !Array.isArray(payload.sources)) throw new Error('Unknown source index');
      return payload.sources.map(source => {
        if (typeof source.title !== 'string' || typeof source.publisher !== 'string'
            || typeof source.href !== 'string' || !sourceHref.test(source.href)
            || ('captured' in source && typeof source.captured !== 'string')
            || ('locator' in source && typeof source.locator !== 'string')) {
          throw new Error('Invalid source index record');
        }
        return { ...source, titleKey: search.normalize(source.title), publisherKey: search.normalize(source.publisher) };
      });
    } finally {
      clearTimeout(timeout);
    }
  }

  function rank({ titleKey, publisherKey }, query, words) {
    if (titleKey === query) return 0;
    if (publisherKey === query) return 1;
    if (titleKey.startsWith(query)) return 2;
    if (publisherKey.startsWith(query)) return 3;
    if (words.every(word => titleKey.includes(word))) return 4;
    return words.every(word => titleKey.includes(word) || publisherKey.includes(word)) ? 5 : -1;
  }

  function resultItem(source, position) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    const detail = document.createElement('span');
    detail.id = `catalog-source-result-detail-${position}`;
    detail.className = 'r-meta';
    detail.textContent = source.publisher + (source.captured ? ` · Captured ${source.captured}` : '');
    if (source.locator) detail.append(document.createElement('br'), source.locator);
    link.href = source.href;
    link.textContent = source.title;
    link.setAttribute('aria-describedby', detail.id);
    item.append(link, detail);
    return item;
  }

  async function lookup(value) {
    const sequence = ++searchSequence;
    const query = search.normalize(value);
    button.textContent = 'Find sources';
    results.hidden = true;
    results.replaceChildren();
    if (!query) {
      status.textContent = 'Enter a source title or publisher.';
      return;
    }

    try {
      if (!index) {
        status.textContent = 'Loading source records…';
        index = readIndex().catch(error => {
          index = undefined;
          throw error;
        });
      }
      const sources = await index;
      if (sequence !== searchSequence) return;

      const words = query.split(' ');
      const matches = sources.map(source => ({ source, rank: rank(source, query, words) }))
        .filter(match => match.rank >= 0).sort((a, b) => a.rank - b.rank);
      results.append(...matches.slice(0, limit).map(({ source }, position) => resultItem(source, position)));
      results.hidden = !matches.length;
      if (!matches.length) {
        status.textContent = `No source records match “${value}”.`;
      } else if (matches.length > limit) {
        status.textContent = `Showing ${limit} of ${matches.length} sources for “${value}”. Use a longer title or publisher name to narrow the results.`;
      } else {
        const label = matches.length === 1 ? 'source matches' : 'sources match';
        status.textContent = `${matches.length} ${label} “${value}”.`;
      }
    } catch {
      if (sequence !== searchSequence) return;
      status.textContent = 'Source lookup couldn’t load. Try again or browse the source ledger below.';
      button.textContent = 'Try again';
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const value = input.value.trim();
    const url = new URL(location.href);
    if (value) {
      url.searchParams.set(input.name, value);
      url.hash = panel.id;
    } else {
      url.searchParams.delete(input.name);
    }
    if (url.href !== location.href) history.replaceState(history.state, '', url);
    lookup(value);
  });

  const saved = new URL(location.href).searchParams.get(input.name);
  form.hidden = false;
  if (saved?.trim()) {
    input.value = saved.slice(0, input.maxLength).trim();
    lookup(input.value);
  }
})();
