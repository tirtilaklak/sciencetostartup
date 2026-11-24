const {test,expect}=require('@playwright/test');
const {routes}=require('../../data/work-routes.json');

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });
  for (const path of ['/work/', '/research/', '/daily/']) {
    test(`the header on ${path} leads to Browse`, async ({ page }) => {
      await page.goto(path);
      const browse = page.locator('header').getByRole('link', { name: 'Browse the guide' });
      const label = browse.locator('.site-search-label');
      await expect(browse).toHaveAttribute('href', '/#browse-guide');
      await expect(browse).not.toHaveAttribute('aria-haspopup', 'dialog');
      await expect(label).toHaveText('Browse');
      expect((await label.boundingBox()).width).toBeGreaterThan(20);
      const size = await browse.boundingBox();
      expect(size.width).toBeGreaterThanOrEqual(44);
      expect(size.height).toBeGreaterThanOrEqual(44);
      await browse.press('Enter');
      await expect(page).toHaveURL('/#browse-guide');
      const links = page.getByRole('navigation', { name: 'Browse the guide' }).getByRole('link');
      await expect(links).toHaveCount(3);
      for (const [index, label] of ['Companies', 'Paid work', 'Research'].entries()) {
        await expect(links.nth(index)).toHaveAccessibleName(label);
      }
    });
  }
});

test('global search keeps the native reader page, filters and opener when dismissed', async ({ page }) => {
  const requests = [];
  page.on('request', request => requests.push(request.url()));
  for (const path of ['/work/?q=python#main', '/research/papers/', '/method/#about']) {
    await page.goto(path);
    const origin = page.url();
    const opener = page.getByRole('link', { name: 'Search the guide' });
    await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
    expect(requests.splice(0).some(url => /home-search\.js|\/presentation\/search\./.test(url))).toBe(false);
    await opener.click();
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const input = dialog.getByRole('combobox');
    await expect(input).toBeFocused();
    await input.fill('Paid work');
    await expect(dialog.getByRole('option').first()).toHaveAttribute('href', '/work/');
    await dialog.getByRole('button', { name: 'Close search' }).click();
    await expect(opener).toBeFocused();
    await expect(page).toHaveURL(origin);
    if (path.startsWith('/work/')) await expect(page.getByRole('searchbox', { name: 'Search listings' })).toHaveValue('python');
    requests.length = 0;
  }
});

test('global search shortcut restores the actual focused control and finds the published DOI', async ({ page }) => {
  for (const path of ['/', '/research/']) {
    await page.goto(path);
    const trigger = page.locator('main a[href="/companies/"], main a[href="/research/data/"]').first();
    await trigger.focus();
    await expect(trigger).toBeFocused();
    await page.keyboard.press('Control+k');
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const input = dialog.getByRole('combobox');
    await input.fill('10.5281/zenodo.24249277');
    await expect(dialog.getByRole('option').first()).toHaveAttribute('href', '/research/editions/2026-11-12/');
    await input.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  }
});

test('Explore guide search opens companies by a recorded alias or a spaced name', async ({ page, isMobile }) => {
  await page.goto('/explore/#market');
  const opener = page.locator('#site-search-open');
  await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
  await opener.click();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const first = dialog.getByRole('option').first();

  await input.fill('micro 1');
  await expect(first.locator('.site-search-name')).toHaveText('micro1');
  await input.fill('Data Force');
  await expect(first).toHaveAttribute('href', '/company/org.dataforce/');
  await input.fill('DataForce by TransPerfect');
  await expect(first).toHaveAttribute('href', '/company/org.dataforce/');
  await expect(first).toContainText('Also known as DataForce by TransPerfect');
  if (isMobile) await first.tap();
  else {
    await input.press('ArrowDown');
    await input.press('Enter');
  }
  await expect(page).toHaveURL('/company/org.dataforce/');
  await page.goBack();
  await expect(input).toHaveValue('DataForce by TransPerfect');
  await expect(first).toHaveAttribute('aria-selected', 'true');
});

