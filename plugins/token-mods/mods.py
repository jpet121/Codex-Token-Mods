"""Codex hooks and terminal controls. Hooks fail open and preserve approvals."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from store import NAMES, DATA, database, active, get, put, log, report, consume_full, save_original
from routing import decision, reader_command, instruction_path, excerpts, text_blocks, paging


def context(event, text):
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': text}}


def hook(db, e):
    event, session = e['hook_event_name'], e['session_id']
    scope = session + (':' + e['agent_id'] if e.get('agent_id') else '')
    turn = e.get('turn_id', '')
    enabled = active(db, session)
    if os.environ.get('TOKEN_MODS_WORKER') == '1':
        enabled -= {'input-router', 'research-router', 'model-router', 'effort-optimizer'}
    if event == 'SessionStart':
        db.execute('INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)', (session, e.get('cwd'), e.get('model'), time.time()))
        if 'mods' in enabled:
            root = Path(__file__).resolve().parent
            return context(event, f'Token Mods: read controls/instructions through mods_status action help, or {root / "skills/mods/SKILL.md"}. '
                           f'Use {sys.executable} {root / "mods.py"} list for settings. '
                           'Manual model, effort, exact reads and full-result requests take priority. '
                           'Large supported read results may be replaced by labeled extracts with a saved original. '
                           'Retrieve originals for exact quotes, edits or missing evidence. No background warm requests run.')
    elif event == 'UserPromptSubmit':
        prompt = e.get('prompt', '')
        if prompt != get(db,'query',scope): db.execute('UPDATE coverage SET notes=NULL WHERE scope=?',(scope,))
        put(db, 'query', prompt, scope)
        if any(s in prompt.casefold() for s in ('full result','full output','full text','verbatim','exact text','unabridged')):
            put(db, 'input-router:full', True, scope)
        if any(s in prompt.casefold() for s in ('full resolution','full size','full-size screenshot')):
            put(db, 'efficient-browser-use:full', True, scope)
        if 'handoff' in enabled:
            db.execute('INSERT INTO turns VALUES(?,?,?,NULL) ON CONFLICT(session,turn) DO UPDATE SET prompt=excluded.prompt', (session, turn, prompt))
            if get(db,'handoff_due',session) and not get(db,'handoff:hidden',session):
                put(db,'handoff_due',False,session)
                return context(event,'Token Mods: observed request input crossed the handoff threshold. This is a context-size proxy. '
                               'A draft can be prepared on request; the current chat remains active.')
        if 'effort-optimizer' in enabled and get(db, 'effort', session) == 'suggest':
            pick = decision(prompt)
            log(db, session, 'effort-optimizer', 'advice', **pick)
            if pick['tier'] != 'standard' and not get(db,'effort-optimizer:hidden',session):
                return context(event, f'Token Mods effort advice: {pick["effort"]}; current setting is unchanged. '
                               'Only change main-thread effort using the user-owned picker or a client that owns turn/start.')
    elif event == 'Stop' and 'handoff' in enabled:
        db.execute('INSERT INTO turns VALUES(?,?,NULL,?) ON CONFLICT(session,turn) DO UPDATE SET reply=excluded.reply',
                   (session, turn, e.get('last_assistant_message')))
    elif event in ('PreCompact','PostCompact'):
        log(db,session,'savings-proof',event,turn=turn,trigger=e.get('trigger'))
    elif event == 'Interrupt':
        log(db, session, 'mods', 'interrupted', turn=turn)
    elif event == 'PostModelRequest':
        if 'cache-clock' in enabled:
            db.execute('INSERT OR REPLACE INTO activity VALUES(?,?)', (session, time.time()))
        if 'savings-proof' in enabled:
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?)',
                       (session, turn, time.time(), e.get('model'), e.get('status'), json.dumps(e.get('token_usage'))))
        usage = e.get('token_usage') or {}
        threshold=get(db,'handoff_next_threshold',session) or get(db, 'handoff_threshold', session)
        if 'handoff' in enabled and usage.get('input_tokens', 0) >= threshold:
            put(db, 'handoff_due', True, session)
            put(db,'handoff_next_threshold',usage['input_tokens']+100000,session)
    elif event == 'PreToolUse':
        tool, args = e.get('tool_name', ''), e.get('tool_input')
        if not isinstance(args, dict): return {}
        replacement = None
        if tool in ('spawn_agent', 'Agent', 'collaboration.spawn_agent') and 'model-router' in enabled:
            prompt = args.get('message', args.get('prompt', ''))
            if args.get('fork_turns') == 'none' and not args.get('model') and isinstance(prompt, str):
                pick = decision(prompt)
                configured = get(db, 'model_' + pick['tier'], session) or os.getenv('CODEX_FLOW_MODEL_' + pick['tier'].upper())
                if configured and pick['confidence'] is not None and pick['confidence'] >= 0.6:
                    replacement = {**args, 'model': configured}
                    log(db, session, 'model-router', 'suggested', model=configured, **pick)
        if tool in ('mcp__chrome-devtools__take_screenshot','mcp__chrome_devtools__take_screenshot') and 'efficient-browser-use' in enabled:
            if not {'format','quality','filePath','scale','clip','fullPage'}.intersection(args) and not consume_full(db, 'efficient-browser-use', scope):
                replacement = {**args, 'format':'jpeg', 'quality':75}
                log(db, session, 'efficient-browser-use', 'jpeg-advice', token_savings=None)
        if replacement is not None:
            # updatedInput requires permissionDecision:allow, which can skip ordinary approval.
            # Advice keeps the host's normal permission decision. MCP workers own their own request.
            return context(event, 'Token Mods suggests these arguments; preserve normal approval: ' + json.dumps(replacement))
    elif event == 'PostToolUse':
        if 'handoff' in enabled:
            from insights import redact
            db.execute('INSERT INTO tool_history VALUES(?,?,?,?,?,?)',(session,turn,time.time(),e.get('tool_name'),json.dumps(redact(json.dumps(e.get('tool_input'),ensure_ascii=False))[:12000]),redact(str(e.get('tool_response','')))[:800]))
        from input_flow import route_result
        return route_result(db,e,session,scope,enabled)
    return {}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('hook'); sub.add_parser('sessions')
    for name in ('list','usage','events'):
        q = sub.add_parser(name); q.add_argument('--session', default='')
        if name == 'usage': q.add_argument('--day')
    for name in ('on','off','full'):
        q = sub.add_parser(name); q.add_argument('module', choices=NAMES); q.add_argument('--session', default='')
    q = sub.add_parser('set'); q.add_argument('name'); q.add_argument('value'); q.add_argument('--session', default='')
    q = sub.add_parser('reset'); q.add_argument('name'); q.add_argument('--session', default='')
    for name in ('handoff','clock'):
        q = sub.add_parser(name); q.add_argument('session')
    a = p.parse_args()
    if a.cmd == 'hook':
        try:
            event = json.load(sys.stdin)
            with database() as db:
                db.execute('BEGIN IMMEDIATE')
                output = hook(db, event)
            print(json.dumps(output, ensure_ascii=True))
        except Exception as error:
            print('{}'); print('Token Mods passed original through: ' + str(error), file=sys.stderr)
        return
    from tools_api import call
    params = vars(a).copy(); params['action'] = params.pop('cmd')
    if a.cmd in ('on','off','full','set','reset','list','events','sessions'):
        name = 'mods'
        if a.cmd == 'set':
            try: params['value'] = json.loads(a.value)
            except ValueError: pass
    else: name = {'usage':'savings_proof', 'handoff':'handoff', 'clock':'cache_clock'}[a.cmd]
    print(json.dumps(call(name, params), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')
    main()
