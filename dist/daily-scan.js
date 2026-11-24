/* The complete reading list and archive remain available without JavaScript. */
(() => {
  'use strict';
  const root = document.querySelector('.daily-scan');
  if (!root) return;
  const search = document.getElementById('scan-search');
  const topic = document.getElementById('scan-topic');
  const kind = document.getElementById('scan-kind');
  const filterDisclosure = root.querySelector('.scan-filter-disclosure');
  const filterSummary = filterDisclosure.querySelector('summary');
  const compact = matchMedia('(max-width: 600px)');
  const date = document.getElementById('scan-date');
  const dateForm = date.form;
  const dateGo = document.getElementById('scan-date-go');
  const archiveContent = root.querySelector('.scan-archive');
  const archive = archiveContent.closest('details');
  const archiveLinks = new Map([...archiveContent.querySelectorAll('a')].map(link => [new URL(link.href).pathname, link]));
  const daySteps = new Map([...root.querySelectorAll('a.scan-day-step')].map(link => [link.rel, link]));
  const editionLinks = [...daySteps.values(), ...archiveLinks.values()];
  const reset = document.getElementById('scan-reset');
  const rows = [...root.querySelectorAll('.scan-item')];
  const rowById = new Map(rows.map(row => [row.id, row]));
  const sourceLinks = [...root.querySelectorAll('.scan-item h2 a, .scan-sources a')];
  const menu = document.querySelector('.site-header > .site-menu');
  const navigationLinks = [...root.querySelectorAll('.scan-follow a'), ...(menu?.querySelectorAll('a') || [])];
  const readingKey = 's2sDailyReading';
  const filterKey = 's2sDailyFilters';
  const maxPosition = 10000000;
  const navigationAPI = globalThis.navigation;
  const navigationState = typeof navigationAPI?.currentEntry?.getState === 'function' &&
    typeof navigationAPI.updateCurrentEntry === 'function' && typeof navigationAPI.addEventListener === 'function';
  const timing = globalThis.performance?.getEntriesByType?.('navigation')?.[0];
  function hashTarget() {
    try { return rowById.get(decodeURIComponent(location.hash.slice(1))); }
    catch (_) { return undefined; }
  }
  let markedFragment = null;
  function syncFragmentHighlight() {
    // A recreated WebKit document can have a valid fragment without a native :target.
    const row = hashTarget();
    const visibleTarget = row && !row.hidden ? row : null;
    if (visibleTarget === markedFragment) return;
    markedFragment?.removeAttribute('data-fragment-target');
    visibleTarget?.setAttribute('data-fragment-target', '');
    markedFragment = visibleTarget;
  }
  const disclosureObserver = navigationState ? null : new MutationObserver(mutations => {
    const details = hashTarget()?.querySelector('details');
    if (mutations.some(mutation => mutation.target === details)) saveReading();
  });
  const filterObserver = navigationState ? null : new MutationObserver(() => {
    if (compact.matches) saveClassicFilters();
  });
  let coldFragmentURL = timing?.type === 'back_forward' && hashTarget() ? location.href : null;
  let resumedDocument = false;
  let restoration = 0;
  let compactFiltersOpen = false;
  function showFilters(open) {
    compactFiltersOpen = open;
    filterDisclosure.open = !compact.matches || open;
    filterObserver?.takeRecords();
  }
  function savedClassicFilters() {
    const state = history.state?.[filterKey];
    return !navigationState && state?.url === location.href && typeof state.open === 'boolean' ? state : null;
  }
  function saveClassicFilters() {
    try {
      const state = history.state;
      if (state != null && Object.prototype.toString.call(state) !== '[object Object]') return;
      const active = document.activeElement;
      history.replaceState({ ...state, [filterKey]: { url: location.href,
        open: filterDisclosure.open, focusSummary: active === filterSummary, focusSearch: active === search } }, '');
      history.scrollRestoration = 'auto';
    } catch (_) { /* Keep native disclosure and history behavior. */ }
  }
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
  function saveReading(link, mirrorToHistory = false) {
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
    const sourceIndex = sourceLinks.indexOf(link);
    const navigationLink = link ?? active;
    const navigationIndex = navigationLinks.indexOf(navigationLink);
    const reading = { url: location.href, edition: root.dataset.edition,
      x: Math.max(0, Math.min(maxPosition, scrollX)), y: Math.max(0, Math.min(maxPosition, scrollY)),
      open: rows.filter(row => row.querySelector('details').open).map(row => row.id),
      anchor: anchor?.id || null, top: anchor?.getBoundingClientRect().top || 0,
      archiveOpen: archive.open,
      filtersOpen: compact.matches ? filterDisclosure.open : compactFiltersOpen,
      returnToFilterSummary: active === filterSummary,
      returnToPermalink: active?.matches('.scan-permalink') ? active.closest('.scan-item')?.id : null,
      returnToSource: sourceIndex < 0 ? null : { index: sourceIndex, href: link.href },
      returnToNavigation: navigationIndex < 0 ? null : { index: navigationIndex, href: navigationLink.href },
      returnToDayStep: active?.matches('.scan-day-step') ? active.rel : null,
      returnToArchive: active?.matches('.scan-archive a') ? new URL(active.href).pathname : null,
      returnToDateGo: active === dateGo };
    try {
      const next = { ...state, [readingKey]: reading };
      if (navigationState) {
        // A cold cross-origin return can lose Navigation API state in WebKit.
        const classic = mirrorToHistory ? history.state : undefined;
        if (mirrorToHistory && (classic == null || Object.prototype.toString.call(classic) === '[object Object]')) {
          history.replaceState({ ...classic, [readingKey]: reading }, '', location.href);
        }
        navigationAPI.updateCurrentEntry({ state: next });
      } else {
        delete next[filterKey];
        history.replaceState(next, '', location.href);
      }
      history.scrollRestoration = 'manual';
    }
    catch (_) { /* Native history remains available when state cannot be saved. */ }
  }
  function restoreReading(scroll = true, changedHash = false) {
    const generation = ++restoration;
    function apply(current, filters) {
      // Recreated documents lose native disclosure state. Layout and position
      // must be restored together after the browser finishes its traversal.
      const reading = filters ? null : current;
      const navigation = reading?.returnToNavigation;
      let navigationLink = Number.isInteger(navigation?.index) ? navigationLinks[navigation.index] : null;
      if (navigationLink?.href !== navigation?.href) navigationLink = null;
      if (navigationLink && menu?.contains(navigationLink)) {
        if (menu.getClientRects().length) menu.open = true;
        else navigationLink = [...menu.parentElement.querySelectorAll(':scope > .site-nav a')]
          .find(link => link.href === navigation.href);
      }
      if (current) {
        for (const row of rows) row.querySelector('details').open = current.open.includes(row.id);
        if (typeof current.archiveOpen === 'boolean') archive.open = current.archiveOpen;
        if (reading?.returnToDateGo === true && compact.matches) archive.open = true;
        disclosureObserver?.takeRecords();
      }
      if (reading) {
        try { history.scrollRestoration = 'manual'; } catch (_) { /* Restore below. */ }
      }
      const filtersOpen = filters?.open ?? current?.filtersOpen;
      if (typeof filtersOpen === 'boolean') showFilters(filtersOpen);
      let returnFocus;
      if (scroll) {
        if (reading) {
          const anchor = rowById.get(reading.anchor);
          const y = anchor && !anchor.hidden ? scrollY + anchor.getBoundingClientRect().top - reading.top : reading.y;
          scrollTo({ left: reading.x, top: Math.max(0, Math.min(maxPosition, y)), behavior: 'instant' });
          const item = rowById.get(reading.returnToPermalink);
          returnFocus = item && !item.hidden ? item.querySelector('details[open] .scan-permalink') : null;
        }
        // Fragment traversal can leave focus or the next Tab at the target
        // article. Restore the originating link after reopening its details.
        if (!returnFocus && document.activeElement === document.body) {
          const source = reading?.returnToSource;
          const sourceLink = Number.isInteger(source?.index) ? sourceLinks[source.index] : null;
          if (sourceLink && sourceLink.href === source.href && !sourceLink.closest('[hidden], details:not([open])')) {
            returnFocus = sourceLink;
          }
          if (navigationLink?.getClientRects().length && !navigationLink.closest('[hidden], details:not([open])')) {
            returnFocus ??= navigationLink;
          }
          const archiveLink = archive.open ? archiveLinks.get(reading?.returnToArchive) : null;
          const focusSummary = compact.matches && (filters?.focusSummary ?? reading?.returnToFilterSummary) === true;
          const focusSearch = filterDisclosure.open && filters?.focusSearch === true;
          returnFocus ??= focusSummary ? filterSummary : focusSearch ? search :
            reading?.returnToDateGo === true ? dateGo : archiveLink || daySteps.get(reading?.returnToDayStep);
        }
        returnFocus?.focus({ preventScroll: true });
      }
      if (reading?.returnToDateGo === true) date.value = root.dataset.edition;
      return returnFocus;
    }
    if (!scroll) {
      const saved = savedReading();
      const filters = timing?.type === 'back_forward' ? savedClassicFilters() : null;
      if (saved || filters) apply(saved, filters);
      return Boolean(saved);
    }
    function complete() {
      const current = savedReading();
      const filters = changedHash || timing?.type === 'back_forward' ? savedClassicFilters() : null;
      const target = changedHash || coldFragmentURL === location.href ? hashTarget() : null;
      coldFragmentURL = null;
      if (!current && target) revealHash(target);
      const returnFocus = (current || filters) && apply(current, filters);

      // Browsers can retain focus from the previous fragment or lose its
      // Tab starting point on a cold return. Honor the saved origin first.
      if (target && !target.hidden && !returnFocus && (changedHash || document.activeElement === document.body)) {
        const heading = target.querySelector('h2');
        const box = heading.getBoundingClientRect();
        if (!current || (box.bottom > 0 && box.top < innerHeight)) {
          heading.tabIndex = -1;
          heading.focus({ preventScroll: true });
        }
      }
    }
    // Hash traversal has already applied native state by hashchange. Set the
    // Tab starting point now and supersede the pending popstate restoration.
    if (changedHash) { complete(); return; }
    setTimeout(() => {
      if (generation !== restoration) return;
      requestAnimationFrame(() => {
        if (generation !== restoration) return;
        // pageshow can precede history.state restoration. Read it in the later
        // task instead of abandoning the return when its early value is null.
        complete();
      });
    }, 0);
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
    syncFragmentHighlight();
    document.getElementById('scan-count').textContent = `${visible} of ${rows.length} selections`;
    document.getElementById('scan-empty').hidden = visible !== 0;
    reset.hidden = !search.value && !topic.value && !kind.value;
    if (updateURL) {
      restoration++;
      const url = new URL(location.href);
      // A newly filtered URL should reproduce these results when shared or reloaded.
      if (hashTarget()?.hidden) url.hash = '';
      for (const [key, value] of [['q', search.value], ['topic', topic.value], ['type', kind.value]]) {
        if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
      }
      try {
        // replaceState resets Navigation state, including other components'
        // fields. Carry that independent state across this URL-only change.
        const entry = navigationState ? navigationAPI.currentEntry.getState() : undefined;
        const filters = savedClassicFilters();
        const state = filters ? { ...history.state, [filterKey]: { ...filters, url: url.href } } : history.state;
        history.replaceState(state, '', url);
        if (navigationState) navigationAPI.updateCurrentEntry({ state: entry });
      } catch (_) { /* Filtering still works. */ }
    }
    for (const link of editionLinks) {
      const target = new URL(link.href);
      target.search = location.search;
      link.href = target.href;
    }
  }
  function clear() {
    search.value = '';
    topic.value = '';
    kind.value = '';
    filter();
    if (compact.matches) showFilters(true);
    search.focus();
    if (filterObserver && compact.matches) {
      const saved = savedClassicFilters();
      if (!saved?.open || !saved.focusSearch) saveClassicFilters();
    }
  }
  compact.addEventListener('change', event => {
    const active = document.activeElement;
    showFilters(event.matches ? compactFiltersOpen || filterDisclosure.contains(active) : filterDisclosure.open);
    if (!event.matches && active === filterSummary) search.focus({ preventScroll: true });
  });
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
  function rememberLink(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest?.('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const sameOrigin = new URL(link.href).origin === location.origin;
    if (sameOrigin || sourceLinks.includes(link) || navigationLinks.includes(link)) {
      saveReading(link, !sameOrigin || Boolean(history.state?.[readingKey]));
    }
  }
  root.addEventListener('click', rememberLink);
  menu?.addEventListener('click', rememberLink);
  if (navigationState) navigationAPI.addEventListener('navigate', event => {
    if (event.navigationType !== 'replace') saveReading(event.sourceElement);
  });
  // Classic History has no event before browser Back leaves the entry. Save
  // a changed fragment disclosure in the same task as its native toggle.
  disclosureObserver?.observe(root, { subtree: true, attributeFilter: ['open'] });
  // Record a manual filter toggle on this entry, leaving its scroll to the browser.
  if (filterObserver) {
    filterObserver.observe(filterDisclosure, { attributeFilter: ['open'] });
    document.addEventListener('focusin', event => {
      const saved = savedClassicFilters();
      if (compact.matches && saved && (saved.focusSummary !== (event.target === filterSummary) ||
          (saved.focusSearch === true) !== (event.target === search))) saveClassicFilters();
    });
  }
  // During pagehide WebKit can already expose the destination entry. Never
  // write History or Navigation state here; only cancel pending restoration.
  addEventListener('pagehide', () => { restoration++; coldFragmentURL = null; });
  addEventListener('pageshow', event => {
    resumedDocument = event.persisted;
    syncFragmentHighlight();
    if (!resumedDocument) restoreReading();
  });
  addEventListener('popstate', () => {
    syncFragmentHighlight();
    if (!resumedDocument) restoreReading();
  });
  function revealHash(target = hashTarget()) {
    restoration++;
    coldFragmentURL = null;
    if (target) {
      if (target.hidden) { search.value = ''; topic.value = ''; kind.value = ''; filter(); }
      target.querySelector('details').open = true;
      disclosureObserver?.takeRecords();
      target.scrollIntoView({block: 'start'});
    }
  }
  addEventListener('hashchange', () => {
    resumedDocument = false;
    syncFragmentHighlight();
    restoreReading(true, true);
  });
  filter(false);
  root.setAttribute('data-daily-enhanced', '');
  showFilters(Boolean(search.value || topic.value || kind.value));
  if (dateForm) dateForm.hidden = false;
  filterDisclosure.hidden = false;
  document.documentElement.removeAttribute('data-daily-pending');
  // A fresh fragment reveals its target. A saved return first restores its
  // disclosures, then pageshow restores the position in that same layout.
  if (!restoreReading(false) && timing?.type !== 'back_forward') revealHash();
})();
