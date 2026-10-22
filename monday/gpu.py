"""Read GPU telemetry without debugfs, root or loading vendor libraries."""
from pathlib import Path
import os, re, shutil, time
import psutil

class GPUInspector:
    def __init__(self,runtime,sys_root=Path('/sys/class/drm'),proc_root=Path('/proc')):
        self.runtime,self.sys_root,self.proc_root=runtime,Path(sys_root),Path(proc_root)
    def inventory(self):
        devices=[]
        for card in sorted(self.sys_root.glob('card[0-9]*')):
            if not re.fullmatch(r'card\d+',card.name): continue
            device=card/'device'
            try:
                vendor=(device/'vendor').read_text().strip()
                driver=(device/'driver').resolve().name
                devices.append({'card':card.name,'vendor':{'0x8086':'Intel','0x1002':'AMD','0x10de':'NVIDIA'}.get(vendor,vendor),
                                'driver':driver,'pci':device.resolve().name,'device':str(device)})
            except OSError: continue
        return devices
    def counters(self):
        clients={}; started=time.monotonic(); total=0
        for proc in psutil.process_iter(['pid']):
            self.runtime.check()
            try:
                if proc.uids().real!=os.getuid(): continue
                folder=self.proc_root/str(proc.pid)/'fdinfo'
                for file in folder.iterdir():
                    total+=1
                    if total>12000 or time.monotonic()-started>1: return clients
                    text=file.read_text()[:16000]
                    if 'drm-client-id:' not in text: continue
                    rows=dict(re.findall(r'^(drm-[\w-]+):\s*(.*?)\s*$',text,re.M))
                    pci=rows.get('drm-pdev','unknown'); ident=rows['drm-client-id']
                    for name,value in rows.items():
                        if not name.startswith('drm-engine-') or name.startswith('drm-engine-capacity-'): continue
                        match=re.fullmatch(r'(\d+) ns',value)
                        if match:
                            engine=name.removeprefix('drm-engine-')
                            capacity=max(1,int(rows.get('drm-engine-capacity-'+engine,'1')))
                            # One DRM client may appear in many processes/fds; count it once.
                            key=(pci,ident,engine)
                            clients[key]=(max(clients.get(key,(0,capacity))[0],int(match[1])),capacity)
            except (OSError,psutil.Error,ValueError): continue
        return clients
    @staticmethod
    def utilization(before,after,elapsed):
        totals={}
        for (pci,client,engine),(value,capacity) in after.items():
            prior=before.get((pci,client,engine))
            if prior is None or value<prior[0]: continue
            key=(pci,engine)
            totals[key]=totals.get(key,0)+(value-prior[0])/max(elapsed,1e-9)/1e9/capacity*100
        return {key:round(min(100,max(0,val)),1) for key,val in totals.items()}
    def inspect(self):
        devices=self.inventory()
        if shutil.which('nvidia-smi') and any(d['vendor']=='NVIDIA' for d in devices):
            r=self.runtime.run(['nvidia-smi','--query-gpu=name,utilization.gpu,memory.used,memory.total','--format=csv,noheader,nounits'],timeout=5)
            if r['exit_code']==0:
                for line in r['stdout'].splitlines():
                    parts=[x.strip() for x in line.split(',')]
                    if len(parts)==4:
                        devices.append({'vendor':'NVIDIA','name':parts[0],'busy_percent':float(parts[1]),'memory_used_mib':float(parts[2]),'memory_total_mib':float(parts[3]),'source':'nvidia-smi'})
        before=self.counters(); started=time.monotonic()
        self.runtime.check(); time.sleep(.2); self.runtime.check()
        after=self.counters(); elapsed=time.monotonic()-started
        measured=self.utilization(before,after,elapsed)
        for d in devices:
            try: d['busy_percent']=float((Path(d['device'])/'gpu_busy_percent').read_text()); d['source']='driver sysfs'
            except (OSError,KeyError): pass
            engines={engine:pct for (pci,engine),pct in measured.items() if pci==d.get('pci')}
            if engines:
                d['engines_percent']=engines; d.setdefault('source','DRM counters for accessible user clients')
                d.setdefault('busy_percent',max(engines.values()))
            d.pop('device',None)
        return {'devices':devices,'sample_seconds':round(elapsed,3),'scope':'accessible user GPU clients; inaccessible processes are excluded'}
