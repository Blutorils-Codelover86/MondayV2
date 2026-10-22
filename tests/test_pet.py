import json, os, shutil, subprocess, threading, time
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest
from monday.pet import PetService,PetHTTP,HealthWatch,session_request


def test_health_alert_requires_sustained_pressure():
    w=HealthWatch(); args=({'percent':95},{'percent':50},{'percent':90,'power_plugged':True})
    assert w.assess(*args,now=0) is None
    assert w.assess(*args,now=30)['key']=='ram'
    assert w.assess(*args,now=60) is None
    assert w.assess(*args,now=650)['key']=='ram'

def test_watch_recovery_resets_pressure():
    w=HealthWatch(); disk={'percent':20}; bat={'percent':80,'power_plugged':True}
    assert w.assess({'percent':95},disk,bat,now=0) is None
    assert w.assess({'percent':40},disk,bat,now=30) is None
    assert w.assess({'percent':95},disk,bat,now=60) is None

def test_low_battery_not_warned_when_charging():
    w=HealthWatch()
    for t in (0,30): assert w.assess({'percent':1},{'percent':1},{'percent':10,'power_plugged':True},now=t) is None

@pytest.fixture
def bridge(cfg):
    service=PetService(cfg); server=PetHTTP(service,'test-secret')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield service,server
    service.shutdown();server.shutdown();server.server_close()
    if service.work_thread: service.work_thread.join(timeout=3)

def request(server,path='/state',data=None,token='test-secret',origin=None):
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    if origin: headers['Origin']=origin
    req=Request(f'http://127.0.0.1:{server.server_port}'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
    with urlopen(req,timeout=3) as r:return json.load(r)

def await_phase(service,phases):
    until=time.monotonic()+3
    while time.monotonic()<until:
        s=service.snapshot()
        if s['phase'] in phases:return s
        time.sleep(.01)
    pytest.fail('Task did not reach expected phase: '+str(service.snapshot()))

@pytest.mark.parametrize('token,origin',[('bad',None),('test-secret','https://example.com'),('test-secret','null')])
def test_bridge_rejects_remote_or_unauthorized_clients(bridge,token,origin):
    with pytest.raises(HTTPError) as e: request(bridge[1],token=token,origin=origin)
    assert e.value.code==403

def test_native_command_roundtrip(bridge):
    service,server=bridge
    request(server,'/command',{'objective':'system ram usage'})
    state=await_phase(service,('done',))
    assert state['response'].startswith('RAM is') and state['history'][-1]['status']=='SUCCESS'

def test_gui_approval_denied_creates_nothing(bridge,cfg):
    service,server=bridge;p=cfg.roots[0]/'file'
    request(server,'/command',{'objective':'tool fs.create '+json.dumps({'path':str(p),'content':'test'})})
    approval=await_phase(service,('approval',))['approval']
    request(server,'/approve',{'id':approval['id'],'accepted':False})
    state=await_phase(service,('error',))
    assert not p.exists() and state['history'][-1]['status']=='CANCELLED'

def test_gui_approval_is_action_bound(bridge,cfg):
    service,server=bridge;p=cfg.roots[0]/'file'
    request(server,'/command',{'objective':'tool fs.create '+json.dumps({'path':str(p),'content':'test'})})
    approval=await_phase(service,('approval',))['approval']
    with pytest.raises(HTTPError):request(server,'/approve',{'id':'wrong','accepted':True})
    with pytest.raises(HTTPError):request(server,'/approve',{'id':approval['id'],'accepted':'yes'})
    assert not p.exists()
    request(server,'/approve',{'id':approval['id'],'accepted':True})
    assert await_phase(service,('done',))['history'][-1]['status']=='SUCCESS' and p.read_text()=='test'

def test_cancel_during_approval_denies_write(bridge,cfg):
    service,server=bridge;p=cfg.roots[0]/'file'
    request(server,'/command',{'objective':'tool fs.create '+json.dumps({'path':str(p)})})
    await_phase(service,('approval',))
    request(server,'/cancel',{})
    await_phase(service,('error',))
    assert not p.exists()

def test_only_one_task_runs_at_once(bridge,cfg):
    service,server=bridge
    request(server,'/command',{'objective':'tool fs.create '+json.dumps({'path':str(cfg.roots[0]/'file')})})
    await_phase(service,('approval',))
    with pytest.raises(HTTPError):request(server,'/command',{'objective':'system ram usage'})
    service.cancel()

def test_shutdown_cancels_pending_approval(bridge,cfg):
    service,server=bridge;p=cfg.roots[0]/'file'
    request(server,'/command',{'objective':'tool fs.create '+json.dumps({'path':str(p)})})
    await_phase(service,('approval',)); request(server,'/shutdown',{})
    assert service.closed.is_set()
    await_phase(service,('error',));assert not p.exists()

def test_watch_can_be_paused(bridge):
    assert request(bridge[1],'/watch',{'enabled':False})['monitoring'] is False

def test_invalid_bridge_endpoint(bridge):
    with pytest.raises(HTTPError) as e: request(bridge[1],'/unknown',{})
    assert e.value.code==404

def test_session_file_is_not_in_task_history(agent,cfg):
    folder=cfg.data_dir/'pet';folder.mkdir();(folder/'session.json').write_text('{}')
    assert agent.audit.history()==[]

def test_native_qml_input_and_result_integration(bridge,tmp_path):
    qml=shutil.which('qml6') or shutil.which('qml')
    if not qml:pytest.skip('Qt QML runtime not installed')
    service,server=bridge
    source=Path(__file__).resolve().parents[1]/'monday'/'ui'/'Pet.qml'
    screenshot=tmp_path/'pet.png'
    env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software')
    result=subprocess.run([qml,'--transparent','-f',str(source),'--',f'http://127.0.0.1:{server.server_port}','test-secret','--smoke',str(screenshot)],env=env,capture_output=True,timeout=12)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert screenshot.is_file() and screenshot.stat().st_size>1000
    assert service.snapshot()['history'][-1]['objective']=='system ram usage'