test('native and Explore guide search open the Revenue & growth section for business health', async ({ page, isMobile }) => {
  for (const path of ['/research/', '/explore/#market']) {
    await page.goto(path);
    const opener = page.locator('header .site-search-open');
    await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
    await opener.click();
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const input = dialog.getByRole('combobox');
    const first = dialog.getByRole('option').first();
    if (path.startsWith('/explore/')) {
      await input.fill('market');
      await expect(first).toHaveAccessibleName(/^Market overview\b/);
    }
    await input.fill('business health');
    await expect(first).toHaveAccessibleName(/^Revenue & growth\b/);
    if (isMobile) await first.tap();
    else {
      await input.press('ArrowDown');
      await input.press('Enter');
    }
    await expect(page).toHaveURL('/explore/#business-health');
    await expect(dialog).toBeHidden();
    await expect(page.locator('#business-health-heading')).toBeInViewport();
  }
});

test('Explore guide search opens published hourly pay and restores the selected action on Back', async ({ page, isMobile }) => {
  await page.goto('/explore/#market');
  const opener = page.locator('#site-search-open');
  await expect(opener).toHaveAttribute('aria-haspopup', 'dialog');
  await opener.click();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const first = dialog.getByRole('option').first();
  for (const query of ['hourly', '  Hourly   Pay  ']) {
    await input.fill(query);
    await expect(first).toHaveAccessibleName(/^See roles with published hourly pay\b/);
    await expect(first).toHaveAttribute('href', '/work/?pay=hourly');
  }
  if (isMobile) await first.tap();
  else {
    await input.press('ArrowDown');
    await input.press('Enter');
  }
  await expect(page).toHaveURL('/work/?pay=hourly');
  await expect(page.locator('[data-work-filters] select[name=pay]')).toHaveValue('hourly');
  await page.goBack();
  await expect(input).toHaveValue('  Hourly   Pay  ');
  await expect(first).toHaveAttribute('aria-selected', 'true');
});

test('Back from an Explore Search product restores the query and selected result', async ({ page, isMobile }) => {
  const origin = '/explore/#market';
  const destination = '/explore/#company/mercor/products';
  const query = 'APEX-Agents';
  const opener = page.locator('#site-search-open');
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const result = dialog.getByRole('option', { name: 'APEX-Agents From Mercor', exact: true });
  const product = page.locator('[data-profile-product="APEX-Agents"]').getByRole('heading', { level: 3 });
  const choose = async () => {
    if (isMobile) await result.tap();
    else {
      await input.press('ArrowDown');
      await expect(result).toHaveAttribute('aria-selected', 'true');
      await input.press('Enter');
    }
  };

  await page.goto(origin);
  await opener.click();
  await input.fill(query);
  await expect(result).toBeVisible();
  await choose();
  await expect(page).toHaveURL(destination);
  await expect(dialog).toBeHidden();
  await expect(product).toBeFocused();

  await page.goBack();
  await expect(page).toHaveURL(origin);
  await expect(input).toBeFocused();
  await expect(input).toHaveValue(query);
  await expect(result).toHaveAttribute('aria-selected', 'true');
  await expect(input).toHaveAttribute('aria-activedescendant', await result.getAttribute('id'));

  await page.goForward();
  await expect(page).toHaveURL(destination);
  await expect(dialog).toBeHidden();
  await opener.click();
  await input.fill(query);
  await choose();
  await expect(product).toBeFocused();
  await page.goBack();
  await expect(page).toHaveURL(origin);
  await expect(input).toBeFocused();
  await expect(result).toHaveAttribute('aria-selected', 'true');
  await dialog.getByRole('button', { name: 'Close search' }).click();

  await page.goForward();
  await expect(page).toHaveURL(destination);
  await page.goBack();
  await expect(page).toHaveURL(origin);
  await expect(dialog).toBeHidden();
});

test('Explore Search native results keep their modified-click navigation', async ({ page, context, isMobile }) => {
  test.skip(isMobile, 'Uses a desktop modifier key.');
  const origin = '/explore/#market';
  const destination = '/research/benchmarks/benchmark.apex-agents/';
  await page.goto(origin);
  await page.locator('#site-search-open').click();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const result = dialog.locator(`a[role=option][href="${destination}"]`);
  await input.fill('APEX-Agents');
  const [tab] = await Promise.all([
    context.waitForEvent('page'),
    result.click({ modifiers: ['ControlOrMeta'] }),
  ]);
  await expect(tab).toHaveURL(destination);
  await expect(page).toHaveURL(origin);
  await expect(dialog).toBeVisible();
  await expect(input).toHaveValue('APEX-Agents');
  await tab.close();
});

