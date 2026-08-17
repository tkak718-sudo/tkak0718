#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ブラウザを使わずに、100社を「自動で回せる／手動」に仕分ける。

form_bot と同じ送信前チェックと項目分類を、取得したHTMLに対して当てる。
ページを GET するだけで、送信は一切行わない。

  python pre_triage.py --csv ../企業リスト.csv --profile profile.json --out triage.csv

ブラウザ版との違い：
  - JavaScriptで描画されるフォームは見えない → ここで「フォーム未検出」でも
    実行時には拾えることがある（つまり本結果は控えめな見積り）
  - ラベル文言の照合が弱い（DOMを辿れないため name/id/placeholder のみ）
"""
import argparse, csv, html, json, re, sys, importlib.util, os
from concurrent.futures import ThreadPoolExecutor

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fb', os.path.join(HERE, 'form_bot.py'))
fb = importlib.util.module_from_spec(spec)
sys.modules['fb'] = fb
spec.loader.exec_module(fb)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept-Language': 'ja,en;q=0.8'})


def analyse(row, profile):
    name = row['会社名']
    url = (row.get('お問い合わせフォームURL') or '').strip()
    out = {'会社名': name, 'フォームURL': url, '判定': '', '理由': '',
           '拾えた項目': '', '本文': '', 'CAPTCHA': '', '確認画面': ''}
    if not url:
        out['判定'] = '手動'; out['理由'] = 'フォームURLなし'
        return out
    try:
        r = S.get(url, timeout=20, allow_redirects=True)
        if r.status_code >= 400:
            out['判定'] = '手動'; out['理由'] = f'HTTP{r.status_code}'
            return out
        h = r.text
    except Exception as e:
        out['判定'] = '手動'; out['理由'] = f'到達不可: {str(e)[:40]}'
        return out

    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h)))

    if fb.NG_SALES.search(t):
        out['判定'] = '送らない'; out['理由'] = '営業お断りの記載'
        return out
    if fb.NG_PURPOSE.search(t) or fb.NG_URL.search(url):
        out['判定'] = '送らない'; out['理由'] = '採用/サポート/取材専用の窓口'
        return out

    cap = bool(fb.CAPTCHA.search(h))
    out['CAPTCHA'] = 'あり' if cap else ''
    out['確認画面'] = 'あり' if re.search(r'(確認画面|入力内容を確認|確認する)', t) else ''
    if cap:
        out['判定'] = '手動'; out['理由'] = 'CAPTCHAあり（自動送信しない）'
        return out

    if not re.search(r'(?is)<form', h):
        out['判定'] = '要確認'; out['理由'] = 'HTMLにフォームなし（JS描画の可能性）'
        return out

    # 項目分類
    kinds = set()
    for m in re.finditer(r'<(?:input|textarea|select)\b([^>]*)>', h, re.I):
        a = m.group(1)
        if re.search(r'type="(hidden|submit|button|image|reset|file)"', a, re.I):
            continue
        blob = ' '.join(re.findall(r'(?:name|id|placeholder|aria-label)="([^"]*)"', a))
        k = fb.classify(blob)
        if k:
            kinds.add(k)
    out['拾えた項目'] = '/'.join(sorted(kinds))

    # 本文の長さ。form_bot と同じ 通常→短縮→極小 の順で判定する
    lims = [int(x) for x in re.findall(r'(?is)<textarea\b[^>]*maxlength="(\d+)"', h)]
    lim = min(lims) if lims else None
    chosen = None
    for key, label in (('body', '通常版'), ('body_short', '短縮版'), ('body_mini', '極小版')):
        body = profile.get(key) or ''
        if body and (lim is None or len(body) <= lim):
            chosen = label
            break
    if chosen is None:
        out['判定'] = '手動'; out['理由'] = f'本文が上限{lim}字に収まらない'
        out['本文'] = f'入らない（上限{lim}）'
        return out
    out['本文'] = chosen + (f'（上限{lim}）' if lim else '')

    if len(kinds) < 3:
        out['判定'] = '要確認'
        out['理由'] = f'HTML上で拾えた項目が{len(kinds)}件（実行時はラベルも見るので増える見込み）'
        return out

    out['判定'] = '自動可'
    out['理由'] = ''
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True)
    ap.add_argument('--profile', default=os.path.join(HERE, 'profile.json'))
    ap.add_argument('--out', default='triage.csv')
    args = ap.parse_args()

    profile = json.load(open(args.profile, encoding='utf-8'))
    rows = list(csv.DictReader(open(args.csv, encoding='utf-8-sig')))
    print(f'{len(rows)}社を仕分けます（GETのみ・送信なし）\n')

    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(lambda r: analyse(r, profile), rows))

    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()), lineterminator='\n')
        w.writeheader()
        w.writerows(res)

    from collections import Counter
    c = Counter(r['判定'] for r in res)
    for k in ('自動可', '要確認', '手動', '送らない'):
        print(f'  {k:<6} {c.get(k, 0):>3}社')
    print(f'\n理由の内訳（自動可以外）')
    for reason, n in Counter(r['理由'] for r in res if r['判定'] != '自動可' and r['理由']).most_common():
        print(f'  {n:>3}社  {reason[:56]}')
    print(f'\n本文の扱い')
    for b, n in Counter(r['本文'] for r in res if r['本文']).most_common(6):
        print(f'  {n:>3}社  {b}')
    print(f'\n書き出し: {args.out}')


if __name__ == '__main__':
    main()
