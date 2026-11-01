#!/usr/bin/env python3
"""税大論叢・税大ジャーナルの PDF 文字層から、『税法学』の A（本文の文のみ）に相当する本文を作る。

規則（LLM は使わない）:
  1. pdftohtml -xml -i で文字層を読む（一時 XML はメモリ上だけで扱い、ファイルにしない）。
  2. 頁の上端 7.5% と下端 7% にある行（柱・頁番号）を除く。
  3. 本文の字の大きさ = 字数がもっとも多い大きさの 30% 以上の字数がある大きさのうち最大のもの（注の字数が本文より多い論文があるため）。これと 0.6pt 以内の行だけを本文として残す。
     行の大きさは、その行で最初に出る漢字・かなの断片の大きさで決める（漢字・かなのない行は同じ頁・段の前の行に従う）。
     小さい字の行（脚注・図表の出所・文末注）は除き、残した行の中の小さい字（注番号）も除く。
     大きい字だけの行（章題）は見出しとして別に印を付ける。
  4. 二段組み（ジャーナル）は頁の中央で左段・右段に分け、左段→右段の順に並べる。
  5. 同じ段で上端の差が 5 以内の断片を 1 行にまとめる。
  6. 目次: 前半 45% の範囲で、点線（·・. が 6 字以上、… が 3 字以上続くもの）を含む行がある頁のまとまりを目次とし、
     その最後の頁の点線行の下端までを除く（論叢の「要約」は目次より前にあるので、ここで除かれる）。
     引用文中の「……」（2 字）は点線と見なさない。その後に凡例（略語表）があるときは、目次の最初の項目
     （「はじめに」等）と同じ文字で始まる行から本文とする。点線のない目次は「目次」の行と最初の項目で範囲を決める。
  0. 頁の枠の外にある字（見開きを半分ずつ切り出した PDF のもう半分）は読まない。
  7. 末尾: 「参考文献」等だけの行から後を除く。
出力: <out>/<ID>/A_本文.txt（物理行）と <out>/<ID>/見出し行.json（大きい字の行）と 抽出記録.csv
"""
import argparse, csv, html, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

LEADER = re.compile(r'(·{6,}|…{3,}|・{6,}|\.{6,}|．{6,}|･{6,}|‥{3,}|-{8,})')
REFHEAD = re.compile(r'^[【〔＜<（(\[]?\s*(主要)?参考文献(一覧|等)?\s*[】〕＞>）)\]]?$')
JP = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
TXT = re.compile(r'<text top="(-?\d+)" left="(-?\d+)" width="(\d+)" height="(\d+)" font="(\d+)">(.*?)</text>', re.S)

def parse(pdf):
    x = subprocess.run(['pdftohtml', '-xml', '-i', '-q', '-stdout', str(pdf)], capture_output=True).stdout.decode('utf-8', errors='replace')
    fs = {m.group(1): float(m.group(2)) for m in re.finditer(r'<fontspec id="(\d+)" size="([\d.]+)"', x)}
    pages = []
    for pg in re.split(r'<page ', x)[1:]:
        num = int(re.match(r'number="(\d+)"', pg).group(1))
        H, W = map(int, re.search(r'height="(\d+)" width="(\d+)"', pg).groups())
        frags = []
        for m in TXT.finditer(pg):
            t = html.unescape(re.sub(r'<[^>]+>', '', m.group(6)))
            if int(m.group(2)) < 0 or int(m.group(2)) >= W:
                continue  # 見開きを半分ずつ切り出した PDF（論叢 80〜83 号）では、頁の外にもう半分の字がある
            frags.append(dict(top=int(m.group(1)), left=int(m.group(2)), width=int(m.group(3)), size=fs[m.group(5)], text=t))
        pages.append(dict(num=num, H=H, W=W, frags=frags))
    return pages

