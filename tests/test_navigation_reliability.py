"""History behavior in browsers without the Navigation API, using delivered modules."""
import unittest

from test_site_search import run_stub


class NavigationReliabilityTests(unittest.TestCase):
    def test_explore_search_routes_papers_and_employment_without_stealing_editing_keys(self):
        result = run_stub(r'''
Object.defineProperty(location,'href',{get:()=>`https://example.test/explore/${location.hash}`});
Object.assign(context,{scrollX:0,scrollY:window.scrollY});
run('initialize()');
run(`window.SEARCH_INDEX={workTitles:['Research Fellow'],researchSearchEntries:[
 {title:'InstructGPT',summary:'Approved',url:'/research/papers/paper.arxiv.2203.02155/',kind:'paper',recordKind:'paper',identifiers:['2203.02155','10.48550/arXiv.2203.02155']},
 {title:'InstructGPT v1',summary:'Approved',url:'/research/papers/paper.arxiv.2203.02155v1/',kind:'paper',recordKind:'paper_version',identifiers:['2203.02155v1']}
]};siteSearchEntries=null`);
const view=query=>plain(run(`siteSearchView(${JSON.stringify(query)})`)).flatMap(group=>group.items);
assert.equal(view('arXiv:2203.02155')[0].href,'/research/papers/paper.arxiv.2203.02155/');
assert.equal(view('https://arxiv.org/pdf/2203.02155v1.pdf')[0].href,'/research/papers/paper.arxiv.2203.02155v1/');
assert.deepEqual(view('arXiv:2203.02155v999'),[]);
assert.equal(view('RLHF  jobs')[0].href,'/work/?q=RLHF++jobs');
assert.equal(view('Research Fellow')[0].href,'/work/?q=Research+Fellow');

const press=(event,editing=false)=>{
 context.shortcutEvent={...event,target:{isContentEditable:editing},preventDefault(){this.defaultPrevented=true;}};
 run('siteSearchShortcut(shortcutEvent)');
 return Boolean(context.shortcutEvent.defaultPrevented);
};
node('site-search-input').select=()=>{};
assert.equal(press({key:'/'}),false);
assert.equal(press({key:'End'},true),false);
assert.equal(press({key:'k',ctrlKey:true},true),false);
assert.equal(press({key:'k',ctrlKey:true}),true);
assert.ok(node('site-search').open);
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_back_forward_restore_each_entry_and_keep_profile_position(self):
        result = run_stub(r'''
run('initialize()');
assert.equal(history.scrollRestoration,'manual','Routing owns scroll restoration in every browser');
assert.ok(windowCallbacks.popstate?.length,'History traversal is detected without the Navigation API');
const scrolls=[];window.scrollTo=options=>scrolls.push(options.top);
const traverse=(hash,scrollY,entryKey)=>{
 location.hash=hash;history.state={scrollY,stsEntryKey:entryKey};
 for(const callback of windowCallbacks.popstate)callback({type:'popstate',state:history.state});
 for(const callback of windowCallbacks.hashchange)callback({type:'hashchange'});
};
// Different entries in the same view retain different reading positions.
traverse('#companies/expert-data-evaluation',620,'entry-1');assert.equal(scrolls.at(-1),620);
traverse('#companies/ai-evaluation-safety',1450,'entry-2');assert.equal(scrolls.at(-1),1450);
traverse('#companies/expert-data-evaluation',620,'entry-1');assert.equal(scrolls.at(-1),620);
// A profile section's normal anchor scroll must not override the reader's saved position.
const section=node('history-profile-work');section.tagName='SECTION';section.scrollIntoView=()=>scrolls.push('section-anchor');
const baseQuery=document.querySelector;
document.querySelector=selector=>['[data-profile-pane="work"]','.profile-tabs'].includes(selector)?section:baseQuery(selector);
traverse('#company/mercor/work',880,'entry-3');assert.equal(scrolls.at(-1),880);
assert.ok(!scrolls.includes('section-anchor'),'Returning to a section restores where the reader left it');
// A genuinely new entry still lands on the requested profile section.
history.state=null;location.hash='#company/appen/work';
for(const callback of windowCallbacks.popstate)callback({type:'popstate',state:null});
for(const callback of windowCallbacks.hashchange)callback({type:'hashchange'});
assert.equal(scrolls.at(-1),'section-anchor');
''')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
