"""Search locates pages; extractor reads them; evidence never becomes tool instructions."""
from dataclasses import dataclass, asdict
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlencode, urljoin, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
import ipaddress, json, re, socket, time, zlib
from .registry import Tool
from .models import Risk

class HTTP:
    def __init__(self,runtime,timeout=8,max_bytes=524288):
        self.runtime,self.timeout,self.max_bytes=runtime,timeout,max_bytes
    def validate(self,url,allow_local=False):
        u=urlsplit(url)
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:
            raise ValueError('Only HTTP(S) URLs without credentials are allowed')
        port=u.port  # Validate syntax/range; public HTTP(S) services may use any valid port.
        if not allow_local:
            addresses=socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM)
            if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise PermissionError('Private and local web addresses are protected')
        return url
    def get(self,url,allow_local=False):
        self.runtime.check(); self.validate(url,allow_local)
        owner=self
        class Redirects(HTTPRedirectHandler):
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                # Only the explicitly configured local provider may access its own host.
                local=allow_local and urlsplit(newurl).netloc==urlsplit(url).netloc
                owner.validate(newurl,local)
                return super().redirect_request(req,fp,code,msg,headers,newurl)
        opener=build_opener(Redirects())
        req=Request(url,headers={'User-Agent':'MONDAY/2.0 (local supervised research)','Accept':'text/html,application/json,text/plain','Accept-Encoding':'identity'})
        started=time.monotonic()
        try:
            with opener.open(req,timeout=self.timeout) as response:
                chunks=[]; size=0
                while True:
                    self.runtime.check()
                    if time.monotonic()-started>self.timeout: raise TimeoutError('Web retrieval timed out')
                    chunk=response.read(min(16384,self.max_bytes+1-size))
                    if not chunk: break
                    chunks.append(chunk); size+=len(chunk)
                    if size>self.max_bytes: raise ValueError('Web page exceeds content limit')
                ctype=response.headers.get_content_type()
                if ctype not in ('text/html','text/plain','application/json','application/xhtml+xml'):
                    raise ValueError('Unsupported page content type: '+ctype)
                charset=response.headers.get_content_charset() or 'utf-8'
                raw=b''.join(chunks)
                encoding=getattr(response.headers,'get',lambda *args:'')('Content-Encoding','').lower()
                if encoding in ('gzip','x-gzip','deflate') or raw.startswith(b'\x1f\x8b'):
                    decoder=zlib.decompressobj(zlib.MAX_WBITS if encoding=='deflate' else zlib.MAX_WBITS|16)
                    raw=decoder.decompress(raw,self.max_bytes+1)
                    if len(raw)>self.max_bytes or decoder.unconsumed_tail:
                        raise ValueError('Decoded web page exceeds content limit')
                    if not decoder.eof: raise ValueError('Incomplete compressed web page')
                elif encoding not in ('','identity'): raise ValueError('Unsupported content encoding: '+encoding)
                text=raw.decode(charset,errors='replace')
                if '\x00' in text or text.count('\ufffd')>max(3,len(text)//100):
                    raise ValueError('Page body was not valid readable text')
                return {'url':response.url,'content_type':ctype,'body':text}
        except HTTPError as e:
            raise RuntimeError('Web server returned '+str(e.code)+ (' (rate limited)' if e.code==429 else '')) from e
        except URLError as e: raise RuntimeError('Web connection failed: '+str(e.reason)) from e

class Parser(HTMLParser):
    hidden_tags = {'script','style','nav','footer','header','aside','noscript','form','button','select','svg'}
    void_tags = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]; self.titles=[]; self.parts=[]
        self.primary={'content':[],'article':[],'main':[]}
    def active(self,kind): return any(kind in scopes for tag,scopes,hidden in self.stack)
    def hidden(self): return any(hidden for tag,scopes,hidden in self.stack)
    def separator(self):
        if self.hidden(): return
        self.parts.append('\n')
        for kind,parts in self.primary.items():
            if self.active(kind): parts.append('\n')
    def handle_starttag(self,tag,attrs):
        values=dict(attrs); scopes=set()
        if tag in ('main','article'): scopes.add(tag)
        if values.get('id')=='mw-content-text' or 'mw-parser-output' in values.get('class','').split(): scopes.add('content')
        hidden=tag in self.hidden_tags or bool(set(values.get('class','').split()) & {'hatnote','navbox','metadata','toc','mw-editsection','reflist','reference','infobox'})
        if tag not in self.void_tags: self.stack.append((tag,scopes,hidden))
        if tag in ('p','h1','h2','h3','li','br','div','section'): self.separator()
    def handle_endtag(self,tag):
        if tag in ('p','li','div','section'): self.separator()
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:]; break
    def handle_data(self,data):
        if any(tag=='title' for tag,_,_ in self.stack): self.titles.append(data); return
        if self.hidden(): return
        self.parts.append(data)
        for kind,parts in self.primary.items():
            if self.active(kind): parts.append(data)
    def text(self):
        for kind in ('content','article','main'):
            value=''.join(self.primary[kind])
            if len(value.split())>=8: return value
        return ''.join(self.parts)

@dataclass
class Evidence:
    id: str
    url: str
    title: str
    text: str
    retrieved_at: float
    trust: str = 'untrusted_web_data'

