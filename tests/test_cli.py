import json
import pytest
from monday.cli import main, approval
from monday.redact import redact

@pytest.fixture(autouse=True)
def env(cfg,monkeypatch):
    # Exercise the normal-user CLI contract even when CI itself runs in a root container.
    # test_no_root below still explicitly exercises the production root refusal.
    monkeypatch.setattr('os.geteuid',lambda:1000)
    monkeypatch.setenv('MONDAY_DATA_DIR',str(cfg.data_dir)); monkeypatch.setenv('MONDAY_ROOTS',str(cfg.roots[0])); monkeypatch.setenv('MONDAY_MODEL',''); monkeypatch.setenv('MONDAY_LAYA_PATH',''); monkeypatch.setenv('MONDAY_SEARCH_PROVIDER','wikipedia')

@pytest.mark.parametrize('args',[['check my ram'],['run','check my ram'],['plan','check my ram'],['status'],['doctor'],['config'],['tools'],['history'],['explain']])
def test_cli_commands(args,capsys):
    assert main(args)==0
    assert capsys.readouterr().out.strip()

def test_cli_normal_output_one_line(capsys):
    assert main(['check my ram'])==0
    assert len(capsys.readouterr().out.strip().splitlines())==1

def test_cli_json(capsys):
    assert main(['--json','check my ram'])==0
    assert json.loads(capsys.readouterr().out)['status']=='SUCCESS'

def test_noninteractive_approval_denied(monkeypatch):
    monkeypatch.setattr('sys.stdin.isatty',lambda:False)
    assert approval('approve') is False

@pytest.mark.parametrize('answer',['','n','YESS','sure','approve','yes please'])
def test_confirmation_not_inferred(monkeypatch,answer):
    monkeypatch.setattr('sys.stdin.isatty',lambda:True); monkeypatch.setattr('builtins.input',lambda _:answer)
    assert approval('approve') is False

@pytest.mark.parametrize('answer',['y','Y','yes','YES',' yes '])
def test_explicit_confirmation(monkeypatch,answer):
    monkeypatch.setattr('sys.stdin.isatty',lambda:True); monkeypatch.setattr('builtins.input',lambda _:answer)
    assert approval('approve') is True

def test_emergency_stop_and_resume(cfg,capsys):
    assert main(['stop'])==0 and (cfg.data_dir/'STOP').exists()
    assert main(['resume'])==0 and not (cfg.data_dir/'STOP').exists()

def test_undo_missing(capsys): assert main(['undo'])==2

def test_no_root(monkeypatch,capsys):
    monkeypatch.setattr('os.geteuid',lambda:0)
    assert main(['check my ram'])==1 and 'normal user' in capsys.readouterr().out

def test_secret_redaction():
    data=redact({'password':'sensitive','text':'token=abc authorization:secret Bearer abcdefghijk'})
    assert 'sensitive' not in str(data) and 'abcdefghijk' not in str(data)

def test_cli_undo_once(approved,cfg,monkeypatch,capsys):
    p=cfg.roots[0]/'created'
    state=approved.run('tool fs.create '+json.dumps({'path':str(p),'content':'owned fixture'}))
    assert state.status=='SUCCESS' and p.exists()
    monkeypatch.setattr('sys.stdin.isatty',lambda:True); monkeypatch.setattr('builtins.input',lambda _:'y')
    assert main(['undo'])==0 and not p.exists()
    assert main(['undo'])==2

def test_cli_undo_refuses_changed_file(approved,cfg,monkeypatch,capsys):
    p=cfg.roots[0]/'created'
    approved.run('tool fs.create '+json.dumps({'path':str(p),'content':'owned fixture'})); p.write_text('user change')
    monkeypatch.setattr('sys.stdin.isatty',lambda:True); monkeypatch.setattr('builtins.input',lambda _:'y')
    assert main(['undo'])==1 and p.read_text()=='user change'
