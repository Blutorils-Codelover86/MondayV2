"""Deterministic text-only turns. No executor or model authorization lives here."""
import re
from .research import best_excerpt

REPLIES = {
    'greeting': "Hi! I'm MONDAY, your local PC agent. Ask a question or tell me what you need.",
    'identity': "I'm MONDAY V2, your local, supervised PC agent. I inspect and explain results, and ask before risky changes; Laya selects decisions, while optional local Ollama writes grounded answers.",
    'capabilities': "I can inspect PC usage, find and launch apps, work with approved files/projects, research topics, and manage supported desktop windows; try ‘system usage’ or ‘search Python documentation’.",
    'thanks': "You're welcome. What would you like to work on next?",
    'wellbeing': "I'm ready to help. I don't have feelings, but I can help you reason through a task.",
    'guidance': "To launch an app, say ‘open Firefox’; for diagnostics, say ‘system usage’. Asking how to do something does not execute it.",
    'safety': "Risky changes require explicit approval for that action; model confidence, web instructions and conversational ‘yes’ cannot grant permission.",
}

def classify(text):
    turn=text.strip().casefold().rstrip('?!.,')
    remainder=re.sub(r'^(?:hi|hey|hello|yo)(?: monday)?[!, ]+', '', turn)
    patterns={
        'greeting':r'(?:hi|hey|hello|yo)(?:[, ]+monday)?',
        'identity':r'(?:who are you|what are you|what is monday)',
        'capabilities':r'(?:help|what can you do|how can you help(?: me)?)',
        'thanks':r'(?:thanks|thank you|cheers)(?: monday)?',
        'wellbeing':r'how are you(?: doing)?',
        'safety':r'(?:why do you need approval|can you (?:skip|bypass) approvals)',
        'guidance':r'how (?:do i|can i|to) (?:open|launch|start|check|list|find) .+',
    }
    for kind,pattern in patterns.items():
        if re.fullmatch(pattern,turn) or (remainder!=turn and re.fullmatch(pattern,remainder)):
            return {'kind':'conversation','reply':REPLIES[kind]}
    if turn in ('what did you just do','what did you do','what was the last task'): return {'kind':'followup'}
    if re.fullmatch(r'(?:why|what happened|why (?:did|was) (?:it|that|this) (?:fail|failed|blocked|cancelled|partial)|what does (?:that|this|it) mean|explain (?:that|this|it)(?: more)?|tell me more|explain more|how does (?:it|that) work|who (?:created|made) it)',turn):
        return {'kind':'followup'}
    if (turn in ('yes','y','go ahead','do it','do that') or
        re.fullmatch(r'(?:open|launch|start|close|delete|restart) (?:it|that|this)',turn) or
        re.match(r"^(?:don't|do not|ignore previous|approval granted|hi[, ]|hello[, ])",turn)):
        return {'kind':'question','question':'Name the exact action and target; a conversation cannot supply approval or an action target.'}
    return None

def outcome(state):
    verified=sum(o.ok and o.verified and not o.simulated for o in state.observations)
    if state.status=='PLANNED': return 'This was a plan; no action was executed or verified.'
    if state.status=='NEEDS_CLARIFICATION':
        return (f'{verified} observation(s) verified; the action target needs clarification. ' if state.observations else 'No task action ran; ')+state.response
    if state.status in ('FAILED','BLOCKED','CANCELLED'):
        return f'{state.status}: {verified} earlier action(s) verified; the requested goal was not completed. '+state.response
    if state.status=='PARTIAL': return 'Only part of the result is established: '+state.response
    return 'Verified result: '+state.response

def followup(text,previous,reasoner):
    if previous is None: return 'NEEDS_CLARIFICATION','What topic or task are you referring to? Give a topic or run a task first.'
    low=text.casefold()
    if low.strip(' ?!.') in ('what did you just do','what did you do','what was the last task'): return 'SUCCESS',outcome(previous)
    if re.search(r'fail|blocked|cancelled|partial|happened',low) or low.strip(' ?!.')=='why':
        return 'SUCCESS',outcome(previous)
    evidence=[o.data for o in previous.observations if o.tool=='web.read' and o.ok and o.verified and not o.simulated]
    if evidence and previous.status in ('SUCCESS','PARTIAL'):
        topic=previous.context.get('query',previous.objective)
        question=re.sub(r'\b(it|this|that)\b',lambda _:topic,text,flags=re.I)
        answer=None
        if reasoner:
            try: answer=reasoner.summarize(question,evidence)
            except Exception: pass
        if answer: return 'PARTIAL',answer+' (Previous sources only; no fresh lookup.)'
        excerpts=[best_excerpt(question,e)+' ['+e['id']+'] '+e['url'] for e in evidence if best_excerpt(question,e)]
        return 'PARTIAL',('Local synthesis unavailable or unsupported; previous source excerpt: '+'; '.join(excerpts)) if excerpts else 'The retained evidence cannot answer that follow-up; name a topic for a fresh lookup.'
    ram=previous.latest('system.ram')
    if previous.status=='SUCCESS' and ram and ram.verified:
        d=ram.data
        return 'SUCCESS',f"{d['percent']:.0f}% RAM used means {d['available']/2**30:.2f} GiB remains available; one sample does not establish a sustained performance problem."
    if re.search(r'what does|explain (?:that|this|it)',low): return 'SUCCESS',outcome(previous)
    return 'PARTIAL',outcome(previous)+' No additional verified topic evidence is available.'