def build(pdf):
    pages = parse(pdf)
    size_chars = Counter(); early = Counter()
    k = max(2, int(len(pages) * 0.4))
    for p in pages:
        for f in p['frags']:
            if p['H'] * 0.075 <= f['top'] <= p['H'] * 0.93:
                size_chars[round(f['size'])] += len(f['text'].strip())
                if 2 <= p['num'] <= k: early[round(f['size'])] += len(f['text'].strip())
    if not size_chars:
        return None
    # 本文の字の大きさ: 字数がもっとも多い大きさの 30% 以上の字数がある大きさのうち、いちばん大きいもの。
    # （脚注・文末注の字数が本文より多い論文があり、注は本文より小さい字で組まれているため）
    top_n = size_chars.most_common(1)[0][1]
    body = max(sz for sz, n in size_chars.items() if n >= top_n * 0.3)
    # 二段組みの判定: 頁の左半分から始まる本文の字の断片の右端が、ほぼすべて頁幅の 53% 以内に収まるか
    rights = []
    for p in pages:
        for f in p['frags']:
            if abs(f['size'] - body) <= 0.6 and len(f['text'].strip()) >= 3 and f['left'] < p['W'] * 0.45:
                rights.append((f['left'] + f['width']) / p['W'])
    twocol = bool(rights) and sum(r <= 0.53 for r in rights) / len(rights) >= 0.9
    lines = []  # (page, col, top, fragments)
    dropped = Counter()
    for p in pages:
        groups = defaultdict(list)
        for f in p['frags']:
            if not f['text'].strip():
                continue
            if f['top'] < p['H'] * 0.075 or f['top'] > p['H'] * 0.93:
                dropped['柱・頁番号'] += len(f['text'].strip()); continue
            col = ('R' if f['left'] >= p['W'] * 0.5 else 'L') if twocol else 'L'
            groups[col].append(f)
        for col in sorted(groups):
            fr = sorted(groups[col], key=lambda z: (z['top'], z['left']))
            cur = []; cur_top = None
            for f in fr:
                if cur and abs(f['top'] - cur_top) <= 5:
                    cur.append(f)
                else:
                    if cur: lines.append((p['num'], col, cur_top, cur))
                    cur = [f]; cur_top = f['top']
            if cur: lines.append((p['num'], col, cur_top, cur))
    # 行ごとの字の大きさ: 行の中で最初に出る漢字・かなの断片の大きさ。漢字・かなのない行は、同じ頁・段の前の行に従う。
    # （脚注の中の数字や欧文が本文と同じ大きさの字体で組まれている論文があるため、断片ごとではなく行ごとに決める）
    out = []; prev = {}
    for num, col, top, cur in lines:
        cur = sorted(cur, key=lambda z: z['left'])
        cjk = [f for f in cur if JP.search(f['text'])]
        if cjk: size = cjk[0]['size']
        elif (num, col) in prev: size = prev[(num, col)]
        else:
            c = Counter()
            for f in cur: c[f['size']] += len(f['text'].strip())
            size = c.most_common(1)[0][0]
        prev[(num, col)] = size
        if size < body - 0.6:
            dropped['小さい字'] += sum(len(f['text'].strip()) for f in cur); continue
        keep = [f for f in cur if f['size'] >= body - 0.6]  # 行の中の小さい字（注番号）は除く
        dropped['小さい字'] += sum(len(f['text'].strip()) for f in cur if f['size'] < body - 0.6)
        if not keep: continue
        text = ''.join(f['text'] for f in keep).strip()
        if not text: continue
        kind = '見出し' if all(f['size'] > body + 0.6 for f in keep) else '本文'
        out.append(dict(page=num, col=col, top=top, text=text, kind=kind))
    # 目次の除去（頁と上下位置で行う。ジャーナルの目次は頁幅いっぱいの行で、その下から二段組みの本文が始まるため）
    sq = lambda t: re.sub(r'\s', '', t)
    n = len(out); first45 = out[: int(n * 0.45)]
    lead = [l for l in first45 if LEADER.search(l['text'])]
    toc_entry = None; found = False; drop = set()
    if lead:
        found = True
        pages_l = sorted({l['page'] for l in lead}); last = pages_l[0]
        for pg in pages_l[1:]:
            if pg - last <= 1: last = pg
            else: break
        bottom = max(l['top'] for l in lead if l['page'] == last)
        drop = {i for i, l in enumerate(out) if l['page'] < last or (l['page'] == last and l['top'] <= bottom)}
        # 目次の最初の項目（例「はじめに」「Ⅰはじめに」）
        g = next((i for i in sorted(drop) if sq(out[i]['text']) == '目次'), None)
        src = out[g + 1]['text'] if g is not None and g + 1 in drop else lead[0]['text']
        toc_entry = sq(re.sub(r'[\s\d０-９]+$', '', LEADER.split(src)[0]))
    else:
        # 点線のない目次: 「目次」の行の次の行（最初の項目）と同じ見出しが本文に再び出る直前までを除く。
        # 項目が文字層にない場合は「目次」の行までを除く。
        g = next((i for i, l in enumerate(first45) if sq(l['text']) == '目次'), None)
        if g is not None:
            found = True; drop = set(range(g + 1))
            if g + 1 < n:
                toc_entry = sq(re.sub(r'[\s\d０-９]+$', '', out[g + 1]['text']))
                if re.search(r'\d+\s*$', out[g + 1]['text']): drop.add(g + 1)  # 頁番号つきの項目行は目次
    toc_chars = sum(len(out[i]['text']) for i in drop)
    out = [l for i, l in enumerate(out) if i not in drop]
    # 目次の後に凡例（略語表）などがあるときは、目次の最初の項目の見出しが本文に出る行から始める（300 行以内）
    skipped_after_toc = 0
    if toc_entry and len(toc_entry) >= 2:
        j = next((k for k in range(min(len(out), 300)) if sq(out[k]['text']).startswith(toc_entry)), None)
        if j:
            skipped_after_toc = sum(len(l['text']) for l in out[:j]); out = out[j:]
    # 末尾の参考文献
    ref_cut = None
    for i, l in enumerate(out):
        if i > len(out) * 0.6 and REFHEAD.match(re.sub(r'\s', '', l['text'])):
            ref_cut = i; break
    ref_chars = 0
    if ref_cut is not None:
        ref_chars = sum(len(l['text']) for l in out[ref_cut:]); out = out[:ref_cut]
    return dict(body_size=body, twocol=twocol, lines=out, dropped=dict(dropped), toc_chars=toc_chars,
                toc_found=found, toc_entry=toc_entry, skipped_after_toc=skipped_after_toc, ref_chars=ref_chars, pages=len(pages), size_chars=dict(size_chars))