test('a result on the current day closes Search and focuses its headline', async ({ page, isMobile }) => {
  const day = '/daily/2026-11-18/';
  const fragment = '#regularized-score-centering';
  const title = 'Regularized Score Centering';
  const opener = page.getByRole('link', { name: 'Search the guide' });
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const first = dialog.getByRole('option').first();
  const target = page.locator(fragment);
  const heading = target.getByRole('heading', { name: title, exact: true });
  await page.goto(day);
  await opener.click();
  await input.fill(title);
  await expect(first).toHaveAttribute('href', day + fragment);
  if (isMobile) await first.tap();
  else {
    await input.press('ArrowDown');
    await input.press('Enter');
  }
  await expect(page).toHaveURL(new RegExp(day + fragment + '$'));
  await expect(dialog).toBeHidden();
  await expect(heading).toBeFocused();
  await expect(heading).toBeInViewport();
  await expect(target.locator('details')).toHaveAttribute('open', '');
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(day + '$'));
});

test('a same-page hub result clears the fragment, closes Search and focuses the page title', async ({ page }) => {
  await page.goto('/work/#main');
  const opener = page.getByRole('link', { name: 'Search the guide' });
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  await opener.click();
  await dialog.getByRole('combobox').fill('Paid work');
  const first = dialog.getByRole('option').first();
  await expect(first).toHaveAttribute('href', '/work/');
  await first.click();
  await expect(page).toHaveURL(/\/work\/$/);
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('heading', { level: 1 })).toBeFocused();
  await page.goBack();
  await expect(page).toHaveURL(/\/work\/#main$/);
});

test('a failed Search component preserves the work shortcuts and can retry', async ({ page }) => {
  for (const path of ['/', '/method/']) {
    const component = '**/home-search.js';
    await page.route(component, route => route.abort());
    await page.goto(path);
    await page.getByRole('link', { name: 'Search the guide' }).click();
    const dialog = page.getByRole('dialog', { name: 'Search the guide' });
    const input = dialog.getByRole('combobox');
    const retry = dialog.getByRole('button', { name: 'Try again' });
    await expect(retry).toBeVisible();
    await input.fill('  Hourly   Pay  ');
    await expect(dialog.getByRole('link', { name: 'See roles with published hourly pay' })).toHaveAttribute('href', '/work/?pay=hourly');
    await input.fill('Paid work');
    await expect(dialog.getByRole('link', { name: 'Browse paid work' })).toHaveAttribute('href', '/work/');
    await input.fill('Sage');
    await expect(dialog.getByRole('link', { name: 'Search paid work for this query' })).toHaveAttribute('href', '/work/?q=Sage');
    await page.unroute(component);
    await retry.click();
    await expect(input).toHaveValue('Sage');
    await expect(dialog.getByRole('option').first()).toHaveAttribute('href', '/work/?q=Sage');
  }
});