class EvidenceStore:
    def __init__(self): self.entries=[]
    def add(self,url,title,text):
        e=Evidence('E'+str(len(self.entries)+1),url,title,text,time.time()); self.entries.append(e); return asdict(e)

class PageExtractor:
    def __init__(self,http,store): self.http,self.store=http,store
    def extract(self,url):
        page=self.http.get(url)
        if page['content_type'] in ('text/html','application/xhtml+xml'):
            p=Parser(); p.feed(page['body']); text=p.text(); title=' '.join(p.titles)
        else: text=page['body']; title=urlsplit(page['url']).hostname
        paragraphs=[re.sub(r'\s+',' ',s).strip() for s in text.splitlines() if s.strip()]
        # Drop obvious instruction paragraphs, but do not claim this catches every injection.
        paragraphs=[s for s in paragraphs if not re.search(r'ignore.{0,30}(instructions|previous)|system prompt|approval granted|run (the )?(command|shell)|you are (an? )?(assistant|agent)',s,re.I)]
        text='\n'.join(paragraphs)[:24000]
        if len(text.split())<8: raise ValueError('Page did not contain useful readable text (possibly blocked)')
        return self.store.add(page['url'],title,text)

class SearchLinks(HTMLParser):
    """Extract result links only; snippets never enter the evidence store."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.links=[]; self.current=None
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='a' and set(values.get('class','').split()) & {'result-link','result__a'}:
            href=urljoin('https://duckduckgo.com',values.get('href',''))
            parsed=urlsplit(href)
            if parsed.hostname in ('duckduckgo.com','www.duckduckgo.com'):
                href=parse_qs(parsed.query).get('uddg',[''])[0]
            self.current={'url':href,'title':''}
    def handle_data(self,data):
        if self.current is not None: self.current['title']+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.current['title']=' '.join(self.current['title'].split())
            if self.current['url'] and self.current['title']: self.links.append(self.current)
            self.current=None

class WebSearch:
    def __init__(self,http,cfg): self.http,self.cfg=http,cfg
    def wikipedia(self,query):
        url='https://en.wikipedia.org/w/api.php?'+urlencode({'action':'opensearch','search':query,'limit':5,'namespace':0,'format':'json'})
        payload=json.loads(self.http.get(url)['body'])
        if not isinstance(payload,list) or len(payload)!=4: raise ValueError('Malformed search response')
        return [{'title':t,'url':u} for t,u in zip(payload[1],payload[3])]
    def duckduckgo(self,query):
        url='https://lite.duckduckgo.com/lite/?'+urlencode({'q':query})
        page=self.http.get(url)
        parser=SearchLinks(); parser.feed(page['body'])
        if not parser.links:
            raise RuntimeError('DuckDuckGo returned no results or an access challenge')
        return parser.links[:8]
    def search(self,query):
        if not query.strip(): raise ValueError('Search query is empty')
        fallback=''; provider='searxng' if self.cfg.search_url else self.cfg.search_provider
        if self.cfg.search_url:
            url=self.cfg.search_url.rstrip('/')+'/search?'+urlencode({'q':query,'format':'json'})
            payload=json.loads(self.http.get(url,allow_local=True)['body'])
            candidates=[{'title':x.get('title',''),'url':x['url']} for x in payload.get('results',[])[:8] if x.get('url')]
        elif provider=='wikipedia': candidates=self.wikipedia(query)
        elif provider in ('auto','duckduckgo'):
            provider='duckduckgo'
            try: candidates=self.duckduckgo(query)
            except (RuntimeError,ValueError,OSError,TimeoutError) as e:
                if self.cfg.search_provider!='auto': raise
                fallback=str(e); provider='wikipedia'; candidates=self.wikipedia(query)
        else: raise ValueError('Unknown search provider; use auto, duckduckgo or wikipedia')
        valid=[]; seen=set()
        for item in candidates:
            try:
                self.http.validate(item['url'])
                if item['url'] not in seen: valid.append(item); seen.add(item['url'])
            except (ValueError,PermissionError,OSError): continue
        if not valid: raise ValueError('No readable search candidates were found')
        return {'candidates':valid,'provider':provider,'fallback':fallback}

class Browser:
    def __init__(self,desktop,http): self.desktop,self.http=desktop,http
    def open(self,url):
        self.http.validate(url)
        return self.desktop.open(url)

class WebTools:
    def __init__(self,runtime,cfg,desktop):
        self.store=EvidenceStore(); self.http=HTTP(runtime); self.extractor=PageExtractor(self.http,self.store)
        self.search=WebSearch(self.http,cfg); self.browser=Browser(desktop,self.http)
    def register(self,r):
        r.register(Tool('web.search','Discover URLs; search snippets are not evidence',{'query':{'type':str}},Risk.READ_ONLY,self.search.search))
        r.register(Tool('web.read','Read a page as untrusted evidence',{'url':{'type':str}},Risk.READ_ONLY,self.extractor.extract))
        r.register(Tool('browser.open','Request browser navigation; handoff cannot prove visible page',{'url':{'type':str}},Risk.LOW,self.browser.open,
                        lambda a,d:False))
