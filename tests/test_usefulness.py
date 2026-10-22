import json
from monday.models import Action
from monday.research import rank_candidates,best_excerpt
from monday.gpu import GPUInspector


def test_reported_bare_typo_query(agent):
    c=agent.engine.interpreter.understand('python offical documentation')
    assert c['kind']=='research' and c['query']=='python official documentation'

def test_reported_storage_usage(agent):
    state=agent.run('system storage usage')
    assert state.status=='SUCCESS' and state.observations[0].tool=='system.disk'

def test_reported_gpu_usage(agent):
    agent.gateway.registry.get('system.gpu').execute=lambda:{'devices':[{'vendor':'Intel','driver':'i915','busy_percent':3.2,'engines_percent':{'render':3.2}}]}
    state=agent.run('system gpu usage')
    assert state.status=='SUCCESS' and '3.2% busy' in state.response

def test_gpu_without_supported_utilization_is_honest(agent):
    agent.gateway.registry.get('system.gpu').execute=lambda:{'devices':[{'vendor':'Intel','driver':'i915'}]}
    assert 'utilization is unavailable' in agent.run('gpu usage').response

def test_structured_strings_and_paths_are_not_spell_corrected(agent,cfg):
    p=str(cfg.roots[0]/'offical')
    c=agent.engine.interpreter.understand('tool fs.create '+json.dumps({'path':p,'content':'offical documentation'}))
    assert c['action'].arguments=={'path':p,'content':'offical documentation'}

def test_action_verbs_never_rewritten(agent):
    c=agent.engine.interpreter.understand('install firefox')
    assert c['kind']=='package' and c['operation']=='install'

def test_documentation_source_ranking():
    candidates=[{'title':'Our Documentation | Python.org','url':'https://www.python.org/doc/'},{'title':'Python Documentation','url':'https://docs.python.org/3/'}]
    assert rank_candidates('python official documentation',candidates)[0]['url']=='https://docs.python.org/3/'

def test_doc_objective_reads_page_before_success(agent):
    agent.gateway.registry.get('web.search').execute=lambda query:{'candidates':[{'title':'Python docs','url':'https://docs.python.org/3/'}]}
    agent.gateway.registry.get('web.read').execute=lambda url:{'id':'E1','title':'Python documentation','url':url,'text':'Welcome to the official documentation for Python with all standard library reference pages.'}
    s=agent.run('python offical documentation')
    assert s.status=='SUCCESS' and s.response=='Python documentation — https://docs.python.org/3/'
    assert [o.tool for o in s.observations]==['web.search','web.read']

def test_web_failure_tries_next_relevant_page(agent):
    agent.gateway.registry.get('web.search').execute=lambda query:{'candidates':[{'title':'Unix','url':'https://example.com/blocked'},{'title':'Unix','url':'https://example.com/good'}]}
    def read(url):
        if url.endswith('blocked'): raise RuntimeError('blocked')
        return {'id':'E1','title':'Unix','url':url,'text':'Unix is an operating system originally developed with well documented interfaces and tools.'}
    agent.gateway.registry.get('web.read').execute=read
    s=agent.run('tell me about Unix')
    assert s.status=='PARTIAL' and 'Unix is an operating system' in s.response
    assert [o.ok for o in s.observations]==[True,False,True]

def test_web_retries_are_bounded(agent):
    agent.gateway.registry.get('web.search').execute=lambda query:{'candidates':[{'title':'Unix','url':'https://example.com/'+str(n)} for n in range(8)]}
    agent.gateway.registry.get('web.read').execute=lambda url:(_ for _ in ()).throw(RuntimeError('blocked'))
    s=agent.run('tell me about Unix')
    assert s.status=='FAILED' and sum(o.tool=='web.read' for o in s.observations)==3

def test_javascript_notice_never_selected_as_answer():
    e={'text':'Possible causes include disabled JavaScript or failure to load scripts or stylesheets.\nPython provides a standard library with documented interfaces for a wide range of tasks.'}
    assert best_excerpt('Python documentation',e).startswith('Python provides')

def test_gpu_engine_capacity_and_shared_client_math():
    before={('pci','client','render'):(0,1),('pci','client','video'):(0,2)}
    after={('pci','client','render'):(100000000,1),('pci','client','video'):(100000000,2)}
    assert GPUInspector.utilization(before,after,.2)=={('pci','render'):50.0,('pci','video'):25.0}

def test_new_gpu_client_not_reported_as_100_percent():
    assert GPUInspector.utilization({}, {('pci','client','render'):(999999999,1)},.2)=={}

def test_bare_noun_topic_is_researched(agent):
    assert agent.engine.interpreter.understand('microkernel versus monolithic kernel')['kind']=='research'

def test_unspecified_mutating_objective_still_asks(agent):
    assert agent.engine.interpreter.understand('change something on my computer')['kind']=='question'

def test_documentation_precedes_system_keyword(agent):
    assert agent.engine.interpreter.understand('python memory allocation documentation')['kind']=='research'

def test_combined_system_overview(agent):
    state=agent.run('system usage')
    assert state.status=='SUCCESS' and state.response.startswith('CPU ') and 'storage' in state.response
    assert [o.tool for o in state.observations]==['system.cpu','system.ram','system.disk']
