import os, re, time
from pathlib import Path
import psutil
from .models import Risk
from .registry import Tool

class System:
    def __init__(self, runtime): self.runtime=runtime
    def cpu(self): return {"percent":psutil.cpu_percent(interval=.15),"logical_cpus":psutil.cpu_count(),"load":os.getloadavg()}
    def ram(self):
        m=psutil.virtual_memory(); return {"total":m.total,"available":m.available,"used":m.used,"percent":m.percent}
    def disk(self):
        d=psutil.disk_usage('/'); return {"path":"/","total":d.total,"free":d.free,"used":d.used,"percent":d.percent}
    def temperatures(self): return {k:[x._asdict() for x in v] for k,v in psutil.sensors_temperatures().items()}
    def battery(self):
        b=psutil.sensors_battery(); return b._asdict() if b else {"available":False}
    def uptime(self): return {"seconds":time.time()-psutil.boot_time()}
    def processes(self,query=""):
        rows=[]
        for p in psutil.process_iter(['pid','name','memory_info','cpu_times','username','create_time']):
            self.runtime.check()
            try:
                info=p.info
                if query and query.casefold() not in info['name'].casefold(): continue
                rows.append({"pid":info['pid'],"name":info['name'],"rss":info['memory_info'].rss,
                             "cpu_seconds":sum(info['cpu_times'][:2]),"username":info['username'],"create_time":info['create_time']})
            except (psutil.NoSuchProcess,psutil.AccessDenied,AttributeError): continue
        return {"processes":sorted(rows,key=lambda x:x['rss'],reverse=True)[:100],"count":len(rows)}
    def inspect_process(self,pid):
        p=psutil.Process(pid)
        return {"pid":pid,"name":p.name(),"status":p.status(),"create_time":p.create_time(),"rss":p.memory_info().rss}
    def terminate(self,pid,create_time):
        p=psutil.Process(pid)
        if p.uids().real!=os.getuid(): raise PermissionError("Can only terminate your own processes")
        if p.create_time()!=create_time: raise ValueError("PID was reused")
        if p.name() in {'systemd','kwin_wayland','Hyprland','plasmashell','dbus-daemon','sshd','monday'}:
            raise PermissionError("Session-critical process is protected")
        p.terminate()
        try: p.wait(timeout=5)
        except psutil.TimeoutExpired: raise TimeoutError("Process did not terminate; no forced kill attempted")
        return {"pid":pid,"create_time":create_time}
    def verify_terminated(self,args,result):
        try:
            p=psutil.Process(result['pid']); return p.create_time()!=result['create_time'] or p.status()==psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess: return True
    def service(self,name):
        self.unit(name)
        return self.runtime.run(['systemctl','show',name,'--property=ActiveState,SubState,LoadState','--no-pager'])
    def unit(self,name):
        if not re.fullmatch(r'[a-zA-Z0-9_.@-]+\.service',name): raise ValueError("Use a service unit name")
    def restart_service(self,name):
        self.unit(name)
        # Normal OS authentication, finite wait, no passwords handled by MONDAY.
        r=self.runtime.run(['pkexec','systemctl','restart',name],timeout=60)
        if r['exit_code']: raise RuntimeError(r['stderr'] or 'Administrator permission denied')
        return self.service(name)
    def network(self):
        return {"interfaces":{k:[{'address':a.address,'family':str(a.family)} for a in v] for k,v in psutil.net_if_addrs().items()},
                "state":{k:v._asdict() for k,v in psutil.net_if_stats().items()}}
    def audio(self): return self.runtime.run(['wpctl','status'])
    def bluetooth(self): return self.runtime.run(['rfkill','--json'])
    def logs(self): return self.runtime.run(['journalctl','--user','-n','50','--no-pager','-p','warning'])
    def gpu(self):
        from .gpu import GPUInspector
        return GPUInspector(self.runtime).inspect()
    def register(self,r):
        for name in ('cpu','ram','disk','gpu','temperatures','battery','uptime','network','audio','bluetooth','logs'):
            r.register(Tool('system.'+name,'Inspect '+name,{},Risk.READ_ONLY,getattr(self,name), (lambda a,d:d['exit_code']==0) if name in ('audio','bluetooth','logs') else None))
        r.register(Tool('process.search','Search and rank processes by RSS',{'query':{'type':str,'required':False}},Risk.READ_ONLY,self.processes))
        r.register(Tool('process.inspect','Inspect a process',{'pid':{'type':int}},Risk.READ_ONLY,self.inspect_process))
        r.register(Tool('process.terminate','Graceful termination of an observed user process',{'pid':{'type':int},'create_time':{'type':float}},Risk.MEDIUM,self.terminate,self.verify_terminated))
        r.register(Tool('service.inspect','Read system service state',{'name':{'type':str}},Risk.READ_ONLY,self.service,lambda a,d:d['exit_code']==0))
        r.register(Tool('service.restart','Restart one service via OS authentication',{'name':{'type':str}},Risk.HIGH,self.restart_service,
                        lambda a,d:d['exit_code']==0 and 'ActiveState=active' in d['stdout']))
