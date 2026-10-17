/* Shared decorative SVG icons. Give icon-only controls an accessible label. */
(() => {
  'use strict';
  const paths = {
    external: '<path d="M7 17 17 7M7 7h10v10"/>',
    right: '<path d="M4 12h16m-7-7 7 7-7 7"/>',
    left: '<path d="M20 12H4m7-7-7 7 7 7"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-right': '<path d="m9 6 6 6-6 6"/>',
    'chevron-left': '<path d="m15 6-6 6 6 6"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
    mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    link: '<path d="m10 13 4-4m-6 6-1.5 1.5a3.5 3.5 0 0 1-5-5L6 7a3.5 3.5 0 0 1 5 0m2 10a3.5 3.5 0 0 0 5 0l4.5-4.5a3.5 3.5 0 0 0-5-5L16 9"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
    filter: '<path d="M4 6h16M7 12h10m-7 6h4"/>'
  };
  const aliases = {'arrow-up-right':'external','arrow-right':'right','arrow-left':'left','x':'close','email':'mail'};
  window.iconHTML = function iconHTML(name) {
    const key = aliases[name] || name;
    if (!Object.hasOwn(paths, key)) return '';
    return `<svg class="ui-icon" data-icon="${key}" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[key]}</svg>`;
  };
})();
