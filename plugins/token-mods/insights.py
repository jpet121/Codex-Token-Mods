"""Read-only plugin discovery, workspace handoff evidence and accepted-run accounting."""
import json
import os
from pathlib import Path
import re
import subprocess
from store import counts


def inventory():
    try: import tomllib
    except ImportError: import tomli as tomllib
    home=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))
    config=home/'config.toml'
    data=tomllib.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    entries=[]
    for identity,settings in data.get('plugins',{}).items():
        name,_,market=identity.partition('@')
        roots=list((home/'plugins/cache'/market/name).glob('*/.codex-plugin/plugin.json'))
        details={}; source=None
        if roots:
            path=max(roots,key=lambda p:p.stat().st_mtime); source=str(path)
            try: details=json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError): pass
        entries.append(dict(id=identity,enabled=settings.get('enabled',True),version=details.get('version'),
            description=details.get('description','')[:400],source=source,has_hooks=bool(details.get('hooks')),
            capabilities=dict(skills=bool(details.get('skills')),mcp=bool(details.get('mcpServers'))),
            controls='Own module controls; explicit mods action plugin can update this plugin enabled state using normal Codex permissions.'))
    return entries


def workspace(cwd):
    root=Path(cwd).resolve()
    result=dict(cwd=str(root),git=False,changed_files=[],recent_commits=[],errors=[])
    def git(*args):
        r=subprocess.run(['git','-C',str(root),*args],capture_output=True,encoding='utf-8',errors='replace',timeout=8)
        if r.returncode: raise ValueError(r.stderr.strip()[:300])
        return r.stdout
    try:
        result['git_root']=git('rev-parse','--show-toplevel').strip(); result['git']=True
        result['status']=git('status','--porcelain=v1','-z').split('\0')[:100]
        result['diff_stat']=git('diff','--stat')[:6000]
        result['recent_commits']=git('log','-3','--format=%h %s').splitlines()
    except (OSError,ValueError,subprocess.TimeoutExpired) as e: result['errors'].append(str(e))
    return result


def redact(text):
    text=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{16,}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{30,}|AKIA[0-9A-Z]{16})\b','[secret removed]',text)
    text=re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}',r'\1[secret removed]',text)
    return re.sub(r'(?i)\b([A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)\s*=\s*)(?!\$)(["\']?)[^\s"\']{8,}\2',r'\1[secret removed]',text)


def compare(before,after):
    records=[]
    for file in (before,after):
        p=Path(file); r=json.loads((p/'result.json' if p.is_dir() else p).read_text(encoding='utf-8'))
        if not (r.get('accepted') or r.get('accepted_stream') or r.get('quality_pass')) or r.get('quality_pass') is False: raise ValueError('Both workloads must pass an explicit acceptance check.')
        usage=counts(r.get('usage'))
        if usage is None: raise ValueError('Complete provider usage is required.')
        records.append((r,usage))
    a,b=records
    for field in ('model','effort','task_hash','input_hash','acceptance_id'):
        if not a[0].get(field) or a[0][field]!=b[0].get(field): raise ValueError('Matched '+field+' is required to isolate a feature.')
    return dict(provider_delta={k:b[1][k]-a[1][k] for k in a[1]},
        uncached_input_delta=b[1]['input_tokens']-b[1]['cached_input_tokens']-a[1]['input_tokens']+a[1]['cached_input_tokens'],
        elapsed_delta=b[0].get('elapsed_seconds',0)-a[0].get('elapsed_seconds',0),
        worker_overhead_before=a[0].get('worker_usage'),worker_overhead_after=b[0].get('worker_usage'),
        billed_savings=None,note='Observed paired result; cache state and stochastic output can affect differences.')
