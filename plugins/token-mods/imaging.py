"""Explicit local preview. Never rewrites host media or claims image-token counts."""
from pathlib import Path
from store import database, log


def preview(source, target, scale=0.5, minimum=512, full=False, session=''):
    from PIL import Image, ImageOps
    if not 0.1 <= scale <= 1 or not 128 <= minimum <= 4096: raise ValueError('Invalid scale or minimum.')
    if source.resolve() == target.resolve(): raise ValueError('Use a separate target; originals are preserved.')
    with Image.open(source) as original:
        image=ImageOps.exif_transpose(original)
        w,h=image.size
        factor=1 if full else min(1,max(scale,minimum/max(w,h)))
        size=(max(1,round(w*factor)),max(1,round(h*factor)))
        image=image.convert('RGB').resize(size,Image.Resampling.LANCZOS)
        with target.open('xb') as f: image.save(f,format='PNG')
    result=dict(source=str(source.resolve()),path=str(target.resolve()),original=[w,h],preview=list(size),
                coordinate_frame=[w,h],point_to_original=[w/size[0],h/size[1]],
                measured_token_savings=None, note='Use the original for fine text and precise visual judgment.')
    with database() as db: log(db,session,'efficient-browser-use','preview',**result)
    return result
