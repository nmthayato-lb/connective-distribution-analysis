#!/usr/bin/env python3
"""①入手: 保存した税大論叢の各論文の HTML から本文 PDF のリンクを読み、PDF を保存する（1.5 秒間隔）。

使い方: python3 scripts/01b_fetch_ronsou_pdfs.py --list <一覧CSV> --html-dir <HTMLの保存先> --pdf-dir <PDFの保存先> --text-dir <テキストの出力先>
  一覧 CSV の列: record_id, url（HTML の url）, publication_year
  User-Agent は環境変数 KIYO_USER_AGENT で指定する（連絡先を入れる場合はここに書く）。
"""
import argparse, csv, hashlib, os, re, socket, subprocess, time, urllib.request
socket.setdefaulttimeout(30)
UA = {"User-Agent": os.environ.get('KIYO_USER_AGENT', 'Mozilla/5.0 (research use)')}
ap = argparse.ArgumentParser()
for k in ['--list', '--html-dir', '--pdf-dir', '--text-dir', '--inventory']:
    ap.add_argument(k, required=(k != '--inventory'))
a = ap.parse_args()
for d in (a.pdf_dir, a.text_dir):
    os.makedirs(d, exist_ok=True)
rows = list(csv.DictReader(open(a.list, encoding='utf-8-sig')))
inv = []
for i, r in enumerate(rows):
    rid = r['record_id']
    rec = {'record_id': rid, 'year': r.get('publication_year', ''), 'status': '', 'chars': 0}
    try:
        hf = os.path.join(a.html_dir, '%s.htm' % hashlib.sha1(r['url'].encode()).hexdigest())
        if not os.path.exists(hf):
            rec['status'] = 'no_html'; inv.append(rec); continue
        t = open(hf, 'rb').read().decode('cp932', 'ignore')
        pdfs = re.findall(r'href="([^"]*\.pdf[^"]*)"', t)
        if not pdfs:
            rec['status'] = 'no_pdf_link'; inv.append(rec); continue
        pu = pdfs[0]
        if not pu.startswith('http'):
            pu = 'https://www.nta.go.jp' + pu
        dest = os.path.join(a.pdf_dir, '%s.pdf' % rid)
        if not os.path.exists(dest):
            req = urllib.request.Request(pu, headers=UA)
            open(dest, 'wb').write(urllib.request.urlopen(req).read())
            time.sleep(1.5)
        txt = subprocess.run(['pdftotext', dest, '-'], capture_output=True).stdout.decode('utf-8', 'ignore')
        open(os.path.join(a.text_dir, f'{rid}.txt'), 'w').write(txt)
        rec['status'] = 'ok'; rec['chars'] = len(txt)
    except Exception as e:
        rec['status'] = 'error:' + type(e).__name__
    inv.append(rec)
    if (i + 1) % 20 == 0:
        print(i + 1, 'done', flush=True)
if a.inventory:
    with open(a.inventory, 'w', newline='') as fp:
        w = csv.DictWriter(fp, fieldnames=list(inv[0].keys())); w.writeheader(); w.writerows(inv)
print('完了: ok %d / %d' % (sum(x['status'] == 'ok' for x in inv), len(inv)))
