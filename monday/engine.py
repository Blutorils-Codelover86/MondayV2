"""Objective recipes describe evidence dependencies; every next step uses observed state."""
import json, re, shlex, time, difflib
from pathlib import Path
from .models import Action, Decision, TaskState, Risk
from .runtime import Cancelled
from .research import rank_candidates, best_excerpt, documentation_response, is_documentation
from .conversation import classify, followup, outcome

class Interpreter:
    def __init__(self,cfg,registry,reasoner=None): self.cfg,self.registry,self.reasoner=cfg,registry,reasoner
    def understand(self,objective):
        s=objective.strip()
        low=s.casefold()
        # Structured tool invocation is first-class for complete, unambiguous control.
        if low.startswith('tool '):
            parts=s.split(maxsplit=2)
            if len(parts)<2: return {'kind':'question','question':'Which tool?'}
            try:
                args=json.loads(parts[2]) if len(parts)>2 else {}
                self.registry.validate(parts[1],args)
                return {'kind':'action','action':Action(parts[1],args)}
            except (ValueError,TypeError) as e: return {'kind':'question','question':str(e)}
        conversation=classify(s)
        if conversation: return conversation
        # Questions take precedence over diagnostic keywords; research only searches/reads.
        if re.match(r'^(?:what (?:is|are)|who |how (?:does|do)|why is|tell me about|explain )',low) and not re.match(r"why (?:isn't|is not) .+ building",low) and not re.search(r'\b(difference|differences|compare|differentiate)\b',low):
            if re.search(r'\b(it|that|this)\b',low): return {'kind':'followup'}
            query=re.sub(r'^(?:what (?:is|are) |tell me about |explain )','',s,flags=re.I).rstrip('?')
            return {'kind':'research','query':query,'subjects':[query]}
        if re.match(r'^(?:i think|i was|i said|could we|can we|should i|can i)\b',low):
            return {'kind':'question','question':'Are you asking for an explanation or an action? Name a concrete target for an action.'}
        # Explicit app/window commands outrank metric words in application titles.
        m=re.fullmatch(r'(?:open|launch|start) (.+)',s,re.I)
        if m:
            target=m[1]
            if target.startswith(('https://','http://')): return {'kind':'action','action':Action('browser.open',{'url':target})}
            if target.startswith(('/','~','.')): return {'kind':'action','action':Action('desktop.open_file',{'path':str(Path(target).expanduser().absolute())})}
            return {'kind':'launch','app':target}
        m=re.fullmatch(r'(focus|close) (?:window )?(.+)',s,re.I)
        if m and not re.fullmatch(r'close (?:process )?\d+',s,re.I):
            return {'kind':'window','operation':m[1].lower(),'target':m[2]}
        vocabulary=('official','documentation','storage','temperature','battery')
        def correct(match):
            word=match.group(0); candidates=difflib.get_close_matches(word.casefold(),vocabulary,n=1,cutoff=.85)
            return candidates[0] if candidates and len(word)>=5 else word
        if not re.match(r'(?:open|launch|start|create|write|delete|copy|move|rename|install|remove|restart|terminate|kill|close|build|test|get)\b',low):
            s=re.sub(r'\b[a-zA-Z]+\b',correct,s); low=s.casefold()
        search=re.fullmatch(r'(?:search(?: the)?(?: web| internet)?(?: for)?|look up) (.+)',s,re.I)
        if search and not re.match(r'process(?:es)?\b',search[1],re.I):
            return {'kind':'research','query':search[1],'subjects':[search[1]]}
        if is_documentation(s): return {'kind':'research','query':s,'subjects':[s]}
        if re.fullmatch(r'(?:system|pc|computer)(?: status| usage| health)',low): return {'kind':'overview'}
        if re.search(r'\b(slow|sluggish|performance)\b',low): return {'kind':'diagnose'}
        if re.search(r'(out of|low on|running out|free up).*(storage|space|disk)|storage.*(full|low)',low): return {'kind':'storage'}
        if re.search(r'\b(ram|memory)\b',low): return {'kind':'action','action':Action('system.ram')}
        for word,tool in [('cpu','cpu'),('gpu','gpu'),('graphics','gpu'),('storage','disk'),('disk','disk'),('temperature','temperatures'),('battery','battery'),('uptime','uptime'),('network','network'),('wi-fi','network'),('wifi','network'),('audio','audio'),('bluetooth','bluetooth'),('logs','logs')]:
            if word in low and not re.search(r'\b(restart|stop|disable|enable|fix)\b',low): return {'kind':'action','action':Action('system.'+tool)}
        m=re.fullmatch(r'(?:restart|inspect|check) (?:the )?([\w@.-]+)(?: service)?',low)
        if m and (m[1].endswith('.service') or 'service' in low or m[1]=='bluetooth'):
            name=m[1] if m[1].endswith('.service') else m[1]+'.service'
            return {'kind':'service','name':name,'restart':low.startswith('restart')}
        m=re.fullmatch(r'(?:terminate|kill|close) (?:process )?(\d+)',low)
        if m: return {'kind':'terminate','pid':int(m[1])}
        if re.search(r'\b(process|processes)\b',low):
            m=re.search(r'(?:find|search) (?:process(?:es)? )?(.+)',s,re.I)
            return {'kind':'action','action':Action('process.search',{'query':m[1] if m else ''})}
        if low.rstrip('?') in ('list windows','show windows','what windows are open'):
            return {'kind':'action','action':Action('desktop.windows')}
        m=re.fullmatch(r'(?:list|show) (?:files(?: in)? )?(.+)',s,re.I)
        if m and (m[1].startswith(('/','~','.'))): return {'kind':'action','action':Action('fs.list',{'path':str(Path(m[1]).expanduser().absolute())})}
        m=re.fullmatch(r'get (.+?) ready',s,re.I)
        if m: return {'kind':'project','name':m[1],'operation':'ready'}
        m=re.search(r"(?:why (?:isn't|is not) |build |test |inspect project |git status )(.*?)(?: building\??)?$",s,re.I)
        if m:
            name=m[1].rstrip('?').strip(); operation='build' if low.startswith(('why','build')) else 'test' if low.startswith('test') else 'inspect'
            return {'kind':'project','name':name,'operation':operation}
        m=re.fullmatch(r'(?:is |inspect package |install |remove )(\S+?)(?: installed\??)?',s,re.I)
        if m and ('package' in low or 'installed' in low or low.startswith(('install ','remove '))):
            return {'kind':'package','name':m[1],'operation':'install' if low.startswith('install') else 'remove' if low.startswith('remove') else 'inspect'}
        if low in ('upgrade system','system upgrade'): return {'kind':'package','name':'','operation':'upgrade'}
        m=re.search(r'https?://\S+',s)
        if m: return {'kind':'research','query':s,'url':m[0].rstrip('.,?')}
        found=re.fullmatch(r'find (.+)',s,re.I)
        if found: return {'kind':'research','query':found[1],'subjects':[found[1]]}
        if low.startswith(('what ','why ','how ','tell me ','differentiate ','compare ','difference ','research ','find information ')):
            query=re.sub(r'^(?:what is |tell me about |research |find information about )','',s,flags=re.I).rstrip('?')
            comparison=re.search(r'(?:between |compare )(.*?) (?:and|versus|vs\.?|with) (.*)',query,re.I)
            return {'kind':'research','query':query,'subjects':[comparison[1],comparison[2]] if comparison else [query]}
        if self.reasoner:
            proposal=self.reasoner.interpret(s,self.registry.describe())
            if isinstance(proposal,dict):
                if proposal.get('question'): return {'kind':'question','question':str(proposal['question'])}
                try:
                    self.registry.validate(proposal['tool'],proposal['arguments'])
                    return {'kind':'question','question':'A model suggested '+proposal['tool']+'; confirm a concrete request using tool '+proposal['tool']+' '+json.dumps(proposal['arguments'])+'. No action has run.'}
                except (ValueError,KeyError,TypeError): pass
        if len(s.split())>=2 and not re.match(r'(?:do|make|change|fix|set|enable|disable|delete|remove|create|write|copy|move|rename|send|buy|pay|update|run|restart|stop|terminate|kill|install|uninstall|open|launch|close|start)\b',low):
            return {'kind':'research','query':s,'subjects':[s]}
        return {'kind':'question','question':'What should I inspect or change? Try “system usage” or “search …”.'}

