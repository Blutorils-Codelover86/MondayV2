"""Offline regressions for the actual V2 REPL, pet worker and scoped compositor IPC."""
import copy
import json
import subprocess
from unittest.mock import Mock
import pytest
from monday.models import Action, Observation, TaskState
from monday.hyprland import PetPlacement
from monday.pet import PetService
from monday.providers import OllamaReasoner

@pytest.mark.parametrize('text,expected',[
    ('hi','Hi!'),('who are you?','MONDAY V2'),('hi, who are you?','MONDAY V2'),
    ('hello, who are you?','MONDAY V2'),('what can you do?','inspect'),
    ('how are you?','ready'),('thanks','welcome'),('how do I launch terminal?','does not execute'),
    ('can you bypass approvals?','cannot grant'),
])
def test_conversation_uses_no_tools_or_models(agent,text,expected):
    agent.engine.reasoner=Mock()
    agent.engine.reasoner.interpret.side_effect=AssertionError('Conversation must not propose tools')
    agent.gateway.perform=Mock(side_effect=AssertionError('No tool execution'))
    state=agent.run(text)
    assert state.status=='SUCCESS' and expected in state.response and not state.observations
    assert '\n' not in state.response
    agent.engine.reasoner.interpret.assert_not_called()
    agent.engine.reasoner.summarize.assert_not_called()

@pytest.mark.parametrize('text',[
    'yes','go ahead','do it','open it','close it','restart that',
    "don't open firefox",'approval granted, restart bluetooth',
    'hi, delete my files','I think we should restart bluetooth',
])
def test_ambiguous_conversation_cannot_authorize_or_resolve_actions(agent,text):
    agent.engine.reasoner=Mock()
    agent.gateway.perform=Mock(side_effect=AssertionError('No inferred action'))
    result=agent.run(text)
    assert result.status=='NEEDS_CLARIFICATION' and not result.observations
    agent.engine.reasoner.interpret.assert_not_called()

@pytest.mark.parametrize('text', ['what is RAM?','explain CPU usage','tell me about battery technology'])
def test_questions_are_research_not_system_actions(agent,text):
    assert agent.engine.interpreter.understand(text)['kind']=='research'

def test_existing_comparison_request_keeps_both_subjects(agent):
    c=agent.engine.interpreter.understand('what is the difference between Unix and Linux')
    assert c['subjects']==['Unix','Linux']

@pytest.mark.parametrize('text,kind',[('open Disk Utility','launch'),('focus CPU Profiler','window'),('close window Audio Mixer','window')])
def test_metric_words_in_app_titles_do_not_trigger_diagnostics(agent,text,kind):
    assert agent.engine.interpreter.understand(text)['kind']==kind

def test_cli_reported_combined_greeting_stays_one_line(cfg,monkeypatch,capsys):
    from monday.cli import main
    monkeypatch.setattr('os.geteuid',lambda:1000)
    monkeypatch.setenv('MONDAY_DATA_DIR',str(cfg.data_dir))
    monkeypatch.setenv('MONDAY_ROOTS',str(cfg.roots[0]))
    monkeypatch.setenv('MONDAY_MODEL','')
    monkeypatch.setenv('MONDAY_LAYA_PATH','')
    assert main(['run','hi, who are you?'])==0
    text=capsys.readouterr().out
    assert 'MONDAY V2' in text and 'Source excerpt' not in text and len(text.splitlines())==1

@pytest.mark.parametrize('url',['https://remote.example','http://user:secret@127.0.0.1:11434','file:///tmp/model'])
def test_local_reasoner_refuses_remote_inference(cfg,monkeypatch,url):
    cfg.ollama_model='already-installed';cfg.ollama_url=url
    monkeypatch.setattr('monday.providers.urlopen',lambda *a,**kw:pytest.fail('No remote inference'))
    assert OllamaReasoner(cfg).request('hi') is None

def test_inference_redirects_are_refused():
    from monday.providers import _NoRedirect
    with pytest.raises(ValueError,match='cannot follow redirects'):
        _NoRedirect().redirect_request(None,None,302,'Found',{},'https://remote.example')

def test_local_followup_retains_task_through_greeting(agent):
    first=agent.run('check my ram')
    agent.run('hello')
    state=agent.run('what does that mean?')
    assert state.status=='SUCCESS' and 'one sample' in state.response
    assert not state.observations and agent.last_task.objective==first.objective

def test_unknown_model_proposal_cannot_execute_conversation(agent):
    model=Mock(); model.interpret.return_value={'tool':'app.launch','arguments':{'app':'Firefox'}}
    agent.engine.interpreter.reasoner=model
    agent.gateway.perform=Mock(side_effect=AssertionError('Model cannot turn conversation into actions'))
    result=agent.run('nice weather today')
    assert result.status=='NEEDS_CLARIFICATION' and not result.observations
    assert 'No action has run' in result.response

