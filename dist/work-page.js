/* The plain work list stays complete when scripts are unavailable. */
(() => {
  const form = document.querySelector('[data-work-filters]');
  if (!form) return;
  const count = document.querySelector('[data-work-count]');
  const empty = document.querySelector('[data-work-empty]');
  const groupLinks = document.querySelector('.work-page-groups');
  const groups = [...document.querySelectorAll('[data-work-group]')];
  const query = form.elements.namedItem('q');
  const kind = form.elements.namedItem('kind');
  const arrangement = form.elements.namedItem('arrangement');
  const fold = value => String(value || '').normalize('NFKD').replace(/\p{M}/gu, '').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
  const records = groups.flatMap(group => [...group.querySelectorAll('[data-work-route]')].map(card => ({
    card, group,
    text: fold(['.work-heading', '.work-offer', '.work-listing-conditions'].map(selector => card.querySelector(selector)?.textContent || '').join(' ')),
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
  }
  function render(updateURL = true) {
    const words = fold(query.value).split(' ').filter(Boolean);
    const active = Boolean(words.length || kind.value || arrangement.value);
    let matches = 0;
    const shownGroups = new Set();
    for (const record of records) {
      const place = arrangement.value;
      const fitsPlace = !place || (place === 'onsite' ? record.arrangements.some(value => value === 'onsite' || value === 'hybrid') : place === 'varies' ? !record.arrangements.some(value => ['remote', 'onsite', 'hybrid'].includes(value)) : record.arrangements.includes(place));
      const visible = (!kind.value || record.group.dataset.workGroup === kind.value) && fitsPlace && words.every(word => record.text.includes(word));
      record.card.hidden = !visible;
      if (visible) { matches++; shownGroups.add(record.group); }
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
    count.textContent = active ? `${matches} matching ${matches === 1 ? 'record' : 'records'}` : `${records.length} records. Career pages and past records are grouped below.`;
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
})();
