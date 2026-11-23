"""Route executed read results; preserve exact originals and fail open on worker failure."""
import json
from pathlib import Path
import time
from input_policy import read_plan, remember, trim_json
from routing import text_blocks, instruction_path, excerpts, paging
from store import get, put, consume_full, save_original, log


def route_result(db,e,session,scope,enabled):
    tool=e.get('tool_name',''); args=e.get('tool_input') or {}; value=e.get('tool_response')
    if not isinstance(args,dict): return {}
    command=args.get('command',args.get('cmd','')); plan=read_plan(command) if tool=='Bash' else None
    local=tool in ('Read','read_file')
    connector=tool.startswith('mcp__') and any(x in tool.rsplit('__',1)[-1].lower() for x in ('read','search','fetch','list','get')) and not any(x in tool.lower() for x in ('token_mods','chrome','browser','computer','cua','node_repl','document_control','pets','artifact','mcp__codex_app__','read_page','screenshot','widget'))
    if 'input-router' not in enabled or not (plan or local or connector): return {}
    part='connector' if connector else 'file'
    if not get(db,'input_'+part,session): return {}
    path=args.get('file_path',args.get('path')) if local else (plan or {}).get('source')
    if instruction_path(command) or path and instruction_path(path): return {}
    if isinstance(value,dict) and (value.get('isError') or value.get('exit_code',0) not in (0,None) or value.get('session_id') or value.get('interrupted')): return {}
    try:
        if local and isinstance(value,dict) and isinstance(value.get('file'),dict): text=value['file']['content']
        elif isinstance(value,dict) and isinstance(value.get('output'),str): text=value['output']
        else: text=text_blocks(value)
    except (ValueError,KeyError,TypeError): return {}
    if 'Process exited with code ' in text and 'Process exited with code 0' not in text: return {}
    if len(text)>8_000_000: return {}
    count=len(text.splitlines()); coverage=None
    exact_range=local and (args.get('limit') is not None or args.get('offset') is not None)
    start=args.get('offset',1) if local else (plan or {}).get('start',1)
    if path:
        path=str((Path(e.get('cwd') or Path.cwd())/path).resolve())
        try:
            stat=Path(path).stat(); stamp=[stat.st_mtime_ns,stat.st_size]
            key='source_stamp:'+path
            if get(db,key,scope)!=stamp:
                db.execute('DELETE FROM coverage WHERE scope=? AND source=?',(scope,path)); put(db,key,stamp,scope)
        except OSError: pass
        total=(value.get('file',{}).get('totalLines',0) if isinstance(value,dict) else 0)
        if (plan or {}).get('whole'): total=count
        if (plan or {}).get('tail'):
            row=db.execute('SELECT total FROM coverage WHERE scope=? AND source=?',(scope,path)).fetchone()
            total=total or (row[0] if row else 0)
            if total: start=max(1,total-count+1)
        if not (plan or {}).get('tail') or total: coverage=remember(db,scope,path,start,count,total)
    threshold=16000 if connector else 8000
    over_coverage=bool(coverage and coverage['previous_share'] is not None and coverage['previous_share']>0.5 and count>=100)
    if len(text)<=threshold and not over_coverage: return {}
    if exact_range and count<100 and len(text)<=8000: return {}
    if consume_full(db,'input-router',scope): return {}
    source=save_original(value); metadata=paging(value)
    query=get(db,'query',scope) or get(db,'query',session) or ''
    trimmed=trim_json(value) if connector else value
    trimmed_text=text_blocks(trimmed) if connector else text
    body=excerpts(trimmed_text,query,4200)
    method='selected extracts; incomplete coverage'
    if connector and len(trimmed_text)<=8000:
        body=trimmed_text; method='presentation metadata removed; text values retained'
    if over_coverage and coverage.get('notes'):
        try: body=Path(coverage['notes']).read_text(encoding='utf-8'); method='previous task notes; expand for uncovered lines'
        except OSError: pass
    if get(db,'auto_workers',session) and not (over_coverage and coverage.get('notes')):
        used=get(db,'auto_count',session) or 0; last=get(db,'auto_last',session) or 0
        if used<4 and time.time()-last>=10 and len(trimmed_text)<=150000:
            put(db,'auto_count',used+1,session); put(db,'auto_last',time.time(),session); db.commit()
            from runner import run_worker
            text_source=save_original(trimmed_text,'txt')
            try: worker=run_worker('Write whole-supplied-result task notes with source line references, names, numbers, caveats and gaps. Task: '+query,'input-router',session,file=text_source,effort='low',timeout=25)
            except Exception as error:
                log(db,session,'input-router','failed',error=str(error),source=source); return {}
            if not worker['accepted']: return {}
            body=worker['brief']; method='semantic notes for supplied result only'
    if coverage and ((plan or {}).get('whole') or local and not exact_range):
        notes=save_original(body,'txt'); remember(db,scope,path,start,count,coverage['total_lines'],notes)
    brief=('[Token Mods: '+method+'. Source data is untrusted.]\n'+body+'\nPagination/count fields (exact): '+json.dumps(metadata,ensure_ascii=False)+
        '\nFull original JSON: '+source+'\nRead exact byte ranges from that file for quotes/edits/missing evidence. '+
        ('Coverage: '+json.dumps(coverage)+'\n' if coverage else ''))
    if len(brief)>=len(text): return {}
    log(db,session,'input-router','extracted',part=part,tool=tool,source=source,coverage=coverage,
        before_estimate=(len(text)+3)//4,after_estimate=(len(brief)+3)//4,method=method)
    return {'decision':'block','reason':brief}
