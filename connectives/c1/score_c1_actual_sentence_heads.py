#!/usr/bin/env python3
"""直接引用の前後（直前文・引用を含む文・直後文）ごとに、文頭に接続表現がある文の割合を文 ID 単位で数える。"""
import argparse,csv,collections,hashlib
from pathlib import Path

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def yes(x):return str(x).strip().lower() in {'true','1','yes'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mapping',required=True);ap.add_argument('--sentences',required=True);ap.add_argument('--base',required=True);ap.add_argument('--expanded',required=True);ap.add_argument('--outdir',default=str(Path(__file__).parent));a=ap.parse_args()
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    mapping=read(a.mapping); corpus=read(a.sentences)
    genre={ (r['ID'],r['文ID']):r.get('論文区分','') for r in corpus }
    body={(r['ID'],r['文ID']) for r in corpus if yes(r.get('地の文あり',''))}
    ids_by_scope={}; occ_by_scope={}
    for name,path in [('53+short',a.base),('72+short',a.expanded)]:
        ids_by_scope[name]=set()
        occ_by_scope[name]=[]
        for r in read(path):
            if r.get('位置')!='狭義文頭': continue
            if r.get('判定')=='主集計候補':
                ids_by_scope[name].add((r.get('ID',''),r.get('文ID','')))
                occ_by_scope[name].append(r)
    mapped_by_stratum=collections.defaultdict(set)
    mapped_union=set(); status_count=collections.Counter(); quote_keys=set(); c1_papers=set()
    for r in mapping:
        pos=r.get('位置',''); status=r.get('最終状態',''); status_count[(pos,status)]+=1
        if r.get('引用番号'):
            quote_keys.add((r.get('ID',''),r.get('引用番号','')))
            c1_papers.add(r.get('ID',''))
        # Main analysis uses at most one ground-text sentence for each C1 position.
        sentids=[x for x in r.get('主対応本文文ID','').split(';') if x]
        for sid in sentids:
            key=(r.get('ID',''),sid)
            if key not in genre:continue
            g=r.get('論文区分',''); c=r.get('引用分類','')
            for stratum in ((g,c,pos),(g,'全種別',pos),('全体',c,pos),('全体','全種別',pos)):
                mapped_by_stratum[stratum].add(key)
            mapped_union.add(key)
    scopes=sorted(mapped_by_stratum)
    groups=[]
    for g,c,pos in scopes:
        groups.append((g,c,pos,mapped_by_stratum[(g,c,pos)]))
    # Ensure the whole corpus's C1-scope general-text reference is available beside each role.
    c1scope=body-mapped_union
    c1scope141={k for k in body if k[0] in c1_papers}-mapped_union
    all141={k for k in body if k[0] in c1_papers}
    for label,refs in [('参考_C1scope一般文_全本',c1scope),('C1scope一般文_主比較_141本',c1scope141),('参考_全候補文_全本',body),('参考_全候補文_141本',all141)]:
        for g in ('全体','論説','判例研究'):
            chosen=refs if g=='全体' else {k for k in refs if genre.get(k)==g}
            groups.append((g,label,'基準',chosen))
    rows=[]
    # C1 mapping uncertainty is explicit in every row; denominators are unique sentence IDs.
    for g,c,pos,den_ids in groups:
        row={'論文区分':g,'引用分類':c,'位置':pos,'一意本文文ID分母':len(den_ids)}
        for scope,hits in ids_by_scope.items():
            n=sum(k in hits for k in den_ids)
            row[f'{scope}_文頭あり一意文ID']=n
            row[f'{scope}_文頭あり率_pct']=round(100*n/len(den_ids),6) if den_ids else ''
        row['分母定義']='位置表は主対応した地の文あり実文ID。C1scope主比較は直接引用の記録がある141本の地の文から主対応文IDのみ除外。全本の集合は参考。未配置C1窓が基準集合に残る可能性がある。'
        rows.append(row)
    with (out/'分析2_本文実文頭率_53short_vs_72short.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    ranking=[]
    for g,c,pos,den_ids in groups:
        if pos=='基準': continue
        for scope,occs in occ_by_scope.items():
            eligible=[r for r in occs if (r.get('ID',''),r.get('文ID','')) in den_ids]
            terms=collections.defaultdict(list)
            for r in eligible:
                terms[(r.get('新6分類',''),r.get('語形_統合後',''),r.get('表記_統合前',''))].append(r)
            ranked=sorted(terms.items(),key=lambda kv:(-len({(r['ID'],r['文ID']) for r in kv[1]}),-len(kv[1]),kv[0]))
            for rank,((cls,merged,rawform),hits) in enumerate(ranked,1):
                ranking.append({'論文区分':g,'引用分類':c,'位置':pos,'語彙範囲':scope,'順位':rank,'新6分類':cls,'語形_統合後':merged,'表記_統合前':rawform,'異なる実文ID数':len({(r['ID'],r['文ID']) for r in hits}),'出現数':len(hits),'異なる論文ID数':len({r['ID'] for r in hits})})
    with (out/'分析2_語形ランキング_C1窓別.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=list(ranking[0]) if ranking else ['論文区分','引用分類','位置','語彙範囲','順位','新6分類','語形_統合後','表記_統合前','異なる実文ID数','出現数','異なる論文ID数']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranking)
    # Window coverage and uniqueness ledger by paper type, citation kind, and role.
    countrows=[]
    keys=sorted(set((r.get('論文区分',''),r.get('引用分類',''),r.get('位置','')) for r in mapping))
    # Add overall strata without double counting a sentence within a stratum.
    keys += sorted({(g,'全種別',pos) for g,_,pos in keys})
    keys += sorted({('全体',c,pos) for _,c,pos in keys})
    keys += sorted({('全体','全種別',pos) for _,_,pos in keys})
    keys=sorted(set(keys))
    for g,c,pos in keys:
        subset=[r for r in mapping if r.get('位置','')==pos and (g=='全体' or r.get('論文区分','')==g) and (c=='全種別' or r.get('引用分類','')==c)]
        good=[r for r in subset if r.get('新本文文ID')]
        c1windows={(r.get('ID'),r.get('引用番号')) for r in subset if r.get('引用番号')}
        pure={'matched_pure_quote_only','mask_projection_pure_quote_only','offset_projection_pure_quote_only'}
        countrows.append({'論文区分':g,'引用分類':c,'位置':pos,'C1窓レコード数':len(subset),'C1引用単位数':len(c1windows),'地の文主対応窓数':sum(bool(r.get('主対応本文文ID')) for r in subset),'主対応一意地の文文ID数':len({(r['ID'],r['主対応本文文ID']) for r in subset if r.get('主対応本文文ID')}),'参考_全重複地の文対応窓数':sum(bool(r.get('新本文文ID_地の文')) for r in subset),'参考_全重複一意地の文文ID数':len({(r['ID'],sid) for r in subset for sid in r.get('新本文文ID_地の文','').split(';') if sid}),'挿入窓_複数地の文保留数':sum(r.get('主対応選定状態')=='hold_multiple_ground_sentences_in_insertion_window' for r in subset),'純引用のみ窓数_全経路':sum(r.get('最終状態') in pure for r in subset),'純引用のみ_直接照合':sum(r.get('最終状態')=='matched_pure_quote_only' for r in subset),'純引用のみ_保持区間投影':sum(r.get('最終状態') in {'mask_projection_pure_quote_only','offset_projection_pure_quote_only'} for r in subset),'新本文未対応窓数':sum(not r.get('新本文文ID') and r.get('最終状態') not in {'empty_window'} for r in subset),'mask_overlap窓数':sum(r.get('脚注mask_overlap')=='yes' for r in subset),'mask_overlap未解決数':sum(r.get('最終状態')=='unresolved_mask_overlap' for r in subset)})
    with (out/'分析2_C1窓再配置カバレッジ.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(countrows[0]));w.writeheader();w.writerows(countrows)
    with (out/'分析2_計算メタデータ.txt').open('w',encoding='utf-8') as f:
        for name,p in [('mapping',a.mapping),('sentences',a.sentences),('base_occurrences',a.base),('expanded_occurrences',a.expanded)]:f.write(f'{name}={p}\n{name}_sha256={sha(p)}\n')
        f.write(f'C1_quote_units={len(quote_keys)}\nC1_position_rows={len(mapping)}\nbody_sentence_ids={len(body)}\nC1_papers={len(c1_papers)}\nC1scope_general_sentence_ids_reference_allpapers={len(c1scope)}\nC1scope_general_sentence_ids_primary_141papers={len(c1scope141)}\n')
        for (pos,status),n in sorted(status_count.items()):f.write(f'{pos}\t{status}\t{n}\n')
    print(f'wrote {len(rows)} rate rows and {len(countrows)} coverage rows; unique C1 quote IDs={len(quote_keys)}')
if __name__=='__main__':main()
