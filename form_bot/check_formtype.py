#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""問い合わせ窓口ではないフォームを洗い出す。

予約・申込・購入・寄付などのフォームに営業文を送ると、相手側で実際の申込として
処理されてしまう。URLに form や contact が入っているだけでは判別できないので、
ページの項目名から用途を見る。GETのみ・送信なし。
"""
import csv, html, re, sys
from concurrent.futures import ThreadPoolExecutor
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept-Language': 'ja,en;q=0.8'})

# 送ってはいけないフォームの型。項目名や見出しに出る語で判定する
BAD_FORM = [
    ('予約・申込フォーム',
     r'(ご利用日|来店日|予約日|宿泊日|チェックイン|人数\s*[（(]?[^)）]{0,8}[)）]?\s*[＊*必須]|'
     r'ご予約|予約フォーム|申込フォーム|お申[しこ]み|申込書|参加申込|受講申込|'
     r'キャンセル(?:料|ポリシー)|団体・?グループ)'),
    ('購入・注文フォーム',
     r'(カートに入れる|注文フォーム|ご注文|購入手続き|決済|お支払い方法|数量|配送先)'),
    ('寄付・会員登録フォーム',
     r'(ご寄付|寄附|募金|入会申込|会員登録|入団申込|退会)'),
    ('資料請求・見学申込',
     r'(資料請求フォーム|見学申込|体験申込|来場予約)'),
    ('アンケート',
     r'(アンケートにご協力|設問\s*\d|満足度)'),
]
# これらがあれば問い合わせ窓口とみなす
GOOD_FORM = r'(お問(?:い)?合わせ内容|お問合せ内容|ご質問|ご相談内容|メッセージ|お問い合わせ種別|件名)'


def check(row):
    name = row['会社名']
    url = (row.get('お問い合わせフォームURL') or '').strip()
    out = {'会社名': name, 'フォームURL': url, '判定': '', '理由': '', '検出語': ''}
    if not url:
        out['判定'] = '除外'; out['理由'] = 'URLなし'
        return out
    try:
        r = S.get(url, timeout=20, allow_redirects=True)
        if r.status_code >= 400:
            out['判定'] = '除外'; out['理由'] = f'HTTP{r.status_code}'
            return out
        h = r.text
    except Exception as e:
        out['判定'] = '除外'; out['理由'] = '到達不可'
        return out

    t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h)))
    hits = []
    for label, pat in BAD_FORM:
        m = re.search(pat, t)
        if m:
            hits.append((label, m.group(0)[:20]))
    good = bool(re.search(GOOD_FORM, t))

    if hits and not good:
        out['判定'] = '送らない'
        out['理由'] = hits[0][0]
        out['検出語'] = ' / '.join(f'{l}:{w}' for l, w in hits[:2])
    elif hits and good:
        out['判定'] = '要確認'
        out['理由'] = f'{hits[0][0]}の語もあるが問い合わせ欄もある'
        out['検出語'] = ' / '.join(f'{l}:{w}' for l, w in hits[:2])
    else:
        out['判定'] = '問い合わせ窓口'
    return out


def main():
    src = sys.argv[1]
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    print(f'{len(rows)}社のフォームの用途を調べます（GETのみ・送信なし）\n')
    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(check, rows))
    out = sys.argv[2] if len(sys.argv) > 2 else 'formtype.csv'
    with open(out, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys()), lineterminator='\n')
        w.writeheader(); w.writerows(res)
    from collections import Counter
    for k, n in Counter(r['判定'] for r in res).most_common():
        print(f'  {k:<10} {n:>3}社')
    print('\n--- 送ってはいけないと判定したもの ---')
    for r in res:
        if r['判定'] == '送らない':
            print(f'  {r["会社名"][:26]:<28} {r["理由"]:<16} {r["検出語"][:40]}')
    print('\n--- 要確認 ---')
    for r in res:
        if r['判定'] == '要確認':
            print(f'  {r["会社名"][:26]:<28} {r["検出語"][:46]}')
    print(f'\n{out}')


if __name__ == '__main__':
    main()
