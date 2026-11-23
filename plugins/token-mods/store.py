"""Shared, transactional state. Never stores credentials or edits Codex configuration."""
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

NAMES = ('mods', 'savings-proof', 'handoff', 'effort-optimizer', 'model-router',
         'input-router', 'research-router', 'efficient-browser-use', 'cache-clock')
DATA = Path(os.environ.get('TOKEN_MODS_DIR') or Path.home() / '.codex-token-mods')
DEFAULTS = {'auto_workers': False, 'worker_timeout': 90, 'worker_max_calls': 12,
            'screenshot_scale': 0.5, 'screenshot_min': 512,
            'model_quick': '', 'model_standard': '', 'model_deep': '',
            'effort': 'suggest', 'handoff_threshold': 250000,
            'input_file': True, 'input_connector': True, 'judge_model': '',
            'research_model': '', 'research_pages': 4, 'research_parts': 2,
            'prices': {}, 'research_fallback': True}


class ScopedConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()


def database(persistent=False):
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(DATA / 'state.sqlite3', timeout=15,factory=sqlite3.Connection if persistent else ScopedConnection)
    db.execute('PRAGMA busy_timeout=15000')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY, enabled INTEGER);
      CREATE TABLE IF NOT EXISTS options(scope TEXT, name TEXT, value TEXT, PRIMARY KEY(scope,name));
      CREATE TABLE IF NOT EXISTS turns(session TEXT, turn TEXT, prompt TEXT, reply TEXT, PRIMARY KEY(session,turn));
      CREATE TABLE IF NOT EXISTS activity(session TEXT PRIMARY KEY, observed REAL);
      CREATE TABLE IF NOT EXISTS requests(session TEXT, turn TEXT, ts REAL, model TEXT, status TEXT, counts TEXT);
      CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, session TEXT, ts REAL, module TEXT, action TEXT, detail TEXT);
      CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, cwd TEXT, model TEXT, seen REAL);
      CREATE TABLE IF NOT EXISTS budget(session TEXT PRIMARY KEY, calls INTEGER);
      CREATE TABLE IF NOT EXISTS tool_history(session TEXT, turn TEXT, ts REAL, tool TEXT, args TEXT, summary TEXT);
      CREATE TABLE IF NOT EXISTS coverage(scope TEXT, source TEXT, ranges TEXT, total INTEGER, notes TEXT, PRIMARY KEY(scope,source));
    ''')
    return db


def get(db, name, session=''):
    for scope in (session, '') if session else ('',):
        row = db.execute('SELECT value FROM options WHERE scope=? AND name=?', (scope, name)).fetchone()
        if row:
            return json.loads(row[0])
    return DEFAULTS.get(name)


def put(db, name, value, session=''):
    db.execute('INSERT OR REPLACE INTO options VALUES(?,?,?)', (session, name, json.dumps(value)))


def active(db, session=''):
    disabled = {n for n, in db.execute('SELECT name FROM settings WHERE enabled=0')}
    return {n for n in NAMES if (get(db,n,session) if get(db,n,session) is not None else n not in disabled)}


def log(db, session, module, action, **detail):
    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',
               (uuid.uuid4().hex, session, time.time(), module, action, json.dumps(detail, ensure_ascii=False)))


def consume_full(db, module, session):
    key = module + ':full'
    if get(db, key, session):
        put(db, key, False, session)
        return True
    return False


def counts(value):
    keys = ('input_tokens', 'cached_input_tokens', 'output_tokens')
    if not isinstance(value, dict) or any(type(value.get(k)) is not int or value[k] < 0 for k in keys):
        return None
    if value['cached_input_tokens'] > value['input_tokens']:
        return None
    return {k: value[k] for k in keys}


def report(db, session=None, day=None):
    where, args = [], []
    if session:
        where.append('session=?'); args.append(session)
    if day:
        where.append("date(ts,'unixepoch','localtime')=?"); args.append(day)
    suffix = ' WHERE ' + ' AND '.join(where) if where else ''
    total = dict(input_tokens=0, cached_input_tokens=0, output_tokens=0)
    measured = missing = failed = 0
    for status, raw in db.execute('SELECT status,counts FROM requests' + suffix, args):
        value = counts(json.loads(raw))
        failed += status != 'completed'
        if value:
            measured += 1
            for k in total:
                total[k] += value[k]
        else:
            missing += 1
    modules = {}
    for module, action, raw in db.execute('SELECT module,action,detail FROM events' + suffix, args):
        m = modules.setdefault(module, dict(actions=0, estimated_text_tokens_removed=0, worker_usage=[], failures=0))
        m['actions'] += 1
        d = json.loads(raw)
        m['estimated_text_tokens_removed'] += max(0, d.get('before_estimate', 0) - d.get('after_estimate', 0))
        if d.get('usage') is not None:
            m['worker_usage'].append(d['usage'])
        m['failures'] += action in ('failed', 'interrupted', 'timeout')
    prices=get(db,'prices',session or '') or {}
    economic=0.0; priced=0; unpriced=0
    for model,raw in db.execute('SELECT model,counts FROM requests'+suffix,args):
        usage=counts(json.loads(raw)); price=prices.get(model)
        if usage and isinstance(price,dict) and all(type(price.get(k)) in (int,float) and price[k]>=0 for k in ('input','cached','output')):
            economic+=((usage['input_tokens']-usage['cached_input_tokens'])*price['input']+usage['cached_input_tokens']*price['cached']+usage['output_tokens']*price['output'])/1e6; priced+=1
        else: unpriced+=1
    return dict(measured_attempts=measured, attempts_without_counts=missing, failed_attempts=failed,
                measured_tokens=total if measured else None, modules=modules,
                causal_savings=None, billed_cost=None,
                list_price_estimate=dict(usd=economic if priced else None,priced_attempts=priced,unpriced_attempts=unpriced,source='user-supplied per-million prices; not billed account cost'),
                note='Provider request counts and character/4 estimates are separate. Worker usage may overlap session totals; do not add them twice. Causal savings require paired accepted runs.')


def save_original(value, extension='json'):
    folder = DATA / 'results'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / (uuid.uuid4().hex + '.' + extension)
    path.write_text(json.dumps(value, ensure_ascii=False) if extension == 'json' else value, encoding='utf-8')
    return str(path.resolve())
