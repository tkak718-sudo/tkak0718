#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""クライアント候補を探して、フォーム入力に使えるCSVまで作る。

  起点URL → 相互リンクを辿って団体を集める
          → 各サイトから 電話/メール/問い合わせフォーム/設立年 を拾う
          → フォームが生きているか確かめる
          → 除外リストと突き合わせて既取得を落とす
          → 19列のCSVを書き出す

すべて GET のみ。送信は一切しない。

  python find_clients.py --seeds seeds.txt --exclude ..\除外リスト_最新.md \
         --genre アマチュアオーケストラ --out ..\新規候補.csv

seeds.txt は起点にするサイトのURLを1行1件。
同じ分野の団体は相互リンクを張り合っていることが多いので、数件あれば広がる。
"""
import argparse, csv, html, io, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from charset_normalizer import from_bytes

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
S = requests.Session()
S.headers.update({'User-Agent': UA, 'Accept-Language': 'ja,en;q=0.8'})

HEAD = ['会社名', '電話番号', 'メールアドレス', 'お問い合わせフォームURL', '担当者', 'ステータス',
        '事業内容', '売上規模', '創業年数', '上場区分', 'チケットツール', 'メモ', '業種', 'ランク',
        'イベント規模', '主催者', 'LINE公式', 'LINE公式アカウント情報', '判定根拠']

# 拾う団体の名前に含まれる語。分野を変えるときはここを差し替える
GROUP = re.compile(r'(交響楽団|管弦楽団|フィルハーモニ|オーケストラ|吹奏楽団|ウインドオーケストラ|'
                   r'ウィンドオーケストラ|ウインドアンサンブル|シンフォニエッタ|合唱団|コーラス|'
                   r'室内管弦楽|劇団|演劇|シアター|一座|人形劇|ミュージカル|バレエ団|舞踊|'
                   r'演劇鑑賞|市民劇場|音楽鑑賞|労音|能楽|太鼓|文化財団|文化振興)')
SKIP_HOST = re.compile(r'(twitter|x\.com|facebook|instagram|youtube|google|yahoo|amazon|rakuten|'
                       r'wikipedia|ameblo|jimdo|wixsite|note\.com|fc2|hatena|line\.me|tiktok|'
                       r'ticket|pia\.jp|eplus|l-tike|teket|peatix)', re.I)
# 学生団体は予算も決裁権もないため落とす。ac.jp ドメインも同様
SKIP_NAME = re.compile(r'(大学|大學|高校|高等学校|中学|学園|学院|学生|ジュニア|少年少女|'
                       r'こども|子ども|附属|付属|OB|OG|卒業生)')
LINKPAGE = re.compile(r'(link|links|リンク)', re.I)

TEL = re.compile(r'(?:TEL|Tel|tel|電話|代表)[^0-9]{0,8}(0\d{1,4}[-(）\-]\d{1,4}[-)）\-]\d{3,4})')
MAIL = re.compile(r'([A-Za-z0-9._%+\-]+)\s*(?:@|＠|\[at\]|\(at\))\s*([A-Za-z0-9.\-]+\.[A-Za-z]{2,})')
BAD_LOCAL = re.compile(r'^(example|sample|xxx+|your|name|user|test|dummy|noreply|no-reply)$', re.I)
BAD_DOM = re.compile(r'\.(png|jpg|jpeg|gif|webp|svg|css|js)$|^(example|sentry|wixpress|w3\.org)', re.I)
YEAR = re.compile(r'(?:設立|創業|創立)[^0-9]{0,12}((?:19|20)\d{2})\s*年')
CONTACT = re.compile(r'(contact|inquiry|toiawase|otoiawase|問合|問い合|form)', re.I)
CAPTCHA = re.compile(r'(recaptcha|g-recaptcha|hcaptcha|cf-turnstile|turnstile)', re.I)
NG_SALES = re.compile(r'(営業|勧誘|セールス|売り込み|広告)[^。、]{0,25}'
                      r'(お断り|ご遠慮|禁止|受け付け(ており)?ませ|お受けし(ており)?ませ|固くお断り)')
CORP = re.compile(r'(株式会社|（株）|\(株\)|㈱|有限会社|（有）|\(有\)|㈲|合同会社|（同）|'
                  r'一般社団法人|公益社団法人|一般財団法人|公益財団法人|特定非営利活動法人|NPO法人)')


def get(u, t=15):
    """https を先に試し、だめなら http も見る。
       小さな団体のサイトは http のままのことが多く、https 固定だと取りこぼす"""
    tries = [u]
    if u.startswith('http://'):
        tries = ['https://' + u[7:], u]
    elif u.startswith('https://'):
        tries = [u, 'http://' + u[8:]]
    for cand in tries:
        try:
            r = S.get(cand, timeout=t, allow_redirects=True)
            if r.status_code >= 400 or not r.content:
                continue
            raw = r.content[:400000]
            enc = r.encoding
            if not enc or enc.lower() == 'iso-8859-1':
                g = from_bytes(raw).best()
                enc = g.encoding if g else 'utf-8'
            return raw.decode(enc, errors='replace'), r.url
        except Exception:
            continue
    return None, None


def strip(h):
    h = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', h)))


# ------------------------------------------------------------------ 1. 集める

def harvest(seed):
    """1サイトのリンク集から、同じ分野の団体サイトを拾う"""
    out = {}
    h, fin = get(seed)
    if not h:
        return out
    base = fin or seed
    pages = [h]
    for m in re.finditer(r'href="([^"]+)"', h):
        u = m.group(1)
        if not LINKPAGE.search(u):
            continue
        u = urljoin(base, u)
        if urlparse(u).netloc != urlparse(base).netloc:
            continue
        hh, _ = get(u)
        if hh:
            pages.append(hh)
        if len(pages) >= 4:
            break
    for hh in pages:
        for m in re.finditer(r'<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', hh, re.S):
            url = m.group(1)
            lab = re.sub(r'\s+', '', html.unescape(re.sub(r'<[^>]+>', '', m.group(2)))).strip()
            if not lab or len(lab) > 30 or SKIP_HOST.search(url) or not GROUP.search(lab):
                continue
            if SKIP_NAME.search(lab) or re.search(r'\.ac\.jp', url, re.I):
                continue
            host = urlparse(url).netloc
            if host == urlparse(base).netloc:
                continue
            out[lab] = 'https://' + host
    return out


def crawl(seeds, waves):
    found, frontier = {}, list(seeds)
    for w in range(1, waves + 1):
        got = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            for d in ex.map(harvest, frontier):
                got.update(d)
        new = {k: v for k, v in got.items() if v not in set(found.values())}
        found.update(new)
        print(f'  第{w}波: {len(new)}件 追加（累計 {len(found)}件）')
        if not new:
            break
        frontier = list(new.values())[:60]
    return found


# ------------------------------------------------------------ 2. 連絡先を拾う

def pick_mail(h, host):
    got = re.findall(r'mailto:([^"\'?>\s]+)', h)
    for m in MAIL.finditer(strip(h)):
        got.append(m.group(1) + '@' + m.group(2))
    out = []
    for e in got:
        e = e.strip().strip('.,;')
        if '@' not in e:
            continue
        local, dom = e.rsplit('@', 1)
        if BAD_LOCAL.match(local) or BAD_DOM.search(dom) or len(local) > 40:
            continue
        out.append(e)
    base = '.'.join(host.split('.')[-2:])
    out.sort(key=lambda e: (base not in e.rsplit('@', 1)[1], len(e)))
    return out[0] if out else ''


def contacts(item):
    name, url = item
    rec = {'name': name, 'site': url, 'tel': '', 'mail': '', 'form': '',
           'founded': '', 'biz': '', 'captcha': False, 'ng': False}
    top, fin = get(url)
    if top is None:
        return None
    base = fin or url
    host = urlparse(base).netloc
    pages = [(base, top)]
    cands = [urljoin(base, m.group(1)) for m in re.finditer(r'href="([^"]+)"', top)
             if CONTACT.search(m.group(1))]
    # メールは問い合わせ頁だけでなく、規約・団員募集・団体概要にも載る。
    # 浅く見ると取りこぼすので、優先順を付けて広めに辿る
    cands += [urljoin(base, m.group(1)) for m in re.finditer(r'href="([^"]+)"', top)
              if re.search(r'(company|about|profile|outline|概要|会社|団体|privacy|policy|'
                           r'recruit|join|member|募集|入団|sitemap)', m.group(1), re.I)]
    seen_u = {base}
    for u in cands:
        if urlparse(u).netloc != host or u in seen_u:
            continue
        seen_u.add(u)
        hh, fu = get(u)
        if hh:
            pages.append((fu or u, hh))
        if len(pages) >= 12:
            break
    for u, h in pages:
        t = strip(h)
        if not rec['tel']:
            m = TEL.search(t)
            if m:
                rec['tel'] = m.group(1)
        if not rec['mail']:
            rec['mail'] = pick_mail(h, host)
        if not rec['founded']:
            m = YEAR.search(t)
            if m:
                rec['founded'] = m.group(1)
        if not rec['biz']:
            m = re.search(r'事業(?:内容|概要)[：:\s]{0,4}(.{10,60})', t)
            if m:
                rec['biz'] = m.group(1).strip()
        if not rec['form'] and CONTACT.search(u) and re.search(r'(?is)<form', h):
            rec['form'] = u
            rec['captcha'] = bool(CAPTCHA.search(h))
        if NG_SALES.search(t):
            rec['ng'] = True
    if not rec['form'] and cands:
        rec['form'] = cands[0]
    return rec


# ------------------------------------------------------ 3. 除外リストと突合

def norm(s):
    s = re.sub(r'[Ａ-Ｚａ-ｚ０-９]', lambda m: chr(ord(m.group(0)) - 0xFEE0), s)
    s = CORP.sub('', re.sub(r'[\s　]', '', s))
    for ch in '・･．.ー-‐':
        s = s.replace(ch, '')
    return s.lower()


def toks(s):
    outs = [s] + re.findall(r'[（(]([^）)]+)[）)]', s) + [re.sub(r'[（(][^）)]*[）)]', '', s)]
    return {norm(o) for o in outs if len(norm(o)) >= 2}


def load_exclude(paths):
    keys = set()
    for p in paths:
        if not os.path.exists(p):
            print(f'  (除外リストが見つかりません: {p})')
            continue
        for line in open(p, encoding='utf-8'):
            s = line.strip()
            if not s or s.startswith(('#', '**', '---', '- ')) or '/' not in s:
                continue
            for x in s.split('/'):
                x = x.strip()
                if x:
                    keys |= toks(x)
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


# ------------------------------------------------------------------- 実行

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', required=True, help='起点URLを1行1件で書いたテキスト')
    ap.add_argument('--exclude', nargs='*', default=[], help='除外リスト(.md)')
    ap.add_argument('--genre', default='', help='CSVの業種欄に入れる文字')
    ap.add_argument('--out', required=True)
    ap.add_argument('--waves', type=int, default=3, help='リンクを何段辿るか')
    ap.add_argument('--need-mail', action='store_true', help='メールがある先だけ残す')
    args = ap.parse_args()

    seeds = [l.strip() for l in open(args.seeds, encoding='utf-8') if l.strip() and not l.startswith('#')]
    print(f'起点 {len(seeds)}件から探します（GETのみ・送信なし）\n')

    print('■ 団体を集める')
    found = crawl(seeds, args.waves)
    if not found:
        sys.exit('見つかりませんでした。起点URLを増やしてください。')

    keys = load_exclude(args.exclude)
    print(f'\n■ 除外リストと突合（照合キー {len(keys)}件）')
    fresh = {k: v for k, v in found.items() if not is_dup(k, keys)}
    print(f'  {len(found)}件 → 既取得を除いて {len(fresh)}件')

    print(f'\n■ 連絡先を拾う（{len(fresh)}件）')
    with ThreadPoolExecutor(max_workers=10) as ex:
        recs = [r for r in ex.map(contacts, fresh.items()) if r]
    print(f'  到達できた {len(recs)}件')

    rows, drop_ng, drop_none, drop_mail = [], 0, 0, 0
    for r in recs:
        if r['ng']:
            drop_ng += 1
            continue
        if not r['mail'] and not r['form']:
            drop_none += 1
            continue
        if args.need_mail and not r['mail']:
            drop_mail += 1
            continue
        founded = ''
        if r['founded']:
            y = int(r['founded'])
            if 1900 <= y <= 2100:
                founded = f'{2026 - y}年'
        memo = 'フォームにreCAPTCHAあり' if r['captcha'] else ''
        rows.append([r['name'], r['tel'], r['mail'], r['form'], '', '',
                     (r['biz'] or '公演の企画・主催')[:58], '', founded, '', '', memo,
                     args.genre, '', '', '〇', '', '',
                     '自主公演を主催しチケットを自団体で扱う、公式サイトで確認'])

    rows.sort(key=lambda x: (x[2] == '', x[0]))
    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(HEAD)
        w.writerows(rows)

    print(f'\n■ 結果')
    print(f'  書き出し {len(rows)}件  （メールあり {sum(1 for r in rows if r[2])} '
          f'/ フォームのみ {sum(1 for r in rows if not r[2] and r[3])}）')
    print(f'  除外: 営業お断り {drop_ng} / 連絡手段なし {drop_none}'
          + (f' / メールなし {drop_mail}' if args.need_mail else ''))
    print(f'  CAPTCHAあり {sum(1 for r in rows if r[11])}件（自動送信できないので手動）')
    print(f'\n  {args.out}')


if __name__ == '__main__':
    main()
