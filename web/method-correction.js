(() => {
  if (location.hash !== '#corrections') return;

  const params = new URLSearchParams(location.search);
  const stableId = params.get('correction');
  const edition = params.get('edition');
  const record = params.get('record');
  const title = params.get('title') || '';
  const controlCharacters = /[\x00-\x1f\x7f]/;
  if (!stableId || !edition || !record || [stableId, edition, record, title].some(value => controlCharacters.test(value))) return;
  if (!/^\/(?:research|company)\//.test(record)) return;

  const localRecord = new URL(record, location.origin);
  if (localRecord.origin !== location.origin || record !== localRecord.pathname + localRecord.hash) return;

  const email = document.getElementById('correction-email');
  const recordNote = document.getElementById('correction-record');
  const recordLink = recordNote?.querySelector('a');
  const canonical = document.querySelector('link[rel="canonical"]');
  const recipient = email?.getAttribute('href')?.split('?')[0];
  if (!recipient?.startsWith('mailto:') || !recordLink || !canonical) return;

  const permalink = new URL(record, canonical.href).href;
  const subject = `ScienceToStartup correction · ${stableId}`;
  const lines = [`Edition: ${edition}`, `Stable record ID: ${stableId}`, `Record URL: ${permalink}`];
  if (title) lines.push(`Record: ${title}`);
  lines.push('What should change:', 'Supporting public evidence:', '');
  email.href = `${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join('\r\n'))}`;
  recordLink.href = record;
  recordLink.textContent = stableId;
  recordNote.hidden = false;
})();
