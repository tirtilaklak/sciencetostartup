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

/* Enhance the native index and navigate to exact matches. */
(() => {
  'use strict';
  const search = globalThis.S2SSearch;
  document.querySelectorAll('[data-research-index]').forEach(index => {
    const form = index.querySelector('[data-index-controls]');
    const field = form.elements.q;
    const papers = index.dataset.indexKind === 'papers';
    const controls = Array.from(form.elements).filter(control => control.name);
    const rows = Array.from(index.querySelectorAll('[data-index-row]')).map(node => ({
      node, text: search?.normalize(node.dataset.search) ?? node.dataset.search,
      facets: JSON.parse(node.dataset.filters),
      identifiers: node.dataset.searchIdentifiers && search ? search.identifiers(JSON.parse(node.dataset.searchIdentifiers)) : [],
      id: node.dataset.recordId || node.querySelector('th .r-record-id')?.textContent
    }));
    const byId = new Map(rows.map(row => [row.id, row]));
    const versions = Array.from(index.querySelectorAll('[data-index-versions]')).map(node => ({
      node, parent: byId.get(node.dataset.parentRecord), details: node.querySelector('details'),
      summaryContext: node.querySelector('summary > span'),
      context: node.querySelector('[data-index-context]'), records: rows.filter(row => node.contains(row.node))
    }));
    const initialOpen = new Map(versions.map(group => [group.details, group.details.open]));
    const count = index.querySelector('[data-index-count]');
    const empty = index.querySelector('[data-index-empty]');
    const advanced = form.querySelector('[data-index-advanced]');
    const advancedCount = form.querySelector('[data-index-advanced-count]');
    const advancedControls = controls.filter(control => !['q', 'status'].includes(control.name));
    const exactLookup = papers && rows.some(row => row.identifiers.length);
    const work = index.querySelector('[data-index-work]');
    const workLink = work?.querySelector('a');
    const workTitles = new Set(JSON.parse(index.querySelector('[data-index-work-titles]')?.textContent || '[]')
      .map(title => search?.normalize(title)));
    let destination;
    let filtering = false;
    function advancedActive() { return advancedControls.filter(control => control.value).length; }
    function apply() {
      const query = field.value;
      const identifier = exactLookup && search.identifier(query);
      const words = (search?.normalize(query) ?? query.trim().toLowerCase()).split(/\s+/).filter(Boolean);
      const active = controls.some(control => control.value.trim());
      let matching = 0, works = 0, sourceVersions = 0;
      let exactWork, exactVersion;
      if (active && !filtering) versions.forEach(group => initialOpen.set(group.details, group.details.open));
      rows.forEach(row => {
        const match = (identifier ? row.identifiers.includes(identifier) : words.every(word => row.text.includes(word))) && controls.every(control =>
          control.name === 'q' || !control.value || (control.value === '__not_recorded__'
            ? !(row.facets[control.name] || []).length : (row.facets[control.name] || []).includes(control.value)));
        row.node.hidden = !match;
        if (match) {
          matching += 1;
          if ((row.facets.type || []).includes('paper_version')) {
            sourceVersions += 1;
            if (identifier) exactVersion ??= row.node.querySelector('th a');
          } else {
            works += 1;
            if (identifier) exactWork ??= row.node.querySelector('th a');
          }
        }
      });
      versions.forEach(group => {
        const hasMatch = group.records.some(row => !row.node.hidden);
        group.node.hidden = !hasMatch;
        const parentVisible = Boolean(group.parent && !group.parent.node.hidden);
        group.summaryContext?.classList.toggle('sr-only', parentVisible);
        if (group.context) group.context.hidden = !active || !hasMatch || !group.parent?.node.hidden;
        if (active && hasMatch) group.details.open = true;
        else if (!active && filtering) group.details.open = initialOpen.get(group.details);
      });
      destination = exactWork || exactVersion;
      if (workLink) {
        work.hidden = !search?.isWorkQuery(query, workTitles);
        if (!work.hidden) {
          workLink.href = search.workUrl(query);
          destination = workLink;
        }
      }
      filtering = active;
      count.textContent = papers
        ? (active ? `${matching} of ${rows.length} matching records · ${works} paper works · ${sourceVersions} source versions`
          : `${works} paper works · ${sourceVersions} source versions (${rows.length} records)`)
        : `${matching} of ${rows.length} records shown`;
      if (advancedCount) advancedCount.textContent = `${advancedActive()} active`;
      empty.hidden = matching !== 0;
    }
    function restore() {
      const params = new URL(window.location.href).searchParams;
      controls.forEach(control => { control.value = params.get(control.name) || ''; });
      if (advanced) advanced.open = advancedActive() > 0;
      apply();
    }
    function update(replace) {
      apply();
      const url = new URL(window.location.href);
      controls.forEach(control => {
        if (control.value.trim()) url.searchParams.set(control.name, control.value);
        else url.searchParams.delete(control.name);
      });
      if (url.href !== window.location.href) window.history[replace ? 'replaceState' : 'pushState'](null, '', url);
    }
    form.addEventListener('submit', event => {
      event.preventDefault();
      update(false);
      if (document.activeElement === field && destination) window.location.assign(destination.href);
    });
    form.addEventListener('input', event => { if (event.target.name === 'q') update(true); });
    // A traversal can blur live search before popstate restores the controls.
    // Its delayed change event must not push stale values back over Back.
    form.addEventListener('change', event => { if (event.target.name !== 'q') update(false); });
    form.addEventListener('reset', event => {
      event.preventDefault();
      controls.forEach(control => { control.value = ''; });
      if (advanced) advanced.open = false;
      update(false);
      field.focus();
    });
    window.addEventListener('popstate', restore);
    restore();
    form.hidden = false;
  });
})();
