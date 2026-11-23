"""Chunked whole-source notes, including PDF text; every coverage gap is explicit."""
from pathlib import Path
from runner import run_worker
from store import save_original


def source_notes(p):
    path=Path(p['path']).resolve(); chunks=[]; gaps=[]
    if path.suffix.lower()=='.pdf':
        from pypdf import PdfReader
        if path.stat().st_size>32000000: raise ValueError('PDF exceeds 32 MB; use an explicit page/text export.')
        reader=PdfReader(path); texts=[]
        for i,page in enumerate(reader.pages[:200]):
            content=page.extract_text()
            if not content: gaps.append(dict(page=i+1,reason='No text layer; visual/OCR inspection required'))
            texts.append(f'=== Original PDF page {i+1} ===\n'+(content or '[No text layer; use visual/OCR inspection]'))
        if len(reader.pages)>200: gaps.append(dict(pages=[201,len(reader.pages)],reason='200-page extraction cap; use page ranges'))
        text='\n'.join(texts); kind='PDF text layer; page labels refer to original PDF'
    else:
        if path.stat().st_size>8_000_000: raise ValueError('Source exceeds 8 MB. Use bounded range reads or a text export.')
        raw=path.read_bytes()
        if b'\0' in raw: raise ValueError('Binary source needs a text export.')
        text=raw.decode('utf-8-sig',errors='replace'); kind='UTF-8 text; character offsets refer to the original decoded source'
    maximum=960000; reports=[]
    if len(text)>maximum: gaps.append(dict(start=maximum,end=len(text),reason='explicit 960k-character coverage cap'))
    for start in range(0,min(len(text),maximum),120000):
        end=min(start+120000,len(text),maximum)
        part=f'Original source: {path}\nCoverage: decoded characters [{start},{end}) of {len(text)}. {kind}\n'+text[start:end]
        file=save_original(part,'txt')
        try: r=run_worker('Write source notes for this part, retaining original references and everything needed for: '+p['question'],
            p.get('module','input-router'),p.get('session',''),model=p.get('model'),effort=p.get('effort') or 'low',file=file,timeout=p.get('timeout'))
        except Exception as e: r=dict(accepted=False,brief='',usage=None,error=str(e))
        reports.append(r)
        if not r['accepted']: gaps.append(dict(start=start,end=end,reason=r.get('error') or r.get('status','worker failure')))
    accepted=[r['brief'] for r in reports if r['accepted']]
    # Keep every part's notes rather than silently dropping detail in another lossy synthesis.
    body='\n\n'.join(f'## Part {i+1}\n'+r['brief'] for i,r in enumerate(reports))
    evidence=save_original(body,'txt')
    return dict(accepted=bool(accepted),partial=bool(gaps),brief=body,source=str(path),coverage=dict(characters=min(len(text),maximum),total_characters=len(text),kind=kind),
                gaps=gaps,evidence=evidence,worker_usage=[r.get('usage') for r in reports],usage=None,usage_complete=False,
                note='Per-worker provider counts are separate; no aggregate count is fabricated for a failed part.')
