#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""姓名が別欄のフォームで、氏名とフリガナが正しく割れるかを確かめる。"""
import importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('fb', os.path.join(HERE, 'form_bot.py'))
fb = importlib.util.module_from_spec(spec)
sys.modules['fb'] = fb
spec.loader.exec_module(fb)

print('--- 欄の見分け ---')
cases = [
    ('姓',                    'name_sei'),
    ('お名前（姓）',            'name_sei'),
    ('last_name',            'name_sei'),
    ('sei',                  'name_sei'),
    ('名',                    'name_mei'),
    ('first_name',           'name_mei'),
    ('mei',                  'name_mei'),
    ('フリガナ（セイ）',         'kana_sei'),
    ('kana_sei',             'kana_sei'),
    ('フリガナ 名',             'kana_mei'),
    ('furigana_mei',         'kana_mei'),
    # 分割していない普通の欄
    ('お名前',                'name'),
    ('氏名 必須',             'name'),
    ('フリガナ',               'name_kana'),
    # 取り違えてはいけないもの
    ('会社名',                'company'),
    ('団体名',                'company'),
    ('貴社名',                'company'),
    ('件名',                  'subject'),
    ('部署名',                'dept'),
    ('お問い合わせ内容',        'body'),
]
ng = 0
for text, want in cases:
    got = fb.classify(text)
    ok = got == want
    if not ok:
        ng += 1
    print(f'  {"OK" if ok else "NG"}  {text:<20} → {got}  (期待 {want})')
print(f'\n{"全件OK" if ng == 0 else str(ng) + "件NG"}')

print('\n--- 値の割り当て ---')
prof = json.load(open(os.path.join(HERE, 'profile.json'), encoding='utf-8'))
values = dict(prof['fields'])
for src, pre in (('name', 'name_'), ('name_kana', 'kana_')):
    parts = re.split(r'[\s　]+', str(values.get(src, '')).strip())
    if len(parts) >= 2:
        values[pre + 'sei'], values[pre + 'mei'] = parts[0], ' '.join(parts[1:])
    elif parts and parts[0]:
        values[pre + 'sei'] = parts[0]
for k in ('name', 'name_sei', 'name_mei', 'name_kana', 'kana_sei', 'kana_mei'):
    print(f'  {k:<10} {values.get(k, "(なし)")}')
assert values['name_sei'] == '石井' and values['name_mei'] == '啓章', '氏名の分割が違う'
assert values['kana_sei'] == 'イシイ' and values['kana_mei'] == 'タカアキ', 'フリガナの分割が違う'
print('\n  OK  姓名別欄・1欄まとめのどちらにも値がある')

print('\n--- 空白なしだったらどうなるか（旧データでの退行確認）---')
v2 = {'name': '石井啓章', 'name_kana': 'イシイタカアキ'}
for src, pre in (('name', 'name_'), ('name_kana', 'kana_')):
    parts = re.split(r'[\s　]+', v2[src].strip())
    if len(parts) >= 2:
        v2[pre + 'sei'], v2[pre + 'mei'] = parts[0], ' '.join(parts[1:])
    elif parts and parts[0]:
        v2[pre + 'sei'] = parts[0]
print(f"  name_sei={v2.get('name_sei')} / name_mei={v2.get('name_mei', '(なし)')}")
print('  → 名の欄が埋まらず、必須なら中止される（誤った値は入らない）')