test('mobile Safari keeps the restored Search opener in view after a cold Back', async ({ page, browserName, isMobile }) => {
  test.skip(browserName !== 'webkit' || !isMobile, 'Covers mobile Safari fragment scroll restoration');
  await page.goto('/companies/?q=Mercor#main');
  const opener = page.getByRole('link', { name: 'Search the guide' });
  await opener.tap();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  await input.fill('Mercor');
  const first = dialog.getByRole('option').first();
  await expect(first).toHaveAttribute('href', '/company/mercor/');
  await first.tap();
  await expect(page).toHaveURL(/\/company\/mercor\/$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/companies\/\?q=Mercor#main$/);
  await expect(input).toHaveValue('Mercor');
  await expect(first).toHaveAttribute('aria-selected', 'true');
  await expect(opener).not.toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
  await expect(opener).toBeInViewport();
  await expect(page.locator('#company-query')).toHaveValue('Mercor');
});

test('static header points to lightweight search and native directory matches contributor brands',async({page})=>{
  await page.goto('/companies/');
  await expect(page.locator('.site-search-open')).toHaveAttribute('href',/\/\?search=?#browse-guide$/);
  for(const [query,id] of [['Outlier','scale_ai'],['Remotasks','scale_ai'],['Alignerr','labelbox'],['DataAnnotation','surge_ai'],['Mindrift','toloka'],['DataForce by TransPerfect','org.dataforce']]){
    await page.goto('/companies/?reader=keep&q='+encodeURIComponent(query)+'#main');
    await expect(page.locator('.directory-company:visible')).toHaveCount(1);
    await expect(page.locator('.directory-company[data-company="'+id+'"]')).toBeVisible();
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    await expect(page.locator('#company-query')).toBeFocused();
    expect(new URL(page.url()).searchParams.get('reader')).toBe('keep');expect(new URL(page.url()).hash).toBe('#main');
  }
});

test('a research-only company can be recovered without leaving the directory', async ({ page, isMobile }) => {
  await page.goto('/companies/?group=expert-data-evaluation#main');
  const directorySearch = page.getByRole('searchbox', { name: 'Search companies' });
  const query = 'Humans in the Loop';
  const literal = '  ' + query + '  ';
  await directorySearch.fill(literal);
  const group = page.getByRole('combobox', { name: 'Business group' });
  const allGroups = page.getByRole('button', { name: 'Search all groups' });
  const recovery = page.getByRole('link', { name: 'Search the full guide' });
  await expect(recovery).toBeHidden();
  if (isMobile) await allGroups.tap();
  else await allGroups.press('Enter');
  await expect(group).toHaveValue('');
  await expect(directorySearch).toHaveValue(literal);
  await expect(directorySearch).toBeFocused();
  await expect(page).toHaveURL('/companies/?q=Humans+in+the+Loop#main');
  const origin = page.url();
  const fallbackHref = '/?search=++Humans+in+the+Loop++#browse-guide';
  await expect(recovery).toBeVisible();
  await expect(recovery).toHaveAttribute('href', fallbackHref);
  if (isMobile) await recovery.tap();
  else await recovery.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const result = dialog.getByRole('option').first();
  await expect(input).toHaveValue(literal);
  await expect(result).toHaveAttribute('href', '/company/org.humans_in_the_loop/');
  await expect(page).toHaveURL(origin);
  await input.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(recovery).toBeFocused();
  await expect(directorySearch).toHaveValue(literal);
  await expect(group).toHaveValue('');
  await expect(page).toHaveURL(origin);

  if (isMobile) await recovery.tap();
  else await recovery.press('Enter');
  await input.fill(query);
  await expect(result).toBeVisible();
  if (isMobile) await result.tap();
  else await input.press('Enter');
  await expect(page).toHaveURL('/company/org.humans_in_the_loop/');
  await page.goBack();
  await expect(page).toHaveURL(origin);
  await expect(input).toHaveValue(query);
  await expect(result).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('Escape');
  await expect(recovery).toBeFocused();
  await expect(recovery).toBeInViewport();
  await expect(directorySearch).toHaveValue(literal);
  await expect(recovery).toHaveAttribute('href', fallbackHref);
});

test('Back from the company directory restores a no-match Search and its fallback link', async ({ page, isMobile }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Search the guide' }).click();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const browse = dialog.getByRole('link', { name: 'Browse companies' });
  const query = 'zzqxv-no-matching-guide-record';
  await input.fill(query);
  await expect(dialog.locator('#home-search-message')).toContainText('No recorded guide matches');
  if (isMobile) await browse.tap();
  else await browse.press('Enter');
  await expect(page).toHaveURL('/companies/');
  await page.goBack();
  await expect(page).toHaveURL('/');
  await expect(input).toHaveValue(query);
  await expect(browse).toBeFocused();
  await expect(browse).toBeInViewport();
});

test('Search shell restores its fallback link on Back when the component is unavailable', async ({ page, isMobile }) => {
  await page.route('**/home-search.js', route => route.abort());
  await page.goto('/');
  await page.getByRole('link', { name: 'Search the guide' }).click();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  const browse = dialog.getByRole('link', { name: 'Browse companies' });
  const query = 'zzqxv-no-matching-guide-record';
  await expect(dialog.getByRole('button', { name: 'Try again' })).toBeVisible();
  await input.fill(query);
  if (isMobile) await browse.tap();
  else await browse.press('Enter');
  await expect(page).toHaveURL('/companies/');
  await page.goBack();
  await expect(dialog.getByRole('button', { name: 'Try again' })).toBeVisible();
  await expect(input).toHaveValue(query);
  await expect(browse).toBeFocused();
});

test('dismissing Search without the component clears the saved Back state', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Search the guide' }).click();
  const dialog = page.getByRole('dialog', { name: 'Search the guide' });
  const input = dialog.getByRole('combobox');
  await input.fill('Paid work');
  await expect(dialog.getByRole('option').first()).toHaveAttribute('href', '/work/');
  await input.press('Enter');
  await expect(page).toHaveURL('/work/');
  await page.route('**/home-search.js', route => route.abort());
  await page.goBack();
  await expect(input).toHaveValue('Paid work');
  await expect(dialog.getByRole('button', { name: 'Try again' })).toBeVisible();
  await input.press('Escape');
  await expect(dialog).toBeHidden();
  await page.locator('.hero-actions a[href="/companies/"]').click();
  await expect(page).toHaveURL('/companies/');
  await page.goBack();
  await expect(page).toHaveURL('/');
  await expect(page.getByRole('link', { name: 'Search the guide' })).toHaveAttribute('aria-expanded', 'false');
  await expect(dialog).toBeHidden();
});

test('native work search uses company aliases and preserves listing buckets and literal queries',async({page})=>{
  await page.goto('/work/?reader=keep&q=DataAnnotation#main');
  const matches=page.locator('[data-work-route]:visible');expect(await matches.count()).toBeGreaterThan(0);
  for(const href of await matches.locator('.work-heading h3 a').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href'))))expect(href).toContain('/company/surge_ai/');
  const query=page.locator('[data-work-filters] input[name=q]');await query.fill('C++');
  await expect(query).toHaveValue('C++');expect(new URL(page.url()).searchParams.get('q')).toBe('C++');expect(new URL(page.url()).hash).toBe('#main');
  await page.locator('.work-page-filter-options').evaluate(node=>{node.open=true;});await page.getByRole('button',{name:'Clear',exact:true}).click();
  await expect(query).toHaveValue('');expect(new URL(page.url()).searchParams.get('reader')).toBe('keep');
  await expect(page.locator('[data-work-route]')).toHaveCount(136);
  const groups=await page.locator('[data-work-group]').evaluateAll(nodes=>nodes.map(node=>node.dataset.workGroup));expect(groups.slice(0,2)).toEqual(['named','programs']);
});

test('homepage search transfers a real work query to the native source-backed list',async({page})=>{
  await page.goto('/?reader=keep&search=Sage#main');await expect(page.locator('#home-search-input')).toHaveValue('Sage');
  const action=page.locator('#home-search-results a').filter({hasText:'Find paid work matching'});await expect(action).toHaveAttribute('href','/work/?q=Sage');await action.click();
  const listing=page.locator('[data-work-route="appen.work.sage-media"]');await expect(listing).toBeVisible();
  for(const value of ['MacBook Pro','qualification','identity'])await expect(listing).toContainText(new RegExp(value,'i'));
  await expect(listing.locator('.work-reviewed')).toContainText(/Terms checked|Pay terms reviewed/);
  await expect(listing.locator('.work-listing-action a').first()).toHaveAttribute('href',/^https:\/\//);
});

test('bare hourly searches lead to published hourly rates by keyboard or touch',async({page,isMobile})=>{
  const expected=routes.filter(route=>route.pay_terms?.hourly_comparable).map(route=>route.id).sort();
  const input=page.getByRole('combobox',{name:'Search the guide'});
  const options=page.locator('#home-search-results').getByRole('option');
  const status=page.locator('#home-search-status');
  const first=options.first();
  await page.goto('/');
  if(isMobile) await page.getByRole('link',{name:'Search the guide'}).tap();
  else await page.keyboard.press('Control+k');
  await expect(input).toBeFocused();
  for(const [query,href] of [
    ['A.Team','/company/a-team/'],
    ['revenue','/explore/#business-health'],
    ['annualized pace','/explore/#business-health'],
    ['remote hourly jobs','/work/?q=remote+hourly+jobs'],
  ]){
    await input.fill(query);
    await expect(first).toHaveAttribute('href',href);
    await expect(options.filter({hasText:'See roles with published hourly pay'})).toHaveCount(0);
  }
  await input.fill('zzqxv-no-matching-guide-record');
  await expect(status).toHaveText('No recorded guide matches. You can search paid work or browse all companies.');

  for(const query of ['hourly','  Hourly   Pay  ']){
    await input.fill(query);
    await expect(first.locator('strong')).toHaveText('See roles with published hourly pay');
    await expect(first).toHaveAttribute('href','/work/?pay=hourly');
    await expect(status).toHaveText('The first result opens Work with the Hourly filter selected.');
    if(isMobile) await first.tap();
    else {
      await input.press('ArrowDown');
      await expect(first).toHaveAttribute('aria-selected','true');
      await input.press('Enter');
    }
    await expect(page).toHaveURL(/\/work\/\?pay=hourly$/);
    await expect(page.locator('[data-work-filters] input[name=q]')).toHaveValue('');
    await expect(page.locator('[data-work-filters] select[name=pay]')).toHaveValue('hourly');
    await expect(page.locator('[data-work-count]')).toHaveText(`${expected.length} records with published hourly pay`);
    await expect.poll(()=>page.locator('[data-work-route]:visible').evaluateAll(cards=>cards.map(card=>card.dataset.workRoute).sort())).toEqual(expected);
    await page.goBack();
    await expect(input).toHaveValue(query);
    await expect(first).toHaveAttribute('aria-selected','true');
    if(!isMobile) await expect(input).toBeFocused();
  }
});

test('the hourly shortcut remains available when the search index cannot load',async({page})=>{
  await page.route('**/presentation/search.*.json',route=>route.abort());
  await page.goto('/');
  await page.getByRole('link',{name:'Search the guide'}).click();
  await expect(page.getByRole('button',{name:'Try again'})).toBeVisible();
  await page.getByRole('combobox',{name:'Search the guide'}).fill('hourly pay');
  await expect(page.getByRole('link',{name:'See roles with published hourly pay'})).toHaveAttribute('href','/work/?pay=hourly');
});

test('global search finds the Daily hub and displayed Greek paper titles',async({page})=>{
  await page.goto('/?search');const input=page.locator('#home-search-input');
  for(const [query,href,title] of [['Daily scan','/daily/','Daily scan'],['τ-Knowledge','/research/papers/paper.arxiv.2603.04370/','τ-Knowledge'],[String.raw`\tau-Knowledge`,'/research/papers/paper.arxiv.2603.04370/','τ-Knowledge']]){
    await input.fill(query);const first=page.locator('#home-search-results [role=option]').first();
    await expect(first).toHaveAttribute('href',href);await expect(first).toContainText(title);
  }
});

test('Home routes exact versions, rejects unknown versions and restores keyboard selection on Back',async({page})=>{
  await page.goto('/');
  await page.keyboard.press('Control+k');
  const input=page.getByRole('combobox',{name:'Search the guide'});
  const results=page.locator('#home-search-results [role=option]');
  await expect(input).toBeFocused();
  await input.fill('arXiv:2203.02155v999');
  await expect(page.locator('#home-search-message')).toContainText('No matching research record');
  await expect(results).toHaveCount(0);
  const query='https://arxiv.org/pdf/2203.02155v1.pdf';
  const target='/research/papers/paper.arxiv.2203.02155v1/';
  await input.fill(query);
  await expect(results.first()).toHaveAttribute('href',target);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button',{name:'Close search'})).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(input).toBeFocused();
  await input.press('ArrowDown');
  await expect(input).toHaveAttribute('aria-activedescendant',await results.first().getAttribute('id'));
  await input.press('Enter');
  await expect(page).toHaveURL(new RegExp(target+'$'));
  await page.goBack();
  await expect(input).toBeFocused();
  await expect(input).toHaveValue(query);
  await expect(results.first()).toHaveAttribute('aria-selected','true');
});

test('employment intent leads to native paid work, preserving spaces in the query',async({page})=>{
  const query='RLHF  jobs';
  await page.goto('/?'+new URLSearchParams({search:query}));
  const result=page.locator('#home-search-results [role=option]').first();
  await expect(result).toContainText('Work search');
  await expect(result).toHaveAttribute('href','/work/?q=RLHF++jobs');
  await page.locator('#home-search-input').press('Enter');
  await expect(page).toHaveURL(/\/work\/\?q=RLHF\+\+jobs$/);
  await expect(page.locator('[data-work-filters] input[name=q]')).toHaveValue(query);
  await expect(page.locator('[data-work-route="afterquery.work.software-engineer-rl-environments"]')).toBeVisible();
});
