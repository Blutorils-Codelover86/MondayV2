"""User screenshot regressions, with offline models and IPC; real app/file fixtures only."""
import io
import json
from unittest.mock import Mock
import pytest
from monday.bootstrap import build
from monday.desktop import DesktopController
from monday.models import Action
from monday.providers import OllamaReasoner
from monday.runtime import Runtime


def language_agent(cfg,answer=None):
    cfg.ollama_model='gemma3:1b'
    a=build(cfg); a.engine.reasoner.request=Mock(return_value=answer)
    a.engine.reasoner.interpret=Mock(return_value={'tool':'app.launch','arguments':{'app':'different app'}})
    return a


def source_fixture(a):
    r=a.gateway.registry
    r.get('web.search').execute=lambda query:{'provider':'fixture','candidates':[{'title':'Python applications','url':'https://example.org/python'}]}
    r.get('web.read').execute=lambda url:{'id':'E1','title':'Python applications','url':url,
        'text':'Python can build websites, automation scripts, games, data analysis tools and scientific applications. These projects can start small and grow over time.'}


@pytest.mark.parametrize('answer',[None,{'answer':'explain python'},{'answer':'I cannot answer that reliably.'},{'answer':7}])
def test_bad_chat_answers_use_public_web_with_citations(cfg,answer):
    cfg.web_fallback=True
    a=language_agent(cfg,answer); source_fixture(a)
    s=a.run('explain python')
    assert s.status=='PARTIAL' and [o.tool for o in s.observations]==['web.search','web.read']
    assert '[E1] https://example.org/python' in s.response
    assert s.context['language_fallback'] is True


def test_project_idea_echo_or_trivial_answer_gets_real_sources(cfg):
    cfg.web_fallback=True
    a=language_agent(cfg,{'answer':'Python projects.'}); source_fixture(a)
    s=a.run('what can i make using python')
    assert s.status=='PARTIAL' and 'websites' in s.response and s.observations


def test_good_conversation_does_not_unnecessarily_search(cfg):
    cfg.web_fallback=True
    a=language_agent(cfg,{'answer':'You could build a quiz game, a small website, a file organizer or a robotics dashboard using Python.'})
    a.gateway.perform=Mock(side_effect=AssertionError('A useful answer needs no tools'))
    s=a.run('what can i make using python')
    assert s.status=='SUCCESS' and not s.observations


@pytest.mark.parametrize('question',['what is my password','explain our secret token','what is me@example.com using','explain /home/blu/private'])
def test_automatic_lookup_does_not_upload_personal_context(cfg,question):
    cfg.web_fallback=True
    a=language_agent(cfg,None)
    a.gateway.perform=Mock(side_effect=AssertionError('No automatic personal query upload'))
    s=a.run(question)
    assert s.status=='PARTIAL' and not s.observations


@pytest.mark.parametrize('question',['what is the latest Python release','what is the news today','who is the current president'])
def test_current_questions_go_to_web_before_model(cfg,question):
    a=language_agent(cfg)
    assert a.engine.interpreter.understand(question)['kind']=='research'
    a.engine.reasoner.request.assert_not_called()


def test_direct_url_is_read_instead_of_invented(cfg):
    a=language_agent(cfg)
    context=a.engine.interpreter.understand('explain https://example.org/article')
    assert context['kind']=='research' and context['url']=='https://example.org/article'


def test_search_failure_reports_connection_failure(cfg):
    cfg.web_fallback=True; a=language_agent(cfg)
    def offline(**args): raise OSError('Network unreachable')
    a.gateway.registry.get('web.search').execute=offline
    s=a.run('explain python')
    assert s.status=='FAILED' and 'Network unreachable' in s.response
    assert not any(o.ok for o in s.observations)


def test_stop_after_fallback_selection_does_not_start_web(cfg):
    cfg.web_fallback=True; a=language_agent(cfg)
    a.stage=lambda message:a.gateway.runtime.stop.set()
    s=a.run('explain python')
    assert s.status=='CANCELLED' and not s.observations


