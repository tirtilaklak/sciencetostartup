"""History behavior in browsers without the Navigation API, using delivered modules."""
import unittest

from test_site_search import run_stub


class NavigationReliabilityTests(unittest.TestCase):
    def test_back_forward_restore_each_entry_and_keep_profile_position(self):
        result = run_stub(r'''
run('initialize()');
assert.equal(history.scrollRestoration,'manual','Routing owns scroll restoration in every browser');
assert.ok(windowCallbacks.popstate?.length,'History traversal is detected without the Navigation API');
const scrolls=[];window.scrollTo=options=>scrolls.push(options.top);
const traverse=(hash,scrollY)=>{
 location.hash=hash;history.state={scrollY};
 for(const callback of windowCallbacks.popstate)callback({type:'popstate',state:history.state});
 for(const callback of windowCallbacks.hashchange)callback({type:'hashchange'});
};
// Different entries in the same view retain different reading positions.
traverse('#companies/expert-data-evaluation',620);assert.equal(scrolls.at(-1),620);
traverse('#companies/ai-evaluation-safety',1450);assert.equal(scrolls.at(-1),1450);
traverse('#companies/expert-data-evaluation',620);assert.equal(scrolls.at(-1),620);
// A profile section's normal anchor scroll must not override the reader's saved position.
const section=node('history-profile-work');section.tagName='SECTION';section.scrollIntoView=()=>scrolls.push('section-anchor');
const baseQuery=document.querySelector;
document.querySelector=selector=>['[data-profile-pane="work"]','.profile-tabs'].includes(selector)?section:baseQuery(selector);
traverse('#company/mercor/work',880);assert.equal(scrolls.at(-1),880);
assert.ok(!scrolls.includes('section-anchor'),'Returning to a section restores where the reader left it');
// A genuinely new entry still lands on the requested profile section.
history.state=null;location.hash='#company/appen/work';
for(const callback of windowCallbacks.hashchange)callback({type:'hashchange'});
assert.equal(scrolls.at(-1),'section-anchor');
''')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
