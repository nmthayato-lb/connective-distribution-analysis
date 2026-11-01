#!/usr/bin/env python3
"""④画像との照合の補助（税大 2 誌）: 頁画像を作り、頁ごとの本文の行を元の位置つきで示し、照合の記録を残す。

照合そのもの（頁画像と本文の行を見くらべて直すこと）は人か AI が行い、このスクリプトは行わない。
使い方（--manifest は ID, pdf, A本文, PDF物理頁数, PDF_SHA256, A_SHA256 の列を持つ CSV、--work は作業フォルダ）:
  python3 scripts/06_page_images.py --manifest M --work W prepare <ID>    本文の各行に PDF の頁・段・元の位置を対応づける
  python3 scripts/06_page_images.py --manifest M --work W render <ID>     頁画像（長辺 1800px の PNG）を作る
  python3 scripts/06_page_images.py --manifest M --work W text <ID> 3 5   3〜5 頁の本文の行を元の位置つきで表示する
  python3 scripts/06_page_images.py --manifest M --work W record <ID> 3 5 "所見" '[除く行番号...]'
                                                                          照合の記録（頁画像の SHA-256 つき）を追記する
"""
import argparse, csv, datetime, hashlib, importlib.util, json, subprocess
from pathlib import Path
HERE = Path(__file__).resolve().parent


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(i): return i if i.startswith('core4-') else 'core4-' + i
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def prepare(M, W, pid):
    r = next(r for r in M if r['ID'] == pid); d = W / pid
    if d.exists(): return d
    assert sha(r['pdf']) == r['PDF_SHA256'] and sha(r['A本文']) == r['A_SHA256']
    for sub in ['入力', '記録', '画像']: (d / sub).mkdir(parents=True)
    s = importlib.util.spec_from_file_location('pdf2a', HERE / '03_nta_pdf_to_body.py'); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    b = m.build(r['pdf']); old = Path(r['A本文']).read_text(encoding='utf-8-sig'); rebuilt = '\n'.join(l['text'] for l in b['lines']) + '\n'
    # 本文が PDF の文字層から作り直せないときは、頁との対応を自動では決めない
    if rebuilt != old: raise ValueError(pid + ': 本文を PDF の文字層から作り直せない（頁との対応を自動では決めない）')
    assert b['pages'] == int(r['PDF物理頁数']); off = 0
    for i, l in enumerate(b['lines'], 1):
        l.update({'物理行': i, 'source_start': off, 'source_end': off + len(l['text']) + 1}); off += len(l['text']) + 1
    (d / '入力/頁行offset.json').write_text(json.dumps(b, ensure_ascii=False, indent=1))
    (d / '記録/開始.json').write_text(json.dumps({'UTC': now(), 'ID': pid, 'pdf': r['pdf'], 'PDF_SHA256': r['PDF_SHA256'], 'A_SHA256': r['A_SHA256'],
                                                 '未確認頁': list(range(1, int(r['PDF物理頁数']) + 1))}, ensure_ascii=False, indent=2))
    return d


def load(W, pid):
    d = W / pid; return d, json.loads((d / '記録/開始.json').read_text()), json.loads((d / '入力/頁行offset.json').read_text())


def imagepath(W, pid, p):
    d, a, b = load(W, pid); return d / '画像' / f'page-{p:0{len(str(b["pages"]))}d}.png'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--manifest', required=True); ap.add_argument('--work', required=True)
    ap.add_argument('cmd'); ap.add_argument('id'); ap.add_argument('args', nargs='*'); a = ap.parse_args()
    M = list(csv.DictReader(open(a.manifest, encoding='utf-8-sig'))); W = Path(a.work); pid = norm(a.id)
    if a.cmd == 'prepare':
        print(prepare(M, W, pid))
    elif a.cmd == 'render':
        d, s, b = load(W, pid)
        subprocess.run(['pdftoppm', '-scale-to', '1800', '-png', s['pdf'], str(d / '画像/page')], check=True); print('rendered', b['pages'])
    elif a.cmd == 'text':
        d, s, b = load(W, pid)
        for p in range(int(a.args[0]), int(a.args[1]) + 1):
            print('PDF物理頁', p)
            for l in b['lines']:
                if l['page'] == p: print(l['物理行'], l['col'], l['top'], f'[{l["source_start"]},{l["source_end"]})', l['text'])
    elif a.cmd == 'record':
        d, s, b = load(W, pid); lo, hi, note = int(a.args[0]), int(a.args[1]), a.args[2]; removes = json.loads(a.args[3]) if len(a.args) > 3 else []
        with (d / '記録/頁画像対本文行_照合.jsonl').open('a', encoding='utf-8') as f:
            for p in range(lo, hi + 1):
                im = imagepath(W, pid, p); ls = [l for l in b['lines'] if l['page'] == p]
                f.write(json.dumps({'ID': pid, 'PDF物理頁': p, '画像SHA256': sha(im), '物理行': [l['物理行'] for l in ls],
                                    '除く物理行': [i for i in removes if any(l['物理行'] == i for l in ls)], '所見': note, 'UTC': now()}, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