def test_plain_chat_transport_accepts_non_json_prose(cfg,monkeypatch):
    cfg.ollama_model='gemma3:1b'; requests=[]
    def transport(request,timeout):
        requests.append(request)
        return io.BytesIO(b'{"models":[{"name":"gemma3:1b"}]}' if isinstance(request,str) else
            b'{"message":{"role":"assistant","content":"Python is a programming language used for automation, websites and science."}}')
    monkeypatch.setattr('monday.providers.urlopen',transport)
    result=OllamaReasoner(cfg).chat('explain python',[])
    assert result['answer'].startswith('Python is')
    assert requests[1].full_url.endswith('/api/chat')
    body=json.loads(requests[1].data)
    assert 'format' not in body and body['messages'][0]['role']=='system'
    assert body['keep_alive']==0 and body['options']['num_ctx']==2048


@pytest.mark.parametrize('proposal',[None,[],{'question':'Which app?'},{'tool':'command.run','arguments':{'argv':['sh','-c','bad']}}])
def test_clear_app_request_cannot_be_vetoed_or_replaced_by_gemma(cfg,proposal):
    a=language_agent(cfg); a.engine.reasoner.interpret.return_value=proposal
    tool=a.gateway.registry.get('desktop.launch_app')
    tool.execute=lambda app:{'app':app}; tool.verify=lambda args,result:True
    s=a.run('open visual studio')
    assert s.status=='SUCCESS' and [o.tool for o in s.observations]==['desktop.launch_app']
    assert s.observations[0].data['app']=='visual studio'
    a.engine.reasoner.interpret.assert_not_called()


def test_ignored_model_proposal_still_cannot_bypass_denial(cfg):
    a=language_agent(cfg); cfg.denied_tools=('app.launch',)
    s=a.run('open visual studio')
    assert s.status=='BLOCKED' and not s.observations[0].verified


@pytest.mark.parametrize('app',['visual studio','visual-studio','vscode'])
def test_installed_editor_alias_resolution(cfg,monkeypatch,app):
    d=DesktopController(Runtime(cfg))
    monkeypatch.setattr(d,'discover',lambda:{'applications':[{'id':'code.desktop','name':'Visual Studio Code'}]})
    assert d.resolve(app)['id']=='code.desktop'


def test_editor_alias_ambiguity_does_not_choose_randomly(cfg,monkeypatch):
    d=DesktopController(Runtime(cfg))
    monkeypatch.setattr(d,'discover',lambda:{'applications':[{'id':'code.desktop','name':'Code'},{'id':'codium.desktop','name':'VSCodium'}]})
    with pytest.raises(ValueError,match='ambiguous'): d.resolve('visual studio')


@pytest.mark.parametrize('command,url',[('open youtube','https://www.youtube.com'),('open python.org','https://python.org')])
def test_site_open_uses_browser_not_app_search(agent,command,url):
    context=agent.engine.interpreter.understand(command)
    assert context['action']==Action('browser.open',{'url':url})


def native_fixture(agent,monkeypatch):
    w={'address':'0x123','title':'Editor','class':'Code','floating':True,'size':[800,600],'workspace':{'id':1}}
    calls=[]
    monkeypatch.setattr(DesktopController,'capabilities',lambda self:{'backend':'hyprland'})
    def run(argv,**kw):
        calls.append(argv)
        if argv==['hyprctl','-j','clients']: return {'exit_code':0,'stdout':json.dumps([w]),'stderr':''}
        assert kw['timeout']==5 and argv[:2]==['hyprctl','dispatch']
        if argv[2]=='movetoworkspacesilent': w['workspace']['id']=int(argv[3].split(',')[0])
        elif argv[2]=='setfloating': w['floating']=True
        elif argv[2]=='settiled': w['floating']=False
        elif argv[2]=='resizewindowpixel': w['size']=[int(x) for x in argv[3].split(',')[0].split()[1:]]
        else: pytest.fail(str(argv))
        return {'exit_code':0,'stdout':'ok','stderr':''}
    monkeypatch.setattr(agent.gateway.runtime,'run',run)
    return w,calls


