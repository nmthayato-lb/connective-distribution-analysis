#!/usr/bin/env python3
"""③の検査: 04_zeihougaku_footnote_mask.py の出力が、除いた範囲だけから再現できるかを確かめる。

使い方: python3 scripts/05_check_mask_outputs.py --manifest <04 に渡した CSV> --out <04 の出力フォルダ>
"""
import argparse, csv, hashlib, json, sys
from pathlib import Path

D = None

def rows(p):
    with Path(p).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    global D
    ap = argparse.ArgumentParser(); ap.add_argument('--manifest', required=True); ap.add_argument('--out', required=True); a = ap.parse_args()
    D = Path(a.out)
    manifest = rows(a.manifest)
    output = rows(D/'masked_manifest.csv')
    masks = rows(D/'masks_all.csv')
    small = rows(D/'small_blocks_all.csv')
    expected = {r['ID'] for r in manifest}
    outids = [r['ID'] for r in output]
    errs=[]; notes=[]
    if len(expected)!=len(manifest): errs.append('duplicate input IDs')
    if len(set(outids))!=len(outids): errs.append('duplicate output IDs')
    if set(outids)!=expected: errs.append(f'ID difference missing={sorted(expected-set(outids))} extra={sorted(set(outids)-expected)}')
    for r in output:
        doc=r['ID'];src=Path(r['土台本文']);dst=Path(r['masked本文'])
        if not src.is_file() or not dst.is_file():
            errs.append(f'{doc}: missing source or masked file'); continue
        raw=src.read_text(encoding='utf-8-sig'); masked=dst.read_text(encoding='utf-8-sig')
        if sha(src)!=r['土台SHA256']: errs.append(f'{doc}: source SHA mismatch')
        if sha(dst)!=r['maskedSHA256']: errs.append(f'{doc}: masked SHA mismatch')
        if len(raw)!=int(r['土台文字数']) or len(masked)!=int(r['mask後文字数']): errs.append(f'{doc}: character count mismatch')
        if len(raw)-len(masked)!=int(r['除外文字数']): errs.append(f'{doc}: removed char count mismatch')
        m=[x for x in masks if x['ID']==doc]
        spans=[]
        for x in m:
            a=int(x['source_start']); b=int(x['source_end'])
            if not (0<=a<b<=len(raw)): errs.append(f'{doc}: invalid mask range {a}:{b}'); continue
            if raw[a:b]!=x.get('除外原文',''): errs.append(f'{doc}: excluded text mismatch at {a}:{b}')
            spans.append((a,b))
        spans.sort(); merged=[]
        for a,b in spans:
            if merged and a<=merged[-1][1]: merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
            else: merged.append((a,b))
        rebuilt=[]; cur=0
        for a,b in merged:
            if a<cur: errs.append(f'{doc}: overlapping mask spans'); continue
            rebuilt.append(raw[cur:a]); cur=b
        rebuilt.append(raw[cur:])
        if ''.join(rebuilt)!=masked: errs.append(f'{doc}: output not reproduced by mask spans')
        removed=sum(b-a for a,b in merged)
        if removed!=len(raw)-len(masked): errs.append(f'{doc}: merged-span length {removed} differs from actual removed length')
        mapfile=D/'masked'/doc/'原Aからmask後_保持区間対応.csv'
        if mapfile.exists():
            segs=rows(mapfile); prevs=preve=0; prevout=0
            for s in segs:
                a,b=int(s['source_start']),int(s['source_end']); oa,ob=int(s['masked_start']),int(s['masked_end'])
                if a<preve or oa<prevout or b-a!=ob-oa: errs.append(f'{doc}: bad keep mapping segment {a}:{b}->{oa}:{ob}')
                if raw[a:b]!=masked[oa:ob]: errs.append(f'{doc}: keep mapping content mismatch {a}:{b}')
                preve=b;prevout=ob
            if sum(int(s['source_end'])-int(s['source_start']) for s in segs)!=len(masked): errs.append(f'{doc}: keep map does not cover output')
            if len(segs)>0 and preve>len(raw): errs.append(f'{doc}: keep map out of bounds')
        else: errs.append(f'{doc}: missing keep mapping')
    by_doc={d:sum(1 for r in small if r['ID']==d) for d in expected}
    no_boundary=[]
    for f in D.glob('masked/*/段別本文下端.csv'):
        for r in rows(f):
            if not r.get('body_last_y'): no_boundary.append((r['ID'],r['PDF_page'],r['column']))
    if no_boundary: notes.append('no body baseline: '+str(len(no_boundary))+' pairs '+repr(no_boundary[:25]))
    print(f'input={len(manifest)} output={len(output)} mask_rows={len(masks)} small_rows={len(small)}')
    print(f'input IDs present in output={len(set(outids)&expected)}/{len(expected)}')
    print('errors:',len(errs))
    for e in errs[:100]: print('ERROR',e)
    for n in notes: print('NOTE',n)
    return 1 if errs else 0

if __name__=='__main__': sys.exit(main())
