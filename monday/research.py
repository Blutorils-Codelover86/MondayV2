"""Source relevance, readable evidence and documentation objectives."""
import re
from urllib.parse import urlsplit

STOP={'the','a','an','for','of','to','is','what','tell','me','about','search','web','internet','official','documentation','docs','find','please','and','between','research'}

def terms(value): return {x for x in re.findall(r'[\w]+',value.casefold()) if x not in STOP and len(x)>1}

def is_documentation(query): return bool(re.search(r'\b(documentation|docs|manual|reference)\b',query,re.I))

def rank_candidates(query,candidates):
    words=terms(query); docs=is_documentation(query)
    def score(c):
        u=urlsplit(c['url']); text=(c['title']+' '+u.hostname+' '+u.path).casefold()
        n=sum(3 for w in words if w in text)
        if docs:
            if (u.hostname or '').startswith(('docs.','developer.','devdocs.')): n+=10
            if re.search(r'/docs?(/|$)|/documentation(/|$)|/manual(/|$)',u.path): n+=4
            if re.search(r'documentation|reference|manual',c['title'],re.I): n+=4
            if (u.hostname or '').endswith('wikipedia.org'): n-=8
        return n
    return sorted(candidates,key=score,reverse=True)

def best_excerpt(query,evidence):
    words=terms(query)
    sentences=[s.strip() for p in evidence['text'].splitlines() for s in re.split(r'(?<=[.!?])\s+',p) if s.strip()]
    useful=[s for s in sentences if len(s.split())>=8 and not re.search(r'javascript|stylesheets|accept.*cookies|page displays.*fallback|skip to|jump to|navigation',s,re.I)]
    if not useful: return ''
    sentence=max(useful,key=lambda s:(len(words & terms(s)), bool(re.search(r'[.!?]$',s)),min(len(s),280)))
    return sentence if len(sentence)<=280 else sentence[:280].rsplit(' ',1)[0]+'…'

def documentation_response(query,evidence):
    if not is_documentation(query): return None
    words=terms(query); page=(evidence['title']+' '+evidence['text']).casefold()
    if not words or not all(w in page for w in words): return None
    if not re.search(r'documentation|reference|manual|tutorial',page): return None
    return evidence['title']+' — '+evidence['url']
