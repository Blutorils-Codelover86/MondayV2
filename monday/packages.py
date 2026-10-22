import re
from .registry import Tool
from .models import Risk

class Packages:
    def __init__(self,runtime): self.runtime=runtime; self.pending=None
    def valid(self,name):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9@+_.-]{0,100}',name): raise ValueError('Invalid package name')
    def inspect(self,name,installed=True):
        self.valid(name)
        r=self.runtime.run(['pacman','-Qi' if installed else '-Si',name])
        return {**r,'name':name,'found':r['exit_code']==0}
    def preview(self,args):
        operation=args['operation']; name=args.get('name','')
        if operation!='upgrade': self.valid(name)
        flag={'install':'-Sp','remove':'-Rp','upgrade':'-Sup'}[operation]
        r=self.runtime.run(['pacman',flag,'--print-format','%n %v',*([name] if name else [])])
        if r['exit_code']: raise RuntimeError(r['stderr'] or 'Package transaction cannot be resolved')
        if r.get('truncated'): raise ValueError('Package preview exceeds output limit; refusing incomplete approval')
        self.pending=(dict(args),r['stdout'])
        return 'Resolved package transaction'+(' from current pacman databases' if operation=='upgrade' else '')+': '+', '.join(r['stdout'].splitlines())
    def operate(self,operation,name=''):
        args={'operation':operation}
        if name: args['name']=name
        if not self.pending: raise PermissionError('No approved transaction preview')
        previous=self.pending; self.preview(args)
        if previous[1]!=self.pending[1]: raise ValueError('Package transaction changed; approval must be renewed')
        if operation!='upgrade': self.valid(name)
        flags={'install':['-S','--needed'],'remove':['-R'],'upgrade':['-Su']}
        # Confirmation covers the displayed resolver output; pkexec provides OS authentication.
        r=self.runtime.run(['pkexec','pacman',*flags[operation],'--noconfirm',*([name] if name else [])],timeout=120)
        if r['exit_code']: raise RuntimeError(r['stderr'] or 'Package operation failed or administrator permission was denied')
        self.pending=None
        return {**r,'operation':operation,'name':name,'transaction':previous[1]}
    def verify(self,args,result):
        for line in result['transaction'].splitlines():
            if not line.strip(): continue
            name=line.split()[0]; self.valid(name)
            r=self.runtime.run(['pacman','-Q',name])
            if result['operation']=='remove':
                if r['exit_code']==0: return False
            elif r['exit_code']!=0 or r['stdout'].strip()!=line.strip(): return False
        return result['exit_code']==0
    def register(self,r):
        r.register(Tool('package.inspect','Inspect installed or repository Arch package',{'name':{'type':str},'installed':{'type':bool,'required':False}},Risk.READ_ONLY,self.inspect))
        r.register(Tool('package.operate','Apply approved, previewed package transaction through pkexec',{'operation':{'type':str,'enum':['install','remove','upgrade']},'name':{'type':str,'required':False}},Risk.HIGH,self.operate,self.verify,self.preview))
