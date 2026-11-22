/* Keep native document links useful when their destination is in a disclosure. */
(() => {
  function openDisclosures(target) {
    let detail = target.closest('details');
    let changed = false;
    while (detail) {
      if (!detail.open) { detail.open = true; changed = true; }
      detail = detail.parentElement?.closest('details');
    }
    return changed;
  }

  function reveal() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = id && document.getElementById(id);
    if (target && openDisclosures(target)) target.scrollIntoView({ block: 'start' });
  }
  addEventListener('hashchange', reveal);
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="#"]');
    if (link && link.hash === location.hash) reveal();
  });
  document.addEventListener('beforematch', event => openDisclosures(event.target));
  reveal();

  const navigation = window.navigation;
  if (navigation && document.querySelector('.r-bulk-shortcuts')) {
    const shortcutVisits = new Map();
    const passage = link => document.getElementById(link.hash.slice(1));
    const inView = bounds => bounds && bounds.bottom > 0 && bounds.top < innerHeight;
    let activatedShortcut;
    document.addEventListener('click', event => {
      activatedShortcut = event.isTrusted && !event.defaultPrevented && event.button === 0 &&
        !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey ?
        event.target.closest?.('.r-bulk-shortcuts a[href^="#"]') : null;
    });
    navigation.addEventListener('navigate', event => {
      const link = activatedShortcut;
      activatedShortcut = null;
      if (event.navigationType === 'traverse') {
        const visit = shortcutVisits.get(navigation.currentEntry.key);
        if (visit?.from === event.destination.key) {
          // Remember the passage position only while the reader is still there.
          const bounds = passage(visit.link)?.getBoundingClientRect();
          visit.passageTop = inView(bounds) ? bounds.top : null;
        }
      }
      if (!link || event.sourceElement !== link || event.navigationType !== 'push' || !event.hashChange) return;
      navigation.addEventListener('currententrychange', ({ from, navigationType }) => {
        if (navigationType !== 'push') return;
        const entry = navigation.currentEntry;
        const key = entry.key;
        shortcutVisits.set(key, { from: from.key, link });
        entry.addEventListener('dispose', () => shortcutVisits.delete(key), { once: true });
      }, { once: true, signal: event.signal });
    });
    navigation.addEventListener('currententrychange', ({ from, navigationType }) => {
      if (navigationType !== 'traverse') return;
      const key = navigation.currentEntry.key;
      const departure = shortcutVisits.get(from.key);
      const arrival = shortcutVisits.get(key);
      const goingBack = departure?.from === key;
      const target = goingBack ? departure.link : arrival?.from === from.key ? passage(arrival.link) : null;
      if (!target || (!goingBack && arrival.passageTop === null)) return;

      // The browser restores scroll after currententrychange.
      requestAnimationFrame(() => {
        if (navigation.currentEntry.key !== key) return;
        let bounds = target.getBoundingClientRect();
        // Some browsers can restore a different part of a long chapter on Forward.
        if (!inView(bounds) && !goingBack && Number.isFinite(arrival.passageTop)) {
          scrollBy({ top: bounds.top - arrival.passageTop, behavior: 'instant' });
          bounds = target.getBoundingClientRect();
        }
        if (inView(bounds)) target.focus({ preventScroll: true });
      });
    });
  }

  const company = location.pathname.match(/^\/company\/([a-z0-9_-]+)\/$/)?.[1];
  const dossier = document.querySelector('.company-dossier');
  if (company && dossier) {
    const canonical = new URL(document.querySelector('link[rel="canonical"]')?.href || location.href);
    const route = `#company/${company}`;
    const handoffs = [...dossier.querySelectorAll('details a[href*="/explore/#company/"]')].filter(link => {
      const url = new URL(link.href);
      return (url.origin === canonical.origin || url.origin === location.origin) &&
        url.pathname === '/explore/' && (url.hash === route || url.hash.startsWith(`${route}/`));
    });

    document.addEventListener('click', event => {
      const link = event.target.closest?.('a[href]');
      if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey ||
          event.metaKey || event.shiftKey || event.altKey || link.hasAttribute('download') ||
          (link.target && link.target !== '_self')) return;

      const { nativeCompanyReturn, ...state } = history.state || {};
      if (handoffs.includes(link)) {
        state.nativeCompanyReturn = { page: location.href, href: link.href, top: link.getBoundingClientRect().top };
      } else if (!nativeCompanyReturn || link.hash && link.href.split('#')[0] === location.href.split('#')[0]) {
        return;
      }
      // The originating entry can share its URL with other entries or tabs.
      try { history.replaceState(state, ''); } catch {}
    });

    addEventListener('pageshow', event => {
      const saved = history.state?.nativeCompanyReturn;
      if (event.persisted || saved?.page !== location.href ||
          performance.getEntriesByType('navigation')[0]?.type !== 'back_forward') return;
      const activation = navigation?.activation;
      if (activation?.from && activation.from.index <= activation.entry.index) return;
      const matches = handoffs.filter(link => link.href === saved.href);
      if (matches.length !== 1) return;
      const [link] = matches;
      // Wait for the browser's history scroll restoration before aligning the reopened link.
      requestAnimationFrame(() => {
        if (document.activeElement !== document.body) return;
        openDisclosures(link);
        link.focus({ preventScroll: true });
        const bounds = link.getBoundingClientRect();
        if (saved.top >= 0 && saved.top + bounds.height <= innerHeight) {
          scrollBy({ top: bounds.top - saved.top, behavior: 'instant' });
        } else {
          link.scrollIntoView({ block: 'center', behavior: 'instant' });
        }
      });
    });
  }

  const chapter = document.querySelector('.r-reader-chapter-content[aria-labelledby="technical-landscape"]');
  const footer = document.querySelector('.site-footer');
  if (!chapter || !footer) return;

  const editors = 'input,textarea,select,[contenteditable],[role="combobox"],[role="listbox"],[role="textbox"]';
  function hasTextCaret() {
    const selection = getSelection();
    return Boolean(selection?.rangeCount &&
      (!selection.isCollapsed || selection.anchorNode?.nodeType === Node.TEXT_NODE));
  }
  addEventListener('keydown', event => {
    if (event.key !== 'End' || event.defaultPrevented || event.isComposing ||
        event.metaKey || event.altKey || event.shiftKey ||
        !document.documentElement.hasAttribute('data-reader-enhanced')) return;
    const target = event.target;
    if (!(target instanceof Element) || target.isContentEditable || target.closest(editors)) return;

    if (event.ctrlKey) {
      // Native Ctrl+End needs the final document height before it scrolls.
      if (getSelection()?.isCollapsed !== false) document.documentElement.removeAttribute('data-reader-enhanced');
      return;
    }

    if (target.closest('button,summary') || hasTextCaret()) return;
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
