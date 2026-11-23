"""Interactive owned-session client. Uses normal Codex approvals; no bypass flags."""
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
from routing import decision
from store import database, get


class Client:
    def __init__(self,interactive=True):
        self.interactive=interactive
        self.proc=subprocess.Popen([shutil.which('codex'),'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,text=True,encoding='utf-8',bufsize=1)
        self.q=queue.Queue(); self.i=0; self.events=[]
        def read():
            for line in self.proc.stdout:
                try: self.q.put(json.loads(line))
                except ValueError: pass
        threading.Thread(target=read,daemon=True).start()
        self.request('initialize',{'clientInfo':{'name':'token-mods-companion','version':'1.1.0'}})
        self.send({'jsonrpc':'2.0','method':'initialized'})
    def send(self,value): self.proc.stdin.write(json.dumps(value)+'\n'); self.proc.stdin.flush()
    def request(self,method,params):
        self.i+=1; identity=self.i; self.send({'jsonrpc':'2.0','id':identity,'method':method,'params':params})
        while True:
            r=self.q.get(timeout=45)
            if r.get('id')==identity and 'method' not in r:
                if r.get('error'): raise ValueError(r['error'])
                return r['result']
            self.handle(r)
    def handle(self,r):
        if 'id' in r and 'method' in r:
            if not self.interactive:
                self.send({'jsonrpc':'2.0','id':r['id'],'error':{'code':-32000,'message':'This operation has no interactive approval handler'}}); return
            # This is the ordinary approval flow, surfaced to the human, never blanket-approved.
            print('\nCodex request:',json.dumps(r,ensure_ascii=False))
            answer=input('Enter the JSON response required by this request, or press Enter to reject: ')
            if answer: self.send({'jsonrpc':'2.0','id':r['id'],'result':json.loads(answer)})
            else: self.send({'jsonrpc':'2.0','id':r['id'],'error':{'code':-32000,'message':'User declined'}})
        else: self.events.append(r)
    def turn(self,thread,text,effort=None,model=None,timeout=300):
        p={'threadId':thread,'input':[{'type':'text','text':text}]}
        if effort: p['effort']=effort
        if model: p['model']=model
        result=self.request('turn/start',p); end=time.monotonic()+timeout
        while time.monotonic()<end:
            try: r=self.q.get(timeout=max(.01,end-time.monotonic()))
            except queue.Empty: break
            self.handle(r)
            if r.get('method')=='item/agentMessage/delta': print(r['params'].get('delta',''),end='',flush=True)
            if r.get('method')=='turn/completed': return r
        self.request('turn/interrupt',{'threadId':thread,'turnId':result['turn']['id']}); raise TimeoutError('Turn interrupted at client time limit')
    def close(self):
        self.proc.terminate()
        try: self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired: self.proc.kill(); self.proc.wait()


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--handoff',type=Path); p.add_argument('--cwd',default=str(Path.cwd())); a=p.parse_args()
    c=Client(); model=None; manual_effort=None
    try:
        t=c.request('thread/start',{'cwd':str(Path(a.cwd).resolve())}); identity=t['thread']['id']
        print('Owned Codex session:',identity,'Model:',t.get('model'),'Approval policy:',t.get('approvalPolicy'))
        print('Commands: :effort LEVEL, :effort auto, :model MODEL, :quit. Settings apply only to this owned session.')
        initial=a.handoff.read_text(encoding='utf-8') if a.handoff else None
        while True:
            text=initial or input('\nYou: '); initial=None
            if text==':quit': break
            if text.startswith(':effort '): manual_effort=text.split(' ',1)[1]; manual_effort=None if manual_effort=='auto' else manual_effort; continue
            if text.startswith(':model '): model=text.split(' ',1)[1]; continue
            with database() as db: auto=get(db,'effort',identity)=='auto'; judge_model=get(db,'judge_model',identity)
            selection=decision(text)
            if auto and not manual_effort and judge_model:
                from research import judge
                judged=judge(text,identity,judge_model)
                if judged.get('confidence') is not None and judged['confidence']>=0.6: selection=judged
                else: selection={'effort':None}
            effort=manual_effort or (selection['effort'] if auto else None)
            c.turn(identity,text,effort,model)
    except KeyboardInterrupt: print('\nInterrupted.')
    finally: c.close()


if __name__=='__main__': main()
