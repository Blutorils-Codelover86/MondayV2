"""Killable, offline Laya worker; checkpoint must be explicitly present locally."""
import json, os, sys

def main():
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'
    payload=json.load(sys.stdin)
    import laya
    agent=laya.load(payload['path'],device='cpu')
    result=agent.predict(payload['state'],{'selection':{'type':'choice','instructions':'Select the most relevant candidate for the user objective.','criteria':payload['candidates']}})
    answer=result['answers']['selection']
    print(json.dumps({'choice':answer.get('choice'),'confidence':answer.get('confidence'),'calibrated':False}))
if __name__=='__main__': main()
