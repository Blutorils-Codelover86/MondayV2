"""Opt-in desktop companion: native QML, authenticated loopback bridge, supervised agent."""
from __future__ import annotations
import fcntl, hmac, json, os, secrets, shutil, signal, subprocess, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from .bootstrap import build
from .config import Config
from .models import Action
from .companion import LanguageSession
from .redact import redact

LABELS={'system.ram':'Checking RAM','system.cpu':'Sampling CPU','system.disk':'Checking storage','system.gpu':'Sampling GPU',
        'web.search':'Finding relevant sources','web.read':'Reading a source','process.search':'Inspecting processes',
        'app.discover':'Finding installed applications','app.launch':'Opening the application',
        'project.locate':'Locating your project','project.run':'Running the approved project command'}

class HealthWatch:
    """Sustained pressure and repeat suppression; observations never authorize changes."""
    def __init__(self): self.hits={}; self.last={}
    def assess(self,ram,disk,battery,now=None):
        now=time.monotonic() if now is None else now
        situations=[('ram',ram.get('percent',0)>=90,'RAM has stayed above 90%; I can inspect the largest processes.','my computer is slow'),
                    ('disk',disk.get('percent',0)>=95,'Storage is almost full; I can find the largest files.','I am running out of storage'),
                    ('battery',battery.get('percent',100)<=15 and not battery.get('power_plugged',True),'Battery is below 15%; plug in soon.','system battery usage')]
        for key,active,message,command in situations:
            self.hits[key]=self.hits.get(key,0)+1 if active else 0
            if self.hits[key]>=2 and now-self.last.get(key,-10000)>=600:
                self.last[key]=now
                return {'key':key,'message':message,'command':command}
        return None

