#!/usr/bin/env python3
"""①対象の選定: 台帳から、『税法学』の対象の刊行年（2015〜2023 年）に合わせて税大論叢・税大ジャーナルを選ぶ。

- 台帳（リポジトリには入れていない。--ledger-dir で指定）: master_papers_v1.csv（媒体・年・形式）、
  phase0_tax_literature_form_method_classification.csv（号など）、nta_pdf_coverage_20260811.csv（ジャーナルの PDF の所在）。
- 論叢は item_type=論文、ジャーナルは item_type=論説・裁決評釈。講演録・海外情報・租税史・学会情報・コラム・研究報告は含めない。
- PDF の 1〜3 頁を pdftotext で読み、日本語の字が 200 字未満のもの（文字層のない画像 PDF）は対象から除き、一覧に残す。
使い方: python3 scripts/02_select_nta.py --ledger-dir <台帳> --raw-dir <PDFの保存先の親> --out <出力CSV>
"""
import argparse, csv, re, subprocess
from collections import Counter
from pathlib import Path
ap = argparse.ArgumentParser(); ap.add_argument('--ledger-dir', required=True); ap.add_argument('--raw-dir', required=True); ap.add_argument('--out', required=True)
a = ap.parse_args(); L = Path(a.ledger_dir); RAW = Path(a.raw_dir)
def read(p): return list(csv.DictReader(open(p, encoding='utf-8-sig')))
m = read(L / 'master_papers_v1.csv')
cov = {r['record_id']: r for r in read(L / 'nta_pdf_coverage_20260811.csv')}
p0 = {r['record_id']: r for r in read(L / 'phase0_tax_literature_form_method_classification.csv')}
rows = []
for r in m:
    j = r['journal']
    if j not in ('論叢', 'ジャーナル') or not r['pub_year']: continue
    y = int(r['pub_year'])
    if not 2015 <= y <= 2023: continue
    if (j, r['item_type']) not in {('論叢', '論文'), ('ジャーナル', '論説'), ('ジャーナル', '裁決評釈')}: continue
    i = r['record_id']
    pdf = RAW / f'nta_ronsou_pdf/{i}.pdf' if j == '論叢' else RAW / Path(cov[i]['pdf_path']).relative_to('raw')
    t = subprocess.run(['pdftotext', '-l', '3', str(pdf), '-'], capture_output=True, text=True).stdout
    jp = len(re.findall(r'[぀-ヿ一-鿿]', t))
    q = p0.get(i, {})
    rows.append({'ID': i, '媒体': '税大論叢' if j == '論叢' else '税大ジャーナル', '年': y, '号': q.get('issue', ''),
                 '形式': r['item_type'], 'pdf': str(pdf), '1〜3頁の日本語字数': jp, '文字層': 'あり' if jp >= 200 else 'なし（画像PDF）'})
with open(a.out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(Counter((r['媒体'], r['形式'], r['文字層']) for r in rows))
