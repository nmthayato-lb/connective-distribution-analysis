#!/usr/bin/env python3
"""判断の記録（data/decisions/）から、10_count.py が読む補正入力（<corrections_dir>/<誌>/<ID>.json）を作る。

使い方: python3 scripts/09_build_corrections.py [--out <補正入力の置き場所>]（省略時は config の corrections_dir）
作るもの（ID ごと）: 引用符の対の補完、引用符として扱わない位置、用法の上書き、除く出現、見出し境界、結び。
本文の補修は本文そのものに入っているので、ここでは扱わない。
"""
import argparse, collections, csv, gzip, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.dont_write_bytecode = True
from connectives import config

D = config.REPO / 'data/decisions'


def read(name):
    p = D / name
    f = gzip.open(p, 'rt', encoding='utf-8-sig') if p.suffix == '.gz' else open(p, encoding='utf-8-sig')
    with f:
        return list(csv.DictReader(f))


def truth(v):
    return str(v).strip().lower() in {'true', '1', 'yes'}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out'); a = ap.parse_args()
    out = Path(a.out) if a.out else config.get('corrections_dir')
    targets = list(csv.DictReader(open(config.REPO / 'data/targets.csv', encoding='utf-8-sig')))
    meta = {t['ID']: {'ID': t['ID'], '本文SHA256': t['本文SHA256'], '引用符の対の補完': [], '引用符として扱わない位置': [],
                      '用法の上書き': [], '除く出現': [], '見出し境界': []} for t in targets}
    for r in read('a_引用符の対の補完.csv'):
        meta[r['ID']]['引用符の対の補完'].append([int(r['位置_開始']), int(r['位置_終了'])])
    for r in read('a_そのために.csv'):
        if r['判断'] == '後続語の修飾として数えない':
            meta[r['ID']]['用法の上書き'].append({'source_start': int(r['位置_開始']), 'source_end': int(r['位置_終了']),
                                                  '表記': r['表記'], '判定': '除外_非接続', '規則': 'そのために_後続語修飾'})
    for r in read('b_画像との照合による補正.csv'):
        m = meta[r['ID']]
        if r['規則名'] == '画像照合_非接続':
            m['用法の上書き'].append({'source_start': int(r['位置_開始']), 'source_end': int(r['位置_終了']), '表記': r['表記'], '判定': r['判断'], '規則': r['規則名']})
        elif r['規則名'] == '画像照合_引用内部':
            m['除く出現'].append({'source_start': int(r['位置_開始']), '表記': r['表記'], '判定': r['判断']})
        elif r['規則名'] == '画像照合_引用符の誤対応':
            m['引用符として扱わない位置'].append(int(r['位置_開始']))
    for r in read('b_見出し境界.csv'):
        meta[r['ID']]['見出し境界'].append(int(r['位置']))
    for r in read('a_結びの節.csv'):
        has = r['判断'] == '結びの節あり'
        meta[r['ID']]['結び'] = {'結びの節': has, '判別不能': r['判断'] == '判別不能', '開始': int(r['位置_開始']) if has else None,
                                 '見出し': r['見出しの語'], '4語': truth(r['4語に当たる'])}
    journal = {t['ID']: ('zeihougaku' if t['誌名'] == '税法学' else 'nta') for t in targets}
    n = collections.Counter()
    for pid, m in meta.items():
        p = out / journal[pid] / f'{pid}.json'; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding='utf-8'); n[journal[pid]] += 1
    print(dict(n), out)


if __name__ == '__main__':
    main()
