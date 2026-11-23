"""Install, upgrade or unregister this plugin without replacing unrelated Codex config."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import venv

ROOT=Path(__file__).resolve().parent
PLUGIN=ROOT/'plugins/token-mods'


def prepare(root=ROOT, interpreter=None):
    plugin=root/'plugins/token-mods'
    interpreter=interpreter or sys.executable
    argv=[str(interpreter),str(plugin/'mods.py'),'hook']
    if os.name=='nt':
        code='[Console]::InputEncoding=[Text.UTF8Encoding]::new($false); [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); & '+ ' '.join("'"+s.replace("'","''")+"'" for s in argv)
        command='powershell.exe -NoProfile -NonInteractive -EncodedCommand '+base64.b64encode(code.encode('utf-16-le')).decode()
    else: command=shlex.join(argv)
    events=('SessionStart','UserPromptSubmit','PostModelRequest','Stop','PreToolUse','PostToolUse','PreCompact','PostCompact','Interrupt')
    hooks={e:[{'hooks':[{'type':'command','command':command,'timeout':3 if e=='Interrupt' else 10}]}] for e in events}
    hooks['PreToolUse'][0]['matcher']='^(Agent|spawn_agent|collaboration.spawn_agent|mcp__chrome[-_]devtools__take_screenshot)$'
    hooks['PostToolUse'][0]['hooks'][0]['timeout']=45
    (plugin/'hooks').mkdir(exist_ok=True)
    (plugin/'hooks/hooks.json').write_text(json.dumps({'hooks':hooks},indent=2),encoding='utf-8')
    manifest={'name':'token-mods','version':'1.1.0','description':'Nine local context, usage, routing and handoff tools for ordinary Codex sessions.',
              'skills':'./skills/','mcpServers':'./.mcp.json','hooks':'./hooks/hooks.json',
              'interface':{'displayName':'Token Mods','shortDescription':'Source-preserving context tools and observed usage'}}
    (plugin/'.codex-plugin/plugin.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    mcp={'mcpServers':{'token_mods':{'command':str(interpreter),'args':[str(plugin/'server.py')],
        'env':{'PYTHONUTF8':'1'},'env_vars':['TOKEN_MODS_DIR','TOKEN_MODS_CODEX','TOKEN_MODS_WORKER','CODEX_FLOW_MODEL_QUICK','CODEX_FLOW_MODEL_STANDARD','CODEX_FLOW_MODEL_DEEP'],
        'startup_timeout_sec':10,'tool_timeout_sec':330}}}
    (plugin/'.mcp.json').write_text(json.dumps(mcp,indent=2),encoding='utf-8')


def cli(*args):
    exe=shutil.which(os.environ.get('TOKEN_MODS_CODEX','codex'))
    if not exe: raise SystemExit('Codex CLI was not found. Set TOKEN_MODS_CODEX or add it to PATH.')
    result=subprocess.run([exe,*args],capture_output=True,text=True,encoding='utf-8',timeout=90)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-3000:])
    print(result.stdout.strip())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--uninstall',action='store_true')
    p.add_argument('--destination',type=Path)
    p.add_argument('--stdlib-only',action='store_true',help='Skip the private image/PDF runtime; those optional actions need their packages installed separately.')
    a=p.parse_args()
    if a.prepare_only: prepare(); return
    if a.uninstall:
        cli('plugin','remove','token-mods@local-token-tools')
        cli('plugin','marketplace','remove','local-token-tools')
        print('Unregistered Token Mods. Source and ~/.codex-token-mods records retained.'); return
    dest=(a.destination or (Path(os.environ['LOCALAPPDATA'])/'CodexTokenMods/marketplace' if os.name=='nt' else Path.home()/'.local/share/codex-token-mods/marketplace')).resolve()
    if dest==ROOT or ROOT in dest.parents: raise SystemExit('Choose an installation directory outside the extracted package.')
    config=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'config.toml'
    backup=dest.parent/'backups'; backup.mkdir(parents=True,exist_ok=True)
    if config.exists():
        digest=hashlib.sha256(config.read_bytes()).hexdigest()[:16]
        target=backup/('config-'+digest+'.toml')
        if not target.exists(): shutil.copy2(config,target)
    dest.mkdir(parents=True,exist_ok=True)
    shutil.copytree(ROOT/'plugins',dest/'plugins',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(ROOT/'.agents',dest/'.agents',dirs_exist_ok=True)
    shutil.copy2(ROOT/'setup_port.py',dest/'setup_port.py')
    shutil.copy2(ROOT/'requirements.txt',dest/'requirements.txt')
    interpreter=sys.executable
    if not a.stdlib_only:
        runtime=dest.parent/'runtime'
        interpreter=runtime/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if not interpreter.exists(): venv.EnvBuilder(with_pip=True).create(runtime)
        marker=runtime/'token-mods-requirements.sha256'
        requirement_hash=hashlib.sha256((ROOT/'requirements.txt').read_bytes()).hexdigest()
        if not marker.exists() or marker.read_text()!=requirement_hash:
            subprocess.run([str(interpreter),'-m','pip','install','--disable-pip-version-check','-r',str(ROOT/'requirements.txt')],check=True,timeout=180)
            marker.write_text(requirement_hash)
    prepare(dest,interpreter)
    cli('plugin','marketplace','add',str(dest),'--json')
    cli('plugin','add','token-mods@local-token-tools','--json')
    print('Installed at '+str(dest))
    print('In a new Codex session, review the concrete hooks in /hooks or Desktop Settings > Hooks. Existing chats may need a fresh session for MCP discovery.')
    print('No authentication, approval, sandbox, model, or unrelated plugin settings were changed.')


if __name__=='__main__': main()
