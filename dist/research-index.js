/* Enhance the complete native table. No requests, navigation interception or claims. */
(() => {
  'use strict';
  document.querySelectorAll('[data-research-index]').forEach(index => {
    const form = index.querySelector('[data-index-controls]');
    const controls = Array.from(form.elements).filter(control => control.name);
    const rows = Array.from(index.querySelectorAll('[data-index-row]')).map(node => ({
      node, search: node.dataset.search, facets: JSON.parse(node.dataset.filters)
    }));
    const count = index.querySelector('[data-index-count]');
    const empty = index.querySelector('[data-index-empty]');
    function apply() {
      const query = form.elements.q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
      let visible = 0;
      rows.forEach(row => {
        const match = query.every(word => row.search.includes(word)) && controls.every(control =>
          control.name === 'q' || !control.value || (control.value === '__not_recorded__'
            ? !(row.facets[control.name] || []).length : (row.facets[control.name] || []).includes(control.value)));
        row.node.hidden = !match;
        if (match) visible += 1;
      });
      count.textContent = `${visible} of ${rows.length} records shown`;
      empty.hidden = visible !== 0;
    }
    function restore() {
      const params = new URL(window.location.href).searchParams;
      controls.forEach(control => { control.value = params.get(control.name) || ''; });
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
    form.addEventListener('change', () => update(false));
    form.addEventListener('reset', event => {
      event.preventDefault();
      controls.forEach(control => { control.value = ''; });
      update(false);
    });
    window.addEventListener('popstate', restore);
    restore();
    form.hidden = false;
  });
})();
