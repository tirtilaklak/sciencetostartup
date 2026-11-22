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
