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

  const chapter = document.querySelector('.r-reader-chapter-content[aria-labelledby="technical-landscape"]');
  const footer = document.querySelector('.site-footer');
  if (!chapter || !footer) return;

  const controls = 'input,textarea,select,button,summary,[contenteditable],[role="combobox"],[role="listbox"],[role="textbox"]';
  function hasTextCaret() {
    const selection = getSelection();
    return Boolean(selection?.rangeCount &&
      (!selection.isCollapsed || selection.anchorNode?.nodeType === Node.TEXT_NODE));
  }
  addEventListener('keydown', event => {
    if (event.key !== 'End' || event.defaultPrevented || event.isComposing ||
        event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
        !document.documentElement.hasAttribute('data-reader-enhanced')) return;
    const target = event.target;
    if (!(target instanceof Element) || target.isContentEditable || target.closest(controls) || hasTextCaret()) return;

    // Native End runs first and can create a caret in Firefox caret browsing.
    requestAnimationFrame(() => {
      if (event.defaultPrevented || hasTextCaret()) return;
      footer.scrollIntoView({ block: 'end', behavior: 'instant' });
      requestAnimationFrame(() => {
        if (!hasTextCaret() && footer.getBoundingClientRect().bottom > innerHeight + 1) {
          footer.scrollIntoView({ block: 'end', behavior: 'instant' });
        }
      });
    });
  });
  document.documentElement.setAttribute('data-reader-end-ready', '');
})();
