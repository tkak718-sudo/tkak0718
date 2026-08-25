#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""問い合わせフォームの自動入力・自動送信。

既定は dry-run。送信するには --send と --yes の両方が要る。
誤送信を防ぐ仕掛けは PREFLIGHT（送信前チェック）と LEDGER（送信済み台帳）に集約した。

  python form_bot.py --csv 企業リスト.csv --profile profile.json            # 下見（送信しない）
  python form_bot.py --csv 企業リスト.csv --profile profile.json --test-url https://自社/contact
  python form_bot.py --csv 企業リスト.csv --profile profile.json --send --yes --limit 10
"""
import argparse, csv, hashlib, json, os, re, sys, time
from datetime import datetime, timezone
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------- 送信前チェック

# このいずれかがページにあれば送らない。営業を断っている相手に送るのが
# フォーム営業で最も苦情になるパターンなので、実行時オプションでは外せなくしてある。
NG_SALES = re.compile(
    r'(営業|勧誘|セールス|売り込み|広告)[^。、]{0,25}'
    r'(お断り|ご遠慮|禁止|受け付け(ており)?ませ|お受けし(ており)?ませ|固くお断り)'
    r'|(営業・勧誘目的|営業目的でのご利用)'
)
# 採用・サポート専用の窓口は用途が違うので送らない
NG_PURPOSE = re.compile(r'(採用|求人|エントリー|リクルート)[^。、]{0,15}(専用|に関するお問)'
                        r'|(技術|製品|カスタマー)?サポート専用'
                        r'|(取材|報道|プレス)専用')
NG_URL = re.compile(r'(recruit|saiyo|career|entry|support|helpdesk|press)', re.I)
# 問い合わせ窓口ではないフォーム。ここに営業文を入れると、相手側で実際の
# 予約・注文・寄付として処理されてしまうので、URLではなく項目名で見分ける。
NG_FORMTYPE = [
    ('予約・申込フォーム',
     r'(ご利用日|来店日|予約日|宿泊日|チェックイン|ご予約|予約フォーム|申込フォーム|'
     r'お申[しこ]み|申込書|参加申込|受講申込|キャンセル(?:料|ポリシー)|団体・?グループ)'),
    ('購入・注文フォーム',
     r'(カートに入れる|注文フォーム|ご注文|購入手続き|決済|お支払い方法|配送先)'),
    ('寄付・会員登録フォーム', r'(ご寄付|寄附|募金|入会申込|会員登録|入団申込)'),
    ('資料請求・見学申込', r'(資料請求フォーム|見学申込|体験申込|来場予約)'),
]
# これがあれば問い合わせ窓口とみなす（予約語と併存していても送信可とする）
OK_FORMTYPE = re.compile(r'(お問(?:い)?合わせ内容|お問合せ内容|ご質問|ご相談内容|'
                         r'メッセージ|お問い合わせ種別)')
CAPTCHA = re.compile(r'(recaptcha|g-recaptcha|hcaptcha|cf-turnstile|turnstile)', re.I)

# ---------------------------------------------------------------- 項目の対応付け

# 上から順に見て、最初に当たったものを採用する。
# name属性・id・placeholder・aria-label・直前のラベル文言をまとめて照合する。

# 姓と名が別欄のフォーム向け。カナ系を先に見るので、フリガナの姓名分割も拾える。
SEI = re.compile(r'(姓|苗字|名字|セイ|せい|last[-_]?name|lastname|family[-_]?name|(^|[-_])sei([-_]|$))', re.I)
MEI = re.compile(r'(メイ|めい|first[-_]?name|firstname|given[-_]?name|(^|[-_])mei([-_]|$))', re.I)
KANA = re.compile(r'(フリガナ|ふりがな|カナ|かな|kana|furigana|ruby)', re.I)
# 姓名の判定前に取り除く語。これを残すと「氏名」が「名」に化ける
STRIP = re.compile(r'(フリガナ|ふりがな|カナ|かな|kana|furigana|ruby|お名前|氏名|name)', re.I)
DECOR = re.compile(r'[\s　:：*＊（）()【】\[\]｜|/／必須任意入力]')


def split_kind(text):
    """姓／名のどちらを指す欄かを返す。判別できなければ None。
       「名」一文字は会社名・件名などと紛れるので、飾りを落として単独の「名」のときだけ拾う"""
    t = DECOR.sub('', STRIP.sub('', text))
    if SEI.search(text) or t == '姓':
        return 'sei'
    if MEI.search(text) or t == '名':
        return 'mei'
    return None


FIELDS = [
    ('company',  r'会社名|法人名|団体名|組織名|貴社名|御社名|企業名|company|corp|kaisha|soshiki'),
    ('dept',     r'部署|所属|部門|department|busho'),
    ('name_kana',r'(フリガナ|ふりがな|カナ|かな|kana|furigana)'),
    ('name',     r'(お?名前|氏名|担当者名|ご担当者|your[-_ ]?name|\bname\b|onamae|shimei)'),
    ('email2',   r'(メール|mail).{0,8}(確認|再入力|confirm)|confirm.{0,8}mail'),
    ('email',    r'(メール|mail|e-?mail|address)'),
    ('tel',      r'(電話|TEL|Tel|tel|phone|denwa)'),
    ('zip',      r'(郵便番号|〒|zip|postal)'),
    ('address',  r'(住所|所在地|address|jusho)'),
    ('url',      r'(URL|ホームページ|サイト|website|homepage)'),
    ('subject',  r'(件名|題名|タイトル|subject|title|用件)'),
    ('body',     r'(お問(い)?合わせ内容|お問合せ内容|内容|本文|ご相談|詳細|メッセージ|message|content|honbun|naiyo|備考)'),
]
# 選択肢から選ぶ「お問い合わせ種別」で、営業・提案に近いものを優先して選ぶ
CATEGORY_PREF = ['提案', '営業', 'サービス', '協業', 'ご提案', 'その他', 'そのほか', 'other']


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def key_of(company, url):
    """送信済み判定のキー。会社名とドメインの両方で見る"""
    host = urlparse(url).netloc.lower()
    name = re.sub(r'[\s　]', '', company)
    return hashlib.sha1(f'{name}|{host}'.encode()).hexdigest()[:16]


def find_file(name):
    """指定されたファイルを、実行フォルダ→スクリプトのフォルダ→その1つ上 の順に探す。
       置き場所を間違えても動くようにするため"""
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (name, os.path.join(here, os.path.basename(name)),
              os.path.join(here, '..', os.path.basename(name)), os.path.join(here, name)):
        if c and os.path.exists(c):
            return c
    return None


class Ledger:
    """送信済み台帳。二重送信を防ぐ唯一の拠り所なので、送信の直前と直後に書く"""

    def __init__(self, path):
        self.path = path
        self.done = {}
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self.done[r['key']] = r

    def sent(self, key):
        r = self.done.get(key)
        return bool(r) and r.get('phase') in ('submitting', 'sent')

    def write(self, rec):
        self.done[rec['key']] = rec
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def label_text(page, el):
    """その入力欄が何を指しているかを、拾えるだけ拾って1つの文字列にする"""
    bits = []
    for attr in ('name', 'id', 'placeholder', 'aria-label', 'title'):
        v = el.get_attribute(attr)
        if v:
            bits.append(v)
    try:
        eid = el.get_attribute('id')
        if eid:
            lab = page.query_selector(f'label[for="{eid}"]')
            if lab:
                bits.append(lab.inner_text())
        # ラベルで囲まれている書き方に加え、th/dt が入力欄の「ひとつ上の階層の
        # 直前の兄弟」になっている作り（表組み、dt/dd、見出しdiv+入力divの
        # 兄弟並びなど）を、決め打ちの階層ぶんだけ遡って探す
        t = el.evaluate("""e => {
            const L = e.closest('label');
            if (L) return L.innerText;
            let node = e;
            for (let i = 0; i < 4 && node; i++) {
                const prev = node.previousElementSibling;
                if (prev) {
                    const s = (prev.innerText || '').trim();
                    if (s && s.length <= 40) return s;
                } else if (node.parentElement) {
                    // 兄弟要素が無い場合、「<p>氏名<span>必須<input/></span></p>」
                    // のように、親要素の中で最初の子要素より前にある文字だけを見る
                    for (const child of node.parentElement.childNodes) {
                        if (child.nodeType === 3) {
                            const s = child.textContent.trim();
                            if (s) { if (s.length <= 40) return s; break; }
                        } else if (child.nodeType === 1) {
                            break;
                        }
                    }
                }
                node = node.parentElement;
            }
            return '';
        }""")
        if t:
            bits.append(t)
    except Exception:
        pass
    return ' '.join(bits)[:300]


def classify(text):
    # 会社名・団体名を「姓名の名」と取り違えないよう、先に通常の分類を当てる
    base = None
    for kind, pat in FIELDS:
        if re.search(pat, text, re.I):
            base = kind
            break
    if base in ('company', 'dept', 'subject', 'body', 'email', 'email2', 'tel', 'zip', 'address', 'url'):
        return base
    part = split_kind(text)
    if part:
        return ('kana_' if (base == 'name_kana' or KANA.search(text)) else 'name_') + part
    return base


def is_required(page, el):
    if el.get_attribute('required') is not None:
        return True
    try:
        t = el.evaluate("e => { const c = e.closest('td,dd,div,p,li'); return c ? c.innerText : ''; }")
        return bool(re.search(r'(必須|required|\*)', t or ''))
    except Exception:
        return False


def body_for(el, profile, company_name, notes):
    """その欄の maxlength に収まる本文を選ぶ。
       通常版 → 短縮版 → 極小版 の順に試し、どれも入らなければ空を返して中止させる。
       黙って切り詰めると文末の連絡先ごと消えるので、切らずに差し替える。"""
    try:
        ml = el.get_attribute('maxlength')
        lim = int(ml) if ml and int(ml) > 0 else None
    except (TypeError, ValueError):
        lim = None
    for key, label in (('body', ''), ('body_short', '短縮版'), ('body_mini', '極小版')):
        text = (profile.get(key) or '').replace('{会社名}', company_name)
        if not text:
            continue
        if lim is None or len(text) <= lim:
            if label:
                notes.append(f'本文を{label}に差し替え(上限{lim}字)')
            return text
    notes.append(f'本文が上限{lim}字に収まらない')
    return ''


def is_search_widget(el):
    """サイト内検索の入力欄かどうか。name/id/placeholderがs・q・searchのような
       検索特有の書き方で、囲むformにもsearchの印がある場合に絞って判定する
       (誤検出を避けるため、複数条件が揃ったときだけ真とする)"""
    try:
        name = (el.get_attribute('name') or '').strip().lower()
        eid = (el.get_attribute('id') or '').strip().lower()
        ph = (el.get_attribute('placeholder') or '')
        looks_like_search = (name in ('s', 'q', 'query', 'search', 'keyword') or
                              eid in ('s', 'q', 'search') or
                              re.search(r'検索|search', ph, re.I) is not None)
        if not looks_like_search:
            return False
        in_search_form = el.evaluate("""e => {
            const f = e.closest('form');
            if (!f) return false;
            const sig = (f.getAttribute('role') || '') + ' ' + (f.id || '') + ' ' +
                        (f.className || '') + ' ' + (f.action || '');
            return /search|検索/i.test(sig);
        }""")
        return bool(in_search_form)
    except Exception:
        return False


def fill_form(page, profile, company_name):
    """フォームに値を入れる。何をどこへ入れたかと、埋め残した必須項目を返す"""
    values = dict(profile['fields'])
    values['body'] = profile['body'].replace('{会社名}', company_name)
    values['subject'] = profile.get('subject', '').replace('{会社名}', company_name)
    # 姓名が別欄のフォーム向けに、空白区切りの氏名・フリガナを割る
    for src, pre in (('name', 'name_'), ('name_kana', 'kana_')):
        parts = re.split(r'[\s　]+', str(values.get(src, '')).strip())
        if len(parts) >= 2:
            values[pre + 'sei'], values[pre + 'mei'] = parts[0], ' '.join(parts[1:])
        elif parts and parts[0]:
            values[pre + 'sei'] = parts[0]
    notes = []

    filled, missing, seen = {}, [], set()
    for el in page.query_selector_all('input, textarea, select'):
        try:
            if not el.is_visible() or not el.is_enabled():
                continue
            typ = (el.get_attribute('type') or el.evaluate('e => e.tagName.toLowerCase()')).lower()
            if typ in ('hidden', 'submit', 'button', 'image', 'file', 'reset'):
                continue
            # サイト内検索ボックスは無視する。required属性が付いているだけで
            # お問い合わせフォームと誤認し、会社まるごと「必須項目が埋まらない」に
            # なってしまうサイトがある(WordPressテーマ等で時々見る)
            if typ == 'search' or is_search_widget(el):
                continue

            text = label_text(page, el)

            if typ == 'checkbox':
                # 個人情報の同意だけ入れる。メルマガ購読などは触らない
                if re.search(r'(同意|承諾|agree|consent|プライバシー|個人情報)', text, re.I):
                    if not el.is_checked():
                        el.check()
                    filled['agree'] = 'checked'
                continue
            if typ == 'radio':
                continue

            kind = classify(text)
            if not kind:
                if is_required(page, el):
                    missing.append(text[:40] or '(不明な必須項目)')
                continue

            if el.evaluate('e => e.tagName.toLowerCase()') == 'select':
                opts = el.query_selector_all('option')
                labels = [(o.inner_text().strip(), o.get_attribute('value')) for o in opts]
                pick = None
                for want in CATEGORY_PREF:
                    for lab, val in labels:
                        if want in lab and (val or '').strip():
                            pick = val
                            break
                    if pick:
                        break
                if pick is None and len(labels) > 1:
                    pick = labels[1][1]
                if pick is not None:
                    el.select_option(pick)
                    filled[kind] = pick
                continue

            if kind == 'body':
                v = body_for(el, profile, company_name, notes)
            else:
                v = values.get(kind if kind != 'email2' else 'email', '')
            if not v:
                if is_required(page, el) or kind == 'body':
                    missing.append(f'{kind}({text[:24]})')
                continue
            if kind in seen and kind not in ('email2',):
                continue
            el.fill(str(v))
            seen.add(kind)
            filled[kind] = str(v)[:60]
        except Exception:
            continue
    if notes:
        filled['_note'] = ' / '.join(notes)
    return filled, missing


def find_button(page, kinds):
    """確認ボタンと送信ボタンは別物。取り違えると1手で送信してしまうので分けて探す"""
    pats = {
        'confirm': r'(確認|内容を確認|入力内容の確認|次へ|confirm)',
        'submit':  r'(送信|送信する|この内容で送信|上記内容で送信|申し込む|submit|send)',
    }
    pat = pats[kinds]
    for el in page.query_selector_all(
            'button, input[type="submit"], input[type="button"], input[type="image"], a[role="button"]'):
        try:
            if not el.is_visible():
                continue
            t = (el.inner_text() or '') + ' ' + (el.get_attribute('value') or '') + ' ' + (el.get_attribute('alt') or '')
            if re.search(pat, t, re.I):
                # 「確認」を送信として拾わないように、送信探索では確認語を弾く
                if kinds == 'submit' and re.search(pats['confirm'], t, re.I) and not re.search(r'送信|submit|send', t, re.I):
                    continue
                return el, t.strip()[:30]
        except Exception:
            continue
    return None, ''


def pick_target(page):
    """フォームがまだ描画されていない/外部iframeに埋め込まれているページに対応する。
       (例1: React等で作られたページは読み込み後しばらくしてフォームを生成する
        例2: フォームメーラー等はページ本体ではなくiframe内にformを生成する
       どちらも、決め打ちの短い待ち時間だけ見ているとフォームが常に
       「見つからない」扱いになるので、見つかるまで少し待ちながら探す)"""
    def has_form(fr):
        try:
            return bool(fr.query_selector('form') or fr.query_selector('textarea'))
        except Exception:
            return False
    if has_form(page):
        return page
    for _ in range(5):
        page.wait_for_timeout(800)
        if has_form(page):
            return page
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            if has_form(fr):
                return fr
    return page


def preflight(page, url):
    """送信してよい相手かを判定する。ここで弾いたものは送信モードでも絶対に送らない"""
    try:
        text = page.inner_text('body')
    except Exception:
        text = ''
    html = page.content()
    ng = []
    if NG_SALES.search(text):
        ng.append('営業お断りの記載')
    if NG_PURPOSE.search(text) or NG_URL.search(urlparse(url).path):
        ng.append('採用/サポート/取材専用の窓口')
    if CAPTCHA.search(html):
        ng.append('CAPTCHAあり（自動送信しない）')
    if not page.query_selector('form') and not page.query_selector('textarea'):
        ng.append('フォームが見つからない')
    # 用途が問い合わせでないフォームは、URLでは見分けられないので項目名で判定する
    if not OK_FORMTYPE.search(text):
        for label, pat in NG_FORMTYPE:
            if re.search(pat, text):
                ng.append(f'{label}（問い合わせ窓口ではない）')
                break
    return ng


def run_one(page, row, profile, args, ledger, shot_dir):
    company = row['会社名']
    url = (row.get('お問い合わせフォームURL') or '').strip()
    key = key_of(company, url or company)
    base = {'key': key, 'company': company, 'url': url, 'time': now()}

    if not url:
        return {**base, 'phase': 'skip', 'reason': 'フォームURLなし'}
    if ledger.sent(key):
        return {**base, 'phase': 'skip', 'reason': '送信済み台帳にあり'}

    try:
        page.goto(url, timeout=args.timeout * 1000, wait_until='domcontentloaded')
        page.wait_for_timeout(1200)
    except PWTimeout:
        return {**base, 'phase': 'skip', 'reason': '読み込みタイムアウト'}
    except Exception as e:
        return {**base, 'phase': 'skip', 'reason': f'到達不可: {str(e)[:60]}'}

    # フォームが外部サービスのiframe埋め込みの場合、targetはそのiframe側になる
    target = pick_target(page)

    ng = preflight(target, url)
    if ng:
        return {**base, 'phase': 'skip', 'reason': ' / '.join(ng)}

    filled, missing = fill_form(target, profile, company)
    shot = os.path.join(shot_dir, f'{key}_filled.png')
    try:
        page.screenshot(path=shot, full_page=True)
    except Exception:
        shot = ''

    if missing:
        return {**base, 'phase': 'skip', 'reason': f'必須項目が埋まらない: {missing[:3]}',
                'filled': filled, 'shot': shot}
    if len(filled) < args.min_fields:
        return {**base, 'phase': 'skip', 'reason': f'入力できた項目が{len(filled)}件（下限{args.min_fields}）',
                'filled': filled, 'shot': shot}

    if args.assist:
        # 入力だけして、送信ボタンの手前で止める。押すのは人。
        # 確認画面を挟むフォームは「確認」まで進めておくと、人は最後の1押しで済む
        step = ''
        if args.to_confirm:
            btn, lab = find_button(target, 'confirm')
            if btn:
                try:
                    btn.click()
                    target.wait_for_load_state('domcontentloaded', timeout=args.timeout * 1000)
                    page.wait_for_timeout(1200)
                    step = f'／確認画面まで進めた（{lab}）'
                except Exception:
                    step = '／確認ボタンを押せなかった'
        sbtn, slab = find_button(target, 'submit')
        print(f'\n  ── {company}')
        print(f'     {url}')
        print(f'     入力: {", ".join(f"{k}={v}" for k, v in filled.items() if k != "_note")[:150]}')
        if filled.get('_note'):
            print(f'     注記: {filled["_note"]}')
        print(f'     送信ボタン: {slab or "見つからない（手で探してください）"}{step}')
        ans = input('     ブラウザで内容を確認し、送信したら Enter ／ '
                    '送らない場合は s ＋Enter ／ 中断は q ＋Enter > ').strip().lower()
        if ans == 'q':
            return {**base, 'phase': 'quit', 'reason': '操作者が中断',
                    'filled': filled, 'shot': shot}
        if ans == 's':
            return {**base, 'phase': 'skip', 'reason': '操作者が送らないと判断',
                    'filled': filled, 'shot': shot}
        try:
            after = os.path.join(shot_dir, f'{key}_after.png')
            page.screenshot(path=after, full_page=True)
            shot = after
        except Exception:
            pass
        rec = {**base, 'phase': 'sent-manual', 'reason': '操作者が送信',
               'filled': filled, 'shot': shot}
        ledger.write(rec)
        return rec

    if not args.send:
        return {**base, 'phase': 'dry-run', 'reason': '下見のみ。送信していない',
                'filled': filled, 'shot': shot}

    # ---- ここから先が実送信。台帳に submitting を先に書き、落ちても再送しない
    ledger.write({**base, 'phase': 'submitting', 'filled': filled})

    btn, lab = find_button(target, 'confirm')
    if btn:
        try:
            btn.click()
            target.wait_for_load_state('domcontentloaded', timeout=args.timeout * 1000)
            page.wait_for_timeout(1200)
        except Exception:
            pass
    sbtn, slab = find_button(target, 'submit')
    if not sbtn:
        rec = {**base, 'phase': 'failed', 'reason': '送信ボタンが見つからない', 'filled': filled, 'shot': shot}
        ledger.write(rec)
        return rec
    try:
        sbtn.click()
        try:
            target.wait_for_load_state('domcontentloaded', timeout=args.timeout * 1000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        try:
            body = target.inner_text('body')[:4000]
        except Exception:
            body = page.inner_text('body')[:4000]
        ok = bool(re.search(r'(送信(が)?完了|受け付けました|ありがとうございました|thank you|完了しました)', body, re.I))
        after = os.path.join(shot_dir, f'{key}_after.png')
        page.screenshot(path=after, full_page=True)
        rec = {**base, 'phase': 'sent' if ok else 'unknown', 'button': slab,
               'reason': '完了表示を確認' if ok else '完了表示を確認できず（要目視）',
               'filled': filled, 'shot': after}
    except Exception as e:
        rec = {**base, 'phase': 'unknown', 'reason': f'送信後の確認に失敗: {str(e)[:60]}',
               'filled': filled, 'shot': shot}
    ledger.write(rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', required=True, help='会社名とお問い合わせフォームURLを含むCSV')
    ap.add_argument('--profile', required=True, help='送信者情報と本文のJSON')
    ap.add_argument('--ledger', default='sent_ledger.jsonl')
    ap.add_argument('--out', default='result.csv')
    ap.add_argument('--shots', default='shots')
    ap.add_argument('--assist', action='store_true',
                    help='自動で入力し、送信ボタンの手前で止める。押すのは人（ブラウザは自動表示）')
    ap.add_argument('--to-confirm', action='store_true',
                    help='--assist のとき、確認画面のあるフォームは確認まで進めておく')
    ap.add_argument('--send', action='store_true', help='送信まで自動でやる')
    ap.add_argument('--yes', action='store_true', help='--send の確認。両方ないと送信しない')
    ap.add_argument('--test-url', help='本番前に自社フォームで1件だけ通す')
    ap.add_argument('--limit', type=int, default=20, help='1回の実行で扱う上限')
    ap.add_argument('--interval', type=float, default=45, help='送信間隔（秒）')
    ap.add_argument('--timeout', type=int, default=30)
    ap.add_argument('--min-fields', type=int, default=3, help='この数を下回る入力なら送らない')
    ap.add_argument('--headed', action='store_true', help='ブラウザを表示する')
    args = ap.parse_args()

    if args.send and not args.yes:
        sys.exit('送信するには --send と --yes の両方が必要です。まず --send なしで下見してください。')
    if args.assist and args.send:
        sys.exit('--assist と --send は同時に使えません。--assist は人が送信する方式です。')
    if args.assist:
        args.headed = True          # 画面が見えないと確認できないので必ず表示する
        args.interval = 0           # 人の操作待ちが間隔になる

    profile = json.load(open(args.profile, encoding='utf-8'))
    csv_path = find_file(args.csv)
    if not csv_path:
        sys.exit(f'CSVが見つかりません: {args.csv}\n'
                 f'  探した場所: このフォルダ / 1つ上のフォルダ\n'
                 f'  CSVファイルを form_bot.py と同じフォルダに置いてください。')
    rows = list(csv.DictReader(open(csv_path, encoding='utf-8-sig')))
    if args.test_url:
        rows = [{'会社名': '【テスト】自社フォーム', 'お問い合わせフォームURL': args.test_url}]
    rows = rows[:args.limit]

    os.makedirs(args.shots, exist_ok=True)
    ledger = Ledger(args.ledger)
    results = []

    with sync_playwright() as p:
        launch = {'headless': not args.headed}
        exe = os.environ.get('PW_CHROME')
        if exe:
            launch['executable_path'] = exe
        browser = p.chromium.launch(**launch)
        ctx = browser.new_context(locale='ja-JP',
                                  user_agent=('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                              '(KHTML, like Gecko) Chrome/125.0 Safari/537.36'))
        page = ctx.new_page()
        for i, row in enumerate(rows, 1):
            r = run_one(page, row, profile, args, ledger, args.shots)
            results.append(r)
            mark = {'sent': '送信', 'sent-manual': '手で送信', 'dry-run': '下見',
                    'skip': '除外', 'failed': '失敗', 'quit': '中断'}.get(r['phase'], r['phase'])
            print(f'[{i}/{len(rows)}] {mark}  {r["company"][:26]}  {r.get("reason","")}')
            if r['phase'] == 'quit':
                print('中断しました。ここまでの分は記録済みです。')
                break
            if args.send and r['phase'] in ('sent', 'unknown'):
                time.sleep(args.interval)
        browser.close()

    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['会社名', 'フォームURL', '結果', '理由', '入力内容', 'スクリーンショット', '時刻'])
        for r in results:
            w.writerow([r['company'], r['url'], r['phase'], r.get('reason', ''),
                        json.dumps(r.get('filled', {}), ensure_ascii=False), r.get('shot', ''), r['time']])

    n = lambda k: sum(1 for r in results if r['phase'] == k)
    if args.assist:
        print(f'\n手で送信 {n("sent-manual")} / 送らなかった {n("skip")} / 中断 {n("quit")}')
    else:
        print(f'\n下見 {n("dry-run")} / 送信 {n("sent")} / 要目視 {n("unknown")} '
              f'/ 除外 {n("skip")} / 失敗 {n("failed")}')
    print(f'結果: {args.out}   台帳: {args.ledger}   画面: {args.shots}/')


if __name__ == '__main__':
    main()
