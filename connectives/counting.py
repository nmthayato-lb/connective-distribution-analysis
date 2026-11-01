"""1 本の論文について、主集計の出現・地の文の字数・地の文を含む文の数を求める。

規則そのものは recount_core.py にある。ここでは次の組み立てだけを行う。
  主集計 = 辞書（基底の語形＋短形「これに対し」）の 位置=狭義文頭・判定=主集計候補
         ＋ 追加語の「むしろ」（添加・並列に入れる）
         ＋「けれども」（逆接・対比に入れる）の 狭義文頭・主集計候補
  地の文の字数 = 地の文を含む文の、引用符（「」『』“”）の内側を除いた字数。引用符の対の補完（補正入力）で与えた
                 範囲も引用符の内側として扱う。
                 句読点・引用符を含む。
『税法学』と税大 2 誌とで関数が分かれているのは、見出しの扱いが違うため。『税法学』は行の型（recount_core.header_kind）で
見出しを除き、税大 2 誌は頁画像と照らして決めた見出しの位置（補正入力の「見出し境界」）で文を区切る。
"""
import bisect, collections, contextlib, json, unicodedata
from pathlib import Path
from . import recount_core as core

CL = list(core.GROUPS)
# 漢字書きの別感度で、仮名書きと同じ語として数える 9 組（主集計には入れない）
KANJI9 = {'更に': 'さらに', '従って': 'したがって', '但し': 'ただし', '尚': 'なお', '即ち': 'すなわち',
          '又': 'また', '然し': 'しかし', '故に': 'ゆえに', '先ず': 'まず'}


@contextlib.contextmanager
def kanji9(enabled):
    """漢字 9 表記を辞書に足し、除外の規則は対応する仮名書きの規則を当てる。"""
    if not enabled:
        yield; return
    BASE0, CLASS0, ALIASES0, RULE0 = list(core.BASE), dict(core.CLASS), dict(core.ALIASES), core.rule_status
    core.BASE += list(KANJI9)
    for k, v in KANJI9.items():
        core.CLASS[k] = core.CLASS[v]; core.ALIASES[k] = core.ALIASES.get(v, v)
    core.rule_status = lambda term, *a, **kw: RULE0(KANJI9.get(term, term), *a, **kw)
    try:
        yield
    finally:
        core.BASE[:] = BASE0; core.CLASS.clear(); core.CLASS.update(CLASS0)
        core.ALIASES.clear(); core.ALIASES.update(ALIASES0); core.rule_status = RULE0


def counted_chars(res, inside=None):
    """地の文の字数に入る字の (compact 位置, 元の位置) の一覧。"""
    text, offsets = res['text'], res['offsets']
    inside = list(core.quotation_mask(text)[1] if inside is None else inside)
    for left, right in res['external_quote_spans']:
        for i, origin in enumerate(offsets):
            if left <= origin < right:
                inside[i] = True
    return [(i, offsets[i]) for u in res['sentences'] if u.get('地の文あり', False)
            for i in range(u['compact_start'], u['compact_end']) if not inside[i] and text[i] != core.SENTINEL]


def _finish(pid, b, occ, cc):
    main = [o for o in occ if o['位置'] == '狭義文頭' and o['判定'] == '主集計候補']
    cp = [x[0] for x in cc]
    for o in main:
        o['順位'] = bisect.bisect_left(cp, int(o['compact_start']))
    return dict(ID=pid, sha=b['sha'], occurrences=occ, main=main, chars=cc, sentences=b['sentences'],
                prose_sentences=sum(1 for u in b['sentences'] if u.get('地の文あり')), raw=b['raw'])


