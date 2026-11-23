"""Explicit paid, bounded read-only source/research worker. No API key required."""
import argparse
import json
import sys
from runner import run_worker


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('source','research'))
    p.add_argument('question'); p.add_argument('--file'); p.add_argument('--session',default='')
    p.add_argument('--model'); p.add_argument('--effort',choices=('low','medium','high','xhigh','max','ultra'))
    p.add_argument('--timeout',type=int); p.add_argument('--cwd')
    a=p.parse_args()
    if a.mode=='source' and not a.file: p.error('--file is required')
    result=run_worker(a.question,'input-router' if a.mode=='source' else 'research-router',a.session,
        a.model,a.effort,a.file,cwd=a.cwd,timeout=a.timeout)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['accepted'] else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try: sys.exit(main())
    except (OSError,ValueError) as error: sys.exit(str(error))