@pytest.mark.parametrize('command,expected',[('move Editor to workspace 2','desktop.move_window_to_workspace'),('tile Editor','desktop.set_floating'),('float Editor','desktop.set_floating'),('resize Editor to 900x700','desktop.resize_window')])
def test_window_workflows_observe_dispatch_and_verify(agent,monkeypatch,command,expected):
    w,calls=native_fixture(agent,monkeypatch)
    s=agent.run(command)
    assert s.status=='SUCCESS' and s.observations[-1].tool==expected
    assert 'read-back verified' in s.response
    assert calls[0]==['hyprctl','-j','clients'] and calls[-1]==['hyprctl','-j','clients']


def test_resize_does_not_implicitly_change_tiling(agent,monkeypatch):
    w,calls=native_fixture(agent,monkeypatch); w['floating']=False
    s=agent.run('resize Editor to 900x700')
    assert s.status=='BLOCKED' and not any('dispatch' in c for c in calls)


def test_compositor_exit_zero_without_state_change_does_not_claim_success(agent,monkeypatch):
    native_fixture(agent,monkeypatch)
    agent.gateway.registry.get('desktop.resize_window').verify=lambda *args:False
    assert agent.run('resize Editor to 900x700').status=='FAILED'


def test_companion_layout_is_not_modified_through_general_tool(agent,monkeypatch):
    w,calls=native_fixture(agent,monkeypatch); w['title']='MONDAY companion'
    s=agent.run('tile MONDAY companion')
    assert s.status=='BLOCKED' and not any('dispatch' in c for c in calls)


def test_short_explanation_falls_back_to_sources(cfg):
    cfg.web_fallback=True; a=language_agent(cfg,{'answer':'A programming language.'}); source_fixture(a)
    s=a.run('explain python')
    assert s.status=='PARTIAL' and s.observations and '[E1]' in s.response


def test_unknown_action_model_proposal_still_needs_clarification(cfg):
    a=language_agent(cfg)
    a.engine.reasoner.interpret.return_value={'tool':'desktop.launch_app','arguments':{'app':'Firefox'}}
    s=a.run('make the desktop nicer')
    assert s.status=='NEEDS_CLARIFICATION' and not s.observations


def test_clipboard_write_previews_text_and_requires_approval(agent):
    tool=agent.gateway.registry.get('desktop.clipboard_write')
    tool.execute=Mock(side_effect=AssertionError('No unapproved clipboard write'))
    previews=[]; agent.gateway.approve=lambda prompt:previews.append(prompt) or False
    s=agent.run('set clipboard to "a user reviewed note"')
    assert s.status=='CANCELLED' and 'a user reviewed note' in previews[0]
    tool.execute.assert_not_called()


def test_clipboard_workflow_verifies_read_back(approved,monkeypatch):
    content=['']; calls=[]
    def run(argv,**kw):
        calls.append(argv)
        if argv==['wl-copy']: content[0]=kw['input_text']
        elif argv!=['wl-paste','--no-newline']: pytest.fail(str(argv))
        return {'exit_code':0,'stdout':content[0],'stderr':''}
    monkeypatch.setattr(approved.gateway.runtime,'run',run)
    assert approved.run('set clipboard to "approved note"').status=='SUCCESS'
    assert approved.run('read clipboard').response=='Clipboard: approved note'
    assert 'approved note' not in approved.audit.path.read_text()


@pytest.mark.parametrize('target',['***','   '])
def test_empty_normalized_app_target_does_not_launch_only_installed_app(cfg,monkeypatch,target):
    d=DesktopController(Runtime(cfg))
    monkeypatch.setattr(d,'discover',lambda:{'applications':[{'id':'code.desktop','name':'Code'}]})
    with pytest.raises(ValueError,match='Name an installed'): d.resolve(target)
