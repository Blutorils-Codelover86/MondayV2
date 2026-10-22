import os, sys, subprocess, time
from pathlib import Path
import pytest
from monday.desktop import DesktopController
from monday.runtime import Runtime
from monday.models import Action
from monday.providers import LayaProvider,OllamaReasoner
from monday.packages import Packages

def test_xdg_discovery(cfg,tmp_path,monkeypatch):
    base=tmp_path/'apps'; (base/'applications').mkdir(parents=True)
    (base/'applications'/'sample.desktop').write_text('[Desktop Entry]\nType=Application\nName=Sample\nExec=/usr/bin/sample %U\n')
    monkeypatch.setenv('XDG_DATA_HOME',str(base)); monkeypatch.setenv('XDG_DATA_DIRS',str(tmp_path/'none'))
    desktop=DesktopController(Runtime(cfg))
    apps=desktop.discover()['applications']
    assert len(apps)==1 and desktop.resolve('sample')['id']=='sample.desktop'
    assert desktop.argv(apps[0],'file with spaces')==['/usr/bin/sample','file with spaces']

@pytest.mark.parametrize('command',['sh -c "rm -rf /"','bash -c evil','env sh','sudo app','python -c code'])
def test_desktop_interpreter_wrapper_denied(cfg,command):
    desktop=DesktopController(Runtime(cfg))
    with pytest.raises(PermissionError): desktop.argv({'exec':command,'name':'x','path':'/x','terminal':False})

def test_unknown_application(cfg,monkeypatch):
    desktop=DesktopController(Runtime(cfg)); monkeypatch.setattr(desktop,'discover',lambda:{'applications':[]})
    with pytest.raises(ValueError,match='not found'): desktop.resolve('missing')

def test_ambiguous_application(cfg,monkeypatch):
    d=DesktopController(Runtime(cfg)); monkeypatch.setattr(d,'discover',lambda:{'applications':[{'id':'a','name':'Editor A'},{'id':'b','name':'Editor B'}]})
    with pytest.raises(ValueError,match='ambiguous'): d.resolve('Editor')

def test_unsupported_windows_honest(cfg,monkeypatch):
    d=DesktopController(Runtime(cfg)); monkeypatch.setattr(d,'capabilities',lambda:{'backend':'xdg'})
    with pytest.raises(NotImplementedError): d.windows()

def test_process_pid_reuse_refused(approved,cfg):
    p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
    try:
        o=approved.gateway.perform(Action('process.terminate',{'pid':p.pid,'create_time':0.0}))
        assert not o.ok and p.poll() is None
    finally: p.terminate(); p.wait()

def test_own_test_child_termination_is_verified(approved):
    p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
    try:
        inspected=approved.gateway.perform(Action('process.inspect',{'pid':p.pid})); assert inspected.ok
        o=approved.gateway.perform(Action('process.terminate',{'pid':p.pid,'create_time':inspected.data['create_time']}))
        assert o.ok and o.verified
    finally:
        if p.poll() is None: p.terminate(); p.wait()

@pytest.mark.parametrize('pid',[0,1])
def test_protected_pids(agent,pid): assert not agent.gateway.perform(Action('process.terminate',{'pid':pid,'create_time':0.0})).ok

@pytest.mark.parametrize('name',['--overwrite=*','a;rm','a b','/etc/a',''])
def test_package_names(cfg,name):
    with pytest.raises(ValueError): Packages(Runtime(cfg)).valid(name)

def test_package_requires_approval_and_preview(agent,monkeypatch):
    t=agent.gateway.registry.get('package.operate')
    t.approval_detail=lambda args:'Resolved transaction: sample 1.0'
    t.execute=lambda **kw:pytest.fail('Unapproved installation')
    o=agent.gateway.perform(Action('package.operate',{'operation':'install','name':'sample'}))
    assert not o.ok and o.data['status']=='CANCELLED'

def test_package_preview_changed_refused(cfg,monkeypatch):
    p=Packages(Runtime(cfg)); responses=iter(['foo 1.0','foo 2.0'])
    monkeypatch.setattr(p.runtime,'run',lambda *a,**kw:{'exit_code':0,'stdout':next(responses),'stderr':''})
    p.preview({'operation':'install','name':'foo'})
    with pytest.raises(ValueError,match='changed'): p.operate('install','foo')

def test_laya_no_checkpoint_no_download(cfg):
    r=Runtime(cfg); r.run=lambda *a,**kw:pytest.fail('Model invoked')
    assert LayaProvider(cfg,r).choose('objective',{'a':'yes'}) is None

def test_laya_worker_malformed_fallback(cfg,monkeypatch):
    cfg.laya_path=str(cfg.roots[0]); r=Runtime(cfg)
    monkeypatch.setattr(r,'run',lambda *a,**kw:{'stdout':'not json'})
    assert LayaProvider(cfg,r).choose('objective',{'a':'yes'}) is None

