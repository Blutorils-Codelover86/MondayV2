import json, os, threading
from pathlib import Path
import pytest
from monday.models import Action, Risk
from monday.safety import PathPolicy, CommandPolicy
from monday.bootstrap import build
from monday.registry import Tool

@pytest.mark.parametrize('name', ['.env','.env.local','.ssh/id_rsa','.gnupg/key','.aws/config','.git/config','.config/settings','node_modules/a','.venv/a'])
def test_protected_paths(cfg,name):
    with pytest.raises(PermissionError): PathPolicy(cfg.roots).resolve(str(cfg.roots[0]/name))

@pytest.mark.parametrize('name',['../outside','/etc/passwd','/etc/shadow','/boot/config','/dev/sda'])
def test_boundaries(cfg,name):
    with pytest.raises(PermissionError): PathPolicy(cfg.roots).resolve(str(cfg.roots[0]/name))

def test_symlink_outside(cfg,tmp_path):
    (cfg.roots[0]/'link').symlink_to(tmp_path)
    with pytest.raises(PermissionError): PathPolicy(cfg.roots).resolve(str(cfg.roots[0]/'link'/'secret'))

def test_symlink_inside(cfg):
    p=cfg.roots[0]/'file'; p.write_text('a'); (cfg.roots[0]/'link').symlink_to(p)
    with pytest.raises(PermissionError): PathPolicy(cfg.roots).resolve(str(cfg.roots[0]/'link'))

def test_root_mutation(cfg):
    with pytest.raises(PermissionError): PathPolicy(cfg.roots).resolve(str(cfg.roots[0]),True)

@pytest.mark.parametrize('argv', [['rm','-rf','/'],['sh','-c','uptime'],['uname','-a',';','rm','a'],['sudo','true'],['python','-c','print(1)'],['git','-c','alias.x=!rm -rf /','x'],['free','-m; touch /tmp/bad'],['env','sh'],['pacman','-S','x']])
def test_commands_denied(argv):
    with pytest.raises(PermissionError): CommandPolicy().validate(argv)

@pytest.mark.parametrize('argv',[['uname','-a'],['uptime'],['df','-h'],['free','-m'],['ip','-brief','address'],['rfkill','list']])
def test_commands_allowed(argv): assert CommandPolicy().validate(argv)==argv

@pytest.mark.parametrize('answer',[False,None,'yes','y',1,[],{}])
def test_only_boolean_approval_is_accepted(cfg,answer):
    agent=build(cfg,approve=lambda _:answer)
    result=agent.gateway.perform(Action('fs.create',{'path':str(cfg.roots[0]/'f'),'content':'x'}))
    assert not result.ok and not (cfg.roots[0]/'f').exists()

def test_dry_run_never_writes(cfg):
    a=build(cfg,approve=lambda _:pytest.fail('Dry run asked approval'),dry_run=True)
    o=a.gateway.perform(Action('fs.create',{'path':str(cfg.roots[0]/'f')}))
    assert o.simulated and not o.verified and not (cfg.roots[0]/'f').exists()

def test_dry_run_still_validates(agent):
    agent.gateway.dry_run=True
    assert not agent.gateway.perform(Action('fs.delete',{'path':'/etc/passwd'})).ok

@pytest.mark.parametrize('tool,args',[('missing',{}),('system.ram',{'bad':1}),('fs.read',{}),('fs.create',{'path':5}),('process.inspect',{'pid':True})])
def test_schema_rejection(agent,tool,args): assert not agent.gateway.perform(Action(tool,args)).ok

def test_stop_before_action(agent,cfg):
    (cfg.data_dir/'STOP').touch()
    o=agent.gateway.perform(Action('system.ram'))
    assert not o.ok and o.data['status']=='CANCELLED'

def test_stop_during_approval(cfg):
    def approval(_): (cfg.data_dir/'STOP').touch(); return True
    a=build(cfg,approve=approval)
    o=a.gateway.perform(Action('fs.create',{'path':str(cfg.roots[0]/'f')}))
    assert not o.ok and not (cfg.roots[0]/'f').exists()

def test_revalidate_after_approval(cfg,tmp_path):
    target=cfg.roots[0]/'folder'; target.mkdir()
    def approval(_): target.rmdir(); target.symlink_to(tmp_path); return True
    a=build(cfg,approve=approval)
    o=a.gateway.perform(Action('fs.create',{'path':str(target/'file')}))
    assert not o.ok and not (tmp_path/'file').exists()

def test_audit_approval_and_no_content(approved,cfg):
    action=Action('fs.create',{'path':str(cfg.roots[0]/'f'),'content':'private body'})
    assert approved.gateway.perform(action).ok
    text=(cfg.data_dir/'audit.jsonl').read_text()
    assert 'private body' not in text
    rows=[json.loads(x) for x in text.splitlines()]
    assert [r['kind'] for r in rows]==['proposal','approval','result']
    assert rows[1]['approved'] is True
    assert (cfg.data_dir/'audit.jsonl').stat().st_mode & 0o077==0

def test_read_has_no_approval(agent):
    agent.gateway.approve=lambda _:pytest.fail('Read requested approval')
    assert agent.gateway.perform(Action('system.ram')).ok

def test_mutation_verifier_required(agent):
    with pytest.raises(ValueError): agent.gateway.registry.register(Tool('bad','bad',{},Risk.HIGH,lambda:None))

def test_confidence_cannot_authorize(agent,cfg):
    agent.engine.provider=type('Provider',(),{'choose':lambda *a:'yes'})()
    state=agent.run('tool fs.create '+json.dumps({'path':str(cfg.roots[0]/'f')}))
    assert state.status=='CANCELLED' and not (cfg.roots[0]/'f').exists()

def test_private_file_content_not_persisted(approved,cfg):
    p=cfg.roots[0]/'notes'; body='private words that should stay local to the requested read'
    approved.run('tool fs.create '+json.dumps({'path':str(p),'content':body}))
    assert body not in ''.join(f.read_text() for f in cfg.data_dir.glob('*.json'))
    approved.run('tool fs.read '+json.dumps({'path':str(p)}))
    records=''.join(f.read_text() for f in cfg.data_dir.glob('*') if f.is_file())
    assert body not in records

def test_schema_is_json_schema(agent):
    schema=next(t['schema'] for t in agent.gateway.registry.describe() if t['name']=='fs.read')
    assert schema=={'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}
