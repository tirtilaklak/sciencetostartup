const {test,expect}=require('@playwright/test');
const {routes}=require('../../data/work-routes.json');

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

test('a research-only company can be recovered from an empty native directory search',async({page})=>{
  await page.goto('/companies/?q=Humans+in+the+Loop');
  const recovery=page.getByRole('link',{name:'Search the full guide'});
  await expect(recovery).toBeVisible();
  await recovery.focus();
  await page.keyboard.press('Enter');
  const input=page.locator('#home-search-input');
  await expect(input).toHaveValue('Humans in the Loop');
  await expect(page.locator('#home-search-results [role=option]').first()).toHaveAttribute('href','/company/org.humans_in_the_loop/');
});

test('native work search uses company aliases and preserves listing buckets and literal queries',async({page})=>{
  await page.goto('/work/?reader=keep&q=DataAnnotation#main');
  const matches=page.locator('[data-work-route]:visible');expect(await matches.count()).toBeGreaterThan(0);
  for(const href of await matches.locator('.work-heading h3 a').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href'))))expect(href).toContain('/company/surge_ai/');
  const query=page.locator('[data-work-filters] input[name=q]');await query.fill('C++');
  await expect(query).toHaveValue('C++');expect(new URL(page.url()).searchParams.get('q')).toBe('C++');expect(new URL(page.url()).hash).toBe('#main');
  await page.locator('.work-page-filter-options').evaluate(node=>{node.open=true;});await page.getByRole('button',{name:'Clear',exact:true}).click();
  await expect(query).toHaveValue('');expect(new URL(page.url()).searchParams.get('reader')).toBe('keep');
  await expect(page.locator('[data-work-route]')).toHaveCount(135);
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
