"""Install the easy interface beside Token Mods. Existing plugin files and trust stay untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

SOURCE=Path(__file__).resolve().parent


def user_path(value=None):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
        try: current,kind=winreg.QueryValueEx(key,'Path')
        except FileNotFoundError: current,kind='',winreg.REG_EXPAND_SZ
        if value is not None: winreg.SetValueEx(key,'Path',0,kind,value)
    return current


def path_parts(value):
    return [os.path.normcase(os.path.normpath(os.path.expandvars(p))) for p in value.split(';') if p]


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uninstall',action='store_true')
    p.add_argument('--destination',type=Path)
    p.add_argument('--skills-home',type=Path)
    p.add_argument('--no-path',action='store_true',help='Install the launcher without adding its folder to user PATH.')
    a=p.parse_args(argv)
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'CodexTokenMods'
    dest=(a.destination or base/'easy-start').resolve()
    if os.name=='nt' and dest.name!='easy-start': raise SystemExit('Choose an installation directory named easy-start so the portable launcher can find it.')
    skills=(a.skills_home or Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'skills').resolve()
    skill=skills/'token-tools'; bin_dir=dest.parent/'bin'; launcher=bin_dir/('tokenmods.cmd' if os.name=='nt' else 'tokenmods')
    core=base/'marketplace/plugins/token-mods'
    if dest==core or core in dest.parents: raise SystemExit('The easy interface must stay outside the existing hook plugin.')
    state=dest/'installation.json'
    saved=json.loads(state.read_text(encoding='utf-8')) if state.exists() else None
    if saved and saved.get('owner')!='token-mods-easy-start': raise SystemExit('This destination belongs to something else.')
    if saved and set(saved['files'])!={str(dest/'tokenmods.py'),str(skill/'SKILL.md'),str(launcher)}: raise SystemExit('The installation record does not match these owned destinations.')
    if a.uninstall:
        if not saved: raise SystemExit('No owned easy-interface installation found here.')
        for file,digest in saved['files'].items():
            target=Path(file)
            # Remove only known files that still match this install, preserving user edits.
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==digest: target.unlink()
        if saved.get('path_added') and os.name=='nt' and not a.no_path:
            current=user_path(); normalized=os.path.normcase(os.path.normpath(str(bin_dir)))
            user_path(';'.join(part for part in current.split(';') if not part or os.path.normcase(os.path.normpath(os.path.expandvars(part)))!=normalized))
        state.unlink()
        for folder in (skill,bin_dir,dest):
            try: folder.rmdir()
            except OSError: pass
        print('Removed the easy interface. Token Mods, hooks and recorded chats remain installed.'); return
    if not (core/'tools_api.py').is_file() and not a.destination: raise SystemExit('Install the main Token Mods 1.1.0 package first.')
    if skill.exists() and not saved: raise SystemExit('An existing token-tools skill is present; refusing to replace it.')
    if launcher.exists() and not saved: raise SystemExit('An existing tokenmods launcher is present; refusing to replace it.')
    dest.mkdir(parents=True,exist_ok=True); skill.mkdir(parents=True,exist_ok=True); bin_dir.mkdir(parents=True,exist_ok=True)
    files={}
    for source,target in ((SOURCE/'tokenmods.py',dest/'tokenmods.py'),(SOURCE/'skill/SKILL.md',skill/'SKILL.md')):
        if target.exists() and saved and hashlib.sha256(target.read_bytes()).hexdigest()!=saved['files'].get(str(target)):
            backup=dest/(target.name+'.before-'+hashlib.sha256(target.read_bytes()).hexdigest()[:10]); shutil.copy2(target,backup)
        shutil.copy2(source,target); files[str(target)]=hashlib.sha256(target.read_bytes()).hexdigest()
    if os.name=='nt':
        launcher.write_text('@echo off\r\nrem token-mods-easy-start\r\nsetlocal\r\nset "PYTHONUTF8=1"\r\n"%LOCALAPPDATA%\\CodexTokenMods\\runtime\\Scripts\\python.exe" "%~dp0..\\easy-start\\tokenmods.py" %*\r\n',encoding='ascii',newline='')
    else:
        import shlex
        launcher.write_text('#!/bin/sh\nexec python3 '+shlex.quote(str(dest/'tokenmods.py'))+' "$@"\n',encoding='utf-8'); launcher.chmod(0o755)
    files[str(launcher)]=hashlib.sha256(launcher.read_bytes()).hexdigest()
    added=bool(saved and saved.get('path_added'))
    if os.name=='nt' and not a.no_path:
        current=user_path()
        if os.path.normcase(os.path.normpath(str(bin_dir))) not in path_parts(current):
            user_path(current+(';' if current and not current.endswith(';') else '')+str(bin_dir)); added=True
            try:
                import ctypes
                result=ctypes.c_size_t()
                ctypes.windll.user32.SendMessageTimeoutW(0xffff,0x1a,0,'Environment',2,1000,ctypes.byref(result))
            except (AttributeError,OSError): pass
    state.write_text(json.dumps(dict(owner='token-mods-easy-start',files=files,path_added=added),indent=2),encoding='utf-8')
    print('Installed. Open a fresh Codex chat and ask normally: "Token Mods, give me a handoff."')
    print('In a new terminal: tokenmods | tokenmods handoff | tokenmods full | tokenmods pause | tokenmods resume')
    print('Existing hook commands and approval/sandbox settings were not changed.')


if __name__=='__main__': main()
