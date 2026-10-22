import hashlib, os, shutil, time
from pathlib import Path
from .models import Action, Risk
from .registry import Tool
from .safety import PathPolicy

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(65536), b''): h.update(block)
    return h.hexdigest()

class Filesystem:
    def __init__(self, cfg, runtime):
        self.cfg, self.runtime, self.policy = cfg, runtime, PathPolicy(cfg.roots)
    def path(self, path, mutation=False): return self.policy.resolve(path, mutation)
    def inspect(self, path):
        p = self.path(path); s=p.stat()
        return {"path":str(p), "directory":p.is_dir(), "bytes":s.st_size, "modified":s.st_mtime}
    def list(self, path):
        p=self.path(path)
        rows=[]
        for q in sorted(p.iterdir(), key=lambda p:p.name.lower()):
            if len(rows)>=500: break
            try: rows.append(self.inspect(str(q)))
            except (PermissionError, OSError): continue
        return {"path":str(p), "entries":rows, "limit":500}
    def search(self, path, pattern):
        p=self.path(path); found=[]; count=0; started=time.monotonic()
        for root, dirs, files in os.walk(p, followlinks=False):
            self.runtime.check()
            dirs[:] = [d for d in dirs if self.allowed(Path(root)/d)]
            for name in dirs+files:
                q=Path(root)/name
                if pattern.casefold() in name.casefold() and self.allowed(q): found.append(str(q))
                count+=1
            if count>20000 or len(found)>=100 or time.monotonic()-started>3: break
        return {"matches":found[:100], "bounded":True}
    def search_roots(self,pattern):
        if not pattern.strip() or len(pattern)>200: raise ValueError('Use a search pattern of 1–200 characters')
        matches=[]; scanned=0; complete=True; started=time.monotonic(); unreadable=0
        def onerror(error):
            nonlocal complete,unreadable
            complete=False; unreadable+=1
        markers={'pyproject.toml','setup.py','requirements.txt'}
        for base in self.cfg.roots:
            base=self.path(str(base))
            if not base.is_dir():
                complete=False; unreadable+=1; continue
            for root,dirs,files in os.walk(base,followlinks=False,onerror=onerror):
                self.runtime.check()
                dirs[:]=[d for d in dirs if self.allowed(Path(root)/d)]
                if pattern=='python-projects':
                    if markers.intersection(files) or any(f.endswith('.py') for f in files): matches.append(root)
                else:
                    for name in dirs+files:
                        q=Path(root)/name
                        if pattern.casefold() in name.casefold() and self.allowed(q): matches.append(str(q))
                scanned+=len(dirs)+len(files)
                if scanned>=20000 or len(matches)>=100 or time.monotonic()-started>=3:
                    complete=False; break
            if not complete: break
        return {'matches':matches[:100],'complete':complete,'scope':'configured roots only','unreadable_roots_or_directories':unreadable,
                'criteria':'Python file or project marker' if pattern=='python-projects' else 'name contains '+pattern}
    def allowed(self, p):
        try: self.path(str(p)); return True
        except (PermissionError,OSError): return False
    def storage(self, path):
        p=self.path(path); sizes={}; largest=[]; count=0; started=time.monotonic(); complete=True
        for root, dirs, files in os.walk(p, followlinks=False):
            self.runtime.check()
            dirs[:]=[d for d in dirs if self.allowed(Path(root)/d)]
            for name in files:
                q=Path(root)/name
                if not self.allowed(q): continue
                try: size=q.stat().st_size
                except OSError: continue
                rel=q.relative_to(p); key=rel.parts[0]
                sizes[key]=sizes.get(key,0)+size
                largest.append({"path":str(q),"bytes":size})
                if len(largest)>200: largest=sorted(largest,key=lambda x:x['bytes'],reverse=True)[:20]
                count+=1
            if count>20000 or time.monotonic()-started>3: complete=False; break
        return {"path":str(p), "directories":sorted(sizes.items(),key=lambda x:x[1],reverse=True)[:10],
                "largest_files":sorted(largest,key=lambda x:x['bytes'],reverse=True)[:10],"complete":complete}
    def read(self,path):
        p=self.path(path)
        if p.stat().st_size>self.cfg.file_limit: raise ValueError("File exceeds read limit")
        return {"path":str(p),"content":p.read_text()}
    def create(self,path, content="", directory=False):
        p=self.path(path,True)
        if p.exists(): raise FileExistsError(str(p))
        if len(content.encode())>self.cfg.file_limit: raise ValueError('Write limit exceeded')
        if directory: p.mkdir(); inverse=Action("fs.undo_create",{"path":str(p),"expected_hash":"directory"})
        else:
            with p.open('x') as f: f.write(content)
            inverse=Action("fs.undo_create",{"path":str(p),"expected_hash":digest(p)})
        return {"path":str(p),"directory":directory,"hash":None if directory else hashlib.sha256(content.encode()).hexdigest(),"_inverse":inverse}
    def write(self,path,content):
        p=self.path(path,True)
        if not p.is_file(): raise ValueError("Write requires an existing regular file")
        if len(content.encode())>self.cfg.file_limit: raise ValueError("Write limit exceeded")
        # No overwrite undo: restoring arbitrary old content later is not a safe generic inverse.
        with p.open('w') as f: f.write(content)
        return {"path":str(p),"hash":hashlib.sha256(content.encode()).hexdigest()}
    def copy(self,source,destination):
        src=self.path(source); dst=self.path(destination,True)
        if not src.is_file() or src.stat().st_size>64*1024*1024: raise ValueError("Copy supports files up to 64 MiB")
        h=digest(src)
        with src.open('rb') as a, dst.open('xb') as b: shutil.copyfileobj(a,b)
        return {"path":str(dst),"hash":h,"_inverse":Action("fs.undo_create",{"path":str(dst),"expected_hash":h})}
    def move(self,source,destination):
        src=self.path(source,True); dst=self.path(destination,True)
        if not src.is_file() or src.stat().st_size>64*1024*1024: raise ValueError("Move supports regular files up to 64 MiB")
        if dst.exists(): raise FileExistsError(str(dst))
        if src.stat().st_dev!=dst.parent.stat().st_dev: raise ValueError("Cross-device move is unsupported")
        # Link with O_EXCL semantics; never overwrite a concurrent destination.
        h=digest(src)
        os.link(src,dst,follow_symlinks=False); src.unlink()
        return {"path":str(dst),"hash":h,"source":str(src),"_inverse":Action("fs.undo_move",{
            "source":str(dst),"destination":str(src),"expected_hash":h})}
    def delete(self,path):
        p=self.path(path,True)
        if p.is_dir(): p.rmdir() # deliberately empty directories only
        elif p.is_file(): p.unlink()
        else: raise ValueError("Not a regular file or empty directory")
        return {"path":str(p)}
    def undo_create(self,path,expected_hash):
        p=self.path(path,True)
        if expected_hash=="directory": p.rmdir()
        else:
            if p.stat().st_size>64*1024*1024: raise ValueError('File changed; undo refused')
            if digest(p)!=expected_hash: raise ValueError("File changed; undo refused")
            p.unlink()
        return {"path":str(p)}
    def undo_move(self,source,destination,expected_hash):
        if self.path(source).stat().st_size>64*1024*1024: raise ValueError('File changed; undo refused')
        if digest(self.path(source))!=expected_hash: raise ValueError("File changed; undo refused")
        result=self.move(source,destination); result.pop('_inverse',None); return result

    def register(self, registry):
        registry.register(Tool('files.search','Bounded name or Python-project search within configured roots',{'pattern':{'type':str}},Risk.READ_ONLY,self.search_roots))
        req=lambda t,**kw:{"type":t,**kw}
        specs=[
            ('inspect',{'path':req(str)},Risk.READ_ONLY,None),
            ('list',{'path':req(str)},Risk.READ_ONLY,None),
            ('search',{'path':req(str),'pattern':req(str)},Risk.READ_ONLY,None),
            ('storage',{'path':req(str)},Risk.READ_ONLY,None),
            ('read',{'path':req(str)},Risk.READ_ONLY,None),
            ('create',{'path':req(str),'content':req(str,required=False),'directory':req(bool,required=False)},Risk.MEDIUM,self.verify_file),
            ('write',{'path':req(str),'content':req(str)},Risk.MEDIUM,self.verify_file),
            ('copy',{'source':req(str),'destination':req(str)},Risk.MEDIUM,self.verify_file),
            ('move',{'source':req(str),'destination':req(str)},Risk.MEDIUM,self.verify_move),
            ('rename',{'source':req(str),'destination':req(str)},Risk.MEDIUM,self.verify_move),
            ('delete',{'path':req(str)},Risk.CRITICAL,self.verify_absent),
            ('undo_create',{'path':req(str),'expected_hash':req(str)},Risk.MEDIUM,self.verify_absent),
            ('undo_move',{'source':req(str),'destination':req(str),'expected_hash':req(str)},Risk.MEDIUM,self.verify_move)]
        for name,schema,risk,verifier in specs:
            fn=self.move if name=='rename' else getattr(self,name)
            registry.register(Tool('fs.'+name, name+' within configured roots',schema,risk,fn,verifier))
    def verify_file(self,args,result):
        p=self.path(result['path'])
        return p.is_dir() if result.get('directory') else p.is_file() and digest(p)==result['hash']
    def verify_move(self,args,result): return not self.path(args['source']).exists() and self.verify_file(args,result)
    def verify_absent(self,args,result): return not self.path(result['path']).exists()
