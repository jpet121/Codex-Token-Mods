"""Dependency-free local MCP stdio server (newline-delimited JSON-RPC)."""
import json
import sys
from tools_api import call

DESCRIPTIONS={
 'handoff_read':'Inspect a captured session handoff with tools, Git status and references; no export or model call. Use handoff for semantic draft or export.',
 'image_preview':'View a smaller local image in chat with original-coordinate mapping. Original is preserved; only an internal preview cache is written.',
 'mods_status':'Read Token Mods settings, sessions, events, installed-plugin inventory or help (the bundled skill text). For changes use mods.',
 'mods':'Control all nine Token Mods: list, on, off, hide, show, full, set, reset, sessions, events. Settings persist across projects.',
 'savings_proof':'Report provider input/cached/output usage, missing values and per-module estimated reductions and worker overhead. No causal or dollar claims.',
 'handoff':'Save a restartable chat draft. Explicit semantic action starts a paid independent worker; draft survives failure.',
 'effort_optimizer':'Suggest effort from task risk. Main-thread advice only. Manual settings win.',
 'model_router':'Plan or run an independent read-only worker. Run consumes account usage; explicit model and effort win. Never changes main-thread model.',
 'input_router':'Brief a local text/JSON/PDF source or retrieve full/range bytes. Worker action is explicit paid semantic reading. Exact source remains available.',
 'research_router':'Run bounded research with planning, quick/deep parallel workers, actual fetched sources, relevance checks, citations, date windows and saved reports. Consumes account usage.',
 'efficient_browser_use':'Create a smaller local image preview and coordinate map, preserving the original. No image-token savings claim.',
 'cache_clock':'Observe age since a model attempt and measured cache reads. Provider expiry unknown; keepwarm disabled.'}
PROPS={
 'action':{'type':'string'},'session':{'type':'string'},'module':{'type':'string'},
 'name':{'type':'string'},'value':{},'question':{'type':'string'},'model':{'type':'string'},
 'effort':{'type':'string'},'path':{'type':'string'},'target':{'type':'string'},'cwd':{'type':'string'},
 'offset':{'type':'integer'},'limit':{'type':'integer'},'page':{'type':'integer'},'pages':{'type':'integer'},
 'timeout':{'type':'integer'},'day':{'type':'string'},'scale':{'type':'number'},'minimum':{'type':'integer'},'full':{'type':'boolean'}}
PROPS.update(part={'type':'string','enum':['file','connector']},mode={'type':'string','enum':['auto','quick','deep']},parts={'type':'array','items':{'type':'string'},'minItems':2,'maxItems':4},since={'type':'string'},before={'type':'string'},after={'type':'string'})
PROPS['plugin']={'type':'string'}
FIELDS={
 'handoff_read':('session',),'image_preview':('path','session','scale','minimum','full'),
 'mods_status':('action','session'), 'mods':('action','session','module','name','value','part','plugin'),
 'savings_proof':('action','session','day','before','after'), 'handoff':('action','session','model','effort','timeout'),
 'effort_optimizer':('action','question','session','model','effort'),
 'model_router':('action','question','session','model','effort','cwd','timeout'),
 'input_router':('action','path','question','session','offset','limit','page','pages','model','effort','timeout'),
 'research_router':('action','question','session','model','effort','cwd','timeout','mode','parts','since'),
 'efficient_browser_use':('action','path','target','session','scale','minimum','full','question','model','effort','timeout'), 'cache_clock':('session',)}
ACTIONS={'mods_status':['list','sessions','events','inventory','help'],'mods':['list','on','off','hide','show','full','set','reset','sessions','events','inventory','plugin'],
 'input_router':['brief','range','full','worker'],'research_router':['run','deep'],'model_router':['plan','run','judge'],
 'effort_optimizer':['plan','judge'],'handoff':['draft','semantic'],'efficient_browser_use':['preview','describe'],'savings_proof':['report','compare']}


def schema(n):
    fields={k:dict(PROPS[k]) for k in FIELDS[n]}
    if n in ACTIONS: fields['action']['enum']=ACTIONS[n]
    return {'type':'object','properties':fields,'additionalProperties':False}


def dispatch(request):
    method=request['method']; p=request.get('params') or {}
    if method=='initialize':
        return dict(protocolVersion='2024-11-05',capabilities={'tools':{}},serverInfo={'name':'token-mods','version':'1.1.0'})
    if method=='ping': return {}
    if method=='tools/list':
        return {'tools':[dict(name=n,description=d,inputSchema=schema(n),
            annotations={'readOnlyHint':n in ('handoff_read','image_preview','mods_status','input_router','model_router','research_router','savings_proof','effort_optimizer','cache_clock'),'destructiveHint':False,'openWorldHint':n=='research_router'}) for n,d in DESCRIPTIONS.items()]}
    if method=='tools/call':
        try:
            result=call(p['name'],p.get('arguments') or {})
            content=[{'type':'text','text':json.dumps(result,ensure_ascii=False,indent=2)}]
            if p['name']=='image_preview':
                import base64
                from pathlib import Path
                content.append({'type':'image','mimeType':'image/png','data':base64.b64encode(Path(result['path']).read_bytes()).decode()})
            return {'content':content, 'isError':False}
        except Exception as error:
            return {'content':[{'type':'text','text':str(error)}],'isError':True}
    raise ValueError('Method not found: '+method)


def main():
    for line in sys.stdin:
        request = None
        try:
            request=json.loads(line)
            if 'id' not in request: continue
            response={'jsonrpc':'2.0','id':request['id'],'result':dispatch(request)}
        except Exception as error:
            response={'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,
                      'error':{'code':-32603,'message':str(error)}}
        print(json.dumps(response,ensure_ascii=True),flush=True)


if __name__=='__main__':
    sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8')
    main()