def count_zeihougaku(pid, form, path, meta, use_kanji9=False):
    meta = meta or {}
    # 引用符の対の補完（記号のある引用で、対が機械的に成立しなかったもの）。引用符のない引用は地の文として数える
    spans = [tuple(x) for x in meta.get('引用符の対の補完', [])]
    drop = {(int(x['source_start']), x['表記']): x.get('判定', '除外_補正入力') for x in meta.get('除く出現', [])}
    with kanji9(use_kanji9):
        b = core.extract(pid, form, path, external_quote_spans=spans)
        e = core.extract(pid, form, path, expanded=True, external_quote_spans=spans)
        seed = core.SEED[:]
        core.SEED = seed + ['けれども']; core.CLASS['けれども'] = '逆接・対比'
        try:
            k = core.extract(pid, form, path, expanded=True, external_quote_spans=spans)
        finally:
            core.SEED = seed; core.CLASS.pop('けれども', None)
    occ = list(b['occurrences'])
    for o in e['occurrences']:
        if o['語形_統合後'] == 'むしろ':
            o = dict(o); o['新6分類'] = '添加・並列'; occ.append(o)
    occ += [o for o in k['occurrences'] if o['表記_統合前'] == 'けれども']
    for o in occ + e['occurrences']:
        key = (int(o['source_start']), o['表記_統合前'])
        if key in drop:
            o['判定'] = drop[key]; o['判定方法'] = 'correction'
    res = _finish(pid, b, occ, counted_chars(b))
    res['expanded_occurrences'] = e['occurrences']
    return res


def _nta_extract(pid, form, path, sha, meta, expanded):
    """税大 2 誌の照合済み本文から抽出する（見出し境界・引用符の対の補完・用法の上書きは補正入力から）。"""
    if core.sha(path) != sha:
        raise ValueError(pid + ' body SHA mismatch')
    meta = meta or {}
    if meta and meta.get('本文SHA256') != sha:
        raise ValueError(pid + ' corrections SHA mismatch')
    spans = meta.get('引用符の対の補完', []); ignored = meta.get('引用符として扱わない位置', [])
    overrides = meta.get('用法の上書き', []); boundaries = meta.get('見出し境界', [])
    raw = Path(path).read_text(encoding='utf-8-sig')
    for x in overrides:
        a, z = int(x['source_start']), int(x['source_end']); assert ''.join(raw[a:z].split()) == x['表記'], (pid, a)
    previous_compact, previous_header, previous_qmask = core.compact_source, core.header_kind, core.quotation_mask
    bounds = set(boundaries)

    def compact_verified(text):
        cc = []; pp = []
        for i, ch in enumerate(text):
            if i in bounds and cc and cc[-1] != core.SENTINEL:
                cc.append(core.SENTINEL); pp.append(-1)
            if ch.isspace() or unicodedata.category(ch) in {'Cc', 'Cf', 'No'}:
                continue
            cc.append(ch); pp.append(i)
        return ''.join(cc), pp, []
    if boundaries:
        core.compact_source = compact_verified
    core.header_kind = lambda *args: ''   # 見出しは照合済みの境界で与えるので、行の型による見出しの除去は当てない
    if ignored:
        _, pp, _ = core.compact_source(raw); bad = {i for i, p in enumerate(pp) if p in ignored}
        assert all(0 <= p < len(raw) and raw[p] in '「」『』“”' for p in ignored)
        core.quotation_mask = lambda text: previous_qmask(''.join('□' if i in bad else ch for i, ch in enumerate(text)))
    try:
        res = core.extract(pid, form, path, expanded=expanded, external_quote_spans=spans)
        res['local_quote_internal_mask'] = core.quotation_mask(res['text'])[1]
    finally:
        core.header_kind, core.quotation_mask, core.compact_source = previous_header, previous_qmask, previous_compact
    lookup = {(int(x['source_start']), x['表記']): x for x in overrides}
    for o in res['occurrences']:
        x = lookup.get((int(o['source_start']), o['表記_統合前']))
        if x and o['判定'] != '除外_引用内部':
            o['判定'] = x.get('判定', '除外_非接続'); o['位置'] = x.get('位置', o['位置'])
            o['判定根拠'] = x.get('規則', ''); o['判定方法'] = 'correction'
    return res


def count_nta(pid, form, path, sha, meta, use_kanji9=False):
    with kanji9(use_kanji9):
        if 'けれども' not in core.SEED:
            core.SEED.append('けれども')
        core.CLASS['けれども'] = '逆接・対比'
        try:
            b = _nta_extract(pid, form, path, sha, meta, False)
            e = _nta_extract(pid, form, path, sha, meta, True)
        finally:
            core.SEED.remove('けれども'); core.CLASS.pop('けれども', None)
    occ = list(b['occurrences'])
    for o in e['occurrences']:
        if o['表記_統合前'] in ('むしろ', 'けれども'):
            o = dict(o)
            if o['表記_統合前'] == 'むしろ':
                o['新6分類'] = '添加・並列'
            occ.append(o)
    return _finish(pid, b, occ, counted_chars(b, b['local_quote_internal_mask']))