class DecisionEngine:
    def __init__(self,cfg,registry,reasoner=None,provider=None):
        self.cfg,self.registry,self.reasoner,self.provider=cfg,registry,reasoner,provider
        self.interpreter=Interpreter(cfg,registry,reasoner)
    def next(self,state):
        ctx=state.context
        if not ctx: ctx.update(self.interpreter.understand(state.objective))
        snapshot=state.snapshot()
        def act(tool,args={},reason='Observe the state needed for this objective',expected='Tool observation satisfies its verification contract'):
            action=Action(tool,args)
            risk=self.registry.get(tool).risk
            return Decision(state.objective,snapshot,action,reason,expected,'All required observations are verified',risk)
        def done(response,status='SUCCESS'):
            return Decision(state.objective,snapshot,None,'Required observations have been assessed','', 'Objective resolved',response=response,status=status)
        if state.observations and not state.observations[-1].ok:
            o=state.observations[-1]
            retry_read=ctx.get('kind')=='research' and o.tool=='web.read' and not ctx.get('url')
            if retry_read:
                return self.research_next(state,snapshot)
            if o.tool=='project.run' and isinstance(o.data,dict) and o.data.get('diagnostics'):
                return done('Build failed: '+o.data['diagnostics'][0], 'FAILED')
            if o.tool in ('browser.open','desktop.open_file') and isinstance(o.data,dict) and o.data.get('exit_code')==0:
                return done('Opening was requested; the visible result could not be verified.', 'PARTIAL')
            return done("Couldn't complete the objective: "+o.error, (o.data or {}).get('status','FAILED') if isinstance(o.data,dict) else 'FAILED')
        kind=ctx['kind']
        if kind=='conversation': return done(ctx['reply'])
        if kind=='question': return done(ctx['question'],'NEEDS_CLARIFICATION')
        if kind=='action':
            a=ctx['action']
            if not state.observations: return act(a.tool,a.arguments)
            return done(self.describe(state.observations[-1]))
        if kind=='overview':
            for tool in ('system.cpu','system.ram','system.disk'):
                if not state.latest(tool): return act(tool)
            cpu=state.latest('system.cpu').data; ram=state.latest('system.ram').data; disk=state.latest('system.disk').data
            return done(f"CPU {cpu['percent']:.0f}%; RAM {ram['percent']:.0f}%; storage {disk['percent']:.0f}% used ({disk['free']/2**30:.1f} GiB free).")
        if kind=='diagnose':
            for tool in ('system.cpu','system.ram','system.disk','process.search'):
                if not state.latest(tool): return act(tool)
            cpu=state.latest('system.cpu').data; ram=state.latest('system.ram').data; procs=state.latest('process.search').data
            top=procs['processes'][0] if procs['processes'] else None
            cause='RAM is under pressure' if ram['percent']>=85 else 'CPU usage is high' if cpu['percent']>=80 else 'No sustained bottleneck was established from this sample'
            return done(cause+(f"; {top['name']} uses the most RAM ({top['rss']/2**20:.0f} MiB)." if top else '.'))
        if kind=='storage':
            if not state.latest('system.disk'): return act('system.disk')
            if not state.latest('fs.storage'):
                root=next((r for r in self.cfg.roots if r.name=='Downloads' and r.is_dir()),next((r for r in self.cfg.roots if r.is_dir()),None))
                if not root: return done('Disk inspected; configure a readable folder to find storage candidates.','PARTIAL')
                return act('fs.storage',{'path':str(root)},'Find large files without deleting anything')
            d=state.latest('fs.storage').data
            if not d['largest_files']: return done('No large files were found in the scanned folder.')
            largest=d['largest_files'][0]
            return done(f"{Path(largest['path']).name} uses {largest['bytes']/2**30:.2f} GiB in {d['path']}"+ (' (partial scan).' if not d['complete'] else '; no files were deleted.'))
        if kind=='launch':
            if not state.latest('app.discover'): return act('app.discover')
            if not state.latest('app.launch'): return act('app.launch',{'app':ctx['app']})
            return done(self.describe(state.latest('app.launch')))
        if kind=='window':
            if not state.latest('desktop.windows'): return act('desktop.windows')
            windows=state.latest('desktop.windows').data['windows']; target=ctx['target'].casefold()
            matches=[w for w in windows if target in (str(w.get('address',w.get('id',''))).casefold(),w.get('title','').casefold(),w.get('class','').casefold())]
            if not matches:
                matches=[w for w in windows if target in w.get('title','').casefold() or target in w.get('class','').casefold()]
            if len(matches)!=1: return done('Which window? '+('Several match; specify a title or observed ID.' if matches else 'No observed window matches that target.'),'NEEDS_CLARIFICATION')
            tool='desktop.'+ctx['operation']
            if not state.latest(tool): return act(tool,{'window_id':str(matches[0].get('address',matches[0].get('id')))})
            return done('Window '+ctx['operation']+' was verified for '+ctx['target']+'.')
        if kind=='service':
            if not state.latest('service.inspect'): return act('service.inspect',{'name':ctx['name']})
            if ctx['restart'] and not state.latest('service.restart'): return act('service.restart',{'name':ctx['name']},'Restart only the named service after approval')
            return done(self.describe(state.observations[-1]))
        if kind=='terminate':
            if not state.latest('process.inspect'): return act('process.inspect',{'pid':ctx['pid']})
            if not state.latest('process.terminate'):
                p=state.latest('process.inspect').data
                return act('process.terminate',{'pid':p['pid'],'create_time':p['create_time']},'Terminate the observed PID only after explicit approval')
            return done(f"Process {ctx['pid']} terminated; its exit was verified.")
        if kind=='project':
            if not state.latest('project.locate'): return act('project.locate',{'name':ctx['name']})
            p=state.latest('project.locate').data; op=ctx['operation']; path=p['path']
            if p['git'] and not state.latest('project.git'): return act('project.git',{'path':path,'operation':'status'})
            if op in ('build','test'):
                if not state.latest('project.run'): return act('project.run',{'path':path,'operation':op},'Project scripts execute code and require approval')
                return done(f"{ctx['name']} {op} passed (exit status 0).")
            if op=='ready':
                if not state.latest('app.discover'): return act('app.discover')
                if not state.latest('project.editor'):
                    apps=state.latest('app.discover').data['applications']; editors=[a for a in apps if re.search(r'code|kate|zed|sublime',a['name'],re.I)]
                    if not editors: return done('No supported editor was discovered; which application should I use?','NEEDS_CLARIFICATION')
                    return act('project.editor',{'path':path,'app':editors[0]['id']})
                if not state.latest('project.terminal'): return act('project.terminal',{'path':path})
                return done(f"{ctx['name']} editor and terminal processes are running at {path}.")
            return done(f"{ctx['name']} is a {p['type']} project at {path}.")
        if kind=='package':
            op=ctx['operation']
            if op=='inspect':
                if not state.latest('package.inspect'): return act('package.inspect',{'name':ctx['name']})
                found=state.latest('package.inspect').data['found']; return done(ctx['name']+(' is installed.' if found else " isn't installed."))
            if not state.latest('package.operate'): return act('package.operate',{'operation':op,'name':ctx['name']})
            return done('Package operation verified.')
        if kind=='research': return self.research_next(state,snapshot)
        return done('I need a more specific objective.','NEEDS_CLARIFICATION')

    def research_next(self,state,snapshot):
        ctx=state.context
        def act(tool,args,reason):
            return Decision(state.objective,snapshot,Action(tool,args),reason,'Relevant readable evidence','Read required sources',Risk.READ_ONLY)
        def done(response,status='PARTIAL'):
            return Decision(state.objective,snapshot,None,'Evidence assessed','','Objective resolved',response=response,status=status)
        if ctx.get('url'):
            if not state.latest('web.read'): return act('web.read',{'url':ctx['url']},'Read the requested page')
        else:
            subjects=ctx.get('subjects',[ctx['query']]); index=ctx.setdefault('index',0)
            searches=[o for o in state.observations if o.tool=='web.search']
            pages=[o for o in state.observations if o.tool=='web.read' and o.ok]
            if index<len(subjects):
                if len(searches)<=index: return act('web.search',{'query':subjects[index]},'Find sources relevant to the objective')
                if len(pages)<=index:
                    tried=ctx.setdefault('tried',{}).setdefault(str(index),[])
                    candidates=rank_candidates(subjects[index],searches[index].data['candidates'])
                    candidates=[c for c in candidates if c['url'] not in tried]
                    if not candidates or len(tried)>=3:
                        return done('Could not read a relevant source; try a direct page URL.','FAILED')
                    chosen=candidates[0]
                    if self.provider and not tried and len(candidates)>1 and not is_documentation(subjects[index]):
                        selected=self.provider.choose(subjects[index],{str(i):a['title'] for i,a in enumerate(candidates)})
                        if selected is not None: chosen=candidates[int(selected)]
                    tried.append(chosen['url'])
                    return act('web.read',{'url':chosen['url']},'Read the best relevant source; try another if it fails')
                ctx['index']+=1
                return self.research_next(state,snapshot)
        evidence=[o.data for o in state.observations if o.tool=='web.read' and o.ok]
        if not evidence: return done('No readable evidence was found.','FAILED')
        documentation=documentation_response(ctx['query'],evidence[0])
        if documentation: return done(documentation,'SUCCESS')
        try: answer=self.reasoner.summarize(state.objective,evidence) if self.reasoner else None
        except Exception: answer=None
        if answer: return done(answer)
        excerpts=[]
        for e in evidence:
            excerpt=best_excerpt(ctx['query'],e)
            if excerpt: excerpts.append(excerpt+' ['+e['id']+'] '+e['url'])
        if not excerpts: return done('The page did not contain useful answer text; source: '+evidence[0]['url'])
        fallback=any(o.tool=='web.search' and o.data.get('fallback') for o in state.observations)
        prefix='Web search unavailable; Wikipedia source excerpt' if fallback else 'Source excerpt'
        return done(prefix+('s' if len(excerpts)>1 else '')+': '+'; '.join(excerpts))

    def conditional_workflow(self,state):
        c=state.context; k=c.get('kind')
        recipes={'overview':['system.cpu','system.ram','system.disk'],'diagnose':['system.cpu','system.ram','system.disk','process.search'],
                 'storage':['system.disk','fs.storage'], 'launch':['app.discover','app.launch'],
                 'terminate':['process.inspect','process.terminate'],
                 'service':['service.inspect']+(['service.restart'] if c.get('restart') else []),
                 'research':['web.read'] if c.get('url') else ['web.search','web.read'],
                 'project':['project.locate','project.git (if Git)']+(['app.discover','project.editor','project.terminal'] if c.get('operation')=='ready' else ['project.run'] if c.get('operation') in ('build','test') else []),
                 'package':['package.inspect' if c.get('operation')=='inspect' else 'package.operate']}
        return recipes.get(k,[c['action'].tool] if 'action' in c else [])

    def describe(self,o):
        d=o.data; t=o.tool
        if t=='desktop.windows':
            titles=[w.get('title') or w.get('class') or str(w.get('address',w.get('id'))) for w in d['windows']]
            return f"Observed {len(titles)} windows: "+(', '.join(titles[:8]) or 'none')+'.'
        if t in ('desktop.focus','desktop.close'): return 'Window '+d['operation']+' was verified for '+d['window_id']+'.'
        if t=='system.ram': return f"RAM is {d['percent']:.0f}% used; {d['available']/2**30:.2f} GiB is available."
        if t=='system.cpu': return f"CPU is {d['percent']:.0f}% busy; load averages are "+', '.join(f'{x:.2f}' for x in d['load'])+'.'
        if t=='system.gpu':
            devices=d['devices']; readings=[]
            for gpu in devices:
                label=gpu.get('name',gpu.get('vendor','GPU')+' '+gpu.get('driver',''))
                value=gpu.get('busy_percent')
                readings.append(label+(f" is {value:.1f}% busy" if value is not None else ': utilization is unavailable'))
            return '; '.join(readings)+(' (accessible user clients).' if any(g.get('engines_percent') for g in devices) else '.') if readings else 'No readable GPU telemetry was found.'
        if t=='system.disk': return f"Disk is {d['percent']:.0f}% used; {d['free']/2**30:.1f} GiB is free."
        if t=='system.battery':
            return 'Battery information is unavailable.' if d.get('available') is False else f"Battery is {d['percent']:.0f}%; {'plugged in' if d['power_plugged'] else 'running on battery'}."
        if t=='system.temperatures':
            readings=[(k,x['current']) for k,values in d.items() for x in values if x['current'] is not None]
            return ('Highest sensor reading: '+max(readings,key=lambda x:x[1])[0]+f" {max(x[1] for x in readings):.0f}°C.") if readings else 'Temperature sensors are unavailable.'
        if t=='system.network':
            active=[k for k,v in d['state'].items() if v['isup'] and k!='lo']
            return 'Active network interfaces: '+(', '.join(active) or 'none')+'; connectivity beyond the host was not tested.'
        if t=='system.bluetooth':
            try:
                devices=json.loads(d['stdout']).get('rfkilldevices',[]); bt=[x for x in devices if x['type']=='bluetooth']
                return '; '.join(f"Bluetooth {x['device']}: software {x['soft']}, hardware {x['hard']}" for x in bt)+'.' if bt else 'No Bluetooth adapter was observed.'
            except (ValueError,KeyError): return 'Bluetooth state could not be decoded.'
        if t=='system.audio': return 'Audio server responded; use “explain” for devices and streams.'
        if t=='system.uptime': return f"Uptime is {d['seconds']/3600:.1f} hours."
        if t=='app.launch': return d['app']+' has a running process; launch was observed.'
        if t.startswith('fs.'):
            if t=='fs.list':
                names=[e.get('name','') if isinstance(e,dict) else str(e) for e in d['entries'][:8]]
                return f"Found {len(d['entries'])} entries in {d['path']}."+(' Entries: '+', '.join(names)+'.' if names else '')
            if t=='fs.search': return f"Found {len(d['matches'])} matching paths."
            if t=='fs.read': return ' '.join(d['content'].split())[:500] or 'File is empty.'
            return t.split('.')[1].capitalize()+' verified for '+d.get('path','the requested path')+'.'
        if t.startswith('service.'):
            return 'Service state: '+'; '.join(d['stdout'].splitlines())+'.'
        if t=='web.search':
            first=d['candidates'][0]
            return f"Found {len(d['candidates'])} results via {d['provider']}; first: {first['title']} {first['url']}"+(' (general search unavailable; fallback used).' if d.get('fallback') else '.')
        if t=='package.inspect': return d['name']+(' is installed.' if d['found'] else " isn't installed.")
        if t=='process.search':
            p=d['processes']; return f"Found {d['count']} processes"+(f"; {p[0]['name']} uses the most RAM ({p[0]['rss']/2**20:.0f} MiB)." if p else '.')
        if isinstance(d,dict) and d.get('stdout'): return ' '.join(d['stdout'].split())[:500]
        return t+' inspected: '+json.dumps(d,default=str,separators=(',',':'))[:500]

