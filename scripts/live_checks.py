"""Opt-in live diagnostics and HTTP integration; no package/service mutations."""
import json, tempfile
from pathlib import Path
from monday.bootstrap import build
from monday.config import Config
from monday.models import Action

def main():
    rows=[]
    with tempfile.TemporaryDirectory(prefix='monday-live-') as directory:
        root=Path(directory)/'project'; root.mkdir()
        cfg=Config(roots=(root,),data_dir=Path(directory)/'state',ollama_model='',laya_path='')
        a=build(cfg)
        for tool,args in [('system.cpu',{}),('system.ram',{}),('system.disk',{}),('system.temperatures',{}),
                          ('system.battery',{}),('system.network',{}),('system.uptime',{}),('system.audio',{}),
                          ('system.bluetooth',{}),('process.search',{}),('service.inspect',{'name':'bluetooth.service'}),
                          ('app.discover',{}),('desktop.capabilities',{}),('package.inspect',{'name':'pacman'}),
                          ('web.read',{'url':'https://example.com'})]:
            o=a.gateway.perform(Action(tool,args)); rows.append({'tool':tool,'ok':o.ok,'verified':o.verified,'error':o.error})
        # Approved build of our own temporary fixture only; no existing user source is modified.
        (root/'Makefile').write_text('all:\n\t@printf "MONDAY live fixture build passed\\n"\n')
        a.gateway.approve=lambda _:True
        o=a.gateway.perform(Action('project.run',{'path':str(root),'operation':'build'}))
        rows.append({'tool':'project.run (temporary fixture)','ok':o.ok,'verified':o.verified,'data':o.data,'error':o.error})
        # Real files, confined to an owned temporary directory.
        o=a.gateway.perform(Action('fs.create',{'path':str(root/'note.txt'),'content':'temporary integration fixture'}))
        rows.append({'tool':'fs.create (temporary fixture)','ok':o.ok,'verified':o.verified})
        if o.inverse:
            inverse=a.gateway.perform(o.inverse)
            rows.append({'tool':'fs.undo_create (temporary fixture)','ok':inverse.ok,'verified':inverse.verified})
    (Path(__file__).resolve().parents[1]/'docs'/'live-results.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(rows,indent=2))
    return 0 if all(r['ok'] for r in rows) else 1
if __name__=='__main__': raise SystemExit(main())
