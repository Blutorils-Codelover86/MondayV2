from pathlib import Path
import json
import pytest
from monday.models import Action

def perform(a,tool,**args): return a.gateway.perform(Action('fs.'+tool,args))

def test_create_and_verified_inverse(approved,cfg):
    p=cfg.roots[0]/'f'
    o=perform(approved,'create',path=str(p),content='hello')
    assert o.ok and o.verified and o.inverse
    assert approved.gateway.perform(o.inverse).ok and not p.exists()

def test_undo_changed_file_is_refused(approved,cfg):
    p=cfg.roots[0]/'f'; o=perform(approved,'create',path=str(p),content='a'); p.write_text('changed')
    assert not approved.gateway.perform(o.inverse).ok and p.read_text()=='changed'

def test_directory_inverse_refuses_nonempty(approved,cfg):
    p=cfg.roots[0]/'dir'; o=perform(approved,'create',path=str(p),directory=True); (p/'child').touch()
    assert not approved.gateway.perform(o.inverse).ok and (p/'child').exists()

def test_write_has_no_false_undo(approved,cfg):
    p=cfg.roots[0]/'f'; p.write_text('old')
    o=perform(approved,'write',path=str(p),content='new')
    assert o.ok and o.inverse is None and p.read_text()=='new'

@pytest.mark.parametrize('tool',['copy','move','rename'])
def test_file_transfer(approved,cfg,tool):
    src=cfg.roots[0]/'a'; dst=cfg.roots[0]/'b'; src.write_text('original')
    o=perform(approved,tool,source=str(src),destination=str(dst))
    assert o.ok and dst.read_text()=='original' and o.inverse
    assert approved.gateway.perform(o.inverse).ok
    assert src.read_text()=='original' and not dst.exists()

@pytest.mark.parametrize('tool',['create','copy','move','rename'])
def test_no_clobber(approved,cfg,tool):
    src=cfg.roots[0]/'a'; dst=cfg.roots[0]/'b'; src.write_text('a'); dst.write_text('b')
    args={'path':str(dst)} if tool=='create' else {'source':str(src),'destination':str(dst)}
    assert not perform(approved,tool,**args).ok
    assert dst.read_text()=='b' and src.read_text()=='a'

def test_delete_requires_critical_confirmation(agent,cfg):
    p=cfg.roots[0]/'f'; p.touch()
    assert agent.gateway.risk(Action('fs.delete',{'path':str(p)})).name=='CRITICAL'
    assert not perform(agent,'delete',path=str(p)).ok and p.exists()

def test_delete_never_recursive(approved,cfg):
    p=cfg.roots[0]/'dir'; p.mkdir(); (p/'f').touch()
    assert not perform(approved,'delete',path=str(p)).ok and (p/'f').exists()

def test_delete_no_inverse(approved,cfg):
    p=cfg.roots[0]/'f'; p.touch(); o=perform(approved,'delete',path=str(p))
    assert o.ok and o.inverse is None

def test_search_filters_secrets_and_symlinks(agent,cfg,tmp_path):
    p=cfg.roots[0]; (p/'visible').touch(); (p/'.env').touch(); (p/'link').symlink_to(tmp_path)
    o=perform(agent,'search',path=str(p),pattern='')
    assert o.ok and o.data['matches']==[str(p/'visible')]

def test_read_limit(agent,cfg):
    p=cfg.roots[0]/'huge'; p.write_text('x'*(cfg.file_limit+1))
    assert not perform(agent,'read',path=str(p)).ok

def test_storage_observes_no_deletion(agent,cfg):
    p=cfg.roots[0]/'large.iso'; p.write_bytes(b'x'*300)
    o=perform(agent,'storage',path=str(cfg.roots[0]))
    assert o.ok and o.data['largest_files'][0]['bytes']==300 and p.exists()

def test_utf8_create_limit(approved,cfg):
    o=perform(approved,'create',path=str(cfg.roots[0]/'f'),content='é'*(cfg.file_limit//2+1))
    assert not o.ok and not (cfg.roots[0]/'f').exists()

def test_write_verifies_expected_bytes(approved,cfg):
    p=cfg.roots[0]/'f'; p.write_text('original')
    o=perform(approved,'write',path=str(p),content='é\nhello')
    import hashlib
    assert o.ok and o.data['hash']==hashlib.sha256('é\nhello'.encode()).hexdigest()