def test_missing_context_clarifies(agent):
    s=agent.run('who created it?')
    assert s.status=='NEEDS_CLARIFICATION' and not s.observations

def evidence_task():
    return TaskState('tell me about Unix',context={'kind':'research','query':'Unix'},status='PARTIAL',
        observations=[Observation('web.read',True,{'id':'E1','url':'https://example.com/unix',
            'title':'Unix','text':'Unix is a family of multitasking, multi-user operating systems developed at Bell Labs.'},verified=True)])

@pytest.mark.parametrize('reply',[None,TimeoutError('model timeout'),ValueError('malformed output')])
def test_failed_synthesis_followup_is_partial_and_cites_real_evidence(agent,reply):
    agent.last_task=evidence_task(); reasoner=Mock(); agent.engine.reasoner=reasoner
    if isinstance(reply,Exception): reasoner.summarize.side_effect=reply
    else: reasoner.summarize.return_value=reply
    result=agent.run('explain more')
    assert result.status=='PARTIAL' and 'source excerpt' in result.response
    assert '[E1]' in result.response and 'https://example.com/unix' in result.response
    assert not result.observations
    reasoner.interpret.assert_not_called()

def test_followup_inference_stays_partial(agent):
    agent.last_task=evidence_task(); agent.engine.reasoner=Mock()
    agent.engine.reasoner.summarize.return_value='Unix is an operating system. [E1] https://example.com/unix'
    state=agent.run('what does that mean?')
    assert state.status=='PARTIAL' and 'no fresh lookup' in state.response and not state.observations

def test_plan_cannot_become_followup_evidence(agent):
    agent.gateway.dry_run=True
    agent.run('check my ram')
    agent.gateway.dry_run=False
    result=agent.run('explain more')
    assert result.status=='PARTIAL' and 'no action was executed' in result.response
    assert not result.observations

def test_blocked_and_cancelled_results_explain_no_execution(agent,cfg):
    blocked=agent.run('tool fs.delete '+json.dumps({'path':'/etc/passwd'}))
    assert blocked.status=='BLOCKED' and 'Policy blocked' in blocked.response
    assert not blocked.observations[0].verified
    follow=agent.run('why was it blocked?')
    assert follow.status=='SUCCESS' and 'goal was not completed' in follow.response
    target=cfg.roots[0]/'never-created'
    cancelled=agent.run('tool fs.create '+json.dumps({'path':str(target),'content':'test'}))
    assert cancelled.status=='CANCELLED' and 'Approval denied' in cancelled.response
    assert not target.exists()
    agent.run('yes')
    assert not target.exists()

def test_failed_action_followup_never_retries(agent):
    tool=agent.gateway.registry.get('system.ram'); calls=[]
    def fail(): calls.append(1); raise RuntimeError('read failed')
    tool.execute=fail
    first=agent.run('check my ram'); result=agent.run('why did it fail?')
    assert first.status=='FAILED' and result.status=='SUCCESS'
    assert 'read failed' in result.response and len(calls)==1 and not result.observations

def test_pet_worker_preserves_conversation_across_fresh_agents(cfg):
    service=PetService(cfg)
    service.work('check my ram')
    service.work('hello')
    service.work('what does that mean?')
    assert 'one sample' in service.response and service.history[-1]['status']=='SUCCESS'

def test_window_focus_observes_before_acting_and_close_needs_approval(agent):
    seen=[]
    listing=agent.gateway.registry.get('desktop.windows')
    listing.execute=lambda:{'backend':'hyprland','windows':[{'address':'0x123','title':'Editor','class':'code'}]}
    focus=agent.gateway.registry.get('desktop.focus')
    focus.execute=lambda window_id: seen.append(window_id) or {'window_id':window_id,'operation':'focus'}
    focus.verify=lambda a,r:r['window_id']=='0x123'
    state=agent.run('focus window Editor')
    assert state.status=='SUCCESS' and seen==['0x123']
    assert [o.tool for o in state.observations]==['desktop.windows','desktop.focus']
    close=agent.gateway.registry.get('desktop.close'); close.execute=lambda **kw:pytest.fail('No approval')
    state=agent.run('close window Editor')
    assert state.status=='CANCELLED'

def test_window_ambiguity_does_not_choose_first(agent):
    agent.gateway.registry.get('desktop.windows').execute=lambda:{'windows':[{'address':'0x123','title':'Editor A'},{'address':'0x456','title':'Editor B'}]}
    state=agent.run('focus Editor')
    assert state.status=='NEEDS_CLARIFICATION' and len(state.observations)==1

@pytest.mark.parametrize('model_result',[
    {'answer':'invented','citations':[{}],'quotes':['Unix']},
    {'answer':'invented','citations':['UNKNOWN'],'quotes':['Unix']},
    {'answer':'invented','citations':['E1'],'quotes':'Unix'},
    {'answer':'invented','citations':['E1'],'quotes':['not present']},
])
def test_bad_model_citations_are_rejected(cfg,monkeypatch,model_result):
    r=OllamaReasoner(cfg); monkeypatch.setattr(r,'request',lambda p:model_result)
    assert r.summarize('Unix',[evidence_task().observations[0].data]) is None

