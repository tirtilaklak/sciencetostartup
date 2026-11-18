const {test,expect}=require('@playwright/test');

test('static header points to lightweight search and native directory matches contributor brands',async({page})=>{
  await page.goto('/companies/');
  await expect(page.locator('.site-search-open')).toHaveAttribute('href','https://sciencetostartup.com/?search');
  for(const [query,id] of [['Outlier','scale_ai'],['Remotasks','scale_ai'],['Alignerr','labelbox'],['DataAnnotation','surge_ai'],['Mindrift','toloka']]){
    await page.goto('/companies/?reader=keep&q='+encodeURIComponent(query)+'#main');
    await expect(page.locator('.directory-company:visible')).toHaveCount(1);
    await expect(page.locator('.directory-company[data-company="'+id+'"]')).toBeVisible();
    await page.getByRole('button',{name:'Clear',exact:true}).click();
    expect(new URL(page.url()).searchParams.get('reader')).toBe('keep');expect(new URL(page.url()).hash).toBe('#main');
  }
});

test('native work search uses company aliases and preserves listing buckets and literal queries',async({page})=>{
  await page.goto('/work/?reader=keep&q=DataAnnotation#main');
  const matches=page.locator('[data-work-route]:visible');expect(await matches.count()).toBeGreaterThan(0);
  for(const href of await matches.locator('.work-company').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href'))))expect(href).toContain('/company/surge_ai/');
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
