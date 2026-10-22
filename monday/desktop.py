"""Desktop APIs: XDG launch, Hyprland IPC, optional KWin kdotool; never X11 emulation."""
import configparser, os, re, shlex, shutil, subprocess, time
from pathlib import Path
import psutil
from .models import Risk
from .registry import Tool

class DesktopController:
    def __init__(self,runtime): self.runtime=runtime
    def capabilities(self):
        hypr=bool(os.getenv('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'))
        kwin='KDE' in os.getenv('XDG_CURRENT_DESKTOP','') and bool(shutil.which('kdotool'))
        return {'desktop':os.getenv('XDG_CURRENT_DESKTOP','unknown'),'windows':hypr or kwin,
                'backend':'hyprland' if hypr else 'kwin-kdotool' if kwin else 'xdg',
                'clipboard':bool(shutil.which('wl-paste')),'notifications':bool(shutil.which('notify-send'))}
    def discover(self):
        bases=[Path(os.getenv('XDG_DATA_HOME',str(Path.home()/'.local/share')))]
        bases.extend(Path(x) for x in os.getenv('XDG_DATA_DIRS','/usr/local/share:/usr/share').split(':'))
        found={}
        for base in bases:
            for path in (base/'applications').rglob('*.desktop'):
                ident=str(path.relative_to(base/'applications')).replace('/','-')
                if ident in found: continue
                parser=configparser.ConfigParser(interpolation=None,strict=False)
                try:
                    parser.read(path); entry=parser['Desktop Entry']
                    if entry.get('Type')!='Application' or entry.get('Hidden','false')=='true': continue
                    if not entry.get('Exec') or entry.get('NoDisplay','false')=='true': continue
                    found[ident]={'id':ident,'name':entry.get('Name',ident),'exec':entry['Exec'],
                                  'path':str(path),'terminal':entry.get('Terminal','false')=='true'}
                except (configparser.Error,KeyError,UnicodeError): continue
        return {'applications':list(found.values())}
    def resolve(self,app):
        apps=self.discover()['applications']
        exact=[a for a in apps if app.casefold() in (a['id'].casefold(),a['name'].casefold(),Path(a['id']).stem.casefold())]
        normalize=lambda text:re.sub(r'[^a-z0-9]','',text.casefold())
        names={'visualstudio':{'visualstudiocode','code','codeoss','vscodium'},
               'vscode':{'visualstudiocode','code','codeoss','vscodium'},
               'filemanager':{'dolphin','nautilus','thunar'}}
        wanted=normalize(app)
        if not wanted and not exact: raise ValueError('Name an installed application')
        aliases=[a for a in apps if normalize(a['name']) in names.get(wanted,set()) or normalize(Path(a['id']).stem) in names.get(wanted,set())]
        candidates=exact or aliases or [a for a in apps if wanted in normalize(a['name']) or wanted in normalize(a['id'])]
        if len(candidates)!=1: raise ValueError('Application not found' if not candidates else 'Application is ambiguous: '+', '.join(a['name'] for a in candidates[:6]))
        return candidates[0]
    def argv(self,entry,file=None):
        tokens=shlex.split(entry['exec']); argv=[]
        for token in tokens:
            if token in ('%f','%F','%u','%U'):
                if file: argv.append(file)
            elif token=='%i': continue
            elif token=='%c': argv.append(entry['name'])
            elif token=='%k': argv.append(entry['path'])
            elif '%' in token:
                if '%%' in token: argv.append(token.replace('%%','%'))
                else: raise ValueError('Unsupported desktop Exec field')
            else: argv.append(token)
        if file and not any(t in tokens for t in ('%f','%F','%u','%U')): argv.append(file)
        if not argv: raise ValueError('Empty desktop command')
        executable=Path(argv[0]).name
        if executable in {'sh','bash','zsh','fish','env','sudo','pkexec','python','python3','perl','ruby'}:
            raise PermissionError('Desktop entry uses an interpreter or privilege wrapper')
        if entry['terminal']: raise ValueError('Terminal desktop entries need a dedicated launcher')
        return argv
    def launch(self,app,file=None):
        entry=self.resolve(app); argv=self.argv(entry,file)
        self.runtime.check()
        p=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        # Give single-instance launchers time to hand off; the verifier inspects processes/windows.
        time.sleep(.3)
        return {'app':entry['name'],'pid':p.pid,'executable':Path(argv[0]).name,'returncode':p.poll()}
    def verify_launch(self,args,result):
        if result.get('returncode') not in (None,0): return False
        until=time.monotonic()+5
        while time.monotonic()<until:
            self.runtime.check()
            for p in psutil.process_iter(['pid','name','status','exe']):
                try:
                    if p.info['status']!=psutil.STATUS_ZOMBIE and (p.pid==result['pid'] or Path(p.info['exe'] or '').name==result['executable']):
                        result['observation']='matching process observed'; return True
                except (psutil.NoSuchProcess,psutil.AccessDenied): continue
            time.sleep(.1)
        return False
    def windows(self):
        backend=self.capabilities()['backend']
        if backend=='hyprland':
            import json
            r=self.runtime.run(['hyprctl','-j','clients'],timeout=5)
            if r['exit_code']: raise RuntimeError(r['stderr'])
            return {'windows':json.loads(r['stdout']),'backend':backend}
        if backend=='kwin-kdotool':
            r=self.runtime.run(['kdotool','search','--name','.*'])
            if r['exit_code']: raise RuntimeError(r['stderr'])
            return {'windows':[{'id':x} for x in r['stdout'].splitlines()],'backend':backend}
        raise NotImplementedError('Window inspection is unavailable on this compositor; KDE needs optional kdotool')
    def window(self,window_id,operation):
        if operation not in ('focus','close'): raise ValueError('Unsupported window operation')
        before=self.windows(); backend=before['backend']
        ids=[str(x.get('address',x.get('id'))) for x in before['windows']]
        if window_id not in ids: raise ValueError('Window is not in observed inventory')
        if backend=='hyprland' and not re.fullmatch(r'0x[0-9a-fA-F]+',window_id): raise ValueError('Invalid Hyprland window address')
        if backend=='hyprland': argv=['hyprctl','dispatch',operation+'window','address:'+window_id]
        else: argv=['kdotool','windowactivate' if operation=='focus' else 'windowclose',window_id]
        r=self.runtime.run(argv,timeout=5)
        if r['exit_code']: raise RuntimeError(r['stderr'])
        return {'window_id':window_id,'operation':operation,'backend':backend}
    def verify_window(self,args,result):
        if result['operation']=='close':
            return not any(str(w.get('address',w.get('id')))==args['window_id'] for w in self.windows()['windows'])
        if result['backend']=='hyprland':
            import json
            r=self.runtime.run(['hyprctl','-j','activewindow'],timeout=5)
            return r['exit_code']==0 and json.loads(r['stdout']).get('address')==args['window_id']
        r=self.runtime.run(['kdotool','getactivewindow']); return r['stdout'].strip()==args['window_id']
    def hypr_json(self,endpoint):
        if endpoint not in ('activewindow','activeworkspace'): raise ValueError('Unsupported IPC read')
        if self.capabilities()['backend']!='hyprland': raise NotImplementedError('This action requires Hyprland IPC')
        import json
        r=self.runtime.run(['hyprctl','-j',endpoint],timeout=5)
        if r['exit_code']: raise RuntimeError(r['stderr'] or 'Hyprland IPC failed')
        data=json.loads(r['stdout'])
        if not isinstance(data,dict) or (endpoint=='activeworkspace' and type(data.get('id')) is not int): raise ValueError('Malformed Hyprland response')
        return data
    def active_window(self):
        data=self.hypr_json('activewindow')
        # Minimize data: no screen capture, clipboard, or window contents.
        return {'window':{k:data[k] for k in ('address','title','class','pid','workspace') if k in data},'backend':'hyprland'}
    def switch_workspace(self,workspace):
        if type(workspace) is not int or not 1<=workspace<=999: raise ValueError('Workspace must be an integer from 1 to 999')
        before=self.hypr_json('activeworkspace')
        r=self.runtime.run(['hyprctl','dispatch','workspace',str(workspace)],timeout=5)
        if r['exit_code']: raise RuntimeError(r['stderr'] or 'Workspace dispatch failed')
        return {'workspace':workspace,'previous_workspace':before.get('id')}
    def verify_workspace(self,args,result):
        return self.hypr_json('activeworkspace').get('id')==args['workspace']
    def configure_window(self,window_id,operation,**values):
        if not re.fullmatch(r'0x[0-9a-fA-F]+',window_id): raise ValueError('Invalid Hyprland window address')
        inventory=self.windows()
        if inventory['backend']!='hyprland': raise NotImplementedError('Window layout control requires Hyprland IPC')
        window=next((w for w in inventory['windows'] if w.get('address')==window_id),None)
        if window is None: raise ValueError('Window is not in observed inventory')
        if window.get('title')=='MONDAY companion': raise PermissionError('Companion layout is managed by its own placement controller')
        if operation=='workspace':
            workspace=values['workspace']
            if type(workspace) is not int or not 1<=workspace<=999: raise ValueError('Workspace must be an integer from 1 to 999')
            dispatcher='movetoworkspacesilent'; parameter=f'{workspace},address:{window_id}'
        elif operation=='floating':
            floating=values['floating']
            if type(floating) is not bool: raise ValueError('Floating must be a boolean')
            dispatcher='setfloating' if floating else 'settiled'; parameter='address:'+window_id
        elif operation=='size':
            width,height=values['width'],values['height']
            if type(width) is not int or type(height) is not int or not (100<=width<=7680 and 100<=height<=4320):
                raise ValueError('Use a size within 100–7680 by 100–4320 pixels')
            if window.get('floating') is not True: raise PermissionError('Float the named window before resizing it')
            dispatcher='resizewindowpixel'; parameter=f'exact {width} {height},address:{window_id}'
        else: raise ValueError('Unsupported layout operation')
        result=self.runtime.run(['hyprctl','dispatch',dispatcher,parameter],timeout=5)
        if result['exit_code']: raise RuntimeError(result['stderr'] or 'Hyprland dispatch failed')
        return {'window_id':window_id,'operation':operation,**values}
    def verify_layout(self,args,result):
        window=next((w for w in self.windows()['windows'] if w.get('address')==args['window_id']),None)
        if window is None: return False
        if result['operation']=='workspace': return window.get('workspace',{}).get('id')==args['workspace']
        if result['operation']=='floating': return window.get('floating') is args['floating']
        if result['operation']=='size': return window.get('size')==[args['width'],args['height']]
        return False
    def open(self,target):
        # xdg-open has no browser observation API: never call navigation verified from exit alone.
        r=self.runtime.run(['xdg-open',target],timeout=15)
        return {**r,'target':target,'observation':'handoff only'}
    def clipboard_read(self): return self.runtime.run(['wl-paste','--no-newline'])
    def clipboard_write(self,text): return self.runtime.run(['wl-copy'],input_text=text)
    def notify(self,text): return self.runtime.run(['notify-send','MONDAY',text])
    def register(self,r):
        s=lambda **kw:{k:{'type':v} for k,v in kw.items()}
        r.register(Tool('desktop.move_window_to_workspace','Move a named observed window to a numbered workspace',s(window_id=str,workspace=int),Risk.LOW,
                        lambda window_id,workspace:self.configure_window(window_id,'workspace',workspace=workspace),self.verify_layout))
        r.register(Tool('desktop.set_floating','Float or tile a named observed window',s(window_id=str,floating=bool),Risk.LOW,
                        lambda window_id,floating:self.configure_window(window_id,'floating',floating=floating),self.verify_layout))
        r.register(Tool('desktop.resize_window','Resize a named observed floating window',s(window_id=str,width=int,height=int),Risk.LOW,
                        lambda window_id,width,height:self.configure_window(window_id,'size',width=width,height=height),self.verify_layout))
        r.register(Tool('desktop.list_windows','List compositor windows on request',{},Risk.READ_ONLY,self.windows))
        r.register(Tool('desktop.get_active_window','Inspect only the current Hyprland window metadata',{},Risk.READ_ONLY,self.active_window))
        r.register(Tool('desktop.focus_window','Focus an observed window',s(window_id=str),Risk.LOW,
                        lambda window_id:self.window(window_id,'focus'),self.verify_window))
        r.register(Tool('desktop.switch_workspace','Switch to a numbered Hyprland workspace',s(workspace=int),Risk.LOW,
                        self.switch_workspace,self.verify_workspace))
        r.register(Tool('desktop.launch_app','Launch a discovered XDG application',s(app=str),Risk.LOW,self.launch,self.verify_launch))
        r.register(Tool('app.discover','Discover XDG desktop entries',{},Risk.READ_ONLY,self.discover))
        r.register(Tool('app.launch','Launch a discovered application',s(app=str),Risk.LOW,self.launch,self.verify_launch))
        r.register(Tool('app.open_file','Open a file with a discovered application',s(app=str,path=str),Risk.MEDIUM,
                        lambda app,path:self.launch(app,path),self.verify_launch))
        r.register(Tool('desktop.capabilities','Report compositor API support',{},Risk.READ_ONLY,self.capabilities))
        r.register(Tool('desktop.windows','Inspect supported compositor windows',{},Risk.READ_ONLY,self.windows))
        for op,risk in [('focus',Risk.LOW),('close',Risk.MEDIUM)]:
            r.register(Tool('desktop.'+op,'Request window '+op,s(window_id=str),risk,
                            lambda window_id,op=op:self.window(window_id,op),self.verify_window))
        r.register(Tool('desktop.open_file','Request XDG file handoff (not verified navigation)',s(path=str),Risk.MEDIUM,
                        lambda path:self.open(path),lambda a,d:False))
        r.register(Tool('desktop.clipboard_read','Read Wayland clipboard',{},Risk.READ_ONLY,self.clipboard_read))
        r.register(Tool('desktop.clipboard_write','Set Wayland clipboard',s(text=str),Risk.MEDIUM,self.clipboard_write,
                        lambda a,d:d['exit_code']==0 and self.clipboard_read()['stdout']==a['text'],
                        lambda a:f"Replace clipboard with {len(a['text'])} characters: {a['text'][:240]!r}"))
        r.register(Tool('desktop.notify','Request desktop notification',s(text=str),Risk.LOW,self.notify,
                        lambda a,d:d['exit_code']==0))
