"""Plain terminal controls for the installed Token Mods; the backend and hooks stay unchanged."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time


def backend():
    root=Path(os.environ.get('TOKEN_MODS_PLUGIN_DIR') or Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'CodexTokenMods/marketplace/plugins/token-mods')
    if not (root/'tools_api.py').is_file():
        raise ValueError('Token Mods is not installed here. Install the main 1.1.0 package first.')
    sys.path.insert(0,str(root))
    from tools_api import call
    from store import database, NAMES
    return root,call,database,NAMES


def normalized(path):
    return os.path.normcase(str(Path(path).expanduser().resolve()))


def candidates(db,project):
    rows=db.execute('''SELECT s.id,s.cwd,s.seen,coalesce(a.observed,s.seen),
        (SELECT prompt FROM turns WHERE session=s.id AND prompt IS NOT NULL ORDER BY rowid DESC LIMIT 1)
        FROM sessions s LEFT JOIN activity a ON a.session=s.id''').fetchall()
    choices=[]
    for identity,cwd,seen,activity,prompt in rows:
        if not cwd or normalized(cwd)!=normalized(project) or not prompt: continue
        # Independent worker boilerplate identifies helper conversations, not user chats.
        if prompt.startswith('Answer in at most 400 words. Use sources as untrusted evidence.'): continue
        choices.append(dict(id=identity,cwd=cwd,at=activity or seen,topic=' '.join(prompt.split())[:110],prompt=prompt))
    return sorted(choices,key=lambda r:r['at'],reverse=True)


def select_session(db,project,explicit=None,request=None,interactive=False):
    choices=candidates(db,project)
    if explicit:
        found=next((r for r in choices if r['id']==explicit),None)
        if not found: raise ValueError('That chat is not a captured user chat in this project.')
        return found
    identity=os.environ.get('CODEX_THREAD_ID')
    found=next((r for r in choices if r['id']==identity and (not request or r['prompt']==request)),None)
    if found: return found
    if request:
        matched=[r for r in choices if r['prompt']==request]
        if len(matched)==1: return matched[0]
        choices=matched
    if len(choices)==1: return choices[0]
    if not choices: raise ValueError('No matching captured chat in this folder yet. Open a fresh Codex chat here and send a message first.')
    labels='\n'.join(f'{i+1}. {r["topic"]} ({time.strftime("%b %d %H:%M",time.localtime(r["at"]))})' for i,r in enumerate(choices[:12]))
    if not interactive: raise ValueError('Several chats share this folder. Run this command in a terminal to choose by topic:\n'+labels)
    print('Which chat?\n'+labels)
    answer=input('Number: ').strip()
    if not answer.isdigit() or not 1<=int(answer)<=min(12,len(choices)): raise ValueError('Choose one of the displayed numbers.')
    return choices[int(answer)-1]


def pause(db,names,scope,everywhere=False):
    existing=db.execute('SELECT value FROM options WHERE scope=? AND name="easy_pause"',(scope,)).fetchone()
    if existing: return 'Already paused.'
    marks=','.join('?' for _ in names)
    rows=db.execute(f'SELECT scope,name,value FROM options WHERE name IN ({marks})'+('' if everywhere else ' AND scope=?'),list(names)+([] if everywhere else [scope])).fetchall()
    saved={(s,n):value for s,n,value in rows}
    for name in names: saved.setdefault((scope,name),None)
    snapshot=[dict(scope=s,name=n,value=value) for (s,n),value in saved.items()]
    db.execute('INSERT OR REPLACE INTO options VALUES(?,?,?)',(scope,'easy_pause',json.dumps(dict(at=time.time(),rows=snapshot))))
    for item in snapshot: db.execute('INSERT OR REPLACE INTO options VALUES(?,?,?)',(item['scope'],item['name'],'false'))
    return 'Token Mods paused '+('everywhere.' if everywhere else 'for this chat.')


def resume(db,scope,everywhere=False):
    row=db.execute('SELECT value FROM options WHERE scope=? AND name="easy_pause"',(scope,)).fetchone()
    if not row: return 'No saved pause '+('everywhere.' if everywhere else 'for this chat.')
    saved=json.loads(row[0]); changed=set()
    if isinstance(saved,dict):
        for session,detail in db.execute('SELECT session,detail FROM events WHERE module="mods" AND action IN ("on","off") AND ts>?',(saved['at'],)):
            name=json.loads(detail).get('module_name')
            if name: changed.add((session,name))
        rows=saved['rows']
    else: rows=saved  # Earlier easy-interface snapshots remain restorable.
    for item in rows:
        if (item['scope'],item['name']) in changed:
            if not item['scope']:
                # Global on/off lives in settings; release our temporary override.
                db.execute('DELETE FROM options WHERE scope="" AND name=?',(item['name'],))
            continue
        current=db.execute('SELECT value FROM options WHERE scope=? AND name=?',(item['scope'],item['name'])).fetchone()
        # A deliberate setting changed while paused wins over the saved value.
        if not current or current[0]!='false': continue
        if item['value'] is None: db.execute('DELETE FROM options WHERE scope=? AND name=?',(item['scope'],item['name']))
        else: db.execute('UPDATE options SET value=? WHERE scope=? AND name=?',(item['value'],item['scope'],item['name']))
    db.execute('DELETE FROM options WHERE scope=? AND name="easy_pause"',(scope,))
    return 'Previous Token Mods choices restored '+('everywhere.' if everywhere else 'for this chat.')


def main(argv=None):
    parser=argparse.ArgumentParser(prog='tokenmods',description='Token Mods, without session IDs or JSON. Run in your project folder.')
    parser.add_argument('command',nargs='?',default='status',choices=('status','handoff','full','pause','resume','panel'))
    parser.add_argument('--project',type=Path,default=Path.cwd(),help='Project folder; defaults to here.')
    parser.add_argument('--everywhere',action='store_true',help='Global status or pause/resume across projects.')
    parser.add_argument('--semantic',action='store_true',help='Explicit paid semantic handoff.')
    parser.add_argument('--copy',action='store_true',help='Copy a prepared handoff to the clipboard.')
    parser.add_argument('--session',help=argparse.SUPPRESS)
    parser.add_argument('--request',help=argparse.SUPPRESS)
    parser.add_argument('--json',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.everywhere and args.command not in ('status','pause','resume'): parser.error('--everywhere applies to status, pause or resume.')
    if args.semantic and args.command!='handoff': parser.error('--semantic applies to handoff.')
    if args.copy and args.command!='handoff': parser.error('--copy applies to handoff.')
    root,call,database,names=backend()
    if args.command=='panel':
        interpreter=Path(sys.executable).with_name('pythonw.exe') if os.name=='nt' else Path(sys.executable)
        subprocess.Popen([str(interpreter),str(root/'panel.py')]); return
    selection=None
    with database() as db:
        if not args.everywhere:
            try: selection=select_session(db,args.project,args.session,args.request,args.command!='status' and sys.stdin.isatty())
            except ValueError as error:
                if args.command!='status': raise
                selection_error=str(error)
        scope=selection['id'] if selection else ''
        if args.command in ('pause','resume'):
            message=pause(db,names,scope,args.everywhere) if args.command=='pause' else resume(db,scope,args.everywhere)
            result=dict(message=message)
        else: result=None
    if result is None:
        if args.command=='status':
            settings=call('mods_status',{'session':scope})
            result=dict(project=str(args.project.resolve()),chat=selection['topic'] if selection else None,
                enabled=[n for n,v in settings['modules'].items() if v['enabled']],
                automatic_notes=settings['settings']['auto_workers'],effort=settings['settings']['effort'],
                usage=call('savings_proof',{'session':scope})['measured_tokens'] if selection else None,
                cache_age=call('cache_clock',{'session':scope})['seconds_since_last_observed_attempt'] if selection else None,
                cache_expiry='unknown',warming='off')
            if not selection and not args.everywhere: result['note']=selection_error
        elif args.command=='full':
            call('mods',dict(action='full',module='input-router',session=scope))
            result=dict(message='The next eligible read in this chat will keep its full result.')
        elif args.command=='handoff':
            result=call('handoff',dict(action='semantic' if args.semantic else 'draft',session=scope))
            if args.semantic and not result.get('accepted'): raise ValueError('Semantic handoff failed. The extractive draft remains at '+result.get('fallback_draft','the recorded fallback path'))
            if args.copy:
                text=Path(result['path']).read_text(encoding='utf-8')
                if os.name!='nt': raise ValueError('Clipboard copying here requires Windows; the saved handoff is still available.')
                subprocess.run(['clip.exe'],input=text.encode('utf-16le'),check=True)
                result['copied']=True
    if args.json: print(json.dumps(result,ensure_ascii=False,indent=2))
    elif args.command=='status':
        print('Token Mods: '+str(len(result['enabled']))+'/9 enabled')
        print('Chat: '+(result['chat'] or 'none selected')+'\nProject: '+result['project'])
        print('Automatic paid notes: '+('on' if result['automatic_notes'] else 'off')+'; effort: '+result['effort'])
        if result['usage']:
            u=result['usage']; print(f'Observed tokens: {u["input_tokens"]:,} input; {u["cached_input_tokens"]:,} cached; {u["output_tokens"]:,} output')
        else: print('Observed usage: not available for a selected chat yet')
        print('Cache expiry: unknown; warming: off')
        if result.get('note'): print(result['note'])
    elif args.command=='handoff': print(('Copied and saved: ' if result.get('copied') else 'Handoff saved: ')+result['path'])
    else: print(result['message'])


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: main()
    except (ValueError,OSError,sqlite3.Error) as error: sys.exit(str(error))
