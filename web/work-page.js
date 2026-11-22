/* The plain work list stays complete when scripts are unavailable. */
(() => {
  const loader = window.WorkPageResource;
  const script = document.currentScript;
  if (loader && !loader.accepts(script)) return;

  function initialize() {
    if (loader && !loader.accepts(script)) return;
    const form = document.querySelector('[data-work-filters]');
    if (!form) return;
    const list = document.querySelector('.work-page-list');
    const count = document.querySelector('[data-work-count]');
    const empty = document.querySelector('[data-work-empty]');
    const navigation = document.querySelector('[data-work-section-navigation]');
    const compareLink = document.querySelector('[data-work-compare]');
    const exploreLink = document.querySelector('[data-work-explore]');
    const comparison = document.querySelector('[data-work-comparison]');
    const exportButton = document.querySelector('[data-work-export]');
    const exportStatus = document.querySelector('[data-work-export-status]');
    const filterOptions = form.querySelector('.work-page-filter-options');
    const filterSummary = filterOptions.querySelector('summary');
    const groupElements = new Map([...list.querySelectorAll('[data-work-group]')].map(group => [group.dataset.workGroup, group]));
    const fields = Object.fromEntries(S2SWork.keys.map(key => [key, form.elements.namedItem(key)]));
    const cards = new Map([...list.querySelectorAll('[data-work-route]')].map(card => [card.dataset.workRoute, card]));
    const records = window.WORK_NATIVE_SELECTION.filter(route => cards.has(route.id)).map(route => ({
      ...route, card: cards.get(route.id)
    }));
    if (records.length !== cards.size) throw new Error('Work selection does not match the page');
    const initialOpen = new Map([...groupElements.values()].filter(group => group.tagName === 'DETAILS').map(group => [group, group.open]));
    let selection = [];
    let active = false;
    let displayedSearch;

    function readURL() {
      const criteria = S2SWork.readCriteria(new URLSearchParams(location.search));
      for (const [key, input] of Object.entries(fields)) if (input) input.value = criteria[key];
      const selectedOption = S2SWork.keys.some(key => key !== 'q' && criteria[key]);
      if (selectedOption) filterOptions.open = true;
    }

    const text = (card, selector) => card.querySelector(selector)?.textContent.trim() || '';

    function comparisonRows(results) {
      const heading = comparison.querySelector('h2');
      comparison.replaceChildren(heading);
      if (!results.length) return;
      const region = document.createElement('div');
      region.className = 'work-compare-scroll';
      region.tabIndex = 0;
      region.setAttribute('role', 'region');
      region.setAttribute('aria-label', 'Matching work records');
      const table = document.createElement('table');
      const header = table.createTHead().insertRow();
      for (const label of ['Listing or program', 'Recorded pay', 'Location and terms']) {
        const column = document.createElement('th');
        column.scope = 'col';
        column.textContent = label;
        header.append(column);
      }
      const body = table.createTBody();
      for (const { id, card, company_name } of results) {
        const row = body.insertRow();
        row.dataset.compareRoute = id;
        const identity = document.createElement('th');
        identity.scope = 'row';
        identity.textContent = [company_name, text(card, 'h3'), text(card, '.work-status')].filter(Boolean).join(' · ');
        row.append(identity);
        row.insertCell().textContent = text(card, '.work-historical-pay') || text(card, '.work-pay') || 'Pay not listed';
        const detail = row.insertCell();
        detail.append([text(card, '.work-place'), text(card, '.work-listing-conditions'), text(card, '.work-reviewed')].filter(Boolean).join(' · '));
        const action = card.querySelector('.work-listing-action a');
        if (action) {
          const copy = action.cloneNode(true);
          copy.removeAttribute('id');
          detail.append(' ', copy);
        }
      }
      region.append(table);
      comparison.append(region);
    }

    function currentCriteria() {
      return S2SWork.normalizeCriteria(Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input?.value])));
    }

    function render(updateURL = false) {
      const criteria = currentCriteria();
      const url = new URL(location.href);
      if (updateURL) {
        S2SWork.writeCriteria(url.searchParams, criteria);
        if (url.href !== location.href) history.replaceState(history.state, '', url.href);
      }
      displayedSearch = location.search;
      const showCompare = url.searchParams.get('view') === 'compare';
      const groups = S2SWork.groupResults(S2SWork.select(records, criteria, route => route.searchText), criteria.sort, criteria.q);
      selection = S2SWork.groups.flatMap(key => groups[key]);
      const selectedIds = new Set(selection.map(route => route.id));
      const optionCount = S2SWork.keys.filter(key => key !== 'q' && criteria[key]).length;
      const filtering = Boolean(criteria.q || optionCount);
      if (filtering && !active) {
        for (const group of initialOpen.keys()) initialOpen.set(group, group.open);
      }
      filterSummary.textContent = optionCount ? `Filters (${optionCount})` : 'Filters';
      for (const { id, card } of records) card.hidden = !selectedIds.has(id);
      for (const [key, group] of groupElements) {
        const matches = groups[key];
        group.hidden = !matches.length;
        const cards = group.querySelector('.work-listings');
        if (matches.some(({ card }, index) => index && Boolean(matches[index - 1].card.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_PRECEDING))) {
          for (const { card } of matches) cards.append(card);
        }
        if (group.tagName === 'DETAILS') {
          const badge = group.querySelector(':scope > summary span');
          if (badge) badge.textContent = matches.length;
          if (filtering && matches.length) group.open = true;
          else if (!filtering && active) group.open = initialOpen.get(group);
        }
      }
      active = filtering;
      list.hidden = showCompare;
      comparison.hidden = !showCompare;
      empty.hidden = selection.length !== 0;
      if (showCompare) comparisonRows(selection);
      count.textContent = `${selection.length} ${filtering ? 'matching ' : ''}${selection.length === 1 ? 'record' : 'records'}`;
      if (navigation) {
        navigation.hidden = showCompare || !selection.length;
        for (const link of navigation.querySelectorAll('[data-work-jump]')) {
          const key = link.dataset.workJump;
          const matches = groups[key].length;
          (link.closest('li') || link).hidden = !matches;
          const badge = link.querySelector('span');
          if (badge) badge.textContent = matches;
        }
      }
      if (showCompare) url.searchParams.delete('view');
      else url.searchParams.set('view', 'compare');
      compareLink.href = url.pathname + url.search + url.hash;
      compareLink.textContent = showCompare ? 'Back to listings' : 'Compare results';
      const search = S2SWork.writeCriteria(new URLSearchParams(), criteria).toString();
      if (exploreLink) exploreLink.href = '/explore/#work' + (search ? '?' + search : '');
    }

    function reset() {
      for (const input of Object.values(fields)) if (input) input.value = '';
      filterOptions.open = false;
      render(true);
      fields.q.focus();
    }

    function targetFromHash() {
      try { return document.getElementById(decodeURIComponent(location.hash.slice(1))); }
      catch { return null; }
    }

    function revealTarget(focus) {
      const target = targetFromHash();
      if (!target?.closest('[data-work-group]') || target.closest('[hidden]')) return false;
      const group = target.closest('details[data-work-group]');
      if (group) group.open = true;
      if (focus) {
        // The browser can finish its own fragment scroll after scripts run.
        requestAnimationFrame(() => requestAnimationFrame(() => {
          if (target !== targetFromHash() || target.closest('[hidden]')) return;
          target.focus({ preventScroll: true });
          target.scrollIntoView({ block: 'start', behavior: 'instant' });
        }));
      }
      return true;
    }

    function restoreJumpFocus() {
      const key = history.state?.workJumpFocus;
      const jump = key && [...(navigation?.querySelectorAll('[data-work-jump]') || [])].find(link => link.hash === key);
      if (!jump || jump.closest('[hidden]')) return false;
      const disclosure = jump.closest('details');
      if (disclosure) disclosure.open = true;
      jump.focus({ preventScroll: true });
      return true;
    }

    form.addEventListener('submit', event => event.preventDefault());
    form.addEventListener('input', () => render(true));
    form.addEventListener('change', () => render(true));
    form.addEventListener('reset', event => { event.preventDefault(); reset(); });
    empty.querySelector('[data-work-clear]')?.addEventListener('click', reset);
    navigation?.addEventListener('click', event => {
      const link = event.target.closest('[data-work-jump]');
      if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      history.replaceState({ ...history.state, workJumpFocus: link.hash }, '', location.href);
      const target = document.getElementById(link.hash.slice(1));
      const disclosure = target?.closest('details[data-work-group]');
      if (disclosure) disclosure.open = true;
      if (link.hash === location.hash) revealTarget(true);
    });
    window.addEventListener('hashchange', () => {
      if (!restoreJumpFocus()) revealTarget(true);
    });
    window.addEventListener('popstate', () => {
      if (displayedSearch !== location.search) { readURL(); render(); }
    });
    exportButton.addEventListener('click', async () => {
      if (exportButton.getAttribute('aria-busy') === 'true') return;
      const { workExportAsset: href, workExportDigest: sha256 } = exportButton.dataset;
      exportButton.setAttribute('aria-busy', 'true');
      if (exportStatus) exportStatus.textContent = 'Preparing your CSV…';
      try {
        const body = await S2SWork.fetchExport({ href, sha256 }, selection.map(route => route.id), currentCriteria());
        S2SWork.downloadCsv(body);
        if (exportStatus) exportStatus.textContent = '';
      } catch {
        if (exportStatus) exportStatus.textContent = 'The CSV could not load. Choose Download CSV to try again.';
      } finally {
        exportButton.removeAttribute('aria-busy');
      }
    });
    readURL();
    render();
    form.hidden = compareLink.hidden = exportButton.hidden = false;
    const revealed = revealTarget(!loader?.interacted || loader?.retried);
    if (!revealed && loader?.retried) fields.q.focus({ preventScroll: true });
    if (!revealed && targetFromHash()?.closest('[data-work-group]') && !loader?.interacted) {
      // A saved anchor can be excluded by the saved criteria.
      count.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
    loader?.complete(script);
    document.documentElement.removeAttribute('data-page-enhancement');
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
