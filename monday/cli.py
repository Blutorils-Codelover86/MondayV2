import argparse, importlib.util, json, os, shutil, sys
from dataclasses import asdict
from pathlib import Path
from .bootstrap import build
from .config import Config
from .models import Action

def approval(prompt):
    if not sys.stdin.isatty(): return False
    try: return input(prompt+' ').strip().lower() in ('y','yes')
    except (EOFError,KeyboardInterrupt): return False

def output(value): print(json.dumps(value,indent=2,default=lambda x:x.__name__ if isinstance(x,type) else str(x)))

def undo(agent):
    for record in agent.audit.history(50):
        if record.get('undo_consumed'): continue
        for o in reversed(record['observations']):
            inverse=o.get('inverse')
            if inverse and o['verified']:
                result=agent.gateway.perform(Action(inverse['tool'],inverse['arguments']))
                if result.ok:
                    # Mark the original record; this inverse can only be consumed once.
                    record['undo_consumed']=True
                    temp=agent.audit.directory/(record['id']+'.tmp')
                    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    with os.fdopen(fd,'w') as f: json.dump(record,f,indent=2)
                    temp.replace(agent.audit.directory/(record['id']+'.json'))
                    agent.audit.emit('undo',task_id=record['id'],tool=inverse['tool'])
                print('Undo verified.' if result.ok else 'Undo refused: '+result.error)
                return 0 if result.ok else 1
    print('No safely reversible action was recorded.'); return 2

def doctor(agent):
    cfg=agent.engine.cfg
    checks={'python':sys.version.split()[0],'normal_user':os.geteuid()!=0,
            'psutil':bool(importlib.util.find_spec('psutil')),'roots':[str(r) for r in cfg.roots if r.is_dir()],
            'commands':{c:shutil.which(c) for c in ('systemctl','pkexec','pacman','git','wpctl','rfkill','wl-paste','xdg-open','kdotool','hyprctl','ollama')},
            'stop_active':agent.gateway.runtime.stop_file.exists(),'desktop':agent.gateway.registry.get('desktop.capabilities').execute(),
            'laya_path':cfg.laya_path or 'disabled','model':cfg.ollama_model or 'disabled','search_provider':'searxng' if cfg.search_url else cfg.search_provider}
    output(checks)

def main(argv=None):
    parser=argparse.ArgumentParser(description='MONDAY local PC decision engine')
    parser.add_argument('--dry-run',action='store_true'); parser.add_argument('--json',action='store_true')
    parser.add_argument('words',nargs='*')
    args=parser.parse_args(argv); words=args.words
    cfg=Config()
    if os.geteuid()==0:
        print('Run MONDAY as your normal user.'); return 1
    command=words[0] if words else ''
    if command=='pet':
        from .pet import command as pet_command
        return pet_command(words[1:],cfg)
    # Emergency stop works even when another MONDAY process has an approval pending.
    if command=='stop':
        cfg.data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        (cfg.data_dir/'STOP').touch(mode=0o600); print('Emergency stop is active.'); return 0
    if command=='resume':
        (cfg.data_dir/'STOP').unlink(missing_ok=True); print('Emergency stop cleared.'); return 0
    agent=build(cfg,approval,args.dry_run or command=='plan')
    if command=='config': output(cfg.public()); return 0
    if command=='tools': output(agent.gateway.registry.describe()); return 0
    if command=='doctor': doctor(agent); return 0
    if command=='history':
        output([{'id':r['id'],'objective':r['objective'],'status':r['status'],'response':r['response']} for r in agent.audit.history()]); return 0
    if command=='explain':
        history=agent.audit.history(1); output(history[0] if history else {'response':'No task recorded.'}); return 0
    if command=='undo': return undo(agent)
    if command=='status': words=['check my ram']
    elif command in ('plan','run'): words=words[1:]
    if words:
        state=agent.run(' '.join(words))
        output(asdict(state)) if args.json else print(state.response)
        return 0 if state.status in ('SUCCESS','PLANNED') else 3 if state.status=='PARTIAL' else 2 if state.status=='NEEDS_CLARIFICATION' else 1
    # No resident models, browsers or services; only this blocking terminal REPL.
    try:
        while True:
            line=input('monday> ').strip()
            if line in ('exit','quit'): return 0
            if not line: continue
            if line in ('explain','history','status','tools','doctor','config','undo','stop','resume'):
                main([line]); continue
            state=agent.run(line); print(state.response)
    except (EOFError,KeyboardInterrupt): print('Stopped.'); return 0

if __name__=='__main__': sys.exit(main())
