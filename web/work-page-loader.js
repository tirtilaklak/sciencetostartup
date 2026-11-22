/* Start the one native enhancer request while the document is still parsing. */
(() => {
  const root = document.documentElement;
  const params = new URLSearchParams(location.search);
  const valid = (key, values) => values.includes(params.get(key));
  const hasOptions = valid('kind', ['named', 'programs', 'boards', 'outside', 'closed'])
    || valid('arrangement', ['remote', 'onsite', 'varies'])
    || valid('type', ['contract', 'employment', 'fellowship', 'bounty', 'study', 'varies', 'unknown'])
    || valid('pay', ['hourly', 'task', 'yearly', 'monthly', 'numeric', 'undisclosed'])
    || valid('sort', ['hourly', 'checked']);
  const filtered = Boolean(params.get('q')?.slice(0, 256).trim() || hasOptions || params.get('view') === 'compare');
  const initialHash = location.hash;
  let current, attempts = 0, deadline, interacted = false;

  for (const type of ['wheel', 'keydown', 'touchstart', 'pointerdown']) {
    addEventListener(type, event => { if (event.isTrusted) interacted = true; }, { capture: true, passive: true, once: true });
  }

  function visitStatus(state) {
    const status = document.querySelector('[data-work-load-status]');
    if (!status) return;
    const message = status.querySelector('[data-work-load-message]');
    const retry = status.querySelector('[data-work-retry]');
    const normalPosition = document.querySelector('[data-work-filter-slot]');
    let target;
    try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { /* Malformed bookmark. */ }
    const group = target?.closest('[data-work-group]');
    if ((state === 'pending' || state === 'failed') && group) {
      if (group.tagName === 'DETAILS') group.open = true;
      if (target.matches('[data-work-route]')) target.prepend(status);
      else target.after(status);
    } else if (normalPosition && !normalPosition.contains(status)) {
      normalPosition.append(status);
    }

    status.hidden = state !== 'pending' && state !== 'failed';
    message.textContent = state === 'pending' ? 'Applying your filters…'
      : state === 'failed' ? 'Filters did not load. Showing the full directory.' : '';
    retry.hidden = state !== 'failed';
    if (!status.hidden && target && !interacted && initialHash === location.hash) {
      requestAnimationFrame(() => target.scrollIntoView({ block: 'start', behavior: 'instant' }));
    }
    retry.onclick = start;
  }

  function setState(state) {
    if (state) root.dataset.workLoad = state;
    else delete root.dataset.workLoad;
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        if ((root.dataset.workLoad || '') === state) visitStatus(state);
      }, { once: true });
    } else visitStatus(state);
  }

  function fail(script) {
    if (current !== script) return;
    clearTimeout(deadline);
    current = null;
    script.remove();
    setState('failed');
  }

  function start() {
    setState(filtered ? 'pending' : 'loading');
    const script = document.createElement('script');
    script.src = '/work-page.js' + (attempts ? '?s2s_retry=' + attempts + '-' + Date.now() : '');
    attempts++;
    current = script;
    script.onerror = () => fail(script);
    script.onload = () => {
      if (document.readyState !== 'loading') fail(script);
      else document.addEventListener('DOMContentLoaded', () => fail(script), { once: true });
    };
    deadline = setTimeout(() => fail(script), 2800);
    document.head.append(script);
  }

  if (hasOptions) {
    const discoverOptions = new MutationObserver(() => {
      const options = document.querySelector('.work-page-filter-options');
      if (!options) return;
      options.open = true;
      discoverOptions.disconnect();
    });
    discoverOptions.observe(root, { childList: true, subtree: true });
    addEventListener('DOMContentLoaded', () => discoverOptions.disconnect(), { once: true });
  }
  window.WorkPageResource = {
    get interacted() { return interacted; },
    get retried() { return attempts > 1; },
    accepts: script => current === script,
    complete(script) {
      if (current !== script) return;
      clearTimeout(deadline);
      current = null;
      setState('');
    }
  };
  start();
})();
