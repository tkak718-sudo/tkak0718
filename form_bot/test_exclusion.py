#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_exclusion.py の動きを確かめる。
   台帳の phase による絞り込みと、更新後リストで再検索したときの重複ゼロを見る。"""
import json, os, subprocess, sys, tempfile, csv, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ue', os.path.join(HERE, 'update_exclusion.py'))
ue = importlib.util.module_from_spec(spec); sys.modules['ue'] = spec.loader  # noqa
spec.loader.exec_module(ue)

tmp = tempfile.mkdtemp()
ledger = os.path.join(tmp, 'led.jsonl')
rows = [
    {'key': 'a1', 'company': '株式会社テスト送信済', 'phase': 'sent',       'time': '2026-08-06T10:00:00'},
    {'key': 'a2', 'company': '株式会社テスト送信中', 'phase': 'submitting', 'time': '2026-08-06T10:01:00'},
    {'key': 'a3', 'company': '株式会社テスト要目視', 'phase': 'unknown',    'time': '2026-08-06T10:02:00'},
    {'key': 'a4', 'company': '株式会社テスト下見',   'phase': 'dry-run',    'time': '2026-08-06T10:03:00'},
    {'key': 'a5', 'company': '株式会社テスト除外',   'phase': 'skip',       'time': '2026-08-06T10:04:00'},
    # 同じkeyの再掲。後勝ちで1件になること
    {'key': 'a1', 'company': '株式会社テスト送信済', 'phase': 'sent',       'time': '2026-08-06T11:00:00'},
]
with open(ledger, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')

got = ue.from_ledger(ledger)
names = sorted(n for n, _, _ in got)
want = sorted(['株式会社テスト送信済', '株式会社テスト送信中', '株式会社テスト要目視'])
print('台帳の絞り込み:', names)
assert names == want, f'期待 {want} / 実際 {names}'
print('  OK  送信していない dry-run / skip は入らない。同一keyは1件にまとまる')

# 更新後のリストで、納品済みの会社が確実に重複判定に掛かるか
base = os.path.join(HERE, '..', '除外リスト_20260806更新版.md')
if os.path.exists(base):
    keys = ue.existing_keys(open(base, encoding='utf-8').read())
    print(f'\n更新版の照合キー: {len(keys)}件')
    checked = dup = 0
    for p in ['../新規クライアント_100社_フォーム可_20260806.csv',
              '../新規クライアント_メール必須_26社_第4弾_20260806.csv',
              '../新規クライアント_メール必須_50社_20260806.csv']:
        fp = os.path.join(HERE, p)
        if not os.path.exists(fp):
            continue
        for row in csv.DictReader(open(fp, encoding='utf-8')):
            n = row['会社名']
            checked += 1
            if ue.is_dup(n, keys):
                dup += 1
    print(f'納品済み {checked}社を更新版で再判定 → 重複と判定 {dup}社')
    assert dup == checked, f'{checked - dup}社が重複と判定されない'
    print('  OK  納品済みは全件が次回検索で除外される')

    # 無関係な会社は誤って除外されないこと
    fresh = ['株式会社まだ見ぬ興行社', '公益財団法人架空県文化推進機構', '合同会社ノーマッチ']
    ng = [n for n in fresh if ue.is_dup(n, keys)]
    print(f'\n未取得の会社3件を判定 → 誤って除外 {len(ng)}件 {ng}')
    assert not ng, '未取得の会社を誤除外している'
    print('  OK  取りこぼしを生む誤除外はない')
print('\nすべて通過')
