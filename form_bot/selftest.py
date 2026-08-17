#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""form_bot の判定ロジックを、実在のフォームHTMLに当てて確かめる。
   ブラウザは使わず取得だけなので、送信は一切行わない。"""
import sys, re, csv, html, importlib.util
import requests

HERE = '/home/user/tkak0718/form_bot/form_bot.py'
spec = importlib.util.spec_from_file_location('fb', HERE)
fb = importlib.util.module_from_spec(spec)
sys.modules['fb'] = fb
spec.loader.exec_module(fb)

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
CSV = sys.argv[1] if len(sys.argv) > 1 else '/home/user/tkak0718/新規クライアント_100社_フォーム可_20260806.csv'
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30

rows = list(csv.DictReader(open(CSV, encoding='utf-8')))
print(f'対象CSV {len(rows)}社 / 先頭{N}社で検証\n')

stat = dict(form=0, captcha=0, ng_sales=0, ng_purpose=0, unreach=0, confirm=0)
hits = {}
for r in rows[:N]:
    u = r.get('お問い合わせフォームURL', '')
    if not u:
        continue
    try:
        h = requests.get(u, headers={'User-Agent': UA}, timeout=18).text
    except Exception:
        stat['unreach'] += 1
        continue
    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h)))
    if re.search(r'(?is)<form', h):
        stat['form'] += 1
    if fb.CAPTCHA.search(h):
        stat['captcha'] += 1
    if fb.NG_SALES.search(t):
        stat['ng_sales'] += 1
    if fb.NG_PURPOSE.search(t) or fb.NG_URL.search(u):
        stat['ng_purpose'] += 1
    if re.search(r'(確認画面|入力内容を確認|確認する)', t):
        stat['confirm'] += 1
    for m in re.finditer(r'<(?:input|textarea|select)\b([^>]*)>', h, re.I):
        blob = ' '.join(re.findall(r'(?:name|id|placeholder|aria-label)="([^"]*)"', m.group(1)))
        k = fb.classify(blob)
        if k:
            hits[k] = hits.get(k, 0) + 1

print('--- 送信前チェックの発火状況 ---')
print(f'  <form>検出 {stat["form"]} / CAPTCHA {stat["captcha"]} / 営業お断り {stat["ng_sales"]}'
      f' / 用途違い {stat["ng_purpose"]} / 到達不可 {stat["unreach"]} / 確認画面あり {stat["confirm"]}')

print('\n--- 項目分類のヒット（name/placeholderのみ。実行時はラベルも見るので下限値）---')
for k, v in sorted(hits.items(), key=lambda x: -x[1]):
    print(f'  {k:<10} {v}')

print('\n--- ボタン判定（確認を送信と取り違えないか）---')
CONF = r'(確認|内容を確認|入力内容の確認|次へ|confirm)'
SUBM = r'(送信|送信する|この内容で送信|上記内容で送信|申し込む|submit|send)'
cases = ['確認する', '入力内容を確認', '確認画面へ進む', '次へ',
         '送信する', 'この内容で送信', '上記内容で送信する', 'Submit']
ng = 0
for s in cases:
    isc = bool(re.search(CONF, s, re.I))
    iss = bool(re.search(SUBM, s, re.I))
    if iss and isc and not re.search(r'送信|submit|send', s, re.I):
        iss = False
    want_submit = bool(re.search(r'送信|submit', s, re.I))
    ok = (iss == want_submit)
    if not ok:
        ng += 1
    print(f'  {s:<16} 確認={isc!s:<5} 送信={iss!s:<5} {"OK" if ok else "NG"}')
print(f'\nボタン判定: {"全件OK" if ng == 0 else str(ng) + "件NG"}')

print('\n--- 営業お断り文言の検出テスト ---')
samples = [
    ('営業・勧誘目的でのご利用はお断りいたします。', True),
    ('営業目的のお問い合わせはご遠慮ください', True),
    ('セールスの電話は固くお断りしております', True),
    ('採用に関するお問い合わせは採用専用フォームへ', False),
    ('公演に関するお問い合わせはこちら', False),
]
ng2 = 0
for s, want in samples:
    got = bool(fb.NG_SALES.search(s))
    if got != want:
        ng2 += 1
    print(f'  {"OK" if got == want else "NG"}  {s[:34]:<36} 検出={got}')
print(f'\n営業お断り検出: {"全件OK" if ng2 == 0 else str(ng2) + "件NG"}')
