"""Pure read classification, loss-aware connector trimming and interval coverage."""
import json
import re
import shlex
from routing import instruction_path, paging

READERS={'get-content','gc','cat','head','tail','sed','awk','gawk','nl','jq','yq','curl','wget','grep','rg','bat','more','less','tac','zcat','strings','pdftotext'}
HELPERS={'sort','sort-object','select-object','select-string','where-object','uniq','cut','tr','column','fold','expand','wc'}
DROP=re.compile(r'(?i)^(?:avatar(?:_url)?|thumbnail(?:_url)?|icon(?:_url)?|image_url|logo_url|html|.*_html|rich_text|.*_rich_text|__typename|etag|_links|_meta|color|.*_color|emoji|placeholder)$')


def pipeline(command):
    """Split unquoted pipes, reject execution structure rather than interpreting it."""
    parts=[]; buf=''; quote=None
    for c in command:
        if quote:
            buf+=c
            if c==quote: quote=None
        elif c in "\"'": quote=c; buf+=c
        elif c=='|': parts.append(buf.strip()); buf=''
        elif c in ';&`\n<>': return []
        else: buf+=c
    if quote or '$(' in command or '${' in command: return []
    return parts+[buf.strip()]


def read_plan(command):
    if instruction_path(command) or re.search(r'(?i)\.(?:ipynb|png|jpe?g|gif|webp|docx|xlsx|pptx|pdf)\b',command): return None
    parts=pipeline(command)
    if not parts: return None
    groups=[]
    for part in parts:
        try: tokens=[x.strip('"\'') for x in shlex.split(part,posix=False)]
        except ValueError: return None
        if not tokens: return None
        name=tokens[0].lower()
        if name not in READERS|HELPERS: return None
        if re.search(r'(?i)--files\b|--files-with(?:out)?-matches|--count|(?:^|\s)-[lcL]\b|--pre\b|--exec\b',part): return None
        groups.append((name,tokens[1:]))
    if not any(name in READERS for name,_ in groups): return None
    source=None; start=1; limit=None; tail=False
    first,args=groups[0]
    if first=='sed' and len(args)>=3 and args[0]=='-n':
        match=re.fullmatch(r'(\d+)(?:,(\d+))?p',args[1])
        if match:
            source=args[-1]; start=int(match[1]); limit=int(match[2] or match[1])-start+1
    if first in ('get-content','gc','cat','head','tail','nl','bat'):
        positional=[]; i=0
        while i<len(args):
            arg=args[i]; lo=arg.lower()
            if lo in ('-literalpath','-path') and i+1<len(args): positional.append(args[i+1]); i+=2; continue
            if lo in ('-totalcount','-head','-first','-n') and i+1<len(args):
                try: limit=int(args[i+1])
                except ValueError: return None
                i+=2; continue
            if lo=='-tail' and i+1<len(args): tail=True; i+=2; continue
            if lo not in ('-raw','-encoding','utf8','utf-8') and not arg.startswith('-'): positional.append(arg)
            i+=1
        if len(positional)==1: source=positional[0]
        if first=='tail': tail=True
    for name,args in groups[1:]:
        if name=='select-object':
            for key,attribute in (('-skip','start'),('-first','limit')):
                lower=[s.lower() for s in args]
                if key in lower:
                    try: value=int(args[lower.index(key)+1])
                    except (ValueError,IndexError): return None
                    if attribute=='start': start=value+1
                    else: limit=value
    return dict(source=source,start=start,limit=limit,tail=tail,whole=source is not None and limit is None and not tail and len(groups)==1)


def trim_json(value):
    """Remove only presentation/duplicate metadata; never cap arbitrary long text."""
    if isinstance(value,list): return [trim_json(v) for v in value]
    if isinstance(value,dict):
        out={}
        for k,v in value.items():
            if DROP.fullmatch(k): continue
            if k=='text' and isinstance(v,str):
                try: v=json.dumps(trim_json(json.loads(v)),ensure_ascii=False,indent=2)
                except ValueError: pass
            else: v=trim_json(v)
            out[k]=v
        return out
    return value


def remember(db,scope,source,start,count,total,notes=None):
    row=db.execute('SELECT ranges,total,notes FROM coverage WHERE scope=? AND source=?',(scope,source)).fetchone()
    ranges=json.loads(row[0]) if row else []; previous=sum(b-a for a,b in ranges)
    total=total or (row[1] if row else 0)
    ranges.append([max(1,start),max(1,start)+count]); merged=[]
    for a,b in sorted(ranges):
        if merged and a<=merged[-1][1]: merged[-1][1]=max(b,merged[-1][1])
        else: merged.append([a,b])
    db.execute('INSERT OR REPLACE INTO coverage VALUES(?,?,?,?,?)',(scope,source,json.dumps(merged),total,notes or (row[2] if row else None)))
    return dict(previous_share=previous/total if total else None,lines_seen=sum(b-a for a,b in merged),total_lines=total,notes=notes or (row[2] if row else None))
