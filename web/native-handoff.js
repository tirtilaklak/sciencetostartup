/* Legacy history APIs do not report which entry the reader just left. */
(() => {
  if (window.navigation || window.top !== window) return;

  const key = 's2s.nativeHandoff';
  let storage;
  try { storage = window.sessionStorage; } catch { return; }

  function takeWitness() {
    try {
      const value = storage.getItem(key);
      if (!value) return;
      storage.removeItem(key);
      return value;
    } catch {}
  }

  const previous = takeWitness();
  // A warm document also consumes the witness when a traversal lands there.
  addEventListener('pageshow', event => { if (event.persisted) takeWitness(); });
  if (!NATIVE_HANDOFF_PARTICIPANT) return;

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

  let witness;
  if (previous) try { witness = JSON.parse(previous); } catch {}
  const type = performance.getEntriesByType('navigation')[0]?.type;
  if (type === 'navigate' && witness?.id && witness.target === fingerprint(witness.id, location.href)) {
    try { history.replaceState({ ...history.state, [entryKey]: witness.id }, ''); } catch {}
  }

  const nativeSource = location.pathname === '/companies/' || location.pathname === '/work/';
  let pending;
  if (nativeSource || history.state?.[entryKey] || type === 'back_forward' || type === 'reload') {
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

  if (nativeSource) {
    window.S2SNativeHandoff = {
      begin(href, event) {
        if (new URL(href).origin !== location.origin) return;
        try {
          const id = Array.from(crypto.getRandomValues(new Uint32Array(4)), part => part.toString(36)).join('-');
          pending = { id, target: fingerprint(id, href), event };
          return id;
        } catch {}
      },
      returnedFrom(id) { return Boolean(id && witness?.target === undefined && witness?.id === id); },
    };
  }
})();
