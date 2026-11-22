/* Browse links and the menu are usable without this enhancement. */
(() => {
  'use strict';

  const configNode = document.getElementById('home-config');
  if (!configNode) return;
  const config = JSON.parse(configNode.textContent);
  const slot = document.getElementById('home-work-example');
  const fallback = slot?.querySelector('article')?.cloneNode(true);

  function refreshPromotion() {
    const now = Date.now();
    const candidate = config.candidates.find(item => now >= Date.parse(item.reviewedAt) && now < Date.parse(item.expiresAt));
    const template = candidate && document.getElementById(candidate.templateId);
    const route = template ? candidate.routeId : '';
    if (route === (slot.dataset.routeId || '')) return;

    const hadFocus = slot.contains(document.activeElement);
    slot.replaceChildren(template ? template.content.cloneNode(true) : fallback.cloneNode(true));
    if (route) slot.dataset.routeId = route;
    else delete slot.dataset.routeId;
    if (hadFocus) slot.querySelector('a[href]')?.focus();
  }

  if (fallback && config.candidates?.length) {
    refreshPromotion();
    setInterval(refreshPromotion, 60_000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshPromotion();
    });
  }

  const menu = document.querySelector('.home-menu');
  menu?.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !menu.open) return;
    event.preventDefault();
    menu.open = false;
    menu.querySelector('summary').focus();
  });
  menu && document.addEventListener('click', event => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });

  const opener = document.getElementById('home-search-open');
  const dialog = document.getElementById('home-search');
  const input = document.getElementById('home-search-input');
  const message = document.getElementById('home-search-message');
  const results = document.getElementById('home-search-results');
  const recovery = document.getElementById('home-search-work-recovery') || dialog?.querySelector('.site-search-fallback a[href="/work/"]');
  if (!opener || !input || !message || !results || !recovery) return;
  let attempt = null;
  let generation = 0;
  let retries = 0;
  let pendingSnapshot;

  opener.setAttribute('aria-haspopup', 'dialog');
  opener.setAttribute('aria-expanded', 'false');
  opener.setAttribute('aria-keyshortcuts', 'Control+K Meta+K');

  function syncWorkRecovery() {
    const query = input.value.slice(0, 256);
    recovery.href = query.trim() ? '/work/?' + new URLSearchParams({ q: query }) : '/work/';
    recovery.textContent = query.trim() ? 'Search paid work for this query' : 'Browse paid work';
  }

  function stop() {
    generation++;
    if (attempt) {
      clearTimeout(attempt.deadline);
      attempt.script.onload = null;
      attempt.script.onerror = null;
      attempt.script.remove();
      attempt = null;
    }
    opener.removeAttribute('aria-busy');
  }

  function openComponent() {
    const snapshot = pendingSnapshot;
    pendingSnapshot = undefined;
    window.openHomeSearch(snapshot);
  }

  function openSearch(snapshot) {
    if (snapshot) {
      pendingSnapshot = snapshot;
      input.value = snapshot.query.slice(0, 256);
    }
    syncWorkRecovery();
    if (typeof window.openHomeSearch === 'function') {
      stop();
      openComponent();
      return;
    }
    if (!dialog.open) dialog.showModal();
    opener.setAttribute('aria-expanded', 'true');
    input.focus();
    if (attempt) return;

    const request = ++generation;
    const script = document.createElement('script');
    message.textContent = 'Loading search…';
    results.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    document.getElementById('home-search-more').hidden = true;
    opener.setAttribute('aria-busy', 'true');

    const failure = () => {
      if (request !== generation || !attempt) return;
      stop();
      if (!dialog.open) return;
      retries++;
      message.innerHTML = 'Search could not load. <button type="button" data-home-component-retry>Try again</button>';
      document.getElementById('home-search-status').textContent = 'Search could not load. Retry or browse the guide.';
    };

    attempt = { script, deadline: setTimeout(failure, 15_000) };
    script.src = retries ? '/home-search.js?retry=' + retries : '/home-search.js';
    script.onload = () => {
      if (request !== generation || !attempt) return;
      if (typeof window.openHomeSearch !== 'function') {
        failure();
        return;
      }
      clearTimeout(attempt.deadline);
      attempt = null;
      opener.removeAttribute('aria-busy');
      if (dialog.open) openComponent();
    };
    script.onerror = failure;
    document.head.append(script);
  }

  opener.addEventListener('click', event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0) return;
    event.preventDefault();
    openSearch();
  });
  input.addEventListener('input', event => {
    pendingSnapshot = undefined;
    if (!event.isComposing) syncWorkRecovery();
  });
  input.addEventListener('compositionend', syncWorkRecovery);
  message.addEventListener('click', event => {
    if (event.target.closest('[data-home-component-retry]')) openSearch();
  });
  document.getElementById('home-search-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    stop();
    pendingSnapshot = undefined;
    opener.setAttribute('aria-expanded', 'false');
    opener.focus();
  });
  document.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229 || event.altKey || event.shiftKey) return;
    if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)
        && !event.target.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) {
      event.preventDefault();
      openSearch();
    }
  });

  const url = new URL(location.href);
  if (url.searchParams.has('search')) {
    input.value = (url.searchParams.get('search') || '').slice(0, 256);
    url.searchParams.delete('search');
    if (url.hash === '#browse-guide') url.hash = '';
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    openSearch();
  } else if (performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
    const snapshot = history.state?.s2sHomeSearchReturn;
    if (typeof snapshot?.query === 'string') openSearch(snapshot);
  }
})();
