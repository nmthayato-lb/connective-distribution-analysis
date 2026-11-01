#!/usr/bin/env python3
"""recount_core.py の辞書と規則の定義を data/dictionary.json に書き出す（読むための控え。数えるときはこのファイルを読まない）。"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.dont_write_bytecode = True
from connectives import recount_core as core
from connectives.counting import KANJI9
out = {
    '6分類と基底の語形': core.GROUPS,
    '短形': {core.SHORT: core.CLASS[core.SHORT]},
    '表記の統合（左を右の語形として数える）': core.ALIASES,
    '並列の8表記（文頭でも別掲）': sorted(core.PARALLEL),
    '追加語（別枠の定型複合表現。主集計には「むしろ」だけを添加・並列として入れる）': core.SEED,
    '主集計に入れる辞書外の語': {'むしろ': '添加・並列', 'けれども': '逆接・対比'},
    '漢字書き9表記（別感度のみ。仮名書きと同じ語として数える）': KANJI9,
    '引用符': {'「': '」', '『': '』', '“': '”'},
}
p = Path(__file__).resolve().parents[1] / 'data/dictionary.json'
p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8'); print(p.name, len(core.BASE), '語形')
