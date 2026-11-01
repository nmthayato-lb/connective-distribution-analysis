#!/usr/bin/env python3
"""3 誌の千字率・100 文率・6 分類の構成比・語形別の件数を集計する。

使い方: python3 scripts/20_rates.py --in <10_count.py の出力フォルダ>... --out <出力フォルダ>
  千字率 = 主集計 ÷ 地の文の字数 × 1,000
  100 文率 = 主集計 ÷ 地の文を含む文の数 × 100（「接続表現を含む文の割合」ではない）
  逆接% = 逆接・対比の件数 ÷ 主集計 × 100
範囲は「全形式」と「論説・論文」（『税法学』の論説、論叢の論文、ジャーナルの論説）の 2 つ。
"""
import argparse, collections, csv
from pathlib import Path
CL = ['添加・並列', '逆接・対比', '説明・換言', '補足・留保', '理由・帰結', '順序・継起']
ORDER = ['税法学', '税大論叢', '税大ジャーナル']


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig')))


def write(p, rows):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--in', dest='inp', nargs='+', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    papers, occ = [], []
    for d in a.inp:
        papers += read(Path(d) / '論文別.csv')
        jr = {p['ID']: p['誌名'] for p in read(Path(d) / '論文別.csv')}
        occ += [dict(o, 誌名=jr[o['ID']]) for o in read(Path(d) / '出現.csv') if o['主集計'] == 'True']
    form = {p['ID']: p['形式'] for p in papers}
    rates, words = [], []
    for scope in ['全形式', '論説・論文']:
        for j in ORDER:
            ps = [p for p in papers if p['誌名'] == j and (scope == '全形式' or p['形式'] in ('論説', '論文'))]
            if not ps:
                continue
            ids = {p['ID'] for p in ps}
            n = sum(int(p['主集計']) for p in ps); ch = sum(int(p['地の文の字数']) for p in ps); ss = sum(int(p['地の文を含む文の数']) for p in ps)
            c = {k: sum(int(p['件数_' + k]) for p in ps) for k in CL}
            rates.append({'範囲': scope, '誌名': j, '本数': len(ps), '主集計': n, '地の文の字数': ch, '地の文を含む文の数': ss,
                          '千字率': round(n / ch * 1000, 3), '100文率': round(n / ss * 100, 3), '逆接%': round(c['逆接・対比'] / n * 100, 3),
                          **{'構成比%_' + k: round(c[k] / n * 100, 3) for k in CL}, **{'件数_' + k: c[k] for k in CL}})
            wc = collections.Counter((o['新6分類'], o['語形_統合後']) for o in occ if o['ID'] in ids)
            for (k, w), m in sorted(wc.items(), key=lambda x: (CL.index(x[0][0]) if x[0][0] in CL else 9, -x[1])):
                words.append({'範囲': scope, '誌名': j, '6分類': k, '語形': w, '件数': m, '千字率': round(m / ch * 1000, 4)})
    write(out / '3誌_率と6分類.csv', rates); write(out / '3誌_語形別.csv', words)
    for r in rates:
        print(r['範囲'], r['誌名'], r['本数'], r['主集計'], r['地の文の字数'], r['千字率'], r['100文率'], r['逆接%'])


if __name__ == '__main__':
    main()