class PetService:
    def __init__(self,cfg):
        self.cfg=cfg; self.lock=threading.RLock(); self.closed=threading.Event()
        self.phase='idle'; self.response='Ready when you are.'; self.progress=''; self.approval=None
        self.task_cancel=threading.Event(); self.work_thread=None
        self.approval_event=threading.Event(); self.approval_answer=False; self.agent=None
        self.alert=None; self.monitoring=False; self.ui_ready=False; self.last_seen=time.monotonic()
        self.watch=HealthWatch(); self.history=[]; self.task_id=''; self.ui_pid=None
        self.last_task=None; self.language=LanguageSession(); self.last_turn_chat=False
        self.steps=[]
        self.ui_geometry=(400,320)
        self.desktop={'backend':'native','configured':False,'detail':''}
        self.task_status='IDLE'
    def snapshot(self):
        with self.lock:
            self.last_seen=time.monotonic()
            return {'phase':self.phase,'response':self.response,'progress':self.progress,
                    'approval':self.approval,'alert':self.alert,'monitoring':self.monitoring,
                    'steps':list(self.steps),'ready':self.ui_ready,'task_id':self.task_id,'history':self.history[-5:],'desktop':self.desktop,'status':self.task_status}
    def geometry(self,width,height):
        if type(width) is not int or type(height) is not int or not (90<=width<=1200 and 80<=height<=1200):
            raise ValueError('Invalid pet geometry')
        with self.lock: self.ui_geometry=(width,height)
    def submit(self,objective):
        if not isinstance(objective,str) or not objective.strip() or len(objective)>4000:
            raise ValueError('Enter a command of 1–4000 characters')
        with self.lock:
            if objective.strip().casefold().rstrip('!.') in ('stop','stop the current task','stop current task'):
                self.cancel()
                if self.phase not in ('busy','approval'):
                    self.task_status='CANCELLED'; self.response='No current task is running.'
                return self.snapshot()
            if self.phase in ('busy','approval'): raise ValueError('A task is already running')
            self.steps=[]
            self.phase='busy'; self.progress='Understanding your request'; self.response=''; self.approval=None
            self.task_status='RUNNING'
            self.task_id=uuid.uuid4().hex; self.alert=None; self.task_cancel.clear()
            self.work_thread=threading.Thread(target=self.work,args=(objective.strip(),),daemon=True)
            self.work_thread.start()
        return self.snapshot()
    def approve(self,prompt):
        with self.lock:
            self.approval_event.clear(); self.approval_answer=False
            self.approval={'id':uuid.uuid4().hex,'prompt':prompt.removesuffix(' Approve? [y/N]').removesuffix('Approve? [y/N]')}
            self.phase='approval'; self.progress='Your approval is required'
        until=time.monotonic()+120
        while time.monotonic()<until:
            if self.closed.is_set() or (self.agent and self.agent.gateway.runtime.stop.is_set()): break
            if self.approval_event.wait(.1): break
        with self.lock:
            accepted=self.approval_answer is True and not self.closed.is_set()
            self.approval=None; self.phase='busy'
            return accepted
    def resolve(self,ident,accepted):
        if type(accepted) is not bool: raise ValueError('Approval must be a boolean')
        with self.lock:
            if not self.approval or not hmac.compare_digest(str(ident),self.approval['id']):
                raise ValueError('Approval expired or does not match this action')
            if self.approval_event.is_set(): raise ValueError('Approval already answered')
            self.approval_answer=accepted; self.approval_event.set()
    def progress_update(self,decision):
        with self.lock:
            action=decision.next_action
            self.progress=LABELS.get(action.tool,action.tool)+'…'
            self.steps.append(redact({'tool':action.tool,'status':'RUNNING',
                'arguments':{k:v for k,v in action.arguments.items() if k not in ('content','text')}}))
            self.steps=self.steps[-32:]
    def stage_update(self,message):
        with self.lock: self.progress=message+'…'
    def observation_update(self,decision,observation):
        with self.lock:
            if self.steps:
                status='VERIFIED' if observation.ok and observation.verified else 'FAILED'
                if not observation.ok and isinstance(observation.data,dict): status=observation.data.get('status',status)
                self.steps[-1]['status']=status
    def work(self,objective):
        response='Task did not complete.'; status='FAILED'
        try:
            agent=build(self.cfg,self.approve)
            agent.last_task=self.last_task
            agent.language=self.language; agent.last_turn_chat=self.last_turn_chat
            with self.lock: self.agent=agent
            agent.progress=self.progress_update; agent.observed=self.observation_update; agent.stage=self.stage_update
            if self.closed.is_set() or self.task_cancel.is_set(): agent.gateway.runtime.stop.set()
            if objective in ('explain','history'):
                records=agent.audit.history(5 if objective=='history' else 1)
                if objective=='history': response=' | '.join(r['response'] for r in records) or 'No tasks yet.'
                elif records:
                    record=records[0]; steps=[d['reason'] for d in record['decisions']]
                    response=record['status']+': '+record['response']+' Steps: '+'; '.join(dict.fromkeys(steps))
                else: response='No task has been recorded yet.'
                status='SUCCESS'
            else:
                result=agent.run(objective); response,status=result.response,result.status
                self.last_task=agent.last_task; self.last_turn_chat=agent.last_turn_chat
        except Exception as e: response=str(e)
        finally:
            # Publish terminal state and clear the active agent together. A new submission
            # cannot race the previous worker's cleanup and lose its cancellation handle.
            with self.lock:
                self.response=response; self.phase='done' if status in ('SUCCESS','PARTIAL','PLANNED') else 'error'
                self.task_status=status
                if self.steps and self.steps[-1]['status']=='RUNNING': self.steps[-1]['status']=status
                self.progress=''; self.agent=None; self.approval=None
                self.history.append({'objective':objective,'response':response,'status':status})
                self.history=self.history[-5:]
    def cancel(self):
        self.task_cancel.set()
        with self.lock:
            if self.agent: self.agent.gateway.runtime.stop.set()
            self.approval_answer=False; self.approval_event.set()
            if self.phase not in ('busy','approval'):
                self.task_status='CANCELLED'; self.phase='done'; self.progress=''; self.response='No current task is running.'
    def shutdown(self): self.closed.set(); self.cancel()
    def monitor(self):
        # Only reads three inexpensive metrics every 30 seconds while opted in.
        agent=build(self.cfg)
        while not self.closed.is_set():
            if self.monitoring and self.phase not in ('busy','approval'):
                try:
                    readings=[agent.gateway.perform(Action('system.'+tool)) for tool in ('ram','disk','battery')]
                    if all(o.ok for o in readings):
                        alert=self.watch.assess(*(o.data for o in readings))
                        if alert:
                            with self.lock: self.alert=alert
                except Exception: pass
            self.closed.wait(30)

class PetHTTP(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,service,token):
        self.service,self.token=service,token
        super().__init__(('127.0.0.1',0),PetHandler)

