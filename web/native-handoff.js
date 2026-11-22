/* Legacy history APIs do not report which entry the reader just left. */
(() => {
  if (window.navigation || window.top !== window) return;

  const key = 's2s.nativeHandoff';
  const firstKey = 'nativeHandoffFirst';
  let storage;
  try { storage = window.sessionStorage; } catch { return; }

  function takeWitness() {
    try {
      const value = storage.getItem(key);
      if (!value) return;
      storage.removeItem(key);
      return JSON.parse(value);
    } catch {}
  }

  let witness = takeWitness();
  addEventListener('pageshow', event => { if (event.persisted) witness = takeWitness(); });
  if (!NATIVE_HANDOFF_PARTICIPANT) return;

  const source = ['/companies/', '/work/', '/explore/'].includes(location.pathname);
  // An uninstrumented page can leave a witness behind after a skipped traversal.
  // Only the oldest entry cannot receive that witness on Forward. Mark it while
  // it is alone, since history.length can later include forward entries.
  if (source && history.length === 1) {
    try { history.replaceState({ ...history.state, [firstKey]: true }, ''); } catch {}
  }

  const entryKey = 'nativeHandoffArrival';
  // Match a pending arrival without putting the address or search text in storage.
  const fingerprint = (id, href) => {
    const value = id + href;
    let hash = 2166136261;
    for (let index = 0; index < value.length; index++) {
      hash = Math.imul(hash ^ value.charCodeAt(index), 16777619);
    }
    return hash >>> 0;
  };

  const type = performance.getEntriesByType('navigation')[0]?.type;
  if (type === 'navigate' && witness?.id && witness.target === fingerprint(witness.id, location.href)) {
    try { history.replaceState({ ...history.state, [entryKey]: witness.id }, ''); } catch {}
  }

  let pending;
  if (source || history.state?.[entryKey] || type === 'back_forward' || type === 'reload') {
    addEventListener('pagehide', () => {
      const outgoing = pending;
      pending = undefined;
      if (outgoing && !outgoing.event.defaultPrevented) {
        const { id, target } = outgoing;
        try { storage.setItem(key, JSON.stringify({ id, target })); } catch {}
        return;
      }
      // A fragment or duplicate address can expose a different history entry.
      const id = history.state?.[entryKey];
      if (!id) return;
      try { storage.setItem(key, JSON.stringify({ id })); } catch {}
    });
  }

  if (source) {
    window.S2SNativeHandoff = {
      begin(href, event) {
        if (!history.state?.[firstKey] || new URL(href).origin !== location.origin) return;
        try {
          const id = Array.from(crypto.getRandomValues(new Uint32Array(4)), part => part.toString(36)).join('-');
          pending = { id, target: fingerprint(id, href), event };
          return id;
        } catch {}
      },
      returnedFrom(id) {
        return Boolean(history.state?.[firstKey] && id && witness?.target === undefined && witness?.id === id);
      },
    };
  }
})();
