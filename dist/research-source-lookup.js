/* Shared by the optional search components at build time; no extra request. */
(() => {
  'use strict';
  if (globalThis.S2SSearch) return;
  // Match both recorded TeX titles and the Greek spelling displayed in the UI.
  const mathTitle = value => String(value ?? '').replace(/\$\\tau(\^2)?\$/gu, (_, squared) => squared ? 'τ²' : 'τ').replace(/\\tau(\^2)?(?![\p{L}\p{N}_])/gu, (_, squared) => squared ? 'τ²' : 'τ');
  const normalize = value => mathTitle(value).normalize('NFKD').replace(/\p{M}+/gu, '').toLowerCase().replace(/\s+/gu, ' ').trim();
  const aliasName = value => String(value).replace(/\s*\([^()]*\)\s*$/u, '').trim();
  const values = value => Array.isArray(value) ? value.flatMap(values) : value == null ? [] : [String(value)];
  const arxiv = /^(?:\d{4}\.\d{4,5}|[a-z][a-z.-]*\/\d{7})(?:v[1-9]\d*)?$/u;
  const doi = /^10\.\d{4,9}\/\S+$/u;
  const record = /^paper\.[a-z0-9_-]+(?:\.[a-z0-9_-]+)+$/u;
  function identifier(value) {
    let text = String(value ?? '').trim().toLowerCase();
    let type = '';
    if (/^https?:\/\//u.test(text) || text.startsWith('/research/papers/')) {
      let url, path;
      try {
        url = new URL(text, 'https://sciencetostartup.com');
        path = decodeURIComponent(url.pathname).toLowerCase();
      } catch { return ''; }
      if (url.username || url.password || url.port) return '';
      if (['arxiv.org', 'www.arxiv.org', 'export.arxiv.org'].includes(url.hostname)) {
        const match = path.match(/^\/(abs|pdf|html)\/(.+?)\/?$/u);
        if (!match) return '';
        type = 'arxiv';
        text = match[1] === 'pdf' ? match[2].replace(/\.pdf$/u, '') : match[2];
      } else if (['doi.org', 'dx.doi.org'].includes(url.hostname)) {
        type = 'doi'; text = path.slice(1);
      } else if (url.hostname === 'sciencetostartup.com') {
        type = 'record'; text = path.match(/^\/research\/papers\/([^/]+)\/?$/u)?.[1] || '';
      } else return '';
    } else {
      const prefix = text.match(/^(arxiv|doi):\s*/u);
      if (prefix) { type = prefix[1]; text = text.slice(prefix[0].length); }
    }
    if ((!type || type === 'arxiv') && arxiv.test(text)) return 'arxiv:' + text;
    if ((!type || type === 'doi') && doi.test(text)) return 'doi:' + text;
    if ((!type || type === 'record') && record.test(text)) return 'record:' + text;
    return '';
  }
  const identifiers = value => [...new Set(values(value).map(identifier).filter(Boolean))];
  const leadingWork = /^(?:jobs?|careers?|hiring|vacancies|openings)(?:\s+(?:for|in))?(?=\s|$)/iu;
  const trailingWork = /(?:^|\s)(?:jobs?|careers?|vacancies|openings)\s*$/iu;
  const researchTerms = /\b(?:papers?|datasets?|benchmarks?|literature|arxiv|doi)\b/iu;
  function explicitWork(value) {
    const text = String(value ?? '').trim();
    return !researchTerms.test(text) && (leadingWork.test(text) || trailingWork.test(text));
  }
  function isWorkQuery(value, titles) {
    return !identifier(value) && (explicitWork(value) || Boolean(titles?.has(normalize(value))));
  }
  function workTerms(value) {
    const text = String(value ?? '');
    return explicitWork(text) ? text.trim().replace(leadingWork, '').replace(trailingWork, '').trim() : text;
  }
  const workUrl = value => '/work/' + (String(value ?? '').trim() ? '?' + new URLSearchParams({ q: value }) : '');
  const hourlyWork = Object.freeze({
    name: 'See roles with published hourly pay',
    summary: 'Includes past listings',
    href: '/work/?pay=hourly'
  });
  const hourlyWorkShortcut = value => {
    const key = normalize(value);
    return key === 'hourly' || key === 'hourly pay' ? hourlyWork : null;
  };
  function compile(row) {
    const aliases = values(row.aliases).map(raw => ({ raw, key: normalize(aliasName(raw)) }));
    const name = normalize(row.name);
    const text = normalize([row.name, ...aliases.map(item => item.raw), ...values(row.summary), ...values(row.group), ...values(row.products), ...values(row.keywords), ...values(row.text)].join(' '));
    return { row, name, aliases, text, identifiers: identifiers(row.identifiers) };
  }
  function rank(entry, query) {
    const key = normalize(query);
    if (!key) return 0;
    if (entry.name === key || entry.aliases.some(alias => alias.key === key)) return 0;
    if (entry.name.startsWith(key)) return 1;
    if (entry.aliases.some(alias => alias.key.startsWith(key))) return 2;
    const words = key.split(' ');
    if (words.every(word => entry.name.includes(word))) return 3;
    return words.every(word => entry.text.includes(word)) ? 4 : -1;
  }
  function compare(a, b) {
    const left = normalize(a.name), right = normalize(b.name);
    // Equally relevant navigation hubs precede individual source versions.
    const priority = row => /^\/company\//u.test(row.href || '') ? 0 : ['report', 'research', 'data', 'review', 'daily'].includes(row.group) || /^\/daily\//u.test(row.href || '') ? 1 : 2;
    return priority(a) - priority(b) || (left < right ? -1 : left > right ? 1 : 0) || String(a.href || a.id || '').localeCompare(String(b.href || b.id || ''), 'en');
  }
  function matchedAlias(entry, query) {
    const key = normalize(query);
    if (!key || entry.name.includes(key)) return '';
    return entry.aliases.find(alias => alias.key === key || alias.key.startsWith(key))?.raw || '';
  }
  globalThis.S2SSearch = Object.freeze({ normalize, identifier, identifiers, isWorkQuery, workTerms, workUrl, hourlyWorkShortcut, compile, rank, compare, matchedAlias });
})();

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
