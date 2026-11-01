"""③脚注の機械マスク（『税法学』）: 本文 A から、PDF の字の大きさと座標で脚注の行を除く。元の A は書き換えない。

規則: PDF の文字層（pdftohtml -xml -i）を頁・段ごとに読み、本文の字（13.5〜14.5pt、上端から 130 より下、8 字以上の断片）の
最下端を段ごとの本文の下端とする。その下端より 18 以上下にある小さい字（10〜12.5pt）の行を、同じ基線の断片をつないでから、
A の中で 1 か所だけ一致したときに除く（一致しない・複数一致は除かずに記録する）。
使い方: python3 scripts/04_zeihougaku_footnote_mask.py --manifest <ID,論文区分,実行用本文,SHA256 の CSV> --pdf-dir <PDF の置き場> --out <出力>
  [--protected <JSON>]  除かない範囲（引用符のない引用など）を {ID: {"SHA256": 本文のSHA256, "spans": [[始,終],...]}} で与える。
出力: <out>/masked/<ID>/A_本文_脚注機械マスク後.txt、除外範囲.csv、小字全範囲_保持除外.csv ほか、<out>/masked_manifest.csv
"""
from pathlib import Path
import csv,subprocess,xml.etree.ElementTree as E,unicodedata,re,hashlib,json,concurrent.futures,argparse
D=None;PDF=None;PROTECTED={}
def read(p):
 with Path(p).open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def save(p,rows,fields=None):
 p=Path(p);p.parent.mkdir(exist_ok=True,parents=True)
 fields=fields or list(dict.fromkeys(k for r in rows for k in r))
 with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def normmap(s):
 chars=[];offset=[]
 for i,c in enumerate(s):
  if c.isspace() or unicodedata.category(c) in {'Cc','Cf','No'}:continue
  for z in unicodedata.normalize('NFKC',c):
   if not z.isspace():chars.append(z);offset.append(i)
 return ''.join(chars),offset
