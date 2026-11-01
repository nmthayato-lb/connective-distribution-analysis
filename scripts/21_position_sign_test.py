#!/usr/bin/env python3
"""論文の中の位置（5 等分）ごとの集計、前 40% 対 後 40% の符号検定、長さ 3 群別の集計。

使い方: python3 scripts/21_position_sign_test.py --in <10_count.py の出力フォルダ>... --out <出力フォルダ>

  位置: 各論文の地の文の字に順位 r（0 始まり）を付け、全字数 N に対して floor(5r/N) で 5 等分する。
        出現の位置は、その語の先頭の字の順位。
  条件: 全文／結び除外（結びの節より後を除く）／4 語の結び除外（結びの見出しが「おわりに」「結び」「むすび」「結語」の
        いずれかに当たる論文だけ除く）。結びの節がない論文は、除外の条件でも全文を使う。
        結びの節があるかどうかを決められなかった論文は、除外の条件から外す。
  向き: 論文ごとに 前（0〜40%）と 後（60〜100%）の 逆接・対比（または「しかし」）の構成比をくらべる。
        整数の交差積（後の該当数×前の件数 − 前の該当数×後の件数）の符号で決める。
  検定: 各側の件数が最低件数（主は 5、感度は 1）に満たない論文と同点の論文を除き、正確な両側二項検定（p = 2×下側確率、上限 1）。
  長さ: 誌・形式・条件ごとに全文の地の文の字数の昇順（同数は ID 順）に並べ、floor(順番×3/本数) で 3 群に分ける。
"""
import argparse, collections, csv, math
from pathlib import Path
CL = ['添加・並列', '逆接・対比', '説明・換言', '補足・留保', '理由・帰結', '順序・継起']
Q = ['0–20%', '20–40%', '40–60%', '60–80%', '80–100%']


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig')))


def write(p, rows):
    fields = list(dict.fromkeys(k for x in rows for k in x))
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def sign(hi, lo):
    n = hi + lo
    return min(1., 2 * sum(math.comb(n, i) for i in range(min(hi, lo) + 1)) / 2 ** n) if n else None


def truth(v):
    return str(v).strip().lower() in {'true', '1', 'yes'}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--in', dest='inp', nargs='+', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stats, occ, heads = [], [], collections.Counter()
    for d in a.inp:
        papers = read(Path(d) / '論文別.csv'); byid = collections.defaultdict(list)
        for o in read(Path(d) / '出現.csv'):
            if o['主集計'] == 'True':
                byid[o['ID']].append(o)
        for p in papers:
            full = int(p['地の文の字数'])
            cuts = [('全文', None)]
            if truth(p['結びの節']):
                heads[(p['誌名'], p['結びの見出し'], truth(p['結び_4語']))] += 1
                cut = int(p['結びより前の地の文の字数'])
                cuts += [('結び除外', cut), ('4語の結び除外', cut if truth(p['結び_4語']) else None)]
            elif not truth(p['結びの判別不能']) and p['結びの節'] != '':
                cuts += [('結び除外', None), ('4語の結び除外', None)]
            for cond, cut in cuts:
                n = full if cut is None else cut
                chosen = [o for o in byid[p['ID']] if int(o['順位']) < n]
                for o in chosen:
                    occ.append({'ID': p['ID'], '誌名': p['誌名'], '形式': p['形式'], '条件': cond, '6分類': o['新6分類'],
                                '語形': o['語形_統合後'], '五等分番号': min(4, int(o['順位']) * 5 // n), '字数': n})
                stats.append({'ID': p['ID'], '誌名': p['誌名'], '形式': p['形式'], '条件': cond, '全文字数': full, '字数': n, '主集計': len(chosen)})
    keys = sorted({(x['誌名'], x['形式'], x['条件']) for x in stats}); tables, tests, member = [], [], []
    for key in keys:
        ps = [x for x in stats if (x['誌名'], x['形式'], x['条件']) == key]
        ordered = sorted(ps, key=lambda x: (x['全文字数'], x['ID'])); tier_of = {x['ID']: min(2, i * 3 // len(ordered)) for i, x in enumerate(ordered)}
        member += [{'誌名': key[0], '形式': key[1], '条件': key[2], 'ID': x['ID'], '全文字数': x['全文字数'], '長さ3群': tier_of[x['ID']] + 1} for x in ordered]
        for tier in [0, 1, 2, 3]:
            sel = ps if tier == 0 else [x for x in ps if tier_of[x['ID']] == tier - 1]; ids = {x['ID'] for x in sel}
            v = [x for x in occ if (x['誌名'], x['形式'], x['条件']) == key and x['ID'] in ids]
            part = [sum(((q + 1) * x['字数'] + 4) // 5 - (q * x['字数'] + 4) // 5 for x in sel) for q in range(5)]
            extra = {'誌名': key[0], '形式': key[1], '条件': key[2], '長さ3群': tier or '全体', '本数': len(sel)}
            for label, qs in [(Q[q], [q]) for q in range(5)] + [('前40%', [0, 1]), ('前60%', [0, 1, 2]), ('後40%', [3, 4])]:
                vv = [x for x in v if x['五等分番号'] in qs]; co = collections.Counter(x['6分類'] for x in vv)
                wd = collections.Counter(x['語形'] for x in vv); ch = sum(part[q] for q in qs); n = len(vv)
                tables.append({**extra, '位置': label, '字数': ch, '文頭件数': n, **{k: co[k] for k in CL},
                               '逆接構成比%': co['逆接・対比'] / n * 100 if n else None, 'しかし構成比%': wd['しかし'] / n * 100 if n else None})
            for layout, early in [('前40%対後40%', [0, 1]), ('前60%対後40%', [0, 1, 2])]:
                for word in ['逆接・対比', 'しかし']:
                    pred = (lambda x: x['6分類'] == '逆接・対比') if word == '逆接・対比' else (lambda x: x['語形'] == 'しかし')
                    for th in [5, 1]:
                        hi = lo = tie = ex = 0
                        for p in sel:
                            f = [x for x in v if x['ID'] == p['ID'] and x['五等分番号'] in early]
                            b = [x for x in v if x['ID'] == p['ID'] and x['五等分番号'] in [3, 4]]
                            if len(f) < th or len(b) < th:
                                ex += 1; continue
                            dlt = sum(map(pred, b)) * len(f) - sum(map(pred, f)) * len(b)
                            hi += dlt > 0; lo += dlt < 0; tie += dlt == 0
                        tests.append({**extra, '比較': layout, '語': word, '各側最低件数': th, '後が高い': hi, '前が高い': lo,
                                      '同点': tie, '対象外': ex, 'n': hi + lo, '両側p': sign(hi, lo)})
    write(out / '論文別_条件別字数件数.csv', stats); write(out / '長さ3群の所属.csv', member)
    write(out / '五等分と前後.csv', tables); write(out / '符号検定.csv', tests)
    write(out / '結びの見出し語.csv', [{'誌名': j, '見出し': h, '4語に当たる': f, '本数': n} for (j, h, f), n in sorted(heads.items())])
    for t in tests:
        if t['長さ3群'] == '全体' and t['比較'] == '前40%対後40%' and t['語'] == '逆接・対比' and t['各側最低件数'] == 5 and t['形式'] in ('論説', '論文'):
            print(t['誌名'], t['形式'], t['条件'], f"{t['後が高い']}/{t['前が高い']}", t['両側p'])


if __name__ == '__main__':
    main()
