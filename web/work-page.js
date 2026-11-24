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
    const sectionDetails = navigation?.closest('details');
    const sectionDisclosure = sectionDetails || navigation;
    const sectionTotals = sectionDisclosure?.querySelector('[data-work-section-totals]');
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
    const profileLinkSelector = '.work-heading a[href^="/company/"]';
    const sourceLinkSelector = '.work-listing-action a.ext[href], .work-terms a.ext[href]';
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
    const compareArrivalKey = 's2s.workCompareArrival';
    let compareDeparture;
    let cardClick, cardDeparture;
    let returnBookmark;
    let selection = [];
    let active = false;
    let displayedSearch;
    let readerInput = 0;
    for (const type of ['wheel', 'keydown', 'touchstart', 'pointerdown']) {
      addEventListener(type, event => { if (event.isTrusted) readerInput++; }, { capture: true, passive: true });
    }

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

    function restoreSectionDisclosure() {
      const open = history.state?.workSectionDisclosureOpen;
      if (sectionDetails && typeof open === 'boolean') sectionDetails.open = open;
    }

    function appendComparisonFields(cell, label, fields, className = 'work-compare-fields') {
      const values = fields.filter(Boolean);
      if (!values.length) return;
      const group = document.createElement('dl');
      group.className = className;
      const term = document.createElement('dt');
      term.textContent = label;
      group.append(term);
      for (const value of values) {
        const field = document.createElement('dd');
        field.textContent = value;
        group.append(field);
      }
      cell.append(group);
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
        appendComparisonFields(row.insertCell(), 'Pay', [
          [historicalLabel, amount?.textContent.trim()].filter(Boolean).join(' ') || 'Pay not listed',
          ...Array.from(pay?.querySelectorAll('strong ~ .sub') || [], note => note.textContent.trim()),
        ]);
        const detail = row.insertCell();
        const groupKind = card.closest('[data-work-group]')?.dataset.workKindLabel;
        const conditionFields = Array.from(card.querySelector('.work-listing-conditions').children, field => field.textContent.trim());
        if (groupKind && conditionFields.length) conditionFields[0] = groupKind + ' · ' + conditionFields[0];
        appendComparisonFields(detail, 'Location', [text(card, '.work-place')]);
        appendComparisonFields(detail, 'Terms and review', [
          ...conditionFields,
          text(card, '.work-reviewed'),
        ], 'work-compare-terms');
        const action = card.querySelector('.work-listing-action a');
        if (action) {
          const copy = action.cloneNode(true);
          copy.removeAttribute('id');
          copy.classList.add('work-compare-action');
          detail.append(copy);
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
        const headingCount = group.querySelector('[data-work-group-count]');
        if (headingCount) headingCount.textContent = matches.length;
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
      const hasResults = selection.length !== 0;
      list.hidden = showCompare;
      if (comparison) comparison.hidden = !showCompare || !hasResults;
      empty.hidden = hasResults;
      if (showCompare) comparisonRows(selection);
      const matchKeys = S2SWork.keys.filter(key => key !== 'sort' && criteria[key]);
      const record = selection.length === 1 ? 'record' : 'records';
      const hourlyOnly = matchKeys.length === 1 && criteria.pay === 'hourly';
      const countLabel = hourlyOnly ? `${selection.length} ${record} with published hourly pay`
        : matchKeys.length ? `${selection.length} matching ${record}` : initialCount;
      if (count.textContent !== countLabel) count.textContent = countLabel;
      if (sectionDisclosure) {
        sectionDisclosure.hidden = showCompare || !hasResults;
        if (sectionTotals) {
          const named = groups.named.length, programs = groups.programs.length;
          const companies = new Set([...groups.named, ...groups.programs].map(route => route.company_id)).size;
          sectionTotals.hidden = Boolean(matchKeys.length) && !named && !programs;
          sectionTotals.textContent = `${named} named ${named === 1 ? 'listing' : 'listings'} · ${programs} ${programs === 1 ? 'network or program' : 'networks and programs'} · ${companies} ${companies === 1 ? 'company' : 'companies'}`;
        }
        for (const link of navigation.querySelectorAll('[data-work-jump]')) {
          const key = link.dataset.workJump;
          const matches = groups[key].length;
          (link.closest('li') || link).hidden = !matches;
          const badge = link.querySelector('span');
          if (badge) badge.textContent = matches;
        }
      }
      if (compareLink) {
        compareLink.hidden = !showCompare && !hasResults;
        if (showCompare) url.searchParams.delete('view');
        else url.searchParams.set('view', 'compare');
        compareLink.href = url.pathname + url.search + url.hash;
        compareLink.textContent = showCompare ? 'Back to listings' : 'Compare results';
      }
      if (exportButton) exportButton.hidden = !hasResults;
      if (exportStatus) exportStatus.hidden = !hasResults;
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
        const input = readerInput;
        const previousFocus = document.activeElement;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          const active = document.activeElement;
          if (input !== readerInput || target !== targetFromHash() || target.closest('[hidden]') ||
              (active !== previousFocus && active !== document.body && active !== target)) return;
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
        const { kind, page, href, top, role, termsOpen, sourceIndex } = workReturnFocus;
        const card = cards.get(role);
        const link = kind === 'source' ? card?.querySelectorAll(sourceLinkSelector)[sourceIndex]
          : kind === 'profile' ? card?.querySelector(profileLinkSelector) : handoffLinks[kind];
        if (link && page === location.href && href === link.href) return { link, top, card, termsOpen };
      } else if (workCompareFocus && compareLink) return { link: compareLink };
      return null;
    }

    function restoreHandoff({ link, top, card, termsOpen }) {
      // A warm history traversal keeps this document and its browser-managed focus.
      // On a cold return, the browser may focus the opener's bookmark first.
      const bookmark = card && card === targetFromHash() ? card : null;
      const source = link.matches(sourceLinkSelector);
      const bookmarkHandoff = bookmark && { target: bookmark, recover: null };
      returnBookmark = bookmarkHandoff;
      const input = readerInput;
      const canRestore = () => input === readerInput && !loader?.interacted &&
        savedHandoff()?.link === link && !link.closest('[hidden]');

      function clearBookmark() {
        if (returnBookmark === bookmarkHandoff) returnBookmark = null;
      }

      function recoverBookmarkFocus() {
        if (returnBookmark === bookmarkHandoff && document.activeElement === bookmark && canRestore()) {
          link.focus({ preventScroll: true });
        }
      }

      function restorePosition() {
        const bounds = link.getBoundingClientRect();
        const headerBottom = Math.max(0, document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0);
        if (Number.isFinite(top) && top >= headerBottom && top + bounds.height <= innerHeight) {
          if (Math.abs(bounds.top - top) >= 1) window.scrollBy({ top: bounds.top - top, behavior: 'instant' });
        } else if (bounds.top < headerBottom || bounds.bottom > innerHeight) {
          link.scrollIntoView({ block: 'center', behavior: 'instant' });
        }
      }

      function settleReturnPosition(event) {
        if (event?.persisted) return clearBookmark();
        // WebKit can apply the native fragment focus and scroll after the
        // opener receives focus. Firefox can clear a source link's focus at pageshow.
        setTimeout(() => requestAnimationFrame(() => requestAnimationFrame(() => {
          recoverBookmarkFocus();
          if (source && document.activeElement === document.body && canRestore()) link.focus({ preventScroll: true });
          if (document.activeElement === link && canRestore()) restorePosition();
          clearBookmark();
        })), 0);
      }

      requestAnimationFrame(() => requestAnimationFrame(() => {
        const focusAvailable = document.activeElement === document.body || document.activeElement === bookmark;
        if (!focusAvailable || !canRestore()) return clearBookmark();
        const group = card?.closest('details[data-work-group]');
        if (group) group.open = true;
        const terms = termsOpen && card?.querySelector('details.work-terms');
        if (terms) terms.open = true;
        if (bookmarkHandoff) bookmarkHandoff.recover = () => queueMicrotask(recoverBookmarkFocus);
        link.focus({ preventScroll: true });
        restorePosition();
        if (bookmark || source) {
          if (document.readyState === 'complete') settleReturnPosition();
          else addEventListener('pageshow', settleReturnPosition, { once: true });
        }
      }));
    }

    function bindProfileArrival() {
      const saved = history.state?.workReturnFocus;
      const browserHistory = window.navigation;
      if (!browserHistory || saved?.kind !== 'profile' || saved.page !== location.href || saved.destinationKey !== undefined) return;
      // The original visit is the next history entry when Work is reactivated.
      // Keep its key so a new visit to the same profile URL cannot stand in for it.
      const next = browserHistory.entries()[(browserHistory.currentEntry?.index ?? -2) + 1];
      const destinationKey = next?.url === saved.href ? next.key : null;
      try { remember({ workReturnFocus: { ...saved, destinationKey } }); } catch {}
    }

    function followsHandoff() {
      const saved = history.state?.workReturnFocus;
      if (saved?.kind === 'source') {
        // Cross-origin history entries are opaque. Restore the last source link
        // saved on this Work entry when a cross-origin traversal recreates it.
        const activation = window.navigation?.activation;
        return !window.navigation || (activation?.navigationType === 'traverse' && !activation.from);
      }
      if (!window.navigation) return window.S2SNativeHandoff?.returnedFrom(saved?.entry);
      const { from, entry } = window.navigation.activation || {};
      if (saved?.kind === 'profile') {
        // The exact role visit must be the adjacent entry we just left on Back.
        return Boolean(saved.destinationKey && from?.key === saved.destinationKey &&
          from.url === saved.href && from.index === window.navigation.currentEntry?.index + 1);
      }
      return !(from && from.index <= entry?.index);
    }

    function sameTabActivation(event, link) {
      return event.isTrusted && !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey &&
        !event.shiftKey && !event.altKey && !link.hasAttribute('download') && (!link.target || link.target.toLowerCase() === '_self');
    }

    function recordCardDeparture() {
      const click = cardClick;
      const departure = cardDeparture;
      cardClick = cardDeparture = null;
      const leaving = departure && ['push', 'replace'].includes(departure.navigationType);
      const activated = click && !click.event.defaultPrevented && (window.navigation
        ? leaving && departure.navigationType === 'push' && departure.sourceElement === click.link && departure.destination.url === click.saved.href
        : click.saved.kind === 'source' || click.saved.entry);
      if (activated && click.saved.kind === 'source') return;
      // Record a profile visit once its navigation commits. Retain the opener
      // on browser traversals so a repeated Back can restore it again.
      if (!activated && (!leaving || !history.state?.workReturnFocus?.role)) return;
      try { remember({ workReturnFocus: activated ? click.saved : null, workCompareFocus: false }); } catch {}
    }

    function takeCompareArrival() {
      if (!comparison || window.top !== window) return false;
      try {
        if (!sessionStorage.getItem(compareArrivalKey)) return false;
        sessionStorage.removeItem(compareArrivalKey);
        if (comparison.hidden || !document.referrer || performance.getEntriesByType('navigation')[0]?.type !== 'navigate') return false;
        // Match the native same-tab link without storing the reader's search.
        const expected = new URL(document.referrer);
        expected.searchParams.set('view', 'compare');
        const arrival = new URL(location.href);
        arrival.hash = '';
        return expected.href === arrival.href;
      } catch {
        return false;
      }
    }

    function focusComparison() {
      const heading = comparison.querySelector('h2');
      const toolbar = compareLink.closest('[data-work-toolbar]');
      const arrival = location.href;
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (loader?.interacted || document.activeElement !== document.body || location.href !== arrival || comparison.hidden) return;
        heading.focus({ preventScroll: true });
        toolbar.scrollIntoView({ block: 'start', behavior: 'instant' });
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
    sectionDetails?.addEventListener('toggle', () => {
      remember({ workSectionDisclosureOpen: sectionDetails.open });
    });
    for (const [kind, link] of Object.entries(handoffLinks)) {
      link?.addEventListener('click', event => {
        if (!sameTabActivation(event, link)) return;
        if (link === compareLink && !list.hidden) {
          compareDeparture = event;
          if (sectionDetails) remember({ workSectionDisclosureOpen: sectionDetails.open });
        }
        const entry = window.S2SNativeHandoff?.begin(link.href, event);
        remember({ workReturnFocus: { kind, page: location.href, href: link.href, top: link.getBoundingClientRect().top, entry }, workCompareFocus: false });
      });
    }
    if (comparison && window.top === window) {
      list.addEventListener('click', event => {
        const link = event.target.closest?.(`${profileLinkSelector}, ${sourceLinkSelector}`);
        if (!link || !sameTabActivation(event, link)) return;
        const card = link.closest('[data-work-route]');
        if (!card) return;
        const profile = link.matches(profileLinkSelector);
        if (!profile && link.origin === location.origin) return;
        const kind = profile ? 'profile' : 'source';
        const entry = profile ? window.S2SNativeHandoff?.begin(link.href, event) : undefined;
        const sourceIndex = profile ? undefined : [...card.querySelectorAll(sourceLinkSelector)].indexOf(link);
        const saved = {
          kind, page: location.href, href: link.href, role: card.dataset.workRoute, sourceIndex,
          top: link.getBoundingClientRect().top, termsOpen: Boolean(card.querySelector('details.work-terms')?.open), entry,
        };
        cardClick = { link, event, saved };
        // WebKit can leave the origin before pagehide can update history.
        if (!profile) {
          try { remember({ workReturnFocus: saved, workCompareFocus: false }); } catch {}
        }
      });
      window.navigation?.addEventListener('navigate', event => {
        if (!event.destination.sameDocument) cardDeparture = event;
      });
      window.addEventListener('pageshow', event => { if (event.persisted) bindProfileArrival(); });
      window.addEventListener('pagehide', recordCardDeparture);
      window.addEventListener('pagehide', () => {
        const departure = compareDeparture;
        compareDeparture = null;
        if (!departure || departure.defaultPrevented) return;
        try { sessionStorage.setItem(compareArrivalKey, '1'); } catch {}
      });
    }
    document.addEventListener('focusin', event => {
      const handoff = savedHandoff();
      const bookmarkFocus = event.target === returnBookmark?.target && !loader?.interacted;
      if (bookmarkFocus) returnBookmark.recover?.();
      if (handoff && event.target !== handoff.link && !bookmarkFocus) remember({ workReturnFocus: null, workCompareFocus: false });
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
      bindProfileArrival();
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
    restoreSectionDisclosure();
    form.hidden = false;
    const retried = loader?.retried;
    const compareArrival = takeCompareArrival() && !loader?.interacted;
    bindProfileArrival();
    const handoff = !loader?.interacted && performance.getEntriesByType('navigation')[0]?.type === 'back_forward' &&
      followsHandoff() && savedHandoff();
    const revealed = !compareArrival && revealTarget(!handoff && (!loader?.interacted || retried));
    if (!compareArrival && !handoff && !revealed && targetFromHash()?.closest('[data-work-group]') && !loader?.interacted) {
      // A saved anchor can be excluded by the saved criteria.
      count.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
    loader?.complete(script);
    document.documentElement.removeAttribute('data-page-enhancement');
    if (compareArrival) focusComparison();
    else if (handoff) restoreHandoff(handoff);
    if (!revealed && retried) {
      // A failed load can leave the reader at a bookmark the filters now hide.
      fields.q.focus({ preventScroll: true });
      const { top, bottom } = fields.q.getBoundingClientRect();
      if (top < 0 || bottom > innerHeight) {
        form.scrollIntoView({ block: 'start', behavior: 'instant' });
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize, { once: true });
    loader?.waitingForDocument?.(script);
  } else initialize();
})();