def test_laya_outside_candidates_rejected(cfg,monkeypatch):
    cfg.laya_path=str(cfg.roots[0]); r=Runtime(cfg)
    monkeypatch.setattr(r,'run',lambda *a,**kw:{'stdout':'{"choice":"unlisted"}'})
    assert LayaProvider(cfg,r).choose('objective',{'a':'yes'}) is None

def test_ollama_disabled_no_network(cfg,monkeypatch):
    monkeypatch.setattr('monday.providers.urlopen',lambda *a,**k:pytest.fail('Network invoked'))
    assert OllamaReasoner(cfg).request('hi') is None

def test_model_missing_never_pulls(cfg,monkeypatch):
    cfg.ollama_model='missing'
    from io import BytesIO
    calls=[]
    def fetch(url,**kw): calls.append(url); return BytesIO(b'{"models":[]}')
    monkeypatch.setattr('monday.providers.urlopen',fetch)
    assert OllamaReasoner(cfg).request('hi') is None and calls==[cfg.ollama_url+'/api/tags']

def test_synthesis_unavailable(cfg,monkeypatch):
    reasoner=OllamaReasoner(cfg); monkeypatch.setattr(reasoner,'request',lambda p:None)
    assert reasoner.summarize('hi',[]) is None

def test_synthesis_fabricated_citation(cfg,monkeypatch):
    reasoner=OllamaReasoner(cfg); monkeypatch.setattr(reasoner,'request',lambda p:{'answer':'Unix is a system','citations':['FAKE'],'quotes':['Unix']})
    assert reasoner.summarize('Unix',[{'id':'E1','url':'https://x.com','text':'Unix is a system'}]) is None

def test_package_version_verification(cfg,monkeypatch):
    p=Packages(Runtime(cfg))
    monkeypatch.setattr(p.runtime,'run',lambda *a,**kw:{'exit_code':0,'stdout':'foo 1.0\n','stderr':''})
    assert p.verify({}, {'operation':'install','transaction':'foo 1.0\n','exit_code':0})
    assert not p.verify({}, {'operation':'install','transaction':'foo 2.0\n','exit_code':0})

def test_hyprland_window_id_inventory(cfg,monkeypatch):
    d=DesktopController(Runtime(cfg)); monkeypatch.setattr(d,'capabilities',lambda:{'backend':'hyprland'})
    monkeypatch.setattr(d,'windows',lambda:{'windows':[{'address':'0x123'}],'backend':'hyprland'})
    monkeypatch.setattr(d.runtime,'run',lambda argv: {'exit_code':0,'stdout':'ok','stderr':''})
    assert d.window('0x123','focus')['window_id']=='0x123'
    with pytest.raises(ValueError): d.window('0x123; exec rm','focus')

def test_nonzero_app_launch_not_verified(cfg):
    d=DesktopController(Runtime(cfg))
    assert not d.verify_launch({}, {'returncode':1})

def test_truncated_package_preview_refused(cfg,monkeypatch):
    p=Packages(Runtime(cfg)); monkeypatch.setattr(p.runtime,'run',lambda *a,**kw:{'exit_code':0,'stdout':'some 1.0','stderr':'','truncated':True})
    with pytest.raises(ValueError,match='incomplete approval'): p.preview({'operation':'install','name':'some'})

def test_service_auth_denial(approved,monkeypatch):
    from monday.system import System
    def command(argv,**kw):
        assert argv[:3]==['pkexec','systemctl','restart']
        return {'exit_code':1,'stdout':'','stderr':'authentication denied'}
    monkeypatch.setattr(approved.gateway.runtime,'run',command)
    o=approved.gateway.perform(Action('service.restart',{'name':'bluetooth.service'}))
    assert not o.ok and 'authentication denied' in o.error

def test_service_restart_needs_active_observation(approved,monkeypatch):
    def command(argv,**kw): return {'exit_code':0,'stdout':'ActiveState=inactive','stderr':''}
    monkeypatch.setattr(approved.gateway.runtime,'run',command)
    o=approved.gateway.perform(Action('service.restart',{'name':'bluetooth.service'}))
    assert not o.ok and not o.verified

def test_package_approved_exact_transaction(approved,monkeypatch):
    seen=[]; approved.gateway.approve=lambda prompt:'foo 1.0' in prompt
    def command(argv,**kw):
        seen.append(argv)
        return {'exit_code':0,'stdout':'foo 1.0\n' if argv[0]=='pacman' else '', 'stderr':''}
    monkeypatch.setattr(approved.gateway.runtime,'run',command)
    o=approved.gateway.perform(Action('package.operate',{'operation':'install','name':'foo'}))
    assert o.ok and o.verified
    assert ['pkexec','pacman','-S','--needed','--noconfirm','foo'] in seen
    assert seen[-1]==['pacman','-Q','foo']

def test_missing_diagnostic_command_error(agent,monkeypatch):
    monkeypatch.setattr(agent.gateway.runtime,'run',lambda *a,**kw:(_ for _ in ()).throw(FileNotFoundError('missing command')))
    o=agent.gateway.perform(Action('system.audio'))
    assert not o.ok and 'missing command' in o.error
