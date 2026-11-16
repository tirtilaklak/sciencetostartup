/* Keep native document links useful when their destination is in a disclosure. */
(() => {
  function reveal() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = id && document.getElementById(id);
    if (!target) return;
    let detail = target.closest('details');
    let changed = false;
    while (detail) {
      if (!detail.open) { detail.open = true; changed = true; }
      detail = detail.parentElement?.closest('details');
    }
    if (changed) target.scrollIntoView({ block: 'start' });
  }
  addEventListener('hashchange', reveal);
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="#"]');
    if (link && link.hash === location.hash) reveal();
  });
  document.addEventListener('beforematch', event => {
    let detail = event.target.closest('details');
    while (detail) { detail.open = true; detail = detail.parentElement?.closest('details'); }
  });
  reveal();
})();
