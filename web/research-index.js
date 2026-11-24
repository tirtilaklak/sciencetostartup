/* Enhance the native index and navigate to exact matches. */
(() => {
  'use strict';
  const search = globalThis.S2SSearch;
  const resultLinkSelector = '[data-index-row] a[href]:not([data-disclosure-return])';
  function installResultReturn(index, rowsById) {
    const navigation = window.navigation;
    if (!navigation) return;

    let clicked, departure;
    index.addEventListener('click', event => {
      clicked = null;
      const link = event.target.closest?.(resultLinkSelector);
      if (!link || !event.isTrusted || event.defaultPrevented || event.button !== 0 ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.hasAttribute('download') ||
          (link.target && link.target.toLowerCase() !== '_self') || link.origin !== location.origin) return;
      clicked = { link, event };
    });
    navigation.addEventListener('navigate', event => {
      const activation = clicked;
      clicked = null;
      departure = event.destination.sameDocument ? null : { event };
      const link = activation?.link;
      if (!departure || !event.isTrusted || event.navigationType !== 'push' ||
          !link || activation.event.defaultPrevented || event.sourceElement !== link ||
          event.destination.url !== link.href) return;
      departure.result = { page: location.href, href: link.href, row: link.closest('[data-index-row]').dataset.recordId };
    });
    addEventListener('pagehide', () => {
      const leaving = departure;
      departure = null;
      if (!leaving || leaving.event.defaultPrevented || leaving.event.signal.aborted ||
          leaving.event.navigationType === 'traverse') return;
      const { researchIndexReturn, ...state } = history.state || {};
      if (leaving.result?.page === location.href) state.researchIndexReturn = leaving.result;
      if (researchIndexReturn || state.researchIndexReturn) {
        try { history.replaceState(state, ''); } catch {}
      }
    });
    addEventListener('pageshow', event => {
      const { researchIndexReturn: saved, ...state } = history.state || {};
      if (!saved) return;
      const { from, entry } = navigation.activation || {};
      if (saved.page !== location.href || !from || !entry || from.index !== entry.index + 1 ||
          from.url !== saved.href || (saved.destinationKey && saved.destinationKey !== from.key)) {
        if (!saved.destinationKey) {
          try { history.replaceState(state, ''); } catch {}
        }
        return;
      }
      if (!saved.destinationKey) {
        // A subsequent Forward and Back must come from the same history entry.
        try { history.replaceState({ ...state, researchIndexReturn: { ...saved, destinationKey: from.key } }, ''); } catch {}
      }
      if (event.persisted || performance.getEntriesByType('navigation')[0]?.type !== 'back_forward') return;
      const input = new AbortController();
      for (const type of ['keydown', 'pointerdown', 'touchstart', 'wheel', 'pagehide']) {
        addEventListener(type, event => { if (event.isTrusted) input.abort(); },
          { capture: true, passive: true, signal: input.signal });
      }
      requestAnimationFrame(() => {
        if (input.signal.aborted) return;
        input.abort();
        if (document.activeElement !== document.body || navigation.currentEntry?.key !== entry.key ||
            location.href !== saved.page) return;
        const row = rowsById.get(saved.row)?.node;
        const link = row && [...row.querySelectorAll(resultLinkSelector)].find(link => link.href === saved.href);
        if (!link?.getClientRects().length) return;
        link.focus({ preventScroll: true });
        const bounds = link.getBoundingClientRect();
        if (bounds.bottom <= 0 || bounds.top >= innerHeight) {
          link.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
        }
      });
    });
  }

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
    installResultReturn(index, byId);
  });
})();
