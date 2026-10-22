import re, shutil, sys
from pathlib import Path
from .models import Risk
from .registry import Tool

class Projects:
    def __init__(self,cfg,runtime,fs,desktop): self.cfg,self.runtime,self.fs,self.desktop=cfg,runtime,fs,desktop
    def locate(self,name):
        matches=[]
        for root in self.cfg.roots:
            if not root.is_dir(): continue
            if root.name.casefold()==name.casefold(): matches.append(str(root))
            for p in root.iterdir():
                if p.is_dir() and p.name.casefold()==name.casefold() and self.fs.allowed(p): matches.append(str(p))
        if len(matches)!=1: raise ValueError('Project not found' if not matches else 'Project name is ambiguous')
        return self.inspect(matches[0])
    def inspect(self,path):
        p=self.fs.path(path)
        if not p.is_dir(): raise ValueError('Project must be a directory')
        files={q.name for q in p.iterdir()}
        kind='python' if 'pyproject.toml' in files else 'node' if 'package.json' in files else 'rust' if 'Cargo.toml' in files else 'cmake' if 'CMakeLists.txt' in files else 'make' if 'Makefile' in files else 'unknown'
        return {'path':str(p),'type':kind,'files':sorted(files)[:100], 'git':(p/'.git').exists()}
    def git(self,path,operation):
        p=self.fs.path(path)
        # --no-ext-diff/--no-textconv and disabled fsmonitor avoid executing repo-configured helpers.
        cmds={'status':['status','--short','--branch'],'diff':['diff','--no-ext-diff','--no-textconv','--stat'],
              'diff_content':['diff','--no-ext-diff','--no-textconv','--']}
        r=self.runtime.run(['git','--no-optional-locks','-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','--no-pager',*cmds[operation]],cwd=p)
        if r['exit_code']: raise RuntimeError(r['stderr'])
        return r
    def run(self,path,operation):
        p=self.fs.path(path); kind=self.inspect(path)['type']
        commands={('python','test'):[sys.executable,'-m','pytest'],('python','build'):[sys.executable,'-m','build'],
                  ('node','build'):['npm','run','build'],('node','test'):['npm','test','--','--run'],
                  ('rust','build'):['cargo','build'],('rust','test'):['cargo','test'],
                  ('make','build'):['make'],('make','test'):['make','test'],
                  ('cmake','build'):['cmake','--build','build'],('cmake','test'):['ctest','--test-dir','build','--output-on-failure']}
        argv=commands.get((kind,operation))
        if not argv: raise ValueError('No supported '+operation+' command for '+kind)
        result=self.runtime.run(argv,cwd=p,timeout=60)
        output=result['stdout']+'\n'+result['stderr']
        result['diagnostics']=[s.strip() for s in output.splitlines() if re.search(r'error:|error |failed|multiple definition|redefinition|not found',s,re.I)][:10]
        result['path']=str(p); return result
    def editor(self,path,app):
        p=self.fs.path(path)
        if not p.is_dir(): raise ValueError('Not a project directory')
        return self.desktop.launch(app,str(p))
    def terminal(self,path):
        p=self.fs.path(path)
        if not p.is_dir(): raise ValueError('Not a project directory')
        # Use installed binaries; argv patterns are dedicated API-specific templates.
        import subprocess, time
        choices=[('konsole',['--workdir',str(p)]),('kitty',['--directory',str(p)]),('foot',['--working-directory='+str(p)]),('alacritty',['--working-directory',str(p)])]
        chosen=next(((app,args) for app,args in choices if shutil.which(app)),None)
        if not chosen: raise ValueError('No supported terminal is installed')
        self.runtime.check(); proc=subprocess.Popen([chosen[0],*chosen[1]],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        time.sleep(.3)
        return {'pid':proc.pid,'executable':chosen[0],'path':str(p),'app':chosen[0],'returncode':proc.poll()}
    def register(self,r):
        r.register(Tool('project.locate','Locate a named project in configured roots',{'name':{'type':str}},Risk.READ_ONLY,self.locate))
        r.register(Tool('project.inspect','Determine project and build type',{'path':{'type':str}},Risk.READ_ONLY,self.inspect))
        r.register(Tool('project.git','Inspect Git without repo-configured executable helpers',{'path':{'type':str},'operation':{'type':str,'enum':['status','diff','diff_content']}},Risk.READ_ONLY,self.git))
        # Build scripts are arbitrary user code, so they ALWAYS require approval.
        r.register(Tool('project.run','Run an approved project build/test template',{'path':{'type':str},'operation':{'type':str,'enum':['build','test']}},Risk.HIGH,self.run,
                        lambda a,d:d['exit_code']==0))
        r.register(Tool('project.editor','Open project in discovered editor',{'path':{'type':str},'app':{'type':str}},Risk.MEDIUM,self.editor,self.desktop.verify_launch))
        r.register(Tool('project.terminal','Launch terminal at project root',{'path':{'type':str}},Risk.LOW,self.terminal,self.desktop.verify_launch))
