import json
import pytest
from monday.models import Action, Decision, Risk, Observation
from monday.registry import Tool
from monday.engine import DecisionEngine

@pytest.mark.parametrize('objective,kind',[('check my ram','action'),('my computer is slow','diagnose'),("I'm running out of storage",'storage'),('open firefox','launch'),('restart bluetooth','service'),('terminate process 223','terminate'),('get greenhouse ready','project'),("why isn't greenhouse building?",'project'),('test greenhouse','project'),('is firefox installed?','package'),('install firefox','package'),('differentiate between microkernel and monolithic kernel','research'),('tell me about Unix','research'),('do something unspecified','question')])
def test_interpretation(agent,objective,kind): assert agent.engine.interpreter.understand(objective)['kind']==kind

def test_unknown_objective_asks(agent):
    state=agent.run('do something unspecified')
    assert state.status=='NEEDS_CLARIFICATION' and not state.observations

def test_slow_inspects_before_concluding(agent):
    state=agent.run('my computer is slow')
    assert state.status=='SUCCESS'
    assert [o.tool for o in state.observations]==['system.cpu','system.ram','system.disk','process.search']
    assert all(o.verified for o in state.observations)
    assert '\n' not in state.response

def test_ram_actual_live_inspection(agent):
    state=agent.run('check my ram')
    assert state.status=='SUCCESS' and state.observations[0].data['total']>0

def test_storage_read_only(agent,cfg):
    p=cfg.roots[0]/'iso'; p.write_bytes(b'0'*100)
    state=agent.run("I'm running out of storage")
    assert state.status=='SUCCESS' and p.exists()
    assert [o.tool for o in state.observations]==['system.disk','fs.storage']

def test_failure_does_not_mean_success(agent):
    tool=agent.gateway.registry.get('system.ram'); tool.execute=lambda:(_ for _ in ()).throw(RuntimeError('hardware failure'))
    state=agent.run('check my ram')
    assert state.status=='FAILED' and 'hardware failure' in state.response

def test_verification_failure(agent):
    tool=agent.gateway.registry.get('app.launch'); tool.execute=lambda app:{'app':app}; tool.verify=lambda a,d:False
    agent.gateway.registry.get('app.discover').execute=lambda:{'applications':[]}
    state=agent.run('open test')
    assert state.status=='FAILED' and not state.observations[-1].verified

def test_browser_handoff_partial(agent):
    t=agent.gateway.registry.get('browser.open'); t.execute=lambda url:{'exit_code':0,'target':url}
    state=agent.run('open https://example.com')
    assert state.status=='PARTIAL' and 'could not be verified' in state.response

def test_loop_guard(agent):
    agent.engine.next=lambda state:Decision(state.objective,{},Action('system.ram'),'observe','ram','seen')
    state=agent.run('anything')
    assert state.status=='FAILED' and len(state.observations)==1

def test_step_budget(agent):
    agent.engine.cfg.max_steps=1
    state=agent.run('my computer is slow')
    assert state.status=='PARTIAL'

def test_task_timeout(agent):
    agent.engine.cfg.task_timeout=-1
    state=agent.run('check my ram')
    assert state.status=='FAILED' and not state.observations

def test_plan_is_not_success(agent):
    agent.gateway.dry_run=True; state=agent.run('check my ram')
    assert state.status=='PLANNED' and state.observations[0].simulated

def test_failed_build_reports_diagnostic(agent,cfg):
    p=cfg.roots[0]/'greenhouse'; p.mkdir(); (p/'Makefile').write_text('')
    agent.gateway.approve=lambda _:True
    agent.gateway.registry.get('project.run').execute=lambda **kw:{'exit_code':2,'diagnostics':['kernel.c: error: redefinition of current_color']}
    state=agent.run("why isn't greenhouse building?")
    assert state.status=='FAILED' and 'current_color' in state.response

def test_project_build_approval(agent,cfg):
    p=cfg.roots[0]/'demo'; p.mkdir(); (p/'Makefile').touch()
    agent.gateway.registry.get('project.run').execute=lambda **kw:pytest.fail('Unapproved build ran')
    state=agent.run('build demo')
    assert state.status=='CANCELLED'

def test_stop_agent(agent,cfg):
    (cfg.data_dir/'STOP').touch(); state=agent.run('check my ram')
    assert not state.observations and state.status in ('CANCELLED','FAILED')

def test_task_record_has_decisions(agent,cfg):
    state=agent.run('check my ram')
    record=agent.audit.history(1)[0]
    assert record['objective']==state.objective and len(record['decisions'])==2 and record['observations'][0]['verified']

@pytest.mark.parametrize('objective',['search web for memory management','search internet for CPU performance','look up battery technology','search for Python documentation'])
def test_explicit_web_objective_takes_precedence_over_pc_keywords(agent,objective):
    assert agent.engine.interpreter.understand(objective)['kind']=='research'

def test_search_process_still_local(agent):
    context=agent.engine.interpreter.understand('search processes chrome')
    assert context['kind']=='action' and context['action'].tool=='process.search'