class Agent:
    def __init__(self,engine,gateway,audit,progress=None):
        self.engine,self.gateway,self.audit,self.progress=engine,gateway,audit,progress
        self.last_task=None
    def run(self,objective):
        state=TaskState(objective)
        try:
            self.gateway.runtime.check()
            state.context.update(self.engine.interpreter.understand(objective))
            for _ in range(self.engine.cfg.max_steps):
                self.gateway.runtime.check()
                if time.monotonic()-state.started>self.engine.cfg.task_timeout: raise TimeoutError('Task time budget exhausted')
                if state.context.get('kind')=='followup':
                    status,response=('PLANNED','Text-only follow-up planned; no tools or model invoked.') if self.gateway.dry_run else followup(objective,self.last_task,self.engine.reasoner)
                    d=Decision(objective,state.snapshot(),None,'Explain selected prior observations','','No new execution',response=response,status=status)
                else: d=self.engine.next(state)
                state.decisions.append(d)
                if d.next_action is None:
                    state.status,state.response=d.status,d.response; break
                # Reject repeated identical action after success: provider loops never run indefinitely.
                if any(old.next_action==d.next_action for old in state.decisions[:-1]):
                    state.status,state.response='FAILED','Decision repeated without progress.'; break
                if self.progress: self.progress(d)
                o=self.gateway.perform(d.next_action); state.observations.append(o)
                if o.simulated:
                    workflow=" → ".join(self.engine.conditional_workflow(state))
                    state.status,state.response='PLANNED',f"Conditional plan: {workflow}; next arguments {d.next_action.arguments}; execution and verification are pending."; break
            else: state.status,state.response='PARTIAL','Step budget exhausted; objective is incomplete.'
        except Cancelled as e:
            state.status,state.response='CANCELLED',str(e)
        except KeyboardInterrupt:
            self.gateway.runtime.stop.set(); state.status,state.response='CANCELLED','Stopped.'
        except Exception as e:
            state.status,state.response='FAILED',str(e)
        state.response=' '.join(state.response.split())
        if state.status in ('FAILED','BLOCKED','CANCELLED') and state.observations:
            count=sum(o.verified and o.ok for o in state.observations)
            state.response+=f' ({count} earlier action(s) verified; requested goal incomplete.)'
        self.audit.save(state)
        if state.context.get('kind') not in ('conversation','followup','question'):
            from copy import deepcopy
            self.last_task=deepcopy(state)
        return state
