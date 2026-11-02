#!/usr/bin/env python3
"""論文に出てくる集計値を、出現表・分母表・引用対応表から計算し JSON に書く。

引数: 組の名前 分析1フォルダ 主集計条件の出現表 分析2フォルダ 引用対応表 出力JSON
  分析1フォルダ: ID別分母・引用span.csv と occurrences_expanded.csv を置いたフォルダ（30_c1_and_numbers.py が作る）
  分析2フォルダ: score_c1_actual_sentence_heads.py と cross_citation_type_x_sixclass.py の出力
値は丸めずに入れる。
"""
import csv, json, sys, collections
from pathlib import Path
def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
CL=['添加・並列','逆接・対比','説明・換言','補足・留保','理由・帰結','順序・継起']
POS=['直前文','引用挿入文','直後文']
def main(name,a1,occp,a2,mapp,out):
    a1=Path(a1); a2=Path(a2); V={}
    den=read(a1/'ID別分母・引用span.csv')
    papers=collections.Counter(r['論文区分'] for r in den); chars=collections.Counter()
    for r in den: chars[r['論文区分']]+=int(r['集計分母_after_masked'])
    V['本数_全体']=len(den); V['本数_論説']=papers['論説']; V['本数_判例研究']=papers['判例研究']
    V['字数_全体']=sum(chars.values()); V['字数_論説']=chars['論説']; V['字数_判例研究']=chars['判例研究']
    occ=read(occp)
    main=[r for r in occ if r['位置']=='狭義文頭' and r['判定']=='主集計候補']
    V['出現_延べ']=len(occ); V['主集計']=len(main)
    for g in ('論説','判例研究'): V['主集計_'+g]=sum(r['論文区分']==g for r in main)
    j=collections.Counter(r['判定'] for r in occ)
    V['引用内部']=j['除外_引用内部']; V['語句並立・文中並立']=j['別掲_語句並立']+j['別掲_文中並立']
    V['節頭・節末等']=sum(1 for r in occ if r['判定']=='除外_位置対象外' or (r['判定']=='主集計候補' and r['位置'] in('節頭候補','節末候補')))
    V['非接続等']=j['除外_非接続']+j['除外_辞書外複合語']
    V['千字率_全体']=V['主集計']/V['字数_全体']*1000; V['1論文平均_全体']=V['主集計']/V['本数_全体']
    for c in CL:
        n=sum(r['新6分類']==c for r in main); V['件数_'+c]=n; V['構成比_'+c]=n/V['主集計']*100; V['千字率_'+c]=n/V['字数_全体']*1000
        for g in ('論説','判例研究'):
            m=sum(r['新6分類']==c and r['論文区分']==g for r in main)
            V[f'件数_{g}_{c}']=m; V[f'構成比_{g}_{c}']=m/V['主集計_'+g]*100; V[f'千字率_{g}_{c}']=m/V['字数_'+g]*1000
    for g in ('論説','判例研究'): V['千字率_'+g]=V['主集計_'+g]/V['字数_'+g]*1000
    f=collections.Counter(r['語形_統合後'] for r in main)
    for k,v in f.items(): V['語形_'+k]=v
    V['反転計']=sum(f[k] for k in ['しかし','ところが','とはいえ','だが','にもかかわらず','けれども'])
    V['対比計']=sum(f[k] for k in ['一方','これに対して','その一方で','それに対して','逆に','反面'])
    V['また_全体比']=f['また']/V['主集計']*100
    V['上位2分類_構成比']=(V['件数_添加・並列']+V['件数_逆接・対比'])/V['主集計']*100
    V['なお+ただし_補足内比']=(f['なお']+f['ただし'])/V['件数_補足・留保']*100
    V['もっとも_全体比']=f['もっとも']/V['主集計']*100; V['もっとも_千字率']=f['もっとも']/V['字数_全体']*1000; V['もっとも_1論文平均']=f['もっとも']/V['本数_全体']
    per=collections.Counter(r['ID'] for r in main if r['語形_統合後']=='もっとも')
    ids=[r['ID'] for r in den]
    V['もっとも0回の本数']=sum(1 for i in ids if per[i]==0); V['もっとも0回の比率']=V['もっとも0回の本数']/len(ids)*100
    top=sorted(per.values(),reverse=True)[:10]; V['もっとも上位10本']=sum(top); V['もっとも上位10本_比']=sum(top)/f['もっとも']*100
    V['説明/理由_倍率']=V['件数_説明・換言']/V['件数_理由・帰結']
    V['すなわち+つまり']=f['すなわち']+f['つまり']; V['例えば+具体的には']=f['例えば']+f['具体的には']
    ex=[r for r in read(a1/'occurrences_expanded.csv') if r['位置']=='狭義文頭' and r['判定']=='主集計候補' and r['新6分類']=='辞書外19_別枠' and r['語形_統合後']!='むしろ']
    fe=collections.Counter(r['語形_統合後'] for r in ex)
    V['別枠_計']=len(ex)
    for k in ['この点','このように','そこで','そうすると']: V['別枠_'+k]=fe[k]
    V['別枠_一方で+他方で']=fe['一方で']+fe['他方で']; V['別枠_その上で+そのうえ+その上']=fe['その上で']+fe['そのうえ']+fe['その上']
    # 分析2
    mp=read(mapp)
    q={}
    for r in mp:
        if r['引用番号']: q[(r['ID'],r['引用番号'])]=(r['論文区分'],r['引用分類'])
    V['引用_全体']=len(q)
    for g in ('論説','判例研究'):
        n=sum(1 for v in q.values() if v[0]==g); V['引用_'+g]=n
        for t in ('法令・通達等','判決文','学説','その他'):
            m=sum(1 for v in q.values() if v==(g,t)); V[f'引用_{g}_{t}']=m; V[f'引用比_{g}_{t}']=m/n*100
    rate=read(a2/'分析2_本文実文頭率_53short_vs_72short.csv')
    for r in rate:
        key=(r['論文区分'],'基準' if r['位置']=='基準' else r['引用分類'],r['位置'])
        if r['位置']=='基準' and 'C1scope一般文_主比較' not in r['引用分類']: continue
        V[f'分析2_分母_{key[0]}_{key[1]}_{key[2]}']=int(r['一意本文文ID分母'])
        V[f'分析2_分子_{key[0]}_{key[1]}_{key[2]}']=int(r['53+short_文頭あり一意文ID'])
        V[f'分析2_率_{key[0]}_{key[1]}_{key[2]}']=float(r['53+short_文頭あり率_pct'])
    for r in read(a2/'分析2_引用種別x6分類_base主表基準.csv'):
        V[f"分析2_分類率_{r['論文区分']}_{r['引用分類']}_{r['位置']}_{r['新6分類']}"]=float(r['文頭あり本文文ID率_pct'] or 0)
    # 添加・並列の占める割合（論説、表3の12行）
    sh=[]
    for t in ('全種別','法令・通達等','判決文','学説'):
        for p in POS:
            sh.append(V[f'分析2_分類率_論説_{t}_{p}_添加・並列']/V[f'分析2_率_論説_{t}_{p}']*100)
    V['添加並列の占める割合_最小']=min(sh); V['添加並列の占める割合_最大']=max(sh)
    V['添加並列が最多でない行数']=sum(1 for t in ('全種別','法令・通達等','判決文','学説') for p in POS
        if V[f'分析2_分類率_論説_{t}_{p}_添加・並列']<max(V[f'分析2_分類率_論説_{t}_{p}_{c}'] for c in CL))
    # 語形別の文数（位置ごとの主対応文に限る）
    occ_by={}
    for r in main: occ_by.setdefault((r['ID'],r['文ID']),[]).append(r)
    exall=[r for r in read(a1/'occurrences_expanded.csv') if r['位置']=='狭義文頭' and r['判定']=='主集計候補']
    ex_by={}
    for r in exall: ex_by.setdefault((r['ID'],r['文ID']),[]).append(r)
    strata=collections.defaultdict(set)
    for r in mp:
        if r['位置'] not in POS: continue
        for sid in [x for x in r['主対応本文文ID'].split(';') if x]:
            strata[(r['論文区分'],r['引用分類'],r['位置'])].add((r['ID'],sid)); strata[(r['論文区分'],'全種別',r['位置'])].add((r['ID'],sid))
    for (g,t,p),ids in strata.items():
        c=collections.Counter(); ce=collections.Counter()
        for k in ids:
            for w in {o['語形_統合後'] for o in occ_by.get(k,[])}: c[w]+=1
            for w in {o['語形_統合後'] for o in ex_by.get(k,[])}: ce[w]+=1
        for w,n in c.items(): V[f'分析2_語形文数_{g}_{t}_{p}_{w}']=n
        for w,n in ce.items(): V[f'分析2_語形文数72_{g}_{t}_{p}_{w}']=n
        top=[w for w,_ in sorted(c.items(),key=lambda kv:(-kv[1],kv[0]))[:2]]
        V[f'分析2_上位2語形_{g}_{t}_{p}']='・'.join(top)
    Path(out).write_text(json.dumps(V,ensure_ascii=False,indent=1),encoding='utf-8')
    print(name,len(V))
if __name__=='__main__': main(*sys.argv[1:7])
