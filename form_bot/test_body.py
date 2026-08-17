#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本文の差し替え判定を確かめる。maxlength ごとに何が選ばれるか。"""
import importlib.util, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fb', os.path.join(HERE, 'form_bot.py'))
fb = importlib.util.module_from_spec(spec)
sys.modules['fb'] = fb
spec.loader.exec_module(fb)

profile = json.load(open(os.path.join(HERE, 'profile.json'), encoding='utf-8'))
full = len(profile['body'])
short = len(profile['body_short'])
print(f'通常版 {full}字 / 短縮版 {short}字\n')


class FakeEl:
    def __init__(self, ml):
        self.ml = ml

    def get_attribute(self, k):
        return str(self.ml) if (k == 'maxlength' and self.ml) else None


cases = [
    (None,  'full',  '制限なし → 通常版'),
    (5000,  'full',  '上限5000 → 通常版'),
    (2000,  'full',  '上限2000（実測の中央値）→ 通常版'),
    (1021,  'full',  'ちょうど収まる → 通常版'),
    (1020,  'short', '1字足りない → 短縮版'),
    (500,   'short', '上限500（相模原市民文化財団）→ 短縮版'),
    (416,   'short', '短縮版ちょうど → 短縮版'),
    (415,   'empty', '短縮版も入らない → 空（=中止）'),
    (100,   'empty', '上限100（4社）→ 空（=中止）'),
]
ng = 0
for ml, want, desc in cases:
    notes = []
    got = fb.body_for(FakeEl(ml), profile, 'テスト団体', notes)
    kind = 'empty' if not got else ('full' if len(got) == full else 'short')
    ok = kind == want
    if not ok:
        ng += 1
    print(f'  {"OK" if ok else "NG"}  {desc:<38} → {kind:<6} {notes}')

print(f'\n{"全件OK" if ng == 0 else str(ng) + "件NG"}')

print('\n--- 会社名の差し込み ---')
b = profile['body'].replace('{会社名}', '公益財団法人テスト文化財団')
line = [l for l in b.split('\n') if 'この度' in l]
print(' ', line[0] if line else '(見つからない)')
assert '{会社名}' not in b, '差し込み漏れ'
print('  OK  差し込み漏れなし')
