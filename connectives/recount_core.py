"""文頭の接続表現を数える規則（辞書・文の切り方・引用符の内側・見出し行・位置・判定）。

本文の各字の元の位置（オフセット）を保ったまま処理する。import しただけでは何も数えない。
"""
from __future__ import annotations
import bisect, csv, hashlib, re, unicodedata
from pathlib import Path

GROUPS = {
 '添加・並列':'また そして さらに あるいは 加えて しかも 及び および 又は または 並びに ならびに 若しくは もしくは'.split(),
 '逆接・対比':'しかし しかしながら にもかかわらず ところが だが とはいえ それにもかかわらず 一方 他方 これに対して 逆に その一方で それに対して 反面'.split(),
 '説明・換言':'すなわち 例えば つまり たとえば 具体的には 要するに'.split(),
 '補足・留保':'なお ただし もっとも ただ'.split(),
 '理由・帰結':'したがって そのため このため その結果 よって なぜなら ゆえに だから というのも したがい'.split(),
 '順序・継起':'まず 次に ところで つぎに'.split(),
}
CLASS = {term:category for category,terms in GROUPS.items() for term in terms}
BASE = list(CLASS)
assert len(BASE)==52
SHORT='これに対し'
CLASS[SHORT]='逆接・対比'
PARALLEL=set('及び および 又は または 並びに ならびに 若しくは もしくは'.split())
ALIASES={SHORT:'これに対して','つぎに':'次に','たとえば':'例えば','または':'又は','および':'及び',
         'もしくは':'若しくは','ならびに':'並びに','しかしながら':'しかし',
         'それにもかかわらず':'にもかかわらず','他方':'一方'}
SEED='そこで そうすると その上で ひいては この点 このように 以上のとおり 以上のように 前述のとおり これにより これによって そのために 他方で 一方で むしろ そのうえ その上 のみならず 併せて'.split()
SENTINEL='\ue000'

def readcsv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def writecsv(path,rows,fields=None):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(rows[0])
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def header_kind(line,previous=''):
    s=line.strip()
    if not s:return ''
    if re.fullmatch(r'[（(]?\d{1,4}[）)]?',s):return '番号行'
    if re.fullmatch(r'税法学[\s\d（()）.．\-－]+',s):return '柱'
    if len(s)<=65 and '。' not in s:
        if s in {'はじめに','おわりに','序論','結論','むすび','まとめ','結びにかえて'}:return '見出し'
        if re.match(r'^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+',s):return '見出し'
        if re.match(r'^(?:[IVX]+|[0-9０-９]+|[一二三四五六七八九十]+)[\s　．.、]+',s):return '見出し'
        if re.fullmatch(r'[0-9０-９]+',previous.strip()) and len(s)<45:return '見出し'
    return ''

def compact_source(raw):
    """物理行をつなぎ、残る各字の元の位置を保つ。見出し・柱・番号行の行は除き、見出しの位置に文の区切りを置く。

    脚注は、この前の工程（字の大きさと座標による機械マスク）で除いておく。ここでは脚注を推測しない。
    """
    chars=[];positions=[];removed=[];start=0;previous=''
    for line in raw.splitlines(keepends=True):
        content=line.rstrip('\r\n');kind=header_kind(content,previous)
        if kind:
            removed.append((start,start+len(content),kind,content))
            if kind=='見出し' and chars and chars[-1]!=SENTINEL:
                chars.append(SENTINEL);positions.append(-1)
        else:
            for j,ch in enumerate(line):
                if ch.isspace() or unicodedata.category(ch) in {'Cc','Cf','No'}:continue
                chars.append(ch);positions.append(start+j)
        start+=len(line);previous=content
    return ''.join(chars),positions,removed