class PetHandler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def authenticated(self):
        # Browser origins are rejected; this is a native frontend, not a web-facing control API.
        expected='Bearer '+self.server.token
        return (not self.headers.get('Origin') and
                self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and
                hmac.compare_digest(self.headers.get('Authorization',''),expected))
    def send(self,code,payload):
        body=json.dumps(payload).encode()
        self.send_response(code); self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if not self.authenticated(): return self.send(403,{'error':'Unauthorized'})
        if self.path not in ('/state','/health'): return self.send(404,{'error':'Unknown endpoint'})
        self.send(200,self.server.service.snapshot())
    def do_POST(self):
        if not self.authenticated(): return self.send(403,{'error':'Unauthorized'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<0 or length>16384: raise ValueError('Request too large')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Use JSON')
            self.connection.settimeout(3)
            data=json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(data,dict): raise ValueError('Expected an object')
            service=self.server.service
            if self.path=='/command': service.submit(data.get('objective'))
            elif self.path=='/approve': service.resolve(data.get('id'),data.get('accepted'))
            elif self.path=='/cancel': service.cancel()
            elif self.path=='/watch':
                if type(data.get('enabled')) is not bool: raise ValueError('Expected enabled boolean')
                service.monitoring=data['enabled']
                if not service.monitoring: service.alert=None
            elif self.path=='/dismiss': service.alert=None
            elif self.path=='/ready': service.ui_ready=True
            elif self.path=='/geometry': service.geometry(data.get('width'),data.get('height'))
            elif self.path=='/shutdown': service.shutdown()
            else: return self.send(404,{'error':'Unknown endpoint'})
            self.send(200,service.snapshot())
        except (ValueError,TypeError,TimeoutError) as e: self.send(400,{'error':str(e)})

def directory(cfg):
    folder=cfg.data_dir/'pet'; folder.mkdir(parents=True,exist_ok=True,mode=0o700); return folder

def session_request(cfg,path='/health',payload=None):
    try:
        session=json.loads((directory(cfg)/'session.json').read_text())
        # Never follow endpoints outside loopback from a state file.
        port=int(session['port'])
        if not 1<=port<=65535: return None
        data=None if payload is None else json.dumps(payload).encode()
        request=Request(f'http://127.0.0.1:{port}'+path,data=data,headers={
            'Authorization':'Bearer '+session['token'],'Content-Type':'application/json'})
        with urlopen(request,timeout=2) as response: return json.load(response)
    except (OSError,ValueError,KeyError): return None

def serve(cfg):
    folder=directory(cfg)
    with (folder/'lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return 1
        service=PetService(cfg); token=secrets.token_urlsafe(32); server=PetHTTP(service,token)
        fd=os.open(folder/'session.json',os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as file: json.dump({'pid':os.getpid(),'port':server.server_port,'token':token},file)
        worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        threading.Thread(target=service.monitor,daemon=True).start()
        qml=shutil.which('qml6') or shutil.which('qml')
        if not qml: server.shutdown(); print('Qt QML runtime is unavailable.'); return 1
        # Keep the bridge secret out of process arguments and avoid qml's positional-file loader.
        ui_dir=Path(__file__).with_name('ui').as_uri()
        wrapper='import QtQuick\nimport '+json.dumps(ui_dir)+' as MondayUI\nMondayUI.Pet { endpoint: '+json.dumps(f'http://127.0.0.1:{server.server_port}')+'; secret: '+json.dumps(token)+' }\n'
        wrapper_path=folder/'Frontend.qml'
        fd=os.open(wrapper_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as file: file.write(wrapper)
        env=dict(os.environ)
        if os.getenv('HYPRLAND_INSTANCE_SIGNATURE') and os.getenv('WAYLAND_DISPLAY'):
            env.setdefault('QT_QPA_PLATFORM','wayland')
        frontend=subprocess.Popen([qml,'--transparent','-f',str(wrapper_path)],start_new_session=True,env=env)
        service.ui_pid=frontend.pid
        from .hyprland import PetPlacement
        placement=PetPlacement(frontend.pid)
        placement_checked=0.0
        def stop(*_): service.shutdown()
        signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
        try:
            while not service.closed.wait(.2):
                if frontend.poll() is not None: break
                now=time.monotonic()
                force=now-placement_checked>=2
                if placement.enabled and (placement.geometry!=service.ui_geometry or force):
                    service.desktop=placement.sync(*service.ui_geometry,force=force)
                    placement_checked=now
        finally:
            service.shutdown(); server.shutdown(); server.server_close()
            if frontend.poll() is None:
                frontend.terminate()
                try: frontend.wait(timeout=3)
                except subprocess.TimeoutExpired: frontend.kill(); frontend.wait()
            if service.work_thread: service.work_thread.join(timeout=30)
            (folder/'session.json').unlink(missing_ok=True)
            (folder/'Frontend.qml').unlink(missing_ok=True)
        return 0

def command(words,cfg=None):
    cfg=cfg or Config(); operation=words[0] if words else 'status'
    if operation=='serve': return serve(cfg)
    if operation=='status':
        state=session_request(cfg); print('MONDAY pet is on.' if state and state.get('ready') else 'MONDAY pet is off.')
        if state and state.get('desktop',{}).get('detail'): print(state['desktop']['detail'])
        return 0
    if operation=='off':
        state=session_request(cfg,'/shutdown',{})
        print('MONDAY pet is off.' if state else 'MONDAY pet is already off.'); return 0
    if operation!='on': print('Use monday pet on, off, or status.'); return 2
    state=session_request(cfg)
    if state and state.get('ready'): print('MONDAY pet is already on.'); return 0
    if not (os.getenv('WAYLAND_DISPLAY') or os.getenv('DISPLAY')):
        print('No desktop session is available.'); return 1
    if not (shutil.which('qml6') or shutil.which('qml')):
        print('Qt QML runtime is missing; install it explicitly before starting the pet.'); return 1
    log_path=directory(cfg)/'gui.log'
    fd=os.open(log_path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,'a') as log:
        process=subprocess.Popen([sys.executable,'-m','monday','pet','serve'],cwd=Path(__file__).resolve().parents[1],
                                 stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(60):
        state=session_request(cfg)
        if state and state.get('ready'):
            print('MONDAY pet is on; type in the box above the bot.'); return 0
        if process.poll() is not None: break
        time.sleep(.1)
    print('Pet could not start; check '+str(log_path)+'.'); return 1
