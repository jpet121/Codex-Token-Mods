"""Install Token Mods and its plain-language/short-command interface together."""
import argparse
from pathlib import Path
import subprocess
import sys

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--uninstall',action='store_true'); p.add_argument('--no-path',action='store_true',help='Leave the user PATH unchanged.'); a=p.parse_args()
    root=Path(__file__).parent
    steps=[root/'easy-start/install.py',root/'setup_port.py'] if a.uninstall else [root/'setup_port.py',root/'easy-start/install.py']
    for script in steps: subprocess.run([sys.executable,str(script)]+(['--uninstall'] if a.uninstall else [])+(['--no-path'] if a.no_path and script.parent.name=='easy-start' else []),check=True)

if __name__=='__main__': main()
