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
    const initialCount = count.textContent;
    const empty = document.querySelector('[data-work-empty]');
    const navigation = document.querySelector('[data-work-section-navigation]');
    const compareLink = document.querySelector('[data-work-compare]');
    const exploreLink = document.querySelector('[data-work-explore]');
    const handoffLinks = { compare: compareLink, explore: exploreLink };
    const comparison = document.querySelector('[data-work-comparison]');
    const exportButton = document.querySelector('[data-work-export]');
    const exportStatus = document.querySelector('[data-work-export-status]');
    const legacy = !compareLink && !exportButton;
    const legacyNavigation = legacy && document.querySelector('.work-page-groups');
    const filterOptions = form.querySelector('.work-page-filter-options');
    const filterSummary = filterOptions.querySelector('summary');
    const groupElements = new Map([...list.querySelectorAll('[data-work-group]')].map(group => [group.dataset.workGroup, group]));
    const fields = Object.fromEntries(S2SWork.keys.map(key => [key, form.elements.namedItem(key)]));
    const cards = new Map([...list.querySelectorAll('[data-work-route]')].map(card => [card.dataset.workRoute, card]));
    const text = (card, selector) => card.querySelector(selector)?.textContent.trim() || '';
    // An older page can still request the current unversioned enhancer. Its own
    // cards supply search terms and groups so a newer release cannot change their facts.
    const legacyKinds = { named: 'named_listing', programs: 'network_program', boards: 'career_page', outside: 'named_listing', closed: 'other_record' };
    const legacyRecords = () => [...cards].map(([id, card]) => {
      const group = card.closest('[data-work-group]').dataset.workGroup;
      const search = ['.work-heading', '.work-offer', '.work-listing-conditions'].map(selector => text(card, selector)).join(' ');
      return {
        id, card,
        route_kind: legacyKinds[group], ai_data_work: group !== 'outside',
        arrangements: (card.dataset.arrangements || '').split(' '),
        searchText: S2SWork.fold(search).replace(/\s+/g, ' '),
      };
    });
    const records = legacy ? legacyRecords() : window.WORK_NATIVE_SELECTION.filter(route => cards.has(route.id)).map(route => ({
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
    }

    function remember(changes) {
      history.replaceState({ ...history.state, ...changes }, '');
    }

    function restoreFilterOptions() {
      const open = history.state?.workFilterOptionsOpen;
      if (typeof open === 'boolean') filterOptions.open = open;
      else remember({ workFilterOptionsOpen: filterOptions.open });
    }

    function appendComparisonFields(cell, fields) {
      for (const value of fields) {
        if (!value) continue;
        const field = document.createElement('div');
        field.textContent = value;
        if (cell.hasChildNodes()) cell.append('\n');
        cell.append(field);
      }
    }

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
        const pay = card.querySelector('.work-pay');
        const amount = pay?.querySelector('strong');
        const historicalLabel = amount?.previousElementSibling?.textContent.trim();
        appendComparisonFields(row.insertCell(), [
          [historicalLabel, amount?.textContent.trim()].filter(Boolean).join(' ') || 'Pay not listed',
          ...Array.from(pay?.querySelectorAll('strong ~ .sub') || [], note => note.textContent.trim()),
        ]);
        const detail = row.insertCell();
        appendComparisonFields(detail, [
          text(card, '.work-place'),
          ...Array.from(card.querySelector('.work-listing-conditions').children, field => field.textContent.trim()),
          text(card, '.work-reviewed'),
        ]);
        const action = card.querySelector('.work-listing-action a');
        if (action) {
          const copy = action.cloneNode(true);
          copy.removeAttribute('id');
          detail.append('\n', copy);
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
        if (legacy) {
          for (const key of ['q', 'kind', 'arrangement']) {
            if (criteria[key]) url.searchParams.set(key, criteria[key]);
            else url.searchParams.delete(key);
          }
        } else S2SWork.writeCriteria(url.searchParams, criteria);
        if (url.href !== location.href) history.replaceState(history.state, '', url.href);
      }
      displayedSearch = location.search;
      const showCompare = !legacy && url.searchParams.get('view') === 'compare';
      const matches = S2SWork.select(records, legacy ? { ...criteria, q: '' } : criteria, route => route.searchText);
      const words = legacy && S2SWork.fold(criteria.q).trim().split(/\s+/).filter(Boolean);
      const groups = legacy ? Object.fromEntries(S2SWork.groups.map(key => [key, matches.filter(route =>
        S2SWork.bucket(route) === key && words.every(word => route.searchText.includes(word)))]))
        : S2SWork.groupResults(matches, criteria.sort, criteria.q);
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
          if (!legacy && badge) badge.textContent = matches.length;
          if (filtering && matches.length) group.open = true;
          else if (!filtering && active) group.open = initialOpen.get(group);
        }
      }
      active = filtering;
      if (legacyNavigation) legacyNavigation.hidden = filtering;
      list.hidden = showCompare;
      if (comparison) comparison.hidden = !showCompare;
      empty.hidden = selection.length !== 0;
      if (showCompare) comparisonRows(selection);
      const matchKeys = S2SWork.keys.filter(key => key !== 'sort' && criteria[key]);
      const record = selection.length === 1 ? 'record' : 'records';
      const hourlyOnly = matchKeys.length === 1 && criteria.pay === 'hourly';
      const countLabel = hourlyOnly ? `${selection.length} ${record} with published hourly pay`
        : matchKeys.length ? `${selection.length} matching ${record}` : initialCount;
      if (count.textContent !== countLabel) count.textContent = countLabel;
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
      if (compareLink) {
        if (showCompare) url.searchParams.delete('view');
        else url.searchParams.set('view', 'compare');
        compareLink.href = url.pathname + url.search + url.hash;
        compareLink.textContent = showCompare ? 'Back to listings' : 'Compare results';
      }
      const search = S2SWork.writeCriteria(new URLSearchParams(), criteria).toString();
      if (exploreLink) exploreLink.href = '/explore/#work' + (search ? '?' + search : '');
    }

    function reset() {
      for (const input of Object.values(fields)) if (input) input.value = '';
      filterOptions.open = false;
      remember({ workFilterOptionsOpen: false });
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

    function savedHandoff() {
      const { workReturnFocus, workCompareFocus } = history.state || {};
      if (workReturnFocus) {
        const link = handoffLinks[workReturnFocus.kind];
        if (workReturnFocus.page === location.href && workReturnFocus.href === link?.href) return { link, top: workReturnFocus.top };
      } else if (workCompareFocus && compareLink) return { link: compareLink };
      return null;
    }

    function restoreHandoff({ link, top }) {
      // A warm history traversal keeps this document and its browser-managed focus.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (loader?.interacted || document.activeElement !== document.body || savedHandoff()?.link !== link || link.closest('[hidden]')) return;
        link.focus({ preventScroll: true });
        const bounds = link.getBoundingClientRect();
        const headerBottom = Math.max(0, document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0);
        if (Number.isFinite(top) && top >= headerBottom && top + bounds.height <= innerHeight) {
          window.scrollBy({ top: bounds.top - top, behavior: 'instant' });
        } else if (bounds.top < headerBottom || bounds.bottom > innerHeight) {
          link.scrollIntoView({ block: 'center', behavior: 'instant' });
        }
      }));
    }

    form.addEventListener('submit', event => event.preventDefault());
    form.addEventListener('input', () => render(true));
    form.addEventListener('change', () => render(true));
    form.addEventListener('reset', event => { event.preventDefault(); reset(); });
    empty.querySelector('[data-work-clear]')?.addEventListener('click', reset);
    filterSummary.addEventListener('click', event => {
      if (!event.defaultPrevented) remember({ workFilterOptionsOpen: !filterOptions.open });
    });
    for (const [kind, link] of Object.entries(handoffLinks)) {
      link?.addEventListener('click', event => {
        if (!event.isTrusted || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
            link.hasAttribute('download') || (link.target && link.target.toLowerCase() !== '_self')) return;
        remember({ workReturnFocus: { kind, page: location.href, href: link.href, top: link.getBoundingClientRect().top }, workCompareFocus: false });
      });
    }
    document.addEventListener('focusin', event => {
      const handoff = savedHandoff();
      if (handoff && event.target !== handoff.link) remember({ workReturnFocus: null, workCompareFocus: false });
    });
    navigation?.addEventListener('click', event => {
      const link = event.target.closest('[data-work-jump]');
      if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      remember({ workJumpFocus: link.hash });
      const target = document.getElementById(link.hash.slice(1));
      const disclosure = target?.closest('details[data-work-group]');
      if (disclosure) disclosure.open = true;
      if (link.hash === location.hash) revealTarget(true);
    });
    window.addEventListener('hashchange', () => {
      if (!restoreJumpFocus()) revealTarget(true);
    });
    window.addEventListener('popstate', () => {
      restoreFilterOptions();
      if (displayedSearch !== location.search) { readURL(); render(); }
    });
    exportButton?.addEventListener('click', async () => {
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
    filterOptions.open = loader?.initialOptionsOpen ?? S2SWork.keys.some(key => key !== 'q' && fields[key]?.value);
    restoreFilterOptions();
    render();
    form.hidden = false;
    if (compareLink) compareLink.hidden = false;
    if (exportButton) exportButton.hidden = false;
    const retried = loader?.retried;
    const activation = window.navigation?.activation;
    const goingForward = activation?.from && activation.from.index <= activation.entry?.index;
    const handoff = !goingForward && !loader?.interacted && performance.getEntriesByType('navigation')[0]?.type === 'back_forward' && savedHandoff();
    const revealed = revealTarget(!handoff && (!loader?.interacted || retried));
    if (!handoff && !revealed && targetFromHash()?.closest('[data-work-group]') && !loader?.interacted) {
      // A saved anchor can be excluded by the saved criteria.
      count.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
    loader?.complete(script);
    document.documentElement.removeAttribute('data-page-enhancement');
    if (handoff) restoreHandoff(handoff);
    if (!revealed && retried) {
      // A failed load can leave the reader at a bookmark the filters now hide.
      fields.q.focus({ preventScroll: true });
      const { top, bottom } = fields.q.getBoundingClientRect();
      if (top < 0 || bottom > innerHeight) {
        form.scrollIntoView({ block: 'start', behavior: 'instant' });
      }
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
