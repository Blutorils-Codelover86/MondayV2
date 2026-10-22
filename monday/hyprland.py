"""Position only the owned pet window using Hyprland IPC; never edit compositor config."""
import json
import math
import os
import re
import shutil
import subprocess

class PetPlacement:
    def __init__(self,pid):
        self.pid=pid
        self.enabled=bool(os.getenv('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'))
        self.address=None
        self.geometry=None
        self.size=None
        self.attempts={}
        self.status={'backend':'hyprland' if self.enabled else 'native','configured':False,'detail':''}

    def call(self,*args):
        result=subprocess.run(['hyprctl',*args],capture_output=True,text=True,timeout=2,check=False)
        if result.returncode or result.stdout.strip().lower().startswith(('error','unknown','invalid')):
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Hyprland IPC failed')
        return result.stdout

    def sync(self,width,height):
        if not self.enabled or self.geometry==(width,height): return self.status
        if type(width) is not int or type(height) is not int or not (90<=width<=1200 and 80<=height<=1200):
            raise ValueError('Invalid pet geometry')
        key=(width,height)
        if self.attempts.get(key,0)>=20: return self.status
        self.attempts[key]=self.attempts.get(key,0)+1
        try:
            clients=json.loads(self.call('-j','clients'))
            owned=[c for c in clients if c.get('pid')==self.pid and c.get('title')=='MONDAY companion']
            if len(owned)!=1:
                self.status['detail']='Waiting for the owned pet window to map.'
                return self.status
            window=owned[0]; address=window.get('address','')
            if not re.fullmatch(r'0x[0-9a-fA-F]+',address): raise ValueError('Invalid owned window address')
            monitors=json.loads(self.call('-j','monitors'))
            monitor=next((m for m in monitors if m.get('id')==window.get('monitor')),None)
            if not monitor: raise ValueError('The pet monitor is unavailable')
            scale=float(monitor.get('scale',1))
            if not math.isfinite(scale) or scale<=0: raise ValueError('Invalid monitor scale')
            mw,mh=int(monitor['width']/scale),int(monitor['height']/scale)
            if monitor.get('transform',0) in (1,3,5,7): mw,mh=mh,mw
            left,top,right,bottom=monitor.get('reserved',[0,0,0,0])
            x0,y0=int(monitor.get('x',0)+left),int(monitor.get('y',0)+top)
            w,h=min(width,max(90,mw-left-right)),min(height,max(80,mh-top-bottom))
            xmax,ymax=int(monitor.get('x',0)+mw-right-w),int(monitor.get('y',0)+mh-bottom-h)
            first=self.address!=address
            if first: x,y=xmax-28,ymax-28
            else:
                x,y=window['at']
                # Preserve the bot's bottom edge when the command box opens or collapses.
                x+=self.size[0]-w
                y+=self.size[1]-h
            x,y=max(x0,min(int(x),xmax)),max(y0,min(int(y),ymax))
            target='address:'+address
            commands=[]
            if not window.get('floating'): commands.append('dispatch setfloating '+target)
            if not window.get('pinned'): commands.append('dispatch pin '+target)
            commands += [f'dispatch resizewindowpixel exact {w} {h},{target}',
                         f'dispatch movewindowpixel exact {x} {y},{target}',
                         'dispatch alterzorder top,'+target]
            # Every interpolated field is a validated owned address or an integer. No shell.
            reply=self.call('--batch','; '.join(commands))
            if any(line.strip().lower()!='ok' for line in reply.splitlines() if line.strip()):
                raise RuntimeError('Hyprland did not accept all pet placement dispatches')
            observed=next((c for c in json.loads(self.call('-j','clients')) if c.get('address')==address and c.get('pid')==self.pid),None)
            if not observed or not observed.get('floating') or not observed.get('pinned') or observed.get('size')!=[w,h] or observed.get('at')!=[x,y]:
                raise RuntimeError('Pet floating/pinning/geometry was not observed')
            self.address=address; self.geometry=(width,height); self.size=(w,h)
            self.attempts.pop(key,None)
            self.status.update(configured=True,detail='Owned pet floats and is pinned across workspaces.')
        except (OSError,ValueError,TypeError,KeyError,StopIteration,RuntimeError,subprocess.TimeoutExpired) as e:
            self.status.update(configured=False,detail='Hyprland pet placement unavailable: '+str(e)[:250])
        return self.status