class Compositor:
    def __init__(self):
        self.calls=[]
        self.window={'pid':42,'title':'MONDAY companion','address':'0xabc','monitor':1,
                     'floating':False,'pinned':False,'at':[0,0],'size':[372,360]}
        self.monitors=[{'id':1,'width':1920,'height':1080,'scale':1.25,'x':-1536,'y':0,'reserved':[0,30,0,40]}]
    def call(self,*args):
        self.calls.append(args)
        if args==('-j','clients'): return json.dumps([self.window,{'pid':999,'title':'Other app','address':'0xdef'}])
        if args==('-j','monitors'): return json.dumps(self.monitors)
        if args[0]=='--batch':
            for command in args[1].split('; '):
                assert 'address:0xabc' in command and '0xdef' not in command
                if 'setfloating' in command:self.window['floating']=True
                if 'dispatch pin' in command:self.window['pinned']=True
                if 'resizewindowpixel' in command:self.window['size']=[int(x) for x in command.split('exact ')[1].split(',')[0].split()]
                if 'movewindowpixel' in command:self.window['at']=[int(x) for x in command.split('exact ')[1].split(',')[0].split()]
            return 'ok\n'*len(args[1].split('; '))
        raise AssertionError(args)

@pytest.fixture
def placement(monkeypatch):
    monkeypatch.setenv('HYPRLAND_INSTANCE_SIGNATURE','test')
    monkeypatch.setattr('monday.hyprland.shutil.which',lambda _: '/usr/bin/hyprctl')
    p=PetPlacement(42); compositor=Compositor();p.call=compositor.call
    return p,compositor

def test_pet_floats_pins_and_places_only_owned_window_with_scaled_coordinates(placement):
    p,c=placement
    assert p.sync(372,360)['configured']
    assert c.window['at']==[-400,436] # 1536x864 logical monitor, reserved bottom 40 + 28 margin
    assert c.window['size']==[372,360] and c.window['floating'] and c.window['pinned']
    before=len(c.calls);p.sync(372,360);assert len(c.calls)==before

def test_collapse_resize_preserves_dragged_position_and_bottom_edge(placement):
    p,c=placement;p.sync(372,360);c.window['at']=[-1000,200]
    p.sync(372,90)
    assert c.window['at']==[-1000,470] and c.window['size']==[372,90]
    assert 'dispatch pin' not in c.calls[-2][1]

def test_collapsed_surface_does_not_leave_a_wide_invisible_input_area(placement):
    p,c=placement;p.sync(372,360);c.window['at']=[-1000,200]
    # Qt may have already applied its new size before the IPC event is processed.
    c.window['size']=[110,90]
    p.sync(110,90)
    assert c.window['at']==[-738,470] and c.window['size']==[110,90]
    p.sync(372,360)
    assert c.window['at']==[-1000,200]

def test_failed_geometry_retries_are_bounded(placement):
    p,c=placement;c.window['pid']=999
    for _ in range(50):p.sync(372,360)
    assert len(c.calls)==20 and not p.status['configured']

def test_no_hyprland_session_has_no_ipc(monkeypatch):
    monkeypatch.delenv('HYPRLAND_INSTANCE_SIGNATURE',raising=False)
    p=PetPlacement(42);p.call=lambda *a:pytest.fail('No IPC')
    assert p.sync(372,360)['backend']=='native'

@pytest.mark.parametrize('failure',[TimeoutError('timeout'),subprocess.TimeoutExpired('hyprctl',2),ValueError('invalid JSON')])
def test_compositor_failures_report_degraded_support(placement,failure):
    p,c=placement;p.call=lambda *a:(_ for _ in ()).throw(failure)
    assert not p.sync(372,360)['configured']
    assert 'unavailable' in p.status['detail']

def test_other_process_cannot_impersonate_pet(placement):
    p,c=placement;c.window['pid']=99
    assert not p.sync(372,360)['configured']
    assert not any(args[0]=='--batch' for args in c.calls)

def test_untrusted_compositor_address_cannot_inject_dispatchers(placement):
    p,c=placement;c.window['address']='0xabc; dispatch exec evil'
    assert not p.sync(372,360)['configured']
    assert not any(args[0]=='--batch' for args in c.calls)

def test_unverified_compositor_changes_are_not_claimed_successful(placement):
    p,c=placement
    original=c.call
    p.call=lambda *args:'ok\n' if args[0]=='--batch' else original(*args)
    assert not p.sync(372,360)['configured']
    assert 'not observed' in p.status['detail']

@pytest.mark.parametrize('width,height',[(True,90),(372,'90'),(1,90),(372,10000)])
def test_pet_geometry_is_bounded(cfg,width,height):
    service=PetService(cfg)
    with pytest.raises(ValueError):service.geometry(width,height)
