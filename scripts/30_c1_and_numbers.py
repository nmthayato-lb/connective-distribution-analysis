#!/usr/bin/env python3
"""『税法学』の直接引用の前後の集計と、論文に出てくる集計値（JSON）を作る。

使い方: python3 scripts/30_c1_and_numbers.py --count <10_count.py の税法学の出力> --c1 <引用と文 ID の対応表 CSV> --out <出力フォルダ>
  引用と文 ID の対応表: 直接引用ごとに、引用の種別（法令・通達等／判決文／学説／その他）と、
  直前文・引用を含む文・直後文に当たる本文の文 ID を書いた表。リポジトリには入れていない（README 参照）。
処理: connectives/c1/ の 3 本（score_c1_actual_sentence_heads.py、cross_citation_type_x_sixclass.py、
      40_manuscript_numbers.py）を、10_count.py の出力を入力にして順に実行する。
"""
import argparse, csv, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]; C1 = REPO / 'connectives/c1'


def read(p):
    return list(csv.DictReader(open(p, encoding='utf-8-sig')))


def write(p, rows, fields):
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--count', required=True); ap.add_argument('--c1', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); cnt = Path(a.count); out = Path(a.out); a1 = out / '分析1'; a2 = out / '分析2'
    a1.mkdir(parents=True, exist_ok=True); a2.mkdir(parents=True, exist_ok=True)
    papers = read(cnt / '論文別.csv')
    write(a1 / 'ID別分母・引用span.csv', [{'ID': p['ID'], '論文区分': p['形式'], '集計分母_after_masked': p['地の文の字数']} for p in papers],
          ['ID', '論文区分', '集計分母_after_masked'])
    exp = read(cnt / '出現_拡張辞書.csv'); write(a1 / 'occurrences_expanded.csv', exp, list(exp[0]))
    sents = read(cnt / '文.csv'); write(a1 / 'corpus_sentences.csv', sents, list(sents[0]))
    occ = cnt / '出現.csv'
    steps = [[C1 / 'score_c1_actual_sentence_heads.py', '--mapping', a.c1, '--sentences', a1 / 'corpus_sentences.csv',
              '--base', occ, '--expanded', a1 / 'occurrences_expanded.csv', '--outdir', a2],
             [C1 / 'cross_citation_type_x_sixclass.py', '--mapping', a.c1, '--occurrences', occ,
              '--out', a2 / '分析2_引用種別x6分類_base主表基準.csv'],
             [C1 / '40_manuscript_numbers.py', '税法学145本', a1, occ, a2, a.c1, out / '原稿の数値.json']]
    for s in steps:
        subprocess.run([sys.executable] + [str(x) for x in s], check=True)


if __name__ == '__main__':
    main()
