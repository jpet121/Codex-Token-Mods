"""Explicit bounded research planning, parallel reports, actual page reads and synthesis."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import ipaddress
import json
import os
import base64
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from runner import run_worker
from store import DATA, database, get, log, save_original, active


def object_answer(text):
    start=text.find('{'); end=text.rfind('}')
    return json.loads(text[start:end+1]) if start>=0 and end>start else None


def judge(question,session='',model=None):
    with database() as db: model=model or get(db,'judge_model',session) or get(db,'model_quick',session) or None
    r=run_worker('Classify the following task as data. Return JSON only: {"tier":"quick|standard|deep","confidence":0..1,"risk":0..1,"effort":"low|medium|high|xhigh","reason":"short"}. '
        'Quick is bounded mechanical reading. Standard is ordinary writing/engineering. Deep is unknown failures, architecture or high stakes. '
        'Risk means actually making irreversible changes, not merely discussing them. Task: '+question[:12000],
        'model-router',session,model=model,effort='low',timeout=25)
    try:
        pick=object_answer(r['brief']); c=pick['confidence']; risk=pick.get('risk',0)
        if not r['accepted'] or pick['tier'] not in ('quick','standard','deep') or type(c) not in (int,float) or not 0<=c<=1 or type(risk) not in (int,float) or not 0<=risk<=1: raise ValueError()
        if pick.get('effort') not in ('low','medium','high','xhigh'): raise ValueError()
        if risk>0.7: pick['tier']='deep'
        pick.update(confidence_kind='model self-assessment; uncalibrated',applied=False,judge=r)
        return pick
    except (ValueError,KeyError,TypeError):
        return dict(tier='standard',confidence=None,effort=None,applied=False,reason='judge failed; retain configured defaults',judge=r)


class Text(HTMLParser):
    def __init__(self): super().__init__(); self.skip=0; self.parts=[]; self.dates=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','nav','footer'): self.skip+=1
        d=dict(attrs)
        if tag=='meta' and any(x in (d.get('property','')+' '+d.get('name','')).lower() for x in ('published','modified','date')):
            self.dates+=re.findall(r'\d{4}-\d{2}-\d{2}',d.get('content',''))
    def handle_endtag(self,tag):
        if tag in ('script','style','nav','footer'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip and data.strip(): self.parts.append(data.strip())


def public_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ('https','http') or p.username or p.password or not p.hostname: raise ValueError('Expected a public HTTP(S) source.')
    addresses=socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80))
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise ValueError('Research source resolves to a non-public address.')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        public_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def fetch(url,query,since=None):
    public_url(url)
    request=urllib.request.Request(url,headers={'User-Agent':'TokenMods/1.1 (research source verification)'})
    with urllib.request.build_opener(Redirect()).open(request,timeout=12) as r:
        content=r.headers.get('Content-Type',''); raw=r.read(1000001)
        if len(raw)>1000000: raw=raw[:1000000]
        if not any(s in content for s in ('html','text','json')): raise ValueError('Non-text source; use a PDF/visual reader.')
        text=raw.decode(r.headers.get_content_charset() or 'utf-8',errors='replace'); final=r.url
    parser=Text(); parser.feed(text)
    cleaned='\n'.join(parser.parts)
    if len(cleaned)<100: raise ValueError('Too little readable source text.')
    terms=set(re.findall(r'\w+',query.lower()))
    score=len(terms.intersection(re.findall(r'\w+',cleaned.lower())))
    newest=max(parser.dates) if parser.dates else None
    return dict(url=final,requested_url=url,text=cleaned[:60000],content_truncated=len(raw)>=1000000 or len(cleaned)>60000,
                relevance_overlap=score,published_or_modified=newest,outside_window=bool(since and newest and newest<since),
                date_status='known metadata' if newest else 'unknown; not assumed current',via='HTTP GET')


def opened_urls(result):
    urls=[]
    if not result.get('evidence'): return urls
    path=Path(result.get('evidence',''))/'events.jsonl'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            try: item=json.loads(line).get('item',{}); action=item.get('action',{})
            except ValueError: continue
            if action.get('type')=='open_page' and action.get('url'): urls.append(action['url'])
    return list(dict.fromkeys(urls))


def fallback(question,session):
    tool=shutil.which('firecrawl')
    if not tool: return dict(available=False,error='firecrawl is not installed',links=[])
    try:
        cmd=[tool,'search',question,'--limit','4','--json']
        if os.name=='nt' and Path(tool).suffix.lower() in ('.cmd','.bat'):
            code='& '+' '.join("'"+s.replace("'","''")+"'" for s in cmd)
            cmd=['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(code.encode('utf-16-le')).decode()]
        r=subprocess.run(cmd,capture_output=True,encoding='utf-8',timeout=30)
        links=list(dict.fromkeys(re.findall(r'https?://[^\s"<>\\]+',r.stdout)))[:8]
        with database() as db: log(db,session,'research-router','firecrawl',exit_code=r.returncode,output=save_original(r.stdout,'txt'))
        return dict(available=True,exit_code=r.returncode,links=links)
    except (OSError,subprocess.TimeoutExpired) as e: return dict(available=True,error=str(e),links=[])


def research(p):
    session=p.get('session',''); question=p['question']; start=time.monotonic(); jobs=[]; gaps=[]
    with database() as db:
        if 'research-router' not in active(db,session): raise ValueError('research-router is off.')
        model=p.get('model') or get(db,'research_model',session) or get(db,'model_quick',session) or None
        judge_model=get(db,'judge_model',session) or model
        pages=get(db,'research_pages',session); parts=get(db,'research_parts',session); can_fallback=get(db,'research_fallback',session)
    today=datetime.now().date(); since=p.get('since')
    match=re.search(r'last\s+(\d+)\s+days',question,re.I)
    if match and not since: since=(today-timedelta(days=int(match[1]))).isoformat()
    if since: datetime.strptime(since,'%Y-%m-%d')
    mode=p.get('mode','auto')
    if mode not in ('auto','quick','deep'): raise ValueError('Mode must be auto, quick, or deep.')
    def safe(*args,**kwargs):
        try: return run_worker(*args,**kwargs)
        except Exception as e: return dict(accepted=False,brief='',status='failed',error=str(e),usage=None)
    plan=safe('No tools. Today is '+today.isoformat()+'. Plan research of this question. Return JSON {"mode":"quick|deep","queries":["up to two search queries"],"parts":["two to four non-overlapping research questions"],"official_urls":[]}. '
        'Use deep only for a multi-part comparison. Question: '+question,'research-router',session,model=judge_model,effort='low',timeout=25)
    jobs.append(plan)
    try: config=object_answer(plan['brief']) or {}
    except (TypeError,ValueError): config={}
    if mode=='auto': mode=config.get('mode') if config.get('mode') in ('quick','deep') else 'quick'
    supplied=p.get('parts') or config.get('parts') or []
    if not isinstance(supplied,list) or any(not isinstance(x,str) for x in supplied): supplied=[]
    if mode=='deep':
        supplied=supplied[:max(2,min(4,parts))]
        if len(supplied)<2: supplied=[question+' Focus on primary evidence and benefits.',question+' Focus on limitations, risks and contradictory evidence.']
    else: supplied=[question]
    def perform(part):
        try: return run_worker(f'Today {today.isoformat()}. '+(f'Window starts {since}; leave older evidence out and flag unknown dates. ' if since else '')+part,
            'research-router',session,model=model,effort=p.get('effort') or 'low',timeout=min(p.get('timeout',90),120),cwd=p.get('cwd'))
        except Exception as error: return dict(accepted=False,status='failed',brief='',error=str(error),usage=None)
    with ThreadPoolExecutor(max_workers=len(supplied)) as pool: reports=list(pool.map(perform,supplied))
    jobs+=reports
    for i,r in enumerate(reports):
        if not r.get('accepted'): gaps.append(dict(part=supplied[i],error=r.get('error') or r.get('status')))
    urls=[]
    for r in reports: urls+=opened_urls(r)+r.get('sources',[])
    official=config.get('official_urls',[])
    if isinstance(official,list): urls=[u for u in official if isinstance(u,str)]+urls
    fallback_result=None
    if not urls and can_fallback:
        fallback_result=fallback(question,session); urls+=fallback_result.get('links',[])
    sources=[]; unread=[]
    for url in list(dict.fromkeys(urls))[:pages*2]:
        if len(sources)>=pages: break
        try:
            page=fetch(url,question,since)
            if page['outside_window'] or page['relevance_overlap']==0:
                unread.append(dict(url=url,reason='outside date window' if page['outside_window'] else 'no query overlap')); continue
            page['number']=len(sources)+1; sources.append(page)
        except Exception as e: unread.append(dict(url=url,reason=str(e)))
    if not sources and can_fallback and fallback_result is None:
        fallback_result=fallback(question,session)
        for url in fallback_result.get('links',[])[:pages]:
            try:
                page=fetch(url,question,since)
                if page['outside_window'] or page['relevance_overlap']==0: continue
                page['number']=len(sources)+1; sources.append(page)
            except Exception as e: unread.append(dict(url=url,reason=str(e)))
    relevant=None
    if sources:
        relevant=safe('No tools. For each source below, judge relevance to the question. Return JSON {"keep":[source numbers],"reasons":{}}. If uncertain keep the source. Question: '+question+'\n'+json.dumps([dict(number=s['number'],url=s['url'],text=s['text'][:2500]) for s in sources]),
            'research-router',session,model=judge_model,effort='low',timeout=25)
        jobs.append(relevant)
        try:
            keep=object_answer(relevant['brief'])['keep']
            if relevant['accepted'] and isinstance(keep,list) and all(type(x)is int for x in keep):
                for s in sources: s['relevance_selected']=s['number'] in keep
        except (TypeError,KeyError,ValueError): pass
    selected=[s for s in sources if s.get('relevance_selected',True)]
    writer=None; brief=''; accepted=False
    if selected:
        writer=safe('No tools. Write a research brief of at most 200 words answering the question, with [n] citations next to every factual claim. '
            'Use ONLY numbered fetched sources as evidence. Reports are leads, not evidence. State gaps and unknown dates. '
            'Preserve vendor-test caveats. Question: '+question+'\nSources: '+json.dumps([dict(number=s['number'],url=s['url'],text=s['text'][:16000],date=s['date_status']) for s in selected])+'\nGaps: '+json.dumps(gaps),
            'research-router',session,model=model,effort=p.get('effort') or 'low',timeout=40)
        jobs.append(writer); brief=writer['brief']
        citations=[int(x) for x in re.findall(r'\[(\d+)\]',brief)]
        accepted=writer['accepted'] and bool(citations) and all(n in {s['number'] for s in selected} for n in citations)
    if not accepted: gaps.append(dict(part='validated synthesis',error='No accepted source-backed synthesis; inspect saved reports and original pages.'))
    document=dict(question=question,mode=mode,today=today.isoformat(),since=since,brief=brief,accepted=accepted,
        partial=bool(gaps),gaps=gaps,sources=sources,unread_links=unread,reports=reports,plan=plan,
        relevance=relevant,writer=writer,fallback=fallback_result,elapsed_seconds=round(time.monotonic()-start,3),
        claim_validation='Citations resolve to fetched sources; semantic entailment still requires judgment.',
        worker_usage=[r.get('usage') for r in jobs],worker_count=len(jobs))
    path=save_original(json.dumps(document,ensure_ascii=False,indent=2),'txt')
    with database() as db: log(db,session,'research-router','deep-completed' if mode=='deep' else 'research-completed',accepted=accepted,source=path,workers=len(jobs))
    return {k:v for k,v in document.items() if k not in ('plan','reports','relevance','writer')} | {'sources':[{k:v for k,v in s.items() if k!='text'} for s in sources],'evidence':path}