def affiliation(pdf):
    """1 頁目の所属表示（機械で読み取った文字列。確認は目視）"""
    t = subprocess.run(['pdftotext', '-l', '1', '-layout', str(pdf), '-'], capture_output=True, text=True).stdout
    t2 = re.sub(r'[ 　]+', '', t)
    keys = ['教授', '准教授', '講師', '研究員', '教育官', '研究部', '主任', '税理士', '弁護士', '審判官', '調査官', '国税', '税務署', '研究科', '客員', '所長', '部長', '課長', '名誉']
    hits = [ln for ln in t2.splitlines() if any(k in ln for k in keys) and len(ln) <= 60 and '公式見解' not in ln and '個人的見解' not in ln]
    return ' / '.join(hits[:4])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cand', required=True); ap.add_argument('--out', required=True); ap.add_argument('--log', required=True)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.cand, encoding='utf-8-sig')))
    log = []
    for r in rows:
        d = Path(a.out) / r['ID']; d.mkdir(parents=True, exist_ok=True)
        res = build(r['pdf'])
        if res is None:
            log.append({**r, '状態': '文字層なし'}); continue
        (d / 'A_本文.txt').write_text('\n'.join(l['text'] for l in res['lines']) + '\n', encoding='utf-8')
        heads = [l['text'] for l in res['lines'] if l['kind'] == '見出し']
        (d / '見出し行.json').write_text(json.dumps(heads, ensure_ascii=False), encoding='utf-8')
        log.append({**r, '状態': '抽出', '頁数': res['pages'], '本文字の大きさ': res['body_size'], '二段組み': res['twocol'],
                    '目次等を除いたか': res['toc_found'], '目次の最初の項目': res['toc_entry'], '目次の後の凡例等で除いた字数': res['skipped_after_toc'], '目次まで除いた字数': res['toc_chars'], '参考文献で除いた字数': res['ref_chars'],
                    '柱・頁番号で除いた字数': res['dropped'].get('柱・頁番号', 0), '小さい字で除いた字数': res['dropped'].get('小さい字', 0),
                    '本文行数': len(res['lines']), '本文字数_空白込み': sum(len(l['text']) for l in res['lines']),
                    '見出し行数_大きい字': len(heads), '字の大きさ別字数': json.dumps(res['size_chars']),
                    '1頁目の所属表示_機械読取': affiliation(r['pdf'])})
        print(r['ID'], res['body_size'], res['twocol'], res['toc_found'], len(res['lines']), file=sys.stderr)
    fields = list(dict.fromkeys(k for l in log for k in l))
    with open(a.log, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(log)

if __name__ == '__main__':
    main()
