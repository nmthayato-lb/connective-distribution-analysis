#!/usr/bin/env python3
"""文頭の接続表現を数え、論文別の表と出現の表を書き出す。

使い方:
  python3 scripts/10_count.py --journal zeihougaku --out <出力フォルダ>
  python3 scripts/10_count.py --journal nta --out <出力フォルダ>
  （--kanji9 を付けると、漢字書き 9 表記を仮名書きと同じ語として数える別感度）

入力:
  data/targets.csv の対象（--journal で誌を選ぶ）。本文は config の data_dir からの相対パス（本文ファイル列）。
  補正入力（引用符の対の補完・見出し境界など。09_build_corrections.py で作る）は config の corrections_dir/<誌>/<ID>.json。なければ補正なしで数える。
出力（本文の文字列は書き出さない）:
  論文別.csv   ID・誌名・形式・主集計・地の文の字数・地の文を含む文の数・6 分類ごとの件数・結びの節の情報
  出現.csv     すべての出現（主集計に入らないものも含む）の 位置・判定・判定の規則・元の位置
  文.csv       文 ID・地の文を含むか（直接引用の前後の集計に使う。文の文字列は入れない）
  出現_拡張辞書.csv  （『税法学』のみ）追加語を含む辞書での全出現。原稿の数値の計算（30_c1_and_numbers.py）に使う
"""
import argparse, collections, csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True
from connectives import config, counting

JOURNAL = {'zeihougaku': ['税法学'], 'nta': ['税大論叢', '税大ジャーナル']}
OCC_FIELDS = ['出現ID', 'ID', '論文区分', '表記_統合前', '語形_統合後', '新6分類', '文ID', '位置', '判定', '判定方法',
              'source_start', 'source_end', 'compact_start', 'compact_end', '主集計', '順位']


def write(p, rows, fields):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--journal', choices=list(JOURNAL), required=True)
    ap.add_argument('--targets', default=str(config.REPO / 'data/targets.csv'))
    ap.add_argument('--out', required=True)
    ap.add_argument('--kanji9', action='store_true')
    ap.add_argument('--no-corrections', action='store_true', help='補正入力を読まずに数える')
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(a.targets, encoding='utf-8-sig')) if r['誌名'] in JOURNAL[a.journal]]
    papers, occs, sents, exps = [], [], [], []
    for r in rows:
        pid = r['ID']; path = config.body_path(r['本文ファイル'])
        mp = config.corrections_path(a.journal, pid)
        meta = json.loads(mp.read_text(encoding='utf-8')) if (mp.exists() and not a.no_corrections) else {}
        if meta and meta.get('本文SHA256') != r['本文SHA256']:
            raise ValueError(pid + ': 補正入力の本文SHA256が本文と一致しない')
        if a.journal == 'zeihougaku':
            if counting.core.sha(path) != r['本文SHA256']:
                raise ValueError(pid + ': 本文SHA256が一致しない')
            res = counting.count_zeihougaku(pid, r['形式'], path, meta, a.kanji9)
        else:
            res = counting.count_nta(pid, r['形式'], path, r['本文SHA256'], meta, a.kanji9)
        cls = collections.Counter(o['新6分類'] for o in res['main'])
        close = meta.get('結び', {})
        cut = close.get('開始')
        papers.append({'ID': pid, '誌名': r['誌名'], '形式': r['形式'], '本文SHA256': res['sha'],
                       '主集計': len(res['main']), '地の文の字数': len(res['chars']), '地の文を含む文の数': res['prose_sentences'],
                       **{'件数_' + c: cls[c] for c in counting.CL},
                       '結びの節': close.get('結びの節', ''), '結びの判別不能': close.get('判別不能', False),
                       '結びの見出し': close.get('見出し', '') if close.get('結びの節') else '',
                       '結び_4語': close.get('4語', ''),
                       '結びより前の地の文の字数': sum(1 for _, s in res['chars'] if s < cut) if cut is not None else ''})
        main_ids = {id(o) for o in res['main']}
        for o in res['occurrences']:
            occs.append({**o, '論文区分': r['形式'], '主集計': id(o) in main_ids, '順位': o.get('順位', '') if id(o) in main_ids else ''})
        for o in res.get('expanded_occurrences', []):
            exps.append({**o, '論文区分': r['形式']})
        for u in res['sentences']:
            sents.append({'ID': pid, '論文区分': r['形式'], '文ID': u['文ID'], 'source_start': u['source_start'],
                          'source_end': u['source_end'], '地の文あり': u.get('地の文あり', False)})
        print(pid, len(res['main']), len(res['chars']), file=sys.stderr)
    pf = list(papers[0])
    write(out / '論文別.csv', papers, pf); write(out / '出現.csv', occs, OCC_FIELDS)
    if exps:
        write(out / '出現_拡張辞書.csv', exps, OCC_FIELDS[:-2])
    write(out / '文.csv', sents, ['ID', '論文区分', '文ID', 'source_start', 'source_end', '地の文あり'])
    tot = collections.defaultdict(lambda: [0, 0, 0])
    for p in papers:
        t = tot[p['誌名']]; t[0] += 1; t[1] += p['主集計']; t[2] += p['地の文の字数']
    summary = {k: {'本数': v[0], '主集計': v[1], '地の文の字数': v[2]} for k, v in tot.items()}
    (out / '合計.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
