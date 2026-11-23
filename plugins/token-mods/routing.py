"""Conservative extraction and independent-worker policy; no paid classifier."""
import json
import re


def decision(prompt):
    words = set(re.findall(r'[a-z]+', prompt.lower()))
    high = words & {'architecture','audit','investigate','debug','prove','design','security','concurrency','migration','verify','compare'}
    easy = words & {'extract','format','list','translate','sort','summarize','summarise'}
    changes = words & {'implement','fix','write','change','delete','run','build','deploy','rename'}
    tier = 'deep' if high else 'quick' if easy and not changes and len(prompt) <= 400 else 'standard'
    return dict(tier=tier, effort={'quick':'low','standard':'medium','deep':'high'}[tier],
                confidence=0.8 if high or tier == 'quick' else None,
                confidence_kind='uncalibrated rule score',
                reason='risk/verification vocabulary' if high else 'bounded read-only task' if tier == 'quick' else 'ambiguous or ordinary work; keep defaults')


def text_blocks(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(text_blocks(x) for x in value)
    if isinstance(value, dict):
        if value.get('type') in ('image','audio','resource_link') or value.get('isError'):
            raise ValueError('media, resource handles, or failed result')
        if value.get('type') == 'text':
            return value.get('text', '')
        if 'content' in value:
            return text_blocks(value['content'])
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def excerpts(text, query, cap=5000):
    terms = set(re.findall(r'\w+', query.casefold()))
    chunks = []
    # Fixed chunks bound memory even for JSON on one enormous line.
    for number, line in enumerate(text.splitlines(), 1):
        for offset in range(0, len(line), 1200):
            part = line[offset:offset + 1200]
            score = len(terms.intersection(re.findall(r'\w+', part.casefold())))
            chunks.append((score, number, offset, part))
    selected, used = [], 0
    for score, number, offset, part in sorted(chunks, key=lambda x: (-x[0], x[1], x[2])):
        entry = f'L{number} char {offset}: {part}'
        if used + len(entry) > cap:
            continue
        selected.append((number, offset, entry)); used += len(entry) + 1
        if used >= cap - 200:
            break
    return '\n'.join(x[2] for x in sorted(selected))


PAGING = re.compile(r'^(page|page_number|current_page|per_page|page_size|page_count|pages|total_pages|count|total|total_count|has_more|has_next|has_next_page|next_page|next_page_token|next_cursor|cursor|offset|limit)$', re.I)


def paging(value, prefix='', out=None):
    out = {} if out is None else out
    if isinstance(value, dict):
        for key, v in value.items():
            name = prefix + '.' + key if prefix else key
            if PAGING.match(key) and not isinstance(v, (dict, list)):
                out[name] = v
            elif isinstance(v, (dict,list)):
                paging(v, name, out)
            elif key == 'text' and isinstance(v, str) and v.lstrip().startswith(('{','[')):
                try:
                    paging(json.loads(v), name, out)
                except ValueError:
                    pass
    elif isinstance(value, list):
        for i, v in enumerate(value):
            paging(v, prefix + f'[{i}]', out)
    return out


def instruction_path(text):
    return bool(re.search(r'(?i)(?:AGENTS|CLAUDE|SKILL)\.md|[/\\]skills[/\\]|[/\\]memor(?:y|ies)[/\\]|settings(?:\.local)?\.json|switches\.json|config\.toml', text))


def reader_command(command):
    # Intentionally narrow: arbitrary programs, pipelines, substitutions, writes and test output pass.
    if instruction_path(command) or re.search(r'(?i)\.(?:ipynb|png|jpe?g|gif|webp|docx|xlsx|pptx|pdf)\b',command) or re.search(r'[|;&`\n]|\$\(|>', command):
        return False
    if re.search(r'(?i)(?:--files(?:-with(?:out)?-matches)?|--count|\s-[lcL]\b)', command):
        return False
    return bool(re.match(r'(?i)^\s*(?:Get-Content|gc|cat|head|tail|rg|grep)\s+', command))
