/* Browse links and the menu are usable without this enhancement. */
(() => {
  'use strict';

  const shell = {"config":{"schemaVersion":"1.0.0","buildId":"bdefb23f130ac40a3e6b","editorialReleaseId":"2026-11-22.10","datasetVersion":"2.5.0","search":{"href":"/presentation/search.b1c31db814f581f5.json","sha256":"b1c31db814f581f5cb37ca8846ea3c3e20a2e664996efc8b1b53fa22ba6aa1ea","bytes":388089}},"dialog":"<dialog id=\"home-search\" class=\"site-search\" aria-labelledby=\"home-search-title\">\n<div class=\"site-search-panel\"><div class=\"site-search-bar\">\n<label id=\"home-search-title\" class=\"sr-only\" for=\"home-search-input\">Search the guide</label>\n<svg class=\"ui-icon\" xmlns=\"http://www.w3.org/2000/svg\" width=\"18\" height=\"18\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\"/><path d=\"m16 16 4 4\"/></svg>\n<input id=\"home-search-input\" class=\"site-search-input\" type=\"search\" role=\"combobox\" aria-autocomplete=\"list\" aria-expanded=\"false\" aria-controls=\"home-search-results\" aria-describedby=\"home-search-message\" autocomplete=\"off\" autocapitalize=\"off\" spellcheck=\"false\" enterkeyhint=\"go\" placeholder=\"Search\">\n<button type=\"button\" id=\"home-search-close\" class=\"site-search-close\" aria-label=\"Close search\"><svg class=\"ui-icon\" xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" aria-hidden=\"true\" focusable=\"false\"><path d=\"m6 6 12 12M18 6 6 18\"/></svg></button>\n</div><div class=\"site-search-content\" tabindex=\"-1\">\n<p id=\"home-search-message\" class=\"site-search-message\">Search research or companies and their products. Try a role or skill for paid work.</p>\n<div id=\"home-search-results\" class=\"site-search-results\" role=\"listbox\" aria-label=\"Search results\" tabindex=\"-1\" hidden></div>\n<p class=\"site-search-fallback\"><a href=\"/companies/\">Browse companies</a><a id=\"home-search-work-recovery\" href=\"/work/\">Browse paid work</a></p>\n<button id=\"home-search-more\" class=\"site-search-more\" type=\"button\" hidden>Show more</button>\n</div><p id=\"home-search-status\" class=\"sr-only\" role=\"status\"></p></div>\n</dialog>\n"};
  if (shell && typeof window.HTMLDialogElement?.prototype.showModal === 'function') {
    const configNode = document.createElement('script');
    configNode.id = 'home-config';
    configNode.type = 'application/json';
    configNode.textContent = JSON.stringify(shell.config);
    document.body.append(configNode);
    document.body.insertAdjacentHTML('beforeend', shell.dialog);
  }
  const configNode = document.getElementById('home-config');
  const config = configNode ? JSON.parse(configNode.textContent) : null;
  const slot = document.getElementById('home-work-example');
  const recorded = document.getElementById('home-work-recorded');

  function refreshPromotion() {
    const now = Date.now();
    const candidate = config.candidates.find(item => now >= Date.parse(item.reviewedAt) && now < Date.parse(item.expiresAt));
    const template = candidate && document.getElementById(candidate.templateId);
    const route = template ? candidate.routeId : '';
    if (route === (slot.dataset.routeId || '')) return;

    const hadFocus = slot.contains(document.activeElement) || recorded?.contains(document.activeElement);
    if (recorded) recorded.hidden = Boolean(template);
    if (template) {
      slot.replaceChildren(template.content.cloneNode(true));
      slot.hidden = false;
      slot.dataset.routeId = route;
      if (hadFocus) slot.querySelector('a[href]')?.focus();
    } else {
      slot.replaceChildren();
      slot.hidden = true;
      delete slot.dataset.routeId;
      if (hadFocus) {
        const work = document.querySelector('.hero-actions a[href="/work/"]');
        work?.focus({ preventScroll: true });
        work?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      }
    }
  }

  if (slot && config?.candidates?.length) {
    refreshPromotion();
    setInterval(refreshPromotion, 60_000);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshPromotion();
    });
  }

  const menu = document.querySelector('.home-menu, .site-menu');
  menu?.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !menu.open) return;
    event.preventDefault();
    menu.open = false;
    menu.querySelector('summary').focus();
  });
  menu && document.addEventListener('click', event => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
  });

  const opener = document.querySelector('.site-header .site-search-open');
  const dialog = document.getElementById('home-search');
  const input = document.getElementById('home-search-input');
  const message = document.getElementById('home-search-message');
  const results = document.getElementById('home-search-results');
  const recovery = document.getElementById('home-search-work-recovery') || dialog?.querySelector('.site-search-fallback a[href="/work/"]');
  if (!opener || typeof dialog?.showModal !== 'function' || !input || !message || !results || !recovery) return;
  opener.id = 'home-search-open';
  const historyField = 's2sHomeSearchReturn';
  const recoveryOpener = document.querySelector('[data-full-guide-search]');
  let attempt = null;
  let generation = 0;
  let retries = 0;
  let pendingSnapshot;
  let returnFocus;

  function syncWorkRecovery() {
    const query = input.value.slice(0, 256);
    const key = query.normalize('NFKD').replace(/\p{M}+/gu, '').toLowerCase().replace(/\s+/gu, ' ').trim();
    if (key === 'hourly' || key === 'hourly pay') {
      recovery.href = '/work/?pay=hourly';
      recovery.textContent = 'See roles with published hourly pay';
    } else if (!key || key === 'paid work') {
      recovery.href = '/work/';
      recovery.textContent = 'Browse paid work';
    } else {
      recovery.href = '/work/?' + new URLSearchParams({ q: query });
      recovery.textContent = 'Search paid work for this query';
    }
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

  function openSearch(snapshot, trigger = document.activeElement) {
    if (!dialog.open) {
      if (typeof snapshot?.directoryQuery === 'string' && recoveryOpener) trigger = recoveryOpener;
      returnFocus = trigger instanceof HTMLElement && trigger !== document.body && !dialog.contains(trigger)
        ? trigger : opener;
      if (returnFocus === recoveryOpener) {
        dialog.dataset.directoryQuery = document.getElementById('company-query')?.value || '';
      } else delete dialog.dataset.directoryQuery;
    }
    if (snapshot) {
      pendingSnapshot = snapshot;
      input.value = snapshot.query.slice(0, 256);
    }
    syncWorkRecovery();
    if (!dialog.open) dialog.showModal();
    opener.setAttribute('aria-expanded', 'true');
    input.focus();
    if (typeof window.openHomeSearch === 'function') {
      stop();
      openComponent();
      return;
    }
    if (attempt) return;

    const request = ++generation;
    const script = document.createElement('script');
    message.textContent = 'Loading search…';
    results.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    const more = document.getElementById('home-search-more');
    if (more) more.hidden = true;
    opener.setAttribute('aria-busy', 'true');

    const failure = () => {
      if (request !== generation || !attempt) return;
      stop();
      if (!dialog.open) return;
      retries++;
      message.innerHTML = 'Search could not load. <button type="button" data-home-component-retry>Try again</button>';
      document.getElementById('home-search-status').textContent = 'Search could not load. Retry or browse the guide.';
      const focused = document.activeElement;
      if (pendingSnapshot?.focus === 'fallback' && (focused === input || !dialog.contains(focused))) {
        const links = [...dialog.querySelectorAll('.site-search-fallback a[href]')];
        links.find(link => !link.hidden && link.getAttribute('href') === pendingSnapshot.resultHref)?.focus();
      }
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

  const ordinaryClick = event => !event.defaultPrevented && event.button === 0
    && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  opener.addEventListener('click', event => {
    if (!ordinaryClick(event)) return;
    event.preventDefault();
    openSearch(undefined, opener);
  });
  recoveryOpener?.addEventListener('click', event => {
    if (!ordinaryClick(event)) return;
    event.preventDefault();
    const query = new URL(recoveryOpener.href).searchParams.get('search') || '';
    openSearch({ query }, recoveryOpener);
  });
  input.addEventListener('input', event => {
    pendingSnapshot = undefined;
    if (!event.isComposing) syncWorkRecovery();
  });
  input.addEventListener('compositionend', syncWorkRecovery);
  input.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    dialog.close();
  });
  message.addEventListener('click', event => {
    if (event.target.closest('[data-home-component-retry]')) openSearch();
  });
  document.getElementById('home-search-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target === dialog) {
      dialog.close();
      return;
    }
    if (!ordinaryClick(event) || typeof window.openHomeSearch === 'function') return;
    const link = event.target.closest('.site-search-fallback a[href]');
    if (!link || link.origin !== location.origin) return;
    try {
      history.replaceState({ ...history.state, [historyField]: {
        query: input.value,
        resultHref: link.getAttribute('href'),
        focus: 'fallback',
        directoryQuery: dialog.dataset.directoryQuery
      } }, '');
    } catch {}
  });
  dialog.addEventListener('close', () => {
    stop();
    pendingSnapshot = undefined;
    if (history.state?.[historyField]) {
      const remaining = { ...history.state };
      delete remaining[historyField];
      try { history.replaceState(remaining, ''); } catch {}
    }
    opener.setAttribute('aria-expanded', 'false');
    const target = returnFocus;
    returnFocus = undefined;
    if (dialog.returnValue === 'search-result') {
      dialog.returnValue = '';
      return;
    }
    if (target?.isConnected) target.focus({ preventScroll: true });
    if (document.activeElement !== target) opener.focus({ preventScroll: true });
    const focused = document.activeElement;
    const bounds = focused.getBoundingClientRect();
    if (bounds.bottom <= 0 || bounds.top >= innerHeight || bounds.right <= 0 || bounds.left >= innerWidth) {
      focused.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
  });
  document.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229 || event.altKey || event.shiftKey) return;
    if (event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)
        && !event.target.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) {
      event.preventDefault();
      openSearch();
    }
  });

  const openerLabel = opener.querySelector('.site-search-label');
  if (openerLabel) openerLabel.textContent = 'Search';
  if (opener.dataset.guideBrowse !== undefined) opener.href = '/?search=#browse-guide';
  opener.querySelector('.ui-icon')?.removeAttribute('hidden');
  opener.querySelector('kbd')?.removeAttribute('hidden');
  opener.setAttribute('aria-label', 'Search the guide');
  opener.setAttribute('aria-haspopup', 'dialog');
  opener.setAttribute('aria-expanded', 'false');
  opener.setAttribute('aria-keyshortcuts', 'Control+K Meta+K');
  opener.dataset.searchReady = '';

  const url = new URL(location.href);
  if (!shell && url.searchParams.has('search')) {
    input.value = (url.searchParams.get('search') || '').slice(0, 256);
    url.searchParams.delete('search');
    if (url.hash === '#browse-guide') url.hash = '';
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    openSearch();
  } else if (performance.getEntriesByType('navigation')[0]?.type === 'back_forward') {
    const snapshot = history.state?.[historyField];
    if (typeof snapshot?.query === 'string') openSearch(snapshot);
  }
})();
