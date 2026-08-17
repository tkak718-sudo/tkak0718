#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""問い合わせを送った企業を、次回検索の除外リストに足す。

form_bot が書く sent_ledger.jsonl と、納品済みCSVを読み、
既存の除外リスト(.md)の末尾に追記した新しい .md を出す。

  python update_exclusion.py --base 除外リスト.md --ledger sent_ledger.jsonl \
         --csv ../納品1.csv ../納品2.csv --out 除外リスト_更新版.md

--ledger は phase が sent / submitting / unknown の行だけを拾う。
下見(dry-run)や除外(skip)は送っていないので足さない。
"""
import argparse, csv, json, os, re, sys
from datetime import datetime

CORP = re.compile(r'(株式会社|（株）|\(株\)|㈱|有限会社|（有）|\(有\)|㈲|合同会社|（同）|\(同\)|'
                  r'一般社団法人|公益社団法人|一般財団法人|公益財団法人|特定非営利活動法人|NPO法人)')


def norm(s):
    s = re.sub(r'[Ａ-Ｚａ-ｚ０-９]', lambda m: chr(ord(m.group(0)) - 0xFEE0), s)
    s = CORP.sub('', re.sub(r'[\s　]', '', s))
    for ch in '・･．.ー-‐':
        s = s.replace(ch, '')
    return s.lower()


def toks(s):
    outs = [s] + re.findall(r'[（(]([^）)]+)[）)]', s) + [re.sub(r'[（(][^）)]*[）)]', '', s)]
    return {norm(o) for o in outs if len(norm(o)) >= 2}


def existing_keys(md_text):
    keys = set()
    for line in md_text.split('\n'):
        s = line.strip()
        if not s or s.startswith(('#', '**', '---', '- ')) or '/' not in s:
            continue
        for p in s.split('/'):
            p = p.strip()
            if p:
                keys |= toks(p)
    return keys


def is_dup(name, keys):
    t = toks(name)
    if t & keys:
        return True
    for a in t:
        if len(a) < 4:
            continue
        if any(len(b) >= 4 and (a in b or b in a) for b in keys):
            return True
    return False


def from_ledger(path):
    """実際に送信処理へ入った会社だけを返す。下見や除外は含めない"""
    out = {}
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get('phase') in ('submitting', 'sent', 'unknown'):
                # 同じkeyは後勝ちでまとめる
                out[r['key']] = r
    return [(r['company'], r.get('phase', ''), r.get('time', '')[:10]) for r in out.values()]


def from_csv(paths):
    out = []
    for p in paths:
        if not os.path.exists(p):
            print(f'  (見つかりません: {p})', file=sys.stderr)
            continue
        for row in csv.DictReader(open(p, encoding='utf-8-sig')):
            n = (row.get('会社名') or '').strip()
            if n:
                out.append((n, os.path.basename(p)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True, help='いまの除外リスト(.md)')
    ap.add_argument('--ledger', default='sent_ledger.jsonl')
    ap.add_argument('--csv', nargs='*', default=[], help='納品済みCSV（取り込んだもの）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--label', default='', help='見出しに付ける補足')
    args = ap.parse_args()

    base = open(args.base, encoding='utf-8').read()
    keys = existing_keys(base)
    print(f'既存の除外リスト: 照合キー {len(keys)}件')

    sent = from_ledger(args.ledger)
    print(f'台帳から送信済み: {len(sent)}社')
    delivered = from_csv(args.csv)
    print(f'納品CSVから: {len(delivered)}社')

    add_sent, add_deliv, skipped = [], [], 0
    seen = set()
    for name, phase, day in sent:
        if name in seen or is_dup(name, keys):
            skipped += 1
            continue
        seen.add(name)
        keys |= toks(name)
        add_sent.append((name, phase, day))
    for name, src in delivered:
        if name in seen or is_dup(name, keys):
            skipped += 1
            continue
        seen.add(name)
        keys |= toks(name)
        add_deliv.append((name, src))

    today = datetime.now().strftime('%Y-%m-%d')
    parts = [base.rstrip(), '']
    if add_deliv:
        parts += ['', f'## 取り込み済み 追加 {len(add_deliv)}社（{today}・納品CSVを取り込み。'
                      f'次回検索の除外対象）{(" " + args.label) if args.label else ""}',
                  ' / '.join(n for n, _ in add_deliv)]
    if add_sent:
        parts += ['', f'## 問い合わせ送信済み 追加 {len(add_sent)}社（{today}・'
                      f'フォームから送信済み。再送しないこと）',
                  ' / '.join(n for n, _, _ in add_sent)]
    if not add_deliv and not add_sent:
        print('追加するものはありませんでした（すべて既存と重複）')
        return

    open(args.out, 'w', encoding='utf-8').write('\n'.join(parts) + '\n')
    print(f'\n追加: 取り込み済み {len(add_deliv)}社 / 送信済み {len(add_sent)}社 '
          f'（重複のため見送り {skipped}社）')
    print(f'書き出し: {args.out}')


if __name__ == '__main__':
    main()
