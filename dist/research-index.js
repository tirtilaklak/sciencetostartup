/* Enhance complete native records. No requests, navigation interception or claims. */
(() => {
  'use strict';
  document.querySelectorAll('[data-research-index]').forEach(index => {
    const form = index.querySelector('[data-index-controls]');
    const controls = Array.from(form.elements).filter(control => control.name);
    const normalize = value => value.normalize('NFKC').toLowerCase();
    const rows = Array.from(index.querySelectorAll('[data-index-row]')).map(node => ({
      node, search: normalize(node.dataset.search), facets: JSON.parse(node.dataset.filters),
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
    const applied = form.querySelector('[data-index-applied]');
    const advancedControls = controls.filter(control => !['q', 'status'].includes(control.name));
    const papers = index.dataset.indexKind === 'papers';
    let filtering = false;
    function advancedActive() { return advancedControls.filter(control => control.value).length; }
    function showApplied() {
      if (!applied) return;
      const fragment = document.createDocumentFragment();
      controls.filter(control => control.value.trim()).forEach(control => {
        const label = control.name === 'q' ? 'Search' : control.closest('label').firstChild.textContent.trim();
        const value = control.name === 'q' ? control.value.trim() : control.selectedOptions[0].textContent;
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.removeFilter = control.name;
        button.setAttribute('aria-label', `Remove ${label}: ${value}`);
        const text = document.createElement('span');
        text.textContent = `${label}: ${value}`;
        const remove = document.createElement('span');
        remove.textContent = '×';
        remove.setAttribute('aria-hidden', 'true');
        button.append(text, remove);
        fragment.append(button);
      });
      applied.replaceChildren(fragment);
      applied.hidden = !applied.childElementCount;
    }
    function apply() {
      const query = normalize(form.elements.q.value.trim()).split(/\s+/).filter(Boolean);
      const active = controls.some(control => control.value.trim());
      let matching = 0, works = 0, sourceVersions = 0;
      if (active && !filtering) versions.forEach(group => initialOpen.set(group.details, group.details.open));
      rows.forEach(row => {
        const match = query.every(word => row.search.includes(word)) && controls.every(control =>
          control.name === 'q' || !control.value || (control.value === '__not_recorded__'
            ? !(row.facets[control.name] || []).length : (row.facets[control.name] || []).includes(control.value)));
        row.node.hidden = !match;
        if (match) {
          matching += 1;
          if ((row.facets.type || []).includes('paper_version')) sourceVersions += 1;
          else works += 1;
        }
      });
      versions.forEach(group => {
        const hasMatch = group.records.some(row => !row.node.hidden);
        group.node.hidden = !hasMatch;
        if (group.context) group.context.hidden = !active || !hasMatch || !group.parent?.node.hidden;
        if (active && hasMatch) group.details.open = true;
        else if (!active && filtering) group.details.open = initialOpen.get(group.details);
      });
      filtering = active;
      count.textContent = papers
        ? (active ? `${matching} of ${rows.length} matching records · ${works} paper works · ${sourceVersions} source versions`
          : `${works} paper works · ${sourceVersions} source versions (${rows.length} records)`)
        : `${matching} of ${rows.length} records shown`;
      if (advancedCount) advancedCount.textContent = `${advancedActive()} active`;
      empty.hidden = matching !== 0;
      showApplied();
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
        if (control.value.trim()) url.searchParams.set(control.name, control.value.trim());
        else url.searchParams.delete(control.name);
      });
      if (url.href !== window.location.href) window.history[replace ? 'replaceState' : 'pushState'](null, '', url);
    }
    form.addEventListener('submit', event => { event.preventDefault(); update(false); });
    form.addEventListener('input', event => { if (event.target.name === 'q') update(true); });
    // A traversal can blur live search before popstate restores the controls.
    // Its delayed change event must not push stale values back over Back.
    form.addEventListener('change', event => { if (event.target.name !== 'q') update(false); });
    form.addEventListener('reset', event => {
      event.preventDefault();
      controls.forEach(control => { control.value = ''; });
      if (advanced) advanced.open = false;
      update(false);
      form.elements.q.focus();
    });
    applied?.addEventListener('click', event => {
      const button = event.target.closest('button[data-remove-filter]');
      if (!button) return;
      const position = Array.from(applied.children).indexOf(button);
      form.elements[button.dataset.removeFilter].value = '';
      update(false);
      (applied.children[Math.min(position, applied.childElementCount - 1)] || form.elements.q).focus();
    });
    window.addEventListener('popstate', restore);
    restore();
    form.hidden = false;
  });
})();
