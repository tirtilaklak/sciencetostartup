({ proof, canonicalHost }) => {
  const main = document.querySelector('main, [role=main]');
  const header = document.querySelector('body > header, [role=banner]');
  const heading = main?.querySelector('h1');
  const width = document.documentElement.clientWidth;
  const height = window.innerHeight;
  const normalize = text => (text || '').replace(/\s+/g, ' ').trim();
  const visible = node => node?.getClientRects().length && getComputedStyle(node).visibility === 'visible';
  const shown = (node, query) => [...(node?.querySelectorAll(query) || [])].filter(visible);
  const rect = value => Object.fromEntries(['left', 'top', 'right', 'bottom', 'width', 'height']
    .map(key => [key, Math.round(value[key] * 10) / 10]));
  const box = node => visible(node) ? rect(node.getBoundingClientRect()) : null;
  const label = node => normalize(node?.getAttribute('aria-label') || node?.innerText);
  const host = name => name.toLowerCase().replace(/^www\./, '');
  const sameSite = url => [host(location.hostname), host(canonicalHost)].includes(host(url.hostname));
  const firstScreen = value => Boolean(value && value.left >= -1 && value.right <= width + 1 &&
    value.top >= -1 && value.bottom <= height + 1);
  const cleanText = node => normalize(node?.innerText);

  function link(node) {
    const value = box(node);
    return { label: label(node), href: node.href || null, box: value, onFirstScreen: firstScreen(value) };
  }

  function browseKind(anchor) {
    const url = new URL(anchor.href);
    if (sameSite(url) && /^\/companies\/?$/.test(url.pathname)) return 'company';
    if (sameSite(url) && /^\/work\/?$/.test(url.pathname)) return 'work';
    if (proof && url.pathname === location.pathname && /^#paid-work$/.test(url.hash)) return 'work';
    return null;
  }

  const hero = heading?.closest('section, header') || heading?.parentElement;
  const intro = heading?.parentElement;
  const actionAnchors = shown(hero, 'a[href]').filter(anchor =>
    anchor.closest('.hero-actions') || !anchor.closest('article, nav, footer'));
  const actions = Object.fromEntries(['company', 'work'].map(kind => {
    const node = actionAnchors.find(anchor => browseKind(anchor) === kind);
    return [kind, node ? link(node) : null];
  }));

  function sourceLink(anchor) {
    const url = new URL(anchor.href);
    return ['http:', 'https:'].includes(url.protocol) && !sameSite(url) && !url.username && !url.password;
  }

  function record(article) {
    const title = shown(article, 'h2, h3, h4, [role=heading]')[0];
    if (!title) return null;
    const markerNodes = shown(article, 'p, span').filter(node =>
      !node.closest('a') && (node.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING));
    const marker = normalize(`${article.getAttribute('aria-label') || ''} ${markerNodes.slice(0, 4).map(cleanText).join(' ')}`);
    const links = shown(article, 'a[href]');
    const work = /\b(paid.*work|expert (network|community)|(?:public|work) listing|network program|work record)\b/i;
    const company = /\b(company (profile|record)|example company)\b/i;
    const kind = work.test(`${marker} ${cleanText(title)}`) ? 'work' :
      company.test(marker) || links.some(anchor => sameSite(new URL(anchor.href)) && /^\/company\//.test(anchor.pathname)) ? 'company' : null;
    if (!kind) return null;
    const metricText = kind === 'company' ? /[$€£]\s?\d|revenue|funding|valuation|headcount/i :
      /[$€£]\s?\d|pay\b|paid per|rate\b|not stated|eligib|remote/i;
    const fields = shown(article, 'p, dl, ul, time, data').filter(node =>
      !node.closest('a') && (title.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING));
    return {
      kind, marker, headline: cleanText(title), box: box(article), headlineBox: box(title),
      evidence: fields.filter(node => metricText.test(cleanText(node)))
        .slice(0, 3).map(node => {
          const value = box(node);
          return { text: cleanText(node), box: value, onFirstScreen: firstScreen(value) };
        }),
      dates: shown(article, 'time').map(node => ({ label: cleanText(node), datetime: node.dateTime, box: box(node) })),
      sources: links.filter(sourceLink).map(link),
    };
  }

  const cards = shown(main, 'article, [role=article]').map(record).filter(Boolean)
    .sort((first, second) => first.box.top - second.box.top || first.box.left - second.box.left);

  function textRects(node) {
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    const boxes = [];
    let part;
    while ((part = walker.nextNode())) {
      const parent = part.parentElement;
      if (!normalize(part.textContent) || !visible(parent) || parent.closest('[aria-hidden=true], [hidden]')) continue;
      const style = getComputedStyle(parent);
      if ((style.clipPath !== 'none' || style.clip !== 'auto') && parent.clientWidth <= 1) continue;
      const range = document.createRange();
      range.selectNodeContents(part);
      boxes.push(...[...range.getClientRects()].filter(value => value.width > 0 && value.height > 0).map(rect));
    }
    return boxes;
  }

  function clipsText(node, textBox) {
    for (let parent = node; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (!['hidden', 'clip'].includes(style.overflowX)) continue;
      const bounds = parent.getBoundingClientRect();
      if (textBox.left < bounds.left - 1 || textBox.right > bounds.right + 1) return true;
    }
    return false;
  }

  const navNodes = shown(header, 'a[href], button, summary, [role=button]');
  const nav = navNodes.map(node => {
    const boxes = textRects(node);
    return {
      ...link(node), text: boxes,
      clippedText: boxes.filter(value => value.left < -1 || value.right > width + 1 || clipsText(node, value)),
    };
  });
  const overlap = [];
  for (const [index, item] of nav.entries()) {
    for (const next of nav.slice(index + 1)) {
      if (item.text.some(a => next.text.some(b => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
        Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1))) overlap.push([item.label, next.label]);
    }
  }

  const art = shown(main, 'figure').find(node => shown(node, 'img').length);
  return {
    viewport: { width, height },
    scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    heading: { text: cleanText(heading), box: box(heading) },
    hero: { intro: box(intro), section: box(hero), portrait: box(art), art: art?.querySelector('img').currentSrc?.slice(0, 240) },
    actions, cards, nav,
    search: nav.find(item => /^search\b/i.test(item.label)) || null,
    overlap,
  };
}
