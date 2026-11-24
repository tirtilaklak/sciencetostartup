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

  const savedQuery = new URL(location.href).searchParams.get(input.name);
  let query, initialLookup;
  form.hidden = false;
  if (savedQuery?.trim()) {
    query = savedQuery.slice(0, input.maxLength).trim();
    input.value = query;
    initialLookup = lookup(query);
  }

  const browserHistory = window.navigation;
  if (!browserHistory) return;

  let resultClick, departure;
  results.addEventListener('click', event => { resultClick = event; });
  browserHistory.addEventListener('navigate', event => {
    const click = resultClick;
    resultClick = departure = undefined;
    if (!click?.isTrusted || click.defaultPrevented || click.button !== 0 ||
        click.ctrlKey || click.metaKey || click.shiftKey || click.altKey) return;
    const link = event.sourceElement;
    if (!event.isTrusted || event.navigationType !== 'push' || event.destination.sameDocument ||
        !(link instanceof HTMLAnchorElement) || click.target.closest?.('a[href]') !== link ||
        event.destination.url !== link.href) return;
    const href = link.getAttribute('href');
    if (!sourceHref.test(href)) return;
    departure = { event, opener: { page: location.href, href, top: link.getBoundingClientRect().top } };
  });
  addEventListener('pagehide', () => {
    const visit = departure;
    departure = undefined;
    if (!visit || visit.event.defaultPrevented || visit.event.signal.aborted) return;
    try { history.replaceState({ ...history.state, sourceLookupReturn: visit.opener }, ''); } catch {}
  });

  function nextRecord(opener) {
    if (opener?.page !== location.href || !sourceHref.test(opener.href)) return;
    const entry = browserHistory.currentEntry;
    if (!entry) return;
    const record = browserHistory.entries()[entry.index + 1];
    if (record?.url === new URL(opener.href, location.origin).href &&
        (opener.recordKey === undefined || record.key === opener.recordKey)) return record;
  }

  addEventListener('pageshow', () => {
    const opener = history.state?.sourceLookupReturn;
    if (!opener) return;
    // A push has no destination key until it commits. Bind it even after a cached Back,
    // so Forward can revisit this record but another entry at the same address cannot replay it.
    const record = nextRecord(opener);
    if (record && opener.recordKey === record.key) return;
    const state = { ...history.state };
    if (record) state.sourceLookupReturn = { ...opener, recordKey: record.key };
    else delete state.sourceLookupReturn;
    try { history.replaceState(state, ''); } catch {}
  });

  const opener = history.state?.sourceLookupReturn;
  const record = nextRecord(opener);
  const activation = browserHistory.activation;
  if (!initialLookup || !record || !Number.isFinite(opener.top) ||
      performance.getEntriesByType('navigation')[0]?.type !== 'back_forward' || activation?.navigationType !== 'traverse' ||
      activation.from?.key !== record.key) return;

  const interaction = new AbortController();
  const { signal } = interaction;
  const initialSequence = searchSequence;
  for (const type of ['keydown', 'pointerdown', 'touchstart', 'wheel', 'focusin', 'input']) {
    addEventListener(type, event => { if (event.isTrusted) interaction.abort(); }, { capture: true, passive: true, signal });
  }
  addEventListener('pagehide', () => interaction.abort(), { once: true, signal });
  addEventListener('pageshow', async event => {
    try {
      if (event.persisted) return;
      await initialLookup;
      const link = Array.from(results.querySelectorAll('a[href]')).find(result => result.getAttribute('href') === opener.href);
      if (signal.aborted || !link) return;
      await document.fonts.ready;
      // Both the results and the browser's own history scroll need to settle.
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (signal.aborted || initialSequence !== searchSequence || location.href !== opener.page || input.value !== query ||
          (document.activeElement !== document.body && document.activeElement !== link)) return;
      const { top, height } = link.getBoundingClientRect();
      const offset = Math.max(0, Math.min(opener.top, innerHeight - height));
      scrollBy({ top: top - offset, behavior: 'instant' });
      link.focus({ preventScroll: true });
    } finally {
      interaction.abort();
    }
  }, { once: true, signal });
})();
