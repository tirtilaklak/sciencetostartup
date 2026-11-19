/* Evergreen links remain usable if this optional enhancement cannot load. */
(() => {
  'use strict';
  const node = document.getElementById('home-config'); if (!node) return;
  const config = JSON.parse(node.textContent), slot = document.getElementById('home-work-example'), evergreen = slot?.innerHTML;
  const refresh = () => {
    if (!slot) return;
    const now = Date.now(), candidate = (config.candidates || []).find(item => now >= Date.parse(item.reviewedAt) && now < Date.parse(item.expiresAt));
    const template = candidate && document.getElementById(candidate.templateId);
    if (template) { if (slot.dataset.routeId !== candidate.routeId) { slot.replaceChildren(template.content.cloneNode(true)); slot.dataset.routeId = candidate.routeId; } }
    else if (slot.dataset.routeId) { slot.innerHTML = evergreen; delete slot.dataset.routeId; }
  };
  if (slot && config.candidates?.length) {
    refresh(); setInterval(refresh, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  }
  const opener = document.getElementById('home-search-open'), dialog = document.getElementById('home-search'), input = document.getElementById('home-search-input'), message = document.getElementById('home-search-message'), results = document.getElementById('home-search-results');
  if (!opener || !dialog || !input || !message || !results) return;
  let attempt = null, generation = 0;
  const stop = () => {
    generation++;
    if (attempt) { clearTimeout(attempt.deadline); attempt.script.onload = attempt.script.onerror = null; attempt.script.remove(); attempt = null; }
    opener.removeAttribute('aria-busy');
  };
  function open() {
    if (typeof window.openHomeSearch === 'function') { stop(); window.openHomeSearch(); return; }
    if (!dialog.open) dialog.showModal();
    opener.setAttribute('aria-expanded', 'true'); input.focus();
    if (attempt) return;
    const request = ++generation, script = document.createElement('script');
    message.textContent = 'Loading search…'; results.hidden = true; input.setAttribute('aria-expanded', 'false');
    document.getElementById('home-search-more')?.setAttribute('hidden', '');
    opener.setAttribute('aria-busy', 'true');
    const failure = () => {
      if (request !== generation || !attempt) return;
      stop();
      if (!dialog.open) return;
      message.innerHTML = 'Search could not load. <button type="button" data-home-component-retry>Try again</button> <a href="/companies/">Browse companies</a> or <a href="/work/">browse paid work</a>.';
      const status = document.getElementById('home-search-status'); if (status) status.textContent = 'Search could not load. Retry or browse the native pages.';
    };
    attempt = { script, deadline: setTimeout(failure, 15000) };
    script.src = '/home-search.js';
    script.onload = () => {
      if (request !== generation || !attempt) return;
      if (typeof window.openHomeSearch !== 'function') { failure(); return; }
      clearTimeout(attempt.deadline); attempt = null; opener.removeAttribute('aria-busy');
      if (dialog.open) window.openHomeSearch();
    };
    script.onerror = failure; document.head.append(script);
  }
  opener.addEventListener('click', event => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button > 0) return;
    event.preventDefault(); open();
  });
  message.addEventListener('click', event => { if (event.target.closest('[data-home-component-retry]')) open(); });
  // These handlers also work before the component installs. Repeated close() is harmless.
  document.getElementById('home-search-close')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { stop(); opener.setAttribute('aria-expanded', 'false'); opener.focus(); });
  document.addEventListener('keydown', event => {
    if (event.isComposing || event.keyCode === 229) return;
    if ((event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey || event.key.toLowerCase() === 'k' && (event.metaKey || event.ctrlKey)) && !event.target.closest?.('input,textarea,select,[contenteditable=true]')) { event.preventDefault(); open(); }
  });
  const url = new URL(location.href);
  if (url.searchParams.has('search')) {
    input.value = (url.searchParams.get('search') || '').slice(0, 256);
    url.searchParams.delete('search'); history.replaceState(history.state, '', url.pathname + url.search + url.hash); open();
  }
})();