def quotation_mask(text):
    """対応のとれた引用符の組の内側だけを引用の内側とする。

    閉じない開き引用符は警告として記録し、それ以降の本文を引用の内側にはしない。
    """
    openers={'「':'」','『':'』','“':'”'};closers=set(openers.values())
    stack=[];pairs=[];warnings=[]
    for i,ch in enumerate(text):
        if ch in openers:stack.append((openers[ch],i))
        elif ch in closers:
            matching=[j for j,x in enumerate(stack) if x[0]==ch]
            if matching:
                j=matching[-1]
                warnings.extend(('unclosed_nested_open',p) for _,p in stack[j+1:])
                pairs.append((stack[j][1],i));stack=stack[:j]
            else:warnings.append(('unmatched_close',i))
    warnings.extend(('unclosed_open_not_masked',p) for _,p in stack)
    mask=[False]*len(text);internal=[False]*len(text)
    for a,b in pairs:
        for i in range(a,b+1):mask[i]=True
        for i in range(a+1,b):internal[i]=True
    return mask,internal,warnings

def sentences(text,positions,doc_id,source_sha):
    qmask,_,warnings=quotation_mask(text)
    units=[];start=0
    for i,ch in enumerate(text):
        end=ch==SENTINEL or (ch in '。！？!?' and not qmask[i])
        if not end:continue
        stop=i if ch==SENTINEL else i+1
        if stop>start:
            units.append((start,stop))
        start=i+1
    if start<len(text):units.append((start,len(text)))
    result=[]
    for a,b in units:
        if not text[a:b].strip(SENTINEL):continue
        valid=[p for p in positions[a:b] if p>=0]
        if not valid:continue
        result.append({'文ID':f'{doc_id}:{source_sha[:8]}:S{len(result)+1:05d}',
                       'compact_start':a,'compact_end':b,'source_start':min(valid),
                       'source_end':max(valid)+1,'text':text[a:b]})
    return result,warnings

def matches(text,terms):
    pattern=re.compile('|'.join(re.escape(t) for t in sorted(set(terms),key=lambda t:(-len(t),t))))
    return list(pattern.finditer(text))

def determine_position(text,a,b,sentence_start,term):
    prefix=text[sentence_start:a].lstrip('「『（(【〈《」』)）')
    if not prefix:return '狭義文頭'
    if term in {'にもかかわらず','それにもかかわらず'}:return '節末候補'
    left=max((text.rfind(c,sentence_start,a) for c in '，、,；;：:'+SENTINEL),default=sentence_start-1)+1
    if not text[left:a].lstrip('「『（(【〈《」』)）'):return '節頭候補'
    return '文中_位置対象外'

def rule_status(term,text,a,b,position,quoted,manual=None):
    """出現ごとの判定（主集計候補／別掲／除外）。上から順に当てる。"""
    l=text[max(0,a-24):a];r=text[b:b+40]
    if quoted:return '除外_引用内部','引用符内。引用種類の確定とは別。','rule_quote'
    if term in PARALLEL:return '別掲_語句並立','並列の8表記は文頭でも別掲。','rule_eight'
    if term=='ただし' and r.startswith('書'):return '除外_非接続','ただし書。','rule_partial'
    if term=='ただ' and r.startswith(('し','の','単','ち','一','ひと','で','なら')):
        return '除外_非接続','限定/副詞または辞書外語形の部分一致。','rule_partial'
    if term=='なお' and r.startswith('かつ'):return '除外_辞書外複合語','なおかつの一部分。','rule_partial'
    # 規則IDは旧記録との対応のため維持する。対象は「あるいは」だけ。
    if term=='あるいは':
        if position=='狭義文頭':
            return '主集計候補','「あるいは」は狭義文頭だけ主集計。','rule_katsu_head_only'
        return '別掲_文中並立','文中の「あるいは」は読点直後を含め別掲。','rule_katsu_head_only'
    if term=='一方' and (r.startswith(('的','通行','当事者','のみ','だけ')) or l.endswith('当事者の')):
        return '除外_非接続','当事者/方向等の一方。','rule_partial'
    if term=='他方' and r.startswith(('当事者','の当事者')):return '除外_非接続','他方当事者。','rule_partial'
    if term in {'よって','したがって','したがい'} and l.endswith(('に','した')):
        return '除外_非接続','によって/にしたがって等。','rule_partial'
    if term=='そのため' and r.startswith('の'):return '除外_非接続','そのための。','rule_partial'
    if term in {'次に','つぎに'} and r.startswith(('掲げ','示す','述べ','列挙')):
        return '除外_非接続','次に掲げる等。','rule_partial'
    if term=='まず' and l.endswith(('ひと','つ')):return '除外_非接続','ひとまず/つまずく等の部分一致。','rule_partial'
    if term=='もっとも' and r.startswith(('多','大','小','少','高','低','重要','適切')):
        return '除外_非接続','最上級程度副詞の候補。','rule_partial'
    if term=='とはいえ' and r.startswith(('ない','なか','ず','ません')):
        return '除外_非接続','とはいえない等の述語部分一致。','rule_partial'
    if position=='文中_位置対象外':
        return '除外_位置対象外','位置の条件（文頭・節頭・節末）に当たらない。','rule_position'
    return '主集計候補','指定位置・引用外・既知非接続規則非該当。','rule_main'

