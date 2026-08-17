#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本文が各社フォームの文字数制限に収まるかを実測する。
   textarea の maxlength を集め、profile.json の本文と突き合わせる。"""
import csv, html, json, re, sys
from concurrent.futures import ThreadPoolExecutor
import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
CSV = sys.argv[1] if len(sys.argv) > 1 else '../新規クライアント_100社_フォーム可_20260806.csv'
PROF = sys.argv[2] if len(sys.argv) > 2 else 'profile.json'

body = json.load(open(PROF, encoding='utf-8'))['body']
blen = len(body)
print(f'本文の長さ: {blen}字（改行含む）\n')

rows = list(csv.DictReader(open(CSV, encoding='utf-8')))


def scan(r):
    u = r.get('お問い合わせフォームURL', '')
    if not u:
        return None
    try:
        h = requests.get(u, headers={'User-Agent': UA}, timeout=18).text
    except Exception:
        return ('unreach', None, r['会社名'])
    lims = []
    for m in re.finditer(r'(?is)<textarea\b([^>]*)>', h):
        ml = re.search(r'maxlength="(\d+)"', m.group(1), re.I)
        if ml:
            lims.append(int(ml.group(1)))
    # input にも制限が付くことがある（件名など）
    subj = []
    for m in re.finditer(r'(?is)<input\b([^>]*)>', h):
        a = m.group(1)
        if re.search(r'(件名|subject|title)', a, re.I):
            ml = re.search(r'maxlength="(\d+)"', a, re.I)
            if ml:
                subj.append(int(ml.group(1)))
    return ('ok', (min(lims) if lims else None, min(subj) if subj else None), r['会社名'])


with ThreadPoolExecutor(max_workers=10) as ex:
    res = [x for x in ex.map(scan, rows) if x]

有制限, 無制限, 到達不可, ng = [], 0, 0, []
for st, v, name in res:
    if st == 'unreach':
        到達不可 += 1
        continue
    lim, slim = v
    if lim is None:
        無制限 += 1
    else:
        有制限.append((lim, name))
        if lim < blen:
            ng.append((lim, name))

print(f'textarea に maxlength あり : {len(有制限)}社')
print(f'                     なし : {無制限}社')
print(f'                 到達不可 : {到達不可}社')

if 有制限:
    vals = sorted(l for l, _ in 有制限)
    print(f'\n制限値: 最小 {vals[0]} / 中央 {vals[len(vals)//2]} / 最大 {vals[-1]}')

print(f'\n本文 {blen}字 が入りきらない社: {len(ng)}社')
for lim, name in sorted(ng):
    print(f'  上限{lim:>5}字  {name[:32]}')

if ng:
    worst = min(l for l, _ in ng)
    print(f'\n→ 全社に通すなら本文は {worst}字 以内。'
          f' もしくは短縮版を用意して {len(ng)}社だけ差し替える')
else:
    print('\n→ 判明している制限には全て収まる')
