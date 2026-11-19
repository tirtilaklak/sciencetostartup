/* Shared by the optional search components at build time; no extra request. */
(() => {
  'use strict';
  if (globalThis.S2SSearch) return;
  // Match both recorded TeX titles and the Greek spelling displayed in the UI.
  const mathTitle = value => String(value ?? '').replace(/\$\\tau(\^2)?\$/gu, (_, squared) => squared ? 'τ²' : 'τ').replace(/\\tau(\^2)?(?![\p{L}\p{N}_])/gu, (_, squared) => squared ? 'τ²' : 'τ');
  const normalize = value => mathTitle(value).normalize('NFKD').replace(/\p{M}+/gu, '').toLowerCase().replace(/\s+/gu, ' ').trim();
  const aliasName = value => String(value).replace(/\s*\([^()]*\)\s*$/u, '').trim();
  const values = value => Array.isArray(value) ? value.flatMap(values) : value == null ? [] : [String(value)];
  function compile(row) {
    const aliases = values(row.aliases).map(raw => ({ raw, key: normalize(aliasName(raw)) }));
    const name = normalize(row.name);
    const text = normalize([row.name, ...aliases.map(item => item.raw), ...values(row.summary), ...values(row.group), ...values(row.products), ...values(row.keywords), ...values(row.text)].join(' '));
    return { row, name, aliases, text };
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
  globalThis.S2SSearch = Object.freeze({ normalize, compile, rank, compare, matchedAlias });
})();

/* The plain work list stays complete when scripts are unavailable. */
(() => {
  const form = document.querySelector('[data-work-filters]');
  if (!form) return;
  const count = document.querySelector('[data-work-count]');
  const initialCount = count.textContent;
  const empty = document.querySelector('[data-work-empty]');
  const groupLinks = document.querySelector('.work-page-groups');
  const groups = [...document.querySelectorAll('[data-work-group]')];
  const query = form.elements.namedItem('q');
  const kind = form.elements.namedItem('kind');
  const arrangement = form.elements.namedItem('arrangement');
  const filterOptions = form.querySelector('.work-page-filter-options');
  const search = globalThis.S2SSearch;
  if (!search) { document.documentElement.removeAttribute('data-page-enhancement'); return; }
  let companyAliases = {};
  try { companyAliases = JSON.parse(document.getElementById('work-search-aliases')?.textContent || '{}'); } catch { /* Older markup still has complete visible records. */ }
  const aliases = card => {
    const company = card.querySelector('.work-company'), id = company?.getAttribute('href')?.match(/\/company\/([^/]+)\//)?.[1];
    return [company?.textContent || '', ...(Array.isArray(companyAliases[id]) ? companyAliases[id] : [])];
  };
  const records = groups.flatMap(group => [...group.querySelectorAll('[data-work-route]')].map((card, index) => ({
    card, group, index,
    compiled: search.compile({name: card.dataset.searchName || card.querySelector('.work-heading h3')?.textContent || '', aliases: aliases(card), text: card.dataset.search || ['.work-heading', '.work-offer', '.work-listing-conditions'].map(selector => card.querySelector(selector)?.textContent || '').join(' ')}),
    arrangements: (card.dataset.arrangements || '').split(' ')
  })));
  const initialOpen = new Map(groups.filter(group => group.tagName === 'DETAILS').map(group => [group, group.open]));
  let filtering = false;
  const validValue = (field, value) => [...field.options].some(option => option.value === value) ? value : '';
  function readURL() {
    const params = new URLSearchParams(location.search);
    query.value = (params.get('q') || '').slice(0, 256);
    kind.value = validValue(kind, params.get('kind') || '');
    arrangement.value = validValue(arrangement, params.get('arrangement') || '');
    if (filterOptions && (kind.value || arrangement.value)) filterOptions.open = true;
  }
  function render(updateURL = true) {
    const key = search.normalize(query.value);
    const active = Boolean(key || kind.value || arrangement.value);
    let matches = 0;
    const shownGroups = new Set();
    for (const record of records) {
      const place = arrangement.value;
      const fitsPlace = !place || (place === 'onsite' ? record.arrangements.some(value => value === 'onsite' || value === 'hybrid') : place === 'varies' ? !record.arrangements.some(value => ['remote', 'onsite', 'hybrid'].includes(value)) : record.arrangements.includes(place));
      record.rank = search.rank(record.compiled, key);
      const visible = (!kind.value || record.group.dataset.workGroup === kind.value) && fitsPlace && record.rank >= 0;
      record.card.hidden = !visible;
      if (visible) { matches++; shownGroups.add(record.group); }
    }
    for (const group of groups) {
      const own = records.filter(record => record.group === group), list = group.querySelector('.work-listings') || own[0]?.card.parentNode;
      if (list) own.sort((a, b) => (key ? a.rank - b.rank : 0) || a.index - b.index).forEach(record => list.append(record.card));
    }
    if (active && !filtering) for (const group of initialOpen.keys()) initialOpen.set(group, group.open);
    for (const group of groups) {
      group.hidden = !shownGroups.has(group);
      if (group.tagName === 'DETAILS') {
        if (active && !group.hidden) group.open = true;
        else if (!active && filtering) group.open = initialOpen.get(group);
      }
    }
    filtering = active;
    count.textContent = active ? `${matches} matching ${matches === 1 ? 'record' : 'records'}` : initialCount;
    empty.hidden = matches !== 0;
    if (groupLinks) groupLinks.hidden = active;
    if (updateURL) {
      const url = new URL(location.href);
      for (const [name, value] of [['q', query.value.trim()], ['kind', kind.value], ['arrangement', arrangement.value]]) {
        if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
      }
      if (url.href !== location.href) history.replaceState(history.state, '', url.href);
    }
  }
  function reset() {
    query.value = ''; kind.value = ''; arrangement.value = '';
    if (filterOptions) filterOptions.open = false;
    render(); query.focus();
  }
  function revealGroup(hash) {
    const target = document.getElementById(hash.replace(/^#/, ''));
    const group = target?.closest('details[data-work-group]');
    if (group) group.open = true;
  }
  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('input', () => render());
  form.addEventListener('change', () => render());
  form.addEventListener('reset', event => { event.preventDefault(); reset(); });
  empty.querySelector('[data-work-clear]')?.addEventListener('click', reset);
  groupLinks?.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#"]');
    if (link) revealGroup(link.getAttribute('href'));
  });
  window.addEventListener('hashchange', () => revealGroup(location.hash));
  window.addEventListener('popstate', () => { readURL(); render(false); });
  readURL(); render(false); revealGroup(location.hash); form.hidden = false;
  document.documentElement.removeAttribute('data-page-enhancement');
})();