def extract(doc_id,genre,path,manual_map=None,expanded=False,external_quote_spans=()):
    path=Path(path);raw=path.read_text(encoding='utf-8-sig');source_sha=sha(path)
    text,offsets,removed=compact_source(raw)
    units,warnings=sentences(text,offsets,doc_id,source_sha)
    starts=[u['compact_start'] for u in units]
    qmask,qinternal,_=quotation_mask(text)
    # 引用符のない引用の範囲（元の本文のオフセット）。呼び出し側が本文の SHA-256 を確かめてから渡す。
    for left,right in external_quote_spans:
        if not (0 <= left < right <= len(raw)):
            raise ValueError(f'{doc_id}: invalid external quotation span {left}:{right}')
        for index,origin in enumerate(offsets):
            if left <= origin < right:
                qmask[index]=qinternal[index]=True
    for unit in units:
        unit['地の文あり']=any(not qmask[index] and unicodedata.category(text[index])[0] in {'L','N'}
                             for index in range(unit['compact_start'],unit['compact_end']))
    lines=[0]+[m.end() for m in re.finditer('\n',raw)]
    rows=[]
    for hit in matches(text,BASE+[SHORT]+(SEED if expanded else [])):
        term=hit.group();a,b=hit.span();origin=offsets[a];origin_end=offsets[b-1]+1
        if origin<0:continue
        i=bisect.bisect_right(starts,a)-1
        if i<0 or a>=units[i]['compact_end']:continue
        unit=units[i];pos=determine_position(text,a,b,unit['compact_start'],term)
        manual=(manual_map or {}).get((doc_id,source_sha,origin,term))
        status,reason,method=rule_status(term,text,a,b,pos,qmask[a],manual)
        ln=bisect.bisect_right(lines,origin)-1
        rows.append({'出現ID':hashlib.sha256(f'{doc_id}|{source_sha}|{origin}|{term}'.encode()).hexdigest()[:24],
            'ID':doc_id,'論文区分':genre,'本文ファイル':str(path.resolve()),'本文SHA256':source_sha,
            '表記_統合前':term,'語形_統合後':ALIASES.get(term,term),'新6分類':CLASS.get(term,'辞書外19_別枠'),
            '文ID':unit['文ID'],'位置':pos,'判定':status,'判定根拠':reason,'判定方法':method,
            'source_start':origin,'source_end':origin_end,'行_1始まり':ln+1,'列_0始まり':origin-lines[ln],
            '改行跨ぎ':('\n' in raw[origin:origin_end]),'前文脈':text[max(0,a-150):a],
            '後文脈':text[b:b+180],'compact_start':a,'compact_end':b})
    # 引用符の内側の字は除き、引用符そのものを含む句読点は残す。
    author_chars=sum(not inside and ch!=SENTINEL for ch,inside in zip(text,qinternal))
    return {'ID':doc_id,'genre':genre,'path':str(path),'sha':source_sha,'raw':raw,'text':text,
            'offsets':offsets,'sentences':units,'removed':removed,'quote_warnings':warnings,
            'author_chars':author_chars,'external_quote_spans':list(external_quote_spans),
            'occurrences':rows}