def normalized(s):return normmap(s)[0]
def work(row):
 doc=row['ID'];source=Path(row['実行用本文']);raw=source.read_text(encoding='utf-8-sig');compact,origins=normmap(raw)
 out=D/'masked'/doc;out.mkdir(parents=True,exist_ok=True)
 source_digest=sha(source)
 pdf=PDF/(doc+'.pdf');pdf_digest=sha(pdf);xml=subprocess.run(['pdftohtml','-xml','-i','-stdout',str(pdf)],capture_output=True,text=True,check=True).stdout
 (out/'PDF文字層.xml').write_text(xml);root=E.fromstring(xml)
 fonts={x.get('id'):{'size':float(x.get('size')),'family':x.get('family')} for x in root.iter('fontspec')}
 pr=PROTECTED.get(doc,{});protected=[tuple(x) for x in pr.get('spans',[])] if pr.get('SHA256')==source_digest else []
 masks=[];small=[];boundary=[]
 for page in root.findall('page'):
  number=int(page.get('number'));width=float(page.get('width'));nodes=[]
  for t in page.findall('text'):
   text=''.join(t.itertext());x=float(t.get('left'));y=float(t.get('top'));font=fonts.get(t.get('font'),{})
   if not text.strip():continue
   nodes.append({'x':x,'y':y,'right':x+float(t.get('width')),'bottom':y+float(t.get('height')),'font_size':font.get('size',0),'font_family':font.get('family',''),'text':text,'column':'R' if x>=width*.5 else 'L'})
  for col in ('L','R'):
   body=[z for z in nodes if z['column']==col and 13.5<=z['font_size']<=14.5 and z['y']>130 and len(normalized(z['text']))>=8]
   end=max((z['y'] for z in body),default=None)
   boundary.append({'ID':doc,'PDF_page':number,'column':col,'body_last_y':end if end is not None else '', 'body_font_nodes':len(body),'処置':'本文下端不明・自動除外なし' if end is None else '閾値で判定'})
   # Join same-baseline font fragments before searching the source A.
   candidates=sorted((z for z in nodes if z['column']==col and 10<=z['font_size']<=12.5 and z['y']>130),key=lambda z:(z['y'],z['x']))
   groups=[]
   for z in candidates:
    if groups and abs(groups[-1]['y']-z['y'])<=1 and z['x']>=groups[-1]['x'] and z['x']-groups[-1]['right']<=45:
     groups[-1]['text']+=z['text'];groups[-1]['right']=max(groups[-1]['right'],z['right']);groups[-1]['bottom']=max(groups[-1]['bottom'],z['bottom'])
    else:groups.append(dict(z))
   for z in groups:
    n=normalized(z['text']);below=end is not None and z['y']>=end+18
    record={'ID':doc,'PDF_page':number,'column':col,**z,'body_last_y':end if end is not None else '', '土台本文':str(source),'土台SHA256':source_digest,'PDF_SHA256':pdf_digest,'source_start':'','source_end':'','一致数':0,'処置':'保持_本文下端より上又は下端不明','小字の自動区分':('目次扉付近' if number==1 and end is not None and z['y']<min(q['y'] for q in body) else '図表注記字形候補' if 'Gothic' in z['font_family'] else '引用文字行候補_脚注内引用も含む' if z['text'].lstrip().startswith(('「','『','“')) else '脚注位置候補' if below else '本文内小字_ブロック引用等候補'),'区分根拠':'頁・本文相対位置・字体family・行頭引用符による機械フラグ。標本で画像確認。','画像判定':'未悉皆確認・標本対象','注記':'小字の引用・表・図注の可能性も含む。脚注確定ではない。'}
    if below:
     positions=[];cursor=0
     if len(n)>=8:
      while True:
       a=compact.find(n,cursor)
       if a<0:break
       positions.append(a);cursor=a+len(n)
     record['一致数']=len(positions)
     if len(positions)==1:
      a=origins[positions[0]];b=origins[positions[0]+len(n)-1]+1
      record['source_start']=a;record['source_end']=b;record['除外原文']=raw[a:b]
      if any(a<right and b>left for left,right in protected):record['処置']='保持_既知本文ブロック引用'
      else:record['処置']='除外_脚注機械マスク';masks.append(record)
     elif not positions:record['処置']='未一致_土台で除去済み又は8字未満又は文字差'
     else:record['処置']='保持_複数一致・位置非確定'
    small.append(record)
 ranges=[]
 for r in sorted(masks,key=lambda z:(z['source_start'],z['source_end'])):
  a,b=r['source_start'],r['source_end']
  if ranges and a<=ranges[-1][1]:ranges[-1][1]=max(b,ranges[-1][1])
  else:ranges.append([a,b])
 parts=[];mapping=[];cursor=0;outpos=0
 for a,b in ranges+[[len(raw),len(raw)]]:
  if a>cursor:
   parts.append(raw[cursor:a]);mapping.append({'ID':doc,'source_start':cursor,'source_end':a,'masked_start':outpos,'masked_end':outpos+a-cursor});outpos+=a-cursor
  cursor=max(cursor,b)
 masked=''.join(parts);target=out/'A_本文_脚注機械マスク後.txt';target.write_text(masked)
 save(out/'除外範囲.csv',masks,fields=list(dict.fromkeys(k for r in small for k in r)))
 save(out/'小字全範囲_保持除外.csv',small)
 save(out/'段別本文下端.csv',boundary);save(out/'原Aからmask後_保持区間対応.csv',mapping)
 spans=[]
 for a,b in protected:
  points=[]
  for m in mapping:
   l=max(a,m['source_start']);rr=min(b,m['source_end'])
   if l<rr:points.append((m['masked_start']+l-m['source_start'],m['masked_start']+rr-m['source_start']))
  if points:spans.append([min(z[0] for z in points),max(z[1] for z in points)])
 (out/'本文ブロック引用span.json').write_text(json.dumps({'SHA256':sha(target),'spans':spans},ensure_ascii=False))
 (out/'metadata.json').write_text(json.dumps({'ID':doc,'source':str(source),'source_sha256':source_digest,'masked':str(target),'masked_sha256':sha(target),'removed_unicode_chars':len(raw)-len(masked),'source_chars':len(raw),'masked_chars':len(masked),'removed_ranges':len(ranges),'matched_mask_rows':len(masks),'small_rows':len(small),'PDF':str(pdf),'PDF_sha256':pdf_digest},ensure_ascii=False,indent=2))
 return {'ID':doc,'論文区分':row['論文区分'],'土台本文':str(source),'土台SHA256':source_digest,'masked本文':str(target),'maskedSHA256':sha(target),'除外文字数':len(raw)-len(masked),'土台文字数':len(raw),'mask後文字数':len(masked),'mask範囲数':len(ranges)},masks,small
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--pdf-dir',required=True);parser.add_argument('--out',required=True);parser.add_argument('--protected');args=parser.parse_args()
 D=Path(args.out);PDF=Path(args.pdf_dir);PROTECTED=json.loads(Path(args.protected).read_text()) if args.protected else {}
 rows=read(args.manifest)
 if len({r['ID'] for r in rows})!=len(rows):raise ValueError('duplicate IDs')
 for row in rows:
  if sha(row['実行用本文'])!=row['SHA256']:raise ValueError('source SHA changed: '+row['ID'])
  if not (PDF/(row['ID']+'.pdf')).exists():raise ValueError('PDF missing')
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(work,rows))
 save(D/'masked_manifest.csv',[x[0] for x in results]);save(D/'masks_all.csv',[r for x in results for r in x[1]]);save(D/'small_blocks_all.csv',[r for x in results for r in x[2]])
 print('papers',len(results),'removed',sum(x[0]['除外文字数'] for x in results))
