#!/usr/bin/env python3
"""引用の種別 × 6 分類の表（主集計の出現で数える）。"""
import argparse, csv, collections
from pathlib import Path

CLASSES=['添加・並列','逆接・対比','説明・換言','補足・留保','理由・帰結','順序・継起']
ROLES=['直前文','引用挿入文','直後文']
GENRES=['論説','判例研究','全体']

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--mapping',required=True)
    ap.add_argument('--occurrences',required=True)
    ap.add_argument('--out',default=str(Path(__file__).parent/'分析2_引用種別x6分類_base主表基準.csv'))
    a=ap.parse_args()
    mapping=read(a.mapping); occ=read(a.occurrences)
    byid=collections.defaultdict(list)
    for r in occ:
        if r.get('位置')=='狭義文頭' and r.get('判定')=='主集計候補':
            byid[(r.get('ID'),r.get('文ID'))].append(r)
    # Citation records and their unique ground-text sentence IDs per stratum.
    records=collections.defaultdict(dict)
    unresolved=collections.Counter()
    types=sorted({m.get('引用分類','') for m in mapping if m.get('引用分類')})
    for m in mapping:
        g=m.get('論文区分',''); cite=m.get('引用分類',''); role=m.get('位置','')
        if role not in ROLES:continue
        q=(m.get('ID',''),m.get('引用番号',''))
        # One C1 position contributes at most one primary ground-text sentence.
        ids={(m.get('ID',''),sid) for sid in m.get('主対応本文文ID','').split(';') if sid}
        scopes={(g,cite,role),(g,'全種別',role),('全体',cite,role),('全体','全種別',role)}
        for scope in scopes:
            records[scope].setdefault(q,set()).update(ids)
            if not ids:unresolved[scope]+=1
    types=['全種別']+types
    output=[]
    for g in GENRES:
      for cite in types:
       for role in ROLES:
        scope=(g,cite,role); quote_map=records.get(scope,{})
        all_q={(m.get('ID',''),m.get('引用番号','')) for m in mapping
               if m.get('位置')==role and (g=='全体' or m.get('論文区分')==g)
               and (cite=='全種別' or m.get('引用分類')==cite) and m.get('引用番号')}
        mapped_q={q for q in all_q if quote_map.get(q)}
        all_ids=set().union(*(quote_map.get(q,set()) for q in all_q)) if all_q else set()
        candidates_by_class={c:collections.defaultdict(list) for c in CLASSES}
        for key in all_ids:
            for r in byid.get(key,[]):
                cls=r.get('新6分類','')
                if cls in candidates_by_class:candidates_by_class[cls][key].append(r)
        for cls in CLASSES:
            hits=candidates_by_class[cls]
            term_ids=set(hits)
            hit_quotes={q for q in mapped_q if any(key in term_ids for key in quote_map.get(q,set()))}
            occurrence_count=sum(len(v) for v in hits.values())
            output.append({'論文区分':g,'引用分類':cite,'位置':role,'新6分類':cls,
              '語彙範囲':'53語形＋短形（base主表）','C1引用単位数':len(all_q),
              '地の文実文対応引用単位数':len(mapped_q),'一意対応地の文文ID分母':len(all_ids),
              '文頭あり本文文ID数':len(term_ids),
              '文頭あり本文文ID率_pct':round(100*len(term_ids)/len(all_ids),6) if all_ids else '',
              '候補出現個票数':occurrence_count,'文頭ありC1引用単位数':len(hit_quotes),
              '文頭ありC1引用単位率_pct':round(100*len(hit_quotes)/len(mapped_q),6) if mapped_q else '',
              '未対応C1窓数':unresolved[scope],
              '注記':'本文実文頭・主集計候補のみ。語形内部の引用出現は除外。率の分母は対応済み地の文文ID/引用単位に限定。'})
    p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
    print(f'wrote {len(output)} rows')
if __name__=='__main__':main()
